"""F1: `nucli init` per als docs: detecció, adopció, plantilles, propostes i idempotència."""
import json
from pathlib import Path

import pytest

from conftest import ARREL_NUCLI, escriu, git, nucli
from nucli import docs

TASQUES = "# Tasques\n\n## A fer\n\n### mt3 · c\n\n## Fet\n\n### mt2 · b\n### mt1 · a\n### ma9 · torn\n"
PROPOSTES = "# Propostes\n\n### mp1 · x\n### mp2 · y\n### mp7 · z\n"
DISSENY = "# Disseny\n\n### md1 · a\n### md2 · b\n### md3 · c\n"
DECISIONS = "# Decisions\n\n## 2026-09-02 · Una\nDecisió: …\n\n## 2026-09-03 · Dues\n"
CLAUDE = "# CLAUDE.md\n\n## Convencions\n- una\n\n## Lliçons apreses\n- lliçó\n"
AGENTS = "# AGENTS.md\n\n## 2. Arquitectura: tres parts\nx\n\n## 3. Estat actual i pla de treball\ny\n"


def instantania(arrel: Path) -> dict:
    return {p.relative_to(arrel).as_posix(): p.read_bytes() for p in arrel.rglob("*") if p.is_file() and ".git" not in p.parts}


@pytest.fixture
def com_el_marcador(fes_repo):
    return fes_repo("marcador", config=None, fitxers={
        "TASQUES.md": TASQUES, "PROPOSTES.md": PROPOSTES, "docs/DISSENY.md": DISSENY, "DECISIONS.md": DECISIONS,
        "CLAUDE.md": CLAUDE, "AGENTS.md": AGENTS, "INFORME_TECNIC.md": "# Informe\n",
        "scripts/check.sh": "true\n", "scraper/tests/test_a.py": "", "scripts/smoke.py": "from playwright.sync_api import x\n",
    })


def test_repo_buit_crea_tot(fes_repo):
    arrel = fes_repo(config=None)
    r = nucli("init", cwd=arrel)
    assert r.returncode == 0, r.stderr
    for rol in ("ESTAT", "DECISIONS", "TRAMPES", "CONVENCIONS", "ARQUITECTURA"):
        assert (arrel / "docs" / f"{rol}.md").is_file()
    assert (arrel / "CLAUDE.md").read_text().startswith("@AGENTS.md")
    agents = (arrel / "AGENTS.md").read_text()
    assert "## Nucli" in agents and "`docs/ESTAT.md`" in agents
    assert len(agents.splitlines()) < 40 and len((arrel / "CLAUDE.md").read_text().splitlines()) < 40
    cfg = json.loads((arrel / "nucli.json").read_text())
    assert cfg["docs"]["decisions"] == {"cami": "docs/DECISIONS.md", "format": "adr"}
    assert "no he endevinat cap check" in r.stdout
    assert "No he fet cap commit" in r.stdout
    abans = instantania(arrel)
    r = nucli("init", cwd=arrel)
    assert "Res a fer: tot ja hi és." in r.stdout and instantania(arrel) == abans
    assert "CLAUDE.md · importa @AGENTS.md" in r.stdout


def test_com_el_marcador_no_toca_res_i_crea_nomes_estat_i_trampes(com_el_marcador):
    arrel = com_el_marcador
    abans = instantania(arrel)
    r = nucli("init", "--adopta", "arquitectura=INFORME_TECNIC.md", cwd=arrel)
    assert r.returncode == 0, r.stderr
    despres = instantania(arrel)
    for cami, contingut in abans.items():
        assert despres[cami] == contingut, f"{cami} ha canviat"
    nous = sorted(set(despres) - set(abans))
    assert nous == [".claude/settings.json", ".gitignore", ".nucli/.gitignore", ".nucli/proposta/AGENTS.md",
                    ".nucli/proposta/CLAUDE.md", ".nucli/proposta/allow.md", ".nucli/proposta/deny.md",
                    ".worktreeinclude", "docs/ESTAT.md", "docs/TRAMPES.md", "nucli.json"]
    assert "Lliçons apreses" in (arrel / "docs/TRAMPES.md").read_text()
    assert "3. Estat actual i pla de treball" in (arrel / "docs/ESTAT.md").read_text()
    assert git(arrel, "status", "--porcelain", "--untracked-files=all").splitlines() == [
        "?? .claude/settings.json", "?? .gitignore", "?? .worktreeinclude", "?? docs/ESTAT.md", "?? docs/TRAMPES.md",
        "?? nucli.json"]

    cfg = json.loads((arrel / "nucli.json").read_text())
    assert cfg["docs"]["arquitectura"] == "INFORME_TECNIC.md"
    assert cfg["docs"]["convencions"] == "CLAUDE.md#Convencions"
    assert cfg["docs"]["decisions"] == {"cami": "DECISIONS.md", "format": "data"}
    assert {a["prefix"]: a["cami"] for a in cfg["docs"]["adoptats"]} == {
        "mt": "TASQUES.md", "mp": "PROPOSTES.md", "md": "docs/DISSENY.md"}
    assert cfg["tasques"] == {"fitxer": "TASQUES.md", "prefix": "mt"}
    assert cfg["checks"]["lint"] == {"ordre": "bash scripts/check.sh"}
    assert cfg["checks"]["test"] == {"ordre": "cd scraper && python3 -m unittest discover -s tests"}
    assert cfg["checks"]["smoke"]["fora_sandbox"] is True
    assert r.stdout.count("← REVISA") == 3

    proposta = (arrel / ".nucli/proposta/CLAUDE.md").read_text()
    assert proposta.startswith(CLAUDE.rstrip("\n")) and "\n## Nucli\n" in proposta
    assert "Només per a Claude Code" in proposta
    assert "Només per a Claude Code" not in (arrel / ".nucli/proposta/AGENTS.md").read_text()
    assert "+## Nucli" in r.stdout  # ensenya el diff


def test_segona_passada_no_fa_res(com_el_marcador):
    arrel = com_el_marcador
    assert nucli("init", cwd=arrel).returncode == 0
    abans = instantania(arrel)
    r = nucli("init", cwd=arrel)
    assert r.returncode == 0
    assert instantania(arrel) == abans
    assert "Res a fer: tot ja hi és." in r.stdout
    assert " crea " not in r.stdout and " proposa " not in r.stdout


def test_dry_run_no_escriu_res(com_el_marcador):
    arrel = com_el_marcador
    abans = instantania(arrel)
    r = nucli("init", "--dry-run", cwd=arrel)
    assert r.returncode == 0
    assert instantania(arrel) == abans
    assert "(--dry-run: no s'escriu res)" in r.stdout and "faria" in r.stdout
    assert "  crea      docs/ESTAT.md" in r.stdout and "  proposa   .nucli/proposta/CLAUDE.md" in r.stdout


def test_amb_nucli_json_existent_el_fa_servir(com_el_marcador):
    arrel = com_el_marcador
    escriu(arrel, "nucli.json", (ARREL_NUCLI / "docs/exemples/marcador.nucli.json").read_text())
    r = nucli("init", cwd=arrel)
    assert r.returncode == 0, r.stderr
    assert "ja hi és  nucli.json" in r.stdout
    assert json.loads((arrel / "nucli.json").read_text())["regles"][2]["checks"] == ["lint", "smoke", "visual"]
    assert (arrel / "docs/ESTAT.md").is_file() and (arrel / "docs/TRAMPES.md").is_file()
    assert "arquitectura → INFORME_TECNIC.md" in r.stdout


def test_si_ja_tenen_el_bloc_no_proposa_res(com_el_marcador):
    arrel = com_el_marcador
    for f in ("CLAUDE.md", "AGENTS.md"):
        escriu(arrel, f, (arrel / f).read_text() + "\n## Nucli\n\nx\n")
    r = nucli("init", cwd=arrel)
    assert "ja hi és  CLAUDE.md · ja té el bloc «Nucli»" in r.stdout
    assert not (arrel / ".nucli/proposta/CLAUDE.md").exists() and not (arrel / ".nucli/proposta/AGENTS.md").exists()


def test_nomes_agents_crea_claude_que_l_importa(fes_repo):
    arrel = fes_repo(config=None, fitxers={"AGENTS.md": "# Agents\n"})
    nucli("init", cwd=arrel)
    assert (arrel / "CLAUDE.md").read_text().startswith("@AGENTS.md")
    assert (arrel / "AGENTS.md").read_text() == "# Agents\n"
    assert (arrel / ".nucli/proposta/AGENTS.md").is_file()


def test_adopta_invalid(fes_repo):
    arrel = fes_repo(config=None)
    r = nucli("init", "--adopta", "arquitectura=NO_EXISTEIX.md", cwd=arrel)
    assert r.returncode == 1 and "no trobo aquest fitxer" in r.stderr
    r = nucli("init", "--adopta", "rara=README.md", cwd=arrel)
    assert r.returncode == 1 and "cal «rol=camí»" in r.stderr


def test_init_en_un_worktree_plega(fes_repo):
    arrel = fes_repo()
    wt = arrel / ".claude/worktrees/x"
    git(arrel, "worktree", "add", "-q", "-b", "worktree-x", str(wt))
    r = nucli("init", cwd=wt)
    assert r.returncode == 1 and "al checkout principal" in r.stderr


def test_prefix_dominant_i_format(tmp_path):
    assert docs.prefix_dominant(escriu(tmp_path, "T.md", TASQUES)) == "mt"
    assert docs.prefix_dominant(escriu(tmp_path, "P.md", "### mp1 · x\n### mp2 · y\n")) is None
    assert docs.format_decisions(escriu(tmp_path, "D.md", DECISIONS)) == "data"
    assert docs.format_decisions(escriu(tmp_path, "A.md", "## ADR-0001 · x\n")) == "adr"


def test_normalitza():
    assert docs.normalitza("2. Arquitectura: tres parts") == "arquitectura"
    assert docs.normalitza("Lliçons apreses") == "llicons apreses"
    assert docs.coincideix_nom("estat actual i pla de treball", {"estat actual"})
    assert not docs.coincideix_nom("estructura", {"estat"})


def test_el_bloc_diu_els_ids_d_issue():
    """v0.1.4: a una branca d'issue l'id és #N, i amb github-issues el fitxer de tasques és historial."""
    from nucli import docs
    base = {"idioma": "ca", "docs": {"adoptats": [{"cami": "TASQUES.md", "prefix": "mt"}]},
            "tasques": {"fitxer": "TASQUES.md", "prefix": "mt"}}
    bloc = docs.bloc_nucli(base, per_claude=True)
    assert "(a una branca d'issue, `issue/N-…`, l'id és `#N` i l'assumpte acaba en ` (#N)`)" in bloc
    assert "historial" not in bloc and "`nucli tasca N`" in bloc
    amb = dict(base, tasques={"font": "github-issues", "branca": "issue/", "fitxer": "TASQUES.md", "prefix": "mt"})
    bloc = docs.bloc_nucli(amb, per_claude=False)
    assert "Les tasques, però, són issues de GitHub (etiqueta `tasca`) i el seu id és `#N`" in bloc
    assert "`TASQUES.md` és historial: no s'hi crea cap `mtN` nou." in bloc and "nucli tasca" not in bloc
    assert "`nucli tasca N`" in docs.claude_nou()
