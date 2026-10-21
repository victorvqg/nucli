# nucli

El nucli fa que els agents de codi (Claude Code, Kimi, Codex) treballin igual i de forma fiable a tots els projectes. Són tres coses: uns **docs** amb el mateix nom a cada repo, una **porta amb rebut** (no es puja res sense haver passat els checks que toquen, i ho demostra un rebut segellat contra el commit) i un **cicle** que fan tots els agents. El que canvia de projecte a projecte és a `nucli.json`, i el nucli només hi posa el mecanisme.

## El flux de treball

Cada canvi neix d'una fitxa, que és un issue de GitHub, i arriba a la web per un PR que els agents de Claude escriuen i proven dins d'unes barreres que es comproven soles.

Tu només hi intervens en tres moments:

1. **Escrius la fitxa:** el què i un criteri de fet que es pugui comprovar.
2. **Aproves el pla:** contestes les preguntes de l'agent i poses `estat: aprovada`.
3. **Fusiones:** després de la CI i del revisor. Només tu pots, perquè `main` està protegida.

```mermaid
flowchart TD
    A["1 · Escrius la fitxa<br/>estat: nova"] --> Z{"Toca una zona<br/>delicada?"}
    Z -- "sí" --> I["Camí interactiu<br/>tu + Claude Code"]
    Z -- "no" --> B["2 · L'agent proposa un pla<br/>estat: pla-proposat"]
    B --> C["3 · Respons i aproves<br/>estat: aprovada"]
    C --> D["4 · L'agent escriu el codi<br/>dins de les barreres"]
    D --> E["5 · L'app obre el PR<br/>estat: pr i avís per Telegram"]
    E --> F["6 · La CI ho comprova tot"]
    I --> F
    F --> G["7 · El revisor llegeix el PR"]
    G -- "defectes" --> H["8 · Ajustos amb @claude<br/>màxim 2 voltes per PR"]
    H --> F
    G -- "tot bé" --> J["9 · Fusiones"]
    J --> K["10 · Es publica la web<br/>i la fitxa es tanca"]

    classDef tu stroke:#0E6A86,stroke-width:3px
    classDef agent stroke:#2C7A4B,stroke-width:2px
    class A,C,J tu
    class B,D,E,G,H agent
```

Les caselles amb la vora blava són els tres moments en què intervens tu. Les verdes són els agents.

## Instal·lació

Cal un Mac amb `git`, `python3` (n'hi ha prou amb el 3.9 de macOS, perquè només fa servir la biblioteca estàndard) i Claude Code. Les ordres que parlen amb GitHub també necessiten `gh`.

```bash
git clone https://github.com/victorvqg/nucli.git
cd nucli
./install.sh --dry-run   # diu què faria, sense escriure res
./install.sh
```

`install.sh` s'executa un cop a cada Mac i no toca cap repo ni cap permís:

- enllaça `bin/nucli` a `~/.local/bin/nucli` (aquesta carpeta ha de ser al `PATH`);
- enllaça les skills de `skills/` a `~/.claude/skills/`;
- afegeix els hooks del nucli a `~/.claude/settings.json`, amb una còpia de seguretat abans.

Si un destí ja existeix i no és del nucli, no el toca i t'ho diu. Si mous el clon, torna'l a executar.

Després, a cada repo: `nucli init --dry-run` per veure què farà, i `nucli init` per fer-ho. No fa commit: t'ho deixa per revisar.

## Ordres

| Ordre | Què fa |
|---|---|
| `nucli init` | Prepara el repo: docs, `nucli.json`, `.gitignore`, permisos i hooks. |
| `nucli tasca N` | Comença l'issue #N: crea la branca `issue/N-…` des de la base i el posa `estat: en-curs`. |
| `nucli agent N` | Llança un agent sense interfície en un worktree nou per fer l'issue #N. |
| `nucli ship plan` | Diu quins checks toquen, segons els fitxers que canvia la branca. |
| `nucli ship run <check>` | Executa un check i en desa el resultat al rebut. |
| `nucli ship seal` | Segella el rebut contra HEAD si els checks requerits són en verd. |
| `nucli finish` | Només tu, al terminal: ensenya el diff, demana confirmació, passa els checks, segella, puja la branca i obre el PR. |
| `nucli rebut markdown` | Escriu el rebut segellat en markdown, el mateix que va al PR (també per a la CI). |
| `nucli port` | Dona el port estable d'aquest worktree (4100–4999). |
| `nucli neteja` | Només tu: treu els worktrees fusionats i esborra les branques locals ja fusionades. |
| `nucli secret NOM --env ENTORN` | Només tu, al terminal: desa a GitHub un valor del `.env` sense ensenyar-lo. |
| `nucli usage` | Ensenya l'ús de les skills, per skill i per repo, i les que no s'han obert. |

## Més detall

- [docs/FLUX.md](docs/FLUX.md): el flux pas a pas, el camí interactiu, les barreres dels agents, els límits del dia i com escriure una bona fitxa.
- [docs/NUCLI.md](docs/NUCLI.md): l'especificació del nucli, ordre per ordre, i el registre de canvis.
