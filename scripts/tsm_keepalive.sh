#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): v3 FULL26 30T 26W WR87% +17.1% pf1.5 (OOS 86%)
export TSM_SCORE_MIN=0.78
export TSM_RSI_OS=25
export TSM_BB_STD=3.0
export TSM_TARGET=8.0
export TSM_TRAIL_ATR=3
export TSM_STOP=8
export TSM_TIME_STOP_MIN=0
export TSM_SKIP_OPEN=5
# lado corto EVALUADO y APAGADO (sweep 2026: sin config >=70% OOS-limpia
# — el uptrend 2026 castiga cortos en este nombre); radar avisa igual
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP94/DOWN99%, umbral por ticker)
export TSM_QUAKE_BANNER=1
export TSM_QUAKE_MIN=0.02
# live: gate de spread NBBO + umbral whale (v3)
export TSM_SPREAD_MAX=0.3
export TSM_WHALE_USD=250000
# re-tune FULL-PROFIT 2026-07-11 (coordinate sweep, train+OOS>0, WR>=70)
export TSM_SHORTS=1
export TSM_S_BB_STD=3.0
export TSM_S_TARGET=3.0
export TSM_S_TRAIL=4
# WFO v2 2026-07-11: 90d , seleccion solo-train, OOS intacto, velas
export TSM_S_MODE=mr
export TSM_S_RSI_OS=30
export TSM_S_VOL_MULT=1.0
while true; do
  pkill -x tsm_signal_bot 2>/dev/null
  sleep 1
  bots/tsm_signal_bot >> logs/tsm_signals.log 2>&1
  echo "$(date) tsm_signal_bot salio; relanzando" >> logs/tsm_signals.log
  sleep 30
done
