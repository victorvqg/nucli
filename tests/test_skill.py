"""F6: la skill tanca-sessio. v0.1.2: mai fa commit a main i acaba recordant nucli finish."""
import os
import re
import sys

from conftest import ARREL_NUCLI, CONFIG_MINIMA, escriu, git, sh

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
    for frase in ("«tanca»", "«hem acabat»", "«plegem»", "nucli.json", "sense push", "mai a main"):
        assert frase in camps["description"]


def test_coherent_amb_nucli_json():
    _, cos = frontmatter()
    for clau in ("docs.decisions", "docs.trampes", "docs.estat", "docs.convencions", "docs.adoptats",
                 '"format": "adr"', '"format": "data"', "fitxer#Secció", "docs(sessio): tancament del AAAA-MM-DD",
                 "Mai facis push", "Mai `--no-verify`", "atura't"):
        assert clau in cos, clau


def test_mai_commit_a_main_i_recorda_nucli_finish():
    _, cos = frontmatter()
    for clau in ("**Mai facis commit a `main`**", "`branca_base`", "`git switch -c docs/sessio-AAAA-MM-DD-HHMM`",
                 "`date +%Y-%m-%d-%H%M`", "HEAD desenganxat"):
        assert clau in cos, clau
    commit = cos.index("## 5. Branca i commit")
    assert cos.index("git switch -c") > commit and cos.index("git switch -c") < cos.index("`git add`", commit)
    final = cos.strip().splitlines()[-1]
    assert final.startswith("L'última línia, **sempre**") and "`nucli finish`" in final and "des del terminal" in final


def test_els_passos_a_main_deixen_main_intacte_i_passen_pels_hooks(fes_repo, tmp_path, monkeypatch):
    """Les ordres de la skill, fetes tal com les escriu, en un repo a main amb els hooks del nucli: branca pròpia,
    commit acceptat pel commit-msg, main sense cap commit nou i un pre-push que deixa pujar la branca."""
    _, cos = frontmatter()
    ordre_branca = re.search(r"`(git switch -c docs/sessio-AAAA-MM-DD-HHMM)`", cos).group(1)
    ordre_data = re.search(r"`(date \+[^`]+)`", cos).group(1)
    missatge = re.search(r"`(docs\(sessio\): tancament del AAAA-MM-DD)`", cos).group(1)
    d = tmp_path / "bin-py"
    d.mkdir()
    (d / "python3").symlink_to(sys.executable)  # els githooks criden bin/nucli amb el python3 del PATH
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    arrel = fes_repo(config=dict(CONFIG_MINIMA, tasques={"fitxer": "TASQUES.md", "prefix": "mt"}))
    git(arrel, "config", "core.hooksPath", str(ARREL_NUCLI / "githooks"))
    main = git(arrel, "rev-parse", "main")

    ara = sh("bash", "-c", ordre_data, cwd=arrel).stdout.strip()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{4}", ara)
    sh(*ordre_branca.replace("AAAA-MM-DD-HHMM", ara).split(), cwd=arrel)
    escriu(arrel, "docs/ESTAT.md", f"Última actualització: {ara[:10]}\n\n## Ara\n\n## Següent\n\n## Bloquejat\n")
    git(arrel, "add", "docs/ESTAT.md")
    dolent = sh("git", "commit", "-q", "-m", "update docs", cwd=arrel, check=False)
    assert dolent.returncode != 0 and "missatge de commit rebutjat" in dolent.stderr  # el commit-msg hi és
    r = sh("git", "commit", "-q", "-m", missatge.replace("AAAA-MM-DD", ara[:10]), cwd=arrel, check=False)
    assert r.returncode == 0, r.stderr

    branca = f"docs/sessio-{ara}"
    assert git(arrel, "branch", "--show-current") == branca
    assert git(arrel, "rev-parse", "main") == main
    assert git(arrel, "log", "-1", "--format=%s") == f"docs(sessio): tancament del {ara[:10]}"
    a_main = sh("git", "push", "origin", "HEAD:main", cwd=arrel, check=False)
    assert a_main.returncode != 0 and "no es pot pujar directament a main" in a_main.stderr  # el pre-push hi és
    r = sh("git", "push", "origin", branca, cwd=arrel, check=False)
    assert r.returncode == 0, r.stderr


# ---------- v0.1.4: les tasques són issues ----------

def test_apunta_a_issues_i_no_crea_mai_cap_mt():
    _, cos = frontmatter()
    for clau in ("`#N`", "`gh issue list --label tasca --state open --json number,title,labels`", "que només llegeix",
                 "no t'inventis cap número", "`tasques.font` és `github-issues`", "és historial",
                 "**Una tasca nova no és mai un id del fitxer de tasques**", "no creïs cap `mtX`, ni tampoc cap issue",
                 "`.github/ISSUE_TEMPLATE/`", "perquè l'obri l'usuari", "tu no l'obres"):
        assert clau in cos, clau
    assert "p. ex. `mt`, `mp`" not in cos  # les mt ja no són un id que la skill pugui crear
    seccio5 = cos[cos.index("## 5. Branca i commit"):cos.index("## 6.")]
    for clau in ("`issue/12-…`", "`worktree-issue-12`", "` (#12)`", "**ha d'acabar**", "`tasques.branca`", "` (mt12)`"):
        assert clau in seccio5, clau


def test_a_una_branca_d_issue_el_commit_acaba_en_numero(fes_repo, tmp_path, monkeypatch):
    """El missatge de la skill a `issue/12-…`: sense « (#12)» el commit-msg el rebutja; amb, passa."""
    _, cos = frontmatter()
    missatge = re.search(r"`(docs\(sessio\): tancament del AAAA-MM-DD)`", cos).group(1).replace("AAAA-MM-DD", "2026-10-01")
    d = tmp_path / "bin-py"
    d.mkdir()
    (d / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    arrel = fes_repo(config=dict(CONFIG_MINIMA, tasques={"font": "github-issues", "branca": "issue/",
                                                         "fitxer": "TASQUES.md", "prefix": "mt"}))
    git(arrel, "config", "core.hooksPath", str(ARREL_NUCLI / "githooks"))
    git(arrel, "switch", "-q", "-c", "issue/12-arregla-el-total")
    escriu(arrel, "docs/ESTAT.md", "Última actualització: 2026-10-01\n\n## Ara\n\n## Següent\n- #13\n\n## Bloquejat\n")
    git(arrel, "add", "docs/ESTAT.md")
    r = sh("git", "commit", "-q", "-m", missatge, cwd=arrel, check=False)
    assert r.returncode != 0 and "l'assumpte ha d'acabar en « (#12)»" in r.stderr
    r = sh("git", "commit", "-q", "-F", "-", cwd=arrel, check=False, entrada=f"{missatge}\n\nIssue #12.\n")
    assert r.returncode != 0  # al cos no n'hi ha prou
    r = sh("git", "commit", "-q", "-m", f"{missatge} (#12)", cwd=arrel, check=False)
    assert r.returncode == 0, r.stderr
