"""Permisos de Claude Code: insercions mínimes a settings.json.

El nucli només afegeix (principi e). Per no reformatar el fitxer de ningú, insereix el text just on toca i
després comprova que el JSON resultant sigui exactament l'original més el que ha afegit.
"""
from __future__ import annotations

import copy
import json
from typing import Optional

from .comu import Plega


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
