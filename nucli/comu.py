"""Peces comunes: errors, crides a git i les dues arrels (checkout principal i worktree)."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Optional

FITXER_CONFIG = "nucli.json"
DIR_NUCLI = ".nucli"


class Plega(Exception):
    """Error esperat: es mostra tal qual i l'ordre surt amb `codi`."""

    def __init__(self, missatge: str, codi: int = 1):
        super().__init__(missatge)
        self.codi = codi


def git(*args: str, cwd, check: bool = True, env: Optional[dict] = None, entrada: Optional[str] = None) -> str:
    """Executa git a `cwd` i en torna la sortida sense el salt de línia final."""
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env, input=entrada)
    if check and r.returncode != 0:
        detall = (r.stderr or r.stdout).strip()
        raise Plega(f"git {' '.join(args)} ha fallat: {detall}")
    return r.stdout.rstrip("\n")


def git_ok(*args: str, cwd, env: Optional[dict] = None) -> bool:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, env=env).returncode == 0


def arrel_principal(worktree: Path) -> Path:
    """L'arrel del checkout principal: la primera entrada de `git worktree list`."""
    for linia in git("worktree", "list", "--porcelain", cwd=worktree).splitlines():
        if linia.startswith("worktree "):
            return Path(linia[len("worktree "):]).resolve()
    return worktree


class Repo:
    """Un repo git vist des d'un directori.

    `worktree` és l'arrel del checkout on ets (NUCLI_WORKTREE) i `arrel` la del checkout principal (NUCLI_ARREL).
    Fora d'un worktree, són la mateixa.
    """

    def __init__(self, cwd):
        self.cwd = Path(cwd).resolve()
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(self.cwd), capture_output=True, text=True)
        if r.returncode != 0:
            raise Plega(f"no ets dins d'un repo git ({self.cwd})")
        self.worktree = Path(r.stdout.strip()).resolve()
        self.arrel = arrel_principal(self.worktree)
        self._config = None

    @property
    def es_worktree(self) -> bool:
        return self.worktree != self.arrel

    @property
    def cami_config(self) -> Path:
        return self.arrel / FITXER_CONFIG

    def te_config(self) -> bool:
        return self.cami_config.is_file()

    def config(self) -> dict:
        """El nucli.json del checkout principal, validat i completat amb els valors per defecte."""
        if self._config is None:
            from . import config
            self._config = config.llegeix(self.cami_config)
        return self._config

    def git(self, *args: str, **kw) -> str:
        return git(*args, cwd=self.worktree, **kw)

    def git_ok(self, *args: str) -> bool:
        return git_ok(*args, cwd=self.worktree)

    def branca(self) -> str:
        """La branca actual del worktree, o «HEAD» si està desenganxat."""
        return self.git("rev-parse", "--abbrev-ref", "HEAD")

    def ref_base(self) -> str:
        """`origin/<branca_base>` si el remot la té, i si no, `<branca_base>` local."""
        base = self.config()["branca_base"]
        if self.git_ok("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{base}"):
            return f"origin/{base}"
        return base

    def dir_nucli(self, crea: bool = False) -> Path:
        """`.nucli/` del worktree actual, amb el seu propi .gitignore perquè no embruti mai l'arbre."""
        d = self.worktree / DIR_NUCLI
        if crea:
            prepara_dir_nucli(d)
        return d


def port_de(cami) -> int:
    """4100 + (sha256(camí real) mod 900): estable per a cada worktree. Hi pot haver col·lisions i s'accepta."""
    real = os.path.realpath(str(cami))
    return 4100 + int(hashlib.sha256(real.encode("utf-8")).hexdigest(), 16) % 900


def prepara_dir_nucli(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("# el crea el nucli: tot .nucli/ queda fora de git\n*\n", encoding="utf-8")


def troba_repo(cwd=None, exigeix_config: bool = True) -> Repo:
    """El repo del directori actual. Si cal nucli.json i el checkout principal no en té, plega."""
    repo = Repo(cwd or os.getcwd())
    if exigeix_config and not repo.te_config():
        raise Plega(
            f"aquest repo no té {FITXER_CONFIG} ({repo.arrel}). El nucli només actua als repos que en tenen: "
            "per activar-lo, executa «nucli init» a l'arrel."
        )
    return repo


def repo_amb_nucli(cwd) -> Optional[Repo]:
    """Per als hooks: el repo si és un repo amb nucli.json, i si no (o davant de qualsevol error), None."""
    try:
        if not cwd or not Path(cwd).is_dir():
            return None
        repo = Repo(cwd)
        return repo if repo.te_config() else None
    except Exception:
        return None
