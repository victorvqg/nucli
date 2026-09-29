"""Permisos de Claude Code: insercions mínimes a settings.json i l'anàlisi de les regles per als worktrees.

El nucli només afegeix (principi e). Per no reformatar el fitxer de ningú, insereix el text just on toca i
després comprova que el JSON resultant sigui exactament l'original més el que ha afegit. Les regles que
protegirien els worktrees no les aplica mai: les proposa.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .comu import Plega
from .patrons import coincideix


class Node:
    def __init__(self, tipus: str, inici: int, fi: int):
        self.tipus = tipus      # objecte · llista · valor
        self.inici = inici      # posició del primer caràcter
        self.fi = fi            # posició just després de l'últim
        self.membres = []       # objecte: [(clau, inici_clau, Node)] · llista: [Node]

    def membre(self, clau: str) -> Optional["Node"]:
        for k, _, v in self.membres:
            if k == clau:
                return v
        return None


class _Lector:
    """Lector de JSON que recorda on comença i on acaba cada valor."""

    def __init__(self, text: str):
        self.t = text
        self.i = 0

    def espais(self):
        while self.i < len(self.t) and self.t[self.i] in " \t\r\n":
            self.i += 1

    def valor(self) -> Node:
        self.espais()
        c = self.t[self.i:self.i + 1]
        if c == "{":
            return self.objecte()
        if c == "[":
            return self.llista()
        inici = self.i
        if c == '"':
            self.cadena()
        else:
            while self.i < len(self.t) and self.t[self.i] not in ",]} \t\r\n":
                self.i += 1
        return Node("valor", inici, self.i)

    def cadena(self) -> str:
        inici = self.i
        self.i += 1
        while self.t[self.i] != '"':
            self.i += 2 if self.t[self.i] == "\\" else 1
        self.i += 1
        return json.loads(self.t[inici:self.i])

    def objecte(self) -> Node:
        n = Node("objecte", self.i, 0)
        self.i += 1
        self.espais()
        if self.t[self.i] == "}":
            self.i += 1
            n.fi = self.i
            return n
        while True:
            self.espais()
            inici_clau = self.i
            clau = self.cadena()
            self.espais()
            self.i += 1  # «:»
            n.membres.append((clau, inici_clau, self.valor()))
            self.espais()
            if self.t[self.i] == ",":
                self.i += 1
                continue
            self.i += 1  # «}»
            n.fi = self.i
            return n

    def llista(self) -> Node:
        n = Node("llista", self.i, 0)
        self.i += 1
        self.espais()
        if self.t[self.i] == "]":
            self.i += 1
            n.fi = self.i
            return n
        while True:
            n.membres.append(self.valor())
            self.espais()
            if self.t[self.i] == ",":
                self.i += 1
                continue
            self.i += 1  # «]»
            n.fi = self.i
            return n


def _sagnat_linia(text: str, pos: int) -> Optional[str]:
    """El blanc que hi ha abans de `pos` a la seva línia, o None si abans hi ha alguna altra cosa."""
    ini = text.rfind("\n", 0, pos) + 1
    prefix = text[ini:pos]
    return prefix if prefix.strip() == "" else None


def _unitat(text: str, arrel: Node) -> str:
    if arrel.membres:
        s = _sagnat_linia(text, arrel.membres[0][1])
        if s:
            return s
    return "  "


def _json(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _insereix_membre(text: str, obj: Node, clau: str, valor_text: str, sagnat: str, unitat: str) -> str:
    """Afegeix «clau: valor» al final d'un objecte, amb el sagnat dels seus germans."""
    if obj.membres:
        ultim = obj.membres[-1][2]
        return text[:ultim.fi] + f",\n{sagnat}{_json(clau)}: {valor_text}" + text[ultim.fi:]
    tancament = sagnat[: -len(unitat)] if sagnat.endswith(unitat) else ""
    return text[:obj.inici + 1] + f"\n{sagnat}{_json(clau)}: {valor_text}\n{tancament}" + text[obj.fi - 1:]


def _llista_nova(regla: str, sagnat: str, unitat: str) -> str:
    return f"[\n{sagnat}{unitat}{_json(regla)}\n{sagnat}]"


def afegeix_regla(text: Optional[str], llista: str, regla: str) -> Optional[str]:
    """Torna el text de settings.json amb `regla` afegida a permissions.<llista>, o None si ja hi era.

    Plega si no ho pot fer sense tocar res més.
    """
    if text is None or not text.strip():
        return json.dumps({"permissions": {llista: [regla]}}, indent=2, ensure_ascii=False) + "\n"
    try:
        original = json.loads(text)
    except json.JSONDecodeError as e:
        raise Plega(f"settings.json no és JSON vàlid (línia {e.lineno}): no el toco")
    if not isinstance(original, dict):
        raise Plega("settings.json no és un objecte JSON: no el toco")
    perms = original.get("permissions", {})
    if not isinstance(perms, dict) or not isinstance(perms.get(llista, []), list):
        raise Plega(f"settings.json té «permissions.{llista}» amb un format inesperat: no el toco")
    if regla in perms.get(llista, []):
        return None

    arrel = _Lector(text).valor()
    unitat = _unitat(text, arrel)
    inici_perms = next((ini for k, ini, _ in arrel.membres if k == "permissions"), None)
    if inici_perms is None:
        valor = "{\n" + f"{unitat * 2}{_json(llista)}: {_llista_nova(regla, unitat * 2, unitat)}\n{unitat}" + "}"
        nou = _insereix_membre(text, arrel, "permissions", valor, unitat, unitat)
    else:
        perms_node = arrel.membre("permissions")
        sagnat_m = (_sagnat_linia(text, inici_perms) or "") + unitat
        if perms_node.membres:
            sagnat_m = _sagnat_linia(text, perms_node.membres[0][1]) or sagnat_m
        node = perms_node.membre(llista)
        if node is None:
            nou = _insereix_membre(text, perms_node, llista, _llista_nova(regla, sagnat_m, unitat), sagnat_m, unitat)
        elif not node.membres:
            nou = text[:node.inici] + _llista_nova(regla, sagnat_m, unitat) + text[node.fi:]
        else:
            ultim = node.membres[-1]
            s = _sagnat_linia(text, ultim.inici)
            separador = f",\n{s}" if s is not None else ", "
            nou = text[:ultim.fi] + separador + _json(regla) + text[ultim.fi:]

    esperat = copy.deepcopy(original)
    esperat.setdefault("permissions", {}).setdefault(llista, []).append(regla)
    try:
        if json.loads(nou) != esperat:
            raise ValueError
    except ValueError:
        raise Plega(f"no he sabut afegir {regla} a settings.json sense tocar res més: afegeix-la tu a «{llista}»")
    return nou


# ---------- worktrees: regles ancorades al checkout principal (§7.1) ----------

REGLA = re.compile(r"^([A-Za-z]+)\((.*)\)$", re.S)
MOSTRA_WT = ".claude/worktrees/nucli-exemple"
PENDENT, AL_PRINCIPAL, APLICADA = "pendent", "al checkout principal, però no a la base", "aplicada"


@dataclass
class Proposta:
    llista: str                 # deny · ask · allow · sandbox.excludedCommands
    nova: str
    vella: Optional[str] = None  # si n'hi ha, és una substitució
    motiu: str = ""
    font: str = ""
    estat: str = PENDENT


@dataclass
class Analisi:
    ref_base: str
    propostes: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    def pendents(self) -> list:
        return [p for p in self.propostes if p.estat != APLICADA]


def _llegeix_json(text: Optional[str], on: str, avisos: list) -> dict:
    if not text or not text.strip():
        return {}
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else {}
    except ValueError:
        avisos.append(f"{on} no és JSON vàlid: no l'he pogut analitzar")
        return {}


def _regles(dades: dict, llista: str) -> list:
    if llista == "sandbox.excludedCommands":
        v = (dades.get("sandbox") or {}).get("excludedCommands") or []
    else:
        v = (dades.get("permissions") or {}).get(llista) or []
    return [r for r in v if isinstance(r, str)]


def _parteix(regla: str):
    m = REGLA.match(regla.strip())
    return (m.group(1), m.group(2)) if m else (None, None)


def _home() -> str:
    return os.path.realpath(os.path.expanduser("~"))


def _real(cami: str) -> str:
    """El camí amb la part inicial sense comodins resolta (enllaços, /var → /private/var)."""
    parts = cami.split("/")
    k = next((i for i, p in enumerate(parts) if any(c in p for c in "*?[")), len(parts))
    fix = "/".join(parts[:k]) or "/"
    return os.path.realpath(fix) + ("/" + "/".join(parts[k:]) if k < len(parts) else "")


def _absolut(contingut: str) -> Optional[str]:
    """Camí absolut d'una regla de camí ancorada amb // o ~/; None per a les relatives."""
    if contingut.startswith("//"):
        return _real(contingut[1:])
    if contingut.startswith("~/"):
        return _real(_home() + contingut[1:])
    return None


def _mostra(patro_rel: str) -> str:
    """Un camí concret que coincideix amb el patró («.env.*» → «.env.x», «**/.env» → «.env»)."""
    s = re.sub(r"\*\*/", "", patro_rel)
    s = re.sub(r"\[[^\]]*\]", "x", s)
    return s.replace("**", "x").replace("*", "x").replace("?", "x")


def _cobreix_cami(contingut: str, font: str, cami: str, arrel_wt: str) -> bool:
    """Si una regla Read/Edit coincideix amb `cami` en una sessió que arrenca a `arrel_wt`."""
    if contingut.startswith("//") or contingut.startswith("~/"):
        patro = _absolut(contingut)
    elif contingut.startswith("/"):
        patro = (_home() + "/.claude" if font == "usuari" else arrel_wt) + contingut
    else:
        rel = contingut[2:] if contingut.startswith("./") else contingut
        return cami.startswith(arrel_wt + "/") and coincideix(rel, cami[len(arrel_wt) + 1:])
    return coincideix(patro.lstrip("/"), cami.lstrip("/"))


def _bash_coincideix(patro: str, ordre: str) -> bool:
    if patro.endswith(":*"):
        patro = patro[:-2] + " *"
    if patro.endswith(" *") and ordre == patro[:-2]:
        return True
    return re.fullmatch(re.escape(patro).replace(r"\*", ".*"), ordre, re.S) is not None


def _grafies(arrel: str) -> list:
    """Com es pot escriure el camí del checkout principal dins d'una ordre."""
    out = [arrel]
    home = _home()
    if arrel.startswith(home + "/"):
        rel = arrel[len(home) + 1:]
        out += [f"~/{rel}", f"$HOME/{rel}"]
    return out


def _coberta(fonts: list, eina: str, llistes: tuple, mostra: str, arrel_wt: str) -> bool:
    for font, dades in fonts:
        for llista in llistes:
            for r in _regles(dades, llista):
                e, c = _parteix(r)
                if e != eina:
                    continue
                if eina == "Bash":
                    if _bash_coincideix(c, mostra):
                        return True
                elif _cobreix_cami(c, font, mostra, arrel_wt):
                    return True
    return False


def _tokens_relatius(contingut: str, arrel: Path) -> list:
    """Paraules d'una ordre que són un fitxer del repo escrit amb camí relatiu («scripts/llanca-sync.sh»)."""
    out = []
    for tok in contingut.split():
        t = tok.strip("'\"")
        net = t[2:] if t.startswith("./") else t
        if not net or net.startswith(("/", "~", "$", "-")) or any(c in net for c in "*?[:"):
            continue
        if (arrel / net).is_file():
            out.append((tok, str(arrel / net)))
    return out


def _substitueix_token(text: str, tok: str, nou: str) -> str:
    return re.sub(r"(?<!\S)" + re.escape(tok) + r"(?!\S)", lambda _: nou, text)


def llegeix_settings_base(arrel: Path, ref_base: str) -> Optional[str]:
    r = subprocess.run(["git", "show", f"{ref_base}:.claude/settings.json"], cwd=str(arrel),
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def analitza(arrel: Path, ref_base: str) -> Analisi:
    """Les regles que protegeixen el checkout principal però no els worktrees, i la proposta per tancar-ho.

    Una proposta és «aplicada» quan la veu un worktree nou: al settings.json de la base, al settings.local.json del
    checkout principal o al ~/.claude/settings.json.
    """
    arrel = Path(os.path.realpath(str(arrel)))
    an = Analisi(ref_base)

    def fitxer(cami: Path) -> Optional[str]:
        return cami.read_text(encoding="utf-8") if cami.is_file() else None

    projecte = _llegeix_json(fitxer(arrel / ".claude/settings.json"), ".claude/settings.json", an.avisos)
    local = _llegeix_json(fitxer(arrel / ".claude/settings.local.json"), ".claude/settings.local.json", an.avisos)
    usuari = _llegeix_json(fitxer(Path(_home()) / ".claude/settings.json"), "~/.claude/settings.json", an.avisos)
    base = _llegeix_json(llegeix_settings_base(arrel, ref_base), f"{ref_base}:.claude/settings.json", an.avisos)
    efectives = [("projecte", base), ("local", local), ("usuari", usuari)]
    principal = [("projecte", projecte), ("local", local), ("usuari", usuari)]
    arrel_wt = f"{arrel}/{MOSTRA_WT}"
    fonts = [(".claude/settings.json", projecte), (".claude/settings.local.json", local),
             (f"{ref_base}:.claude/settings.json", base)]
    vistes = set()

    def proposa(p: Proposta, aplicada: bool, al_principal: bool) -> None:
        if (p.llista, p.nova, p.vella) in vistes or aplicada:
            return
        vistes.add((p.llista, p.nova, p.vella))
        p.estat = AL_PRINCIPAL if al_principal else PENDENT
        an.propostes.append(p)

    for nom_font, dades in fonts:
        for llista in ("deny", "ask"):
            llistes_cob = ("deny",) if llista == "deny" else ("ask", "deny")
            for regla in _regles(dades, llista):
                eina, c = _parteix(regla)
                if eina in ("Write", "NotebookEdit") and c:
                    an.avisos.append(f"{llista}: «{regla}» no es consulta mai (Claude Code només mira "
                                     f"Edit(…) i Read(…)); fes-la «Edit({c})»")
                    continue
                if eina in ("Edit", "Read") and c:
                    absolut = _absolut(c)
                    if not absolut or not absolut.startswith(str(arrel) + "/"):
                        continue
                    rel = absolut[len(str(arrel)) + 1:]
                    if not c.endswith(rel) or rel.startswith(".claude/worktrees/"):
                        continue
                    mostra = f"{arrel_wt}/{_mostra(rel)}"
                    if _cobreix_cami(c, nom_font, mostra, arrel_wt):
                        continue  # ja porta «**» (com les de .env): cobreix els worktrees tota sola
                    nova = f"{eina}({c[: len(c) - len(rel)]}.claude/worktrees/**/{rel})"
                    p = Proposta(llista, nova, motiu=f"«{regla}» protegeix el checkout principal, no els worktrees",
                                 font=nom_font)
                    proposa(p, _coberta(efectives, eina, llistes_cob, mostra, arrel_wt),
                            _coberta(principal, eina, llistes_cob, mostra, arrel_wt))
                elif eina == "Bash" and c:
                    for g in _grafies(str(arrel)):
                        if g + "/" not in c or f"{g}/.claude/worktrees/" in c:
                            continue
                        nou_c = c.replace(g + "/", g + "/.claude/worktrees/*/")
                        mostra = _mostra(nou_c.replace(g + "/", str(arrel) + "/"))
                        p = Proposta(llista, f"Bash({nou_c})", font=nom_font,
                                     motiu=f"«{regla}» apunta al checkout principal, no als worktrees")
                        proposa(p, _coberta(efectives, "Bash", llistes_cob, mostra, arrel_wt),
                                _coberta(principal, "Bash", llistes_cob, mostra, arrel_wt))
                        break

        for regla in _regles(dades, "allow"):
            eina, c = _parteix(regla)
            if eina != "Bash" or not c:
                continue
            tokens = _tokens_relatius(c[:-2] if c.endswith(":*") else c, arrel)
            if not tokens:
                continue
            nou_c = c
            for tok, absolut in tokens:
                nou_c = _substitueix_token(nou_c, tok, absolut)
            en = lambda fonts_: any(regla in _regles(d, "allow") for _, d in fonts_)  # noqa: E731
            p = Proposta("allow", f"Bash({nou_c})", vella=regla, font=nom_font,
                         motiu="amb camí relatiu, en un worktree executaria la còpia del worktree sense preguntar")
            proposa(p, not en(efectives), not en(principal))
            for exclosa in _regles(dades, "sandbox.excludedCommands"):
                nova_ex = exclosa
                for tok, absolut in tokens:
                    nova_ex = _substitueix_token(nova_ex, tok, absolut)
                if nova_ex != exclosa:
                    en_ex = lambda fonts_: any(exclosa in _regles(d, "sandbox.excludedCommands") for _, d in fonts_)  # noqa: E731
                    p = Proposta("sandbox.excludedCommands", nova_ex, vella=exclosa, font=nom_font,
                                 motiu="si no, la invocació amb camí absolut correria dins del sandbox i fallaria")
                    proposa(p, not en_ex(efectives), not en_ex(principal))

        tokens_allow = {t for r in _regles(dades, "allow") for t, _ in _tokens_relatius(_parteix(r)[1] or "", arrel)
                        if _parteix(r)[0] == "Bash"}
        for exclosa in _regles(dades, "sandbox.excludedCommands"):
            for tok, _ in _tokens_relatius(exclosa, arrel):
                if tok not in tokens_allow:
                    an.avisos.append(f"sandbox.excludedCommands: «{exclosa}» és relatiu: en un worktree "
                                     "sortiria del sandbox amb la còpia del worktree (després de preguntar-te)")
    an.avisos = list(dict.fromkeys(an.avisos))
    return an


def text_proposta(an: Analisi, arrel: Path) -> str:
    """El contingut de .nucli/proposta/permisos.md."""
    l = ["# Permisos per als worktrees (proposta de `nucli init`, no aplicada)", "",
         "Aquestes regles protegeixen el checkout principal però no `.claude/worktrees/**`, que és on treballen "
         "`nucli agent`, `claude --worktree` i els subagents amb `isolation: worktree`.", "",
         f"Un worktree llegeix el `.claude/settings.json` **de la base** (`{an.ref_base}`), no el del checkout principal. "
         "Aplica-les tu al `.claude/settings.json`, en un commit propi, i fusiona'l: fins llavors no facis servir "
         "worktrees en aquest repo, i `nucli agent` es nega a arrencar. També valen al `.claude/settings.local.json` "
         "del checkout principal o al teu `~/.claude/settings.json`.", ""]
    for llista in ("deny", "ask", "allow", "sandbox.excludedCommands"):
        ps = [p for p in an.propostes if p.llista == llista]
        if not ps:
            continue
        l.append(f"## `{llista}`")
        l.append("")
        for p in ps:
            if p.vella:
                l.append(f"- substitueix `{p.vella}`")
                l.append(f"  per `{p.nova}`")
            else:
                l.append(f"- afegeix `{p.nova}`")
            l.append(f"  ({p.motiu}; font: {p.font}; estat: {p.estat})")
        l.append("")
    if an.avisos:
        l += ["## Avisos (no bloquegen)", ""] + [f"- {a}" for a in an.avisos] + [""]
    l.append("Cap d'aquests canvis no afluixa res: afegeixen `deny`/`ask` o estrenyen un `allow` i una exclusió del sandbox.")
    return "\n".join(l) + "\n"


def resum_linies(an: Analisi) -> list:
    out = []
    for p in an.propostes:
        marca = "" if p.estat == PENDENT else f"   [{p.estat}]"
        if p.vella:
            out.append(f"{p.llista:<9} {p.vella}  →  {p.nova}{marca}")
        else:
            out.append(f"{p.llista:<9} + {p.nova}{marca}")
    return out
