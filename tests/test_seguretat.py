"""v0.1.1: res de la branca s'executa fora del sandbox sense que una persona n'hagi llegit el diff.

- `nucli agent` no executa mai els checks `fora_sandbox` (ni cap altre): queden pendents al segell.
- `nucli finish` ensenya el diff contra la base, marca amb ⚠ els fitxers que formen part dels checks i demana
  confirmació [s/N] (no per defecte) abans d'executar res. Amb un sí, executa també els pendents i segella.
"""
import json
import os

import pytest

from conftest import commit, escriu, git, nucli
from test_ship import branques_remot, finish_amb_terminal

CONFIG = {
    "versio": 1,
    "branca_base": "main",
    "checks": {
        "lint": {"ordre": "bash scripts/check.sh"},
        "test": {"ordre": "cd lib && ls tests > /dev/null"},
        "smoke": {"ordre": "touch \"$HOME/smoke-executat\" && test ! -f \"$HOME/falla-smoke\"", "fora_sandbox": True},
    },
    "regles": [{"patrons": ["*.md"], "checks": []}, {"patrons": ["web/**"], "checks": ["lint", "smoke"]}],
    "per_defecte": ["lint", "test"],
}


@pytest.fixture
def gh_fals(tmp_path, monkeypatch):
    d = tmp_path / "bin-gh"
    d.mkdir()
    (d / "gh").write_text(f'#!/bin/bash\necho "$@" >> "{tmp_path}/gh.log"\n'
                          '[ "$1 $2" = "pr list" ] && echo "[]"; [ "$1 $2" = "pr create" ] && echo https://github.com/p/r/pull/1\n'
                          'exit 0\n')
    (d / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")


@pytest.fixture
def wt(fes_repo):
    """Una branca com la que deixa un agent: toca un script dels checks, tests, codi i web, i ha passat els
    checks de dins del sandbox. El smoke (fora_sandbox) no l'ha executat ningú."""
    arrel = fes_repo(config=CONFIG, fitxers={
        "scripts/check.sh": "echo check-ok\n", "lib/app.py": "x = 1\n", "lib/tests/test_a.py": "a = 1\n",
        "web/x.html": "<p>\n",
    })
    cami = arrel / ".claude/worktrees/feina"
    git(arrel, "worktree", "add", "-q", "-b", "worktree-feina", str(cami), "origin/main")
    escriu(cami, "scripts/check.sh", "echo check-ok\necho i una línia nova\n")
    escriu(cami, "lib/app.py", "x = 2\n")
    escriu(cami, "lib/tests/test_a.py", "a = 2\n")
    escriu(cami, "web/x.html", "<p>2\n")
    escriu(cami, "altres/test_b.py", "b = 1\n")
    commit(cami, "feat(web): canvi")
    for c in ("lint", "test"):
        assert nucli("ship", "run", c, cwd=cami).returncode == 0
    r = nucli("ship", "seal", cwd=cami)
    assert r.returncode == 0, r.stderr
    assert "Fora del sandbox, pendents: smoke. No els executa cap agent" in r.stdout
    return cami


def rebut(wt):
    return json.loads((wt / ".nucli/rebuts/worktree-feina.json").read_text())


def test_el_segell_deixa_pendents_els_fora_sandbox(wt, entorn):
    s = rebut(wt)["segell"]
    assert s["fora_sandbox_pendents"] == ["smoke"] and s["requerits"] == ["lint", "test", "smoke"]
    assert not (entorn / "smoke-executat").exists()


def test_un_check_de_dins_fallit_continua_sense_segell(fes_repo):
    arrel = fes_repo(config=CONFIG, fitxers={"scripts/check.sh": "exit 1\n", "lib/tests/t.py": ""})
    escriu(arrel, "lib/app.py", "x = 1\n")
    git(arrel, "checkout", "-q", "-b", "feina")
    commit(arrel, "feat: x")
    nucli("ship", "run", "lint", cwd=arrel)
    nucli("ship", "run", "test", cwd=arrel)
    r = nucli("ship", "seal", cwd=arrel)
    assert r.returncode == 1 and "lint: l'última execució ha fallat" in r.stderr


@pytest.mark.parametrize("resposta", ["\n", "n\n", "no\n", "potser\n"])
def test_finish_ensenya_el_diff_marca_i_per_defecte_no_fa_res(wt, entorn, gh_fals, resposta):
    abans = (wt / ".nucli/rebuts/worktree-feina.json").read_bytes()
    r = finish_amb_terminal(wt, resposta)
    assert r.returncode == 1 and "no confirmat: no he executat res ni pujat res" in r.stderr
    # el diff --stat contra la base
    assert "Canvis de la branca respecte de origin/main" in r.stdout and "5 files changed" in r.stdout
    # ⚠ als fitxers que formen part dels checks, i només a aquests
    assert "⚠ scripts/check.sh · l'executa el check lint" in r.stdout
    assert "⚠ lib/tests/test_a.py · és a lib/tests/, que fa servir el check test; test" in r.stdout
    assert "⚠ altres/test_b.py · test" in r.stdout
    assert "⚠ lib/app.py" not in r.stdout and "⚠ web/x.html" not in r.stdout
    assert "smoke (encara no s'ha executat). Has llegit el diff? [s/N]" in r.stdout
    # i no ha fet res: ni checks, ni rebut, ni push
    assert not (entorn / "smoke-executat").exists()
    assert (wt / ".nucli/rebuts/worktree-feina.json").read_bytes() == abans
    assert "worktree-feina" not in branques_remot(wt)


def test_finish_sense_terminal_no_executa_res(wt, entorn, gh_fals):
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "cal un terminal per confirmar l'execució fora del sandbox" in r.stderr
    assert "⚠ scripts/check.sh" in r.stdout  # el diff sí que l'ensenya
    assert not (entorn / "smoke-executat").exists()
    assert "worktree-feina" not in branques_remot(wt)


def test_finish_amb_un_si_executa_els_pendents_i_segella(wt, entorn, gh_fals):
    r = finish_amb_terminal(wt, "s\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (entorn / "smoke-executat").exists()
    dades = rebut(wt)
    assert [(e["check"], e["via"]) for e in dades["execucions"][-3:]] == [("lint", "finish"), ("test", "finish"),
                                                                          ("smoke", "finish")]
    assert dades["segell"]["fora_sandbox_pendents"] == [] and dades["segell"]["head"] == git(wt, "rev-parse", "HEAD")
    assert "Segellat · HEAD" in r.stdout and "worktree-feina" in branques_remot(wt)


def test_finish_amb_el_pendent_fallit_no_puja(wt, entorn, gh_fals):
    (entorn / "falla-smoke").write_text("")
    r = finish_amb_terminal(wt, "s\n")
    assert r.returncode == 1 and "smoke falla a l'execució contra HEAD (codi 1): no pujo res" in r.stderr
    assert rebut(wt)["segell"] is None and "worktree-feina" not in branques_remot(wt)


def test_finish_sense_checks_no_demana_res(fes_repo, gh_fals):
    arrel = fes_repo(config=CONFIG)
    git(arrel, "checkout", "-q", "-b", "docs")
    escriu(arrel, "NOTES.md", "nota\n")
    commit(arrel, "docs: una nota")
    assert nucli("ship", "seal", cwd=arrel).returncode == 0
    r = nucli("finish", cwd=arrel)  # sense terminal: no cal, perquè no s'executa res de la branca
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 file changed" in r.stdout and "Cap check automàtic requerit: no executo res de la branca." in r.stdout
    assert "[s/N]" not in r.stdout and "refs/heads/docs" in branques_remot(arrel)
