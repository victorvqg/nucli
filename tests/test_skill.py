"""F6: la skill tanca-sessio."""
import re

from conftest import ARREL_NUCLI

SKILL = ARREL_NUCLI / "skills" / "tanca-sessio" / "SKILL.md"


def frontmatter():
    text = SKILL.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "cal un frontmatter entre ---"
    camps = dict(l.split(": ", 1) for l in m.group(1).splitlines())
    return camps, m.group(2)


def test_frontmatter_valid():
    camps, _ = frontmatter()
    assert set(camps) == {"name", "description"}
    assert camps["name"] == "tanca-sessio" == SKILL.parent.name


def test_descripcio_curta_i_amb_les_frases():
    camps, _ = frontmatter()
    assert len(camps["description"]) < 1536
    for frase in ("«tanca»", "«hem acabat»", "«plegem»", "nucli.json", "sense push"):
        assert frase in camps["description"]


def test_coherent_amb_nucli_json():
    _, cos = frontmatter()
    for clau in ("docs.decisions", "docs.trampes", "docs.estat", "docs.convencions", "docs.adoptats",
                 '"format": "adr"', '"format": "data"', "fitxer#Secció", "docs(sessio): tancament del AAAA-MM-DD",
                 "Mai facis push", "Mai `--no-verify`", "atura't"):
        assert clau in cos, clau
