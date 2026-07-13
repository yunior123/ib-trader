#!/bin/zsh
cd "$(dirname "$0")/.."
# Samsung Elec (KRX 005930) — TERREMOTO / deteccion-only (creado 2026-07-12).
# Datos: korea_bar_bridge.py (IBKR KRX realtime, sub Korea waived cubre la API;
# ver [[ibkr-account-facts]]). Sigue data/bars_samsung.txt. Motor de ENTRADAS
# APAGADO hasta pasar WR-70 + OOS (regla ship, orden #7); banner AMBAS
# direcciones. Es el mercado de memoria/DRAM: lider ~13h antes que MU/DRAM US.
export SAMSUNG_QUAKE_BANNER=1
# umbral PROVISIONAL (sin backtest KRX aun) — calibrar con historial real:
export SAMSUNG_QUAKE_MIN=0.02
# entradas OFF: score imposible (max real 1.0) => nunca arma compra; shorts 0
export SAMSUNG_SCORE_MIN=9
while true; do
  pkill -x samsung_signal_bot 2>/dev/null
  sleep 1
  ./samsung_signal_bot >> samsung_signals.log 2>&1
  echo "$(date) samsung_signal_bot salio; relanzando" >> samsung_signals.log
  sleep 30
done
