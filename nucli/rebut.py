"""`nucli rebut markdown [--origen ci]`: el bloc «Rebut» d'un rebut segellat, en markdown (v0.1.4).

És el mateix bloc que `nucli finish` posa al PR, perquè la CI en pugui fer un d'idèntic: `nucli ship plan --json`
→ `nucli ship run` de cada check automàtic → `nucli ship seal` → `nucli rebut markdown --origen ci`. Només llegeix
el rebut: no executa res. Un rebut sense segell, retocat (sha256) o d'un HEAD que ja no és l'actual no s'escriu.
"""
from __future__ import annotations

from . import VERSIO
from .comu import Plega, troba_repo
from .ship import branca_amb_rebut, llegeix_rebut, sha_rebut, ultima

ORIGENS = {"finish": "per `nucli finish`", "ci": "per la CI"}


def markdown(rebut: dict, origen: str = "finish") -> str:
    """El bloc «Rebut del nucli»: per a cada check automàtic requerit pel segell, l'execució que el fa valer.

    Els requerits que no s'han executat (manuals sense confirmar i `fora_sandbox` pendents) surten a part, perquè
    el rebut no digui més del que s'ha fet.
    """
    segell = rebut["segell"]
    head = segell["head"]
    manuals = list(segell.get("manuals_pendents") or [])
    fora = list(segell.get("fora_sandbox_pendents") or [])
    automatics = [c for c in segell.get("requerits") or [] if c not in manuals and c not in fora]
    execucions = [e for e in (ultima(rebut, c) for c in automatics) if e]
    linies = ["## Rebut del nucli", "", f"Checks executats {ORIGENS[origen]} contra HEAD `{head[:12]}`:", ""]
    if execucions:
        linies += ["| check | codi | durada | hora |", "|---|---|---|---|"]
        linies += [f"| {e['check']} | {e['codi']} | {e['durada_s']} s | {e['hora']} |" for e in execucions]
    else:
        linies.append("Cap check automàtic requerit.")
    confirmacions = (rebut.get("finish") or {}).get("confirmacions") or []
    if confirmacions:
        linies += ["", "Confirmacions manuals:"]
        linies += [f"- {c['check']}: {c['resposta']} ({c['hora']})" for c in confirmacions]
    confirmats = {c["check"] for c in confirmacions if c.get("resposta") == "sí"}
    pendents = [m for m in manuals if m not in confirmats]
    if pendents:
        linies += ["", f"Checks manuals pendents (revisió humana): {', '.join(pendents)}"]
    if fora:
        linies += ["", f"Checks fora del sandbox pendents (sense executar): {', '.join(fora)}"]
    linies += ["", f"HEAD `{head}` · nucli {VERSIO}"]
    return "\n".join(linies) + "\n"


def ordre(args) -> int:
    repo = troba_repo()
    branca = branca_amb_rebut(repo)
    rebut = llegeix_rebut(repo, branca, exigeix=True)
    segell = rebut.get("segell")
    if not segell:
        raise Plega("el rebut no està segellat: passa els checks i «nucli ship seal»")
    if segell.get("sha256") != sha_rebut(rebut):
        raise Plega("el sha256 del segell no quadra: algú ha tocat el rebut. Torna a passar els checks i «nucli ship seal»")
    head = repo.git("rev-parse", "HEAD")
    if head != segell.get("head"):
        raise Plega(f"HEAD ({head[:8]}) no és el del segell ({str(segell.get('head'))[:8]}): el rebut és d'un altre "
                    "commit. Torna a passar els checks i «nucli ship seal»")
    if args.origen == "finish" and not rebut.get("finish"):
        raise Plega("aquest rebut no ha passat per «nucli finish»: si els checks els ha executat la CI, "
                    "«nucli rebut markdown --origen ci»")
    print(markdown(rebut, args.origen), end="")
    return 0
