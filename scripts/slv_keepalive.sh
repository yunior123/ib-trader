#!/bin/zsh
cd "$(dirname "$0")/.."
# SLV (plata) — TERREMOTO bot (orden Yunior 2026-07-11 "add bot for silver...
# choose the fastest api websocket, all in c++"): ws = el ws mas
# rapido medido (quotes crypto ~0-30ms vs finnhub ~135ms; polygon sin ws).
# Solo deteccion banner AMBAS direcciones; entradas OFF hasta WR-70 + OOS.
export SLV_QUAKE_BANNER=1
# umbral 90d, metrica OFICIAL flota (no-retrace>50% en 30min): precision
# 94% (n=106), 8.2 alertas/sem <=10; control GLD@0.01 = 95%
export SLV_QUAKE_MIN=0.02
export SLV_SCORE_MIN=9
while true; do
  pkill -x slv_signal_bot 2>/dev/null
  sleep 1
  ./slv_signal_bot >> slv_signals.log 2>&1
  echo "$(date) slv_signal_bot salio; relanzando" >> slv_signals.log
  sleep 30
done
