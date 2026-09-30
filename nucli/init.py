"""`nucli init [--dry-run] [--adopta rol=camí]…`: prepara un repo sense tocar res del que ja hi ha.

Cada pas afegeix «accions» a una llista: primer es planifica tot, després s'imprimeix i, si no és --dry-run,
s'executen les que escriuen. Idempotent: una segona passada només troba «ja hi és».
"""
from __future__ import annotations

import difflib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import config, docs, permisos
from .comu import FITXER_CONFIG, Plega, Repo, prepara_dir_nucli
from .config import ROLS, cami_doc


@dataclass
class Accio:
    verb: str                                   # crea · adopta · proposa · afegeix · activa · ja hi és · avís
    objectiu: str
    detall: str = ""
    fes: Optional[Callable[[], None]] = None    # None: l'acció no escriu res
    extra: str = ""                             # text sota la línia (un diff, una llista)


class Context:
    def __init__(self, repo: Repo, dry_run: bool):
        self.repo = repo
        self.arrel = repo.arrel
        self.dry_run = dry_run
        self.accions = []
        self.cfg = None
        self.analisi = None

    def afegeix(self, *args, **kw) -> Accio:
        a = Accio(*args, **kw)
        self.accions.append(a)
        return a


DIR_PROPOSTA = "proposta"


def escriu_fitxer(cami: Path, text: str) -> Callable[[], None]:
    def _fes():
        cami.parent.mkdir(parents=True, exist_ok=True)
        cami.write_text(text, encoding="utf-8")
    return _fes


def _escriu_proposta(arrel: Path, nom: str, text: str) -> Callable[[], None]:
    def _fes():
        prepara_dir_nucli(arrel / ".nucli")
        dest = arrel / ".nucli" / DIR_PROPOSTA / nom
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return _fes


def diff(original: str, nou: str, de: str, a: str) -> str:
    linies = difflib.unified_diff(original.splitlines(), nou.splitlines(), fromfile=de, tofile=a, lineterm="", n=2)
    return "\n".join(linies)


# ---------- pas 1-4: docs, CLAUDE.md/AGENTS.md i nucli.json ----------

def llegeix_forcats(valors: list) -> dict:
    forcats = {}
    for v in valors:
        rol, sep, cami = v.partition("=")
        if not sep or rol not in ROLS or not cami:
            raise Plega(f"--adopta {v}: cal «rol=camí», amb rol entre {', '.join(ROLS)}")
        forcats[rol] = cami
    return forcats


def pas_docs(ctx: Context, forcats: dict) -> None:
    arrel = ctx.arrel
    for rol, valor in forcats.items():
        if not docs.te_seccio(arrel, valor):
            raise Plega(f"--adopta {rol}={valor}: no trobo aquest fitxer o aquesta secció")
    det = docs.detecta(arrel, forcats)
    cami_cfg = arrel / FITXER_CONFIG

    if cami_cfg.is_file():
        ctx.cfg = config.llegeix(cami_cfg)
        ctx.afegeix("ja hi és", FITXER_CONFIG, "no el toco; els rols dels docs surten d'aquí")
        if forcats:
            ctx.afegeix("avís", "--adopta", "nucli.json ja existeix i no el toco: canvia-hi els rols a mà")
        rols = {rol: ctx.cfg["docs"][rol] for rol in ROLS if ctx.cfg["docs"].get(rol)}
        rols = {rol: (v["cami"] if isinstance(v, dict) else v) for rol, v in rols.items()}
        nou = False
    else:
        rols = dict(det.rols)
        for rol in ROLS:
            rols.setdefault(rol, docs.CAMI_NOU[rol])
        ctx.cfg = config.completa(docs.config_nova(arrel, det, rols))
        nou = True

    for rol in ROLS:
        valor = rols.get(rol)
        if not valor:
            continue
        fitxer = cami_doc(valor)
        if "#" in valor:
            if docs.te_seccio(arrel, valor):
                ctx.afegeix("adopta" if nou else "ja hi és", f"{rol} → {valor}", "secció existent, no es toca")
            else:
                ctx.afegeix("avís", f"{rol} → {valor}", "aquesta secció no existeix: revisa nucli.json")
        elif (arrel / fitxer).is_file():
            extra = f" (format {det.format_decisions})" if rol == "decisions" and nou else ""
            ctx.afegeix("adopta" if nou else "ja hi és", f"{rol} → {fitxer}{extra}")
        else:
            punter = det.punters.get(rol)
            detall = f"apunta a {docs.descriu(punter)}, sense moure-hi res" if punter else "des de plantilla"
            ctx.afegeix("crea", fitxer, detall, fes=escriu_fitxer(arrel / fitxer, docs.plantilla_doc(rol, punter)))

    if nou:
        if det.adoptats:
            ctx.afegeix("adopta", "ids", " · ".join(f"{a['prefix']} → {a['cami']}" for a in det.adoptats))
        cfg_text = json.dumps(docs.config_nova(arrel, det, rols), indent=2, ensure_ascii=False) + "\n"
        checks = ctx.cfg["checks"]
        if checks:
            llista = "\n".join(
                f"{nom:<8} {c['ordre']}{'  (fora_sandbox)' if c.get('fora_sandbox') else ''}   ← REVISA"
                for nom, c in checks.items()
            )
        else:
            llista = "no he endevinat cap check: omple «checks» i «per_defecte» abans de fer servir la porta"
        ctx.afegeix("crea", FITXER_CONFIG, "amb el que he detectat; revisa'l abans del commit",
                    fes=escriu_fitxer(cami_cfg, cfg_text), extra=llista)

    pas_instruccions(ctx)


def pas_instruccions(ctx: Context) -> None:
    arrel, cfg = ctx.arrel, ctx.cfg
    claude, agents = arrel / "CLAUDE.md", arrel / "AGENTS.md"
    if not claude.exists() and not agents.exists():
        ctx.afegeix("crea", "AGENTS.md", "docs, cicle i «mai», per a tots els agents",
                    fes=escriu_fitxer(agents, docs.agents_nou(cfg)))
        ctx.afegeix("crea", "CLAUDE.md", "@AGENTS.md + el que és només de Claude", fes=escriu_fitxer(claude, docs.claude_nou()))
        return
    for cami, per_claude in ((claude, True), (agents, False)):
        if not cami.exists():
            continue
        if docs.te_bloc(cami):
            ctx.afegeix("ja hi és", cami.name, f"ja té el bloc «{docs.MARCA_BLOC[3:]}»")
            continue
        if per_claude and agents.exists() and docs.importa_agents(cami):
            ctx.afegeix("ja hi és", cami.name, "importa @AGENTS.md, on va el bloc «Nucli»")
            continue
        original = cami.read_text(encoding="utf-8")
        bloc = docs.bloc_nucli(cfg, per_claude)
        proposta = docs.amb_bloc(original, bloc)
        dest = arrel / ".nucli" / DIR_PROPOSTA / cami.name
        rel = dest.relative_to(arrel).as_posix()
        if dest.is_file() and dest.read_text(encoding="utf-8") == proposta:
            ctx.afegeix("ja hi és", rel, f"proposta per a {cami.name}")
            continue
        n = len(bloc.splitlines())
        ctx.afegeix("proposa", rel, f"el teu {cami.name} + un bloc «Nucli» de {n} línies al final; {cami.name} no es toca",
                    fes=_escriu_proposta(arrel, cami.name, proposta),
                    extra=diff(original, proposta, cami.name, rel))
    if agents.exists() and not claude.exists():
        ctx.afegeix("crea", "CLAUDE.md", "@AGENTS.md + el que és només de Claude", fes=escriu_fitxer(claude, docs.claude_nou()))
    if claude.exists() and not agents.exists():
        ctx.afegeix("avís", "AGENTS.md", "no existeix i no el creo: CLAUDE.md ja porta les instruccions. "
                    "Si fas servir Kimi o Codex, crea'l i deixa «@AGENTS.md» a CLAUDE.md")


# ---------- pas 5: el que s'afegeix sense tocar res més ----------

ENTRADES_GITIGNORE = [".nucli/", ".claude/worktrees/"]
REGLA_FINISH = "Bash(nucli finish:*)"
SETTINGS = ".claude/settings.json"


def pas_gitignore(ctx: Context) -> None:
    cami = ctx.arrel / ".gitignore"
    text = cami.read_text(encoding="utf-8") if cami.is_file() else ""
    linies = {l.strip() for l in text.splitlines()}
    falten = [e for e in ENTRADES_GITIGNORE
              if not {e, e.rstrip("/"), "/" + e, "/" + e.rstrip("/")} & linies]
    if not falten:
        ctx.afegeix("ja hi és", ".gitignore", ", ".join(ENTRADES_GITIGNORE))
        return
    nou = text + ("\n" if text and not text.endswith("\n") else "") + "# nucli\n" + "\n".join(falten) + "\n"
    ctx.afegeix("afegeix", ".gitignore", ", ".join(falten), fes=escriu_fitxer(cami, nou))


def pas_ask_finish(ctx: Context) -> None:
    """`nucli finish` sempre el llança una persona: si Claude l'intenta, et pregunta (i cap allow no ho salta)."""
    cami = ctx.arrel / SETTINGS
    text = cami.read_text(encoding="utf-8") if cami.is_file() else None
    try:
        if text and REGLA_FINISH in (json.loads(text).get("permissions", {}).get("deny") or []):
            ctx.afegeix("ja hi és", SETTINGS, f"{REGLA_FINISH} a deny (encara més estricte)")
            return
        nou = permisos.afegeix_regla(text, "ask", REGLA_FINISH)
    except (Plega, ValueError, AttributeError) as e:
        ctx.afegeix("avís", SETTINGS, f"no hi afegeixo {REGLA_FINISH}: {e}")
        return
    if nou is None:
        ctx.afegeix("ja hi és", SETTINGS, f"{REGLA_FINISH} a ask")
    else:
        ctx.afegeix("afegeix", SETTINGS, f"{REGLA_FINISH} a ask, i res més", fes=escriu_fitxer(cami, nou),
                    extra=diff(text or "", nou, SETTINGS, SETTINGS))


COMENTARI_WORKTREEINCLUDE = ("# nucli: aquí només hi va l'entorn de desenvolupament (.env.dev). "
                             "MAI l'.env de producció.\n")


def pas_worktreeinclude(ctx: Context) -> None:
    """Els fitxers ignorats que Claude Code copia a cada worktree nou. Si ja existeix, no el toca."""
    cami = ctx.arrel / ".worktreeinclude"
    if cami.exists():
        ctx.afegeix("ja hi és", ".worktreeinclude", "no el toco")
        return
    text = COMENTARI_WORKTREEINCLUDE
    detall = "només el comentari (no hi ha .env.dev)"
    if (ctx.arrel / ".env.dev").is_file():
        text += ".env.dev\n"
        detall = ".env.dev"
    ctx.afegeix("crea", ".worktreeinclude", detall, fes=escriu_fitxer(cami, text))


def pas_permisos_worktrees(ctx: Context) -> None:
    """§7.1: proposa (mai aplica) les regles que falten perquè els worktrees quedin tan protegits com el checkout."""
    base = ctx.cfg["branca_base"]
    ref = f"origin/{base}" if ctx.repo.git_ok("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{base}") else base
    an = permisos.analitza(ctx.arrel, ref)
    ctx.analisi = an
    for a in an.avisos:
        ctx.afegeix("avís", "permisos", a)
    if not an.propostes:
        ctx.afegeix("ja hi és", "permisos dels worktrees", "cap regla ancorada al checkout principal sense cobrir")
        return
    text = permisos.text_proposta(an, ctx.arrel)
    dest = ctx.arrel / ".nucli" / DIR_PROPOSTA / "permisos.md"
    rel = dest.relative_to(ctx.arrel).as_posix()
    extra = "\n".join(permisos.resum_linies(an))
    if dest.is_file() and dest.read_text(encoding="utf-8") == text:
        ctx.afegeix("ja hi és", rel, f"{len(an.pendents())} regla(es) de permisos pendents", extra=extra)
    else:
        ctx.afegeix("proposa", rel, f"{len(an.pendents())} regla(es) de permisos per als worktrees, sense aplicar-les",
                    fes=_escriu_proposta(ctx.arrel, "permisos.md", text), extra=extra)


GITHOOKS = Path(__file__).resolve().parent.parent / "githooks"


def _es_de_nucli(cami: str) -> bool:
    """Un core.hooksPath que apunta a uns githooks del nucli (encara que el clon s'hagi mogut)."""
    p = Path(cami)
    if p.name != "githooks":
        return False
    hook = p / "pre-push"
    return not p.exists() or (hook.is_file() and "nucli githook" in hook.read_text(encoding="utf-8", errors="ignore"))


def pas_hookspath(ctx: Context) -> None:
    desti = str(GITHOOKS)
    local = ctx.repo.git("config", "--local", "--get", "core.hooksPath", check=False)
    global_ = ctx.repo.git("config", "--global", "--get", "core.hooksPath", check=False)
    if local == desti:
        ctx.afegeix("ja hi és", "core.hooksPath", desti)
        return
    if local and not _es_de_nucli(local):
        ctx.afegeix("avís", "core.hooksPath", f"el repo ja en té un ({local}): no el trepitjo; els hooks del nucli no "
                    "s'activen. Crida'ls des dels teus hooks si els vols")
        return
    if not local and global_:
        ctx.afegeix("avís", "core.hooksPath", f"tens un core.hooksPath global ({global_}): no el tapo; els hooks del "
                    "nucli no s'activen en aquest repo")
        return

    def _fes():
        ctx.repo.git("config", "--local", "core.hooksPath", desti)
    detall = f"{desti} (abans {local}: el nucli s'ha mogut)" if local else desti
    ctx.afegeix("activa", "core.hooksPath", detall, fes=_fes)


ALLOWS_SHIP = ["Bash(nucli ship plan)", "Bash(nucli ship run:*)", "Bash(nucli ship seal)", "Bash(nucli port)",
               "Bash(nucli usage)"]


def _settings(ctx: Context) -> list:
    """Les dades del settings.json i el settings.local.json del projecte i del teu ~/.claude/settings.json."""
    fonts = [ctx.arrel / SETTINGS, ctx.arrel / ".claude/settings.local.json", Path.home() / ".claude/settings.json"]
    dades = []
    for f in fonts:
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        except ValueError:
            d = {}
        dades.append(d if isinstance(d, dict) else {})
    return dades


def _regles(dades: list, llista: str) -> set:
    return {r for d in dades for r in (((d.get("permissions") or {}).get(llista)) or [])}


def pas_allows_ship(ctx: Context) -> None:
    """Sense sandbox, Claude et preguntaria cada `nucli ship`: te'n proposa els allow (no els aplica mai)."""
    dades = _settings(ctx)
    if any(isinstance(d.get("sandbox"), dict) and d["sandbox"].get("enabled") for d in dades):
        ctx.afegeix("ja hi és", "allow de nucli ship", "amb el sandbox actiu, autoAllowBashIfSandboxed ja els aprova")
        return
    tenim = _regles(dades, "allow")
    falten = [r for r in ALLOWS_SHIP if r not in tenim]
    if not falten:
        ctx.afegeix("ja hi és", "allow de nucli ship", ", ".join(ALLOWS_SHIP))
        return
    text = ("# Allow per a nucli ship (proposta de `nucli init`, no aplicada)\n\n"
            "Aquest repo no té el sandbox actiu. Si vols que Claude no et pregunti cada `nucli ship`, afegeix això a "
            "`permissions.allow` de `.claude/settings.json`. `ship run` només executa les ordres del `nucli.json` del "
            "checkout principal. `nucli finish` es queda a `ask`.\n\n"
            + "".join(f"    \"{r}\",\n" for r in falten))
    dest = ctx.arrel / ".nucli" / DIR_PROPOSTA / "allow.md"
    rel = dest.relative_to(ctx.arrel).as_posix()
    if dest.is_file() and dest.read_text(encoding="utf-8") == text:
        ctx.afegeix("ja hi és", rel, "proposta d'allow per a nucli ship")
        return
    ctx.afegeix("proposa", rel, "repo sense sandbox: allow per a nucli ship, sense aplicar-los",
                fes=_escriu_proposta(ctx.arrel, "allow.md", text), extra="\n".join(falten))


DENY_SECRET = "Bash(nucli secret:*)"


def pas_deny_secret(ctx: Context) -> None:
    """`nucli secret` només la llança una persona: te'n proposa la regla deny perquè Claude ni ho intenti (v0.1.3)."""
    if {DENY_SECRET, "Bash(nucli secret *)"} & _regles(_settings(ctx), "deny"):
        ctx.afegeix("ja hi és", "deny de nucli secret", DENY_SECRET)
        return
    text = ("# Deny per a nucli secret (proposta de `nucli init`, no aplicada)\n\n"
            "`nucli secret` desa a GitHub un valor del `.env` i només la pot llançar una persona, al terminal. Ja plega "
            "sola si detecta que corre dins de Claude Code; amb aquesta regla, Claude ni tan sols ho intenta. Afegeix "
            "això a `permissions.deny` de `.claude/settings.json` (o del teu `~/.claude/settings.json`, i valdrà per a "
            "tots els repos):\n\n"
            f"    \"{DENY_SECRET}\",\n")
    dest = ctx.arrel / ".nucli" / DIR_PROPOSTA / "deny.md"
    rel = dest.relative_to(ctx.arrel).as_posix()
    if dest.is_file() and dest.read_text(encoding="utf-8") == text:
        ctx.afegeix("ja hi és", rel, "proposta de deny per a nucli secret")
        return
    ctx.afegeix("proposa", rel, f"{DENY_SECRET} a deny, sense aplicar-la",
                fes=_escriu_proposta(ctx.arrel, "deny.md", text))


PASSOS = [pas_gitignore, pas_worktreeinclude, pas_ask_finish, pas_allows_ship, pas_deny_secret, pas_hookspath,
          pas_permisos_worktrees]


def avis_worktrees(an) -> str:
    return (
        f"⚠ WORKTREES NO PROTEGITS en aquest repo: {len(an.pendents())} regla(es) de permisos pendents "
        "(.nucli/proposta/permisos.md).\n"
        f"  Mentre no siguin al .claude/settings.json de {an.ref_base} (o al .claude/settings.local.json del checkout "
        "principal, o al teu ~/.claude/settings.json):\n"
        "  - no facis servir claude --worktree ni subagents amb «isolation: worktree» en aquest repo;\n"
        "  - nucli agent es nega a arrencar."
    )


def imprimeix(ctx: Context) -> None:
    print(f"nucli init · {ctx.arrel}" + ("  (--dry-run: no s'escriu res)" if ctx.dry_run else ""))
    for a in ctx.accions:
        linia = f"  {a.verb:<9} {a.objectiu}"
        if a.detall:
            linia += f" · {a.detall}"
        print(linia)
        if a.extra:
            for l in a.extra.splitlines():
                print(f"              {l}")
    canvis = [a for a in ctx.accions if a.fes]
    propostes = [a for a in ctx.accions if a.verb == "proposa"]
    avisos = [a for a in ctx.accions if a.verb == "avís"]
    if not canvis:
        print("Res a fer: tot ja hi és.")
    else:
        temps = "faria" if ctx.dry_run else "he fet"
        print(f"Resum: {temps} {len(canvis)} canvi(s), dels quals {len(propostes)} proposta(es) a .nucli/proposta/. "
              "Cap fitxer existent no s'ha modificat.")
    if avisos:
        print(f"Avisos: {len(avisos)}. Llegeix-los a dalt.")
    if canvis and not ctx.dry_run:
        print("No he fet cap commit: revisa-ho i fes-lo tu.")
    if ctx.analisi is not None and ctx.analisi.pendents():
        print()
        print(avis_worktrees(ctx.analisi))


def ordre(args) -> int:
    repo = Repo(os.getcwd())
    if repo.es_worktree:
        raise Plega(f"executa «nucli init» al checkout principal ({repo.arrel}), no en un worktree")
    ctx = Context(repo, args.dry_run)
    pas_docs(ctx, llegeix_forcats(args.adopta))
    for pas in PASSOS:
        pas(ctx)
    imprimeix(ctx)
    if not ctx.dry_run:
        for a in ctx.accions:
            if a.fes:
                a.fes()
    return 0
