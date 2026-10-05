"""v0.1.6 (#2): seccions automàtiques «Resum» i «Risc de fusió» al rebut del PR.

Les omple el nucli sol, amb git, el rebut i nucli.json: sense executar res i sense cap text d'un agent.
`nucli rebut markdown` sense opcions continua idèntic; `--seccions` hi afegeix les dues; `nucli finish` les posa sempre.
"""
import json
import os
import re

import pytest

from conftest import CONFIG_MINIMA, commit, escriu, git, nucli
from nucli import VERSIO, config
from nucli.rebut import MAX_ARBRE, Canvi, canvis_de, codi, markdown, resum, risc_de_fusio, text_pla
from test_ship import finish_amb_terminal

# ---------- el bloc d'abans no canvia ----------

REBUT_FIX = {
    "versio": 1, "branca": "issue/7-prova",
    "execucions": [
        {"check": "lint", "codi": 1, "durada_s": 0.1, "hora": "2026-10-05T09:59:00+02:00"},
        {"check": "lint", "codi": 0, "durada_s": 0.12, "hora": "2026-10-05T10:00:00+02:00"},
        {"check": "test", "codi": 0, "durada_s": 1.5, "hora": "2026-10-05T10:00:02+02:00"},
    ],
    "segell": {"head": "a" * 40, "requerits": ["lint", "test", "visual", "smoke"], "manuals_pendents": ["visual"],
               "fora_sandbox_pendents": ["smoke"]},
    "finish": {"confirmacions": [{"check": "visual", "resposta": "sí", "hora": "2026-10-05T10:01:00+02:00"}]},
}

# La sortida de la v0.1.4 per a aquest rebut (generada amb el rebut.py de la v0.1.4). L'única diferència
# admesa és el número de versió del peu, que és el del nucli que l'escriu.
V014 = (
    "## Rebut del nucli\n\nChecks executats {per} contra HEAD `aaaaaaaaaaaa`:\n\n"
    "| check | codi | durada | hora |\n|---|---|---|---|\n"
    "| lint | 0 | 0.12 s | 2026-10-05T10:00:00+02:00 |\n| test | 0 | 1.5 s | 2026-10-05T10:00:02+02:00 |\n\n"
    "Confirmacions manuals:\n- visual: sí (2026-10-05T10:01:00+02:00)\n\n"
    "Checks fora del sandbox pendents (sense executar): smoke\n\n"
    "HEAD `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` · nucli {versio}\n"
)


@pytest.mark.parametrize("origen, per", [("finish", "per `nucli finish`"), ("ci", "per la CI")])
def test_el_bloc_sense_opcions_es_el_de_la_v014(origen, per):
    assert markdown(REBUT_FIX, origen) == V014.format(per=per, versio=VERSIO)
    assert VERSIO == "0.1.6"


# ---------- el diff de la branca ----------

def test_canvis_de_la_sortida_de_git():
    """`git diff -z --name-status -M` i `--numstat -M`: renomenats amb les dues rutes, binaris sense línies."""
    name_status = "R080\0lib/a.py\0lib/b.py\0A\0logo.png\0D\0vell.txt\0M\0docs/guia.md\0"
    numstat = "1\t1\t\0lib/a.py\0lib/b.py\0-\t-\tlogo.png\0" "0\t1\tvell.txt\0" "2\t1\tdocs/guia.md\0"
    assert canvis_de(name_status, numstat) == [
        Canvi("R", "lib/b.py", "lib/a.py", 1, 1),
        Canvi("A", "logo.png", None, None, None),
        Canvi("D", "vell.txt", None, 0, 1),
        Canvi("M", "docs/guia.md", None, 2, 1),
    ]


def test_canvis_tipus_es_un_m():
    assert canvis_de("T\0enllac\0", "0\t0\tenllac\0") == [Canvi("M", "enllac", None, 0, 0)]


# ---------- Resum: l'arbre de fitxers ----------

CANVIS = [
    Canvi("M", "README.md", None, 1, 0),
    Canvi("A", "db/migrations/001_init.sql", None, 3, 0),
    Canvi("M", "docs/guia.md", None, 2, 1),
    Canvi("A", "img/logo.png", None, None, None),
    Canvi("R", "lib/b.py", "lib/a.py", 1, 1),
    Canvi("D", "vell.txt", None, 0, 1),
]


def test_resum_es_l_arbre_de_fitxers():
    assert resum(CANVIS) == "\n".join([
        "## Resum",
        "",
        "6 fitxers · +7 -3 · A 2 · M 2 · D 1 · R 1 · 1 binari",
        "",
        "```text",
        "db/",
        "  migrations/",
        "    001_init.sql  A  +3 -0",
        "docs/",
        "  guia.md         M  +2 -1",
        "img/",
        "  logo.png        A  binari",
        "lib/",
        "  b.py            R  +1 -1  (era lib/a.py)",
        "README.md         M  +1 -0",
        "vell.txt          D  +0 -1",
        "```",
        "",
    ])


def test_resum_amb_un_sol_fitxer_i_sense_canvis():
    assert resum([Canvi("M", "app.py", None, 1, 1)]).splitlines()[2] == "1 fitxer · +1 -1 · M 1"
    assert resum([]) == "## Resum\n\nCap fitxer canviat respecte de la base.\n"


def test_resum_amb_massa_fitxers_en_diu_quants_en_falten():
    molts = [Canvi("A", f"gen/f{i:03d}.txt", None, 1, 0) for i in range(MAX_ARBRE + 5)]
    text = resum(molts)
    assert text.splitlines()[2] == f"{MAX_ARBRE + 5} fitxers · +{MAX_ARBRE + 5} -0 · A {MAX_ARBRE + 5}"
    assert sum(1 for l in text.splitlines() if l.startswith("  f")) == MAX_ARBRE
    assert "f064.txt" not in text
    assert text.rstrip().endswith("… i 5 fitxers més, que no surten a l'arbre.")


def test_resum_amb_cometes_al_nom_allarga_la_tanca():
    text = resum([Canvi("A", "a ```b``` c.txt", None, 1, 0)])
    assert "\n````text\n" in text and text.rstrip().endswith("````")


# ---------- Risc de fusió ----------

AMB_CONFIG = CANVIS + [Canvi("M", ".github/workflows/ci.yml", None, 1, 1)]
RISC = [{"patrons": ["db/migrations/**"], "motiu": "una migració aplicada no es desfà amb un revert"},
        {"patrons": ["infra/**"], "motiu": "no hi coincideix"}]


def test_risc_dificil_de_desfer_amb_senyals_i_abast():
    text = risc_de_fusio(AMB_CONFIG, {"risc": RISC}, ["lint", "test", "revisio-config"])
    assert text == "\n".join([
        "## Risc de fusió",
        "",
        "**Difícil de desfer.**",
        "- una migració aplicada no es desfà amb un revert: `db/migrations/001_init.sql`",
        "",
        "Senyals:",
        "- Configuració o seguretat (`revisio-config`): `.github/workflows/ci.yml`",
        "- Esborrats (1): `vell.txt`",
        "- Renomenats (1): `lib/a.py` → `lib/b.py`",
        "- Mida: 7 fitxers, +8 -4, 1 binari",
        "",
        "Abast:",
        "- Carpetes de primer nivell: `.github/`, `db/`, `docs/`, `img/`, `lib/` i l'arrel",
        "- Checks del segell: lint, test, revisio-config",
        "",
    ])


def test_risc_es_pot_desfer_sense_regles_o_sense_coincidencies():
    sense_clau = risc_de_fusio([Canvi("M", "app.py", None, 1, 1)], {}, ["lint"])
    assert sense_clau.splitlines()[2] == "**Es pot desfer** amb un revert del PR: `nucli.json` no té cap regla `risc`."
    assert "- Configuració o seguretat (`revisio-config`): cap" in sense_clau
    assert "- Esborrats: cap" in sense_clau and "- Renomenats: cap" in sense_clau
    assert "- Mida: 1 fitxer, +1 -1" in sense_clau
    assert "- Carpetes de primer nivell: l'arrel" in sense_clau
    sense_coincidencia = risc_de_fusio([Canvi("M", "app.py", None, 1, 1)], {"risc": RISC}, [])
    assert sense_coincidencia.splitlines()[2] == ("**Es pot desfer** amb un revert del PR: cap patró de la clau `risc` "
                                                  "de `nucli.json` hi coincideix.")
    assert "- Checks del segell: cap" in sense_coincidencia


@pytest.mark.parametrize("canvi", [
    Canvi("D", "db/migrations/002.sql", None, 0, 4),                 # esborrar una migració també
    Canvi("R", "altres/003.sql", "db/migrations/003.sql", 0, 0),     # i treure-la d'on era
])
def test_risc_mira_les_rutes_velles(canvi):
    text = risc_de_fusio([canvi], {"risc": RISC}, [])
    assert "**Difícil de desfer.**" in text and "db/migrations/" in text


def test_risc_amb_moltes_coincidencies_les_talla():
    molts = [Canvi("A", f"db/migrations/{i:03d}.sql", None, 1, 0) for i in range(15)]
    linia = risc_de_fusio(molts, {"risc": RISC}, []).splitlines()[3]
    assert linia.count("`db/migrations/") == 10 and linia.endswith(" i 5 més")


def test_el_motiu_s_escriu_sense_format():
    text = risc_de_fusio([Canvi("A", "x/a", None, 1, 0)],
                         {"risc": [{"patrons": ["x/**"], "motiu": "*perill* [mira](http://x) <b> @algu"}]}, [])
    assert "- \\*perill\\* \\[mira\\]\\(http://x\\) \\<b\\> \\@algu: `x/a`" in text


# ---------- noms de fitxer de la branca: sempre escapats ----------

def test_codi_en_linia():
    assert codi("a.py") == "`a.py`"
    assert codi("a`b") == "``a`b``"
    assert codi("`x") == "`` `x ``"
    assert codi("salt\nlinia") == "`salt\\nlinia`"
    assert codi("tab\tbidi‮") == "`tab\\tbidi\\u202e`"


def test_text_pla():
    assert text_pla("a *b* _c_ [d](e) <f> @g #h | ~i `j` \\k") == \
        "a \\*b\\* \\_c\\_ \\[d\\]\\(e\\) \\<f\\> \\@g \\#h \\| \\~i \\`j\\` \\\\k"
    assert text_pla("dues\nlínies") == "dues línies"


# ---------- la clau «risc» de nucli.json ----------

@pytest.mark.parametrize("risc, error", [
    ({"patrons": ["a/**"]}, "«risc» ha de ser una llista"),
    ([{"motiu": "x"}], "la regla de risc 1 ha de tenir «patrons» (llista de textos)"),
    ([{"patrons": [], "motiu": "x"}], "la regla de risc 1 ha de tenir «patrons» (llista de textos)"),
    ([{"patrons": ["a/**"]}], "la regla de risc 1 ha de tenir «motiu»: un text d'una línia"),
    ([{"patrons": ["a/**"], "motiu": " "}], "la regla de risc 1 ha de tenir «motiu»: un text d'una línia"),
    ([{"patrons": ["a/**"], "motiu": "dues\nlínies"}], "la regla de risc 1 ha de tenir «motiu»: un text d'una línia"),
    ([{"patrons": ["a/**"], "motiu": "x" * 201}], "de 200 caràcters com a màxim"),
])
def test_risc_invalid(risc, error):
    assert any(error in e for e in config.valida(dict(CONFIG_MINIMA, risc=risc)))


def test_risc_valid():
    assert config.valida(dict(CONFIG_MINIMA, risc=RISC)) == []
    assert config.valida(dict(CONFIG_MINIMA, risc=[])) == []


# ---------- amb git: nucli rebut markdown --seccions ----------

CONFIG = json.loads(json.dumps(CONFIG_MINIMA))
CONFIG["risc"] = [{"patrons": ["db/migrations/**"], "motiu": "una migració aplicada no es desfà amb un revert"}]
CONFIG["checks"]["lint"] = {"ordre": "touch \"$HOME/lint-executat\""}


@pytest.fixture
def repo(fes_repo):
    return fes_repo(config=CONFIG, fitxers={
        "app.py": "x = 1\n", "lib/a.py": "a\nb\nc\nd\ne\n", "vell.txt": "vell\n", "docs/guia.md": "guia\n",
    })


def wt_de(repo, branca="worktree-feina", nom="feina"):
    cami = repo / ".claude" / "worktrees" / nom
    git(repo, "worktree", "add", "-q", "-b", branca, str(cami), "origin/main")
    return cami


def segella(cami):
    """El que fa un agent o la CI: plan → run de cada automàtic → seal."""
    pla = json.loads(nucli("ship", "plan", "--json", cwd=cami).stdout)
    for c in pla["automatics"]:
        assert nucli("ship", "run", c["check"], cwd=cami).returncode == 0
    r = nucli("ship", "seal", cwd=cami)
    assert r.returncode == 0, r.stdout + r.stderr


def fes_la_branca(cami):
    escriu(cami, "app.py", "x = 2\n")
    git(cami, "mv", "lib/a.py", "lib/b.py")
    escriu(cami, "lib/b.py", "a\nb\nc\nd\nE\n")
    git(cami, "rm", "-q", "vell.txt")
    escriu(cami, "db/migrations/001_init.sql", "create table x (id int);\n")
    (cami / "img").mkdir()
    (cami / "img/logo.png").write_bytes(b"\x00\x01PNG\x00")
    escriu(cami, ".github/workflows/ci.yml", "on: push\n")
    commit(cami, "feat(app): canvi")


def seccio(text, titol):
    m = re.search(rf"^## {re.escape(titol)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"no hi ha la secció «{titol}»"
    return m.group(1)


def test_seccions_amb_git(repo, entorn):
    cami = wt_de(repo)
    fes_la_branca(cami)
    segella(cami)
    (entorn / "lint-executat").unlink()
    r = nucli("rebut", "markdown", "--origen", "ci", "--seccions", cwd=cami)
    assert r.returncode == 0, r.stderr
    assert not (entorn / "lint-executat").exists()  # per fer les seccions no s'executa cap check
    text = r.stdout
    assert [l for l in text.splitlines() if l.startswith("## ")] == ["## Resum", "## Risc de fusió", "## Rebut del nucli"]
    assert text.endswith(nucli("rebut", "markdown", "--origen", "ci", cwd=cami).stdout)
    arbre = seccio(text, "Resum")
    assert "6 fitxers · +4 -3 · A 3 · M 1 · D 1 · R 1 · 1 binari" in arbre
    for linia in ("db/", "  migrations/", "    001_init.sql", "  b.py", "(era lib/a.py)", "  logo.png", "binari",
                  "vell.txt", "app.py", ".github/"):
        assert linia in arbre, linia
    risc = seccio(text, "Risc de fusió")
    assert "**Difícil de desfer.**" in risc and "`db/migrations/001_init.sql`" in risc
    assert "- Configuració o seguretat (`revisio-config`): `.github/workflows/ci.yml`" in risc
    assert "- Esborrats (1): `vell.txt`" in risc and "- Renomenats (1): `lib/a.py` → `lib/b.py`" in risc
    assert "- Checks del segell: lint, test, revisio-config" in risc


def test_sense_seccions_no_canvia_res(repo):
    cami = wt_de(repo)
    fes_la_branca(cami)
    segella(cami)
    r = nucli("rebut", "markdown", "--origen", "ci", cwd=cami)
    assert r.returncode == 0 and r.stdout.startswith("## Rebut del nucli\n") and "## Resum" not in r.stdout


def test_noms_de_fitxer_estranys(fes_repo):
    cfg = dict(CONFIG, risc=[{"patrons": ["raro/**"], "motiu": "prova"}])
    repo = fes_repo(config=cfg)
    cami = wt_de(repo)
    noms = ["raro/te ```tres```.txt", "raro/<b>negre</b>.txt", "raro/@usuari.txt", "raro/salt\nlinia.txt",
            "raro/amb espais.txt"]
    for n in noms:
        escriu(cami, n, "x\n")
    commit(cami, "feat: noms")
    segella(cami)
    r = nucli("rebut", "markdown", "--origen", "ci", "--seccions", cwd=cami)
    assert r.returncode == 0, r.stderr
    arbre, risc = seccio(r.stdout, "Resum"), seccio(r.stdout, "Risc de fusió")
    assert "\n````text\n" in arbre and "salt\\nlinia.txt" in arbre
    assert not any(l.startswith("linia.txt") for l in r.stdout.splitlines())  # el salt de línia no trenca l'arbre
    fora_del_bloc = re.sub(r"````text\n.*?\n````", "", arbre, flags=re.S)
    fora_del_codi = re.sub(r"(`+)(.+?)\1", "", risc)
    for perill in ("<b>", "@usuari", "```"):
        assert perill not in fora_del_bloc and perill not in fora_del_codi, perill
    assert "`raro/salt\\nlinia.txt`" in risc and "`raro/amb espais.txt`" in risc


def test_risc_invalid_a_nucli_json_plega(fes_repo):
    repo = fes_repo(config=dict(CONFIG, risc=[{"patrons": ["a/**"]}]))
    r = nucli("ship", "plan", cwd=repo)
    assert r.returncode == 1 and "la regla de risc 1 ha de tenir «motiu»" in r.stderr


# ---------- nucli finish les posa sempre ----------

@pytest.fixture
def gh_fals(tmp_path, monkeypatch):
    d = tmp_path / "bin-gh"
    d.mkdir()
    cos, llista = tmp_path / "gh-cos.md", tmp_path / "gh-llista.json"
    (d / "gh").write_text(f"""#!/bin/bash
echo "$@" >> "{tmp_path}/gh.log"
case "$1 $2" in
  "pr list") if [ -f "{llista}" ]; then cat "{llista}"; else echo "[]"; fi ;;
  "pr create") cat > "{cos}"; echo "https://github.com/prova/repo/pull/7" ;;
  "pr comment") cat > "{cos}" ;;
esac
""")
    (d / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    return {"cos": cos, "llista": llista}


def test_finish_posa_les_seccions_al_pr_nou(repo, gh_fals):
    cami = wt_de(repo, "issue/12-arregla", "issue")
    escriu(cami, "app.py", "x = 2\n")
    commit(cami, "fix(app): el total (#12)")
    segella(cami)
    r = finish_amb_terminal(cami, "s\n")
    assert r.returncode == 0, r.stdout + r.stderr
    cos = gh_fals["cos"].read_text()
    assert cos.startswith("Closes #12\n\n## Resum\n")
    assert cos == "Closes #12\n\n" + nucli("rebut", "markdown", "--seccions", cwd=cami).stdout
    assert "**Es pot desfer** amb un revert del PR" in cos and "## Rebut del nucli" in cos


def test_finish_posa_les_seccions_al_comentari(repo, gh_fals):
    gh_fals["llista"].write_text('[{"number": 7, "url": "https://github.com/prova/repo/pull/7"}]')
    cami = wt_de(repo, "issue/12-arregla", "issue")
    escriu(cami, "app.py", "x = 2\n")
    commit(cami, "fix(app): el total (#12)")
    segella(cami)
    assert finish_amb_terminal(cami, "s\n").returncode == 0
    cos = gh_fals["cos"].read_text()
    assert cos.startswith("## Resum\n") and "## Risc de fusió" in cos and "## Rebut del nucli" in cos
    assert "Closes" not in cos
