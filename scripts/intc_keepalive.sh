#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 31T 23W WR74% +25.8% pf2.1 (OOS 73%)
export INTC_BB_STD=3.0
export INTC_RSI_OS=35
export INTC_VOL_MULT=1.0
export INTC_TARGET=4
export INTC_TRAIL_ATR=3
export INTC_STOP=8
export INTC_TIME_STOP_MIN=240
export INTC_SKIP_OPEN=5
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# live: gate de spread NBBO + umbral whale (v3)
export INTC_SPREAD_MAX=0.3
export INTC_WHALE_USD=250000
while true; do
  pkill -x intc_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read INTC" 2>/dev/null
  sleep 1
  ./intc_signal_bot >> intc_signals.log 2>&1
  echo "$(date) intc_signal_bot salio; relanzando" >> intc_signals.log
  sleep 30
done
