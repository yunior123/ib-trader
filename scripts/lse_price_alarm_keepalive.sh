#!/bin/zsh
# London-only alert daemon.  The distinct binary name is intentional: fleet_sleep
# stops the generic IBKR alarm while this explicitly mounted LSE alert remains live.
cd "$(dirname "$0")/.." || exit 1
while true; do
  pkill -x lse_price_alarm 2>/dev/null
  sleep 1
  bin/lse_price_alarm >> logs/lse_price_alarm.log 2>&1
  echo "$(date) lse_price_alarm exited; restarting" >> logs/lse_price_alarm.log
  sleep 2
done
