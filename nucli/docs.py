"""Docs del nucli: detecció del que el repo ja té, plantilles per al que falta i el bloc «Nucli».

No mou, no renomena i no reescriu res: només llegeix, i diu a `init` què crear i què proposar.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Optional

from .config import ROLS, TIPUS_COMMIT, cami_doc

PLANTILLES = Path(__file__).resolve().parent.parent / "plantilles"

# Noms de fitxer (sense extensió, en minúscules i sense accents) que delaten cada rol.
NOMS_FITXER = {
    "estat": {"estat", "estado", "status", "state"},
    "decisions": {"decisions", "decisiones", "adr", "adrs"},
    "trampes": {"trampes", "trampas", "gotchas", "pitfalls", "llicons", "lessons"},
    "convencions": {"convencions", "convenciones", "conventions"},
    "arquitectura": {"arquitectura", "architecture"},
}
# Títols de secció H2 equivalents (normalitzats: sense numeració, sense accents, en minúscules).
NOMS_SECCIO = {
    "estat": {"estat", "estat actual", "estado", "status"},
    "decisions": {"decisions", "decisiones"},
    "trampes": {"trampes", "llicons apreses", "lecciones aprendidas", "lessons learned", "gotchas"},
    "convencions": {"convencions", "convenciones", "conventions"},
    "arquitectura": {"arquitectura", "architecture"},
}
# Els rols que poden viure en una secció d'un altre fitxer. La resta sempre són fitxers propis (P2).
ROLS_SECCIO = {"convencions", "arquitectura"}
NOMS_TASQUES = {"tasques", "tareas", "tasks", "todo"}
CAMI_NOU = {rol: f"docs/{rol.upper()}.md" for rol in ROLS}
CAP_ID = re.compile(r"^### ([a-z]+)(\d+) ·", re.M)
CAP_DATA = re.compile(r"^## \d{4}-\d{2}-\d{2}", re.M)
CAP_ADR = re.compile(r"^## ADR-\d+", re.M)
MARCA_BLOC = "## Nucli"


def normalitza(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()
    t = re.sub(r"^\d+[.)]\s*", "", t)  # «2. Arquitectura…» → «arquitectura…»
    return re.split(r"[:(·—-]", t, maxsplit=1)[0].strip()


def coincideix_nom(nom: str, noms: set) -> bool:
    """El títol és un dels noms, o hi comença seguit d'una paraula («estat actual i pla» → «estat actual»)."""
    return any(nom == n or nom.startswith(n + " ") for n in noms)


def seccions_h2(cami: Path) -> list:
    if not cami.is_file():
        return []
    return [l[3:].strip() for l in cami.read_text(encoding="utf-8").splitlines() if l.startswith("## ")]


def te_seccio(arrel: Path, valor: str) -> bool:
    fitxer, _, seccio = valor.partition("#")
    if not (arrel / fitxer).is_file():
        return False
    return not seccio or seccio in seccions_h2(arrel / fitxer)


def _mds(arrel: Path) -> list:
    """Els .md de l'arrel i de docs/ (un nivell), en ordre estable."""
    out = []
    for d in (arrel, arrel / "docs"):
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".md")
    return out


class Deteccio:
    """El que `init` ha trobat al repo, rol per rol."""

    def __init__(self):
        self.rols = {}          # rol → camí o «fitxer#Secció» adoptat
        self.punters = {}       # rol → «fitxer#Secció» equivalent, quan el rol ha de ser un fitxer propi
        self.format_decisions = "adr"
        self.adoptats = []      # [{"cami", "prefix"}]
        self.tasques = None     # {"fitxer", "prefix"}


def detecta(arrel: Path, forcats: Optional[dict] = None) -> Deteccio:
    d = Deteccio()
    mds = _mds(arrel)
    for p in mds:
        nom = normalitza(p.stem)
        for rol, noms in NOMS_FITXER.items():
            if nom in noms and rol not in d.rols:
                d.rols[rol] = p.relative_to(arrel).as_posix()
    for fitxer in ("CLAUDE.md", "AGENTS.md"):
        for titol in seccions_h2(arrel / fitxer):
            nom = normalitza(titol)
            for rol, noms in NOMS_SECCIO.items():
                if coincideix_nom(nom, noms) and rol not in d.rols:
                    if rol in ROLS_SECCIO:
                        d.rols[rol] = f"{fitxer}#{titol}"
                    else:
                        d.punters.setdefault(rol, f"{fitxer}#{titol}")
    for rol, valor in (forcats or {}).items():
        d.rols[rol] = valor
        d.punters.pop(rol, None)
    if "decisions" in d.rols:
        d.format_decisions = format_decisions(arrel / cami_doc(d.rols["decisions"]))
    for p in mds:
        prefix = prefix_dominant(p)
        if prefix:
            rel = p.relative_to(arrel).as_posix()
            d.adoptats.append({"cami": rel, "prefix": prefix})
            if d.tasques is None and normalitza(p.stem) in NOMS_TASQUES:
                d.tasques = {"fitxer": rel, "prefix": prefix}
    return d


def prefix_dominant(cami: Path) -> Optional[str]:
    """El prefix d'id d'un doc amb 3 o més encapçalaments «### <prefix><n> ·», o None."""
    try:
        comptes = Counter(m.group(1) for m in CAP_ID.finditer(cami.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError):
        return None
    if not comptes:
        return None
    prefix, n = comptes.most_common(1)[0]
    return prefix if n >= 3 else None


def format_decisions(cami: Path) -> str:
    if not cami.is_file():
        return "adr"
    text = cami.read_text(encoding="utf-8")
    return "data" if len(CAP_DATA.findall(text)) > len(CAP_ADR.findall(text)) else "adr"


def descriu(valor) -> str:
    """«CLAUDE.md#Convencions» → «`CLAUDE.md` § Convencions»."""
    valor = valor["cami"] if isinstance(valor, dict) else valor
    fitxer, _, seccio = valor.partition("#")
    return f"`{fitxer}` § {seccio}" if seccio else f"`{fitxer}`"


def plantilla_doc(rol: str, punter: Optional[str]) -> str:
    text = (PLANTILLES / f"{rol.upper()}.md").read_text(encoding="utf-8")
    linia = ""
    if punter:
        linia = f"\nHi ha contingut anterior a {descriu(punter)}. No s'ha mogut: les entrades noves van aquí.\n"
    return text.replace("{punter}", linia)


# ---------- bloc «Nucli» per a CLAUDE.md i AGENTS.md ----------

def _frase_docs(cfg: dict) -> str:
    noms = {"estat": "estat", "decisions": "decisions", "trampes": "trampes",
            "convencions": "convencions", "arquitectura": "arquitectura"}
    docs = cfg.get("docs", {})
    frase = "Aquest repo fa servir el nucli (`nucli.json`: checks, regles i commits)."
    parts = [f"{noms[rol]} {descriu(docs[rol])}" for rol in ROLS if docs.get(rol)]
    if parts:
        frase += " Docs: " + " · ".join(parts) + "."
    adoptats = docs.get("adoptats") or []
    if adoptats:
        ids = ", ".join(f"`{a['prefix']}N` a `{a['cami']}`" for a in adoptats)
        frase += f" Ids fixos i mai reutilitzats ({ids}): un id nou és el màxim del fitxer + 1."
    return frase


def bloc_nucli(cfg: dict, per_claude: bool) -> str:
    idioma = "en català" if cfg.get("idioma", "ca") == "ca" else f"en l'idioma «{cfg['idioma']}»"
    linies = [
        MARCA_BLOC,
        "",
        _frase_docs(cfg),
        "",
        "Cicle de cada canvi: llegeix els docs i la tasca → si toca més d'un mòdul, pla a `.nucli/pla-<id>.md` abans del codi → "
        f"canvi mínim, amb commits `tipus(àmbit): què (<id>)` {idioma} → `nucli ship plan` → `nucli ship run <check>` per a "
        "cada check automàtic → `nucli ship seal`. Si no pots acabar, escriu per què a `.nucli/atura-<id>.md` i no facis "
        "commit de feina a mitges.",
        "",
        "Mai: push, merge, deploy ni `nucli finish` (el llança una persona). No editis `.nucli/rebuts/`, `nucli.json` ni "
        "`.claude/` per passar la porta.",
    ]
    if per_claude:
        linies += ["", "Només per a Claude Code: " + " · ".join(linies_claude())]
    return "\n".join(linies) + "\n"


def linies_claude() -> list:
    return [
        "worktrees amb `claude --worktree <id>` només si `nucli init` no avisa de permisos pendents",
        "`nucli finish` no el llancis tu: el fa l'usuari al terminal o amb `!`",
        "per tancar o pausar la sessió, la skill `tanca-sessio`.",
    ]


def agents_nou(cfg: dict) -> str:
    return (PLANTILLES / "AGENTS.md").read_text(encoding="utf-8").replace("{bloc}", bloc_nucli(cfg, per_claude=False))


def claude_nou() -> str:
    linies = "\n".join(f"- {l[0].upper()}{l[1:].rstrip('.')}." for l in linies_claude())
    return (PLANTILLES / "CLAUDE.md").read_text(encoding="utf-8").replace("{claude}", linies)


def te_bloc(cami: Path) -> bool:
    return cami.is_file() and any(l.strip() == MARCA_BLOC for l in cami.read_text(encoding="utf-8").splitlines())


def importa_agents(cami: Path) -> bool:
    return any(l.strip() == "@AGENTS.md" for l in cami.read_text(encoding="utf-8").splitlines())


def amb_bloc(text: str, bloc: str) -> str:
    return text.rstrip("\n") + "\n\n" + bloc


# ---------- nucli.json endevinat ----------

def endevina_checks(arrel: Path) -> dict:
    """Ordres de check endevinades a partir dels fitxers del repo. Totes s'han de revisar."""
    checks = {}
    py = '"$NUCLI_ARREL/.venv/bin/python"' if (arrel / ".venv" / "bin" / "python").exists() else "python3"
    pkg = {}
    if (arrel / "package.json").is_file():
        try:
            pkg = json.loads((arrel / "package.json").read_text(encoding="utf-8")).get("scripts", {}) or {}
        except (ValueError, OSError):
            pkg = {}

    for cand in ("scripts/check.sh", "check.sh", "scripts/lint.sh"):
        if (arrel / cand).is_file():
            checks["lint"] = {"ordre": f"bash {cand}"}
            break
    else:
        if "lint" in pkg:
            checks["lint"] = {"ordre": "npm run lint"}

    pytest = any((arrel / f).is_file() for f in ("pytest.ini", "conftest.py")) or (
        (arrel / "pyproject.toml").is_file() and "[tool.pytest" in (arrel / "pyproject.toml").read_text(encoding="utf-8")
    )
    dirs_tests = [p for p in [arrel / "tests", *sorted(arrel.glob("*/tests"))]
                  if p.is_dir() and any(p.glob("test_*.py")) and ".venv" not in p.parts]
    if pytest:
        checks["test"] = {"ordre": f"{py} -m pytest -q"}
    elif dirs_tests:
        pare = dirs_tests[0].parent
        cd = "" if pare == arrel else f"cd {pare.relative_to(arrel).as_posix()} && "
        checks["test"] = {"ordre": f"{cd}{py} -m unittest discover -s tests"}
    elif pkg.get("test") and "no test specified" not in pkg["test"]:
        checks["test"] = {"ordre": "npm test"}

    for cand in ("scripts/smoke.py", "smoke.py"):
        p = arrel / cand
        if p.is_file():
            c = {"ordre": f"{py} {cand}"}
            if re.search(r"playwright|selenium|puppeteer", p.read_text(encoding="utf-8", errors="ignore")):
                c["fora_sandbox"] = True  # els navegadors no arrenquen dins del sandbox de Claude Code
            checks["smoke"] = c
            break
    return checks


def branca_base(arrel: Path) -> str:
    from .comu import git

    ref = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", cwd=arrel, check=False)
    if ref.startswith("refs/remotes/origin/"):
        return ref[len("refs/remotes/origin/"):]
    actual = git("rev-parse", "--abbrev-ref", "HEAD", cwd=arrel, check=False)
    return actual if actual in ("main", "master") else "main"


def config_nova(arrel: Path, det: Deteccio, rols: dict) -> dict:
    checks = endevina_checks(arrel)
    docs = {}
    for rol in ROLS:
        if rol in rols:
            docs[rol] = {"cami": rols[rol], "format": det.format_decisions} if rol == "decisions" else rols[rol]
    if det.adoptats:
        docs["adoptats"] = det.adoptats
    cfg = {"versio": 1, "idioma": "ca", "branca_base": branca_base(arrel), "docs": docs}
    if det.tasques:
        cfg["tasques"] = det.tasques
    cfg.update({
        "checks": checks,
        "regles": [{"patrons": ["*.md", "docs/**"], "checks": []}],
        "per_defecte": [n for n, c in checks.items() if "ordre" in c],
        "commits": {"tipus": TIPUS_COMMIT},
        "agent": {"torns": 60, "pressupost_usd": 7, "prohibides": []},
    })
    return cfg
