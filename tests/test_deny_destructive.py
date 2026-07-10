"""Tests del guard PreToolUse (`scripts/deny_destructive.py`).

El guard vive fuera del paquete, así que se carga por ruta. `current_branch()` se mockea en cada
test: si dependiera de la rama real, la suite pasaría en local (sobre `main`) y fallaría en CI
(sobre la rama del PR).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "scripts" / "deny_destructive.py"

_spec = importlib.util.spec_from_file_location("deny_destructive", GUARD_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
sys.modules["deny_destructive"] = guard
_spec.loader.exec_module(guard)

# El guard deriva PROJECT_ROOT de CLAUDE_PROJECT_DIR o del cwd; en tests lo fijamos al repo para
# que el veredicto no dependa de desde dónde se invoque pytest.
guard.PROJECT_ROOT = REPO_ROOT


def decide_bash(command: str, capsys, *, branch: str = "feature/x") -> str:
    """Devuelve 'deny' o 'neutral'. `deny()` imprime JSON y sale con SystemExit(0)."""
    guard.current_branch = lambda: branch
    try:
        guard.check_bash(command)
    except SystemExit:
        payload = json.loads(capsys.readouterr().out)
        return payload["hookSpecificOutput"]["permissionDecision"]
    return "neutral"


def decide_write(file_path: str, capsys) -> str:
    try:
        guard.check_write(file_path)
    except SystemExit:
        payload = json.loads(capsys.readouterr().out)
        return payload["hookSpecificOutput"]["permissionDecision"]
    return "neutral"


# Texto inerte dentro de comillas no debe disparar nada. Este era el bug original: trocear la
# cadena por `;` antes de tokenizar partía los strings citados por la mitad.
QUOTED_TEXT = [
    'echo "cuidado con git push --force"',
    'if [ -f /tmp/a ]; then echo "Bash(git push *)"; fi',
    'echo "nunca corras rm -rf /"',
    'printf "%s" "gh pr merge --admin"',
    "grep -f patrones.txt archivo",
]


@pytest.mark.parametrize("command", QUOTED_TEXT)
def test_texto_citado_no_dispara(command, capsys):
    assert decide_bash(command, capsys) == "neutral"


DESTRUCTIVE = [
    "gh pr merge 28 --squash --admin",
    "git push --force origin feat",
    "git push -f origin feat",
    "git push --force-with-lease",
    "git push origin main",
    "git push origin HEAD:main",
    "git push origin master",
    "rm -rf build",
    "rm -fr build",
    "rm -r -f build",
    "rm --recursive --force build",
    "sudo rm -rf /tmp/x",
    # Los flags del wrapper deben consumirse junto con su argumento, o el comando real queda
    # invisible tras `-u root` (hallado por Copilot en el PR #29).
    "sudo -u root rm -rf build",
    "sudo -E rm -rf build",
    "sudo -u root -E rm -rf build",
    "env FOO=bar rm -rf build",
    "cd /tmp && git push --force",
    "true; git push origin main",
    # Formas que el guard dejaba pasar (halladas por Codex en el PR #29).
    "git push --force-with-lease=feature origin feature",
    "git push --force-with-lease=feature:abc123 origin feature",
    "git push origin +feature",
    "git push origin HEAD:refs/heads/main",
    "git push origin refs/heads/master",
]


def test_no_force_with_lease_no_se_confunde_con_force(capsys):
    assert decide_bash("git push --no-force-with-lease origin feat", capsys) == "neutral"


# Una comilla sin cerrar hacía que shlex lanzara ValueError y `_segments` devolviera []. El guard
# quedaba inerte: no denegaba nada y tampoco corría `bd export`. Debe fallar CERRADO.
MALFORMADOS_DESTRUCTIVOS = [
    "git push origin main; echo it's fine",
    "rm -rf build; echo don't",
    'git push --force origin feat && echo "sin cerrar',
    "gh pr merge 1 --admin; echo can't stop me",
]


@pytest.mark.parametrize("command", MALFORMADOS_DESTRUCTIVOS)
def test_comillas_rotas_no_desactivan_el_guard(command, capsys):
    assert decide_bash(command, capsys, branch="main") == "deny"


def test_comillas_rotas_no_impiden_el_export_de_beads(fake_run, capsys):
    calls = fake_run()
    guard.current_branch = lambda: "feature/x"
    guard.check_bash(f"git add {guard.BEADS_JSONL} && echo \"sin cerrar")
    assert ["bd", "export", "-o", guard.BEADS_JSONL] in calls


@pytest.mark.parametrize("command", DESTRUCTIVE)
def test_comandos_destructivos_denegados(command, capsys):
    assert decide_bash(command, capsys) == "deny"


SAFE = [
    "git push origin HEAD:feat",
    "gh pr merge 28 --squash",
    "git commit -m mensaje",
    "rm -f /tmp/x",
    "git status --short",
    "uv run pytest -q",
]


@pytest.mark.parametrize("command", SAFE)
def test_comandos_seguros_pasan(command, capsys):
    assert decide_bash(command, capsys) == "neutral"


# `git push` y `git push -u origin HEAD` resuelven a la rama checkouteada: el veredicto depende
# de dónde estemos parados, no del texto del comando.
@pytest.mark.parametrize("command", ["git push", "git push -u origin HEAD", "git push origin"])
def test_push_implicito_depende_de_la_rama(command, capsys):
    assert decide_bash(command, capsys, branch="main") == "deny"
    assert decide_bash(command, capsys, branch="feature/x") == "neutral"


BLOCKED_WRITES = [
    ".env",
    ".env.local",
    "data/bronze/x.zip",
    "data/silver/x.parquet",
    "data/gold/x.tif",
    "data/_metadata/authorship.tsv",
    "outputs/trophic_risk.json",
]


@pytest.mark.parametrize("rel", BLOCKED_WRITES)
def test_escrituras_bloqueadas(rel, capsys):
    assert decide_write(str(guard.PROJECT_ROOT / rel), capsys) == "deny"


# `data/sources/` está versionado y se edita a mano (CSVs transcritos): no debe bloquearse.
ALLOWED_WRITES = [
    "data/sources/peblt.csv",
    "src/titicaca_environmental_foresight/model.py",
    "docs/DECISION_LOG.md",
    "tests/test_model.py",
]


@pytest.mark.parametrize("rel", ALLOWED_WRITES)
def test_escrituras_permitidas(rel, capsys):
    assert decide_write(str(guard.PROJECT_ROOT / rel), capsys) == "neutral"


# El hook corre con cualquier cwd. Si `check_write` resolviera las rutas relativas contra el cwd
# del proceso, `./data/bronze/x.zip` escaparía del prefijo bloqueado (hallado por Copilot, #29).
RELATIVAS_BLOQUEADAS = [
    "data/bronze/x.zip",
    "./data/bronze/x.zip",
    "./outputs/a.json",
    "data/gold/../gold/x.tif",
    "./.env",
    ".env",
]


@pytest.mark.parametrize("rel", RELATIVAS_BLOQUEADAS)
def test_rutas_relativas_se_anclan_al_repo(rel, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert decide_write(rel, capsys) == "deny"


@pytest.mark.parametrize("rel", ["./src/model.py", "docs/DECISION_LOG.md", "./data/sources/x.csv"])
def test_rutas_relativas_permitidas_siguen_pasando(rel, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert decide_write(rel, capsys) == "neutral"


def test_env_se_bloquea_este_donde_este(capsys):
    """Las credenciales se bloquean por nombre, aunque el path caiga fuera del repo."""
    assert decide_write("/home/otro/proyecto/.env", capsys) == "deny"


def test_archivo_ajeno_fuera_del_repo_no_es_asunto_del_guard(capsys):
    assert decide_write("/home/otro/proyecto/data/bronze/x.zip", capsys) == "neutral"


# --- despacho por herramienta ---


@pytest.mark.parametrize("tool", guard.WRITE_TOOLS)
def test_toda_herramienta_de_escritura_pasa_por_check_write(tool, capsys):
    payload = {"tool_name": tool, "tool_input": {"file_path": str(guard.PROJECT_ROOT / ".env")}}
    guard.current_branch = lambda: "feature/x"
    with pytest.raises(SystemExit):
        guard.dispatch(payload)
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_el_matcher_del_settings_cubre_todas_las_write_tools():
    """Si el matcher y WRITE_TOOLS se desincronizan, el guard nunca se invoca para la que falte."""
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    matchers = [g["matcher"] for g in settings["hooks"]["PreToolUse"]]
    cubiertas = {tool for m in matchers for tool in m.split("|")}
    assert set(guard.WRITE_TOOLS) <= cubiertas
    assert "Bash" in cubiertas


# --- auto-export de beads antes de versionar el JSONL ---


@pytest.fixture
def fake_run(monkeypatch):
    """Sustituye subprocess.run dentro del guard y registra las invocaciones.

    `git status` se responde aparte de `bd export`: `dirty` lista las rutas que el guard debe
    ver como modificadas, y `status_rc` permite simular que git falla. Así `exc`/`returncode`
    siguen describiendo solo al `bd export`, como en los tests que ya existían.
    """
    calls: list[list[str]] = []

    def factory(returncode=0, stderr="", exc=None, dirty=(), status_rc=0):
        def _run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "status"]:
                path = cmd[-1]
                out = f" M {path}\n" if path in dirty else ""
                return SimpleNamespace(returncode=status_rc, stdout=out, stderr="")
            if exc is not None:
                raise exc
            return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)

        monkeypatch.setattr(guard.subprocess, "run", _run)
        return calls

    return factory


# `git add .` y `git add -A` stagean el JSONL igual que nombrarlo: son el flujo de commit más
# común, y el guard los ignoraba (hallado por Codex en el PR #29).
ADD_QUE_TOCA_BEADS = [
    ".beads/issues.jsonl",
    ".",
    "./",
    "-A",
    "--all",
    "-u",
    ".beads",
    ".beads/",
    "-A .beads",
    "src/model.py .beads/issues.jsonl",
]


@pytest.mark.parametrize("pathspec", ADD_QUE_TOCA_BEADS)
def test_git_add_que_toca_beads_dispara_export(pathspec, fake_run, capsys):
    calls = fake_run()
    guard.current_branch = lambda: "feature/x"
    guard.check_bash(f"git add {pathspec}")
    assert ["bd", "export", "-o", guard.BEADS_JSONL] in calls
    assert capsys.readouterr().out == ""


ADD_QUE_NO_TOCA_BEADS = ["src/model.py", "docs/DECISION_LOG.md", "tests/", "src docs"]


@pytest.mark.parametrize("pathspec", ADD_QUE_NO_TOCA_BEADS)
def test_git_add_de_otros_archivos_no_dispara_export(pathspec, fake_run, capsys):
    calls = fake_run()
    guard.current_branch = lambda: "feature/x"
    guard.check_bash(f"git add {pathspec}")
    assert calls == []


def test_export_fallido_deniega_el_git_add(fake_run, capsys):
    fake_run(returncode=1, stderr="dolt: database is locked")
    with pytest.raises(SystemExit):
        guard.check_bash(f"git add {guard.BEADS_JSONL}")
    payload = json.loads(capsys.readouterr().out)
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "database is locked" in reason


def test_bd_ausente_deniega_el_git_add(fake_run, capsys):
    fake_run(exc=FileNotFoundError())
    with pytest.raises(SystemExit):
        guard.check_bash(f"git add {guard.BEADS_JSONL}")
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "PATH" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_timeout_de_export_deniega_el_git_add(fake_run, capsys):
    fake_run(exc=subprocess.TimeoutExpired(cmd="bd", timeout=30))
    with pytest.raises(SystemExit):
        guard.check_bash(f"git add {guard.BEADS_JSONL}")
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"


# --- config local de backend que Gas Town reescribe en el clon (tef-vtt) ---
#
# `gt rig add` muta archivos VERSIONADOS: metadata.json pasa a dolt_mode=server y config.yaml
# gana `export.auto: "false"`. Si un polecat los commitea, el auto-export de beads queda apagado
# para todos. Solo se deniega cuando están realmente modificados: `git add .` con el árbol limpio
# es el flujo de commit normal y debe seguir pasando.

CONFIG = ".beads/config.yaml"
METADATA = ".beads/metadata.json"


@pytest.mark.parametrize("pathspec", [".", "-A", "--all", "-u", ".beads", ".beads/", CONFIG])
def test_git_add_de_config_local_modificada_se_deniega(pathspec, fake_run, capsys):
    fake_run(dirty={CONFIG})
    guard.current_branch = lambda: "feature/x"
    with pytest.raises(SystemExit):
        guard.check_bash(f"git add {pathspec}")
    payload = json.loads(capsys.readouterr().out)
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert CONFIG in reason
    assert "restore" in reason


def test_metadata_modificada_tambien_se_deniega(fake_run, capsys):
    fake_run(dirty={METADATA})
    guard.current_branch = lambda: "feature/x"
    with pytest.raises(SystemExit):
        guard.check_bash("git add .")
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert METADATA in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_se_deniega_antes_de_exportar_beads(fake_run, capsys):
    """El deny no debe dejar rastro: si igual corriera `bd export`, reescribiría el JSONL."""
    calls = fake_run(dirty={CONFIG})
    guard.current_branch = lambda: "feature/x"
    with pytest.raises(SystemExit):
        guard.check_bash("git add .")
    assert not any(cmd[:2] == ["bd", "export"] for cmd in calls)


def test_git_add_con_config_limpia_no_se_deniega(fake_run, capsys):
    """Falso positivo a evitar: `git add .` con el árbol limpio es el flujo normal."""
    calls = fake_run(dirty=set())
    guard.current_branch = lambda: "feature/x"
    guard.check_bash("git add .")
    assert capsys.readouterr().out == ""
    assert ["bd", "export", "-o", guard.BEADS_JSONL] in calls


@pytest.mark.parametrize("pathspec", ["src/model.py", "docs/DECISION_LOG.md", "tests/"])
def test_add_que_no_cubre_la_config_no_se_deniega_aunque_este_sucia(pathspec, fake_run, capsys):
    fake_run(dirty={CONFIG, METADATA})
    guard.current_branch = lambda: "feature/x"
    guard.check_bash(f"git add {pathspec}")
    assert capsys.readouterr().out == ""


def test_git_status_fallido_deniega_el_git_add(fake_run, capsys):
    """Fail closed: sin poder saber si la config está sucia, no se stagea."""
    fake_run(status_rc=128)
    guard.current_branch = lambda: "feature/x"
    with pytest.raises(SystemExit):
        guard.check_bash("git add .")
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
