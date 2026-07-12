#!/bin/zsh
cd "$(dirname "$0")/.."
# fleet_executor — capa de EJECUCION con ETFs apalancados (orden Yunior
# 2026-07-11). IBKR primario (TFSA U26942420), Alpaca PAPER fallback.
# Reglas: bull = comprar con BUY, vender SOLO mas arriba (+1%), si no BOLSA
# con GTC de recuperacion; bear = comprar con BUY PUT, stop GTC -5%, sin bolsa.
# ARMADO: existe data/etf_armed => opera cuando NetLiq >= 450 USD.
# KILL SWITCH: rm data/etf_armed (pasa a dry-run al instante).
while true; do
  pkill -f "scripts/fleet_executor.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/fleet_executor.py >> fleet_executor.log 2>&1
  echo "$(date) fleet_executor salio; relanzando" >> fleet_executor.log
  sleep 30
done
