"""PreToolUse guard: bloquea acciones locales irreversibles y sincroniza beads.

GitHub protege el remoto (CI `test`, conversation resolution, no force-push). Este hook
cubre lo que la branch protection no puede:

- `gh pr merge --admin`, que saltea esos gates porque `enforce_admins` está en false.
- Force-push y push directo a `main`.
- `rm -rf`.
- Escritura a mano sobre credenciales y capas de datos generadas.

Además ejecuta `bd export` antes de versionar `.beads/issues.jsonl`: el export de beads es
diferido respecto de la DB, así que un `git add` inmediato puede versionar el estado anterior
y perder el cambio en silencio (ver DECISION_LOG y memoria `beads-bd-export-*`).

Contrato del hook: JSON por stdin. Silencio = decisión neutral (sigue el flujo normal de
permisos). Solo se emite `deny`; nunca `allow`, que auto-aprobaría saltándose los prompts.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# El hook puede correr con cualquier cwd; Claude Code exporta CLAUDE_PROJECT_DIR.
PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()

PROTECTED_BRANCHES = ("main", "master")

# Solo capas generadas + credenciales. `data/sources/` está versionado y se edita a mano.
BLOCKED_WRITE_PREFIXES = (
    "data/bronze/",
    "data/silver/",
    "data/gold/",
    "data/_metadata/",
    "outputs/",
)

BEADS_JSONL = ".beads/issues.jsonl"

# `MultiEdit` no existe en Claude Code 2.1.x, pero sí en otras versiones/harnesses. Incluirlo no
# cuesta nada y evita que la protección dependa de qué herramienta de edición esté disponible.
# Debe mantenerse sincronizado con el `matcher` de .claude/settings.json.
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


OPERATORS = {";", "&&", "||", "|", "&", "\n"}
NOISE_PREFIXES = ("sudo", "command", "time", "env", "nohup", "xargs")


def _segments(command: str) -> list[list[str]]:
    """Tokeniza respetando comillas y trocea por operadores de shell.

    Tokenizar ANTES de trocear es lo que importa. Si se parte la cadena por `;` o `|` primero,
    un `;` dentro de comillas rompe el string por la mitad y `echo "ojo con git push --force"`
    termina pareciendo un force-push. Con `punctuation_chars` el lexer emite los operadores como
    tokens propios y deja el texto citado como un único token inerte.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []

    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in OPERATORS:
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)

    out: list[list[str]] = []
    for seg in segments:
        while seg and (ENV_ASSIGN.match(seg[0]) or seg[0] in NOISE_PREFIXES):
            seg = seg[1:]
        if seg:
            out.append(seg)
    return out


def _invocations(command: str, *prefix: str) -> list[list[str]]:
    """Segmentos cuyo comando real es `prefix` (p.ej. ('git','push')). Devuelve sus argumentos."""
    n = len(prefix)
    return [t[n:] for t in _segments(command) if len(t) >= n and tuple(t[:n]) == prefix]


def _flags(args: list[str]) -> tuple[str, set[str]]:
    short = "".join(a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--"))
    long_flags = {a for a in args if a.startswith("--")}
    return short, long_flags


def is_recursive_force_rm(command: str) -> bool:
    for args in _invocations(command, "rm"):
        short, long_flags = _flags(args)
        recursive = "r" in short or "R" in short or "--recursive" in long_flags
        force = "f" in short or "--force" in long_flags
        if recursive and force:
            return True
    return False


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def current_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=PROJECT_ROOT,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _target_branch(refspec: str) -> str:
    """Rama destino de un refspec. `+HEAD:refs/heads/main` -> `main`."""
    dest = refspec.lstrip("+").split(":")[-1]
    return dest.removeprefix("refs/heads/")


def is_force_push(args: list[str]) -> bool:
    """Cubre `-f`, `--force`, `--force-with-lease[=<refname>[:<expect>]]` y el refspec `+rama`.

    `--no-force-with-lease` no cuenta: empieza con `--no`.
    """
    short, _ = _flags(args)
    if "f" in short:
        return True
    if any(a.startswith("--force") for a in args):
        return True
    return any(a.startswith("+") for a in args if not a.startswith("-"))


def pushes_to_protected(args: list[str]) -> bool:
    """True si el push apunta a main/master: por refspec explícito, o por la rama checkouteada.

    `git push` a secas y `git push -u origin HEAD` resuelven ambos a la rama actual, así que no
    alcanza con leer el comando: hay que preguntarle a git en qué rama estamos.
    """
    positional = [a for a in args if not a.startswith("-")]

    for arg in positional:
        if _target_branch(arg) in PROTECTED_BRANCHES:
            return True

    if current_branch() not in PROTECTED_BRANCHES:
        return False

    # En rama protegida, solo es seguro un refspec que nombre otro destino (`HEAD:feat`).
    return not any(":" in a for a in positional)


BROAD_ADD_FLAGS = {"-A", "--all", "-u", "--update", "--no-ignore-removal"}


def add_touches_beads(args: list[str]) -> bool:
    """True si el `git add` podría stagear el JSONL de beads.

    No alcanza con buscar la ruta literal: `git add .`, `git add -A` y `git add .beads` lo stagean
    igual, y son el flujo de commit más común.
    """
    if any(a in BROAD_ADD_FLAGS for a in args):
        return True

    paths = [a for a in args if not a.startswith("-")]
    if not paths:
        return True

    for path in paths:
        candidate = path.rstrip("/")
        if candidate in (".", ":/", ""):
            return True
        if candidate == BEADS_JSONL or BEADS_JSONL.startswith(f"{candidate}/"):
            return True
    return False


def export_beads() -> None:
    """Refresca el JSONL desde la DB antes de versionarlo. Si falla, deniega.

    Tragarse el error sería peor que no tener el hook: `git add` versionaría el JSONL viejo y el
    backlog remoto divergiría en silencio — el modo de falla exacto que esto viene a prevenir.
    """
    try:
        result = subprocess.run(
            ["bd", "export", "-o", BEADS_JSONL],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=PROJECT_ROOT,
        )
    except FileNotFoundError:
        deny(
            f"`bd` no está en PATH, así que no se pudo refrescar `{BEADS_JSONL}` antes de "
            "versionarlo. Instalá beads o quitá ese archivo del `git add`."
        )
    except subprocess.SubprocessError as exc:
        deny(f"`bd export` no pudo completarse ({type(exc).__name__}); `{BEADS_JSONL}` sin refrescar.")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        deny(
            f"`bd export` falló (exit {result.returncode}): {detail[-1] if detail else 'sin salida'}. "
            f"Versionar `{BEADS_JSONL}` ahora publicaría un backlog desactualizado."
        )


def check_bash(command: str) -> None:
    for args in _invocations(command, "gh", "pr", "merge"):
        if "--admin" in args:
            deny(
                "`gh pr merge --admin` saltea branch protection (enforce_admins=false): "
                "mergearía sin CI verde ni conversaciones de review resueltas. "
                "CLAUDE.md: «no se requiere --admin; si lo necesitas, algo está mal configurado»."
            )

    for args in _invocations(command, "git", "push"):
        if is_force_push(args):
            deny("Force-push denegado: reescribe historia publicada.")
        if pushes_to_protected(args):
            deny(
                "Push directo a una rama protegida. CLAUDE.md exige rama + PR + CI verde + "
                "conversaciones resueltas."
            )

    if is_recursive_force_rm(command):
        deny("`rm -rf` denegado: borrado recursivo irreversible. Borrá rutas concretas.")

    for args in _invocations(command, "git", "add"):
        if add_touches_beads(args):
            export_beads()


def check_write(file_path: str) -> None:
    if not file_path:
        return
    try:
        rel = Path(file_path).resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        rel = file_path

    name = Path(rel).name
    if name == ".env" or name.startswith(".env."):
        deny(f"Escritura a `{rel}` denegada: contiene credenciales (CDSE).")

    for prefix in BLOCKED_WRITE_PREFIXES:
        if rel.startswith(prefix):
            deny(
                f"Escritura a mano sobre `{rel}` denegada: `{prefix}` es una capa generada. "
                "Regenerala con el módulo del pipeline que la produce."
            )


def dispatch(payload: dict) -> None:
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool == "Bash":
        check_bash(tool_input.get("command", "") or "")
    elif tool in WRITE_TOOLS:
        check_write(tool_input.get("file_path", "") or "")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    dispatch(payload)


if __name__ == "__main__":
    main()
