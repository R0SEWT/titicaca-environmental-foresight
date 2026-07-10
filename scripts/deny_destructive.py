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

# Config local del backend de beads. Está versionada, pero `gt rig add` (Gas Town) la reescribe en
# el clon: metadata.json pasa a `dolt_mode: server` y config.yaml gana `export.auto: "false"`.
# Commitear eso apaga el auto-export de beads para todo el repo — la misma divergencia silenciosa
# que arregló el PR #28. Ver tef-vtt.
BEADS_LOCAL_CONFIG = (".beads/config.yaml", ".beads/metadata.json")

# `MultiEdit` no existe en Claude Code 2.1.x, pero sí en otras versiones/harnesses. Incluirlo no
# cuesta nada y evita que la protección dependa de qué herramienta de edición esté disponible.
# Debe mantenerse sincronizado con el `matcher` de .claude/settings.json.
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


OPERATORS = {";", "&&", "||", "|", "&", "\n"}
WRAPPERS = ("sudo", "command", "time", "env", "nohup", "xargs", "doas")

# Flags de wrapper que consumen el token siguiente. Si no se descartan junto con su argumento,
# `sudo -u root rm -rf x` deja el segmento empezando en `-u` y el comando real queda invisible.
WRAPPER_FLAGS_WITH_ARG = {
    "-u", "-g", "-p", "-C", "-h", "-U", "-r", "-t", "-n",
    "--user", "--group", "--prompt", "--host", "--role", "--type",
}  # fmt: skip


def _strip_wrappers(seg: list[str]) -> list[str]:
    """Descarta prefijos inertes (`sudo`, `env`, asignaciones) y los flags que traigan."""
    while seg:
        if ENV_ASSIGN.match(seg[0]):
            seg = seg[1:]
            continue
        if seg[0] in WRAPPERS:
            seg = seg[1:]
            while seg and seg[0].startswith("-"):
                consume = 2 if seg[0] in WRAPPER_FLAGS_WITH_ARG and len(seg) > 1 else 1
                seg = seg[consume:]
            continue
        break
    return seg


def _tokenize(command: str) -> list[str]:
    """Tokeniza respetando comillas. Ante entrada malformada, falla CERRADO.

    `shlex` posix lanza ValueError con comillas sin cerrar. Devolver una lista vacía ahí
    desactivaría el guard entero: `git push origin main; echo it's fine` pasaría limpio, y el
    `bd export` previo al `git add` no correría. Un guard debe fallar cerrado, así que se degrada
    a un lexer más tolerante y, en última instancia, a un split ingenuo (que puede sobre-denegar,
    pero nunca deja pasar).
    """
    for posix in (True, False):
        lexer = shlex.shlex(command, posix=posix, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            return list(lexer)
        except ValueError:
            continue
    spaced = re.sub(r"(&&|\|\||[;|&\n])", r" \1 ", command)
    return spaced.split()


def _segments(command: str) -> list[list[str]]:
    """Tokeniza y trocea por operadores de shell.

    Tokenizar ANTES de trocear es lo que importa. Si se parte la cadena por `;` o `|` primero,
    un `;` dentro de comillas rompe el string por la mitad y `echo "ojo con git push --force"`
    termina pareciendo un force-push. Con `punctuation_chars` el lexer emite los operadores como
    tokens propios y deja el texto citado como un único token inerte.
    """
    tokens = _tokenize(command)

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
        stripped = _strip_wrappers(seg)
        if stripped:
            out.append(stripped)
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


def add_covers(args: list[str], target: str) -> bool:
    """True si el `git add` podría stagear `target`.

    No alcanza con buscar la ruta literal: `git add .`, `git add -A` y `git add .beads` stagean
    `.beads/issues.jsonl` igual, y son el flujo de commit más común.
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
        if candidate == target or target.startswith(f"{candidate}/"):
            return True
    return False


def is_dirty(rel_path: str) -> bool:
    """True si `rel_path` difiere de HEAD (en índice o en árbol de trabajo).

    Falla CERRADO: si git no responde, se asume sucio. Denegar un `git add` porque `git status`
    no corre es inocuo — con git roto el `git add` tampoco iba a funcionar.
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", rel_path],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=PROJECT_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if out.returncode != 0:
        return True
    return bool(out.stdout.strip())


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
        # El deny va ANTES del export: si `bd export` corriera igual, reescribiría el JSONL para
        # un `git add` que no se va a ejecutar.
        dirty = [p for p in BEADS_LOCAL_CONFIG if add_covers(args, p) and is_dirty(p)]
        if dirty:
            rutas = ", ".join(f"`{p}`" for p in dirty)
            deny(
                f"{rutas}: config local del backend de beads, modificada respecto de HEAD. "
                "Suele ser Gas Town (`gt rig add`) reescribiendo el clon: pone `dolt_mode: server` "
                'y `export.auto: "false"`. Commitearlo apagaría el auto-export de beads para todo '
                f"el repo. Descartá los cambios (`git restore {' '.join(dirty)}`) o stageá rutas "
                "concretas en vez de `git add .`."
            )

        if add_covers(args, BEADS_JSONL):
            export_beads()


def check_write(file_path: str) -> None:
    """Deniega escrituras a credenciales y capas generadas.

    Las rutas relativas se anclan a PROJECT_ROOT, no al cwd del proceso: el hook puede correr
    desde cualquier directorio, y resolver contra el cwd hacía que `./data/bronze/x.zip` escapara
    del prefijo bloqueado.
    """
    if not file_path:
        return

    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate = candidate.resolve()

    # Las credenciales se bloquean por nombre, esté el archivo donde esté.
    name = candidate.name
    if name == ".env" or name.startswith(".env."):
        deny(f"Escritura a `{name}` denegada: contiene credenciales (CDSE).")

    try:
        rel = candidate.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        # Fuera del repo: las capas generadas son un concepto relativo a este proyecto.
        return

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
