#!/bin/zsh
cd '/Users/yuniorrodriguezosorio/ib-trader'
SY=(qqq nvda smh mu aapl msft)
while true; do
  for ((i=1; i<=6; i++)); do
    p=$((8079 + i)); s=${SY[$i]}
    z=$(lsof -tnP -iTCP:$p -sTCP:LISTEN 2>/dev/null)
    [[ -n $z ]] && continue
    '/Users/yuniorrodriguezosorio/ib-trader/venv-chart/bin/python' scripts/chart_bridge.py --lse-only --sym $s --http-port $p >/tmp/w6_$s.log 2>&1 &
  done
  sleep 20
done
