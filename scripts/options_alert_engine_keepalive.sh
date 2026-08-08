#!/bin/zsh
cd "$(dirname "$0")/.." || exit 1
mkdir -p bin logs
# Automatic mode explicitly requested 2026-08-08. Keep the measured hard cap and every
# liquidity/freshness gate; no qualifying contract means no alert.
export OPTIONS_ALERT_AUTO=1
export OPTIONS_ALERT_MIN_PROB=55
export OPTIONS_ALERT_TOP_N=2
while true; do
  if [[ ! -x bin/options_alert_engine || scripts/options_alert_engine.cpp -nt bin/options_alert_engine || scripts/options_alert_engine_core.h -nt bin/options_alert_engine ]]; then
    clang++ -std=c++17 -O2 -Wall -Wextra -o bin/options_alert_engine scripts/options_alert_engine.cpp >> logs/options_alert_engine.log 2>&1 || { sleep 30; continue; }
  fi
  if ! pgrep -f "bin/options_alert_engine --daemon" >/dev/null; then
    nohup ./bin/options_alert_engine --daemon >> logs/options_alert_engine.log 2>&1 &
    echo "$(date) options_alert_engine lanzado (pid $!)" >> logs/options_alert_engine.log
  fi
  sleep 30
done
