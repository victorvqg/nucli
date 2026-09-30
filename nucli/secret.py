"""`nucli secret NOM --env ENTORN [--des-de NOM_AL_ENV]`: desa a GitHub un valor del .env sense ensenyar-lo.

Només la llança una persona, al terminal: sense terminal, o si detecta que corre dins de Claude Code, plega abans de
llegir res. Llegeix el .env del checkout principal com les eines habituals (python-dotenv, docker compose): treu els
comentaris en línia, els espais i les cometes. Comprova que el valor no sigui buit i que només tingui ASCII
imprimible, n'ensenya la longitud (i els 10 primers caràcters només si comença per un prefix conegut), demana
confirmació [s/N] i fa `gh secret set NOM --env ENTORN` amb el valor per stdin. Mai no imprimeix el valor.

Motiu (v0.1.3): al marcador, copiar la clau del .env amb `cut` hi va enganxar un comentari amb una «é».
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from .comu import Plega, troba_repo

# Variables que Claude Code posa a l'entorn de les ordres que llança.
VARIABLES_CLAUDE = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
# Prefixos que no són secrets: els 10 primers caràcters no diuen res de la clau.
PREFIXOS_CONEGUTS = ("sb_secret_", "sb_publishable_", "eyJ")
MOSTRA = 10

NOM_GITHUB = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CLAU_ENV = r"[A-Za-z_][A-Za-z0-9_.-]*"
LINIA = re.compile(rf"^\s*(?:export\s+)?({CLAU_ENV})\s*=(.*)$")
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}


def valor_del_env(text: str, clau: str) -> tuple:
    """(valor, línia, vegades) de l'última assignació de `clau`, o (None, 0, 0) si no hi és.

    Com python-dotenv: `export` opcional, espais al voltant de l'«=», cometes simples o dobles (amb \\" i \\n a les
    dobles) i comentaris en línia (un «#» després d'un espai, o al principi del valor). L'última assignació mana.
    """
    trobat, linia_trobada, vegades = None, 0, 0
    for n, linia in enumerate(text.removeprefix("\ufeff").split("\n"), 1):
        m = LINIA.match(linia.rstrip("\r"))
        if not m or m.group(1) != clau:
            continue
        trobat, linia_trobada, vegades = _valor(m.group(2), n), n, vegades + 1
    return trobat, linia_trobada, vegades


def _valor(cru: str, n: int) -> str:
    cru = cru.lstrip(" \t")
    if cru[:1] not in ("'", '"'):
        return re.sub(r"(?:^|\s)#.*", "", cru).strip(" \t")
    cometa, out, i = cru[0], [], 1
    while i < len(cru):
        c = cru[i]
        if c == "\\" and i + 1 < len(cru) and (cru[i + 1] in (cometa, "\\") or cometa == '"' and cru[i + 1] in ESCAPES):
            out.append(ESCAPES[cru[i + 1]] if cometa == '"' else cru[i + 1])
            i += 2
            continue
        if c == cometa:
            resta = cru[i + 1:].strip(" \t")
            if resta and not resta.startswith("#"):
                raise Plega(f"línia {n} del .env: hi ha text després de la cometa que tanca el valor. No he desat res")
            return "".join(out)
        out.append(c)
        i += 1
    raise Plega(f"línia {n} del .env: la cometa no es tanca a la mateixa línia (els valors de més d'una línia no "
                "s'accepten). No he desat res")


def problemes_del_valor(valor: str) -> list:
    """Les posicions (1..n) dels caràcters que no són ASCII imprimible, amb el tipus. Mai el caràcter."""
    out = []
    for i, c in enumerate(valor, 1):
        if not " " <= c <= "~":
            out.append(f"posició {i} ({'no ASCII' if ord(c) > 127 else 'caràcter de control'})")
    return out


def descriu(valor: str) -> str:
    """La longitud i, només si comença per un prefix conegut, els 10 primers caràcters."""
    if valor.startswith(PREFIXOS_CONEGUTS):
        return f"{len(valor)} caràcters · comença per «{valor[:MOSTRA]}»"
    return f"{len(valor)} caràcters · no comença per cap prefix conegut, i no n'ensenyo res"


def comprova_persona() -> None:
    detectades = [v for v in VARIABLES_CLAUDE if os.environ.get(v)]
    if detectades:
        raise Plega(f"nucli secret només la llança una persona, al terminal, i aquí corre dins de Claude Code "
                    f"({', '.join(detectades)}). No he llegit res")
    if not sys.stdin.isatty():
        raise Plega("nucli secret només la llança una persona i cal un terminal per confirmar-ho. No he llegit res")


def ordre(args) -> int:
    comprova_persona()
    repo = troba_repo()
    nom, entorn = args.nom, args.entorn.strip()
    clau = args.des_de or nom
    if not NOM_GITHUB.match(nom) or nom.upper().startswith("GITHUB_"):
        raise Plega(f"«{nom}» no és un nom de secret vàlid a GitHub: lletres, xifres i «_», sense començar per xifra "
                    "ni per GITHUB_")
    if not re.fullmatch(CLAU_ENV, clau):
        raise Plega(f"«{clau}» no és un nom de variable del .env")
    if not entorn:
        raise Plega("--env: cal el nom de l'entorn de GitHub")
    if shutil.which("gh") is None:
        raise Plega("no trobo «gh» al PATH: el necessito per desar el secret")

    cami = repo.arrel / ".env"
    try:
        text = cami.read_bytes().decode("utf-8", errors="replace")
    except FileNotFoundError:
        raise Plega(f"no trobo el .env ({cami})")
    except OSError as e:
        raise Plega(f"no puc llegir el .env ({cami}): {e.strerror}")
    valor, linia, vegades = valor_del_env(text, clau)
    if valor is None:
        raise Plega(f"{clau} no és al .env ({cami})")
    if not valor:
        raise Plega(f"{clau} és buida al .env (línia {linia}). Si el valor comença per «#», posa'l entre cometes. "
                    "No he desat res")
    problemes = problemes_del_valor(valor)
    if problemes:
        mostra = ", ".join(problemes[:5]) + (f" i {len(problemes) - 5} més" if len(problemes) > 5 else "")
        raise Plega(f"{clau} (línia {linia} del .env) té caràcters que no són ASCII imprimible: {mostra}. Sol ser un "
                    "comentari o un caràcter enganxat en copiar-la: revisa aquesta línia. No he desat res")

    origen = f"{clau} al .env, línia {linia}" if clau == nom else f"des de {clau} al .env, línia {linia}"
    print(f"nucli secret · {nom} ({origen}) → entorn «{entorn}» de GitHub")
    if vegades > 1:
        print(f"Avís: {clau} surt {vegades} cops al .env. Faig servir l'últim (línia {linia}), com les eines habituals.")
    print(f"Valor: {descriu(valor)}")
    try:
        resposta = input(f"Deso aquest valor com a {nom} a l'entorn «{entorn}» de GitHub? [s/N] ").strip().lower()
    except EOFError:
        resposta = ""
    if resposta not in ("s", "si", "sí"):
        raise Plega("no confirmat: no he desat res")
    r = subprocess.run(["gh", "secret", "set", nom, "--env", entorn], cwd=str(repo.arrel), input=valor,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Plega(f"«gh secret set» ha fallat: {(r.stderr or r.stdout).strip()}")
    sortida = (r.stdout + r.stderr).strip()
    print(sortida or f"Desat: {nom} a l'entorn «{entorn}».")
    return 0
