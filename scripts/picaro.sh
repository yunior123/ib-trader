#!/bin/zsh
# picaro.sh — recetas Finviz Elite listas para disparar (2026-07-17).
# Uso: ./scripts/picaro.sh <receta> [n]   (n = filas, default 15)
#      ./scripts/picaro.sh list
# Señal-solamente: esto ENCUENTRA candidatos; el print de precio decide (playbook).
cd "$(dirname "$0")/.." || exit 1
source config/feeds.env 2>/dev/null
AUTH="${FINVIZ_AUTH3:-$FINVIZ_AUTH}"
[[ -z "$AUTH" ]] && { echo "SIN TOKEN (feeds.env)"; exit 1; }
N="${2:-15}"

# registro: nombre|filtros|orden|descripcion
typeset -A RECIPES DESC ORDER
# — las recetas se cargan de data/picaro_recipes.txt (editable sin tocar codigo)
while IFS='|' read -r name filt ord desc; do
  [[ "$name" == \#* || -z "$name" ]] && continue
  RECIPES[$name]="$filt"; ORDER[$name]="$ord"; DESC[$name]="$desc"
done < data/picaro_recipes.txt

if [[ "$1" == "list" || -z "$1" ]]; then
  echo "recetas pícaras disponibles:"
  for k in ${(k)RECIPES}; do printf "  %-16s %s\n" "$k" "${DESC[$k]}"; done
  exit 0
fi
F="${RECIPES[$1]}"
[[ -z "$F" ]] && { echo "receta desconocida: $1 (./scripts/picaro.sh list)"; exit 1; }
O="${ORDER[$1]:+&o=${ORDER[$1]}}"
curl -s --max-time 20 "https://elite.finviz.com/export/screener?v=152&f=${F}${O}&auth=${AUTH}&c=1,6,25,30,61,64,65,66,67,68" \
  | head -$((N+1)) | column -s, -t | sed 's/"//g'
