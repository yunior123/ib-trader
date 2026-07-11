#!/bin/zsh
cd "$(dirname "$0")/.."
# CONFIG WR-70 (backtest 2026 completo ene-jul, orden Yunior 2026-07-11
# "all of them should be above 70 percent"): TREND FULL26 178T 135W WR76% +14.0% pf2.1 (OOS 76%)
export QQQ_MODE=trend
export QQQ_TREND_CUSUM=0.004
export QQQ_TARGET=1.0
export QQQ_STOP=0.4
export QQQ_TRAIL_ATR=3
export QQQ_MAX_DAY=2
export QQQ_FLOOR=0.1
export QQQ_SKIP_OPEN=15
export QQQ_EOD_FORCE=1
export QQQ_TIME_STOP_MIN=0
# LADO CORTO v4 (2026-07-11 'both directions'): cortos FULL26 151T 111W WR74% +15.4% pf2.5 (OOS 76%)
export QQQ_SHORTS=1
export QQQ_S_TARGET=0.5
export QQQ_S_STOP=1.5
export QQQ_S_TRAIL=3
export QQQ_S_TSTOP=120
export QQQ_S_FLOOR=0.1
# live: gate de spread NBBO + umbral whale (v3)
export QQQ_SPREAD_MAX=0.3
export QQQ_WHALE_USD=250000
while true; do
  pkill -x qqq_signal_bot 2>/dev/null
  pkill -f "alpaca_ws_bridge read QQQ" 2>/dev/null
  sleep 1
  ./qqq_signal_bot >> qqq_signals.log 2>&1
  echo "$(date) qqq_signal_bot salio; relanzando" >> qqq_signals.log
  sleep 30
done
