#!/bin/zsh
cd "$(dirname "$0")/.."
# SOX index feed keepalive (2026-07-16). Nivel del indice para sirenas.
# PORTERO DE PROVEEDOR (2026-08-03): sox_index_feed.py es IBKR puro (`from ib_insync import
# IB, Index`, scripts/sox_index_feed.py:14). Sin Gateway se pasa la vida arrancando un
# interprete para estrellarse contra un puerto cerrado: 24.091 relanzados y 21 MB de
# logs/sox_feed.log. El codigo IBKR se QUEDA intacto: vuelve solo con market_source=ibkr.
while true; do
  MARKET_SOURCE="$(cat data/market_source.txt 2>/dev/null || echo ibkr)"
  if [[ "$MARKET_SOURCE" != "ibkr" ]]; then
    # Una linea por hora, no una cada 31 s: es un estado ESPERADO, no una alarma.
    if [[ ! -f data/.sox_gated_at ]] || (( $(date +%s) - $(stat -f %m data/.sox_gated_at) > 3600 )); then
      echo "$(date) sox_feed EN PAUSA: market_source=$MARKET_SOURCE (feed IBKR apagado); vuelve solo con 'ibkr'" >> logs/sox_feed.log
      touch data/.sox_gated_at
    fi
    sleep 300
    continue
  fi
  rm -f data/.sox_gated_at
  pkill -f "scripts/sox_index_feed.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/sox_index_feed.py >> logs/sox_feed.log 2>&1
  echo "$(date) sox_feed salio; relanzando" >> logs/sox_feed.log
  sleep 30
done
