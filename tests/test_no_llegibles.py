"""v0.1.2: els fitxers que el sandbox no deixa llegir (al marcador, el `denyRead` de `.env.*` → `.env.example`).

- Dins del sandbox (`nucli ship`), un fitxer no llegible no compta ni com a esborrat ni com a canvi: surt com a
  «no llegible (sandbox)» i no compta ni per al pla ni per a l'arbre net. El que en diuen els commits, sí.
- Fora del sandbox (`nucli finish`), l'arbre net és estricte: si el fitxer ha canviat, o no el pot llegir, no puja res.

El sandbox se simula amb `sandbox-exec` (macOS), el mateix mecanisme que fa servir Claude Code: `lstat` → EPERM.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import BIN, commit, escriu, git, nucli
from test_ship import branques_remot, gh_fals  # noqa: F401 (gh_fals és una fixture)

SANDBOX_EXEC = shutil.which("sandbox-exec")
cal_sandbox = pytest.mark.skipif(SANDBOX_EXEC is None, reason="cal sandbox-exec (macOS)")

CONFIG = {
    "versio": 1,
    "branca_base": "main",
    "checks": {"lint": {"ordre": "echo lint-ok"}, "test": {"ordre": "echo test-ok"}},
    "regles": [{"patrons": ["*.md", "docs/**"], "checks": []}, {"patrons": ["*.py"], "checks": ["lint", "test"]}],
    "per_defecte": ["lint", "test"],
}


def sandbox(nega, *ordre, cwd):
    """`ordre` amb un sandbox que no deixa ni consultar els camins de `nega`, com el `denyRead` del marcador."""
    camins = " ".join(f'(literal "{os.path.realpath(c)}")' for c in nega)
    perfil = f"(version 1)(allow default)(deny file-read* {camins})"
    return subprocess.run([SANDBOX_EXEC, "-p", perfil, *ordre], cwd=str(cwd), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env=dict(os.environ))


def nucli_sandbox(nega, *args, cwd):
    return sandbox(nega, sys.executable, str(BIN), *args, cwd=cwd)


@pytest.fixture
def wt(fes_repo):
    """Un worktree d'un repo amb `.env.example` a git, com el marcador."""
    arrel = fes_repo(config=CONFIG, fitxers={".env.example": "CLAU=\n", "app.py": "x = 1\n"})
    cami = arrel / ".claude/worktrees/feina"
    git(arrel, "worktree", "add", "-q", "-b", "worktree-feina", str(cami), "origin/main")
    return cami


def env(wt):
    return [wt / ".env.example"]


def una_nota(wt):
    escriu(wt, "docs/nota.md", "nota\n")
    commit(wt, "docs: una nota")


def rebut(wt):
    return json.loads((wt / ".nucli/rebuts/worktree-feina.json").read_text())


# ---------- la causa ----------

@cal_sandbox
def test_git_diff_el_dona_per_esborrat_i_git_status_no(wt):
    """`git diff <commit>`, el que fa servir el pla, compara amb l'arbre de treball i dona per esborrat, sense cap
    avís, el que no pot consultar. `git status` se'l salta amb l'avís «Operation not permitted»."""
    diff = sandbox(env(wt), "git", "diff", "--name-status", "origin/main", cwd=wt)
    assert diff.returncode == 0 and diff.stdout.strip() == "D\t.env.example" and diff.stderr == ""
    status = sandbox(env(wt), "git", "status", "--porcelain", cwd=wt)
    assert status.returncode == 0 and status.stdout == ""
    assert ".env.example: Operation not permitted" in status.stderr


# ---------- dins del sandbox: ship ----------

@cal_sandbox
def test_plan_el_mostra_com_a_no_llegible_i_no_el_compta(wt):
    una_nota(wt)
    r = nucli_sandbox(env(wt), "ship", "plan", cwd=wt)
    assert r.returncode == 0, r.stderr
    assert "D  .env.example" not in r.stdout
    assert re.search(r"·  \.env\.example +no llegible \(sandbox\) → ni esborrat ni canvi: fora del pla", r.stdout)
    assert "Checks requerits: cap." in r.stdout  # abans: «D .env.example» → per defecte → lint, test
    fora = nucli("ship", "plan", cwd=wt)
    assert ".env.example" not in fora.stdout and "Checks requerits: cap." in fora.stdout


@cal_sandbox
def test_plan_sense_cap_altre_canvi(wt):
    r = nucli_sandbox(env(wt), "ship", "plan", cwd=wt)
    assert r.returncode == 0, r.stderr
    assert "no llegible (sandbox) → ni esborrat ni canvi" in r.stdout
    assert "Cap canvi respecte de la base: cap check requerit." in r.stdout


@cal_sandbox
def test_un_esborrat_de_debo_continua_sent_esborrat(wt):
    (wt / "app.py").unlink()
    r = nucli_sandbox(env(wt), "ship", "plan", cwd=wt)
    assert re.search(r"D  app\.py +regla 2 → lint, test", r.stdout)
    assert "D  .env.example" not in r.stdout


@cal_sandbox
def test_el_que_diuen_els_commits_si_que_compta(wt):
    """Un canvi als commits, git el sap sense llegir el fitxer: compta, amb la nota."""
    escriu(wt, ".env.example", "CLAU=\nALTRA=\n")
    commit(wt, "chore: una clau nova")
    r = nucli_sandbox(env(wt), "ship", "plan", cwd=wt)
    assert re.search(r"M  \.env\.example +sense regla → per defecte → lint, test"
                     r"  · no llegible \(sandbox\): només compta el canvi dels commits", r.stdout)
    assert "fora del pla" not in r.stdout and "lint            automàtic" in r.stdout


@cal_sandbox
def test_seal_dins_del_sandbox_no_el_compta_per_a_l_arbre_net(wt):
    una_nota(wt)
    r = nucli_sandbox(env(wt), "ship", "seal", cwd=wt)
    assert r.returncode == 0, r.stderr
    assert "No llegibles (sandbox), no compten per a l'arbre net: .env.example" in r.stdout
    s = rebut(wt)["segell"]
    assert s["no_llegibles"] == [".env.example"] and s["requerits"] == []


@cal_sandbox
def test_un_fitxer_nou_no_llegible_no_trenca_run_ni_seal(wt):
    escriu(wt, "app.py", "x = 2\n")
    commit(wt, "feat(app): canvi")
    escriu(wt, "claus.local", "secret\n")  # nou, no ignorat, i el sandbox no el deixa llegir
    nega = env(wt) + [wt / "claus.local"]
    plan = nucli_sandbox(nega, "ship", "plan", cwd=wt)
    assert "?  claus.local" not in plan.stdout and re.search(r"·  claus\.local +no llegible \(sandbox\)", plan.stdout)
    for c in ("lint", "test"):
        r = nucli_sandbox(nega, "ship", "run", c, cwd=wt)
        assert r.returncode == 0, r.stdout + r.stderr  # sense la correcció, `git add -A` hi plega
    assert rebut(wt)["execucions"][-1]["arbre"] == git(wt, "rev-parse", "HEAD^{tree}")
    seal = nucli_sandbox(nega, "ship", "seal", cwd=wt)
    assert seal.returncode == 0, seal.stderr
    assert rebut(wt)["segell"]["no_llegibles"] == [".env.example", "claus.local"]
    fora = nucli("finish", cwd=wt)  # fora del sandbox, el fitxer nou es veu: l'arbre no és net
    assert fora.returncode == 1 and "l'arbre de treball no és net" in fora.stderr and "?? claus.local" in fora.stderr


# ---------- fora del sandbox: finish, sense excepcions ----------

@cal_sandbox
def test_finish_detecta_el_canvi_que_el_sandbox_no_veia(wt, gh_fals):
    una_nota(wt)
    escriu(wt, ".env.example", "CLAU=secreta\n")  # canviat de debò, sense commit
    plan = nucli_sandbox(env(wt), "ship", "plan", cwd=wt)
    assert "fora del pla" in plan.stdout
    assert nucli_sandbox(env(wt), "ship", "seal", cwd=wt).returncode == 0  # dins del sandbox no es pot veure
    r = nucli("finish", cwd=wt)
    assert r.returncode == 1 and "l'arbre de treball no és net" in r.stderr and " M .env.example" in r.stderr
    assert "worktree-feina" not in branques_remot(wt) and not gh_fals["registre"].exists()


@cal_sandbox
def test_finish_dins_del_sandbox_plega_sense_pujar_res(wt, gh_fals):
    una_nota(wt)
    assert nucli_sandbox(env(wt), "ship", "seal", cwd=wt).returncode == 0
    r = nucli_sandbox(env(wt), "finish", cwd=wt)
    assert r.returncode == 1 and "l'arbre de treball no és net" in r.stderr
    assert ".env.example: no el puc llegir (sense permís)" in r.stderr
    assert "worktree-feina" not in branques_remot(wt) and not gh_fals["registre"].exists()


@cal_sandbox
def test_finish_fora_del_sandbox_amb_el_fitxer_intacte_puja(wt, gh_fals):
    una_nota(wt)
    assert nucli_sandbox(env(wt), "ship", "seal", cwd=wt).returncode == 0
    r = nucli("finish", cwd=wt)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Dins del sandbox no es podien llegir: .env.example. Aquí sí, i no han canviat: l'arbre és net." in r.stdout
    assert "refs/heads/worktree-feina" in branques_remot(wt)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ho pot llegir tot")
def test_finish_plega_amb_un_fitxer_que_no_pot_llegir(fes_repo, gh_fals):
    """Sense sandbox-exec: una carpeta sense permisos (EACCES). Finish no fa cap excepció, sigui quin sigui el motiu."""
    arrel = fes_repo(config=CONFIG, fitxers={"conf/.env.example": "CLAU=\n"})
    git(arrel, "checkout", "-q", "-b", "docs")
    una_nota(arrel)
    assert nucli("ship", "seal", cwd=arrel).returncode == 0
    conf = arrel / "conf"
    conf.chmod(0)
    try:
        r = nucli("finish", cwd=arrel)
    finally:
        conf.chmod(0o755)
    assert r.returncode == 1 and "conf/.env.example: no el puc llegir (sense permís)" in r.stderr
    assert "refs/heads/docs" not in branques_remot(arrel) and not gh_fals["registre"].exists()
