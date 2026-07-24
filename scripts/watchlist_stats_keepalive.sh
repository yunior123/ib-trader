#!/bin/zsh
cd "$(dirname "$0")/.."
# watchlist_stats keepalive (2026-07-24). Estadísticas TradingView-like
# (%cambio del día vs cierre previo REAL + volumen del día) para la lista del
# cockpit -> data/watchlist_stats.json. Fuentes realtime: Finnhub /quote +
# barras IBKR de la flota (fallback Finviz Elite). Señal-solamente; jamás delayed.
while true; do
  python3 scripts/watchlist_stats.py --loop >> watchlist_stats.log 2>&1
  echo "$(date) watchlist_stats salio; relanzando" >> watchlist_stats.log
  sleep 30
done
