#!/bin/zsh
cd "$(dirname "$0")/.."
# CPER (cobre) — TERREMOTO bot (orden Yunior 2026-07-11 "maybe copper too").
# ETF fino en IEX (~64 bars/dia): bars escasos, el CUSUM opera sobre lo que
# imprime. Solo deteccion banner AMBAS direcciones; entradas OFF (WR-70 gate).
export CPER_QUAKE_BANNER=1
# umbral 90d, metrica OFICIAL flota (no-retrace>50% en 30min): precision
# 100% (n=64), 5.0 alertas/sem
export CPER_QUAKE_MIN=0.01
export CPER_SCORE_MIN=9
while true; do
  pkill -x cper_signal_bot 2>/dev/null
  sleep 1
  ./cper_signal_bot >> cper_signals.log 2>&1
  echo "$(date) cper_signal_bot salio; relanzando" >> cper_signals.log
  sleep 30
done
