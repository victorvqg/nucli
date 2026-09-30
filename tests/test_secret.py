"""v0.1.3: nucli secret desa a GitHub un valor del .env sense ensenyar-lo, i només la llança una persona.

Motiu: al marcador, copiar la clau del .env amb `cut` hi va enganxar un comentari amb una «é».
"""
import json
import os
import pty
import subprocess
import sys

import pytest

from conftest import BIN, CONFIG_MINIMA, git, nucli
from nucli.comu import Plega
from nucli.secret import descriu, problemes_del_valor, valor_del_env

CLAU = "sb_secret_Zq9xYw8vU7tS6rR5pP4o"
ENV = f"""# Supabase
SUPABASE_URL=https://abc.supabase.co
SUPABASE_SECRET_KEY={CLAU} # clau de producció: no la toquis é
"""


# ---------- lectura del .env ----------

@pytest.mark.parametrize("linia, esperat", [
    ("K=abc", "abc"),
    ("K=abc # comentari amb é", "abc"),
    ("K=abc\t# comentari", "abc"),
    ("  K  =   abc   ", "abc"),
    ("export K=abc", "abc"),
    ("K=abc#def", "abc#def"),              # sense espai davant, el «#» és del valor
    ("K='abc # def' # comentari", "abc # def"),
    ('K="abc # def"   # comentari', "abc # def"),
    ('K="a\\"b\\\\c"', 'a"b\\c'),
    ("K='a\\'b'", "a'b"),
    ('K=""', ""),
    ("K= # només un comentari", ""),
    ("K=#abc", ""),                        # ambigu entre eines: buit, i el valor buit plega
    ("K=abc\r", "abc"),                    # CRLF
])
def test_valor_com_les_eines_habituals(linia, esperat):
    assert valor_del_env(f"A=1\n{linia}\nB=2\n", "K") == (esperat, 2, 1)


def test_l_ultima_assignacio_mana_i_es_compta():
    assert valor_del_env("﻿K=vell\nKK=no\nK=nou\n", "K") == ("nou", 3, 2)


def test_no_hi_es():
    assert valor_del_env("KA=1\n# K=2\nK\n", "K") == (None, 0, 0)


def test_un_salt_de_pagina_no_parteix_la_linia():
    """Només es parteix per «\\n»: un \\f enganxat queda dins del valor i el detecta la comprovació d'ASCII."""
    valor, _, _ = valor_del_env("K=abc\x0cdef\n", "K")
    assert valor == "abc\x0cdef" and problemes_del_valor(valor) == ["posició 4 (caràcter de control)"]


@pytest.mark.parametrize("linia, motiu", [
    ('K="abc', "no es tanca"),
    ("K='abc' xyz", "text després de la cometa"),
])
def test_cometes_mal_tancades_pleguen_sense_ensenyar_el_valor(linia, motiu):
    with pytest.raises(Plega) as e:
        valor_del_env(f"A=1\n{linia}\n", "K")
    assert motiu in str(e.value) and "línia 2" in str(e.value) and "abc" not in str(e.value)


def test_problemes_del_valor():
    assert problemes_del_valor("abc") == []
    assert problemes_del_valor("a b~") == []
    assert problemes_del_valor("aé\tb") == ["posició 2 (no ASCII)", "posició 3 (caràcter de control)"]


@pytest.mark.parametrize("valor, esperat", [
    (CLAU, f"{len(CLAU)} caràcters · comença per «sb_secret_»"),
    ("sb_publishable_xyz123", "21 caràcters · comença per «sb_publish»"),
    ("eyJhbGciOiJIUzI1NiJ9.x.y", "24 caràcters · comença per «eyJhbGciOi»"),
    ("ghp_secretissim", "15 caràcters · no comença per cap prefix conegut, i no n'ensenyo res"),
])
def test_descriu_nomes_ensenya_els_prefixos_coneguts(valor, esperat):
    assert descriu(valor) == esperat


# ---------- l'ordre ----------

@pytest.fixture
def repo(fes_repo):
    arrel = fes_repo(config=CONFIG_MINIMA)
    (arrel / ".env").write_text(ENV, encoding="utf-8")
    return arrel


@pytest.fixture
def gh_fals(tmp_path, monkeypatch):
    d = tmp_path / "bin-gh"
    d.mkdir()
    registre, valor = tmp_path / "gh.log", tmp_path / "gh-valor"
    (d / "gh").write_text(f"""#!/bin/bash
echo "$@" >> "{registre}"
if [ -f "$HOME/gh-falla" ]; then echo "HTTP 404: no existeix l'entorn" >&2; exit 1; fi
cat > "{valor}"
echo "✓ Set Actions secret $3 for prova/repo"
""")
    (d / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    return {"registre": registre, "valor": valor}


def amb_terminal(*args, cwd, resposta=b"s\n", env_extra=None):
    mestre, esclau = pty.openpty()
    os.write(mestre, resposta)
    try:
        return subprocess.run([sys.executable, str(BIN), *args], cwd=str(cwd), stdin=esclau, capture_output=True,
                              text=True, env=dict(os.environ, **(env_extra or {})))
    finally:
        os.close(esclau)
        os.close(mestre)


def sortida(r):
    return r.stdout + r.stderr


def test_cami_bo_el_cas_del_marcador(repo, gh_fals):
    """El comentari amb «é» no hi va: puja exactament la clau, per stdin, i no l'ensenya."""
    r = amb_terminal("secret", "SUPABASE_KEY", "--env", "production", "--des-de", "SUPABASE_SECRET_KEY", cwd=repo)
    assert r.returncode == 0, sortida(r)
    assert gh_fals["registre"].read_text() == "secret set SUPABASE_KEY --env production\n"
    assert gh_fals["valor"].read_text() == CLAU
    assert f"Valor: {len(CLAU)} caràcters · comença per «sb_secret_»" in r.stdout
    assert "des de SUPABASE_SECRET_KEY al .env, línia 3" in r.stdout
    assert "Deso aquest valor com a SUPABASE_KEY a l'entorn «production» de GitHub? [s/N]" in r.stdout
    assert "✓ Set Actions secret SUPABASE_KEY" in r.stdout
    assert CLAU[10:] not in sortida(r)


def test_des_d_un_worktree_llegeix_el_env_del_checkout_principal(repo, gh_fals):
    wt = repo / ".claude/worktrees/feina"
    git(repo, "worktree", "add", "-q", "-b", "worktree-feina", str(wt), "origin/main")
    r = amb_terminal("secret", "SUPABASE_SECRET_KEY", "--env", "production", cwd=wt)
    assert r.returncode == 0, sortida(r)
    assert gh_fals["valor"].read_text() == CLAU


@pytest.mark.parametrize("variable", ["CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"])
def test_dins_de_claude_code_plega_abans_de_llegir_res(repo, gh_fals, variable):
    r = amb_terminal("secret", "SUPABASE_SECRET_KEY", "--env", "production", cwd=repo, env_extra={variable: "1"})
    assert r.returncode == 1 and "dins de Claude Code" in r.stderr and variable in r.stderr
    assert "No he llegit res" in r.stderr and "caràcters" not in r.stdout
    assert not gh_fals["registre"].exists()


def test_sense_terminal_plega(repo, gh_fals):
    r = nucli("secret", "SUPABASE_SECRET_KEY", "--env", "production", cwd=repo, entrada="s\n")
    assert r.returncode == 1 and "cal un terminal" in r.stderr and "No he llegit res" in r.stderr
    assert not gh_fals["registre"].exists()


def test_amb_un_no_no_desa_res(repo, gh_fals):
    r = amb_terminal("secret", "SUPABASE_SECRET_KEY", "--env", "production", cwd=repo, resposta=b"\n")
    assert r.returncode == 1 and "no confirmat: no he desat res" in r.stderr
    assert not gh_fals["registre"].exists()


@pytest.mark.parametrize("linia, missatge", [
    ('K="sb_secret_abc é"', "posició 15 (no ASCII)"),
    ("K=abcdef\tghi", "posició 7 (caràcter de control)"),
    ("K=", "és buida"),
    ("K=   # posa-hi la clau", "és buida"),
])
def test_valors_dolents_no_es_desen(fes_repo, gh_fals, linia, missatge):
    arrel = fes_repo(config=CONFIG_MINIMA)
    (arrel / ".env").write_text(f"A=1\n{linia}\n", encoding="utf-8")
    r = amb_terminal("secret", "K", "--env", "production", cwd=arrel)
    assert r.returncode == 1 and missatge in r.stderr and "línia 2" in r.stderr
    assert "No he desat res" in r.stderr
    assert "abc" not in sortida(r) and "posa-hi" not in sortida(r)
    assert not gh_fals["registre"].exists()


def test_un_env_que_no_es_utf8_tampoc_passa(fes_repo, gh_fals):
    arrel = fes_repo(config=CONFIG_MINIMA)
    (arrel / ".env").write_bytes("K=sb_secret_abc\xe9\n".encode("latin-1"))
    r = amb_terminal("secret", "K", "--env", "production", cwd=arrel)
    assert r.returncode == 1 and "posició 14 (no ASCII)" in r.stderr
    assert not gh_fals["registre"].exists()


def test_prefix_desconegut_nomes_la_longitud_i_avisa_dels_duplicats(fes_repo, gh_fals):
    arrel = fes_repo(config=CONFIG_MINIMA)
    (arrel / ".env").write_text("TOKEN=vell\nTOKEN='ghp_secretissim'\n", encoding="utf-8")
    r = amb_terminal("secret", "TOKEN", "--env", "ci", cwd=arrel)
    assert r.returncode == 0, sortida(r)
    assert "Valor: 15 caràcters · no comença per cap prefix conegut, i no n'ensenyo res" in r.stdout
    assert "TOKEN surt 2 cops al .env. Faig servir l'últim (línia 2)" in r.stdout
    assert "ghp_" not in sortida(r) and "vell" not in sortida(r)
    assert gh_fals["valor"].read_text() == "ghp_secretissim"


@pytest.mark.parametrize("args, missatge", [
    (["GITHUB_TOKEN", "--env", "p"], "no és un nom de secret vàlid"),
    (["1CLAU", "--env", "p"], "no és un nom de secret vàlid"),
    (["CLAU", "--env", "p", "--des-de", "NO HI ES"], "no és un nom de variable"),
    (["NO_HI_ES", "--env", "p"], "NO_HI_ES no és al .env"),
    (["SUPABASE_URL", "--env", "  "], "cal el nom de l'entorn"),
])
def test_arguments_i_claus_que_no_hi_son(repo, gh_fals, args, missatge):
    r = amb_terminal("secret", *args, cwd=repo)
    assert r.returncode == 1 and missatge in r.stderr
    assert not gh_fals["registre"].exists()


def test_sense_env(fes_repo, gh_fals):
    r = amb_terminal("secret", "K", "--env", "p", cwd=fes_repo(config=CONFIG_MINIMA))
    assert r.returncode == 1 and "no trobo el .env" in r.stderr


def test_si_gh_falla_ho_diu(repo, gh_fals, entorn):
    (entorn / "gh-falla").write_text("")
    r = amb_terminal("secret", "SUPABASE_SECRET_KEY", "--env", "noexisteix", cwd=repo)
    assert r.returncode == 1 and "«gh secret set» ha fallat: HTTP 404" in r.stderr
    assert CLAU[10:] not in sortida(r)


def test_fora_d_un_repo_amb_nucli_json_plega(fes_repo, gh_fals):
    arrel = fes_repo(config=None)
    (arrel / ".env").write_text(ENV, encoding="utf-8")
    r = amb_terminal("secret", "SUPABASE_SECRET_KEY", "--env", "production", cwd=arrel)
    assert r.returncode == 1 and "no té nucli.json" in r.stderr
    assert not gh_fals["registre"].exists()


def test_sense_env_obligatori(repo):
    r = nucli("secret", "SUPABASE_SECRET_KEY", cwd=repo)
    assert r.returncode == 2 and "falten aquests arguments: --env" in r.stderr


# ---------- nucli init proposa el deny ----------

def test_init_proposa_el_deny_sense_aplicar_lo(fes_repo):
    arrel = fes_repo(config=CONFIG_MINIMA)
    r = nucli("init", cwd=arrel)
    assert r.returncode == 0, r.stderr
    assert "proposa   .nucli/proposta/deny.md · Bash(nucli secret:*) a deny, sense aplicar-la" in r.stdout
    assert '"Bash(nucli secret:*)",' in (arrel / ".nucli/proposta/deny.md").read_text()
    settings = json.loads((arrel / ".claude/settings.json").read_text())
    assert "deny" not in settings["permissions"]  # només hi afegeix l'ask de nucli finish
    assert "Res a fer" in nucli("init", cwd=arrel).stdout


@pytest.mark.parametrize("on", ["projecte", "local", "usuari"])
def test_init_amb_el_deny_ja_posat_no_proposa_res(fes_repo, entorn, on):
    arrel = fes_repo(config=CONFIG_MINIMA)
    dades = json.dumps({"permissions": {"deny": ["Bash(nucli secret:*)"]}})
    cami = {"projecte": arrel / ".claude/settings.json", "local": arrel / ".claude/settings.local.json",
            "usuari": entorn / ".claude/settings.json"}[on]
    cami.parent.mkdir(parents=True, exist_ok=True)
    cami.write_text(dades)
    r = nucli("init", cwd=arrel)
    assert "ja hi és  deny de nucli secret · Bash(nucli secret:*)" in r.stdout
    assert not (arrel / ".nucli/proposta/deny.md").exists()
