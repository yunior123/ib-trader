#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 31T 23W WR74% +25.8% pf2.1 (OOS 73%)
export INTC_BB_STD=3.0
export INTC_RSI_OS=35
export INTC_VOL_MULT=1.2
export INTC_TARGET=8.0
export INTC_TRAIL_ATR=5
export INTC_STOP=8
export INTC_TIME_STOP_MIN=240
export INTC_SKIP_OPEN=0
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# LADO CORTO optimizado (sweep independiente 2026-07-11): cortos trend FULL26 255T 205W WR80% +106.4% pf2.1 (OOS +53.5% 83%)
export INTC_SHORTS=1
export INTC_S_MODE=trend
export INTC_S_TREND_CUSUM=0.015
export INTC_S_TARGET=1.5
export INTC_S_STOP=4
export INTC_S_TRAIL=2
export INTC_S_TSTOP=120
export INTC_S_FLOOR=0.25
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP94/DOWN99%, umbral por ticker)
export INTC_QUAKE_BANNER=1
export INTC_QUAKE_MIN=0.05
# live: gate de spread NBBO + umbral whale (v3)
export INTC_SPREAD_MAX=0.3
export INTC_WHALE_USD=250000
while true; do
  pkill -x intc_signal_bot 2>/dev/null
  sleep 1
  bots/intc_signal_bot >> logs/intc_signals.log 2>&1
  echo "$(date) intc_signal_bot salio; relanzando" >> logs/intc_signals.log
  sleep 30
done
