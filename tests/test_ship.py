"""F2: classificador, rebut, segell, nucli finish (amb re-execució contra HEAD) i el hook protegeix-rebuts."""
import json
import os
import pty
import subprocess
import sys

import pytest

from conftest import BIN, CONFIG_MINIMA, commit, escriu, git, nucli
from nucli import permisos
from nucli.comu import troba_repo
from nucli.ship import calcula_pla, classifica

CONFIG = json.loads(json.dumps(CONFIG_MINIMA))
CONFIG["checks"].update({
    "lint": {"ordre": "echo lint-ok"},
    "test": {"ordre": "test ! -f \"$HOME/falla\" && echo test-ok"},
    "migracions": {"manual": "Migració provada en transacció desfeta"},
    "brut": {"ordre": "if [ -f \"$HOME/embruta\" ]; then touch brut.txt; fi; true"},
})
CONFIG["regles"].append({"patrons": ["supabase/migrations/**"], "checks": ["test", "migracions"]})
CONFIG["regles"].append({"patrons": ["gen/**"], "checks": ["brut"]})


@pytest.fixture
def repo(fes_repo):
    return fes_repo(config=CONFIG, fitxers={"app.py": "x = 1\n", "web/index.html": "<p>\n", "docs/a.md": "a\n"})


@pytest.fixture
def wt(repo):
    """Un worktree com els de Claude Code, a .claude/worktrees/feina, branca worktree-feina."""
    cami = repo / ".claude" / "worktrees" / "feina"
    git(repo, "worktree", "add", "-q", "-b", "worktree-feina", str(cami), "origin/main")
    return cami


@pytest.fixture
def gh_fals(tmp_path, monkeypatch):
    d = tmp_path / "bin-fals"
    d.mkdir()
    registre = tmp_path / "gh.log"
    cos = tmp_path / "gh-cos.md"
    llista = tmp_path / "gh-llista.json"
    (d / "gh").write_text(f"""#!/bin/bash
echo "$@" >> "{registre}"
case "$1 $2" in
  "pr list") if [ -f "{llista}" ]; then cat "{llista}"; else echo "[]"; fi ;;
  "pr create") cat > "{cos}"; echo "https://github.com/prova/repo/pull/7" ;;
  "pr comment") cat > "{cos}" ;;
esac
""")
    (d / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    return {"registre": registre, "cos": cos, "llista": llista}


def classifica_camins(camins, cfg=CONFIG):
    from nucli.config import completa
    fitxers, requerits = classifica(completa(cfg), [("M", c) for c in camins])
    return {f.cami: f.checks for f in fitxers}, requerits


# ---------- classificador ----------

def test_nomes_docs_no_demana_res():
    per_fitxer, req = classifica_camins(["README.md", "docs/a/b.md", "docs/imatge.png"])
    assert req == [] and all(v == [] for v in per_fitxer.values())


def test_regles_i_unio():
    per_fitxer, req = classifica_camins(["app.py", "web/index.html", "web/x.py"])
    assert per_fitxer["app.py"] == ["lint", "test"]
    assert per_fitxer["web/index.html"] == ["lint", "visual"]
    assert per_fitxer["web/x.py"] == ["lint", "test", "visual"]
    assert req == ["lint", "test", "visual"]


def test_migracions_i_per_defecte():
    per_fitxer, req = classifica_camins(["supabase/migrations/051.sql", "Makefile"])
    assert per_fitxer["supabase/migrations/051.sql"] == ["test", "migracions"]
    assert per_fitxer["Makefile"] == ["lint", "test"]
    assert req == ["lint", "test", "migracions"]


@pytest.mark.parametrize("cami", ["nucli.json", ".claude/settings.json", ".mcp.json", ".worktreeinclude",
                                  ".gitignore", "web/.gitignore", "githooks/pre-push", "sub/.claude/settings.json"])
def test_configuracio_demana_revisio(cami):
    per_fitxer, req = classifica_camins([cami])
    assert "revisio-config" in per_fitxer[cami] and req[-1] == "revisio-config"


def test_renomenats_esborrats_i_nous(repo, wt):
    git(wt, "mv", "app.py", "docs/app.md")
    git(wt, "rm", "-q", "web/index.html")
    escriu(wt, "nou.py", "y = 2\n")
    commit(wt, "refactor: moviments")
    escriu(wt, "sense_commit.txt", "z\n")
    pla = calcula_pla(troba_repo(wt))
    camins = {f.cami: f.checks for f in pla.fitxers}
    assert camins["app.py"] == ["lint", "test"]            # la ruta vella del renomenat compta
    assert camins["docs/app.md"] == []
    assert camins["web/index.html"] == ["lint", "visual"]  # esborrat
    assert camins["nou.py"] == ["lint", "test"]
    assert camins["sense_commit.txt"] == ["lint", "test"]  # sense regla → per defecte


def test_les_regles_son_les_del_checkout_principal(repo, wt):
    """Si l'agent reescriu el nucli.json del worktree per declarar-ho tot «docs», no li serveix de res."""
    trampa = dict(CONFIG, regles=[{"patrons": ["**"], "checks": []}], per_defecte=[])
    escriu(wt, "nucli.json", json.dumps(trampa))
    escriu(wt, "app.py", "x = 2\n")
    commit(wt, "feat: trampa")
    pla = calcula_pla(troba_repo(wt))
    assert "lint" in pla.requerits and "test" in pla.requerits and "revisio-config" in pla.requerits


def test_plan_ho_ensenya(repo, wt):
    escriu(wt, "web/index.html", "<p>2\n")
    r = nucli("ship", "plan", cwd=wt)
    assert r.returncode == 0, r.stderr
    assert "base origin/main" in r.stdout and f"Regles: {repo}/nucli.json" in r.stdout
    assert "web/index.html" in r.stdout and "visual          manual" in r.stdout


# ---------- run i seal ----------

def fes_feina(wt, cami="app.py", text="x = 2\n"):
    escriu(wt, cami, text)
    commit(wt, "feat(app): canvi")


def passa(wt, *checks):
    for c in checks:
        r = nucli("ship", "run", c, cwd=wt)
        assert r.returncode == 0, r.stdout + r.stderr
    r = nucli("ship", "seal", cwd=wt)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def rebut(wt):
    return json.loads((wt / ".nucli/rebuts/worktree-feina.json").read_text())


def test_run_desa_el_rebut_i_no_embruta_l_arbre(wt):
    fes_feina(wt)
    r = nucli("ship", "run", "lint", cwd=wt)
    assert r.returncode == 0 and "lint-ok" in r.stdout
    e = rebut(wt)["execucions"][-1]
    assert e["check"] == "lint" and e["codi"] == 0 and e["via"] == "ship" and "lint-ok" in e["sortida"]
    assert e["arbre"] == git(wt, "rev-parse", "HEAD^{tree}") and e["head"] == git(wt, "rev-parse", "HEAD")
    assert git(wt, "status", "--porcelain") == ""  # .nucli/ s'ignora sol, encara que la base no l'ignori


def test_run_surt_amb_el_codi_del_check(wt, entorn):
    fes_feina(wt)
    (entorn / "falla").write_text("")
    r = nucli("ship", "run", "test", cwd=wt)
    assert r.returncode == 1 and rebut(wt)["execucions"][-1]["codi"] == 1


def test_run_d_un_manual_o_desconegut(wt):
    assert nucli("ship", "run", "visual", cwd=wt).returncode == 2
    r = nucli("ship", "run", "inventat", cwd=wt)
    assert r.returncode == 2 and "no és a nucli.json" in r.stderr


def test_seal_bo(wt):
    fes_feina(wt)
    r = passa(wt, "lint", "test")
    assert "segellat" in r.stdout
    s = rebut(wt)["segell"]
    assert s["head"] == git(wt, "rev-parse", "HEAD") and s["requerits"] == ["lint", "test"] and len(s["sha256"]) == 64


def test_seal_amb_arbre_brut(wt):
    fes_feina(wt)
    nucli("ship", "run", "lint", cwd=wt)
    nucli("ship", "run", "test", cwd=wt)
    escriu(wt, "app.py", "x = 3\n")
    r = nucli("ship", "seal", cwd=wt)
    assert r.returncode == 1 and "no és net" in r.stderr


def test_seal_amb_check_fallit_o_sense_executar(wt, entorn):
    fes_feina(wt)
    nucli("ship", "run", "lint", cwd=wt)
    r = nucli("ship", "seal", cwd=wt)
    assert r.returncode == 1 and "test: no s'ha executat mai" in r.stderr
    (entorn / "falla").write_text("")
    nucli("ship", "run", "test", cwd=wt)
    r = nucli("ship", "seal", cwd=wt)
    assert "test: l'última execució ha fallat (codi 1" in r.stderr


def test_seal_amb_check_sobre_un_altre_arbre(wt):
    fes_feina(wt)
    escriu(wt, "app.py", "x = 99\n")  # els checks corren sobre un arbre sense commit…
    nucli("ship", "run", "lint", cwd=wt)
    nucli("ship", "run", "test", cwd=wt)
    commit(wt, "feat: un altre")        # el commit té exactament l'arbre provat: val
    assert nucli("ship", "seal", cwd=wt).returncode == 0
    escriu(wt, "app.py", "x = 100\n")
    commit(wt, "feat: editat després")
    r = nucli("ship", "seal", cwd=wt)
    assert r.returncode == 1 and "executat sobre un arbre diferent del de HEAD (has editat després?)" in r.stderr


# ---------- finish ----------

def branques_remot(repo):
    return git(repo, "ls-remote", "--heads", "origin")


def test_finish_cami_bo(repo, wt, gh_fals):
    fes_feina(wt)
    passa(wt, "lint", "test")
    r = nucli("finish", cwd=wt)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "refs/heads/worktree-feina" in branques_remot(repo)
    log = gh_fals["registre"].read_text()
    assert "pr create --base main --head worktree-feina --title feat(app): canvi" in log
    cos = gh_fals["cos"].read_text()
    assert "| lint | 0 |" in cos and "| test | 0 |" in cos and "re-executats per `nucli finish`" in cos
    reg = rebut(wt)["finish"]
    assert reg["resultat"] == "pujat" and [e["via"] for e in reg["execucions"]] == ["finish", "finish"]
    assert "Torno a executar contra HEAD" in r.stdout and "No he fet cap merge" in r.stdout


def test_finish_amb_pr_obert_hi_comenta(repo, wt, gh_fals):
    gh_fals["llista"].write_text('[{"number": 7, "url": "https://github.com/prova/repo/pull/7"}]')
    fes_feina(wt)
    passa(wt, "lint", "test")
    r = nucli("finish", cwd=wt)
    assert r.returncode == 0, r.stderr
    assert "pr comment 7 --body-file -" in gh_fals["registre"].read_text()
    assert "comentari al PR obert" in r.stdout


def test_finish_reexecucio_fallida_no_puja_res(repo, wt, gh_fals, entorn):
    """El rebut diu verd, però ara (fora del sandbox, contra HEAD) el test falla: no es puja res."""
    fes_feina(wt)
    passa(wt, "lint", "test")
    (entorn / "falla").write_text("")
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "test falla a la re-execució contra HEAD (codi 1): no pujo res" in r.stderr
    assert "worktree-feina" not in branques_remot(repo)
    assert not gh_fals["registre"].exists() or "pr create" not in gh_fals["registre"].read_text()
    assert rebut(wt)["finish"]["resultat"].startswith("aturat: test falla")


def test_finish_check_que_embruta_l_arbre_no_puja(repo, wt, gh_fals, entorn):
    fes_feina(wt, "gen/x.txt", "g\n")
    passa(wt, "brut")
    (entorn / "embruta").write_text("")
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "brut ha modificat l'arbre de treball: no pujo res" in r.stderr
    assert "worktree-feina" not in branques_remot(repo)


def test_finish_sense_rebut(wt, gh_fals):
    fes_feina(wt)
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "no hi ha rebut" in r.stderr


def test_finish_sense_segell(wt, gh_fals):
    fes_feina(wt)
    nucli("ship", "run", "lint", cwd=wt)
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "no està segellat" in r.stderr


def test_una_execucio_nova_treu_el_segell(wt, gh_fals):
    fes_feina(wt)
    passa(wt, "lint", "test")
    nucli("ship", "run", "lint", cwd=wt)
    assert rebut(wt)["segell"] is None


def test_finish_amb_head_canviat(wt, gh_fals):
    fes_feina(wt)
    passa(wt, "lint", "test")
    fes_feina(wt, "docs/b.md", "b\n")
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "no és el del segell" in r.stderr


def test_finish_amb_sha_alterat(wt, gh_fals):
    fes_feina(wt)
    passa(wt, "lint", "test")
    p = wt / ".nucli/rebuts/worktree-feina.json"
    dades = json.loads(p.read_text())
    dades["execucions"][0]["codi"] = 0
    dades["segell"]["requerits"] = []
    p.write_text(json.dumps(dades))
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "sha256" in r.stderr


def test_finish_recalcula_els_requerits(repo, wt, gh_fals):
    """Si el nucli.json del checkout principal passa a demanar més checks, el segell vell no n'hi ha prou."""
    fes_feina(wt)
    passa(wt, "lint", "test")
    cfg = json.loads((repo / "nucli.json").read_text())
    cfg["regles"][1]["checks"] = ["lint", "test", "brut"]
    (repo / "nucli.json").write_text(json.dumps(cfg))
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "brut: no s'ha executat mai" in r.stderr


def test_finish_a_la_branca_base(repo, gh_fals):
    r = nucli("finish", cwd=repo)
    assert r.returncode == 1 and "branca base" in r.stderr


def test_finish_amb_manuals_sense_terminal(repo, wt, gh_fals):
    fes_feina(wt, "web/index.html", "<p>2\n")
    passa(wt, "lint")
    r = nucli("finish", cwd=wt, entrada="s\n")
    assert r.returncode == 1 and "hi ha checks manuals (visual) i no hi ha terminal" in r.stderr
    assert "worktree-feina" not in branques_remot(repo)


def finish_amb_terminal(wt, resposta: str):
    mestre, esclau = pty.openpty()
    os.write(mestre, resposta.encode())
    proc = subprocess.run([sys.executable, str(BIN), "finish"], cwd=str(wt), stdin=esclau,
                          capture_output=True, text=True, env=dict(os.environ))
    os.close(esclau)
    os.close(mestre)
    return proc


def test_finish_manuals_confirmats_al_terminal(repo, wt, gh_fals):
    fes_feina(wt, "web/index.html", "<p>2\n")
    passa(wt, "lint")
    r = finish_amb_terminal(wt, "s\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "worktree-feina" in branques_remot(repo)
    assert "- visual: sí" in gh_fals["cos"].read_text()
    assert rebut(wt)["finish"]["confirmacions"][0]["resposta"] == "sí"


def test_finish_manual_no_confirmat(repo, wt, gh_fals):
    fes_feina(wt, "web/index.html", "<p>2\n")
    passa(wt, "lint")
    r = finish_amb_terminal(wt, "n\n")
    assert r.returncode == 1 and "visual no confirmat: no pujo res" in r.stderr
    assert "worktree-feina" not in branques_remot(repo)


def test_finish_sense_gh_no_puja(repo, wt, monkeypatch):
    fes_feina(wt)
    passa(wt, "lint", "test")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "no trobo «gh»" in r.stderr
    assert "worktree-feina" not in branques_remot(repo)


# ---------- init: .gitignore i regla ask ----------

SETTINGS_MARCADOR = """{
  "permissions": {
    "allow": [
      "Bash(bash scripts/llanca-sync.sh)"
    ],
    "ask": [
      "Bash(git push:*)",
      "WebSearch"
    ]
  },
  "sandbox": {
    "enabled": true
  }
}
"""


def test_insercio_a_settings_conserva_la_resta_byte_a_byte():
    nou = permisos.afegeix_regla(SETTINGS_MARCADOR, "ask", "Bash(nucli finish:*)")
    assert nou.replace(',\n      "Bash(nucli finish:*)"', "") == SETTINGS_MARCADOR
    assert permisos.afegeix_regla(nou, "ask", "Bash(nucli finish:*)") is None


@pytest.mark.parametrize("text", [None, "{}", '{"a": 1}', '{\n  "permissions": {}\n}\n', '{"permissions": {"ask": []}}',
                                  '{\n\t"permissions": {\n\t\t"deny": ["x"]\n\t}\n}\n'])
def test_insercio_en_formes_diverses(text):
    nou = permisos.afegeix_regla(text, "ask", "R")
    assert json.loads(nou)["permissions"]["ask"][-1] == "R"


def test_insercio_amb_json_trencat_plega():
    from nucli.comu import Plega
    with pytest.raises(Plega):
        permisos.afegeix_regla("{ trencat", "ask", "R")


def test_init_afegeix_gitignore_i_ask(fes_repo):
    arrel = fes_repo(config=CONFIG, fitxers={".gitignore": "node_modules/", ".claude/settings.json": SETTINGS_MARCADOR})
    r = nucli("init", cwd=arrel)
    assert r.returncode == 0, r.stderr
    assert (arrel / ".gitignore").read_text() == "node_modules/\n# nucli\n.nucli/\n.claude/worktrees/\n"
    assert "Bash(nucli finish:*)" in json.loads((arrel / ".claude/settings.json").read_text())["permissions"]["ask"]
    r = nucli("init", cwd=arrel)
    assert "Res a fer" in r.stdout


# ---------- hook protegeix-rebuts ----------

def hook(entrada, cwd):
    return nucli("hook", "protegeix-rebuts", cwd=cwd, entrada=json.dumps(entrada))


@pytest.mark.parametrize("eina, clau", [("Edit", "file_path"), ("Write", "file_path"), ("NotebookEdit", "notebook_path")])
def test_hook_nega_els_rebuts(wt, eina, clau):
    cami = str(wt / ".nucli/rebuts/worktree-feina.json")
    r = hook({"tool_name": eina, "tool_input": {clau: cami}, "cwd": str(wt)}, wt)
    assert r.returncode == 0
    sortida = json.loads(r.stdout)["hookSpecificOutput"]
    assert sortida["permissionDecision"] == "deny" and "nucli ship" in sortida["permissionDecisionReason"]


def test_hook_nega_amb_cami_relatiu(wt):
    r = hook({"tool_name": "Write", "tool_input": {"file_path": ".nucli/rebuts/x.json"}, "cwd": str(wt)}, wt)
    assert "deny" in r.stdout


def test_hook_deixa_la_resta(wt, fes_repo, tmp_path):
    r = hook({"tool_name": "Edit", "tool_input": {"file_path": str(wt / "app.py")}, "cwd": str(wt)}, wt)
    assert r.returncode == 0 and r.stdout == ""
    sense = fes_repo("sense", config=None)
    r = hook({"tool_name": "Edit", "tool_input": {"file_path": str(sense / ".nucli/rebuts/x.json")}, "cwd": str(sense)}, sense)
    assert r.returncode == 0 and r.stdout == ""
    r = nucli("hook", "protegeix-rebuts", cwd=tmp_path, entrada="no és json")
    assert r.returncode == 0 and r.stdout == ""
