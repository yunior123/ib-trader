#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 49T 40W WR82% +14.2% pf1.4 (OOS 89% +10.6%)
export AAPL_BB_STD=2.0
export AAPL_RSI_OS=30
export AAPL_VOL_MULT=1.0
export AAPL_TARGET=4
export AAPL_TRAIL_ATR=2
export AAPL_STOP=4
export AAPL_TIME_STOP_MIN=0
export AAPL_SKIP_OPEN=5
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP97/DOWN99%, umbral por ticker)
export AAPL_QUAKE_BANNER=1
export AAPL_QUAKE_MIN=0.015
# live: gate de spread NBBO + umbral whale (v3)
export AAPL_SPREAD_MAX=0.3
export AAPL_WHALE_USD=250000
while true; do
  pkill -x aapl_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read AAPL" 2>/dev/null
  sleep 1
  ./aapl_signal_bot >> aapl_signals.log 2>&1
  echo "$(date) aapl_signal_bot salio; relanzando" >> aapl_signals.log
  sleep 30
done
