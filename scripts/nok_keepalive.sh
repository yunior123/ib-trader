#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): FULL26 13T 13W WR100% +25.4% (perfil stop-ancho: perdidas pueden quedar en bag)
export NOK_BB_STD=3.0
export NOK_RSI_OS=30
export NOK_VOL_MULT=1.2
export NOK_TARGET=4
export NOK_TRAIL_ATR=2
export NOK_STOP=8
export NOK_TIME_STOP_MIN=0
export NOK_SKIP_OPEN=5
# live: gate de spread NBBO + umbral whale (v3)
export NOK_SPREAD_MAX=0.3
export NOK_WHALE_USD=150000
while true; do
  pkill -x nok_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read NOK" 2>/dev/null
  sleep 1
  ./nok_signal_bot >> nok_signals.log 2>&1
  echo "$(date) nok_signal_bot salio; relanzando" >> nok_signals.log
  sleep 30
done
