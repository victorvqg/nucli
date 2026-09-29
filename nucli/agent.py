"""`nucli agent <id>`: la versió general de scripts/agent.sh. Un agent headless en un worktree nou, sense push.

Es nega a arrencar mentre hi hagi permisos pendents per als worktrees (§7.1). En acabar desbloqueja el
worktree, passa els checks `fora_sandbox` que toquin i intenta segellar. L'última línia diu sempre com
revisar-ho i llançar `nucli finish`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import permisos
from .comu import Plega, Repo, prepara_dir_nucli, troba_repo
from .ship import calcula_pla, desa_rebut, executa_check, llegeix_rebut, ordre_seal

ID_VALID = re.compile(r"^[a-z0-9-]+$")

EINES_PERMESES = ["Read", "Edit", "Write", "Grep", "Glob", "Bash(git:*)", "Bash(nucli ship plan)",
                  "Bash(nucli ship run:*)", "Bash(nucli ship seal)", "Bash(nucli port)"]
EINES_PROHIBIDES = [
    "Bash(git push:*)", "Bash(git merge:*)", "Bash(git checkout:*)", "Bash(git switch:*)", "Bash(git rebase:*)",
    "Bash(git reset:*)", "Bash(git -C:*)", "Bash(git config:*)", "Bash(git diff --no-index:*)", "Bash(git add -f:*)",
    "Bash(git add --force:*)", "Bash(curl:*)", "Bash(npx:*)", "Bash(npm:*)", "Bash(pip:*)", "Bash(gh:*)",
    "WebFetch", "WebSearch",
    "Bash(nucli finish:*)", "Bash(nucli neteja:*)", "Bash(nucli init:*)", "Bash(nucli agent:*)",
]


def variants_absolutes(regla: str, arrel: Path) -> list:
    """Per a `Bash(bash scripts/x.sh)`, també `Bash(bash <arrel>/scripts/x.sh)`, `~/…` i `./…`."""
    eina, c = permisos._parteix(regla)
    if eina != "Bash" or not c:
        return []
    out = []
    for tok, absolut in permisos._tokens_relatius(c[:-2] if c.endswith(":*") else c, arrel):
        rel = tok[2:] if tok.startswith("./") else tok
        grafies = [absolut, f"./{rel}"] + [f"{g}/{rel}" for g in permisos._grafies(str(arrel))[1:]]
        for g in grafies:
            if g != tok:
                out.append(f"Bash({permisos._substitueix_token(c, tok, g)})")
    return out


def allows_ancorats(arrel: Path, ref: str) -> list:
    """Les regles `allow` de Bash que veurà el worktree i que apunten al checkout principal."""
    fonts = [permisos.llegeix_settings_base(arrel, ref)]
    local = arrel / ".claude" / "settings.local.json"
    if local.is_file():
        fonts.append(local.read_text(encoding="utf-8"))
    out = []
    for text in fonts:
        dades = permisos._llegeix_json(text, "settings", [])
        for r in permisos._regles(dades, "allow"):
            eina, c = permisos._parteix(r)
            if eina == "Bash" and c and any(g + "/" in c for g in permisos._grafies(str(arrel))):
                out.append(r)
    return out


def eines_prohibides(cfg: dict, arrel: Path, ref: str) -> list:
    out = list(EINES_PROHIBIDES)
    for r in cfg["agent"]["prohibides"]:
        out.append(r)
        out += variants_absolutes(r, arrel)
    out += allows_ancorats(arrel, ref)
    return list(dict.fromkeys(out))


def bloc_tasca(cfg: dict, arrel: Path, id_: str):
    t = cfg.get("tasques")
    if not t:
        return None
    cami = arrel / t["fitxer"]
    if not cami.is_file():
        return None
    linies = cami.read_text(encoding="utf-8").splitlines()
    for i, l in enumerate(linies):
        if re.match(rf"^### {re.escape(id_)}( ·|$)", l):
            fi = i + 1
            while fi < len(linies) and not linies[fi].startswith(("### ", "## ")):
                fi += 1
            return "\n".join(linies[i:fi]).rstrip()
    return None


def prompt(cfg: dict, repo: Repo, id_: str, tasca: str) -> str:
    docs = cfg.get("docs", {})
    llista = ", ".join(f"`{docs[r] if isinstance(docs[r], str) else docs[r]['cami']}`"
                       for r in ("estat", "decisions", "trampes", "convencions", "arquitectura") if docs.get(r))
    idioma = "en català" if cfg["idioma"] == "ca" else f"en l'idioma «{cfg['idioma']}»"
    return f"""Ets un agent de codi en mode headless al worktree `.claude/worktrees/{id_}` (branca `worktree-{id_}`) del repo «{repo.arrel.name}». Fes NOMÉS aquesta tasca:

{tasca}

Cicle (obligatori):
1. Llegeix CLAUDE.md o AGENTS.md i els docs del nucli{': ' + llista if llista else ''}.
2. Si el canvi toca més d'un mòdul, escriu el pla a `.nucli/pla-{id_}.md` abans de tocar codi.
3. Fes el canvi mínim. Commits Conventional Commits {idioma}, amb l'id al final: `tipus(àmbit): què ({id_})`. Tipus vàlids: {', '.join(cfg['commits']['tipus'])}. `git add` dels fitxers concrets, no `-A`.
4. Porta: `nucli ship plan` → `nucli ship run <check>` per a cada check automàtic que demani, excepte els marcats «fora del sandbox» (els passa nucli agent quan acabis) → `nucli ship seal`. Si un check falla, arregla el codi i torna'l a executar. No editis mai `.nucli/rebuts/`.
5. Si no pots acabar, escriu per què t'atures a `.nucli/atura-{id_}.md` i no facis commit de feina a mitges.

Mai: push, merge, deploy, canviar de branca, instal·lar res ni executar `nucli finish` (el llança una persona). No toquis `nucli.json`, `.claude/`, `.mcp.json` ni cap secret.

Acaba amb UNA frase que resumeixi què has canviat i què cal revisar."""


def comprova_previes(repo: Repo, args) -> tuple:
    cfg = repo.config()
    if repo.es_worktree:
        raise Plega(f"executa «nucli agent» al checkout principal ({repo.arrel})")
    if not ID_VALID.match(args.id):
        raise Plega(f"id no vàlid: «{args.id}» (només [a-z0-9-])")
    ref = repo.ref_base()
    if not repo.git_ok("cat-file", "-e", f"{ref}:nucli.json"):
        raise Plega(f"la base ({ref}) encara no té nucli.json: primer fusiona el commit de «nucli init»")
    an = permisos.analitza(repo.arrel, ref)
    if an.pendents():
        linies = "\n  ".join(permisos.resum_linies(an))
        raise Plega(
            f"no arrenco: els worktrees d'aquest repo no estan protegits ({len(an.pendents())} regla(es) pendents).\n  "
            f"{linies}\nProposta sencera: nucli init (la deixa a .nucli/proposta/permisos.md). Aplica-la al "
            f".claude/settings.json i fusiona-la a {ref}.")
    if shutil.which("claude") is None:
        raise Plega("no trobo «claude» al PATH")
    if (repo.arrel / ".claude" / "worktrees" / args.id).exists():
        raise Plega(f".claude/worktrees/{args.id} ja existeix: revisa'l, o treu'l amb «nucli neteja»")
    tasca = args.tasca or bloc_tasca(cfg, repo.arrel, args.id)
    if not tasca:
        on = cfg["tasques"]["fitxer"] if cfg.get("tasques") else "el fitxer de tasques (no n'hi ha a nucli.json)"
        raise Plega(f"cal --tasca \"text\" o un bloc «### {args.id} ·» a {on}")
    return cfg, ref, tasca


def ordre(args) -> int:
    repo = troba_repo()
    cfg, ref, tasca = comprova_previes(repo, args)
    torns = args.torns or cfg["agent"]["torns"]
    pressupost = args.pressupost or cfg["agent"]["pressupost_usd"]
    dir_agent = repo.arrel / ".nucli" / "agent"
    prepara_dir_nucli(repo.arrel / ".nucli")
    dir_agent.mkdir(parents=True, exist_ok=True)
    log, err = dir_agent / f"{args.id}.json", dir_agent / f"{args.id}.stderr.log"
    ordre_claude = [
        "claude", "-p", prompt(cfg, repo, args.id, tasca), "--worktree", args.id,
        "--permission-mode", "acceptEdits", "--strict-mcp-config",
        "--max-turns", str(torns), "--max-budget-usd", str(pressupost),
        "--output-format", "json", "--no-session-persistence",
        "--allowedTools", *EINES_PERMESES,
        "--disallowedTools", *eines_prohibides(cfg, repo.arrel, ref),
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    print(f"nucli agent · {args.id} · base {ref} · màx. {torns} torns i {pressupost} $ → {log.relative_to(repo.arrel)}", flush=True)
    with open(log, "w", encoding="utf-8") as sortida, open(err, "w", encoding="utf-8") as errors:
        codi = subprocess.run(ordre_claude, cwd=str(repo.arrel), env=env, stdout=sortida, stderr=errors).returncode

    wt = repo.arrel / ".claude" / "worktrees" / args.id
    resultat = {}
    try:
        resultat = json.loads(log.read_text(encoding="utf-8") or "{}")
    except ValueError:
        pass
    print(f"claude ha acabat amb codi {codi} · cost {resultat.get('total_cost_usd', '?')} $ · "
          f"{resultat.get('num_turns', '?')} torns")
    if resultat.get("result"):
        print(f"resum de l'agent: {str(resultat['result']).strip().splitlines()[-1][:300]}")
    segellat = False
    if wt.is_dir():
        subprocess.run(["git", "worktree", "unlock", str(wt)], cwd=str(repo.arrel), capture_output=True)
        segellat = despres(Repo(wt), cfg)
        atura = wt / ".nucli" / f"atura-{args.id}.md"
        if atura.is_file():
            print(f"L'agent s'ha aturat. Motiu ({atura.relative_to(repo.arrel)}):")
            print("  " + "\n  ".join(atura.read_text(encoding="utf-8").strip().splitlines()[:15]))
    else:
        print(f"no hi ha worktree a {wt.relative_to(repo.arrel)}: mira {err.relative_to(repo.arrel)}")
    print(f"revisa-ho i, si et va bé: cd .claude/worktrees/{args.id} && nucli finish")
    return 0 if codi == 0 and segellat else 1


def despres(repo_wt: Repo, cfg: dict) -> bool:
    """Passa els checks fora_sandbox requerits, torna a intentar segellar i ensenya l'estat del rebut."""
    try:
        pla = calcula_pla(repo_wt)
        branca = repo_wt.branca()
        fora = [c for c in pla.automatics(cfg) if cfg["checks"][c].get("fora_sandbox")]
        if fora:
            print(f"Checks fora del sandbox: {', '.join(fora)}")
            rebut = llegeix_rebut(repo_wt, branca)
            for c in fora:
                rebut["execucions"].append(executa_check(repo_wt, cfg, c, via="agent"))
                rebut["segell"] = None
            desa_rebut(repo_wt, rebut)
        ordre_seal(repo_wt)
        return True
    except Plega as e:
        print(f"rebut sense segell: {e}")
        return False
