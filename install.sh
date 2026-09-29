#!/usr/bin/env bash
# install.sh [--dry-run] — instal·la el nucli en aquest Mac. Un cop per Mac; no toca cap repo ni cap permís.
#
#   1. enllaça bin/nucli → ~/.local/bin/nucli
#   2. enllaça cada skills/<nom> → ~/.claude/skills/<nom> (no toca les altres skills)
#   3. fusiona els hooks del nucli a ~/.claude/settings.json (amb còpia de seguretat, sense duplicats)
#
# Si un destí ja existeix i no és un enllaç del nucli, no el toca i t'ho diu. Si el clon del nucli s'ha mogut,
# torna'l a executar: actualitza els enllaços i els camins dels hooks. Amb --dry-run només diu què faria.
set -euo pipefail

SEC=0
case "${1:-}" in
  "") ;;
  --dry-run) SEC=1 ;;
  *) echo "ús: install.sh [--dry-run]" >&2; exit 2 ;;
esac

NUCLI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
AVISOS=0

# enllaça <origen> <destí> <sufix que identifica un enllaç del nucli, p. ex. bin/nucli>
enllaca() {
  local origen="$1" desti="$2" sufix="$3" actual
  if [ -L "$desti" ]; then
    actual="$(readlink "$desti")"
    if [ "$actual" = "$origen" ]; then
      echo "  ja hi és  $desti"
      return
    fi
    # un enllaç a un altre clon del nucli (o a un que ja no hi és) s'actualitza; qualsevol altra cosa, no
    if [[ "$actual" == */"$sufix" ]] && { [ ! -e "$actual" ] || [ -f "$(dirname "$actual")/../nucli/__init__.py" ]; }; then
      echo "  actualitza $desti → $origen (abans $actual: el nucli s'ha mogut)"
      [ "$SEC" = 1 ] || ln -sfn "$origen" "$desti"
      return
    fi
  fi
  if [ -e "$desti" ] || [ -L "$desti" ]; then
    echo "  avís      $desti ja existeix i no és un enllaç del nucli: no el toco"
    AVISOS=$((AVISOS + 1))
    return
  fi
  echo "  enllaça   $desti → $origen"
  if [ "$SEC" = 0 ]; then
    mkdir -p "$(dirname "$desti")"
    ln -s "$origen" "$desti"
  fi
}

echo "nucli · install.sh · $NUCLI$([ "$SEC" = 1 ] && echo "  (--dry-run: no s'escriu res)")"
echo "Ordre:"
enllaca "$NUCLI/bin/nucli" "$HOME/.local/bin/nucli" "bin/nucli"
echo "Skills:"
for skill in "$NUCLI"/skills/*/; do
  nom="$(basename "$skill")"
  enllaca "$NUCLI/skills/$nom" "$HOME/.claude/skills/$nom" "skills/$nom"
done
echo "Hooks de Claude Code (~/.claude/settings.json):"
if [ "$SEC" = 1 ]; then
  "$NUCLI/bin/nucli" intern fusiona-ganxos --dry-run
else
  "$NUCLI/bin/nucli" intern fusiona-ganxos
fi

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "  avís      ~/.local/bin no és al PATH: afegeix-l'hi per poder escriure «nucli»"; AVISOS=$((AVISOS + 1)) ;;
esac
[ "$AVISOS" = 0 ] || echo "Avisos: $AVISOS. Llegeix-los a dalt."
if [ "$SEC" = 1 ]; then
  echo "Res escrit. Per instal·lar-lo: $NUCLI/install.sh"
else
  echo "Fet. No he tocat cap repo ni cap permís: a cada repo, «nucli init --dry-run» i després «nucli init»."
fi
