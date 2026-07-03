#!/bin/zsh
export SKHYNIX_KRX=1   # sesion KRX (open 9:00 KST) para motor v6
cd "$(dirname "$0")/.."
# SK Hynix (KRX 000660) — TERREMOTO / deteccion-only (creado 2026-07-12).
# Datos: korea_bar_bridge.py (IBKR KRX realtime, sub Korea waived cubre la API;
# ver [[ibkr-account-facts]]). Sigue data/bars_skhynix.txt. Motor de ENTRADAS
# APAGADO hasta pasar WR-70 + OOS (regla ship, orden #7); banner AMBAS
# direcciones. Es el mercado de memoria/DRAM: lider ~13h antes que MU/DRAM US.
export SKHYNIX_QUAKE_BANNER=1
# umbral PROVISIONAL (sin backtest KRX aun) — calibrar con historial real:
export SKHYNIX_QUAKE_MIN=0.02
# entradas OFF: score imposible (max real 1.0) => nunca arma compra; shorts 0
export SKHYNIX_SCORE_MIN=9
while true; do
  pkill -x skhynix_signal_bot 2>/dev/null
  sleep 1
  bots/skhynix_signal_bot >> logs/skhynix_signals.log 2>&1
  echo "$(date) skhynix_signal_bot salio; relanzando" >> logs/skhynix_signals.log
  sleep 30
done
