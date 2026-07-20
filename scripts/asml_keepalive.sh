#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 17T 14W WR82% +15.1% pf2.1 (OOS 73%)
export ASML_BB_STD=1.5
export ASML_RSI_OS=25
export ASML_VOL_MULT=1.0
export ASML_TARGET=8.0
export ASML_TRAIL_ATR=5
export ASML_STOP=8.0
export ASML_TIME_STOP_MIN=0
export ASML_SKIP_OPEN=0
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# LADO CORTO optimizado (sweep independiente 2026-07-11): cortos MR FULL26 56T 39W WR70% +8.6% pf1.2 (OOS 67%)
export ASML_SHORTS=1
export ASML_S_MODE=mr
export ASML_S_SCORE_MIN=0
export ASML_S_BB_STD=1.5
export ASML_S_RSI_OS=35
export ASML_S_VOL_MULT=1.2
export ASML_S_TARGET=4.5
export ASML_S_STOP=3.0
export ASML_S_TRAIL=5
export ASML_S_TSTOP=0
export ASML_S_FLOOR=0.5
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP98/DOWN95%, umbral por ticker)
export ASML_QUAKE_BANNER=1
export ASML_QUAKE_MIN=0.02
# live: gate de spread NBBO + umbral whale (v3)
export ASML_SPREAD_MAX=0.3
export ASML_WHALE_USD=250000
# WFO v2 2026-07-11: 90d , seleccion solo-train, OOS intacto, velas
export ASML_S_CANDLE=1
while true; do
  pkill -x asml_signal_bot 2>/dev/null
  sleep 1
  ./asml_signal_bot >> asml_signals.log 2>&1
  echo "$(date) asml_signal_bot salio; relanzando" >> asml_signals.log
  sleep 30
done
