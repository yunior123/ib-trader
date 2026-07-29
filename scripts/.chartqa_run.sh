#!/bin/zsh
cd '/Users/yuniorrodriguezosorio/ib-trader'
SY=(qqq nvda smh mu aapl msft)
while true; do
  for i in {1..6}; do
    p=$((8079 + i)); s=${SY[$i]}
    z=$(lsof -tnP -iTCP:$p -sTCP:LISTEN 2>/dev/null)
    [[ -n $z ]] && continue
    cid=$((71 + i - 1))
    '/Users/yuniorrodriguezosorio/ib-trader/venv-chart/bin/python' scripts/chart_bridge.py --sym $s --http-port $p --client-id $cid >/tmp/w6_$s.log 2>&1 &
  done
  sleep 20
done
