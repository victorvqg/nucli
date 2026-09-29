"""`nucli finish`: l'executa sempre una persona, fora del sandbox (al terminal o amb `!`).

1. Git i rebut: comprovacions sobre el segell, HEAD i l'arbre.
2. Checks manuals, confirmats un per un en un terminal.
3. Torna a executar contra HEAD tots els checks automàtics requerits. Si algun falla, no puja res.
4. Push de la branca i PR (o comentari al PR obert). Mai merge.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from . import VERSIO
from .comu import Plega, Repo, troba_repo
from .ship import (arbre_head, ara, calcula_pla, canvis_pendents, desa_rebut, executa_check, llegeix_rebut,
                   problemes_checks, sha_rebut, text_manual)


def comprova_git_i_rebut(repo: Repo, cfg: dict, branca: str):
    if branca == "HEAD":
        raise Plega("HEAD desenganxat: nucli finish puja una branca")
    if branca == cfg["branca_base"]:
        raise Plega(f"ets a la branca base ({branca}): nucli finish només puja branques de feina")
    rebut = llegeix_rebut(repo, branca, exigeix=True)
    segell = rebut.get("segell")
    if not segell:
        raise Plega("el rebut no està segellat: passa els checks i «nucli ship seal»")
    if segell.get("sha256") != sha_rebut(rebut):
        raise Plega("el sha256 del segell no quadra: algú ha tocat el rebut. Torna a passar els checks i «nucli ship seal»")
    head = repo.git("rev-parse", "HEAD")
    if head != segell.get("head"):
        raise Plega(f"HEAD ({head[:8]}) no és el del segell ({str(segell.get('head'))[:8]}): hi ha commits posteriors. "
                    "Torna a passar els checks i «nucli ship seal»")
    pendents = canvis_pendents(repo)
    if pendents:
        raise Plega("l'arbre de treball no és net:\n  " + "\n  ".join(pendents[:20]))
    pla = calcula_pla(repo)
    commits = repo.git("log", "--reverse", "--format=%s", f"{pla.merge_base}..HEAD").splitlines()
    if not commits:
        raise Plega(f"la branca no té cap commit respecte de {pla.ref_base}: no hi ha res a pujar")
    problemes = problemes_checks(rebut, pla.automatics(cfg), arbre_head(repo))
    if problemes:
        raise Plega("el rebut no cobreix els checks requerits (recalculats ara):\n  " + "\n  ".join(problemes))
    return rebut, pla, head, commits[0]


def confirma_manuals(cfg: dict, manuals: list, registre: dict, repo: Repo, rebut: dict) -> None:
    if not manuals:
        return
    if not sys.stdin.isatty():
        raise Plega(f"hi ha checks manuals ({', '.join(manuals)}) i no hi ha terminal: "
                    "llança «nucli finish» en un terminal perquè una persona els confirmi")
    print("Checks manuals (els confirmes tu, un per un):")
    for m in manuals:
        try:
            resposta = input(f"  {m}: {text_manual(cfg, m)}. Confirmes? [s/N] ").strip().lower()
        except EOFError:
            resposta = ""
        ok = resposta in ("s", "si", "sí")
        registre["confirmacions"].append({"check": m, "resposta": "sí" if ok else "no", "hora": ara()})
        if not ok:
            registre["resultat"] = f"aturat: {m} no confirmat"
            desa_rebut(repo, rebut)
            raise Plega(f"{m} no confirmat: no pujo res")


def torna_a_passar_checks(repo: Repo, cfg: dict, automatics: list, head: str, registre: dict, rebut: dict) -> None:
    if not automatics:
        return
    arbre = arbre_head(repo)
    print(f"Torno a executar contra HEAD {head[:8]}: {', '.join(automatics)}. "
          "Corren fora del sandbox i executen codi d'aquesta branca.")
    for c in automatics:
        e = executa_check(repo, cfg, c, via="finish")
        registre["execucions"].append(e)
        motiu = None
        if e["codi"] != 0:
            motiu = f"{c} falla a la re-execució contra HEAD (codi {e['codi']})"
        elif repo.git("rev-parse", "HEAD") != head:
            motiu = f"HEAD ha canviat mentre s'executava {c}"
        elif canvis_pendents(repo) or e.get("arbre_despres") or e["arbre"] != arbre:
            motiu = f"{c} ha modificat l'arbre de treball"
        if motiu:
            registre["resultat"] = f"aturat: {motiu}"
            desa_rebut(repo, rebut)
            raise Plega(f"{motiu}: no pujo res")


def resum(cfg: dict, head: str, registre: dict) -> str:
    linies = ["## Rebut del nucli", "", f"Checks re-executats per `nucli finish` contra HEAD `{head[:12]}`:", ""]
    if registre["execucions"]:
        linies += ["| check | codi | durada | hora |", "|---|---|---|---|"]
        linies += [f"| {e['check']} | {e['codi']} | {e['durada_s']} s | {e['hora']} |" for e in registre["execucions"]]
    else:
        linies.append("Cap check automàtic requerit.")
    if registre["confirmacions"]:
        linies += ["", "Confirmacions manuals:"]
        linies += [f"- {c['check']}: {c['resposta']} ({c['hora']})" for c in registre["confirmacions"]]
    linies += ["", f"HEAD `{head}` · nucli {VERSIO}"]
    return "\n".join(linies) + "\n"


def gh(*args: str, entrada: str = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, input=entrada)


def puja(repo: Repo, cfg: dict, branca: str, titol: str, cos: str) -> str:
    r = subprocess.run(["git", "push", "-u", "origin", branca], cwd=str(repo.worktree))
    if r.returncode != 0:
        raise Plega("el push ha fallat (si l'has llançat des del Bash de Claude, és el sandbox: fes-ho amb «!» o al terminal)")
    r = gh("pr", "list", "--head", branca, "--state", "open", "--json", "number,url")
    oberts = json.loads(r.stdout or "[]") if r.returncode == 0 else []
    if oberts:
        pr = oberts[0]
        r = gh("pr", "comment", str(pr["number"]), "--body-file", "-", entrada=cos)
        if r.returncode != 0:
            raise Plega(f"push fet, però no he pogut comentar el PR #{pr['number']}: {r.stderr.strip()}")
        return f"push fet i resum afegit com a comentari al PR obert: {pr['url']}"
    r = gh("pr", "create", "--base", cfg["branca_base"], "--head", branca, "--title", titol, "--body-file", "-", entrada=cos)
    if r.returncode != 0:
        raise Plega(f"push fet, però «gh pr create» ha fallat: {r.stderr.strip()}")
    return f"push fet i PR obert: {r.stdout.strip()}"


def ordre(args) -> int:
    repo = troba_repo()
    cfg = repo.config()
    branca = repo.branca()
    rebut, pla, head, titol = comprova_git_i_rebut(repo, cfg, branca)
    if shutil.which("gh") is None:
        raise Plega("no trobo «gh» al PATH: el necessito per obrir el PR, i no pujo res sense poder-lo obrir")
    registre = {"hora": ara(), "head": head, "confirmacions": [], "execucions": [], "resultat": "en curs"}
    rebut["finish"] = registre  # fora del sha256: el segell cobreix el que va fer l'agent, això és el que fas tu
    print(f"nucli finish · branca {branca} · HEAD {head[:8]} · requerits: {', '.join(pla.requerits) or 'cap'}")
    confirma_manuals(cfg, pla.manuals(cfg), registre, repo, rebut)
    torna_a_passar_checks(repo, cfg, pla.automatics(cfg), head, registre, rebut)
    missatge = puja(repo, cfg, branca, titol, resum(cfg, head, registre))
    registre["resultat"] = "pujat"
    desa_rebut(repo, rebut)
    print(f"nucli finish · {missatge}")
    print("No he fet cap merge: el fas tu des de GitHub.")
    return 0
