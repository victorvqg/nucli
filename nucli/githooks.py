"""Hooks de git del nucli (els activa `nucli init` amb core.hooksPath → githooks/ d'aquest repo).

Primer criden el hook propi del repo (.git/hooks/<nom>) si n'hi ha. Sense nucli.json al checkout principal no
fan res més. Les sortides d'emergència (NUCLI_MAIN=1, NUCLI_IDIOMA=0) s'anoten a ~/.nucli/excepcions.jsonl, i si
no es poden anotar (per exemple, dins del sandbox) no es concedeixen.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .comu import git, repo_amb_nucli
from .config import issue_de_branca, prefixos_tasques
from .ship import ara

ZERO = "0" * 40
ACCEPTATS_GIT = ("Merge ", "Revert \"", "fixup! ", "squash! ", "amend! ")

ANGLES = {"the", "and", "with", "add", "adds", "added", "fix", "fixes", "fixed", "remove", "removes", "removed",
          "update", "updates", "updated", "use", "uses", "for", "from", "to", "in", "of", "when", "new", "into", "is",
          "are", "was", "this", "that", "it", "by", "support", "change", "changes", "make", "makes", "move", "rename",
          "delete", "improve", "handle", "allow", "create", "get", "only", "not", "instead", "missing", "wrong", "after",
          "before", "should", "now"}
CASTELLA = {"los", "las", "con", "para", "añade", "añadir", "añadido", "corrige", "corregir", "y", "pero", "cuando",
            "sin", "más", "está", "esta", "esto", "este", "nuevo", "nueva", "ahora", "también", "porque", "hay", "muy",
            "cambia", "cambiar", "quita", "quitar", "hacer", "desde", "por", "sus", "su", "datos", "fecha", "usuario",
            "lo", "ya", "siempre", "nunca", "cuál", "qué"}
CATALA = {"amb", "els", "per", "dels", "pels", "i", "què", "perquè", "quan", "sense", "més", "ja", "també", "ara",
          "nou", "nova", "afegeix", "treu", "canvia", "mostra", "cal", "fa", "fer", "és", "són", "hi", "ho", "l", "d",
          "s", "n", "m", "t", "aquest", "aquesta", "com", "on", "mai", "sempre", "encara", "abans", "després", "puja",
          "surt", "queda"}


def _hook_propi(nom: str, args: list, entrada: bytes) -> int:
    """Crida .git/hooks/<nom> del repo si existeix i és executable. Torna el seu codi (0 si no n'hi ha)."""
    comu = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                          capture_output=True, text=True)
    if comu.returncode != 0:
        return 0
    propi = Path(comu.stdout.strip()) / "hooks" / nom
    if not (propi.is_file() and os.access(propi, os.X_OK)):
        return 0
    return subprocess.run([str(propi), *args], input=entrada).returncode


def anota_excepcio(dades: dict) -> bool:
    try:
        d = Path(os.path.expanduser("~")) / ".nucli"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "excepcions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(dict({"data": ara()}, **dades), ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


# ---------- pre-push ----------

def pre_push(repo, entrada: str) -> int:
    base = repo.config()["branca_base"]
    desti = f"refs/heads/{base}"
    bloquejats = []
    for linia in entrada.splitlines():
        parts = linia.split()
        if len(parts) == 4 and parts[2] == desti:
            bloquejats.append(parts)
    if not bloquejats:
        return 0
    if os.environ.get("NUCLI_MAIN") == "1":
        for local_ref, local_sha, _, _ in bloquejats:
            dades = {"tipus": "main", "repo": repo.arrel.name, "branca": base, "sha": local_sha,
                     "esborra": local_sha == ZERO}
            if not anota_excepcio(dades):
                print("nucli: no puc anotar l'excepció a ~/.nucli/excepcions.jsonl: no la concedeixo", file=sys.stderr)
                return 1
        print(f"nucli: push a {base} amb NUCLI_MAIN=1: excepció anotada a ~/.nucli/excepcions.jsonl", file=sys.stderr)
        return 0
    esborra = any(p[1] == ZERO for p in bloquejats)
    que = f"esborrar {base}" if esborra else f"pujar directament a {base}"
    print(f"nucli: no es pot {que}. Puja una branca i obre un PR (nucli finish).\n"
          f"Si de debò cal, sortida d'emergència (queda anotada): NUCLI_MAIN=1 git push …", file=sys.stderr)
    return 1


# ---------- commit-msg ----------

def assumpte(text: str) -> str:
    for linia in text.splitlines():
        if linia.strip() and not linia.startswith("#"):
            return linia.strip()
    return ""


def id_de_branca(branca: str, prefixos: list, cfg: dict = None):
    """L'id de la tasca de la branca: `#N` si és d'un issue (`issue/N-…`, `worktree-issue-N`), i si no, el primer
    `<prefix><n>` (`worktree-mt12`, `mt/mt12` → `mt12`). L'issue va primer: `issue/12-arregla-mt3` → `#12`."""
    n = issue_de_branca(branca, cfg or {})
    if n is not None:
        return f"#{n}"
    for p in prefixos:
        m = re.search(rf"(?:^|[/-])({re.escape(p)}\d+)(?:$|[/-])", branca)
        if m:
            return m.group(1)
    return None


def paraules_estrangeres(descripcio: str):
    """(estrangeres, catalanes, total) d'una descripció, sense els trossos entre `."""
    net = re.sub(r"`[^`]*`", " ", descripcio)
    net = re.sub(r"\([a-z]+\d+\)", " ", net)
    net = re.sub(r"\(#\d+\)", " ", net)
    paraules = [p for p in re.split(r"[^\wàèéíïòóúüç·ñ]+", net.lower()) if p and not p.isdigit()]
    estrangeres = [p for p in paraules if p in ANGLES or p in CASTELLA]
    catalanes = [p for p in paraules if p in CATALA]
    return estrangeres, catalanes, len(paraules)


def commit_msg(repo, cami_missatge: str) -> int:
    cfg = repo.config()
    text = Path(cami_missatge).read_text(encoding="utf-8", errors="replace")
    subj = assumpte(text)
    if not subj or subj.startswith(ACCEPTATS_GIT):
        return 0
    tipus = cfg["commits"]["tipus"]
    m = re.match(rf"^({'|'.join(map(re.escape, tipus))})(\([^)]+\))?!?: (.+)$", subj)
    errors = []
    if not m:
        errors.append(f"l'assumpte ha de ser «tipus(àmbit): què», amb tipus entre: {', '.join(tipus)}")
    branca = git("rev-parse", "--abbrev-ref", "HEAD", cwd=os.getcwd(), check=False)
    id_ = id_de_branca(branca, prefixos_tasques(cfg) or [], cfg) if branca and branca != "HEAD" else None
    if id_ and id_.startswith("#"):
        # d'un issue, només val al final de l'assumpte: un «Closes #3» al cos no pot passar per l'id
        if not subj.endswith(f" ({id_})"):
            errors.append(f"la branca {branca} és de l'issue {id_}: l'assumpte ha d'acabar en « ({id_})»")
    elif id_ and not re.search(rf"(?<![A-Za-z0-9]){re.escape(id_)}(?![0-9])", text):
        errors.append(f"la branca {branca} és de la tasca {id_}: el missatge l'ha de contenir, p. ex. «… ({id_})»")
    if m and cfg.get("idioma", "ca") == "ca":
        estrangeres, catalanes, total = paraules_estrangeres(m.group(3))
        if total >= 3 and len(estrangeres) > len(catalanes):
            if os.environ.get("NUCLI_IDIOMA") == "0":
                if not anota_excepcio({"tipus": "idioma", "repo": repo.arrel.name, "branca": branca, "missatge": subj}):
                    print("nucli: no puc anotar l'excepció a ~/.nucli/excepcions.jsonl: no la concedeixo", file=sys.stderr)
                    return 1
                print("nucli: NUCLI_IDIOMA=0: excepció d'idioma anotada", file=sys.stderr)
            else:
                errors.append(f"l'assumpte no sembla en català (he vist: {', '.join(estrangeres)}). "
                              "Si és un fals positiu: NUCLI_IDIOMA=0 git commit …")
    if errors:
        print("nucli: missatge de commit rebutjat:\n  - " + "\n  - ".join(errors) + f"\n  assumpte: {subj}", file=sys.stderr)
        return 1
    return 0


def ordre(args) -> int:
    entrada = b"" if sys.stdin.isatty() else sys.stdin.buffer.read()
    codi = _hook_propi(args.nom, args.args, entrada)
    if codi != 0:
        return codi
    repo = repo_amb_nucli(os.getcwd())
    if repo is None:
        return 0
    if args.nom == "pre-push":
        return pre_push(repo, entrada.decode("utf-8", "replace"))
    if not args.args:
        return 0
    return commit_msg(repo, args.args[0])
