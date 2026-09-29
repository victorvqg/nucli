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
