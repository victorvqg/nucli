"""`nucli init [--dry-run] [--adopta rol=camí]…`: prepara un repo sense tocar res del que ja hi ha.

Cada pas afegeix «accions» a una llista: primer es planifica tot, després s'imprimeix i, si no és --dry-run,
s'executen les que escriuen. Idempotent: una segona passada només troba «ja hi és».
"""
from __future__ import annotations

import difflib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import config, docs
from .comu import FITXER_CONFIG, Plega, Repo, prepara_dir_nucli
from .config import ROLS, cami_doc


@dataclass
class Accio:
    verb: str                                   # crea · adopta · proposa · afegeix · activa · ja hi és · avís
    objectiu: str
    detall: str = ""
    fes: Optional[Callable[[], None]] = None    # None: l'acció no escriu res
    extra: str = ""                             # text sota la línia (un diff, una llista)


class Context:
    def __init__(self, repo: Repo, dry_run: bool):
        self.repo = repo
        self.arrel = repo.arrel
        self.dry_run = dry_run
        self.accions = []
        self.cfg = None

    def afegeix(self, *args, **kw) -> Accio:
        a = Accio(*args, **kw)
        self.accions.append(a)
        return a


DIR_PROPOSTA = "proposta"


def escriu_fitxer(cami: Path, text: str) -> Callable[[], None]:
    def _fes():
        cami.parent.mkdir(parents=True, exist_ok=True)
        cami.write_text(text, encoding="utf-8")
    return _fes


def _escriu_proposta(arrel: Path, nom: str, text: str) -> Callable[[], None]:
    def _fes():
        prepara_dir_nucli(arrel / ".nucli")
        dest = arrel / ".nucli" / DIR_PROPOSTA / nom
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return _fes


def diff(original: str, nou: str, de: str, a: str) -> str:
    linies = difflib.unified_diff(original.splitlines(), nou.splitlines(), fromfile=de, tofile=a, lineterm="", n=2)
    return "\n".join(linies)


# ---------- pas 1-4: docs, CLAUDE.md/AGENTS.md i nucli.json ----------

def llegeix_forcats(valors: list) -> dict:
    forcats = {}
    for v in valors:
        rol, sep, cami = v.partition("=")
        if not sep or rol not in ROLS or not cami:
            raise Plega(f"--adopta {v}: cal «rol=camí», amb rol entre {', '.join(ROLS)}")
        forcats[rol] = cami
    return forcats


def pas_docs(ctx: Context, forcats: dict) -> None:
    arrel = ctx.arrel
    for rol, valor in forcats.items():
        if not docs.te_seccio(arrel, valor):
            raise Plega(f"--adopta {rol}={valor}: no trobo aquest fitxer o aquesta secció")
    det = docs.detecta(arrel, forcats)
    cami_cfg = arrel / FITXER_CONFIG

    if cami_cfg.is_file():
        ctx.cfg = config.llegeix(cami_cfg)
        ctx.afegeix("ja hi és", FITXER_CONFIG, "no el toco; els rols dels docs surten d'aquí")
        if forcats:
            ctx.afegeix("avís", "--adopta", "nucli.json ja existeix i no el toco: canvia-hi els rols a mà")
        rols = {rol: ctx.cfg["docs"][rol] for rol in ROLS if ctx.cfg["docs"].get(rol)}
        rols = {rol: (v["cami"] if isinstance(v, dict) else v) for rol, v in rols.items()}
        nou = False
    else:
        rols = dict(det.rols)
        for rol in ROLS:
            rols.setdefault(rol, docs.CAMI_NOU[rol])
        ctx.cfg = config.completa(docs.config_nova(arrel, det, rols))
        nou = True

    for rol in ROLS:
        valor = rols.get(rol)
        if not valor:
            continue
        fitxer = cami_doc(valor)
        if "#" in valor:
            if docs.te_seccio(arrel, valor):
                ctx.afegeix("adopta" if nou else "ja hi és", f"{rol} → {valor}", "secció existent, no es toca")
            else:
                ctx.afegeix("avís", f"{rol} → {valor}", "aquesta secció no existeix: revisa nucli.json")
        elif (arrel / fitxer).is_file():
            extra = f" (format {det.format_decisions})" if rol == "decisions" and nou else ""
            ctx.afegeix("adopta" if nou else "ja hi és", f"{rol} → {fitxer}{extra}")
        else:
            punter = det.punters.get(rol)
            detall = f"apunta a {docs.descriu(punter)}, sense moure-hi res" if punter else "des de plantilla"
            ctx.afegeix("crea", fitxer, detall, fes=escriu_fitxer(arrel / fitxer, docs.plantilla_doc(rol, punter)))

    if nou:
        if det.adoptats:
            ctx.afegeix("adopta", "ids", " · ".join(f"{a['prefix']} → {a['cami']}" for a in det.adoptats))
        cfg_text = json.dumps(docs.config_nova(arrel, det, rols), indent=2, ensure_ascii=False) + "\n"
        checks = ctx.cfg["checks"]
        if checks:
            llista = "\n".join(
                f"{nom:<8} {c['ordre']}{'  (fora_sandbox)' if c.get('fora_sandbox') else ''}   ← REVISA"
                for nom, c in checks.items()
            )
        else:
            llista = "no he endevinat cap check: omple «checks» i «per_defecte» abans de fer servir la porta"
        ctx.afegeix("crea", FITXER_CONFIG, "amb el que he detectat; revisa'l abans del commit",
                    fes=escriu_fitxer(cami_cfg, cfg_text), extra=llista)

    pas_instruccions(ctx)


def pas_instruccions(ctx: Context) -> None:
    arrel, cfg = ctx.arrel, ctx.cfg
    claude, agents = arrel / "CLAUDE.md", arrel / "AGENTS.md"
    if not claude.exists() and not agents.exists():
        ctx.afegeix("crea", "AGENTS.md", "docs, cicle i «mai», per a tots els agents",
                    fes=escriu_fitxer(agents, docs.agents_nou(cfg)))
        ctx.afegeix("crea", "CLAUDE.md", "@AGENTS.md + el que és només de Claude", fes=escriu_fitxer(claude, docs.claude_nou()))
        return
    for cami, per_claude in ((claude, True), (agents, False)):
        if not cami.exists():
            continue
        if docs.te_bloc(cami):
            ctx.afegeix("ja hi és", cami.name, f"ja té el bloc «{docs.MARCA_BLOC[3:]}»")
            continue
        original = cami.read_text(encoding="utf-8")
        bloc = docs.bloc_nucli(cfg, per_claude)
        proposta = docs.amb_bloc(original, bloc)
        dest = arrel / ".nucli" / DIR_PROPOSTA / cami.name
        rel = dest.relative_to(arrel).as_posix()
        if dest.is_file() and dest.read_text(encoding="utf-8") == proposta:
            ctx.afegeix("ja hi és", rel, f"proposta per a {cami.name}")
            continue
        n = len(bloc.splitlines())
        ctx.afegeix("proposa", rel, f"el teu {cami.name} + un bloc «Nucli» de {n} línies al final; {cami.name} no es toca",
                    fes=_escriu_proposta(arrel, cami.name, proposta),
                    extra=diff(original, proposta, cami.name, rel))
    if agents.exists() and not claude.exists():
        ctx.afegeix("crea", "CLAUDE.md", "@AGENTS.md + el que és només de Claude", fes=escriu_fitxer(claude, docs.claude_nou()))
    if claude.exists() and not agents.exists():
        ctx.afegeix("avís", "AGENTS.md", "no existeix i no el creo: CLAUDE.md ja porta les instruccions. "
                    "Si fas servir Kimi o Codex, crea'l i deixa «@AGENTS.md» a CLAUDE.md")


# Passos que s'afegeixen a les fases següents (gitignore, settings, worktrees, hooks de git).
PASSOS = []


def imprimeix(ctx: Context) -> None:
    print(f"nucli init · {ctx.arrel}" + ("  (--dry-run: no s'escriu res)" if ctx.dry_run else ""))
    for a in ctx.accions:
        linia = f"  {a.verb:<9} {a.objectiu}"
        if a.detall:
            linia += f" · {a.detall}"
        print(linia)
        if a.extra:
            for l in a.extra.splitlines():
                print(f"              {l}")
    canvis = [a for a in ctx.accions if a.fes]
    propostes = [a for a in ctx.accions if a.verb == "proposa"]
    avisos = [a for a in ctx.accions if a.verb == "avís"]
    if not canvis:
        print("Res a fer: tot ja hi és.")
    else:
        temps = "faria" if ctx.dry_run else "he fet"
        print(f"Resum: {temps} {len(canvis)} canvi(s), dels quals {len(propostes)} proposta(es) a .nucli/proposta/. "
              "Cap fitxer existent no s'ha modificat.")
    if avisos:
        print(f"Avisos: {len(avisos)}. Llegeix-los a dalt.")
    if canvis and not ctx.dry_run:
        print("No he fet cap commit: revisa-ho i fes-lo tu.")


def ordre(args) -> int:
    repo = Repo(os.getcwd())
    if repo.es_worktree:
        raise Plega(f"executa «nucli init» al checkout principal ({repo.arrel}), no en un worktree")
    ctx = Context(repo, args.dry_run)
    pas_docs(ctx, llegeix_forcats(args.adopta))
    for pas in PASSOS:
        pas(ctx)
    imprimeix(ctx)
    if not ctx.dry_run:
        for a in ctx.accions:
            if a.fes:
                a.fes()
    return 0
