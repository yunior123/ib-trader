#!/bin/zsh
# momentum_bot 24/5 keepalive: relaunches detector+bridge if anything dies
cd "$(dirname "$0")/.."
while true; do
  ./momentum_bot >> momentum_alerts.log 2>&1
  echo "$(date) momentum_bot exited; relanzando en 30s" >> momentum_alerts.log
  sleep 30
done
