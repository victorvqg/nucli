"""Lectura i validació de nucli.json. Tot el que canvia de projecte a projecte viu aquí (principi a)."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Optional

from .comu import Plega

VERSIO_CONFIG = 1
CHECK_REVISIO_CONFIG = "revisio-config"
TEXT_REVISIO_CONFIG = "Canvi de configuració o de seguretat: revisió humana"
MAX_MOTIU = 200  # v0.1.6: el motiu d'una regla de «risc» surt al PR
ROLS = ("estat", "decisions", "trampes", "convencions", "arquitectura")
TIPUS_COMMIT = ["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert", "wip"]
FONTS_TASQUES = ("fitxer", "github-issues")
BRANCA_ISSUES = "issue/"          # branques d'issue per defecte: issue/N-descripcio (v0.1.4)
WORKTREE_ISSUE = "worktree-issue-"  # la branca del worktree de `nucli agent N` (id issue-N)

PER_DEFECTE = {
    "versio": VERSIO_CONFIG,
    "idioma": "ca",
    "branca_base": "main",
    "docs": {},
    "tasques": None,
    "checks": {},
    "regles": [],
    "per_defecte": [],
    "commits": {"tipus": TIPUS_COMMIT},
    "agent": {"torns": 60, "pressupost_usd": 7, "prohibides": []},
}


def llegeix(cami: Path) -> dict:
    try:
        text = Path(cami).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Plega(f"no trobo {cami}")
    try:
        dades = json.loads(text)
    except json.JSONDecodeError as e:
        raise Plega(f"{cami}: JSON no vàlid (línia {e.lineno}, columna {e.colno}): {e.msg}")
    errors = valida(dades)
    if errors:
        raise Plega(f"{cami} té errors:\n" + "\n".join(f"  - {e}" for e in errors))
    return completa(dades)


def completa(dades: dict) -> dict:
    cfg = copy.deepcopy(PER_DEFECTE)
    for clau, valor in dades.items():
        if clau == "agent":
            cfg["agent"].update(valor)
        else:
            cfg[clau] = valor
    return cfg


def _es_llista_de_textos(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


def valida(d) -> list:
    """Torna la llista d'errors (en català). Buida si el fitxer és correcte."""
    if not isinstance(d, dict):
        return ["l'arrel ha de ser un objecte JSON"]
    e = []
    if d.get("versio") != VERSIO_CONFIG:
        e.append(f"«versio» ha de ser {VERSIO_CONFIG}")
    for clau in ("idioma", "branca_base"):
        if clau in d and not (isinstance(d[clau], str) and d[clau]):
            e.append(f"«{clau}» ha de ser un text")

    checks = d.get("checks", {})
    if not isinstance(checks, dict):
        e.append("«checks» ha de ser un objecte")
        checks = {}
    for nom, c in checks.items():
        if nom == CHECK_REVISIO_CONFIG:
            e.append(f"«{CHECK_REVISIO_CONFIG}» és un check reservat del nucli")
        if not isinstance(c, dict) or (("ordre" in c) == ("manual" in c)):
            e.append(f"el check «{nom}» ha de tenir «ordre» (automàtic) o «manual» (text), i només un dels dos")
            continue
        if "ordre" in c and not (isinstance(c["ordre"], str) and c["ordre"].strip()):
            e.append(f"l'«ordre» del check «{nom}» ha de ser un text")
        if "manual" in c and not (isinstance(c["manual"], str) and c["manual"].strip()):
            e.append(f"el «manual» del check «{nom}» ha de ser un text")
        if "fora_sandbox" in c and not isinstance(c["fora_sandbox"], bool):
            e.append(f"«fora_sandbox» del check «{nom}» ha de ser true o false")
        if "manual" in c and c.get("fora_sandbox"):
            e.append(f"el check manual «{nom}» no pot ser «fora_sandbox»")

    def comprova_noms(noms, on):
        if not _es_llista_de_textos(noms) and noms != []:
            e.append(f"{on} ha de ser una llista de noms de check")
            return
        for n in noms:
            if n not in checks:
                e.append(f"{on} fa servir el check «{n}», que no és a «checks»")

    regles = d.get("regles", [])
    if not isinstance(regles, list):
        e.append("«regles» ha de ser una llista")
        regles = []
    for i, r in enumerate(regles, 1):
        if not isinstance(r, dict) or not _es_llista_de_textos(r.get("patrons")):
            e.append(f"la regla {i} ha de tenir «patrons» (llista de textos)")
            continue
        if "checks" not in r:
            e.append(f"la regla {i} ha de tenir «checks» (pot ser [])")
        else:
            comprova_noms(r["checks"], f"la regla {i}")
    comprova_noms(d.get("per_defecte", []), "«per_defecte»")

    risc = d.get("risc", [])  # v0.1.6: els patrons que fan una branca «difícil de desfer», amb el motiu
    if not isinstance(risc, list):
        e.append("«risc» ha de ser una llista de regles amb «patrons» i «motiu»")
        risc = []
    for i, r in enumerate(risc, 1):
        if not isinstance(r, dict) or not (_es_llista_de_textos(r.get("patrons")) and r["patrons"]):
            e.append(f"la regla de risc {i} ha de tenir «patrons» (llista de textos)")
            continue
        motiu = r.get("motiu")
        if not (isinstance(motiu, str) and motiu.strip() and "\n" not in motiu and "\r" not in motiu
                and len(motiu) <= MAX_MOTIU):
            e.append(f"la regla de risc {i} ha de tenir «motiu»: un text d'una línia, de {MAX_MOTIU} caràcters "
                     "com a màxim")

    docs = d.get("docs", {})
    if not isinstance(docs, dict):
        e.append("«docs» ha de ser un objecte")
        docs = {}
    for rol in ROLS:
        v = docs.get(rol)
        if v is None:
            continue
        if isinstance(v, dict):
            if not (isinstance(v.get("cami"), str) and v["cami"]):
                e.append(f"docs.{rol} ha de tenir «cami»")
            if rol == "decisions" and v.get("format", "adr") not in ("adr", "data"):
                e.append("docs.decisions.format ha de ser «adr» o «data»")
        elif not (isinstance(v, str) and v):
            e.append(f"docs.{rol} ha de ser un camí o un objecte amb «cami»")
    for i, a in enumerate(docs.get("adoptats", []) or [], 1):
        if not (isinstance(a, dict) and isinstance(a.get("cami"), str) and isinstance(a.get("prefix"), str) and a["prefix"].isalpha()):
            e.append(f"docs.adoptats[{i}] ha de tenir «cami» i «prefix» (lletres)")

    t = d.get("tasques")
    if t is not None and not (isinstance(t, dict) and isinstance(t.get("fitxer"), str) and isinstance(t.get("prefix"), str)):
        e.append("«tasques» ha de tenir «fitxer» i «prefix»")
    if isinstance(t, dict):
        font = t.get("font", "fitxer")
        if font not in FONTS_TASQUES:
            e.append(f"«tasques.font» ha de ser {' o '.join(f'«{f}»' for f in FONTS_TASQUES)}")
        if font == "github-issues" and "branca" not in t:
            e.append("amb «tasques.font» «github-issues», cal «tasques.branca» (p. ex. «issue/»)")
        if "branca" in t and not (isinstance(t["branca"], str) and len(t["branca"]) > 1 and t["branca"].endswith("/")):
            e.append("«tasques.branca» ha de ser un text acabat en «/» (p. ex. «issue/»)")

    commits = d.get("commits", {})
    if not (isinstance(commits, dict) and _es_llista_de_textos(commits.get("tipus", TIPUS_COMMIT))):
        e.append("«commits.tipus» ha de ser una llista de textos")

    agent = d.get("agent", {})
    if not isinstance(agent, dict):
        e.append("«agent» ha de ser un objecte")
    else:
        if "torns" in agent and not (isinstance(agent["torns"], int) and agent["torns"] > 0):
            e.append("«agent.torns» ha de ser un enter positiu")
        if "pressupost_usd" in agent and not (isinstance(agent["pressupost_usd"], (int, float)) and agent["pressupost_usd"] > 0):
            e.append("«agent.pressupost_usd» ha de ser un nombre positiu")
        if "prohibides" in agent and not (_es_llista_de_textos(agent["prohibides"]) or agent["prohibides"] == []):
            e.append("«agent.prohibides» ha de ser una llista de regles")
    return e


def cami_doc(valor) -> str:
    """El fitxer d'un rol de docs, sense la «#Secció» si en porta."""
    if isinstance(valor, dict):
        valor = valor["cami"]
    return valor.split("#", 1)[0]


def branca_issues(cfg: dict) -> str:
    """El prefix de les branques d'issue: el de «tasques.branca», i si no n'hi ha, «issue/»."""
    return (cfg.get("tasques") or {}).get("branca") or BRANCA_ISSUES


def issue_de_branca(branca: str, cfg: dict) -> Optional[int]:
    """El número de l'issue d'una branca `issue/N-…` (o `issue/N`) o `worktree-issue-N` (la de `nucli agent N`)."""
    for patro in (rf"^{re.escape(branca_issues(cfg))}(\d+)(?:-|$)", rf"^{re.escape(WORKTREE_ISSUE)}(\d+)(?:-|$)"):
        m = re.match(patro, branca or "")
        if m:
            return int(m.group(1))
    return None


def prefixos_tasques(cfg: dict) -> list:
    """Prefixos d'ids de tasques: el de «tasques» i els dels docs adoptats."""
    prefixos = []
    if cfg.get("tasques"):
        prefixos.append(cfg["tasques"]["prefix"])
    for a in cfg.get("docs", {}).get("adoptats", []) or []:
        if a["prefix"] not in prefixos:
            prefixos.append(a["prefix"])
    return prefixos
