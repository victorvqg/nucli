"""El diagrama del README és una còpia del de docs/FLUX.md: si se separen, falla."""
import re

from conftest import ARREL_NUCLI


def diagrames(cami):
    text = (ARREL_NUCLI / cami).read_text(encoding="utf-8")
    return re.findall(r"^```mermaid\n(.*?)^```$", text, re.S | re.M)


def test_el_diagrama_del_readme_es_el_de_flux():
    flux = diagrames("docs/FLUX.md")
    assert len(flux) == 1, "docs/FLUX.md ha de tenir un sol diagrama mermaid"
    assert diagrames("README.md") == flux, "el diagrama del README ha de ser idèntic al de docs/FLUX.md"
