"""Punt d'entrada de l'ordre `nucli`: arguments en català i despatx a cada mòdul."""
from __future__ import annotations

import argparse
import importlib
import sys

from . import VERSIO
from .comu import Plega

_TRADUCCIONS = {
    "usage: ": "ús: ",
    "positional arguments": "arguments",
    "optional arguments": "opcions",
    "options": "opcions",
    "show this help message and exit": "mostra aquesta ajuda i surt",
    "show program's version number and exit": "mostra la versió i surt",
    "%(prog)s: error: %(message)s\n": "%(prog)s: error: %(message)s\n",
    "the following arguments are required: %s": "falten aquests arguments: %s",
    "unrecognized arguments: %s": "arguments desconeguts: %s",
    "expected one argument": "cal un valor",
    "invalid choice: %(value)r (choose from %(choices)s)": "opció no vàlida: %(value)r (tria entre %(choices)s)",
    "invalid %(type)s value: %(value)r": "valor no vàlid: %(value)r",
}
argparse._ = lambda text: _TRADUCCIONS.get(text, text)  # type: ignore[attr-defined]

# ordre → (mòdul, funció). Les ordres que encara no s'han construït apunten a `_pendent`.
_ORDRES = {
    "init": ("init", "ordre"),
    "ship": ("ship", "ordre"),
    "finish": ("finish", "ordre"),
    "port": ("worktree", "ordre_port"),
    "neteja": ("worktree", "ordre_neteja"),
    "agent": ("agent", "ordre"),
    "usage": ("us", "ordre"),
    "hook": ("ganxos", "ordre"),
    "githook": ("githooks", "ordre"),
    "intern": ("install", "ordre"),
}


def construeix_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nucli",
        description="El nucli: docs comuns, porta amb rebut i cicle d'agent per a tots els teus repos. "
        "Tret d'init, usage i --help, les ordres només actuen en repos amb nucli.json.",
    )
    p.add_argument("--version", action="version", version=f"nucli {VERSIO}")
    sub = p.add_subparsers(dest="ordre", metavar="<ordre>")

    s = sub.add_parser("init", help="prepara el repo: docs, nucli.json, .gitignore, permisos i hooks (no fa commit)")
    s.add_argument("--dry-run", action="store_true", help="diu què faria sense escriure res")
    s.add_argument("--adopta", action="append", default=[], metavar="ROL=CAMÍ",
                   help="força l'adopció d'un doc (p. ex. arquitectura=INFORME_TECNIC.md)")

    s = sub.add_parser("ship", help="porta amb rebut: plan, run <check>, seal")
    ss = s.add_subparsers(dest="pas", metavar="<pas>")
    ss.add_parser("plan", help="quins checks demana el diff d'aquesta branca")
    r = ss.add_parser("run", help="executa un check i en desa el resultat al rebut")
    r.add_argument("check")
    ss.add_parser("seal", help="segella el rebut si tots els checks requerits són en verd sobre l'arbre de HEAD")

    sub.add_parser("finish", help="(només tu, fora del sandbox) verifica, torna a passar els checks, fa push i obre el PR")

    s = sub.add_parser("port", help="port estable d'aquest worktree (4100–4999)")
    s.add_argument("--comprova", action="store_true", help="avisa si el port està ocupat")

    s = sub.add_parser("neteja", help="(només tu) treu els worktrees fusionats")
    s.add_argument("--dry-run", action="store_true", help="només diu què trauria")

    s = sub.add_parser("agent", help="llança un agent headless en un worktree nou")
    s.add_argument("id", help="id del worktree i de la tasca ([a-z0-9-]+)")
    s.add_argument("--tasca", help="text de la tasca (si no, el bloc <id> del fitxer de tasques)")
    s.add_argument("--pressupost", type=float, help="màxim en dòlars (per defecte, el de nucli.json)")
    s.add_argument("--torns", type=int, help="màxim de torns (per defecte, el de nucli.json)")

    s = sub.add_parser("usage", help="ús de les skills per skill i per repo, i les que no s'han obert")
    s.add_argument("--dies", type=int, default=30, help="finestra en dies (per defecte, 30)")

    s = sub.add_parser("hook", help="(intern) hooks de Claude Code")
    s.add_argument("nom", choices=["protegeix-rebuts", "us-skill"])

    s = sub.add_parser("githook", help="(intern) hooks de git")
    s.add_argument("nom", choices=["pre-push", "commit-msg"])
    s.add_argument("args", nargs="*")

    s = sub.add_parser("intern", help="(intern) passos d'install.sh")
    s.add_argument("pas", choices=["fusiona-ganxos"])
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--settings", help="camí del settings.json (per defecte, ~/.claude/settings.json)")
    return p


def main(argv=None) -> int:
    parser = construeix_parser()
    args = parser.parse_args(argv)
    if not args.ordre:
        parser.print_help()
        return 0
    if args.ordre == "ship" and not args.pas:
        parser.parse_args(["ship", "--help"])
    modul, funcio = _ORDRES[args.ordre]
    try:
        try:
            m = importlib.import_module(f"nucli.{modul}")
        except ModuleNotFoundError as e:
            if e.name != f"nucli.{modul}":
                raise
            return _pendent(args)
        return getattr(m, funcio)(args) or 0
    except Plega as e:
        print(f"nucli: {e}", file=sys.stderr)
        return e.codi
    except KeyboardInterrupt:
        print("\nnucli: interromput", file=sys.stderr)
        return 130


def _pendent(args) -> int:
    """Ordre encara no construïda: fora d'un repo amb nucli.json plega com les altres."""
    from .comu import troba_repo

    if args.ordre not in ("usage", "hook", "githook", "intern"):
        troba_repo()
    raise Plega(f"«nucli {args.ordre}» encara no està implementada en aquesta versió")
