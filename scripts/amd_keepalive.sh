#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 69T 60W WR87% +37.0% pf1.5 (OOS 84% +15.7%)
export AMD_BB_STD=2.0
export AMD_RSI_OS=35
export AMD_VOL_MULT=1.2
export AMD_TARGET=8.0
export AMD_TRAIL_ATR=5
export AMD_STOP=8
export AMD_TIME_STOP_MIN=0
export AMD_SKIP_OPEN=0
# LADO CORTO optimizado (sweep independiente 2026-07-11): cortos trend FULL26 128T 98W WR77% +46.8% pf4.7 (OOS +18.8%; antes +6.3)
export AMD_SHORTS=1
export AMD_S_MODE=trend
export AMD_S_TREND_CUSUM=0.005
export AMD_S_TARGET=2.0
export AMD_S_STOP=1.0
export AMD_S_TRAIL=3
export AMD_S_TSTOP=0
export AMD_S_FLOOR=0.5
# TERREMOTO banner AMBAS direcciones (orden 2026-07-11 'detect up and down
# in ALL of them'; precision 2026: UP93/DOWN94%, umbral por ticker)
export AMD_QUAKE_BANNER=1
export AMD_QUAKE_MIN=0.03
# live: gate de spread NBBO + umbral whale (v3)
export AMD_SPREAD_MAX=0.3
export AMD_WHALE_USD=250000
while true; do
  pkill -x amd_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read AMD" 2>/dev/null
  sleep 1
  ./amd_signal_bot >> amd_signals.log 2>&1
  echo "$(date) amd_signal_bot salio; relanzando" >> amd_signals.log
  sleep 30
done
