"""F0: el llançador, la cerca de l'arrel i la lectura de nucli.json."""
import json

import pytest

from conftest import BIN, CONFIG_MINIMA, git, nucli, escriu
from nucli import config
from nucli.comu import Plega, Repo, troba_repo


def test_help_en_catala(tmp_path):
    r = nucli("--help", cwd=tmp_path)
    assert r.returncode == 0
    assert "ús: nucli" in r.stdout
    for ordre in ("init", "ship", "finish", "port", "neteja", "agent", "usage", "tasca", "rebut"):
        assert ordre in r.stdout


def test_sense_ordre_mostra_ajuda(tmp_path):
    r = nucli(cwd=tmp_path)
    assert r.returncode == 0 and "ús: nucli" in r.stdout


def test_el_llancador_resol_l_enllac(tmp_path):
    enllac = tmp_path / "bin" / "nucli"
    enllac.parent.mkdir()
    enllac.symlink_to(BIN)
    r = nucli("--version", cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == "nucli 0.1.6"


ORDRES_DE_REPO = [["ship", "plan"], ["ship", "plan", "--json"], ["finish"], ["port"], ["agent", "x1"], ["agent", "12"],
                  ["neteja"], ["tasca", "12"], ["rebut", "markdown"]]


@pytest.mark.parametrize("args", ORDRES_DE_REPO)
def test_fora_d_un_repo_git_plega(tmp_path, args):
    r = nucli(*args, cwd=tmp_path)
    assert r.returncode != 0
    assert "no ets dins d'un repo git" in r.stderr


@pytest.mark.parametrize("args", ORDRES_DE_REPO)
def test_repo_sense_nucli_json_plega(fes_repo, args):
    arrel = fes_repo(config=None)
    r = nucli(*args, cwd=arrel)
    assert r.returncode != 0
    assert "no té nucli.json" in r.stderr and "nucli init" in r.stderr


def test_arrels_des_d_un_subdirectori_i_un_worktree(fes_repo):
    arrel = fes_repo()
    (arrel / "sub").mkdir()
    repo = Repo(arrel / "sub")
    assert repo.worktree == arrel and repo.arrel == arrel and not repo.es_worktree

    wt = arrel / ".claude" / "worktrees" / "prova"
    git(arrel, "worktree", "add", "-q", "-b", "worktree-prova", str(wt), "origin/main")
    repo = Repo(wt)
    assert repo.worktree == wt.resolve() and repo.arrel == arrel and repo.es_worktree


def test_la_config_es_llegeix_del_checkout_principal(fes_repo):
    """Un worktree que edita el seu nucli.json no canvia les regles: manen les del checkout principal."""
    arrel = fes_repo()
    wt = arrel / ".claude" / "worktrees" / "prova"
    git(arrel, "worktree", "add", "-q", "-b", "worktree-prova", str(wt), "origin/main")
    trampa = dict(CONFIG_MINIMA, per_defecte=[], regles=[{"patrons": ["**"], "checks": []}])
    escriu(wt, "nucli.json", json.dumps(trampa))
    cfg = troba_repo(wt).config()
    assert cfg["per_defecte"] == ["lint", "test"]


def test_ref_base_prefereix_origin(fes_repo):
    arrel = fes_repo()
    assert troba_repo(arrel).ref_base() == "origin/main"
    git(arrel, "remote", "remove", "origin")
    assert troba_repo(arrel).ref_base() == "main"


def test_config_completa_els_valors_per_defecte(tmp_path):
    p = escriu(tmp_path, "nucli.json", json.dumps({"versio": 1}))
    cfg = config.llegeix(p)
    assert cfg["branca_base"] == "main" and cfg["idioma"] == "ca"
    assert cfg["agent"]["torns"] == 60 and "feat" in cfg["commits"]["tipus"]


@pytest.mark.parametrize("dades, error", [
    ({"versio": 2}, "«versio» ha de ser 1"),
    ({"versio": 1, "checks": {"a": {}}}, "ha de tenir «ordre»"),
    ({"versio": 1, "checks": {"a": {"ordre": "x", "manual": "y"}}}, "només un dels dos"),
    ({"versio": 1, "checks": {"revisio-config": {"manual": "x"}}}, "reservat"),
    ({"versio": 1, "checks": {}, "per_defecte": ["lint"]}, "«lint», que no és a «checks»"),
    ({"versio": 1, "checks": {}, "regles": [{"patrons": ["*.py"]}]}, "ha de tenir «checks»"),
    ({"versio": 1, "checks": {}, "regles": [{"patrons": ["*.py"], "checks": ["test"]}]}, "«test», que no és a «checks»"),
    ({"versio": 1, "checks": {"m": {"manual": "x", "fora_sandbox": True}}}, "no pot ser «fora_sandbox»"),
    ({"versio": 1, "docs": {"decisions": {"cami": "D.md", "format": "raro"}}}, "«adr» o «data»"),
    ({"versio": 1, "agent": {"torns": 0}}, "enter positiu"),
    ({"versio": 1, "tasques": {"fitxer": "T.md"}}, "«tasques» ha de tenir «fitxer» i «prefix»"),
    ({"versio": 1, "tasques": {"fitxer": "T.md", "prefix": "mt", "font": "jira"}},
     "«tasques.font» ha de ser «fitxer» o «github-issues»"),
    ({"versio": 1, "tasques": {"fitxer": "T.md", "prefix": "mt", "font": "github-issues"}}, "cal «tasques.branca»"),
    ({"versio": 1, "tasques": {"fitxer": "T.md", "prefix": "mt", "font": "github-issues", "branca": "issue"}},
     "acabat en «/»"),
    ({"versio": 1, "tasques": {"fitxer": "T.md", "prefix": "mt", "font": "github-issues", "branca": "/"}},
     "acabat en «/»"),
])
def test_config_invalida(tmp_path, dades, error):
    p = escriu(tmp_path, "nucli.json", json.dumps(dades))
    with pytest.raises(Plega) as e:
        config.llegeix(p)
    assert error in str(e.value)


@pytest.mark.parametrize("tasques", [
    {"fitxer": "TASQUES.md", "prefix": "mt"},                                    # com fins ara: font «fitxer»
    {"font": "fitxer", "fitxer": "TASQUES.md", "prefix": "mt"},
    {"font": "github-issues", "branca": "issue/", "fitxer": "TASQUES.md", "prefix": "mt"},
])
def test_tasques_valides(tmp_path, tasques):
    p = escriu(tmp_path, "nucli.json", json.dumps({"versio": 1, "tasques": tasques}))
    assert config.llegeix(p)["tasques"] == tasques


def test_branca_d_issues_per_defecte_i_de_nucli_json():
    assert config.branca_issues({}) == "issue/" and config.branca_issues({"tasques": None}) == "issue/"
    cfg = {"tasques": {"font": "github-issues", "branca": "tasca/", "fitxer": "T.md", "prefix": "mt"}}
    assert config.branca_issues(cfg) == "tasca/"
    assert config.issue_de_branca("tasca/7-x", cfg) == 7 and config.issue_de_branca("issue/7-x", cfg) is None
    assert config.issue_de_branca("worktree-issue-7", cfg) == 7


def test_json_trencat(tmp_path):
    p = escriu(tmp_path, "nucli.json", "{ \"versio\": 1,, }")
    with pytest.raises(Plega) as e:
        config.llegeix(p)
    assert "JSON no vàlid (línia 1" in str(e.value)


def test_l_exemple_del_marcador_es_valid():
    from conftest import ARREL_NUCLI
    cfg = config.llegeix(ARREL_NUCLI / "docs" / "exemples" / "marcador.nucli.json")
    web = [r for r in cfg["regles"] if r["patrons"] == ["web/**"]][0]
    assert web["checks"] == ["lint", "smoke", "visual"]
    assert cfg["checks"]["smoke"]["fora_sandbox"] is True
    assert cfg["tasques"] == {"font": "github-issues", "branca": "issue/", "fitxer": "TASQUES.md", "prefix": "mt"}
