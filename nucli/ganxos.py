"""Hooks de Claude Code (globals, els instal·la install.sh). Fora d'un repo amb nucli.json no fan res.

Llegeixen l'entrada JSON de stdin. Davant de qualsevol error inesperat surten amb 0: un hook del nucli
no ha de trencar mai una sessió.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .comu import DIR_NUCLI, repo_amb_nucli

MOTIU_REBUTS = ("nucli: els rebuts de .nucli/rebuts/ només els escriu «nucli ship». No s'editen a mà: "
                "si un check falla, arregla el codi i torna'l a executar.")


def _camins(entrada: dict) -> list:
    ti = entrada.get("tool_input") or {}
    base = entrada.get("cwd") or os.getcwd()
    out = []
    for clau in ("file_path", "notebook_path"):
        v = ti.get(clau)
        if isinstance(v, str) and v:
            p = Path(os.path.expanduser(v))
            if not p.is_absolute():
                p = Path(base) / p
            out.append(Path(os.path.normpath(str(p))))
            out.append(Path(os.path.realpath(str(p))))
    return out


def arrel_de_rebut(cami: Path):
    """Si `cami` és dins de <arrel>/.nucli/rebuts/, torna <arrel>; si no, None."""
    parts = cami.parts
    for i in range(len(parts) - 1):
        if parts[i] == DIR_NUCLI and parts[i + 1] == "rebuts":
            return Path(*parts[:i])
    return None


def protegeix_rebuts(entrada: dict) -> int:
    for cami in _camins(entrada):
        arrel = arrel_de_rebut(cami)
        if arrel is not None and repo_amb_nucli(arrel) is not None:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": MOTIU_REBUTS,
            }}, ensure_ascii=False))
            return 0
    return 0


def ordre(args) -> int:
    try:
        entrada = json.load(sys.stdin)
        if not isinstance(entrada, dict):
            return 0
        if args.nom == "protegeix-rebuts":
            return protegeix_rebuts(entrada)
        if args.nom == "us-skill":
            from . import us
            return us.registra(entrada)
    except Exception:
        return 0
    return 0
