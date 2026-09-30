"""F5: githooks/pre-push i githooks/commit-msg, i core.hooksPath a nucli init."""
import json
import os
import sys

import pytest

from conftest import ARREL_NUCLI, CONFIG_MINIMA, escriu, git, nucli, sh
from nucli import githooks

CONFIG = dict(CONFIG_MINIMA, tasques={"fitxer": "TASQUES.md", "prefix": "mt"})
GITHOOKS = str(ARREL_NUCLI / "githooks")


@pytest.fixture(autouse=True)
def nucli_al_path(tmp_path, monkeypatch):
    """Els githooks criden bin/nucli amb el python3 del PATH: en les proves, el de la suite."""
    d = tmp_path / "bin-py"
    d.mkdir()
    (d / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")


@pytest.fixture
def repo(fes_repo):
    arrel = fes_repo(config=CONFIG)
    git(arrel, "config", "core.hooksPath", GITHOOKS)
    return arrel


def fes_commit(arrel, missatge, env_extra=None, fitxer="f.txt"):
    escriu(arrel, fitxer, missatge)
    git(arrel, "add", "-A")
    env = dict(os.environ, **(env_extra or {}))
    return sh("git", "commit", "-q", "-m", missatge, cwd=arrel, check=False, env=env)


def excepcions(entorn):
    p = entorn / ".nucli/excepcions.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


# ---------- pre-push ----------

def test_push_a_main_bloquejat(repo):
    fes_commit(repo, "docs: una línia amb els canvis")
    r = sh("git", "push", "origin", "main", cwd=repo, check=False)
    assert r.returncode != 0 and "no es pot pujar directament a main" in r.stderr


def test_esborrar_main_bloquejat(repo):
    r = sh("git", "push", "origin", ":main", cwd=repo, check=False)
    assert r.returncode != 0 and "no es pot esborrar main" in r.stderr


def test_push_d_una_branca_passa(repo):
    git(repo, "checkout", "-q", "-b", "worktree-mt3")
    fes_commit(repo, "docs: canvi (mt3)")
    r = sh("git", "push", "origin", "worktree-mt3", cwd=repo, check=False)
    assert r.returncode == 0, r.stderr


def test_nucli_main_passa_i_s_anota(repo, entorn):
    fes_commit(repo, "docs: una línia amb els canvis")
    r = sh("git", "push", "origin", "main", cwd=repo, check=False, env=dict(os.environ, NUCLI_MAIN="1"))
    assert r.returncode == 0, r.stderr
    [e] = excepcions(entorn)
    assert e["tipus"] == "main" and e["branca"] == "main" and e["repo"] == repo.name and len(e["sha"]) == 40


def test_excepcio_no_anotable_no_es_concedeix(repo, entorn):
    (entorn / ".nucli").write_text("no és una carpeta")  # com al sandbox: ~/.nucli no s'hi pot escriure
    fes_commit(repo, "docs: una línia amb els canvis")
    r = sh("git", "push", "origin", "main", cwd=repo, check=False, env=dict(os.environ, NUCLI_MAIN="1"))
    assert r.returncode != 0 and "no la concedeixo" in r.stderr


def test_sense_nucli_json_no_fan_res(fes_repo):
    arrel = fes_repo("sense", config=None)
    git(arrel, "config", "core.hooksPath", GITHOOKS)
    assert fes_commit(arrel, "whatever I want").returncode == 0
    assert sh("git", "push", "origin", "main", cwd=arrel, check=False).returncode == 0


# ---------- commit-msg ----------

@pytest.mark.parametrize("missatge", [
    "feat(web): afegeix el mode fosc",
    "fix: el total dels partits surt amb decimals",
    "refactor(scraper)!: canvia `fetch_all` per la versió amb reintents",
    "docs: README",
    "Merge branch 'x' into main",
    'Revert "feat: x"',
    "fixup! feat(web): afegeix el mode fosc",
])
def test_missatges_valids(repo, missatge):
    r = fes_commit(repo, missatge)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("missatge, error", [
    ("afegeix el mode fosc", "ha de ser «tipus(àmbit): què»"),
    ("feature(web): afegeix el mode fosc", "ha de ser «tipus(àmbit): què»"),
    ("feat(web): add support for the dark mode", "no sembla en català (he vist: add, support, for, the)"),
    ("fix: corrige el total de los partidos", "no sembla en català (he vist: corrige, los)"),
])
def test_missatges_invalids(repo, missatge, error):
    r = fes_commit(repo, missatge)
    assert r.returncode != 0 and error in r.stderr
    assert "NUCLI_IDIOMA=0" in r.stderr or "idioma" not in error


def test_codi_entre_cometes_no_compta(repo):
    assert fes_commit(repo, "fix: `update the cache with new data` ara es fa sol").returncode == 0


def test_id_de_la_branca(repo):
    git(repo, "checkout", "-q", "-b", "worktree-mt12")
    r = fes_commit(repo, "fix(app): el total")
    assert r.returncode != 0 and "és de la tasca mt12" in r.stderr
    assert fes_commit(repo, "fix(app): el total (mt12)").returncode == 0
    git(repo, "checkout", "-q", "-b", "mt/mt13")
    assert fes_commit(repo, "fix(app): el total (mt13)", fitxer="g.txt").returncode == 0


# ---------- branques d'issue (v0.1.4) ----------

def fes_commit_amb_cos(arrel, missatge, fitxer="f.txt"):
    escriu(arrel, fitxer, missatge)
    git(arrel, "add", "-A")
    return sh("git", "commit", "-q", "-F", "-", cwd=arrel, check=False, entrada=missatge)


def test_branca_d_issue_exigeix_l_assumpte_acabat_en_numero(repo):
    git(repo, "checkout", "-q", "-b", "issue/12-arregla-el-total")
    r = fes_commit(repo, "fix(app): el total")
    assert r.returncode != 0
    assert "la branca issue/12-arregla-el-total és de l'issue #12: l'assumpte ha d'acabar en « (#12)»" in r.stderr
    assert fes_commit(repo, "fix(app): el total (#12)").returncode == 0


@pytest.mark.parametrize("missatge", [
    "fix(app): el total\n\nCloses #12\n",          # només al cos: un «Closes #N» no passa per l'id
    "fix(app): el total\n\nÉs la part (#12).\n",
    "fix(app): el total (#12) i el subtotal",        # al mig de l'assumpte, no al final
    "fix(app): el total (#123)",                     # un altre número
    "fix(app): el total(#12)",                       # sense l'espai
    "fix(app): el total #12",
    "fix(app): el total (12)",
])
def test_branca_d_issue_rebutja_el_numero_fora_del_final(repo, missatge):
    git(repo, "checkout", "-q", "-b", "issue/12-arregla-el-total")
    r = fes_commit_amb_cos(repo, missatge)
    assert r.returncode != 0 and "és de l'issue #12" in r.stderr


def test_branca_d_issue_amb_numero_al_final_i_cos(repo):
    git(repo, "checkout", "-q", "-b", "issue/12-arregla-el-total")
    assert fes_commit_amb_cos(repo, "fix(app): el total (#12)\n\nCloses #12\n").returncode == 0


@pytest.mark.parametrize("branca", ["issue/12", "worktree-issue-12", "worktree-issue-12-segona"])
def test_altres_formes_de_branca_d_issue(repo, branca):
    git(repo, "checkout", "-q", "-b", branca)
    r = fes_commit(repo, "fix(app): el total")
    assert r.returncode != 0 and "és de l'issue #12" in r.stderr
    assert fes_commit(repo, "fix(app): el total (#12)", fitxer="g.txt").returncode == 0


def test_l_issue_mana_sobre_la_tasca_del_nom(repo):
    """`issue/12-arregla-mt3` és de l'issue #12, no de la mt3."""
    git(repo, "checkout", "-q", "-b", "issue/12-arregla-mt3")
    r = fes_commit(repo, "fix(app): el total (mt3)")
    assert r.returncode != 0 and "és de l'issue #12" in r.stderr and "és de la tasca mt3" not in r.stderr
    assert fes_commit(repo, "fix(app): el total de la mt3 (#12)", fitxer="g.txt").returncode == 0


def test_les_mt_continuen_igual_amb_github_issues(fes_repo):
    cfg = dict(CONFIG_MINIMA, tasques={"font": "github-issues", "branca": "issue/", "fitxer": "TASQUES.md",
                                       "prefix": "mt"})
    arrel = fes_repo(config=cfg)
    git(arrel, "config", "core.hooksPath", GITHOOKS)
    git(arrel, "checkout", "-q", "-b", "mt/mt82")
    r = fes_commit(arrel, "fix(app): el total")
    assert r.returncode != 0 and "és de la tasca mt82" in r.stderr
    assert fes_commit(arrel, "fix(app): el total (mt82)").returncode == 0


def test_prefix_de_branca_de_nucli_json(fes_repo):
    cfg = dict(CONFIG_MINIMA, tasques={"font": "github-issues", "branca": "tasca/", "fitxer": "TASQUES.md",
                                       "prefix": "mt"})
    arrel = fes_repo(config=cfg)
    git(arrel, "config", "core.hooksPath", GITHOOKS)
    git(arrel, "checkout", "-q", "-b", "tasca/7-mode-fosc")
    r = fes_commit(arrel, "feat(web): mode fosc")
    assert r.returncode != 0 and "és de l'issue #7" in r.stderr
    assert fes_commit(arrel, "feat(web): mode fosc (#7)").returncode == 0


@pytest.mark.parametrize("branca, id_", [
    ("issue/12-arregla-el-total", "#12"), ("issue/12", "#12"), ("issue/012-x", "#12"), ("worktree-issue-12", "#12"),
    ("issue/12-arregla-mt3", "#12"), ("worktree-mt12", "mt12"), ("mt/mt13", "mt13"), ("feature/issue/12-x", None),
    ("issue/abc", None), ("issues/12-x", None), ("worktree-issue-x", None), ("main", None),
])
def test_id_de_branca(branca, id_):
    assert githooks.id_de_branca(branca, ["mt"], {}) == id_


def test_el_numero_de_l_issue_no_compta_com_a_paraula():
    assert githooks.paraules_estrangeres("afegeix el total (#12)")[2] == 3


def test_nucli_idioma_0_s_anota(repo, entorn):
    r = fes_commit(repo, "feat: add the new thing", env_extra={"NUCLI_IDIOMA": "0"})
    assert r.returncode == 0, r.stderr
    assert excepcions(entorn)[0]["tipus"] == "idioma"


@pytest.mark.parametrize("descripcio, resultat", [
    ("add support for dark mode", True),
    ("afegeix el suport per al mode fosc", False),
    ("mostra l'escut al capçal", False),
    ("canvi mínim", False),
    ("fix the bug", True),
])
def test_deteccio_d_idioma(descripcio, resultat):
    estrangeres, catalanes, total = githooks.paraules_estrangeres(descripcio)
    assert (total >= 3 and len(estrangeres) > len(catalanes)) is resultat


def test_encadena_el_hook_propi(repo):
    propi = repo / ".git/hooks/commit-msg"
    propi.write_text("#!/bin/sh\necho propi >> \"$(git rev-parse --git-dir)/propi.log\"\ngrep -q PROHIBIT \"$1\" && exit 3\nexit 0\n")
    propi.chmod(0o755)
    assert fes_commit(repo, "docs: primer canvi").returncode == 0
    assert (repo / ".git/propi.log").read_text() == "propi\n"
    r = fes_commit(repo, "docs: PROHIBIT pel hook propi", fitxer="g.txt")
    assert r.returncode != 0


# ---------- init ----------

def test_init_activa_el_hookspath(fes_repo):
    arrel = fes_repo(config=CONFIG)
    r = nucli("init", cwd=arrel)
    assert "activa    core.hooksPath" in r.stdout
    assert git(arrel, "config", "--local", "--get", "core.hooksPath") == GITHOOKS
    assert "ja hi és  core.hooksPath" in nucli("init", cwd=arrel).stdout


def test_init_respecta_un_hookspath_existent(fes_repo):
    arrel = fes_repo(config=CONFIG)
    git(arrel, "config", "core.hooksPath", ".husky")
    r = nucli("init", cwd=arrel)
    assert "avís      core.hooksPath · el repo ja en té un (.husky): no el trepitjo" in r.stdout
    assert git(arrel, "config", "--local", "--get", "core.hooksPath") == ".husky"


def test_init_corregeix_un_nucli_mogut(fes_repo, tmp_path):
    arrel = fes_repo(config=CONFIG)
    git(arrel, "config", "core.hooksPath", str(tmp_path / "vell" / "nucli" / "githooks"))
    r = nucli("init", cwd=arrel)
    assert "el nucli s'ha mogut" in r.stdout
    assert git(arrel, "config", "--local", "--get", "core.hooksPath") == GITHOOKS
