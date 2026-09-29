"""`nucli intern fusiona-ganxos [--dry-run] [--settings camí]`: el pas d'install.sh que toca ~/.claude/settings.json.

Afegeix els hooks del nucli sense esborrar ni reordenar res i sense duplicats (reconeix els seus per «nucli hook
<nom>»). Abans d'escriure en fa una còpia de seguretat, i després comprova que el resultat sigui exactament
l'original més els hooks del nucli. No toca cap permís.
"""
from __future__ import annotations

import copy
import datetime
import difflib
import json
import re
import shutil
from pathlib import Path

from .comu import Plega

BIN = Path(__file__).resolve().parent.parent / "bin" / "nucli"


def ganxos(bin_: Path) -> list:
    ordre = f'"{bin_}" hook'
    return [
        ("PreToolUse", "^(Edit|Write|NotebookEdit)$", f"{ordre} protegeix-rebuts"),
        ("PostToolUse", "^Skill$", f"{ordre} us-skill"),
        ("UserPromptExpansion", None, f"{ordre} us-skill"),
    ]


def _es_nostre(handler: dict, nom: str) -> bool:
    return bool(re.search(rf"nucli\"? hook {re.escape(nom)}$", str(handler.get("command", "")).strip()))


def fusiona(original: dict, bin_: Path):
    """Torna (nou, accions). `accions` és una llista de (verb, esdeveniment, ordre)."""
    nou = copy.deepcopy(original)
    hooks = nou.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise Plega("«hooks» de settings.json no és un objecte: no el toco")
    accions = []
    for esdeveniment, matcher, ordre in ganxos(bin_):
        nom = ordre.rsplit(" ", 1)[1]
        grups = hooks.setdefault(esdeveniment, [])
        trobat = next((h for g in grups for h in (g.get("hooks") or []) if _es_nostre(h, nom)), None)
        if trobat is not None:
            if trobat.get("command") == ordre:
                accions.append(("ja hi és", esdeveniment, ordre))
            else:
                trobat["command"] = ordre
                accions.append(("actualitza", esdeveniment, ordre))
            continue
        grup = {"matcher": matcher} if matcher else {}
        grup["hooks"] = [{"type": "command", "command": ordre, "timeout": 10}]
        grups.append(grup)
        accions.append(("afegeix", esdeveniment, ordre))
    return nou, accions


def sense_els_nostres(dades: dict, original: dict) -> dict:
    """`dades` sense el que hi ha posat el nucli: ha de tornar a ser exactament `original`."""
    d = copy.deepcopy(dades)
    hooks_o = original.get("hooks", {}) if isinstance(original.get("hooks"), dict) else {}
    for esdeveniment, grups in list(d.get("hooks", {}).items()):
        grups_o = hooks_o.get(esdeveniment, [])
        net = []
        for i, g in enumerate(grups):
            if i < len(grups_o):
                # un grup que ja hi era: només hi pot haver canviat l'ordre d'un hook nostre (camí nou)
                for j, h in enumerate(g.get("hooks") or []):
                    if any(_es_nostre(h, n) for n in ("protegeix-rebuts", "us-skill")):
                        h["command"] = grups_o[i]["hooks"][j]["command"]
                net.append(g)
            elif not all(any(_es_nostre(h, n) for n in ("protegeix-rebuts", "us-skill")) for h in g.get("hooks") or []):
                net.append(g)
        if net or esdeveniment in hooks_o:
            d["hooks"][esdeveniment] = net
        else:
            del d["hooks"][esdeveniment]
    if "hooks" not in original and d.get("hooks") == {}:
        del d["hooks"]
    return d


def ordre(args) -> int:
    cami = Path(args.settings) if args.settings else Path.home() / ".claude" / "settings.json"
    text = cami.read_text(encoding="utf-8") if cami.is_file() else ""
    try:
        original = json.loads(text) if text.strip() else {}
    except ValueError as e:
        raise Plega(f"{cami} no és JSON vàlid ({e}): no el toco")
    if not isinstance(original, dict):
        raise Plega(f"{cami} no és un objecte JSON: no el toco")
    nou, accions = fusiona(original, BIN)
    for verb, esdeveniment, ordre_ in accions:
        print(f"  {verb:<9} hook {esdeveniment}: {ordre_}")
    if sense_els_nostres(nou, original) != original:
        raise Plega("la fusió tocaria alguna cosa que no és del nucli: no escric res")
    if all(v == "ja hi és" for v, _, _ in accions):
        return 0
    text_nou = json.dumps(nou, indent=2, ensure_ascii=False) + "\n"
    diff = difflib.unified_diff(text.splitlines(), text_nou.splitlines(), str(cami), str(cami), lineterm="", n=2)
    if args.dry_run:
        print("\n".join(f"    {l}" for l in diff))
        return 0
    cami.parent.mkdir(parents=True, exist_ok=True)
    if cami.is_file():
        copia = cami.with_name(f"{cami.name}.nucli-{datetime.datetime.now():%Y%m%d-%H%M%S}.bak")
        shutil.copy2(cami, copia)
        print(f"  còpia     {copia}")
    cami.write_text(text_nou, encoding="utf-8")
    if json.loads(cami.read_text(encoding="utf-8")) != nou:
        raise Plega(f"{cami} no ha quedat com esperava: recupera la còpia de seguretat")
    return 0
