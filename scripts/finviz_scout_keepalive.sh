#!/bin/zsh
IBT_OSA="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/osa_gate"  # portero: respeta data/notify_off
cd "$(dirname "$0")/.."
# finviz_scout keepalive (2026-07-17). Datos Finviz Elite premarket/RTH
# (short float, gap, rel vol, earnings, target/recom) -> data/finviz_*.txt.
# Señal-solamente. Lanzado por fleet_keepalive_start.sh (respeta fleet_sleep).
# anti-crash-loop (2026-07-29): 10 banners "sin token" en 5 min — muertes rapidas
# consecutivas = GRITAR una vez y backoff 10 min, no un banner por relanzamiento
FAILS=0
INCIDENT="data/finviz_crash_notified"
while true; do
  pkill -x finviz_scout 2>/dev/null
  sleep 1
  T0=$(date +%s)
  bin/finviz_scout >> logs/finviz_scout.log 2>&1
  DUR=$(( $(date +%s) - T0 ))
  echo "$(date) finviz_scout salio tras ${DUR}s; relanzando" >> logs/finviz_scout.log
  if (( DUR < 60 )); then
    FAILS=$((FAILS+1))
    if (( FAILS >= 3 )); then
      if [ ! -e "$INCIDENT" ]; then
        "$IBT_OSA" -e 'display notification "finviz_scout muere al arrancar (3+ seguidas) — backoff 10 min. Revisar logs/finviz_scout.log" with title "🔴 FINVIZ CRASH-LOOP" sound name "Sosumi"' 2>/dev/null
        : > "$INCIDENT"
      fi
      sleep 600
      FAILS=0
      continue
    fi
  else
    FAILS=0
    rm -f "$INCIDENT"
  fi
  sleep 30
done
