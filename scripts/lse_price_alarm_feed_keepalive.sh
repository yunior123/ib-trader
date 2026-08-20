#!/bin/zsh
# Dedicated London-only quote bridge for active TSLA/INTC entry alarms.
cd "$(dirname "$0")/.." || exit 1
while true; do
  ./venv/bin/python scripts/lse_price_alarm_feed.py --symbols TSLA,INTC \
    >> logs/lse_price_alarm_feed.log 2>&1
  echo "$(date) London price-alarm feed exited; restarting" \
    >> logs/lse_price_alarm_feed.log
  sleep 2
done
