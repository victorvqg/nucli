"""v0.1.4: `nucli tasca N` comença l'issue #N en una sessió (branca issue/N-… des de la base i «estat: en-curs»)."""
import json
import os
import sys

import pytest

from conftest import ARREL_NUCLI, CONFIG_MINIMA, commit, escriu, git, nucli, sh
from nucli.tasca import slug

CONFIG = dict(CONFIG_MINIMA, tasques={"font": "github-issues", "branca": "issue/", "fitxer": "TASQUES.md",
                                      "prefix": "mt"})
ISSUE = {"number": 12, "title": "Arregla el total dels partits", "state": "OPEN",
         "labels": [{"name": "tasca"}, {"name": "estat: aprovada"}, {"name": "P1"}, {"name": "interactiu"}]}


@pytest.fixture
def gh_fals(tmp_path, monkeypatch):
    """gh simulat: `issue view` torna gh-issue.json (o falla si no hi és); `issue edit` falla si hi ha gh-edit-falla."""
    d = tmp_path / "bin-gh"
    d.mkdir()
    registre, dades, falla = tmp_path / "gh.log", tmp_path / "gh-issue.json", tmp_path / "gh-edit-falla"
    (d / "gh").write_text(f"""#!/bin/bash
echo "$@" >> "{registre}"
case "$1 $2" in
  "issue view") if [ -f "{dades}" ]; then cat "{dades}"; else echo "no trobo l'issue" >&2; exit 1; fi ;;
  "issue edit") if [ -f "{falla}" ]; then echo "'estat: en-curs' not found" >&2; exit 1; fi ;;
esac
""")
    (d / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    dades.write_text(json.dumps(ISSUE))
    return {"registre": registre, "dades": dades, "falla": falla}


@pytest.fixture
def repo(fes_repo):
    return fes_repo(config=CONFIG, fitxers={"app.py": "x = 1\n"})


def ordres_gh(gh_fals):
    return gh_fals["registre"].read_text().splitlines() if gh_fals["registre"].exists() else []


@pytest.mark.parametrize("titol, esperat", [
    ("Arregla el total dels partits", "arregla-el-total-dels-partits"),
    ("Mostra l'escut al capçal", "mostra-l-escut-al-capcal"),
    ("Col·legi — àrbitres i ÀRBITRES", "collegi-arbitres-i-arbitres"),
    ("mt77 · Robot, part B, tasca 2: aplicar i provar la 051…", "mt77-robot-part-b-tasca-2-aplicar-i-prov"),  # tallat a 40, com sigui
    ("  --Hola, món!--  ", "hola-mon"),
    ("a" * 39 + " b", "a" * 39),  # tallat a 40 i sense «-» al final
    ("🎉🎉", "tasca"),
    ("", "tasca"),
])
def test_slug(titol, esperat):
    assert slug(titol) == esperat
    assert len(slug(titol)) <= 40


@pytest.mark.parametrize("arg", ["12", "#12"])
def test_cami_bo(repo, gh_fals, arg):
    r = nucli("tasca", arg, cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    branca = "issue/12-arregla-el-total-dels-partits"
    assert git(repo, "branch", "--show-current") == branca
    assert git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")
    assert sh("git", "rev-parse", "--abbrev-ref", "@{u}", cwd=repo, check=False).returncode != 0  # no segueix main
    assert ordres_gh(gh_fals) == ["issue view 12 --json number,title,state,labels",
                                  "issue edit 12 --add-label estat: en-curs --remove-label estat: aprovada"]
    assert f"branca {branca} creada des de origin/main" in r.stdout
    assert "issue #12: «estat: en-curs» (abans: estat: aprovada)" in r.stdout
    assert "tipus(àmbit): què (#12)" in r.stdout and "Closes #12" in r.stdout


def test_parteix_de_la_base_del_remot_al_dia(repo, gh_fals, tmp_path):
    """Fa `git fetch` abans: la branca surt de l'origin/main d'ara, no de la còpia vella."""
    altre = tmp_path / "altre"
    git(tmp_path, "clone", "-q", str(tmp_path / "repo-origin.git"), str(altre))
    escriu(altre, "b.txt", "nou\n")
    nou = commit(altre, "feat: un canvi d'algú altre")
    git(altre, "push", "-q", "origin", "main")
    assert git(repo, "rev-parse", "origin/main") != nou
    r = nucli("tasca", "12", cwd=repo)
    assert r.returncode == 0, r.stderr
    assert git(repo, "rev-parse", "HEAD") == nou


def test_amb_el_prefix_de_nucli_json(fes_repo, gh_fals):
    cfg = dict(CONFIG, tasques=dict(CONFIG["tasques"], branca="tasca/"))
    arrel = fes_repo(config=cfg)
    assert nucli("tasca", "12", cwd=arrel).returncode == 0
    assert git(arrel, "branch", "--show-current") == "tasca/12-arregla-el-total-dels-partits"


def test_sense_font_github_issues_fa_servir_issue(fes_repo, gh_fals):
    arrel = fes_repo(config=dict(CONFIG_MINIMA, tasques={"fitxer": "TASQUES.md", "prefix": "mt"}))
    assert nucli("tasca", "12", cwd=arrel).returncode == 0
    assert git(arrel, "branch", "--show-current") == "issue/12-arregla-el-total-dels-partits"


def test_issue_tancat(repo, gh_fals):
    gh_fals["dades"].write_text(json.dumps(dict(ISSUE, state="CLOSED")))
    r = nucli("tasca", "12", cwd=repo)
    assert r.returncode == 1 and "l'issue #12 no és obert (CLOSED)" in r.stderr
    assert git(repo, "branch", "--show-current") == "main" and len(ordres_gh(gh_fals)) == 1


@pytest.mark.parametrize("existent, on", [
    ("issue/12-un-titol-vell", "local"), ("worktree-issue-12", "local"), ("issue/12-al-remot", "remot"),
])
def test_ja_te_branca(repo, gh_fals, existent, on):
    git(repo, "branch", existent, "main")
    if on == "remot":
        git(repo, "push", "-q", "origin", existent)
        git(repo, "branch", "-D", existent)
    r = nucli("tasca", "12", cwd=repo)
    assert r.returncode == 1 and "l'issue #12 ja té branca" in r.stderr and existent in r.stderr
    assert git(repo, "branch", "--show-current") == "main"
    assert not any(o.startswith("issue edit") for o in ordres_gh(gh_fals))


def test_una_branca_d_un_altre_issue_no_molesta(repo, gh_fals):
    git(repo, "branch", "issue/120-una-altra", "main")
    git(repo, "branch", "issue/1-una-altra", "main")
    assert nucli("tasca", "12", cwd=repo).returncode == 0


def test_si_l_etiqueta_falla_la_branca_hi_es_i_ho_diu(repo, gh_fals):
    gh_fals["falla"].write_text("")
    r = nucli("tasca", "12", cwd=repo)
    assert r.returncode == 1
    assert git(repo, "branch", "--show-current") == "issue/12-arregla-el-total-dels-partits"
    assert "la branca hi és, però no he pogut posar «estat: en-curs» a l'issue #12" in r.stderr
    assert "gh issue edit 12 --add-label 'estat: en-curs'" in r.stderr


def test_si_gh_no_pot_llegir_l_issue_no_toca_res(repo, gh_fals):
    gh_fals["dades"].unlink()
    r = nucli("tasca", "12", cwd=repo)
    assert r.returncode == 1 and "no he pogut llegir l'issue #12 amb gh: no trobo l'issue" in r.stderr
    assert "és el sandbox" in r.stderr and git(repo, "branch", "--show-current") == "main"


@pytest.mark.parametrize("arg", ["abc", "12a", "issue-12", "-1"])
def test_numero_no_valid(repo, gh_fals, arg):
    r = nucli("tasca", "--", arg, cwd=repo)
    assert r.returncode == 1 and "no és el número d'un issue" in r.stderr and not ordres_gh(gh_fals)


def test_sense_gh(repo, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    r = nucli("tasca", "12", cwd=repo)
    assert r.returncode == 1 and "no trobo «gh»" in r.stderr


def test_i_despres_el_commit_msg_demana_el_numero(repo, gh_fals, tmp_path, monkeypatch):
    """La branca que fa nucli tasca és la que vigila el commit-msg: l'assumpte ha d'acabar en « (#12)»."""
    d = tmp_path / "bin-py"
    d.mkdir()
    (d / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    git(repo, "config", "core.hooksPath", str(ARREL_NUCLI / "githooks"))
    assert nucli("tasca", "12", cwd=repo).returncode == 0
    escriu(repo, "app.py", "x = 2\n")
    git(repo, "add", "app.py")
    r = sh("git", "commit", "-q", "-m", "fix(app): el total", cwd=repo, check=False)
    assert r.returncode != 0 and "és de l'issue #12" in r.stderr
    assert sh("git", "commit", "-q", "-m", "fix(app): el total (#12)", cwd=repo, check=False).returncode == 0
