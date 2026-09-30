"""Aïllament natiu: `nucli port` i `nucli neteja`. Els worktrees els crea Claude Code (`claude --worktree`).

`nucli neteja` treu els worktrees fusionats i, des de la v0.1.3, també esborra les branques locals que ja són a la
base per història, sempre amb `git branch -d` (mai -D), i mai la branca actual ni la base.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .comu import Plega, Repo, port_de, troba_repo

PREFIX_BRANCA = "worktree-"  # P5: la v0.1 només neteja les branques que crea `claude --worktree`


def ordre_port(args) -> int:
    repo = troba_repo()
    port = port_de(repo.worktree)
    print(port)
    if args.comprova:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print(f"nucli: el port {port} està ocupat", file=sys.stderr)
                return 1
    return 0


@dataclass
class Worktree:
    cami: Path
    branca: str
    head: str
    bloquejat: bool


def worktrees_de_claude(repo: Repo) -> list:
    """Els worktrees sota .claude/worktrees/ del checkout principal."""
    arrel_wt = repo.arrel / ".claude" / "worktrees"
    out, actual = [], {}
    for linia in repo.git("worktree", "list", "--porcelain").splitlines() + [""]:
        if not linia:
            if actual.get("worktree"):
                cami = Path(actual["worktree"]).resolve()
                if arrel_wt in cami.parents:
                    branca = actual.get("branch", "").replace("refs/heads/", "")
                    out.append(Worktree(cami, branca, actual.get("HEAD", ""), "locked" in actual))
            actual = {}
            continue
        clau, _, valor = linia.partition(" ")
        actual[clau] = valor
    return out


def fusionat_per_gh(branca: str, head: str, cwd: Path):
    """El número del PR fusionat amb aquest mateix HEAD (fusions squash des de GitHub), o None."""
    if shutil.which("gh") is None:
        return None
    r = subprocess.run(["gh", "pr", "list", "--head", branca, "--state", "merged", "--json", "number,headRefOid"],
                       cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    for pr in json.loads(r.stdout or "[]"):
        if pr.get("headRefOid") == head:
            return pr["number"]
    return None


def branques_fusionades(repo: Repo, base: str, excepte: set) -> list:
    """Les branques locals que ja són a `base` per història i que no té cap worktree (les dels worktrees les
    tracta la neteja de worktrees). Les d'`excepte` (la branca actual i la base) no hi surten mai."""
    out = []
    sortida = repo.git("for-each-ref", f"--merged={base}", "--format=%(refname:lstrip=2) %(worktreepath)", "refs/heads/")
    for linia in sortida.splitlines():
        branca, _, worktree = linia.partition(" ")
        if branca and not worktree and branca not in excepte:
            out.append(branca)
    return out


def ordre_neteja(args) -> int:
    repo = troba_repo()
    if repo.es_worktree:
        raise Plega(f"executa «nucli neteja» al checkout principal ({repo.arrel})")
    if subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo.arrel)).returncode != 0:
        raise Plega("git fetch ha fallat: nucli neteja necessita xarxa (executa-la tu, fora del sandbox)")
    base = repo.ref_base()
    fora, dins = [], []
    for wt in worktrees_de_claude(repo):
        nom = wt.cami.name
        if not wt.branca.startswith(PREFIX_BRANCA):
            fora.append(f"{nom}: la branca «{wt.branca or 'cap'}» no és {PREFIX_BRANCA}*")
            continue
        if wt.bloquejat:
            fora.append(f"{nom}: bloquejat (git worktree unlock si ja no el fa servir ningú)")
            continue
        if subprocess.run(["git", "status", "--porcelain"], cwd=str(wt.cami), capture_output=True, text=True).stdout.strip():
            fora.append(f"{nom}: té canvis sense commit")
            continue
        if repo.git_ok("merge-base", "--is-ancestor", wt.head, base):
            dins.append((wt, "-d", f"ja és a {base} (història)"))
            continue
        pr = fusionat_per_gh(wt.branca, wt.head, repo.arrel)
        if pr is not None:
            dins.append((wt, "-D", f"PR #{pr} fusionat amb aquest mateix HEAD (squash, verificat amb gh)"))
        else:
            fora.append(f"{nom}: no està fusionat")
    branques = branques_fusionades(repo, base, {repo.branca(), repo.config()["branca_base"]})
    print(f"nucli neteja · {repo.arrel} · base {base}" + ("  (--dry-run)" if args.dry_run else ""))
    for wt, _, motiu in dins:
        print(f"  treu     {wt.cami.name} ({wt.branca}) · {motiu}")
    for f in fora:
        print(f"  es queda {f}")
    for b in branques:
        print(f"  esborra  branca {b} · ja és a {base} (història)")
    if not dins and not branques:
        print("Res a netejar.")
        return 0
    if args.dry_run:
        return 0
    if not sys.stdin.isatty():
        raise Plega("cal un terminal per confirmar la neteja")
    que = []
    if dins:
        que.append(f"trec {len(dins)} worktree(s) i les seves branques")
    if branques:
        que.append(f"esborro {len(branques)} branca(es) local(s) fusionada(es) amb git branch -d")
    pregunta = ", i ".join(que)
    if input(f"{pregunta[0].upper()}{pregunta[1:]}? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No he tocat res.")
        return 0
    for wt, opcio, _ in dins:
        r = subprocess.run(["git", "worktree", "remove", str(wt.cami)], cwd=str(repo.arrel), capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ✗ {wt.cami.name}: {r.stderr.strip()}", file=sys.stderr)
            continue
        r = subprocess.run(["git", "branch", opcio, wt.branca], cwd=str(repo.arrel), capture_output=True, text=True)
        estat = "✓" if r.returncode == 0 else f"worktree tret, però la branca no: {r.stderr.strip()}"
        print(f"  {estat} {wt.cami.name} ({wt.branca})")
    for b in branques:
        r = subprocess.run(["git", "branch", "-d", b], cwd=str(repo.arrel), capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  ✓ branca {b}")
        else:
            print(f"  ✗ branca {b}: {r.stderr.strip()}", file=sys.stderr)
    return 0
