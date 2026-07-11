#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): v3 FULL26 45T 40W WR89% +17.1% pf1.4 (OOS 89%)
export NVDA_SCORE_MIN=0.66
export NVDA_RSI_OS=35
export NVDA_BB_STD=2.5
export NVDA_TARGET=4
export NVDA_TRAIL_ATR=2
export NVDA_STOP=8
export NVDA_TIME_STOP_MIN=0
export NVDA_SKIP_OPEN=0
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# LADO CORTO optimizado (sweep independiente 2026-07-11): cortos trend FULL26 71T 62W WR87% +16.2% pf8.8 (OOS 92%)
export NVDA_SHORTS=1
export NVDA_S_MODE=trend
export NVDA_S_TREND_CUSUM=0.005
export NVDA_S_TARGET=0.56
export NVDA_S_STOP=0.5
export NVDA_S_TRAIL=3
export NVDA_S_TSTOP=0
export NVDA_S_FLOOR=0.5
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP96/DOWN97%, umbral por ticker)
export NVDA_QUAKE_BANNER=1
export NVDA_QUAKE_MIN=0.02
# live: gate de spread NBBO + umbral whale (v3)
export NVDA_SPREAD_MAX=0.3
export NVDA_WHALE_USD=250000
while true; do
  pkill -x nvda_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read NVDA" 2>/dev/null
  sleep 1
  ./nvda_signal_bot >> nvda_signals.log 2>&1
  echo "$(date) nvda_signal_bot salio; relanzando" >> nvda_signals.log
  sleep 30
done
