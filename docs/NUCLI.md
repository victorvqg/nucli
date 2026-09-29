# NUCLI.md — especificació i pla de la v0.1

Última revisió: 2026-09-29 · Estat: **aprovat amb canvis (n478)**. La v0.1 es construeix per fases (§8), amb un commit per fase.

Canvis de la n478 respecte de l'esborrany:
1. El forat dels worktrees afecta **qualsevol** worktree, també un `claude --worktree` interactiu. `nucli init` detecta les regles ancorades al checkout principal i proposa (sense aplicar-les) les versions que cobreixen `.claude/worktrees/**`, i que l'`allow` dels scripts relatius només valgui al checkout principal. Mentre no hi siguin, `init` ho avisa i `nucli agent` no arrenca (§5.1, §5.4, §7.1).
2. `nucli finish` torna a executar els checks automàtics requerits contra HEAD abans de pujar. Si algun falla, no puja res (§5.2).
3. Preguntes: P1 = A (bloc «Nucli» curt), P3 = sí, P6 = sí, la resta segons la recomanació (§9).
4. Es mantenen: regles i ordres llegides del `nucli.json` del checkout principal, check vàlid només sobre l'arbre exacte de HEAD i `nucli finish` executat sempre per tu.

«nucli» és el meu kernel personal perquè els agents de codi (Claude Code, Kimi, Codex) treballin igual i de forma fiable a tots els meus projectes. S'inspira en Crux de Jorge Carrera. Són tres coses: uns **docs** amb el mateix nom a cada repo, una **porta amb rebut** (no es puja res sense haver passat els checks que toquen, i ho demostra un rebut segellat contra el commit) i un **cicle** que fan tots els agents. El que canvia de projecte a projecte és a `nucli.json`, i el nucli només hi posa el mecanisme.

---

## 1. Principis i com s'apliquen

| | Principi | Conseqüència concreta |
|---|---|---|
| a | Si una cosa canvia en canviar de projecte, no va al nucli | Ordres de check, regles del diff, ubicació dels docs, prefixos d'ids, tipus de commit i eines prohibides extra van a `nucli.json`. El nucli no sap res de Supabase, de `check.sh` ni de `TASQUES.md`. |
| b | S'instal·la un cop a cada Mac i només actua als repos amb `nucli.json` | `install.sh` enllaça `bin/nucli` i les skills i fusiona els hooks globals. Tots els hooks (de Claude Code i de git) i totes les ordres, tret d'`init`, `usage` i `--help`, busquen `nucli.json` pujant des del directori actual. Si no el troben, **surten amb 0 sense fer res** (els hooks) o **plegen amb un missatge** (les ordres). |
| c | No reinventis el que Claude Code ja fa | Worktrees amb `claude --worktree` i `.worktreeinclude`, instruccions compartides amb `@AGENTS.md` dins de `CLAUDE.md`, skills a `~/.claude/skills`, hooks, regles de permisos i sandbox. El nucli no té sandbox, memòria ni gestor de tasques propis. |
| d | Tot en català | Sortida de l'eina, docs generats, missatges d'error, prompts de l'agent, commits del nucli. Els identificadors de codi i les claus de `nucli.json` també són en català. |
| e | Respecta la seguretat de cada repo i no l'afluixis mai | El nucli **només afegeix**: una regla `ask`, entrades al `.gitignore`, un `.worktreeinclude` i `core.hooksPath`. Mai toca `allow`/`deny`/`sandbox` existents. Si calen regles `allow`, te les proposa i les aplica tu. Els canvis a la configuració de seguretat d'una branca obliguen a revisió humana (§5.2). |

## 2. Què adopto del marcador

Llegit en només lectura el 29/9/2026: `CLAUDE.md`, `TASQUES.md`, `PROPOSTES.md`, `DECISIONS.md`, `docs/DISSENY.md`, `scripts/agent.sh` i `.claude/settings.json`. També he mirat `AGENTS.md`, `.gitignore`, `scripts/check.sh` i `ci.yml`.

- **Ids fixos, mai reutilitzats**: `mtX` (tasques), `mpX` (propostes), `mdX` (tensions de disseny), `maNNN`/`nNNN` (torns). El nucli ho generalitza: cada doc adoptat declara el seu prefix, i un id nou és sempre el màxim de tot el fitxer + 1, comptant també «Fet» i «Descartades».
- **Commits**: `tipus(àmbit): què (mtX)` en català. L'id de la tasca va al commit que la tanca. `agent.sh` també fa servir `wip(...)` i `chore(tasques)`.
- **REGLA ZERO, punt 5**: l'agent treballa en una branca i no fusiona, no desplega i no fa push. `nucli agent` el manté, i `nucli finish` l'executa una persona.
- **Pla abans del codi en zona sensible**, i les decisions de «no fer X» també es documenten. El cicle de l'agent ho inclou.
- **Provar el comportament**, no només que no peti: cada check guarda la sortida, i el segell exigeix que el check s'hagi executat sobre l'arbre exacte del commit (§5.2).
- **La pila de seguretat de la mp45**: `deny`, `ask` i sandbox (`autoAllowBashIfSandboxed`, `excludedCommands`, `denyRead`/`denyWrite`) a `.claude/settings.json`, i `--disallowedTools` + `--strict-mcp-config` a `agent.sh`. Lliçons que condicionen el disseny:
  - una ordre exclosa del sandbox només en surt si comença **exactament** com diu la regla;
  - les ordres `!` corren **fora** del sandbox;
  - el sandbox cobreix Bash, però no les eines MCP ni l'eina Edit;
  - les regles de ruta del marcador són **absolutes** (`~/PROJECTS/MARCADOR/marcador/…`), i això té conseqüències als worktrees (§7).
- **Formats existents**:
  - `DECISIONS.md` és ADR-lite **datat** (`## AAAA-MM-DD · títol` amb Decisió / Motiu / Com revertir-la), sense numeració. S'adopta tal com és.
  - Els repos nous tindran ADR **numerats** (`## ADR-0001 · …`).
  - Al marcador, les convencions i les lliçons apreses viuen a seccions de `CLAUDE.md`, i l'arquitectura a `INFORME_TECNIC.md`.
- **Al marcador ja hi ha `AGENTS.md`** (per a Kimi, 7 KB): `nucli init` l'ha de tractar igual que `CLAUDE.md`, amb una proposta de fusió i sense sobreescriure'l.

## 3. Fets verificats a la documentació de Claude Code

Comprovat el 29/9/2026 amb el CLI 2.1.284, a `code.claude.com/docs/en/{hooks,worktrees,permissions,settings,skills,memory,sandboxing,tools-reference}.md`.

| Fet | Conseqüència per al nucli |
|---|---|
| `claude --worktree <id>` crea `.claude/worktrees/<id>/` amb la branca `worktree-<id>`. Funciona amb `-p`. | `nucli agent` el fa servir tal qual. |
| La base és `origin/HEAD` (branca per defecte **del remot**, amb un fetch si fa més de 24 h), no el `main` local. `worktree.baseRef: "head"` la canvia pel HEAD local, però no accepta noms de branca. | Els commits no pujats a `main` **no** arriben al worktree. La base del nucli és `origin/<branca_base>` si existeix, i si no, `<branca_base>` local. |
| Amb `-p` no hi ha neteja en sortir, i el worktree **queda bloquejat** (`git worktree lock`). | `nucli agent` el desbloqueja quan `claude` acaba. Si no, `nucli neteja` no el podria treure. |
| `.worktreeinclude`: sintaxi `.gitignore`, a l'arrel del repo. Només copia fitxers que coincideixen **i** que git ignora. | Al marcador, `.env.*` ja és ignorat: `.env.dev` es copiaria i l'`.env` no, perquè no s'hi anomena. |
| Hooks: el matcher de l'eina de skills és **`Skill`**. Un `/skill` que escrius tu **no** passa per `PreToolUse`/`PostToolUse`: passa per `UserPromptExpansion` (camp `command_name`). | La mesura del punt 7 no veuria les skills que obres a mà. Vegeu la pregunta P6. |
| El camp d'entrada de l'eina `Skill` no surt a la documentació de hooks. L'esquema de l'eina diu `skill` (i `args`). | El hook llegeix `tool_input.skill`. Es comprova amb una crida real a la fase 7. |
| Blocar des de `PreToolUse`: `hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason` (o `exit 2` + stderr). Eines d'edició: `Edit`, `Write`, `NotebookEdit`, amb el camp `file_path`. | El hook de rebuts té el matcher `^(Edit\|Write\|NotebookEdit)$`. |
| Els hooks de tots els fitxers de configuració s'executen tots, en paral·lel. Un handler idèntic a dos fitxers només corre un cop. | Els hooks globals del nucli conviuen amb els del projecte (p. ex. `mcp-sql-sensible.sh`). |
| `CLAUDE_PROJECT_DIR` no segueix el worktree, però el camp `cwd` de l'entrada sí. | Els hooks del nucli fan servir `cwd`. |
| `Bash(x:*)` equival a `Bash(x *)` i també coincideix amb `x` sol. Precedència: deny > ask > allow, entre tots els fitxers. | `Bash(nucli finish:*)` cobreix `nucli finish` sense arguments, i cap `allow` no el pot saltar. |
| Una skill a `~/.claude/skills/<nom>` pot ser un **enllaç simbòlic** a una carpeta. `description` + `when_to_use` es tallen a 1.536 caràcters. | `install.sh` enllaça cada skill per separat, sense tocar la resta de skills que ja tens. |
| `CLAUDE.md` pot importar `@AGENTS.md`. Si hi ha `CLAUDE.md`, Claude no llegeix `AGENTS.md` pel seu compte. | Als repos nous, el contingut va a `AGENTS.md`, i `CLAUDE.md` = `@AGENTS.md` + el que és només de Claude. |
| Sandbox en un worktree: deixa escriure al `.git` compartit, però **no** a `hooks/` ni a `config`. | Un agent dins del sandbox no pot canviar `core.hooksPath`. |
| `.claude/settings.json` (i els seus hooks) es llegeix del `.claude/` del directori on arrenca la sessió, sense pujar. `settings.local.json` es llegeix de l'arrel del repo, que en un worktree és **el checkout principal**. | En un worktree, les regles del projecte són les del `settings.json` **de la base** (`origin/main`), no les del checkout principal. Una regla nova només protegeix els worktrees quan és a la base, al `settings.local.json` del checkout principal o al teu `~/.claude/settings.json`. |
| Ancoratges de les regles de camí: `//camí` és absolut, `~/camí` parteix de HOME, `/camí` és relatiu a la font (al projecte, el directori de treball principal, que en un worktree és l'arrel del worktree) i `camí` és relatiu al directori actual. | Les regles `~/…` i `//…` que apunten al checkout principal **no** cobreixen `.claude/worktrees/<id>/`. Les `/…`, les relatives i les que porten `**` sí. |
| Les regles de camí només es consulten a `Edit(…)` i `Read(…)`. `Edit` cobreix totes les eines d'edició. Una regla `Write(camí)` o `NotebookEdit(camí)` s'accepta però **no es consulta mai**. | El nucli analitza `Edit`, `Read` i `Bash`, i avisa de les `Write(camí)` mortes. |
| Una sessió en un worktree bloca `Edit`/`Write`/`NotebookEdit` cap al checkout principal, i també el Bash que hi apunta (`cd`, `git -C`…). | El checkout principal queda fora de l'abast d'un agent en un worktree, i per això les regles es llegeixen del seu `nucli.json` (§5.2). El forat és l'altre sentit: els fitxers protegits **del worktree**. |
| `UserPromptExpansion` porta `command_name`, `command_args` i `cwd`, i accepta un matcher pel nom de l'ordre. | P6: el nucli hi penja la mateixa mesura que a `PostToolUse` (§5.7). |

## 4. Estructura del repo `nucli`

```
bin/nucli              llançador (python3, només biblioteca estàndard); resol el seu enllaç i importa nucli/
nucli/                 paquet: comu.py (git, arrels), config.py (nucli.json), patrons.py (sintaxi .gitignore),
                       docs.py i init.py (init), permisos.py (settings.json i worktrees), ship.py, finish.py,
                       worktree.py (port, neteja), agent.py, ganxos.py (hooks de Claude), githooks.py, us.py
githooks/              pre-push, commit-msg (els activa core.hooksPath)
skills/tanca-sessio/   SKILL.md
plantilles/            CLAUDE.md, AGENTS.md, ESTAT.md, DECISIONS.md, TRAMPES.md, CONVENCIONS.md, ARQUITECTURA.md, nucli.json
tests/                 pytest (repos git temporals a tmp_path; gh i claude simulats al PATH)
install.sh             --dry-run; enllaços + fusió de hooks amb còpia de seguretat
docs/NUCLI.md          aquest document
docs/exemples/         marcador.nucli.json (el nucli.json proposat per al marcador, §5.0)
```

- `bin/nucli` fa servir `#!/usr/bin/env python3` i és compatible amb **Python 3.9** (el `/usr/bin/python3` de macOS), sense dependre del `.venv`.
- El `.venv` del repo només serveix per a pytest: `python3 -m venv .venv && .venv/bin/pip install pytest`.
- Cada fase passa els tests amb el Python de Homebrew i fa un `compileall` + `nucli --help` amb el 3.9.

## 5. Especificació de la v0.1

### 5.0 `nucli.json`

Va a git, a l'arrel del repo. `nucli init` en genera un de genèric (checks endevinats, marcats «REVISA»). La proposta per al marcador és aquesta, i també és a `docs/exemples/marcador.nucli.json`: si la copies a l'arrel del marcador abans de `nucli init`, `init` la fa servir i no la trepitja.

```json
{
  "versio": 1,
  "idioma": "ca",
  "branca_base": "main",
  "docs": {
    "estat":        "docs/ESTAT.md",
    "decisions":    {"cami": "DECISIONS.md", "format": "data"},
    "trampes":      "docs/TRAMPES.md",
    "convencions":  "CLAUDE.md#Convencions",
    "arquitectura": "INFORME_TECNIC.md",
    "adoptats": [
      {"cami": "TASQUES.md",      "prefix": "mt"},
      {"cami": "PROPOSTES.md",    "prefix": "mp"},
      {"cami": "docs/DISSENY.md", "prefix": "md"}
    ]
  },
  "tasques": {"fitxer": "TASQUES.md", "prefix": "mt"},
  "checks": {
    "lint":       {"ordre": "bash scripts/check.sh"},
    "test":       {"ordre": "cd scraper && \"$NUCLI_ARREL/.venv/bin/python\" -m unittest discover -s tests"},
    "smoke":      {"ordre": "\"$NUCLI_ARREL/.venv/bin/python\" scripts/smoke.py", "fora_sandbox": true},
    "visual":     {"manual": "Revisió visual al mòbil a 360, 390 i 430 px (refresc dur)"},
    "migracions": {"manual": "Migració provada en transacció desfeta (begin; … rollback;); l'aplica l'usuari abans del merge"}
  },
  "regles": [
    {"patrons": ["*.md", "docs/**"],          "checks": []},
    {"patrons": ["*.py"],                     "checks": ["lint", "test"]},
    {"patrons": ["web/**"],                   "checks": ["lint", "smoke", "visual"]},
    {"patrons": ["supabase/migrations/**"],   "checks": ["test", "migracions"]}
  ],
  "per_defecte": ["lint", "test"],
  "commits": {"tipus": ["feat","fix","docs","style","refactor","perf","test","build","ci","chore","revert","wip"]},
  "agent": {
    "torns": 60, "pressupost_usd": 7,
    "prohibides": ["Bash(bash scripts/deploy.sh)", "Bash(supabase:*)", "Bash(bash scripts/llanca-sync.sh)", "mcp__supabase__*"]
  }
}
```

**Camps del fitxer:**
- **`docs`**: cada rol apunta a un fitxer o a `fitxer#Secció`, que vol dir «escriu dins d'aquesta secció H2».
- **`checks`**: n'hi ha de dos tipus. **Automàtics** (`ordre`, una línia de shell) i **manuals** (`manual`, el text que es mostra quan s'han de confirmar).
- **`fora_sandbox`**: marca els checks que no poden córrer dins del sandbox. `smoke.py` n'és un, perquè Chromium no hi arrenca (mp44). Els passa `nucli agent` en acabar, o tu amb `!`.
- **`regles`**: els patrons segueixen la sintaxi `.gitignore`. Sense `/`, coincideixen amb el nom del fitxer a qualsevol nivell; amb `/`, des de l'arrel; `**` vol dir qualsevol nombre de carpetes.
  - Si un fitxer coincideix amb diverses regles, es fa la unió dels seus checks.
  - Si un fitxer **no coincideix amb cap**, s'aplica `per_defecte`. Així un fitxer que no s'ha previst no es queda mai sense checks.
- **Variables de les ordres**: `NUCLI_ARREL` (l'arrel del checkout principal, perquè el `.venv` no és al worktree), `NUCLI_WORKTREE` (l'arrel del worktree actual) i `NUCLI_PORT` (§5.3).

### 5.1 Docs: `nucli init [--dry-run] [--adopta rol=camí]…`

1. **Detecta** el que ja existeix:
   - els 5 rols pel nom del fitxer (arrel o `docs/`, sense distingir majúscules; també `ARCHITECTURE`, `CONVENTIONS`…);
   - seccions H2 de `CLAUDE.md`/`AGENTS.md` amb noms equivalents (`Convencions`, `Lliçons apreses`, `Trampes`, `Arquitectura`…);
   - docs amb ids: un fitxer amb 3 o més encapçalaments `### <prefix><n> ·` s'adopta amb aquell prefix. Al marcador: `mt`, `mp` i `md`.
   
   `--adopta arquitectura=INFORME_TECNIC.md` força una adopció que la detecció no veu.
2. **Crea a `docs/` només el que falta**, a partir de plantilles curtes (encapçalament, «com s'escriu una entrada» i cap contingut inventat). **No mou, no renomena i no reescriu res**, i no toca cap id.
3. **`CLAUDE.md` i `AGENTS.md`** (menys de 40 línies cadascun):
   - Si no n'hi ha cap, `AGENTS.md` porta el contingut (docs, cicle i «mai») i `CLAUDE.md` = `@AGENTS.md` + 5–8 línies només per a Claude (worktrees, `nucli finish` pregunta, skill `tanca-sessio`).
   - Si ja existeixen, **no els toca**: escriu la proposta de fusió a `.nucli/proposta/CLAUDE.md` i `.nucli/proposta/AGENTS.md` i n'ensenya el diff. La proposta és el fitxer tal com és més un bloc `## Nucli` curt al final (P1): on són els docs, el cicle i «mai». No n'aprima ni en mou res. Si el fitxer ja té el bloc, no proposa res.
4. **`nucli.json`**: el crea si no existeix, amb el que ha detectat i les ordres de check que endevina. Les endevinades porten el comentari «REVISA» a la sortida. Si ja existeix, no el toca.
5. **Afegeix sense tocar res més** (més detall a §5.2, §5.3 i §5.5):
   - `.nucli/` i `.claude/worktrees/` al `.gitignore`;
   - el `.worktreeinclude`;
   - `Bash(nucli finish:*)` a `ask` de `.claude/settings.json`;
   - `core.hooksPath`.
6. **Permisos per als worktrees** (§7.1). Llegeix les regles de `.claude/settings.json` i `.claude/settings.local.json` del checkout principal i **proposa, sense aplicar res**, a `.nucli/proposta/permisos.md`:
   - per a cada regla `deny`/`ask` de tipus `Edit`, `Read` o `Bash` ancorada al camí del checkout principal (`~/…` o `//…`) que no cobreixi `.claude/worktrees/**`, la mateixa regla per a `<checkout>/.claude/worktrees/**/<camí>`, a la mateixa llista. Si una altra regla ja la cobreix (p. ex. les de `.env` amb `**`), no proposa res;
   - per a cada regla `allow` de Bash que executa un script del repo amb camí relatiu (`bash scripts/llanca-sync.sh`), substituir-la per la versió amb el camí absolut del checkout principal, i el mateix a `sandbox.excludedCommands`. Si no, en un worktree aquella ordre executaria **la còpia del worktree**, sense preguntar i fora del sandbox;
   - avisa de les regles `Write(camí)`/`NotebookEdit(camí)`, que Claude Code no consulta, i de les entrades relatives d'`excludedCommands` sense `allow` (en un worktree sortirien del sandbox amb la còpia del worktree, després de preguntar-te).

   Una proposta es dona per aplicada quan la veu un worktree nou, és a dir, quan és al `settings.json` **de la base**, al `settings.local.json` del checkout principal o al `~/.claude/settings.json`. Si només és al `settings.json` del checkout principal sense commit ni fusió, `init` t'ho diu. Mentre en quedi alguna de pendent, `init` acaba amb un avís clar i **`nucli agent` es nega a arrencar**.
7. **Idempotent**: una segona passada no canvia res. `--dry-run` imprimeix cada acció (crea / adopta / proposa / afegeix / ja hi és) sense escriure res.
8. **No fa commit**: t'ho deixa per revisar.

### 5.2 Porta amb rebut

**`nucli ship plan`**
- Llegeix les regles i les ordres del **`nucli.json` del checkout principal** (`$NUCLI_ARREL/nucli.json`), no les del worktree. Si no, un agent podria editar les regles i declarar-ho tot «docs». Des d'un worktree, Claude Code no deixa editar el checkout principal i el sandbox no hi deixa escriure (§3).
- El diff que classifica: `git diff --name-status -M <merge-base>` (també la ruta vella dels fitxers renomenats o esborrats) + els canvis sense commit + els fitxers nous. El merge-base es calcula contra `origin/<branca_base>` si existeix, i si no, contra `<branca_base>`.
- Si el checkout principal no té `nucli.json`, plega i diu «primer executa `nucli init`».
- Treu la llista de fitxers → regla que els toca → checks, i els checks requerits al final.
- **Regla fixa del nucli, no configurable**: si el diff toca `nucli.json`, `.claude/**`, `.mcp.json`, `.worktreeinclude`, `.gitignore` o `githooks/**`, s'hi afegeix el check manual `revisio-config` («canvi de configuració o de seguretat: revisió humana»). Principi (e).

**`nucli ship run <check>`**
- Executa l'ordre del `nucli.json` del checkout principal amb `bash -c` a l'arrel del worktree, amb les variables `NUCLI_*`, i mostra la sortida en directe.
- A `.nucli/rebuts/<branca>.json` (les `/` de la branca passen a `__`), per a cada execució, desa:
  - l'ordre, el codi de sortida i la durada;
  - la sortida (els últims 20 KB, amb una marca si està retallada);
  - l'hora i el HEAD;
  - l'**arbre** del directori de treball en aquell moment: `git write-tree` sobre un índex temporal amb `add -A`.
- Surt amb el codi del check.
- Un check `manual` no s'executa: es confirma a `finish`.

**`nucli ship seal`**
- Torna a calcular els checks requerits a partir del diff, sense fiar-se del rebut, i segella només si:
  - l'arbre de treball és net;
  - l'última execució de cada check automàtic requerit té codi 0;
  - aquella execució es va fer **sobre l'arbre exacte de HEAD** (`arbre == HEAD^{tree}`).
- El segell desa: `head`, `arbre`, `hora`, `requerits`, `manuals_pendents` i un `sha256` del contingut canònic del rebut.
- Si falla, diu exactament què falta: «test: executat sobre un arbre diferent del de HEAD (has editat després?)».

**`nucli finish`** (l'executes sempre tu, al terminal o amb `! nucli finish`, és a dir, fora del sandbox). Va per passos, i al primer refús s'atura **sense pujar res**, amb el motiu i l'ordre que ho arregla:
1. **Git i rebut.** Es nega a continuar si:
   - ets a la branca base;
   - no hi ha rebut, o no està segellat;
   - el `sha256` no quadra (algú ha tocat el rebut);
   - HEAD ≠ `segell.head`, o l'arbre de treball no és net;
   - algun check requerit, **recalculat ara**, té l'última execució fallida, sobre un arbre que no és el de HEAD, o no n'ha tingut cap.
2. **Checks manuals.** Si n'hi ha i no hi ha terminal, plega. Si n'hi ha, una persona els confirma un per un (`s/N`); un «no» atura el `finish`. Les respostes queden al rebut.
3. **Torna a executar contra HEAD tots els checks automàtics requerits**, també els `fora_sandbox`, un darrere l'altre, a l'arrel del worktree i amb l'arbre net. Després de cada check comprova que HEAD no ha canviat i que l'arbre continua net: un check que modifica fitxers és un refús. Cada execució queda al rebut amb `"via": "finish"`. **Si algun falla, no puja res.**
4. Si tot és correcte:
   - `git push -u origin <branca>` (el pre-push del nucli el deixa passar perquè no és `main`);
   - `gh pr create --base main` amb el títol del primer commit de la branca i el resum a la descripció: la taula check · codi · durada · hora **de les execucions del pas 3**, les confirmacions manuals, HEAD i versió del nucli.

   Si la branca ja té un PR obert, fa el push i hi afegeix el resum com a comentari. **No fa mai merge.**

Els manuals van abans del pas 3 perquè la persona que confirma que ha revisat la branca ho faci abans que el codi de la branca s'executi fora del sandbox.

**Límit, dit clar**: el pas 3 executa codi de la branca (scripts i tests que l'agent pot haver tocat) fora del sandbox i amb xarxa. És el mateix que avui fa `agent.sh` en acabar, però aquí passa després de la teva revisió. Revisa el diff abans de llançar `nucli finish`.

**Proteccions**
- `.nucli/` va al `.gitignore`.
- Un hook `PreToolUse` global (matcher `^(Edit|Write|NotebookEdit)$`) nega qualsevol `file_path` dins de `.nucli/rebuts/` d'un repo amb `nucli.json`.
- `.nucli/` porta el seu propi `.gitignore` (`*`), perquè el rebut no embruti l'arbre d'un worktree la base del qual encara no ignora `.nucli/`.
- **Límit, dit clar**: una ordre Bash sí que pot escriure el rebut. El rebut és una barana contra errors, no una frontera contra un agent hostil. El que el fa fiable: `finish` ho torna a comprovar tot contra git (HEAD, arbre, regles del checkout principal), el `sha256` detecta retocs a mà, els manuals només es confirmen en un terminal i, sobretot, `finish` torna a executar els checks ell mateix abans de pujar.

**Permisos**
- `nucli init` afegeix `Bash(nucli finish:*)` a `ask`. Ho fa amb una inserció de text mínima a l'array `ask` (conserva el format del fitxer) i després comprova que el JSON resultant sigui l'original més aquesta regla. Si no pot, plega i t'ho diu. No toca cap altra regla.
- Al marcador no cal cap `allow`: `nucli ship|port|usage` corren dins del sandbox i `autoAllowBashIfSandboxed` ja els aprova.
- Als repos **sense** sandbox, `init` et **proposa** (no aplica): `Bash(nucli ship plan)`, `Bash(nucli ship run:*)`, `Bash(nucli ship seal)`, `Bash(nucli port)` i `Bash(nucli usage)`. `ship run` només executa ordres de `nucli.json` de la base, i per això és segur deixar-lo lliure.

### 5.3 Aïllament natiu

- **Worktrees**: `claude --worktree <id>`, que crea `.claude/worktrees/<id>` i la branca `worktree-<id>`. `nucli init` afegeix `.claude/worktrees/` al `.gitignore`.
- **`.worktreeinclude`**: si existeix `.env.dev`, conté `.env.dev` i un comentari. Si no (el marcador, fins al pas 3 del flux), **només el comentari**:
  ```
  # nucli: aquí només hi va l'entorn de desenvolupament (.env.dev). MAI l'.env de producció.
  ```
- **`nucli port`**: `4100 + (sha256(camí real de l'arrel del worktree) mod 900)`. És estable per a cada worktree, i el mateix valor va a `NUCLI_PORT`. Amb `--comprova`, avisa si el port està ocupat. Hi pot haver col·lisions entre worktrees: s'accepta.
- **`nucli neteja [--dry-run]`** (necessita `gh` i xarxa, i per tant l'executes tu):
  1. Fa `git fetch`. Per a cada worktree de `.claude/worktrees/`, el dona per fusionat si la seva branca és a `origin/main` (per història) **o** si `gh` diu que el seu PR s'ha fusionat amb aquest mateix HEAD (fusions *squash* des de GitHub, que és com fusiones ara, n475).
  2. Salta els que tenen canvis sense commit o estan bloquejats. Mai fa servir `--force`.
  3. Et mostra la llista i et demana confirmació.
  4. Fa `git worktree remove` i, després, `git branch -d` (o `-D` només en el cas *squash* verificat amb `gh`).
  
  Les branques: v0.1 només toca `worktree-*` (vegeu P5).

### 5.4 `nucli agent <id> [--tasca "text"] [--pressupost N] [--torns N]`

Versió general de `scripts/agent.sh`, sense res del marcador (el moviment de `TASQUES.md` es queda a `agent.sh`). Passos:

1. **Prèvies**:
   - el checkout principal té `nucli.json`, i la base també (perquè el worktree en tingui els docs);
   - **cap proposta de permisos pendent** (§5.1 pas 6, §7.1). Si n'hi ha, es nega a arrencar i les llista;
   - `claude` és al PATH;
   - `.claude/worktrees/<id>` encara no existeix;
   - l'id és vàlid (`[a-z0-9-]+`).
2. **Prompt del cicle**, en català:
   - llegir `CLAUDE.md`/`AGENTS.md` i els docs de `nucli.json`, i la tasca (`--tasca`, o el bloc `<id>` del fitxer de `tasques`);
   - si toca més d'un mòdul, escriure el pla a `.nucli/pla-<id>.md` abans de tocar codi;
   - implementar el canvi mínim, amb commits Conventional Commits en l'idioma de `nucli.json` i amb `(<id>)`;
   - `nucli ship plan` → `nucli ship run` de cada check automàtic que no sigui `fora_sandbox` → `nucli ship seal`;
   - si no pot acabar, **escriure per què s'atura** a `.nucli/atura-<id>.md` i no fer commit de feina a mitges.
3. **Llançament**: `env -u CLAUDECODE claude -p --worktree <id>` amb les opcions d'`agent.sh`:
   - `--permission-mode acceptEdits`, `--strict-mcp-config`, `--max-turns`, `--max-budget-usd`, `--output-format json` i `--no-session-persistence`;
   - **`--allowedTools`**: `Read Edit Write Grep Glob "Bash(git:*)" "Bash(nucli ship plan)" "Bash(nucli ship run:*)" "Bash(nucli ship seal)" "Bash(nucli port)"`;
   - **`--disallowedTools`**:
     - tota la llista d'`agent.sh`: `git push|merge|checkout|switch|rebase|reset|-C|config|diff --no-index|add -f|add --force`, `curl`, `npx`, `npm`, `pip`, `gh`, `WebFetch` i `WebSearch`;
     - `git commit --no-verify` i `git commit -n`, perquè el `commit-msg` no es pugui saltar;
     - `nucli finish|neteja|init|agent`;
     - les `prohibides` de `nucli.json`, i per a cada una que executa un script del repo amb camí relatiu, també les variants amb el camí absolut del checkout principal (`/…` i `~/…`) i amb `./`. Si no, quan apliquis la proposta del §7.1 (l'`allow` amb camí absolut), l'agent podria llançar l'script del checkout principal fora del sandbox;
     - totes les regles `allow` de Bash del projecte que apunten al checkout principal: són per a les teves sessions al checkout principal, i l'agent treballa al worktree.
   
   El log va a `.nucli/agent/<id>.json` del checkout principal.
4. **En acabar**:
   - `git worktree unlock`;
   - passa els checks `fora_sandbox` que toquin (el `smoke` del marcador) amb `nucli ship run` dins del worktree, i torna a intentar `ship seal`;
   - imprimeix un resum: el rebut, el cost, els torns i, si n'hi ha, el motiu d'aturada.
5. **Sense push, PR, deploy ni merge**. L'última línia és sempre:
   ```
   revisa-ho i, si et va bé: cd .claude/worktrees/<id> && nucli finish
   ```

### 5.5 Hooks de git (`core.hooksPath` → `githooks/` del nucli, els activa `nucli init`)

**Activació**
- `nucli init` els activa amb `git config core.hooksPath <camí real de githooks>`. Si el repo ja té un `core.hooksPath` (husky…), no el trepitja i t'ho diu.
- Si hi ha hooks propis a `.git/hooks/` (el marcador no en té), els del nucli els criden després dels seus.
- Sense `nucli.json` a l'arrel, no fan res.

**`pre-push`**
- Bloca qualsevol push a `refs/heads/<branca_base>`, també si és per esborrar-la.
- Sortida explícita: `NUCLI_MAIN=1 git push …`. Deixa passar el push i l'anota a `~/.nucli/excepcions.jsonl` (data, repo, branca, SHA) i a la sortida.

**`commit-msg`**
1. **Conventional Commits**: `^(tipus)(\(àmbit\))?!?: .+`, amb els tipus de `nucli.json`. Deixa passar els `Merge …`, `Revert "…"`, `fixup!` i `squash!` de git.
2. **Id de la tasca**: si la branca en porta un (`worktree-mt123` o `mt/mt123` → `mt123`, amb els prefixos de `nucli.json`), el missatge l'ha de contenir.
3. **Idioma**, amb una comprovació senzilla:
   - es treuen els trossos entre `` ` ``;
   - es compten, a l'assumpte, les paraules distintives d'anglès (`the`, `and`, `with`, `add`, `fix`…) i de castellà (`los`, `con`, `para`, `añade`, `y`…) contra les catalanes (`amb`, `els`, `per`, `dels`, `i`…);
   - si hi ha 3 paraules o més i les estrangeres guanyen, rebutja i mostra quines ha vist.
   
   Sortida: `NUCLI_IDIOMA=0` (anotada igual que `NUCLI_MAIN`).

**Sortides d'emergència**: només valen si es poden anotar a `~/.nucli/excepcions.jsonl`. Dins del sandbox, on `~/.nucli` no s'hi pot escriure, no es concedeixen: un agent no se les pot donar a si mateix.

### 5.6 Skill `tanca-sessio` (`skills/tanca-sessio/SKILL.md`, enllaçada a `~/.claude/skills/tanca-sessio`)

**Descripció** (què fa, quan i amb quines paraules):

> Tanca una sessió de treball en un repo amb `nucli.json`: extreu de la conversa les decisions, les trampes, les regles noves i l'estat, les escriu als docs que diu `nucli.json` i en fa commit, sense push. Usa-la quan l'usuari vulgui acabar o pausar la feina, amb frases com «tanca», «tanca la sessió», «hem acabat», «deixa-ho per avui», «plegem» o «ho deixem aquí».

**Passos**
1. Sense `nucli.json`, ho diu i s'atura.
2. Classifica el que ha passat a la sessió en quatre pilots:
   - **decisions**: en l'estil del fitxer adoptat; ADR numerat als repos nous, entrada datada al marcador;
   - **trampes**: símptoma · causa · com evitar-la;
   - **regles noves**: les **proposa** com a canvi de `nucli.json` o de convencions, sense aplicar-les;
   - **estat**: `docs/ESTAT.md` es reescriu sencer (ara · següent · bloquejat · data).
3. No duplica: busca abans el que ja hi ha. Els ids nous són el màxim del fitxer + 1.
4. Si algun d'aquests fitxers ja tenia canvis sense commit, t'ho diu i et pregunta abans de continuar.
5. Fa commit **només dels docs que ha tocat** (`git add <camins>`), amb `docs(sessio): tancament del AAAA-MM-DD` (+ `(<id>)` si la branca en porta). Passa pel `commit-msg`.
6. Acaba amb un resum de què ha escrit on. **Mai fa push.**

### 5.7 Mesura

- **Hook `PostToolUse`** global amb matcher `^Skill$`: `nucli hook us-skill`. Afegeix `{"data", "skill", "repo", "via": "claude"}` a `~/.nucli/us.jsonl`.
  - La skill surt de `tool_input.skill`. El repo és el nom del checkout principal, i surt del `cwd` de l'entrada, que segueix el worktree.
  - Només escriu si el `cwd` és d'un repo amb `nucli.json`.
- **Hook `UserPromptExpansion`** global (P6), sense matcher: el mateix `nucli hook us-skill`, que llegeix `command_name` i escriu la mateixa línia amb `"via": "usuari"`. Així es compten els `/skill` que obres tu.
- Els hooks de mesura no bloquegen mai: davant de qualsevol error surten amb 0 sense escriure res.
- **`nucli usage [--dies 30]`**:
  - mostra els usos per skill i per repo;
  - llista les skills instal·lades (`~/.claude/skills/*` i les `.claude/skills/*` del repo actual);
  - **marca les que no s'han obert** en el període.

### 5.8 `install.sh [--dry-run]`

**Què fa**
1. Enllaça `bin/nucli` → `~/.local/bin/nucli` (ja és al teu PATH).
2. Enllaça **cada** `skills/<nom>` → `~/.claude/skills/<nom>`. Si ja existeix i no és un enllaç del nucli, no el toca i t'ho diu.
3. Fusiona els tres hooks (`protegeix-rebuts`, `us-skill` a `PostToolUse` i a `UserPromptExpansion`) a `~/.claude/settings.json`:
   - abans, en fa una còpia de seguretat (`settings.json.nucli-AAAAMMDD-HHMMSS.bak`);
   - avui no hi tens cap hook;
   - no esborra ni reordena res i no afegeix duplicats (reconeix els seus per `nucli hook`);
   - comprova que el resultat sigui l'original més els hooks del nucli.
   
   Les ordres dels hooks porten el camí absolut, no depenen del PATH.

**`--dry-run`**: diu què faria i ensenya el diff del JSON.

**Límits**: no toca cap permís i no toca cap repo.

## 6. Què toca el nucli a cada repo (i res més)

| Fitxer | Què hi fa | Qui ho aplica |
|---|---|---|
| `docs/*.md` que falten | els crea des de plantilla | `nucli init` |
| `CLAUDE.md`, `AGENTS.md` | els crea si no existeixen; si existeixen, **proposta** a `.nucli/proposta/` | `init` / tu |
| `nucli.json` | el crea si no existeix | `init` (tu el revises) |
| `.gitignore` | + `.nucli/`, `.claude/worktrees/` | `init` |
| `.worktreeinclude` | el crea si no existeix | `init` |
| `.claude/settings.json` | + `Bash(nucli finish:*)` a `ask`; res més | `init` |
| `.git/config` | `core.hooksPath` | `init` |
| regles `allow` o de protecció noves, i les dels worktrees (§7.1) | només **proposta**, a `.nucli/proposta/permisos.md` | tu |

## 7. Trampes detectades abans de començar (el marcador)

1. **Les regles de ruta absolutes no cobreixen els worktrees. Condició per fer servir worktrees al marcador.**
   - `Edit(~/PROJECTS/MARCADOR/marcador/web/escut.png)`, `…/.mcp.json`, `…/scripts/llanca-sync.sh` i `…/web/config.js` protegeixen el checkout principal, **no** `.claude/worktrees/<id>/web/escut.png`. Les de `.env` sí que el cobreixen, perquè porten `**`.
   - El `denyWrite` del sandbox (`./…`) cobreix el Bash del worktree, però no l'eina Edit.
   - `Bash(bash scripts/llanca-sync.sh)` és a `allow` i a `excludedCommands` amb camí relatiu: en un worktree executaria **la còpia del worktree** sense preguntar i fora del sandbox.
   - Conseqüència: en **qualsevol** worktree (un `nucli agent`, però també un `claude --worktree` interactiu o un subagent amb `isolation: worktree`), Claude podria editar `.mcp.json` (la següent sessió en aquell worktree carregaria la URL canviada) o `scripts/llanca-sync.sh` i després executar-lo. **Això seria afluixar la mp45.**
   - **Condició**: al marcador no es fa servir cap worktree de Claude Code (ni `nucli agent`, ni `claude --worktree`, ni subagents aïllats) fins que les regles de sota siguin al `.claude/settings.json` **d'`origin/main`** (un worktree llegeix el `settings.json` de la base, no el del checkout principal). `nucli init` ho comprova, t'ho avisa i deixa la proposta a `.nucli/proposta/permisos.md`; `nucli agent` es nega a arrencar mentre falti res.
   - Proposta per al marcador (la genera `nucli init`; l'apliques tu, en un commit propi, que passarà per `revisio-config`):
     - `deny`, afegir: `Edit(~/PROJECTS/MARCADOR/marcador/.claude/worktrees/**/web/config.js)`, `…/.claude/worktrees/**/web/escut.png`, `…/.claude/worktrees/**/.mcp.json` i `…/.claude/worktrees/**/scripts/llanca-sync.sh`;
     - `allow`, substituir `Bash(bash scripts/llanca-sync.sh)` per `Bash(bash /Users/<usuari>/PROJECTS/MARCADOR/marcador/scripts/llanca-sync.sh)`;
     - `sandbox.excludedCommands`, substituir `bash scripts/llanca-sync.sh` per `bash /Users/<usuari>/PROJECTS/MARCADOR/marcador/scripts/llanca-sync.sh`. Sense aquest canvi, la invocació absoluta correria dins del sandbox i el sync fallaria.
     
     A partir d'aquí, el sync es llança amb el camí absolut. Cap d'aquests canvis no afluixa res: afegeixen `deny` o estrenyen un `allow` i una exclusió del sandbox.
   - **Verificat el 29/9/2026** amb `claude -p --worktree` (Haiku) en un repo de prova: amb només `Edit(//<repo>/web/config.js)` a `deny`, Claude va editar `web/config.js` dins del worktree sense cap denegació. Amb la regla que proposa el nucli (`Edit(//<repo>/.claude/worktrees/**/web/config.js)`) pujada a la base, l'Edit va quedar denegat i el fitxer no va canviar. Al clon del marcador, amb les regles reancorades al camí del clon, `nucli init` en treu exactament la proposta de sobre.
   - `bash scripts/deploy.sh` també és a `excludedCommands` amb camí relatiu, però no té `allow`: en un worktree et demanaria permís. `init` ho avisa sense bloquejar.
   - `nucli agent` afegeix a `--disallowedTools` les variants absolutes de les `prohibides` i els `allow` de Bash ancorats al checkout principal (§5.4), perquè l'`allow` absolut nou no obri res a l'agent.
2. **`nucli finish` des del Bash de Claude al marcador** correria dins del sandbox, sense xarxa, i el push fallaria. Falla tancat, i està bé. Es llança al terminal o amb `! nucli finish`. **No** l'afegeixo a `excludedCommands`: seria afluixar.
3. **La base del worktree és `origin/main`**: el commit de `nucli init` s'ha de fusionar (PR) abans que `ship` i `agent` funcionin.
4. **El `.venv` no és al worktree**: les ordres de check hi arriben amb `$NUCLI_ARREL/.venv`.
5. **`claude -p --worktree` deixa el worktree bloquejat**: el desbloqueja `nucli agent`.
6. **La mesura amb `PostToolUse` no veu els `/skill` escrits a mà** (P6).

## 8. Pla per fases

Cada fase acaba amb els tests en verd (pytest amb el `.venv` + `compileall` i `--help` amb el Python 3.9) i **un commit** (Conventional Commits, en català). Les proves contra el marcador es fan sobre un **clon local al directori temporal** (`git clone` només copia el que és a git, sense `.env`). **Mai sobre l'original.**

| Fase | Contingut | Tests / criteri de fet | Commit |
|---|---|---|---|
| F0 | Esquelet: `bin/nucli` + paquet, lectura de `nucli.json` (del checkout principal, també des d'un worktree), cerca de l'arrel, `.gitignore`, `.venv` de proves, aquest document | `nucli --help`; fora d'un repo amb `nucli.json`, les ordres pleguen | `build: esquelet del nucli i especificació` |
| F1 | `nucli init` (docs): detecció, adopció, plantilles, `CLAUDE.md`/`AGENTS.md` o proposta, `nucli.json`, `--dry-run`, idempotència | init sobre un repo buit i sobre el clon del marcador: no toca cap fitxer existent, proposa les fusions, crea només `docs/ESTAT.md` i `docs/TRAMPES.md`, i la segona passada no fa res | `feat(init): docs adoptats, CLAUDE.md i AGENTS.md curts i nucli.json` |
| F2 | `ship plan/run/seal`, `finish`, hook `protegeix-rebuts`; `init` afegeix `.nucli/` i la regla `ask` | **classificador** (només docs → cap; `*.py`; `web/**`; migracions; renomenats i esborrats; sense regla → per defecte; `nucli.json` → `revisio-config`; regles llegides del checkout principal i no del worktree); **segell** (arbre brut, check fallit, check sobre un arbre diferent de HEAD, sense executar); **refusos de finish** (sense rebut, sense segell, HEAD canviat, `sha256` alterat, check fallit, branca base, manuals sense TTY, **re-execució fallida contra HEAD → no hi ha push**, check que embruta l'arbre) i el camí bo amb un remot *bare* i `gh` simulat; la inserció a `settings.json` conserva la resta byte a byte | `feat(ship): porta amb rebut i nucli finish` |
| F3 | `.claude/worktrees/` al `.gitignore`, `.worktreeinclude`, `nucli port`, `nucli neteja`, **anàlisi de permisos per als worktrees** a `init` (§5.1 pas 6) | port estable i dins del rang; neteja: fusionat per història, *squash* (`gh` simulat), brut, bloquejat, `--dry-run`; permisos: regles ancorades amb i sense cobertura, `allow` relatiu, proposta aplicada només al checkout principal, a la base, al local i a l'usuari. Sobre el clon del marcador (amb les regles reancorades al clon), `init` treu exactament la proposta del §7.1 | `feat(worktree): aïllament natiu, port estable i neteja` |
| F4 | `nucli agent` | amb `claude` simulat: es nega a arrencar amb permisos pendents; arguments exactes (allowed/disallowed/strict-mcp, variants absolutes de les `prohibides`), prompt, desbloqueig, checks `fora_sandbox`, missatge final. Sense cridar el `claude` real (té cost): la prova real la fas tu | `feat(agent): nucli agent, versió general d'agent.sh` |
| F5 | `githooks/pre-push`, `githooks/commit-msg`, `core.hooksPath` a `init` | push a main bloquejat / amb `NUCLI_MAIN=1` i anotat; missatges vàlids i invàlids (tipus, id de la branca, anglès, castellà, codi entre `` ` ``); encadenament amb hooks existents; sense `nucli.json` no fan res | `feat(githooks): pre-push protegeix main i commit-msg valida el format` |
| F6 | Skill `tanca-sessio` | frontmatter vàlid, descripció < 1.536 caràcters, instruccions coherents amb `nucli.json` (revisió manual) | `feat(skills): tanca-sessio` |
| F7 | Hook `us-skill` (`PostToolUse` i `UserPromptExpansion`), `nucli usage` | entrada simulada de tots dos esdeveniments (dins i fora d'un repo amb `nucli.json`), finestra de 30 dies, skills sense ús | `feat(us): mesura d'ús de les skills` |
| F8 | `install.sh [--dry-run]` | contra un `HOME` temporal: enllaços, còpia de seguretat, fusió sense perdre res, idempotència | `build(install): install.sh amb --dry-run` |

Després de la F8:
- `gh repo create nucli --private --source=. --push`;
- et dono les ordres d'instal·lació i de prova al marcador, dient per a cadascuna si va al **terminal del Mac**, al **xat de Claude Code** o amb **`!` dins de Claude Code**.

## 9. Preguntes (decidides a la n478)

Resum de les decisions: **P1 = A**, **P2** segons la recomanació, **P3 = sí** (`web/**` → `lint + smoke + visual`), **P4** confirmar-los a `finish`, **P5** només `worktree-*`, **P6 = sí**, **P7** mantenir `revisio-config`, **P8** segons la recomanació. Cap d'aquestes decisions no afluixa la mp45.

- **P1 · `CLAUDE.md` del marcador (183 línies).**
  - (A) Afegir-hi un bloc «Nucli» d'unes 10 línies que apunti a `nucli.json`, als docs i al cicle, i deixar la resta com està.
  - (B) Aprimar-lo a menys de 40 línies traient seccions a `docs/`.
  
  **Recomano A** per a la v0.1: B és moure contingut, i ho has prohibit. Si el vols, B es fa després com a tasca pròpia. El mateix per a `AGENTS.md`.
- **P2 · Rols del marcador.**
  - Arquitectura → adoptar `INFORME_TECNIC.md`.
  - Convencions → `CLAUDE.md#Convencions`.
  - Trampes → crear `docs/TRAMPES.md` per a les noves, amb una línia que apunti a «Lliçons apreses» de `CLAUDE.md` (sense moure-les).
  - Estat → crear `docs/ESTAT.md`.
  
  **Recomano** això: evita dos documents que diguin el mateix (la teva regla de coherència de la documentació).
- **P3 · Checks del marcador.** Al marcador no hi ha linter de Python, i la REGLA ZERO 2 prohibeix eines noves: `lint` = `check.sh`.
  
  **Recomano afegir `smoke` a `web/**`**: la definició de fet de `CLAUDE.md` l'exigeix. Si es fa, `web/**` → `lint + smoke + visual`.
- **P4 · Checks manuals.** Es confirmen a `nucli finish`, en un terminal, i no bloquegen el segell.
  
  L'alternativa és una ordre `nucli ship ok <check>`, però aleshores un agent també la podria fer. **Recomano** confirmar-los a `finish`.
- **P5 · `nucli neteja` i branques.** Només `worktree-*`, o totes les fusionades? Al marcador tens `feature/*` i `hotfix/*`.
  
  **Recomano** només `worktree-*` a la v0.1.
- **P6 · Mesura dels `/skill` escrits a mà.** Afegir també un hook `UserPromptExpansion` (camp `command_name`), perquè `PostToolUse` només veu les skills que obre Claude.
  
  **Recomano sí**: és la mateixa línia a `us.jsonl` amb `"via": "usuari"`.
- **P7 · `revisio-config`.** És el check manual automàtic quan una branca toca `nucli.json`, `.claude/**`, `.mcp.json`, `.worktreeinclude`, `.gitignore` o `githooks/**`. No me l'has demanat.
  
  **Recomano mantenir-lo**: és el principi (e) aplicat a la porta.
- **P8 · On viu el nucli.** El repo a `~/PROJECTS/nucli` a cada Mac, i `core.hooksPath` apunta al camí real d'aquest clon. Si el mous, `nucli init` es torna a executar i ho corregeix.

## 10. Fora de la v0.1

- Revisió visual automàtica.
- Repo de docs multi-repo.
- Base de dades per worktree.
- Integració a la CI.
- Moure tasques entre seccions de `TASQUES.md` (es queda a `agent.sh`).
- Fer servir el nucli dins del mateix repo `nucli`.
