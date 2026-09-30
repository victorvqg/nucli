---
name: tanca-sessio
description: Tanca una sessió de treball en un repo amb nucli.json. Extreu de la conversa les decisions, les trampes, les regles noves i l'estat, les escriu als docs que diu nucli.json i en fa commit en una branca pròpia (mai a main), sense push. Usa-la quan l'usuari vulgui acabar o pausar la feina, amb frases com «tanca», «tanca la sessió», «hem acabat», «deixa-ho per avui», «plegem» o «ho deixem aquí».
---

# Tanca la sessió

Deixa escrit als docs del repo el que ha passat en aquesta sessió, perquè la següent (teva o d'un altre agent) comenci sabent-ho. No inventis res: només el que ha passat de debò a la conversa.

## 1. Troba nucli.json

- Llegeix `nucli.json` a l'arrel del repo (`git rev-parse --show-toplevel`). Si ets en un worktree i no hi és, llegeix el del checkout principal (el primer camí de `git worktree list`).
- **Si no n'hi ha cap, digues-ho i atura't.** Aquesta skill només treballa en repos amb el nucli.
- Els camins de `docs` són relatius a l'arrel on treballes. Un valor `fitxer#Secció` vol dir «dins de la secció H2 `## Secció` d'aquell fitxer, al final».

## 2. Classifica la sessió en quatre piles

1. **Decisions** (`docs.decisions`), també les de «no farem X». Segueix el format del fitxer:
   - `"format": "adr"` (o sense format): `## ADR-NNNN · títol`, amb `Data:`, `Decisió:`, `Motiu:` i `Com revertir-la:`. El número és el màxim del fitxer + 1, amb quatre xifres.
   - `"format": "data"`: `## AAAA-MM-DD · títol`, amb `Decisió:`, `Motiu:` i `Com revertir-la:`. Mira una entrada existent i copia'n l'estil.
2. **Trampes** (`docs.trampes`): una entrada per trampa, `### títol` amb `- Símptoma:`, `- Causa:` i `- Com evitar-la:`.
3. **Regles noves**: **només les proposes** al resum final, com a canvi concret de `nucli.json` o de `docs.convencions`. No les apliquis tu.
4. **Estat** (`docs.estat`): reescriu el fitxer sencer amb `Última actualització: AAAA-MM-DD` i les seccions `## Ara`, `## Següent` i `## Bloquejat`. És l'única escriptura que substitueix contingut.
   - Si `tasques.font` és `github-issues`, a «Següent» i «Bloquejat» cada tasca s'apunta amb el seu issue: `#N`. Per saber què hi ha obert: `gh issue list --label tasca --state open --json number,title,labels`, que només llegeix. Si no el pots executar (sense xarxa o sense permís), no t'inventis cap número: digues-ho al resum.
   - Amb `github-issues`, el fitxer de tasques (`tasques.fitxer`) és historial: no el llegeixis com a cua ni hi escriguis res.

Si una pila és buida, no hi escriguis res.

## 3. No dupliquis ni inventis ids

- Abans d'escriure una decisió o una trampa, busca si ja hi és (també amb altres paraules). Si hi és, no la tornis a escriure.
- **Una tasca nova no és mai un id del fitxer de tasques** (`tasques.prefix`, p. ex. `mt`): no creïs cap `mtX`, ni tampoc cap issue. Si de la sessió en surt una, proposa'n el text al resum final perquè l'obri l'usuari: amb `github-issues`, amb els apartats del formulari d'issues del repo (`.github/ISSUE_TEMPLATE/`; al Marcador, «Què vull», «Per què», «Criteri de fet», «Prioritat», «Mida», «Zones delicades» i «Notes»), i si no, com un bloc sense id perquè l'afegeixi ell al fitxer de tasques.
- Si has de crear un id en un altre doc adoptat (`docs.adoptats`, p. ex. `mp`, `md`), és el màxim de **tot** el fitxer + 1, comptant també «Fet» i «Descartades». Mai reutilitzis un id.

## 4. Abans d'escriure

- Mira `git status --porcelain -- <camins dels docs que tocaràs>`. Si algun ja tenia canvis sense commit, **digues-ho a l'usuari i pregunta-li** abans de continuar.

## 5. Branca i commit

- **Mai facis commit a `main`**, ni a la `branca_base` de `nucli.json` si és una altra. Mira on ets amb `git branch --show-current`.
- Si hi ets (o si surt buit, HEAD desenganxat), abans del commit crea una branca pròpia i passa-hi: `git switch -c docs/sessio-AAAA-MM-DD-HHMM`, amb la data i l'hora d'ara (`date +%Y-%m-%d-%H%M`). Si ja existeix, afegeix-hi `-2`, `-3`… Els canvis sense commit que hi hagués passen a la branca nova: no en toquis cap.
- `git add` **només** dels docs que has tocat (camins concrets, mai `-A`).
- Missatge: `docs(sessio): tancament del AAAA-MM-DD`.
  - Si la branca és d'un issue (`issue/12-…`, o `<prefix>12-…` si `tasques.branca` en diu un altre, o `worktree-issue-12`, la de `nucli agent 12`), afegeix ` (#12)` al final: l'assumpte **ha d'acabar** així, i no n'hi ha prou que surti al cos.
  - Si no, i la branca porta un id de tasca amb els prefixos de `nucli.json` (`worktree-mt12` o `mt/mt12` → `mt12`), afegeix ` (mt12)` al final.
- El hook `commit-msg` del nucli el validarà: si el rebutja, corregeix el missatge. Mai `--no-verify`.
- **Mai facis push**, ni `nucli finish`.

## 6. Resum final

Acaba amb una llista curta: què has escrit i a quin fitxer, les regles que proposes (sense aplicar), les tasques noves que proposes (el text perquè l'usuari obri l'issue: tu no l'obres), la branca i el hash del commit. Si has creat la branca, digues-ho.

L'última línia, **sempre**: recorda a l'usuari que aquesta branca (digues quina) s'ha de pujar amb `nucli finish`, des del terminal. Abans, `nucli ship seal` (i `nucli ship run <check>` dels checks que demani `nucli ship plan`).
