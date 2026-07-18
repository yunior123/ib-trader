#!/bin/zsh
export KOSPI_KRX=1   # sesion KRX (open 9:00 KST) para motor v6
cd "$(dirname "$0")/.."
# KOSPI (proxy KODEX 200 ETF, KRX 069500) — TERREMOTO / deteccion-only
# (creado 2026-07-12, orden "earthquake alert for kospi, down or up").
# Datos: korea_bar_bridge.py (IBKR KRX realtime; el indice K200 no tiene sub
# API -> usamos el ETF que ES accion). Banner AMBAS direcciones; sin entradas.
export KOSPI_QUAKE_BANNER=1
# umbral PROVISIONAL — un indice se mueve menos que una accion; calibrar:
export KOSPI_QUAKE_MIN=0.01
export KOSPI_SCORE_MIN=9
while true; do
  pkill -x kospi_signal_bot 2>/dev/null
  sleep 1
  ./kospi_signal_bot >> kospi_signals.log 2>&1
  echo "$(date) kospi_signal_bot salio; relanzando" >> kospi_signals.log
  sleep 30
done
