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
    "cd /tmp && git push --force",
    "true; git push origin main",
]


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


# --- auto-export de beads antes de versionar el JSONL ---


@pytest.fixture
def fake_run(monkeypatch):
    """Sustituye subprocess.run dentro del guard y registra las invocaciones."""
    calls: list[list[str]] = []

    def factory(returncode=0, stderr="", exc=None):
        def _run(cmd, **kwargs):
            calls.append(cmd)
            if exc is not None:
                raise exc
            return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)

        monkeypatch.setattr(guard.subprocess, "run", _run)
        return calls

    return factory


def test_git_add_del_jsonl_dispara_bd_export(fake_run, capsys):
    calls = fake_run()
    guard.current_branch = lambda: "feature/x"
    guard.check_bash(f"git add {guard.BEADS_JSONL}")
    assert ["bd", "export", "-o", guard.BEADS_JSONL] in calls
    assert capsys.readouterr().out == ""


def test_git_add_de_otro_archivo_no_dispara_export(fake_run, capsys):
    calls = fake_run()
    guard.current_branch = lambda: "feature/x"
    guard.check_bash("git add src/model.py")
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
