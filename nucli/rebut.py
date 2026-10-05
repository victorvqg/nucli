"""`nucli rebut markdown [--origen ci] [--seccions]`: el bloc «Rebut» d'un rebut segellat, en markdown (v0.1.4).

És el mateix bloc que `nucli finish` posa al PR, perquè la CI en pugui fer un d'idèntic: `nucli ship plan --json`
→ `nucli ship run` de cada check automàtic → `nucli ship seal` → `nucli rebut markdown --origen ci`. Només llegeix
el rebut: no executa res. Un rebut sense segell, retocat (sha256) o d'un HEAD que ja no és l'actual no s'escriu.

v0.1.6 (#2): amb `--seccions`, abans del bloc hi van «Resum» (l'arbre de fitxers de la branca) i «Risc de fusió»
(veredicte, senyals i abast). Les fa el nucli sol, amb git, el rebut i nucli.json, i tampoc no executen res.
`nucli finish` les posa sempre. Sense `--seccions`, el bloc és el de la v0.1.4.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from . import VERSIO
from .comu import Plega, Repo, troba_repo
from .config import CHECK_REVISIO_CONFIG
from .patrons import algun, coincideix
from .ship import PATRONS_CONFIG, branca_amb_rebut, llegeix_rebut, sha_rebut, ultima

ORIGENS = {"finish": "per `nucli finish`", "ci": "per la CI"}


def markdown(rebut: dict, origen: str = "finish") -> str:
    """El bloc «Rebut del nucli»: per a cada check automàtic requerit pel segell, l'execució que el fa valer.

    Els requerits que no s'han executat (manuals sense confirmar i `fora_sandbox` pendents) surten a part, perquè
    el rebut no digui més del que s'ha fet.
    """
    segell = rebut["segell"]
    head = segell["head"]
    manuals = list(segell.get("manuals_pendents") or [])
    fora = list(segell.get("fora_sandbox_pendents") or [])
    automatics = [c for c in segell.get("requerits") or [] if c not in manuals and c not in fora]
    execucions = [e for e in (ultima(rebut, c) for c in automatics) if e]
    linies = ["## Rebut del nucli", "", f"Checks executats {ORIGENS[origen]} contra HEAD `{head[:12]}`:", ""]
    if execucions:
        linies += ["| check | codi | durada | hora |", "|---|---|---|---|"]
        linies += [f"| {e['check']} | {e['codi']} | {e['durada_s']} s | {e['hora']} |" for e in execucions]
    else:
        linies.append("Cap check automàtic requerit.")
    confirmacions = (rebut.get("finish") or {}).get("confirmacions") or []
    if confirmacions:
        linies += ["", "Confirmacions manuals:"]
        linies += [f"- {c['check']}: {c['resposta']} ({c['hora']})" for c in confirmacions]
    confirmats = {c["check"] for c in confirmacions if c.get("resposta") == "sí"}
    pendents = [m for m in manuals if m not in confirmats]
    if pendents:
        linies += ["", f"Checks manuals pendents (revisió humana): {', '.join(pendents)}"]
    if fora:
        linies += ["", f"Checks fora del sandbox pendents (sense executar): {', '.join(fora)}"]
    linies += ["", f"HEAD `{head}` · nucli {VERSIO}"]
    return "\n".join(linies) + "\n"


# ---------- v0.1.6: les seccions «Resum» i «Risc de fusió» ----------

MAX_ARBRE = 60   # fitxers a l'arbre del Resum: la resta es compten, perquè el cos del PR no passi del límit de GitHub
MAX_LLISTA = 10  # camins a cada llista del Risc de fusió
ESTATS = "AMDR"
_DIRECCIO = set("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_ESPECIALS = re.compile(r"([\\`*_{}\[\]()<>#+!|~@])")


@dataclass
class Canvi:
    estat: str               # A, M, D o R
    cami: str                # el camí del fitxer (el nou, si és R; el d'abans, si és D)
    vell: Optional[str]      # el camí d'abans, si és R
    mes: Optional[int]       # línies afegides; None, si és binari
    menys: Optional[int]

    def camins(self) -> list:
        return [self.cami] + ([self.vell] if self.vell else [])


def canvis_de(name_status: str, numstat: str) -> list:
    """Els canvis a partir de `git diff -z --name-status -M` i `git diff -z --numstat -M`."""
    linies, parts, i = {}, numstat.split("\0"), 0
    while i < len(parts) and parts[i]:
        mes, menys, cami = parts[i].split("\t", 2)
        if cami == "":  # renomenat: «mes\tmenys\t», i després la ruta vella i la nova
            cami, i = parts[i + 2], i + 3
        else:
            i += 1
        linies[cami] = (None, None) if mes == "-" else (int(mes), int(menys))
    out, parts, i = [], name_status.split("\0"), 0
    while i < len(parts) and parts[i]:
        estat = parts[i][0]
        if estat in "RC":
            vell, cami, i = parts[i + 1], parts[i + 2], i + 3
        else:
            vell, cami, i = None, parts[i + 1], i + 2
        if estat == "C":  # una còpia és un fitxer nou
            estat, vell = "A", None
        elif estat not in ESTATS:  # T (tipus), U…
            estat = "M"
        mes, menys = linies.get(cami, (0, 0))
        out.append(Canvi(estat, cami, vell, mes, menys))
    return out


def net(text: str) -> str:
    """Un nom que ve de la branca, amb els caràcters de control i de direcció del text escrits escapats."""
    out = []
    for ch in text:
        if ch in "\n\t\r":
            out.append({"\n": "\\n", "\t": "\\t", "\r": "\\r"}[ch])
        elif unicodedata.category(ch) == "Cc":
            out.append(f"\\x{ord(ch):02x}")
        elif ch in _DIRECCIO:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def codi(text: str) -> str:
    """Codi en línia: res del que hi hagi a dins (enllaços, mencions, HTML) no es fa servir com a markdown."""
    t = net(text)
    tanca = "`" * (max((len(m) for m in re.findall(r"`+", t)), default=0) + 1)
    if t.startswith("`") or t.endswith("`"):
        t = f" {t} "
    return f"{tanca}{t}{tanca}"


def text_pla(text: str) -> str:
    """Un text en una línia, amb els caràcters de markdown escapats: es veu igual, però no fa cap format."""
    return _ESPECIALS.sub(r"\\\1", net(" ".join(text.split())))


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _i(elements: list) -> str:
    return elements[0] if len(elements) == 1 else ", ".join(elements[:-1]) + " i " + elements[-1]


def _llista(elements: list) -> str:
    text = ", ".join(elements[:MAX_LLISTA])
    return text + (f" i {len(elements) - MAX_LLISTA} més" if len(elements) > MAX_LLISTA else "")


def _xifres(canvis: list) -> tuple:
    mes = sum(c.mes or 0 for c in canvis)
    menys = sum(c.menys or 0 for c in canvis)
    binaris = sum(1 for c in canvis if c.mes is None)
    return mes, menys, binaris


def _ordena(camins) -> list:
    return sorted(camins, key=lambda c: (c.casefold(), c))


def _arbre(canvis: list) -> list:
    """Les línies de l'arbre: a cada nivell, primer les carpetes i després els fitxers, per ordre alfabètic."""
    node = {"carpetes": {}, "fitxers": []}
    for c in canvis:
        *carpetes, nom = c.cami.split("/")
        n = node
        for carpeta in carpetes:
            n = n["carpetes"].setdefault(carpeta, {"carpetes": {}, "fitxers": []})
        n["fitxers"].append((nom, c))
    files = []

    def recorre(n, sagnat):
        for nom in _ordena(n["carpetes"]):
            files.append((f"{sagnat}{net(nom)}/", None))
            recorre(n["carpetes"][nom], sagnat + "  ")
        for nom, c in sorted(n["fitxers"], key=lambda f: (f[0].casefold(), f[0])):
            files.append((f"{sagnat}{net(nom)}", c))

    recorre(node, "")
    ample = max((len(f) for f, c in files if c is not None), default=0)
    linies = []
    for f, c in files:
        if c is None:
            linies.append(f)
            continue
        xifres = "binari" if c.mes is None else f"+{c.mes} -{c.menys}"
        era = f"  (era {net(c.vell)})" if c.vell else ""
        linies.append(f"{f.ljust(ample)}  {c.estat}  {xifres}{era}")
    return linies


def resum(canvis: list) -> str:
    """«Resum»: l'arbre de fitxers de la branca (A/M/D/R i +/-, per carpetes), en un bloc de codi."""
    if not canvis:
        return "## Resum\n\nCap fitxer canviat respecte de la base.\n"
    mes, menys, binaris = _xifres(canvis)
    xifres = [_plural(len(canvis), "fitxer", "fitxers"), f"+{mes} -{menys}"]
    xifres += [f"{e} {n}" for e in ESTATS for n in [sum(1 for c in canvis if c.estat == e)] if n]
    if binaris:
        xifres.append(_plural(binaris, "binari", "binaris"))
    mostrats = sorted(canvis, key=lambda c: (c.cami.casefold(), c.cami))[:MAX_ARBRE]
    arbre = _arbre(mostrats)
    tanca = "`" * max(3, max((len(m) for l in arbre for m in re.findall(r"`+", l)), default=0) + 1)
    linies = ["## Resum", "", " · ".join(xifres), "", f"{tanca}text", *arbre, tanca]
    falten = len(canvis) - len(mostrats)
    if falten:
        linies += ["", f"… i {_plural(falten, 'fitxer més, que no surt', 'fitxers més, que no surten')} a l'arbre."]
    return "\n".join(linies) + "\n"


def risc_de_fusio(canvis: list, cfg: dict, requerits: list) -> str:
    """«Risc de fusió»: el veredicte amb la clau `risc` de nucli.json, els senyals i l'abast."""
    regles = cfg.get("risc") or []
    linies = ["## Risc de fusió", ""]
    dificils = []
    for r in regles:
        camins = _ordena({c for canvi in canvis for c in canvi.camins() if algun(r["patrons"], c)})
        if camins:
            dificils.append(f"- {text_pla(r['motiu'])}: {_llista([codi(c) for c in camins])}")
    if dificils:
        linies += ["**Difícil de desfer.**", *dificils]
    elif regles:
        linies.append("**Es pot desfer** amb un revert del PR: cap patró de la clau `risc` de `nucli.json` hi coincideix.")
    else:
        linies.append("**Es pot desfer** amb un revert del PR: `nucli.json` no té cap regla `risc`.")

    config_ = _ordena({c for canvi in canvis for c in canvi.camins() if any(coincideix(p, c) for p in PATRONS_CONFIG)})
    esborrats = _ordena(c.cami for c in canvis if c.estat == "D")
    renomenats = sorted((c for c in canvis if c.estat == "R"), key=lambda c: (c.cami.casefold(), c.cami))
    mes, menys, binaris = _xifres(canvis)
    mida = f"{_plural(len(canvis), 'fitxer', 'fitxers')}, +{mes} -{menys}"
    if binaris:
        mida += f", {_plural(binaris, 'binari', 'binaris')}"
    linies += ["", "Senyals:",
               f"- Configuració o seguretat (`{CHECK_REVISIO_CONFIG}`): "
               + (_llista([codi(c) for c in config_]) if config_ else "cap"),
               f"- Esborrats ({len(esborrats)}): {_llista([codi(c) for c in esborrats])}" if esborrats
               else "- Esborrats: cap",
               f"- Renomenats ({len(renomenats)}): {_llista([f'{codi(c.vell)} → {codi(c.cami)}' for c in renomenats])}"
               if renomenats else "- Renomenats: cap",
               f"- Mida: {mida}"]

    tots = [c for canvi in canvis for c in canvi.camins()]
    carpetes = [codi(f"{d}/") for d in _ordena({c.split("/", 1)[0] for c in tots if "/" in c})]
    if any("/" not in c for c in tots):
        carpetes.append("l'arrel")
    linies += ["", "Abast:",
               f"- Carpetes de primer nivell: {_i(carpetes) if carpetes else 'cap'}",
               f"- Checks del segell: {', '.join(requerits) if requerits else 'cap'}"]
    return "\n".join(linies) + "\n"


def canvis_de_la_branca(repo: Repo, head: str) -> list:
    """El diff dels commits de la branca contra el merge-base amb la base (el que portarà el PR)."""
    ref = repo.ref_base()
    try:
        mb = repo.git("merge-base", ref, head)
    except Plega:
        raise Plega(f"no trobo el merge-base de {ref} i HEAD: les seccions necessiten la història de la base "
                    "(a la CI, un fetch de la branca base)")
    # --no-ext-diff i --no-textconv: git no executa cap programa de la configuració per fer el diff
    opcions = ["--no-ext-diff", "--no-textconv", "-M", "-z"]
    return canvis_de(repo.git("diff", "--name-status", *opcions, mb, head),
                     repo.git("diff", "--numstat", *opcions, mb, head))


def seccions(repo: Repo, cfg: dict, rebut: dict) -> str:
    """«Resum» i «Risc de fusió» d'un rebut segellat. Només llegeix git, el rebut i nucli.json."""
    segell = rebut["segell"]
    canvis = canvis_de_la_branca(repo, segell["head"])
    return resum(canvis) + "\n" + risc_de_fusio(canvis, cfg, list(segell.get("requerits") or []))


def ordre(args) -> int:
    repo = troba_repo()
    branca = branca_amb_rebut(repo)
    rebut = llegeix_rebut(repo, branca, exigeix=True)
    segell = rebut.get("segell")
    if not segell:
        raise Plega("el rebut no està segellat: passa els checks i «nucli ship seal»")
    if segell.get("sha256") != sha_rebut(rebut):
        raise Plega("el sha256 del segell no quadra: algú ha tocat el rebut. Torna a passar els checks i «nucli ship seal»")
    head = repo.git("rev-parse", "HEAD")
    if head != segell.get("head"):
        raise Plega(f"HEAD ({head[:8]}) no és el del segell ({str(segell.get('head'))[:8]}): el rebut és d'un altre "
                    "commit. Torna a passar els checks i «nucli ship seal»")
    if args.origen == "finish" and not rebut.get("finish"):
        raise Plega("aquest rebut no ha passat per «nucli finish»: si els checks els ha executat la CI, "
                    "«nucli rebut markdown --origen ci»")
    text = markdown(rebut, args.origen)
    if args.seccions:
        text = seccions(repo, repo.config(), rebut) + "\n" + text
    print(text, end="")
    return 0
