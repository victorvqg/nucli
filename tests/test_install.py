"""F8: install.sh contra un HOME temporal."""
import json
import os
import subprocess
import sys

import pytest

from conftest import ARREL_NUCLI, escriu

INSTALL = ARREL_NUCLI / "install.sh"
BIN = ARREL_NUCLI / "bin" / "nucli"
SKILL = ARREL_NUCLI / "skills" / "tanca-sessio"

SETTINGS = {
    "env": {"X": "1"},
    "permissions": {"allow": ["Bash(git add:*)"], "deny": ["Read(~/.ssh/**)"]},
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo meu"}]}]},
    "effortLevel": "high",
}


@pytest.fixture(autouse=True)
def python_al_path(tmp_path, monkeypatch):
    d = tmp_path / "bin-py"
    d.mkdir()
    (d / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")


def install(*args):
    return subprocess.run(["bash", str(INSTALL), *args], capture_output=True, text=True, env=dict(os.environ))


def settings(entorn):
    return json.loads((entorn / ".claude/settings.json").read_text())


def copies(entorn):
    return sorted(p.name for p in (entorn / ".claude").glob("settings.json.nucli-*.bak"))


def test_instal_la_i_es_idempotent(entorn):
    escriu(entorn, ".claude/settings.json", json.dumps(SETTINGS, indent=2) + "\n")
    escriu(entorn, ".claude/skills/pdf/SKILL.md", "---\nname: pdf\n---\n")
    r = install()
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.readlink(entorn / ".local/bin/nucli") == str(BIN)
    assert os.readlink(entorn / ".claude/skills/tanca-sessio") == str(SKILL)
    assert (entorn / ".claude/skills/pdf/SKILL.md").is_file()
    s = settings(entorn)
    for clau in ("env", "permissions", "effortLevel"):
        assert s[clau] == SETTINGS[clau]
    assert s["hooks"]["PreToolUse"][0] == SETTINGS["hooks"]["PreToolUse"][0]  # el teu hook, primer i intacte
    ordres = {e: [h["command"] for g in s["hooks"][e] for h in g["hooks"]] for e in s["hooks"]}
    assert f'"{BIN}" hook protegeix-rebuts' in ordres["PreToolUse"]
    assert ordres["PostToolUse"] == [f'"{BIN}" hook us-skill']
    assert ordres["UserPromptExpansion"] == [f'"{BIN}" hook us-skill']
    assert s["hooks"]["PreToolUse"][1]["matcher"] == "^(Edit|Write|NotebookEdit)$"
    assert s["hooks"]["PostToolUse"][0]["matcher"] == "^Skill$"
    assert len(copies(entorn)) == 1
    abans = (entorn / ".claude/settings.json").read_text()

    r = install()
    assert r.returncode == 0
    assert r.stdout.count("ja hi és") == 5  # ordre, skill i tres hooks
    assert (entorn / ".claude/settings.json").read_text() == abans and len(copies(entorn)) == 1


def test_dry_run_no_escriu_res(entorn):
    escriu(entorn, ".claude/settings.json", json.dumps(SETTINGS, indent=2) + "\n")
    abans = (entorn / ".claude/settings.json").read_text()
    r = install("--dry-run")
    assert r.returncode == 0, r.stderr
    assert "enllaça" in r.stdout and "afegeix   hook PreToolUse" in r.stdout
    assert any(l.strip().startswith("+") and "hook protegeix-rebuts" in l for l in r.stdout.splitlines())  # el diff
    assert not (entorn / ".local/bin/nucli").exists() and not (entorn / ".claude/skills/tanca-sessio").exists()
    assert (entorn / ".claude/settings.json").read_text() == abans and copies(entorn) == []


def test_sense_settings_el_crea(entorn):
    r = install()
    assert r.returncode == 0, r.stderr
    assert set(settings(entorn)) == {"hooks"} and copies(entorn) == []


def test_no_trepitja_el_que_no_es_seu(entorn):
    escriu(entorn, ".claude/skills/tanca-sessio/SKILL.md", "la meva\n")
    escriu(entorn, ".local/bin/nucli", "#!/bin/sh\necho altre\n")
    r = install()
    assert r.returncode == 0
    assert r.stdout.count("no és un enllaç del nucli: no el toco") == 2
    assert (entorn / ".claude/skills/tanca-sessio/SKILL.md").read_text() == "la meva\n"


def test_settings_trencat_no_el_toca(entorn):
    escriu(entorn, ".claude/settings.json", "{ trencat")
    r = install()
    assert r.returncode != 0 and "no és JSON vàlid" in r.stderr
    assert (entorn / ".claude/settings.json").read_text() == "{ trencat"


def test_clon_mogut_s_actualitza(entorn, tmp_path):
    vell = tmp_path / "vell" / "nucli"
    (vell / "bin").mkdir(parents=True)
    (entorn / ".local/bin").mkdir(parents=True)
    os.symlink(vell / "bin" / "nucli", entorn / ".local/bin/nucli")  # apunta a un clon que ja no hi és
    vells = dict(SETTINGS, hooks={"PostToolUse": [{"matcher": "^Skill$", "hooks": [
        {"type": "command", "command": f'"{vell}/bin/nucli" hook us-skill', "timeout": 10}]}]})
    escriu(entorn, ".claude/settings.json", json.dumps(vells, indent=2))
    r = install()
    assert r.returncode == 0, r.stderr
    assert os.readlink(entorn / ".local/bin/nucli") == str(BIN) and "el nucli s'ha mogut" in r.stdout
    s = settings(entorn)
    assert [h["command"] for g in s["hooks"]["PostToolUse"] for h in g["hooks"]] == [f'"{BIN}" hook us-skill']
    assert "actualitza hook PostToolUse" in r.stdout
