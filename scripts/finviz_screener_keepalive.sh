#!/bin/zsh
# Supervisor genérico para las tres instancias Finviz Elite.
cd "$(dirname "$0")/.." || exit 1
SCREEN=${1:?uso: finviz_screener_keepalive.sh buffett|squeeze|momentum}
case "$SCREEN" in buffett|squeeze|momentum) ;; *) echo "screen inválido: $SCREEN" >&2; exit 2;; esac

# Separar peticiones del scout y entre screeners: menos ráfagas, diagnósticos más limpios.
case "$SCREEN" in buffett) sleep 15;; squeeze) sleep 35;; momentum) sleep 55;; esac
FAILS=0
while true; do
  T0=$(date +%s)
  bin/finviz_screener_watch --screen "$SCREEN" >> "logs/finviz_${SCREEN}.log" 2>&1
  DUR=$(( $(date +%s) - T0 ))
  echo "$(date) finviz_${SCREEN} salió tras ${DUR}s" >> "logs/finviz_${SCREEN}.log"
  if (( DUR < 60 )); then FAILS=$((FAILS+1)); else FAILS=0; fi
  (( FAILS >= 3 )) && { sleep 600; FAILS=0; } || sleep 30
done
