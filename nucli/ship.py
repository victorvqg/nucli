"""Porta amb rebut: `nucli ship plan | run <check> | seal`.

Les regles i les ordres surten del nucli.json del checkout principal, mai del worktree. Un check només val
si s'ha executat sobre l'arbre exacte de HEAD, i el segell es recalcula sempre des del diff.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSIO
from .comu import Plega, Repo, git, port_de, troba_repo
from .config import CHECK_REVISIO_CONFIG, TEXT_REVISIO_CONFIG
from .patrons import algun, coincideix

# Regla fixa del nucli (principi e): tocar configuració o seguretat demana revisió humana. No és configurable.
PATRONS_CONFIG = ["/nucli.json", ".claude/", ".mcp.json", ".worktreeinclude", ".gitignore", "githooks/"]
MAX_SORTIDA = 20 * 1024


def ara() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------- classificador ----------

@dataclass
class Fitxer:
    estat: str
    cami: str
    regles: list            # índexs (1..n) de les regles que hi coincideixen
    checks: list
    config: bool = False


@dataclass
class Pla:
    ref_base: str
    merge_base: str
    fitxers: list = field(default_factory=list)
    requerits: list = field(default_factory=list)

    def automatics(self, cfg: dict) -> list:
        return [c for c in self.requerits if c != CHECK_REVISIO_CONFIG and "ordre" in cfg["checks"][c]]

    def manuals(self, cfg: dict) -> list:
        return [c for c in self.requerits if c == CHECK_REVISIO_CONFIG or "manual" in cfg["checks"][c]]


def text_manual(cfg: dict, nom: str) -> str:
    return TEXT_REVISIO_CONFIG if nom == CHECK_REVISIO_CONFIG else cfg["checks"][nom]["manual"]


def fitxers_del_diff(repo: Repo, merge_base: str) -> list:
    """(estat, camí) de tot el que canvia respecte del merge-base: commits, canvis sense commit i fitxers nous.

    Dels renomenats i esborrats també compta la ruta vella.
    """
    out = []
    camps = repo.git("diff", "--name-status", "-M", "-z", merge_base).split("\0")
    i = 0
    while i < len(camps) and camps[i]:
        estat = camps[i]
        if estat[0] in "RC":
            out.append((estat[0], camps[i + 1]))
            out.append((estat[0], camps[i + 2]))
            i += 3
        else:
            out.append((estat[0], camps[i + 1]))
            i += 2
    for cami in repo.git("ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if cami:
            out.append(("?", cami))
    vistos, unics = set(), []
    for e, c in out:
        if c not in vistos:
            vistos.add(c)
            unics.append((e, c))
    return unics


def classifica(cfg: dict, fitxers: list) -> tuple:
    """Torna ([Fitxer], requerits) aplicant les regles de nucli.json i la regla fixa de configuració."""
    ordre_checks = list(cfg["checks"])
    requerits, resultat = set(), []
    for estat, cami in fitxers:
        idx = [n for n, r in enumerate(cfg["regles"], 1) if algun(r["patrons"], cami)]
        if idx:
            checks = []
            for n in idx:
                checks += [c for c in cfg["regles"][n - 1]["checks"] if c not in checks]
        else:
            checks = list(cfg["per_defecte"])
        f = Fitxer(estat, cami, idx, checks)
        if any(coincideix(p, cami) for p in PATRONS_CONFIG):
            f.config = True
            f.checks = f.checks + [CHECK_REVISIO_CONFIG]
        requerits.update(f.checks)
        resultat.append(f)
    ordenats = [c for c in ordre_checks if c in requerits]
    if CHECK_REVISIO_CONFIG in requerits:
        ordenats.append(CHECK_REVISIO_CONFIG)
    return resultat, ordenats


def calcula_pla(repo: Repo) -> Pla:
    cfg = repo.config()
    ref = repo.ref_base()
    if not repo.git_ok("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
        raise Plega(f"no trobo la base «{ref}» (branca_base de nucli.json)")
    mb = repo.git("merge-base", ref, "HEAD")
    fitxers, requerits = classifica(cfg, fitxers_del_diff(repo, mb))
    return Pla(ref, mb, fitxers, requerits)


# ---------- arbre i estat de git ----------

def arbre_de_treball(repo: Repo) -> str:
    """L'arbre que tindria un commit de tot el directori de treball ara mateix (git add -A en un índex temporal)."""
    d = repo.dir_nucli(crea=True)
    index = d / f"index-{os.getpid()}"
    env = dict(os.environ, GIT_INDEX_FILE=str(index))
    try:
        if repo.git_ok("rev-parse", "--verify", "--quiet", "HEAD"):
            git("read-tree", "HEAD", cwd=repo.worktree, env=env)
        git("add", "-A", cwd=repo.worktree, env=env)
        return git("write-tree", cwd=repo.worktree, env=env)
    finally:
        if index.exists():
            index.unlink()


def canvis_pendents(repo: Repo) -> list:
    return [l for l in repo.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.strip()]


def arbre_head(repo: Repo) -> str:
    return repo.git("rev-parse", "HEAD^{tree}")


# ---------- rebut ----------

def cami_rebut(repo: Repo, branca: str) -> Path:
    return repo.dir_nucli() / "rebuts" / (branca.replace("/", "__") + ".json")


def branca_amb_rebut(repo: Repo) -> str:
    b = repo.branca()
    if b == "HEAD":
        raise Plega("HEAD desenganxat: el rebut va lligat a una branca")
    return b


def llegeix_rebut(repo: Repo, branca: str, exigeix: bool = False) -> dict:
    p = cami_rebut(repo, branca)
    if not p.is_file():
        if exigeix:
            raise Plega(f"no hi ha rebut per a la branca {branca}: executa «nucli ship plan», els checks amb "
                        "«nucli ship run <check>» i «nucli ship seal»")
        return {"versio": 1, "branca": branca, "execucions": [], "segell": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise Plega(f"el rebut {p} no és JSON vàlid: esborra'l i torna a executar els checks")


def desa_rebut(repo: Repo, rebut: dict) -> None:
    p = cami_rebut(repo, rebut["branca"])
    repo.dir_nucli(crea=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rebut, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def sha_rebut(rebut: dict) -> str:
    segell = {k: v for k, v in (rebut.get("segell") or {}).items() if k != "sha256"}
    canonic = {"versio": rebut.get("versio"), "branca": rebut.get("branca"),
               "execucions": rebut.get("execucions"), "segell": segell}
    return hashlib.sha256(json.dumps(canonic, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def ultima(rebut: dict, check: str):
    for e in reversed(rebut.get("execucions", [])):
        if e.get("check") == check:
            return e
    return None


def problemes_checks(rebut: dict, automatics: list, arbre: str) -> list:
    """Per a cada check automàtic requerit, què falla perquè valgui sobre l'arbre de HEAD."""
    out = []
    for c in automatics:
        e = ultima(rebut, c)
        if e is None:
            out.append(f"{c}: no s'ha executat mai (nucli ship run {c})")
        elif e.get("codi") != 0:
            out.append(f"{c}: l'última execució ha fallat (codi {e.get('codi')}, {e.get('hora')})")
        elif e.get("arbre") != arbre:
            out.append(f"{c}: executat sobre un arbre diferent del de HEAD (has editat després?): nucli ship run {c}")
    return out


# ---------- execució d'un check ----------

def entorn_nucli(repo: Repo, check: str) -> dict:
    env = dict(os.environ)
    env.update({
        "NUCLI_ARREL": str(repo.arrel),
        "NUCLI_WORKTREE": str(repo.worktree),
        "NUCLI_PORT": str(port_de(repo.worktree)),
        "NUCLI_CHECK": check,
    })
    return env


def executa_check(repo: Repo, cfg: dict, nom: str, via: str) -> dict:
    ordre_shell = cfg["checks"][nom]["ordre"]
    arbre = arbre_de_treball(repo)
    head = repo.git("rev-parse", "HEAD")
    print(f"── nucli · {nom}: {ordre_shell}", flush=True)
    t0 = time.monotonic()
    proc = subprocess.Popen(["bash", "-c", ordre_shell], cwd=str(repo.worktree), env=entorn_nucli(repo, nom),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf, retallada = bytearray(), False
    while True:
        tros = os.read(proc.stdout.fileno(), 65536)
        if not tros:
            break
        sys.stdout.buffer.write(tros)
        sys.stdout.flush()
        buf += tros
        if len(buf) > MAX_SORTIDA:
            del buf[:-MAX_SORTIDA]
            retallada = True
    codi = proc.wait()
    execucio = {
        "check": nom, "ordre": ordre_shell, "codi": codi, "durada_s": round(time.monotonic() - t0, 2),
        "sortida": buf.decode("utf-8", "replace"), "retallada": retallada, "hora": ara(),
        "head": head, "arbre": arbre, "via": via,
    }
    despres = arbre_de_treball(repo)
    if despres != arbre:
        execucio["arbre_despres"] = despres
    estat = "✓" if codi == 0 else f"✗ codi {codi}"
    print(f"── nucli · {nom}: {estat} ({execucio['durada_s']} s)", flush=True)
    if despres != arbre:
        print(f"── nucli · avís: {nom} ha modificat fitxers del directori de treball", flush=True)
    return execucio


# ---------- ordres ----------

def ordre_plan(repo: Repo) -> int:
    cfg = repo.config()
    pla = calcula_pla(repo)
    print(f"nucli ship plan · branca {repo.branca()} · base {pla.ref_base} (merge-base {pla.merge_base[:8]})")
    print(f"Regles: {repo.cami_config}")
    if not pla.fitxers:
        print("Cap canvi respecte de la base: cap check requerit.")
        return 0
    ample = min(max(len(f.cami) for f in pla.fitxers), 48)
    for f in pla.fitxers:
        if f.regles:
            on = "regla " + ", ".join(str(n) for n in f.regles)
        else:
            on = "sense regla → per defecte"
        checks = ", ".join(f.checks) if f.checks else "(cap)"
        print(f"  {f.estat}  {f.cami:<{ample}}  {on} → {checks}")
    if not pla.requerits:
        print("Checks requerits: cap.")
        return 0
    print("Checks requerits:")
    for c in pla.requerits:
        if c in pla.automatics(cfg):
            ch = cfg["checks"][c]
            fora = "  (fora del sandbox: el passa nucli agent o tu amb !)" if ch.get("fora_sandbox") else ""
            print(f"  {c:<15} automàtic  {ch['ordre']}{fora}")
        else:
            print(f"  {c:<15} manual     {text_manual(cfg, c)} (es confirma a nucli finish)")
    return 0


def ordre_run(repo: Repo, nom: str) -> int:
    cfg = repo.config()
    if nom == CHECK_REVISIO_CONFIG or nom in cfg["checks"] and "manual" in cfg["checks"][nom]:
        print(f"nucli: «{nom}» és un check manual: no s'executa, el confirma una persona a nucli finish", file=sys.stderr)
        return 2
    if nom not in cfg["checks"]:
        raise Plega(f"el check «{nom}» no és a nucli.json ({', '.join(cfg['checks']) or 'no n’hi ha cap'})", codi=2)
    branca = branca_amb_rebut(repo)
    rebut = llegeix_rebut(repo, branca)
    execucio = executa_check(repo, cfg, nom, via="ship")
    rebut["execucions"].append(execucio)
    rebut["segell"] = None  # qualsevol execució nova invalida el segell anterior
    desa_rebut(repo, rebut)
    return execucio["codi"]


def ordre_seal(repo: Repo) -> int:
    cfg = repo.config()
    branca = branca_amb_rebut(repo)
    pla = calcula_pla(repo)
    pendents = canvis_pendents(repo)
    if pendents:
        raise Plega("l'arbre de treball no és net: fes commit (o descarta) abans de segellar:\n  " + "\n  ".join(pendents[:20]))
    rebut = llegeix_rebut(repo, branca)
    arbre = arbre_head(repo)
    problemes = problemes_checks(rebut, pla.automatics(cfg), arbre)
    if problemes:
        raise Plega("no segello:\n  " + "\n  ".join(problemes))
    segell = {
        "head": repo.git("rev-parse", "HEAD"), "arbre": arbre, "hora": ara(), "requerits": pla.requerits,
        "manuals_pendents": pla.manuals(cfg), "nucli": VERSIO,
    }
    rebut["segell"] = segell
    segell["sha256"] = sha_rebut(rebut)
    desa_rebut(repo, rebut)
    print(f"nucli ship seal · segellat · HEAD {segell['head'][:8]} · requerits: {', '.join(pla.requerits) or 'cap'}")
    if segell["manuals_pendents"]:
        print(f"Manuals pendents (els confirma una persona a nucli finish): {', '.join(segell['manuals_pendents'])}")
    return 0


def ordre(args) -> int:
    repo = troba_repo()
    if args.pas == "plan":
        return ordre_plan(repo)
    if args.pas == "run":
        return ordre_run(repo, args.check)
    return ordre_seal(repo)
