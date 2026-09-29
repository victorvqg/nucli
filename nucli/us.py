"""Mesura d'ús de les skills: el hook `us-skill` i `nucli usage [--dies 30]`.

El hook escriu una línia a ~/.nucli/us.jsonl per cada skill oberta en un repo amb nucli.json: les que obre
Claude (PostToolUse de l'eina Skill, "via": "claude") i els `/skill` que escrius tu (UserPromptExpansion,
"via": "usuari").
"""
from __future__ import annotations

import datetime
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from .comu import Repo, repo_amb_nucli
from .ship import ara


def fitxer_us() -> Path:
    return Path(os.path.expanduser("~")) / ".nucli" / "us.jsonl"


def registra(entrada: dict) -> int:
    esdeveniment = entrada.get("hook_event_name")
    if esdeveniment == "UserPromptExpansion":
        skill, via = entrada.get("command_name"), "usuari"
    elif esdeveniment == "PostToolUse" and entrada.get("tool_name") == "Skill":
        skill, via = (entrada.get("tool_input") or {}).get("skill"), "claude"
    else:
        return 0
    if not isinstance(skill, str) or not skill.strip():
        return 0
    repo = repo_amb_nucli(entrada.get("cwd"))
    if repo is None:
        return 0
    linia = {"data": ara(), "skill": skill.strip().lstrip("/"), "repo": repo.arrel.name, "via": via}
    p = fitxer_us()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(linia, ensure_ascii=False) + "\n")
    return 0


def llegeix(desde: datetime.datetime) -> list:
    p = fitxer_us()
    if not p.is_file():
        return []
    out = []
    for linia in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(linia)
            if datetime.datetime.fromisoformat(d["data"]) >= desde:
                out.append(d)
        except (ValueError, KeyError, TypeError):
            continue
    return out


def skills_installades(cwd) -> list:
    """(nom, on) de les skills de ~/.claude/skills i de .claude/skills del repo actual (i del checkout principal)."""
    dirs = [(Path(os.path.expanduser("~")) / ".claude" / "skills", "~/.claude/skills")]
    try:
        repo = Repo(cwd)
        for arrel in dict.fromkeys([repo.worktree, repo.arrel]):
            dirs.append((arrel / ".claude" / "skills", f"{arrel.name}/.claude/skills"))
    except Exception:
        pass
    out = {}
    for d, on in dirs:
        if d.is_dir():
            for s in sorted(d.iterdir()):
                if (s / "SKILL.md").is_file() and s.name not in out:
                    out[s.name] = on
    return sorted(out.items())


def ordre(args) -> int:
    ara_ = datetime.datetime.now().astimezone()
    usos = llegeix(ara_ - datetime.timedelta(days=args.dies))
    print(f"nucli usage · últims {args.dies} dies · {len(usos)} usos (només es compten els repos amb nucli.json)")
    per_skill = Counter(u["skill"] for u in usos)
    vies = defaultdict(Counter)
    for u in usos:
        vies[u["skill"]][u.get("via", "claude")] += 1
    if usos:
        ample = max(len(s) for s in per_skill)
        print("Per skill:")
        for skill, n in per_skill.most_common():
            detall = " · ".join(f"{via} {k}" for via, k in sorted(vies[skill].items()))
            print(f"  {skill:<{ample}}  {n:>4}  ({detall})")
        print("Per repo:")
        for repo, n in Counter(u["repo"] for u in usos).most_common():
            print(f"  {repo:<{ample}}  {n:>4}")
    installades = skills_installades(os.getcwd())
    sense = [(nom, on) for nom, on in installades if nom not in per_skill]
    print(f"Skills instal·lades: {len(installades)}. Sense cap ús en {args.dies} dies: {len(sense)}.")
    for nom, on in sense:
        print(f"  {nom}  ({on})")
    return 0
