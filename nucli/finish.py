"""`nucli finish`: l'executa sempre una persona, al terminal (fora del sandbox).

1. Git i rebut: comprovacions sobre el segell, HEAD i l'arbre. No executa res de la branca. L'arbre net es
   comprova sense excepcions: el que `ship` no podia llegir dins del sandbox, aquí ha de ser llegible i sense canvis.
2. Checks manuals, confirmats un per un.
3. Ensenya el `git diff --stat` contra la base, marca amb ⚠ els fitxers de la branca que formen part dels checks i
   demana confirmació explícita [s/N], amb el no per defecte. Amb un no, no fa res.
4. Executa contra HEAD tots els checks automàtics requerits, també els `fora_sandbox` pendents, i segella.
   Si algun falla, no puja res.
5. Push de la branca i PR (o comentari al PR obert). Mai merge.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from . import VERSIO
from .comu import Plega, Repo, troba_repo
from .ship import (arbre_head, ara, calcula_pla, canvis_pendents, desa_rebut, estat_del_rebut, executa_check,
                   fitxers_del_diff, fitxers_dels_checks, llegeix_rebut, segella, sha_rebut, text_manual)


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
    problemes, fora = estat_del_rebut(cfg, pla, rebut, arbre_head(repo))
    if problemes:
        raise Plega("el rebut no cobreix els checks requerits (recalculats ara):\n  " + "\n  ".join(problemes))
    return rebut, pla, head, commits[0], fora


def pregunta(text: str) -> bool:
    try:
        resposta = input(text).strip().lower()
    except EOFError:
        resposta = ""
    return resposta in ("s", "si", "sí")


def confirma_manuals(cfg: dict, manuals: list, registre: dict) -> None:
    if not manuals:
        return
    if not sys.stdin.isatty():
        raise Plega(f"hi ha checks manuals ({', '.join(manuals)}) i no hi ha terminal: "
                    "llança «nucli finish» en un terminal perquè una persona els confirmi. No he executat res")
    print("Checks manuals (els confirmes tu, un per un):")
    for m in manuals:
        ok = pregunta(f"  {m}: {text_manual(cfg, m)}. Confirmes? [s/N] ")
        registre["confirmacions"].append({"check": m, "resposta": "sí" if ok else "no", "hora": ara()})
        if not ok:
            raise Plega(f"{m} no confirmat: no he executat res ni pujat res")


def ensenya_diff(repo: Repo, cfg: dict, pla, automatics: list) -> dict:
    """El `git diff --stat` contra la base i, amb ⚠, els fitxers de la branca que executaran els checks."""
    print(f"Canvis de la branca respecte de {pla.ref_base} (merge-base {pla.merge_base[:8]}):")
    stat = repo.git("diff", "--stat=160", pla.merge_base, "HEAD")
    print("\n".join(f"  {l}" for l in stat.splitlines()) or "  (cap)")
    camins = [c for _, c in fitxers_del_diff(repo, pla.merge_base)]
    marcats = fitxers_dels_checks(repo, cfg, automatics, camins)
    if marcats:
        print("Fitxers de la branca que formen part dels checks (s'executaran fora del sandbox; revisa'ls):")
        for cami, motiu in marcats.items():
            print(f"  ⚠ {cami} · {motiu}")
    return marcats


def confirma_execucio(automatics: list, fora: dict) -> None:
    if not sys.stdin.isatty():
        raise Plega("cal un terminal per confirmar l'execució fora del sandbox: no he executat res ni pujat res")
    detall = ", ".join(f"{c} (encara no s'ha executat)" if c in fora else c for c in automatics)
    if not pregunta(f"Executo fora del sandbox, amb el codi d'aquesta branca: {detall}. Has llegit el diff? [s/N] "):
        raise Plega("no confirmat: no he executat res ni pujat res")


def executa_i_segella(repo: Repo, cfg: dict, pla, automatics: list, head: str, registre: dict, rebut: dict) -> None:
    """Executa contra HEAD cada check automàtic requerit i segella. Al primer error, desa el rebut sense segell i plega."""
    arbre = arbre_head(repo)
    rebut["finish"] = registre  # fora del sha256: el segell cobreix les execucions; això són les teves respostes
    for c in automatics:
        e = executa_check(repo, cfg, c, via="finish")
        rebut["execucions"].append(e)
        rebut["segell"] = None
        registre["execucions"].append({k: e[k] for k in ("check", "codi", "durada_s", "hora")})
        motiu = None
        if e["codi"] != 0:
            motiu = f"{c} falla a l'execució contra HEAD (codi {e['codi']})"
        elif repo.git("rev-parse", "HEAD") != head:
            motiu = f"HEAD ha canviat mentre s'executava {c}"
        elif canvis_pendents(repo) or e.get("arbre_despres") or e["arbre"] != arbre:
            motiu = f"{c} ha modificat l'arbre de treball"
        if motiu:
            registre["resultat"] = f"aturat: {motiu}"
            desa_rebut(repo, rebut)
            raise Plega(f"{motiu}: no pujo res")
    segell = segella(repo, cfg, pla, rebut)
    print(f"Segellat · HEAD {segell['head'][:8]} · en verd contra HEAD: {', '.join(automatics)}")


def resum(cfg: dict, head: str, registre: dict) -> str:
    linies = ["## Rebut del nucli", "", f"Checks executats per `nucli finish` contra HEAD `{head[:12]}`:", ""]
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
        raise Plega("el push ha fallat (si l'has llançat des del Bash de Claude, és el sandbox: fes-ho al terminal)")
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
    rebut, pla, head, titol, fora = comprova_git_i_rebut(repo, cfg, branca)
    if shutil.which("gh") is None:
        raise Plega("no trobo «gh» al PATH: el necessito per obrir el PR, i no pujo res sense poder-lo obrir")
    automatics = pla.automatics(cfg)
    registre = {"hora": ara(), "head": head, "confirmacions": [], "execucions": [], "resultat": "en curs"}
    print(f"nucli finish · branca {branca} · HEAD {head[:8]} · requerits: {', '.join(pla.requerits) or 'cap'}")
    amagats = rebut["segell"].get("no_llegibles")
    if amagats:
        print(f"Dins del sandbox no es podien llegir: {', '.join(amagats)}. Aquí sí, i no han canviat: l'arbre és net.")
    confirma_manuals(cfg, pla.manuals(cfg), registre)
    ensenya_diff(repo, cfg, pla, automatics)
    if automatics:
        confirma_execucio(automatics, fora)
        executa_i_segella(repo, cfg, pla, automatics, head, registre, rebut)
    else:
        print("Cap check automàtic requerit: no executo res de la branca.")
        rebut["finish"] = registre
    missatge = puja(repo, cfg, branca, titol, resum(cfg, head, registre))
    registre["resultat"] = "pujat"
    desa_rebut(repo, rebut)
    print(f"nucli finish · {missatge}")
    print("No he fet cap merge: el fas tu des de GitHub.")
    return 0
