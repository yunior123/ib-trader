#!/bin/zsh
# keepalive del NBBO por WebSocket de LSE (scripts/lse_price_alarm_feed.py).
#
# POR QUE (medido 2026-08-24): el WS NO gasta cuota REST — con la cuota diaria (15.000)
# agotada seguia sirviendo bid/ask vivos. provider_bridge pedia el NBBO por REST cada 7 s
# para 36 simbolos: mataba la cuota en menos de una hora y dejaba el ib-trader ONLINE
# congelado en las barras del viernes. El pulso vivo sale de aqui; el REST solo para historia.
cd "$(dirname "$0")/.."

LOG=logs/lse_price_alarm_feed.log
FAILS=0

while true; do
  pkill -f "scripts/lse_price_alarm_feed.py" 2>/dev/null
  sleep 1
  SYMS=$(tr -s ' \n' ',' < data/fleet.txt | sed 's/^,//;s/,$//')
  START=$(date +%s)
  ./venv/bin/python scripts/lse_price_alarm_feed.py --symbols "$SYMS" >> "$LOG" 2>&1
  RAN=$(( $(date +%s) - START ))
  echo "$(date) lse_price_alarm_feed salio tras ${RAN}s; relanzando" >> "$LOG"
  if (( RAN < 15 )); then
    FAILS=$((FAILS + 1))
    if (( FAILS >= 3 )); then
      echo "$(date) NBBO WS EN CRASH-LOOP (3 muertes en <15s) — la flota se queda sin pulso" >> "$LOG"
      ./scripts/speak.sh DANGER "El feed de precios por websocket esta en crash loop." 2>/dev/null
      FAILS=0
    fi
  else
    FAILS=0
  fi
  sleep 5
done
