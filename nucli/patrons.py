"""Patrons amb la sintaxi de .gitignore, sobre camins relatius separats per «/».

Sense «/» (tret d'un de final), el patró coincideix amb el nom a qualsevol nivell; amb «/», des de l'arrel.
«**» vol dir qualsevol nombre de carpetes, «*» i «?» no travessen «/», i un «/» final vol dir «carpeta».
Un patró que coincideix amb una carpeta coincideix amb tot el que hi ha a dins.
"""
from __future__ import annotations

import re
from functools import lru_cache


def a_regex(patro: str) -> str:
    out, i, n = [], 0, len(patro)
    while i < n:
        c = patro[i]
        if c == "*":
            if patro.startswith("**", i):
                if patro.startswith("**/", i):
                    out.append("(?:.*/)?")
                    i += 3
                else:
                    out.append(".*")
                    i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = patro.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                classe = patro[i + 1:j]
                if classe.startswith("!"):
                    classe = "^" + classe[1:]
                out.append("[" + classe.replace("\\", "\\\\") + "]")
                i = j + 1
                continue
        elif c == "\\" and i + 1 < n:
            out.append(re.escape(patro[i + 1]))
            i += 2
            continue
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


@lru_cache(maxsize=512)
def _compila(patro: str):
    return re.compile(a_regex(patro) + r"\Z", re.S)


def coincideix(patro: str, cami: str) -> bool:
    p = patro.strip()
    if not p or p.startswith("#"):
        return False
    nomes_carpeta = p.endswith("/")
    p = p.rstrip("/")
    ancorat = "/" in p
    p = p.lstrip("/")
    parts = cami.strip("/").split("/")
    rx = _compila(p)
    if not ancorat:
        candidats = parts[:-1] if nomes_carpeta else parts
        return any(rx.match(c) for c in candidats)
    for k in range(len(parts), 0, -1):
        if nomes_carpeta and k == len(parts):
            continue
        if rx.match("/".join(parts[:k])):
            return True
    return False


def algun(patrons, cami: str) -> bool:
    return any(coincideix(p, cami) for p in patrons)
