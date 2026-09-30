"""Bastida de proves: HOME i git aïllats, repos temporals amb un remot «bare» i l'ordre nucli real."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ARREL_NUCLI = Path(__file__).resolve().parent.parent
BIN = ARREL_NUCLI / "bin" / "nucli"

CONFIG_MINIMA = {
    "versio": 1,
    "branca_base": "main",
    "checks": {
        "lint": {"ordre": "true"},
        "test": {"ordre": "true"},
        "visual": {"manual": "Revisió visual al mòbil"},
    },
    "regles": [
        {"patrons": ["*.md", "docs/**"], "checks": []},
        {"patrons": ["*.py"], "checks": ["lint", "test"]},
        {"patrons": ["web/**"], "checks": ["lint", "visual"]},
    ],
    "per_defecte": ["lint", "test"],
}


@pytest.fixture(autouse=True)
def entorn(tmp_path, monkeypatch):
    """Cada prova té un HOME propi i una configuració de git que no depèn de la del Mac."""
    home = tmp_path / "home"
    home.mkdir()
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Prova\n\temail = prova@example.com\n[init]\n\tdefaultBranch = main\n"
        "[commit]\n\tgpgsign = false\n[advice]\n\tdetachedHead = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in list(os.environ):
        if var.startswith("NUCLI_") or var in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "GIT_DIR", "GIT_WORK_TREE",
                                               "GIT_INDEX_FILE"):
            monkeypatch.delenv(var, raising=False)
    return home


def sh(*args, cwd, check=True, entrada=None, env=None):
    r = subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True, input=entrada, env=env)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} → {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def git(cwd, *args, check=True):
    return sh("git", *args, cwd=cwd, check=check).stdout.strip()


def nucli(*args, cwd, entrada=None, env_extra=None, python=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    # sense entrada, stdin és /dev/null: una prova no ha d'heretar mai el terminal de qui llança pytest
    return subprocess.run(
        [python or sys.executable, str(BIN), *args], cwd=str(cwd), capture_output=True, text=True, env=env,
        **({"input": entrada} if entrada is not None else {"stdin": subprocess.DEVNULL}),
    )


def escriu(arrel: Path, cami: str, text: str) -> Path:
    p = arrel / cami
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def commit(arrel: Path, missatge: str = "chore: canvi", *camins: str) -> str:
    git(arrel, "add", *(camins or ["-A"]))
    git(arrel, "commit", "-q", "--no-verify", "-m", missatge)
    return git(arrel, "rev-parse", "HEAD")


@pytest.fixture
def fes_repo(tmp_path):
    """Crea un repo amb un commit inicial a main, pujat a un remot bare «origin»."""

    def _fes(nom="repo", config=CONFIG_MINIMA, fitxers=None):
        remot = tmp_path / f"{nom.replace('/', '_')}-origin.git"
        sh("git", "init", "-q", "--bare", "-b", "main", str(remot), cwd=tmp_path)
        arrel = tmp_path / nom
        arrel.mkdir(parents=True)
        git(arrel, "init", "-q", "-b", "main")
        escriu(arrel, "README.md", "# prova\n")
        for cami, text in (fitxers or {}).items():
            escriu(arrel, cami, text)
        if config is not None:
            escriu(arrel, "nucli.json", json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        commit(arrel, "chore: inici")
        git(arrel, "remote", "add", "origin", str(remot))
        git(arrel, "push", "-q", "-u", "origin", "main")
        git(arrel, "remote", "set-head", "origin", "main")
        return arrel.resolve()

    return _fes
