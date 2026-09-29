"""F7: el hook us-skill (PostToolUse i UserPromptExpansion) i nucli usage."""
import datetime
import json

import pytest

from conftest import escriu, git, nucli


def hook(entrada, cwd):
    return nucli("hook", "us-skill", cwd=cwd, entrada=json.dumps(entrada) if isinstance(entrada, dict) else entrada)


def usos(entorn):
    p = entorn / ".nucli/us.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def post_tool_use(skill, cwd):
    return {"hook_event_name": "PostToolUse", "tool_name": "Skill", "tool_input": {"skill": skill}, "cwd": str(cwd)}


def expansio(nom, cwd):
    return {"hook_event_name": "UserPromptExpansion", "command_name": nom, "command_args": [], "cwd": str(cwd),
            "expanded_prompt": "…"}


def test_skill_oberta_per_claude(fes_repo, entorn):
    arrel = fes_repo("marcador")
    r = hook(post_tool_use("tanca-sessio", arrel), arrel)
    assert r.returncode == 0 and r.stdout == ""
    [u] = usos(entorn)
    assert u["skill"] == "tanca-sessio" and u["repo"] == "marcador" and u["via"] == "claude"
    datetime.datetime.fromisoformat(u["data"])


def test_skill_escrita_per_l_usuari(fes_repo, entorn):
    arrel = fes_repo("marcador")
    hook(expansio("tanca-sessio", arrel), arrel)
    assert usos(entorn)[0]["via"] == "usuari"


def test_des_d_un_worktree_el_repo_es_el_principal(fes_repo, entorn):
    arrel = fes_repo("marcador")
    wt = arrel / ".claude/worktrees/x"
    git(arrel, "worktree", "add", "-q", "-b", "worktree-x", str(wt))
    hook(post_tool_use("pdf", wt), wt)
    assert usos(entorn)[0]["repo"] == "marcador"


def test_fora_d_un_repo_amb_nucli_no_escriu(fes_repo, entorn, tmp_path):
    sense = fes_repo("sense", config=None)
    hook(post_tool_use("pdf", sense), sense)
    hook(expansio("pdf", tmp_path), tmp_path)
    assert usos(entorn) == []


@pytest.mark.parametrize("entrada", [
    "no és json",
    {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "x"}},
    {"hook_event_name": "PostToolUse", "tool_name": "Skill", "tool_input": {}},
])
def test_entrades_que_no_compten(fes_repo, entorn, entrada):
    arrel = fes_repo()
    if isinstance(entrada, dict):
        entrada = dict(entrada, cwd=str(arrel))
    r = hook(entrada, arrel)
    assert r.returncode == 0 and r.stdout == "" and usos(entorn) == []


def test_usage(fes_repo, entorn):
    arrel = fes_repo("marcador")
    fa = lambda dies: (datetime.datetime.now().astimezone() - datetime.timedelta(days=dies)).isoformat(timespec="seconds")
    linies = [
        {"data": fa(1), "skill": "tanca-sessio", "repo": "marcador", "via": "claude"},
        {"data": fa(2), "skill": "tanca-sessio", "repo": "marcador", "via": "usuari"},
        {"data": fa(3), "skill": "pdf", "repo": "altre", "via": "claude"},
        {"data": fa(45), "skill": "xlsx", "repo": "marcador", "via": "claude"},
    ]
    escriu(entorn, ".nucli/us.jsonl", "\n".join(json.dumps(l) for l in linies) + "\nlínia trencada\n")
    for s in ("tanca-sessio", "pdf", "xlsx", "vella"):
        escriu(entorn, f".claude/skills/{s}/SKILL.md", "---\nname: x\n---\n")
    escriu(arrel, ".claude/skills/local/SKILL.md", "---\nname: local\n---\n")
    r = nucli("usage", cwd=arrel)
    assert r.returncode == 0, r.stderr
    assert "últims 30 dies · 3 usos" in r.stdout
    assert "tanca-sessio     2  (claude 1 · usuari 1)" in r.stdout
    assert "Sense cap ús en 30 dies: 3." in r.stdout
    for s in ("xlsx  (~/.claude/skills)", "vella  (~/.claude/skills)", "local  (marcador/.claude/skills)"):
        assert s in r.stdout
    assert "  pdf  (" not in r.stdout
    r = nucli("usage", "--dies", "60", cwd=arrel)
    assert "4 usos" in r.stdout and "Sense cap ús en 60 dies: 2." in r.stdout


def test_usage_funciona_fora_d_un_repo(tmp_path):
    r = nucli("usage", cwd=tmp_path)
    assert r.returncode == 0 and "0 usos" in r.stdout
