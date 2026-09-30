"""F3: .gitignore i .worktreeinclude, nucli port, nucli neteja i l'anàlisi de permisos per als worktrees (§7.1)."""
import json
import os
import pty
import socket
import subprocess
import sys

import pytest

from conftest import BIN, CONFIG_MINIMA, commit, escriu, git, nucli
from nucli import permisos
from nucli.comu import port_de

PREFIX = "~/PROJECTS/MARCADOR/marcador"


def settings_marcador(prefix=PREFIX):
    return {
        "permissions": {
            "allow": ["Bash(gh run list:*)", "Bash(bash scripts/llanca-sync.sh)"],
            "deny": [f"Read({prefix}/.env)", f"Read({prefix}/**/.env)", f"Edit({prefix}/.env)", f"Edit({prefix}/**/.env)",
                     f"Edit({prefix}/.env.*)", f"Edit({prefix}/**/.env.*)", f"Edit({prefix}/web/config.js)",
                     f"Edit({prefix}/web/escut.png)", f"Edit({prefix}/.mcp.json)", f"Edit({prefix}/scripts/llanca-sync.sh)",
                     "Bash(*.env*)"],
            "ask": ["Bash(git push:*)", "Bash(*deploy.sh*)"],
        },
        "sandbox": {"enabled": True, "excludedCommands": ["gh *", "bash scripts/deploy.sh", "bash scripts/llanca-sync.sh"]},
    }


@pytest.fixture
def marcador(fes_repo):
    """Un repo sota HOME amb les regles del marcador ancorades al seu camí amb ~/."""
    return fes_repo("home/PROJECTS/MARCADOR/marcador", config=CONFIG_MINIMA, fitxers={
        ".claude/settings.json": json.dumps(settings_marcador(), indent=2) + "\n",
        "scripts/llanca-sync.sh": "echo sync\n", "scripts/deploy.sh": "echo deploy\n", "web/index.html": "<p>\n",
    })


def aplica(dades: dict, propostes: list) -> dict:
    for p in propostes:
        if p.llista == "sandbox.excludedCommands":
            llista = dades["sandbox"]["excludedCommands"]
        else:
            llista = dades["permissions"].setdefault(p.llista, [])
        if p.vella:
            llista[llista.index(p.vella)] = p.nova
        else:
            llista.append(p.nova)
    return dades


# ---------- anàlisi de permisos ----------

def test_proposta_del_marcador(marcador):
    an = permisos.analitza(marcador, "origin/main")
    fets = {(p.llista, p.nova, p.vella) for p in an.propostes}
    abs_sync = f"{marcador}/scripts/llanca-sync.sh"
    assert fets == {
        ("deny", f"Edit({PREFIX}/.claude/worktrees/**/web/config.js)", None),
        ("deny", f"Edit({PREFIX}/.claude/worktrees/**/web/escut.png)", None),
        ("deny", f"Edit({PREFIX}/.claude/worktrees/**/.mcp.json)", None),
        ("deny", f"Edit({PREFIX}/.claude/worktrees/**/scripts/llanca-sync.sh)", None),
        ("allow", f"Bash(bash {abs_sync})", "Bash(bash scripts/llanca-sync.sh)"),
        ("sandbox.excludedCommands", f"bash {abs_sync}", "bash scripts/llanca-sync.sh"),
    }
    assert all(p.estat == permisos.PENDENT for p in an.propostes) and len(an.pendents()) == 6
    assert any("bash scripts/deploy.sh" in a for a in an.avisos)  # relatiu però sense allow: avís, no bloqueja


def test_aplicada_al_checkout_principal_pero_no_a_la_base(marcador):
    cami = marcador / ".claude/settings.json"
    an = permisos.analitza(marcador, "origin/main")
    cami.write_text(json.dumps(aplica(json.loads(cami.read_text()), an.propostes), indent=2))
    an = permisos.analitza(marcador, "origin/main")
    assert len(an.pendents()) == 6 and all(p.estat == permisos.AL_PRINCIPAL for p in an.propostes)
    commit(marcador, "fix(claude): permisos per als worktrees")
    assert len(permisos.analitza(marcador, "origin/main").pendents()) == 6  # encara no és a origin/main
    git(marcador, "push", "-q", "origin", "main")
    git(marcador, "fetch", "-q")
    an = permisos.analitza(marcador, "origin/main")
    assert an.pendents() == [] and an.propostes == []


def test_al_settings_local_o_a_l_usuari_tambe_valen(marcador, entorn):
    an = permisos.analitza(marcador, "origin/main")
    deny = [p.nova for p in an.propostes if p.llista == "deny"]
    escriu(marcador, ".claude/settings.local.json", json.dumps({"permissions": {"deny": deny[:2]}}))
    escriu(entorn, ".claude/settings.json", json.dumps({"permissions": {"deny": deny[2:]}}))
    an = permisos.analitza(marcador, "origin/main")
    assert {p.llista for p in an.pendents()} == {"allow", "sandbox.excludedCommands"}


def test_una_regla_mes_ampla_ja_ho_cobreix(marcador):
    cami = marcador / ".claude/settings.json"
    dades = json.loads(cami.read_text())
    dades["permissions"]["deny"] += [f"Edit({PREFIX}/**/.mcp.json)", f"Edit({PREFIX}/.claude/worktrees/*/web/**)"]
    cami.write_text(json.dumps(dades))
    commit(marcador, "fix: més ample")
    git(marcador, "push", "-q", "origin", "main")
    git(marcador, "fetch", "-q")
    novas = {p.nova for p in permisos.analitza(marcador, "origin/main").propostes}
    assert novas == {f"Edit({PREFIX}/.claude/worktrees/**/scripts/llanca-sync.sh)",
                     f"Bash(bash {marcador}/scripts/llanca-sync.sh)", f"bash {marcador}/scripts/llanca-sync.sh"}


def test_ancoratge_absolut_bash_i_write(fes_repo):
    arrel = fes_repo("abs", config=CONFIG_MINIMA, fitxers={"x.sh": "true\n"})
    escriu(arrel, ".claude/settings.json", json.dumps({"permissions": {
        "deny": [f"Edit(/{arrel}/secret.txt)", f"Bash(rm -rf {arrel}/dades:*)", f"Write(/{arrel}/w.txt)", "Edit(/rel.txt)"],
        "ask": [f"Read(/{arrel}/privat/**)"],
    }}))
    an = permisos.analitza(arrel, "origin/main")
    fets = {(p.llista, p.nova) for p in an.propostes}
    assert fets == {
        ("deny", f"Edit(/{arrel}/.claude/worktrees/**/secret.txt)"),
        ("deny", f"Bash(rm -rf {arrel}/.claude/worktrees/*/dades:*)"),
        ("ask", f"Read(/{arrel}/.claude/worktrees/**/privat/**)"),
    }
    assert any("Write(" in a and "no es consulta mai" in a for a in an.avisos)


def test_sense_regles_ancorades_no_hi_ha_res(fes_repo):
    arrel = fes_repo(config=CONFIG_MINIMA)
    assert permisos.analitza(arrel, "origin/main").propostes == []


def test_init_avisa_i_escriu_la_proposta(marcador):
    r = nucli("init", "--dry-run", cwd=marcador)
    assert "⚠ WORKTREES NO PROTEGITS en aquest repo: 6 regla(es)" in r.stdout
    assert "nucli agent es nega a arrencar" in r.stdout
    assert not (marcador / ".nucli/proposta/permisos.md").exists()
    r = nucli("init", cwd=marcador)
    assert r.returncode == 0, r.stderr
    text = (marcador / ".nucli/proposta/permisos.md").read_text()
    assert "substitueix `Bash(bash scripts/llanca-sync.sh)`" in text and "origin/main" in text
    assert "⚠ WORKTREES NO PROTEGITS" in r.stdout
    settings = json.loads((marcador / ".claude/settings.json").read_text())
    assert "Bash(bash scripts/llanca-sync.sh)" in settings["permissions"]["allow"]  # no aplica res
    assert f"Edit({PREFIX}/.claude/worktrees/**/.mcp.json)" not in settings["permissions"]["deny"]
    r = nucli("init", cwd=marcador)
    assert "Res a fer" in r.stdout and "⚠ WORKTREES NO PROTEGITS" in r.stdout  # idempotent, i continua avisant


def test_init_sense_forats_no_avisa(marcador):
    cami = marcador / ".claude/settings.json"
    an = permisos.analitza(marcador, "origin/main")
    cami.write_text(json.dumps(aplica(json.loads(cami.read_text()), an.propostes), indent=2) + "\n")
    commit(marcador, "fix(claude): permisos per als worktrees")
    git(marcador, "push", "-q", "origin", "main")
    r = nucli("init", cwd=marcador)
    assert "WORKTREES NO PROTEGITS" not in r.stdout
    assert "permisos dels worktrees · cap regla" in r.stdout


# ---------- .gitignore i .worktreeinclude ----------

def test_worktreeinclude(fes_repo):
    arrel = fes_repo(config=None)
    nucli("init", cwd=arrel)
    assert (arrel / ".worktreeinclude").read_text().startswith("# nucli: aquí només hi va")
    assert ".claude/worktrees/" in (arrel / ".gitignore").read_text()
    amb_dev = fes_repo("dev", config=None, fitxers={".env.dev": "A=1\n"})
    nucli("init", cwd=amb_dev)
    assert (amb_dev / ".worktreeinclude").read_text().splitlines()[-1] == ".env.dev"
    propi = fes_repo("propi", config=None, fitxers={".worktreeinclude": "config/x\n"})
    r = nucli("init", cwd=propi)
    assert (propi / ".worktreeinclude").read_text() == "config/x\n" and "ja hi és  .worktreeinclude" in r.stdout


# ---------- port ----------

def test_port_estable_i_dins_del_rang(fes_repo):
    arrel = fes_repo()
    (arrel / "sub").mkdir()
    r1, r2 = nucli("port", cwd=arrel), nucli("port", cwd=arrel / "sub")
    assert r1.stdout == r2.stdout and 4100 <= int(r1.stdout) <= 4999
    assert int(r1.stdout) == port_de(arrel)


def test_port_comprova_ocupat(fes_repo):
    arrel = fes_repo()
    port = port_de(arrel)
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen()
        r = nucli("port", "--comprova", cwd=arrel)
    assert r.returncode == 1 and "ocupat" in r.stderr
    assert nucli("port", "--comprova", cwd=arrel).returncode == 0


# ---------- neteja ----------

def nou_wt(arrel, nom, branca=None):
    cami = arrel / ".claude/worktrees" / nom
    git(arrel, "worktree", "add", "-q", "-b", branca or f"worktree-{nom}", str(cami), "origin/main")
    return cami


@pytest.fixture
def escenari(fes_repo, tmp_path, monkeypatch):
    arrel = fes_repo()
    # fusionat per història
    a = nou_wt(arrel, "historia")
    escriu(a, "a.txt", "a\n")
    commit(a, "feat: a")
    git(arrel, "merge", "-q", "--ff-only", "worktree-historia")
    git(arrel, "push", "-q", "origin", "main")
    # fusionat amb squash des de GitHub (gh simulat diu que el PR es va fusionar amb aquest HEAD)
    b = nou_wt(arrel, "squash")
    escriu(b, "b.txt", "b\n")
    head_b = commit(b, "feat: b")
    # brut, bloquejat, no fusionat i una branca que no és worktree-*
    c = nou_wt(arrel, "brut")
    escriu(c, "c.txt", "c\n")
    d = nou_wt(arrel, "bloquejat")
    git(arrel, "worktree", "lock", str(d))
    e = nou_wt(arrel, "viu")
    escriu(e, "e.txt", "e\n")
    commit(e, "feat: e")
    nou_wt(arrel, "altra", branca="feature/x")
    # branques locals sense worktree: una ja fusionada a origin/main per història i una de viva
    git(arrel, "switch", "-q", "-c", "feature/fusionada")
    escriu(arrel, "f.txt", "f\n")
    commit(arrel, "feat: f")
    git(arrel, "switch", "-q", "main")
    git(arrel, "merge", "-q", "--ff-only", "feature/fusionada")
    git(arrel, "push", "-q", "origin", "main")
    git(arrel, "switch", "-q", "-c", "feature/viva")
    escriu(arrel, "v.txt", "v\n")
    commit(arrel, "feat: v")
    git(arrel, "switch", "-q", "main")
    bin_fals = tmp_path / "bin"
    bin_fals.mkdir()
    (bin_fals / "gh").write_text(
        "#!/bin/bash\n"
        f'if [[ "$*" == *"worktree-squash"* ]]; then echo \'[{{"number": 12, "headRefOid": "{head_b}"}}]\'; '
        'else echo "[]"; fi\n')
    (bin_fals / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_fals}:{os.environ['PATH']}")
    return arrel


def test_neteja_dry_run(escenari):
    r = nucli("neteja", "--dry-run", cwd=escenari)
    assert r.returncode == 0, r.stderr
    assert "treu     historia (worktree-historia) · ja és a origin/main (història)" in r.stdout
    assert "treu     squash (worktree-squash) · PR #12 fusionat amb aquest mateix HEAD" in r.stdout
    assert "es queda brut: té canvis sense commit" in r.stdout
    assert "es queda bloquejat: bloquejat" in r.stdout
    assert "es queda viu: no està fusionat" in r.stdout
    assert "es queda altra: la branca «feature/x» no és worktree-*" in r.stdout
    assert "esborra  branca feature/fusionada · ja és a origin/main (història)" in r.stdout
    esborra = [l for l in r.stdout.splitlines() if l.startswith("  esborra")]
    assert len(esborra) == 1  # ni la viva, ni main, ni les que té un worktree (feature/x, worktree-*)
    assert (escenari / ".claude/worktrees/historia").is_dir()
    assert "feature/fusionada" in git(escenari, "branch", "--list")


def test_neteja_sense_terminal_no_toca_res(escenari):
    r = nucli("neteja", cwd=escenari)
    assert r.returncode == 1 and "cal un terminal" in r.stderr
    assert (escenari / ".claude/worktrees/squash").is_dir()


def test_neteja_amb_confirmacio(escenari):
    mestre, esclau = pty.openpty()
    os.write(mestre, b"s\n")
    r = subprocess.run([sys.executable, str(BIN), "neteja"], cwd=str(escenari), stdin=esclau,
                       capture_output=True, text=True)
    os.close(esclau)
    os.close(mestre)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (escenari / ".claude/worktrees/historia").exists()
    assert not (escenari / ".claude/worktrees/squash").exists()
    branques = git(escenari, "branch", "--list")
    assert "worktree-historia" not in branques and "worktree-squash" not in branques
    for queda in ("brut", "bloquejat", "viu", "altra"):
        assert (escenari / ".claude/worktrees" / queda).is_dir()
    assert "  ✓ branca feature/fusionada" in r.stdout
    assert "feature/fusionada" not in branques
    assert "feature/viva" in branques and "main" in branques and "feature/x" in branques


def amb_terminal(cwd, resposta):
    mestre, esclau = pty.openpty()
    os.write(mestre, resposta)
    try:
        return subprocess.run([sys.executable, str(BIN), "neteja"], cwd=str(cwd), stdin=esclau,
                              capture_output=True, text=True)
    finally:
        os.close(esclau)
        os.close(mestre)


def test_neteja_branques_mai_l_actual_ni_la_base_i_mai_amb_força(fes_repo):
    """v0.1.3: git branch -d i prou. Si git s'hi nega, la branca es queda."""
    arrel = fes_repo()
    # feature/remota és a origin/main, però no al main local ni a HEAD i no té upstream: git branch -d s'hi nega
    git(arrel, "switch", "-q", "-c", "feature/remota")
    escriu(arrel, "r.txt", "r\n")
    commit(arrel, "feat: r")
    git(arrel, "push", "-q", "origin", "feature/remota:main")
    git(arrel, "switch", "-q", "main")
    # la branca actual (fusionada) i main (la base, ara sense cap worktree) no surten mai
    git(arrel, "switch", "-q", "-c", "feature/actual")
    r = nucli("neteja", "--dry-run", cwd=arrel)
    assert r.returncode == 0, r.stderr
    esborra = [l for l in r.stdout.splitlines() if l.startswith("  esborra")]
    assert esborra == ["  esborra  branca feature/remota · ja és a origin/main (història)"]
    r = amb_terminal(arrel, b"s\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "✗ branca feature/remota" in r.stderr
    assert set(git(arrel, "branch", "--format=%(refname:short)").split()) == {"main", "feature/actual", "feature/remota"}


def test_neteja_branques_amb_un_no_no_toca_res(escenari):
    r = amb_terminal(escenari, b"n\n")
    assert r.returncode == 0 and "No he tocat res." in r.stdout
    assert "esborro 1 branca(es) local(s) fusionada(es) amb git branch -d? [s/N]" in r.stdout
    assert "feature/fusionada" in git(escenari, "branch", "--list")
    assert (escenari / ".claude/worktrees/historia").is_dir()


def test_neteja_sense_res_fusionat(fes_repo):
    arrel = fes_repo()
    git(arrel, "branch", "feature/viva")
    git(arrel, "switch", "-q", "feature/viva")
    escriu(arrel, "v.txt", "v\n")
    commit(arrel, "feat: v")
    git(arrel, "switch", "-q", "main")
    r = nucli("neteja", cwd=arrel)
    assert r.returncode == 0 and "Res a netejar." in r.stdout and "esborra" not in r.stdout


def test_neteja_des_d_un_worktree_plega(escenari):
    r = nucli("neteja", "--dry-run", cwd=escenari / ".claude/worktrees/viu")
    assert r.returncode == 1 and "al checkout principal" in r.stderr
