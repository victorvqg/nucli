"""`nucli tasca N` (v0.1.4): comença en una sessió la feina de l'issue #N de GitHub.

Llegeix l'issue amb `gh`, crea la branca `issue/N-descripcio` des de la base (després d'un `git fetch`), s'hi passa
i canvia l'estat de l'issue a `estat: en-curs`. Fa servir `gh` i la xarxa: la llança una persona, al terminal, o
Claude després de preguntar-t'ho. Mai fa push ni commit.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata

from .comu import Plega, Repo, troba_repo
from .config import branca_issues, issue_de_branca

NUMERO = re.compile(r"^#?([0-9]+)$")
MAX_SLUG = 40
PREFIX_ESTAT = "estat: "
EN_CURS = "estat: en-curs"
AVIS_SANDBOX = "si l'has llançada des del Bash de Claude, és el sandbox: fes-ho al terminal"


def slug(titol: str) -> str:
    """La descripció de la branca, feta amb el títol: sense accents (NFKD i només ASCII), en minúscules, cada tros
    que no és [a-z0-9] passa a un sol «-», sense «-» als extrems i de 40 caràcters com a màxim (tallat, i sense «-»
    al final). Si no en queda res, «tasca». `tasques_gh.py` (els agents del Marcador) ha de fer exactament això."""
    t = unicodedata.normalize("NFKD", titol).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:MAX_SLUG].rstrip("-")
    return t or "tasca"


def gh(*args: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=str(cwd), capture_output=True, text=True)


def llegeix_issue(repo: Repo, n: int) -> dict:
    r = gh("issue", "view", str(n), "--json", "number,title,state,labels", cwd=repo.worktree)
    if r.returncode != 0:
        raise Plega(f"no he pogut llegir l'issue #{n} amb gh: {(r.stderr or r.stdout).strip()} ({AVIS_SANDBOX})")
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise Plega(f"gh no ha tornat JSON per a l'issue #{n}")


def branques_de_l_issue(repo: Repo, cfg: dict, n: int) -> list:
    """Les branques locals i del remot que ja són de l'issue #N (`issue/N-…`, `worktree-issue-N`…)."""
    locals_ = repo.git("for-each-ref", "--format=%(refname:strip=2)", "refs/heads/").splitlines()
    out = [b for b in locals_ if issue_de_branca(b, cfg) == n]
    if repo.git_ok("remote", "get-url", "origin"):
        r = subprocess.run(["git", "ls-remote", "--heads", "origin"], cwd=str(repo.worktree), capture_output=True,
                           text=True)
        if r.returncode != 0:
            raise Plega(f"git ls-remote ha fallat: {r.stderr.strip()} ({AVIS_SANDBOX})")
        for linia in r.stdout.splitlines():
            b = linia.split("refs/heads/", 1)[-1]
            if issue_de_branca(b, cfg) == n and f"origin/{b}" not in out:
                out.append(f"origin/{b}")
    return out


def ordre(args) -> int:
    repo = troba_repo()
    cfg = repo.config()
    m = NUMERO.match(args.numero)
    if not m:
        raise Plega(f"«{args.numero}» no és el número d'un issue (p. ex. 12 o #12)")
    n = int(m.group(1))
    if shutil.which("gh") is None:
        raise Plega("no trobo «gh» al PATH: el necessito per llegir l'issue i canviar-ne l'estat")

    issue = llegeix_issue(repo, n)
    titol = (issue.get("title") or "").strip()
    if str(issue.get("state", "")).upper() != "OPEN":
        raise Plega(f"l'issue #{n} no és obert ({issue.get('state')}): no hi començo cap branca")
    branca = f"{branca_issues(cfg)}{n}-{slug(titol)}"
    existents = branques_de_l_issue(repo, cfg, n)
    if existents:
        raise Plega(f"l'issue #{n} ja té branca: {', '.join(existents)}. Si és teva, passa-hi (git switch …); "
                    "no en creo cap altra")

    base = cfg["branca_base"]
    if repo.git_ok("remote", "get-url", "origin"):
        r = subprocess.run(["git", "fetch", "-q", "origin", base], cwd=str(repo.worktree), capture_output=True, text=True)
        if r.returncode != 0:
            raise Plega(f"git fetch origin {base} ha fallat: {r.stderr.strip()} ({AVIS_SANDBOX})")
    ref = repo.ref_base()
    r = subprocess.run(["git", "switch", "--no-track", "-c", branca, ref], cwd=str(repo.worktree),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Plega(f"no he pogut crear la branca {branca}: {r.stderr.strip()}")
    print(f"nucli tasca · #{n} · {titol}")
    print(f"branca {branca} creada des de {ref} ({repo.git('rev-parse', '--short', 'HEAD')}): ja hi ets")

    treu = [e["name"] for e in issue.get("labels") or [] if e.get("name", "").startswith(PREFIX_ESTAT)
            and e["name"] != EN_CURS]
    edita = ["issue", "edit", str(n), "--add-label", EN_CURS]
    for e in treu:
        edita += ["--remove-label", e]
    r = gh(*edita, cwd=repo.worktree)
    if r.returncode != 0:
        print(f"nucli: la branca hi és, però no he pogut posar «{EN_CURS}» a l'issue #{n}: "
              f"{(r.stderr or r.stdout).strip()}. Posa-la a mà: gh issue edit {n} --add-label '{EN_CURS}'",
              file=sys.stderr)
        return 1
    print(f"issue #{n}: «{EN_CURS}»" + (f" (abans: {', '.join(treu)})" if treu else ""))
    print(f"Commits: tipus(àmbit): què (#{n}). Per pujar-la, nucli ship i nucli finish: el PR portarà «Closes #{n}».")
    return 0
