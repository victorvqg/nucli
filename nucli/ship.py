"""Porta amb rebut: `nucli ship plan | run <check> | seal`.

Les regles i les ordres surten del nucli.json del checkout principal, mai del worktree. Un check només val
si s'ha executat sobre l'arbre exacte de HEAD, i el segell es recalcula sempre des del diff.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shlex
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
NO_LLEGIBLE = "no llegible (sandbox)"


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
    no_llegible: bool = False


@dataclass
class Pla:
    ref_base: str
    merge_base: str
    fitxers: list = field(default_factory=list)
    requerits: list = field(default_factory=list)
    no_llegibles: list = field(default_factory=list)

    def fora_del_pla(self) -> list:
        """Els no llegibles sense cap canvi als commits ni a l'índex: no compten ni com a esborrats ni com a canvi."""
        al_pla = {f.cami for f in self.fitxers}
        return [c for c in self.no_llegibles if c not in al_pla]

    def automatics(self, cfg: dict) -> list:
        return [c for c in self.requerits if c != CHECK_REVISIO_CONFIG and "ordre" in cfg["checks"][c]]

    def manuals(self, cfg: dict) -> list:
        return [c for c in self.requerits if c == CHECK_REVISIO_CONFIG or "manual" in cfg["checks"][c]]


def text_manual(cfg: dict, nom: str) -> str:
    return TEXT_REVISIO_CONFIG if nom == CHECK_REVISIO_CONFIG else cfg["checks"][nom]["manual"]


def llegible(cami: Path) -> bool:
    """Fals si no se'n pot ni fer `lstat` per falta de permís (el `denyRead` del sandbox dona EPERM)."""
    try:
        os.lstat(cami)
    except PermissionError:
        return False
    except OSError:
        pass
    return True


def no_llegibles(repo: Repo) -> tuple:
    """(seguits, nous): els fitxers de l'arbre de treball que git veuria però que no es poden llegir.

    Dels seguits, `git status` se'n salta l'arbre de treball amb un avís, però `git diff <commit>` i `ls-files -d`
    els donen per esborrats, sense avís. Els nous, `ls-files --others` els llista i `git add -A` hi plega.
    `lstat` separa els que no hi són dels que hi són però no es deixen llegir.
    """
    def filtra(*args):
        return [c for c in repo.git("ls-files", *args, "-z").split("\0") if c and not llegible(repo.worktree / c)]
    return filtra("-d"), filtra("--others", "--exclude-standard")


def sense(camins: list) -> list:
    """Pathspec de tot l'arbre menys aquests camins (literals)."""
    return (["--", "."] + [f":(exclude,literal){c}" for c in camins]) if camins else []


def _name_status(sortida: str) -> list:
    out, camps, i = [], sortida.split("\0"), 0
    while i < len(camps) and camps[i]:
        estat = camps[i]
        if estat[0] in "RC":
            out.append((estat[0], camps[i + 1]))
            out.append((estat[0], camps[i + 2]))
            i += 3
        else:
            out.append((estat[0], camps[i + 1]))
            i += 2
    return out


def fitxers_del_diff(repo: Repo, merge_base: str, amaga: list = ()) -> list:
    """(estat, camí) de tot el que canvia respecte del merge-base: commits, canvis sense commit i fitxers nous.

    Dels renomenats i esborrats també compta la ruta vella. Dels camins d'`amaga` (els no llegibles, dins del
    sandbox), l'arbre de treball no compta: només el que en diuen els commits i l'índex, que git sap sense llegir-los.
    """
    out = _name_status(repo.git("diff", "--name-status", "-M", "-z", merge_base))
    for cami in repo.git("ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if cami:
            out.append(("?", cami))
    if amaga:
        amagats = set(amaga)
        out = [(e, c) for e, c in out if c not in amagats]
        out += _name_status(repo.git("diff", "--cached", "--name-status", "--no-renames", "-z", merge_base, "--",
                                     *[f":(literal){c}" for c in amaga]))
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


def calcula_pla(repo: Repo, tolera: bool = False) -> Pla:
    """El pla del diff contra la base. Amb `tolera` (ship, dins del sandbox), l'arbre de treball dels fitxers no
    llegibles no compta: no surten com a esborrats, sinó a `no_llegibles`."""
    cfg = repo.config()
    ref = repo.ref_base()
    if not repo.git_ok("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
        raise Plega(f"no trobo la base «{ref}» (branca_base de nucli.json)")
    mb = repo.git("merge-base", ref, "HEAD")
    amaga = sum(no_llegibles(repo), []) if tolera else []
    fitxers, requerits = classifica(cfg, fitxers_del_diff(repo, mb, amaga))
    for f in fitxers:
        f.no_llegible = f.cami in amaga
    return Pla(ref, mb, fitxers, requerits, amaga)


# ---------- arbre i estat de git ----------

def arbre_de_treball(repo: Repo, tolera: bool = False) -> str:
    """L'arbre que tindria un commit de tot el directori de treball ara mateix (git add -A en un índex temporal).

    Un fitxer seguit que no es pot llegir, `add -A` el deixa com és a HEAD. Amb `tolera`, els nous no llegibles
    queden fora (sense, `add -A` hi plega).
    """
    d = repo.dir_nucli(crea=True)
    index = d / f"index-{os.getpid()}"
    env = dict(os.environ, GIT_INDEX_FILE=str(index))
    try:
        if repo.git_ok("rev-parse", "--verify", "--quiet", "HEAD"):
            git("read-tree", "HEAD", cwd=repo.worktree, env=env)
        git("add", "-A", *sense(no_llegibles(repo)[1] if tolera else []), cwd=repo.worktree, env=env)
        return git("write-tree", cwd=repo.worktree, env=env)
    finally:
        if index.exists():
            index.unlink()


def canvis_pendents(repo: Repo, tolera: bool = False) -> list:
    """El que fa que l'arbre de treball no sigui net.

    Dels fitxers no llegibles, git no en pot veure l'arbre de treball. Amb `tolera` (ship, dins del sandbox) no
    compten. Sense (finish, fora del sandbox), cadascun és una línia més: si no es pot llegir, l'arbre no és net.
    """
    seguits, nous = no_llegibles(repo)
    linies = [l for l in repo.git("status", "--porcelain", "--untracked-files=all", *sense(nous)).splitlines()
              if l.strip()]
    if not tolera:
        linies += [f"{c}: no el puc llegir (sense permís), i sense llegir-lo no puc dir que no hagi canviat"
                   for c in seguits + nous]
    return linies


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


def dins_i_fora(cfg: dict, automatics: list) -> tuple:
    """Els checks automàtics que corren dins del sandbox, i els `fora_sandbox`."""
    fora = [c for c in automatics if cfg["checks"][c].get("fora_sandbox")]
    return [c for c in automatics if c not in fora], fora


def estat_del_rebut(cfg: dict, pla: "Pla", rebut: dict, arbre: str) -> tuple:
    """(problemes, pendents): el que impedeix segellar i els `fora_sandbox` que encara no valen sobre HEAD.

    Els `fora_sandbox` no els pot passar cap agent: queden pendents al segell i els executa `nucli finish`,
    després que una persona hagi llegit el diff. `pendents` és {check: motiu}.
    """
    dins, fora = dins_i_fora(cfg, pla.automatics(cfg))
    pendents = {}
    for c in fora:
        motiu = problemes_checks(rebut, [c], arbre)
        if motiu:
            pendents[c] = motiu[0]
    return problemes_checks(rebut, dins, arbre), pendents


MISSATGE_FORA = "No els executa cap agent: s'executaran a «nucli finish», després que llegeixis el diff."


def segella(repo: Repo, cfg: dict, pla: "Pla", rebut: dict, tolera: bool = False) -> dict:
    """Segella el rebut si l'arbre és net i els checks de dins del sandbox són en verd sobre HEAD.

    Els `fora_sandbox` que falten queden a `fora_sandbox_pendents`. Amb `tolera` (ship seal), els fitxers no
    llegibles no compten per a l'arbre net i queden a `no_llegibles`. Plega si no pot segellar.
    """
    pendents = canvis_pendents(repo, tolera)
    if pendents:
        raise Plega("l'arbre de treball no és net: fes commit (o descarta) abans de segellar:\n  " + "\n  ".join(pendents[:20]))
    arbre = arbre_head(repo)
    problemes, fora = estat_del_rebut(cfg, pla, rebut, arbre)
    if problemes:
        raise Plega("no segello:\n  " + "\n  ".join(problemes))
    segell = {
        "head": repo.git("rev-parse", "HEAD"), "arbre": arbre, "hora": ara(), "requerits": pla.requerits,
        "manuals_pendents": pla.manuals(cfg), "fora_sandbox_pendents": list(fora),
        "no_llegibles": list(pla.no_llegibles), "nucli": VERSIO,
    }
    rebut["segell"] = segell
    segell["sha256"] = sha_rebut(rebut)
    desa_rebut(repo, rebut)
    return segell


# ---------- fitxers de la branca que formen part dels checks ----------

PATRONS_TEST = ["test_*.py", "*_test.py", "conftest.py", "*_test.go", "*.test.js", "*.test.ts", "*.spec.js",
                "*.spec.ts", "tests/", "test/", "__tests__/"]
SEPARADORS = {"&&", "||", ";", "|", "&", "(", ")"}


def referencies(ordre_shell: str, arrel: Path) -> list:
    """Fitxers i carpetes del repo que fa servir una ordre de check: [(camí relatiu, és carpeta)].

    Segueix els `cd` («cd scraper && … -s tests» → scraper/tests). No mira dins dels scripts.
    """
    try:
        lex = shlex.shlex(ordre_shell, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = ordre_shell.split()
    base, out, i = "", [], 0
    while i < len(tokens):
        t = tokens[i]
        if t == "cd" and i + 1 < len(tokens):
            base = os.path.normpath(os.path.join(base, tokens[i + 1]))
            i += 2
            continue
        i += 1
        if not t or t in SEPARADORS or t.startswith(("-", "$", "/", "~")) or "=" in t:
            continue
        rel = os.path.normpath(os.path.join(base, t))
        if rel == "." or rel.startswith(".."):
            continue
        cami = arrel / rel
        if cami.exists():
            out.append((Path(rel).as_posix(), cami.is_dir()))
    return out


def fitxers_dels_checks(repo: Repo, cfg: dict, automatics: list, camins: list) -> dict:
    """{camí: motiu} dels fitxers del diff que executaran els checks: els scripts que criden, el que hi ha a les
    carpetes que fan servir i els tests."""
    refs = [(rel, es_dir, c) for c in automatics for rel, es_dir in referencies(cfg["checks"][c]["ordre"], repo.worktree)]
    marcats = {}
    for cami in camins:
        motius = []
        for rel, es_dir, c in refs:
            if cami == rel:
                motius.append(f"l'executa el check {c}")
            elif es_dir and cami.startswith(rel + "/"):
                motius.append(f"és a {rel}/, que fa servir el check {c}")
        if algun(PATRONS_TEST, cami):
            motius.append("test")
        if motius:
            marcats[cami] = "; ".join(dict.fromkeys(motius))
    return marcats


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


def executa_check(repo: Repo, cfg: dict, nom: str, via: str, tolera: bool = False) -> dict:
    ordre_shell = cfg["checks"][nom]["ordre"]
    arbre = arbre_de_treball(repo, tolera)
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
    despres = arbre_de_treball(repo, tolera)
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
    pla = calcula_pla(repo, tolera=True)
    print(f"nucli ship plan · branca {repo.branca()} · base {pla.ref_base} (merge-base {pla.merge_base[:8]})")
    print(f"Regles: {repo.cami_config}")
    fora = pla.fora_del_pla()
    if pla.fitxers or fora:
        ample = min(max(len(c) for c in [f.cami for f in pla.fitxers] + fora), 48)
    for f in pla.fitxers:
        if f.regles:
            on = "regla " + ", ".join(str(n) for n in f.regles)
        else:
            on = "sense regla → per defecte"
        checks = ", ".join(f.checks) if f.checks else "(cap)"
        nota = f"  · {NO_LLEGIBLE}: només compta el canvi dels commits" if f.no_llegible else ""
        print(f"  {f.estat}  {f.cami:<{ample}}  {on} → {checks}{nota}")
    for c in fora:
        print(f"  ·  {c:<{ample}}  {NO_LLEGIBLE} → ni esborrat ni canvi: fora del pla")
    if not pla.fitxers:
        print("Cap canvi respecte de la base: cap check requerit.")
        return 0
    if not pla.requerits:
        print("Checks requerits: cap.")
        return 0
    print("Checks requerits:")
    for c in pla.requerits:
        if c in pla.automatics(cfg):
            ch = cfg["checks"][c]
            fora = "  (fora del sandbox: no l'executa cap agent, el passa nucli finish)" if ch.get("fora_sandbox") else ""
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
    execucio = executa_check(repo, cfg, nom, via="ship", tolera=True)
    rebut["execucions"].append(execucio)
    rebut["segell"] = None  # qualsevol execució nova invalida el segell anterior
    desa_rebut(repo, rebut)
    return execucio["codi"]


def ordre_seal(repo: Repo) -> int:
    cfg = repo.config()
    branca = branca_amb_rebut(repo)
    pla = calcula_pla(repo, tolera=True)
    rebut = llegeix_rebut(repo, branca)
    segell = segella(repo, cfg, pla, rebut, tolera=True)
    print(f"nucli ship seal · segellat · HEAD {segell['head'][:8]} · requerits: {', '.join(pla.requerits) or 'cap'}")
    if segell["no_llegibles"]:
        print(f"No llegibles (sandbox), no compten per a l'arbre net: {', '.join(segell['no_llegibles'])}. "
              "Fora del sandbox, nucli finish ho comprova sense excepcions.")
    if segell["fora_sandbox_pendents"]:
        print(f"Fora del sandbox, pendents: {', '.join(segell['fora_sandbox_pendents'])}. {MISSATGE_FORA}")
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
