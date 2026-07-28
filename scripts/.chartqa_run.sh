#!/bin/zsh
# .chartqa_run.sh — keepalive de los 6 chart bridges del cockpit (puertos 8080-8085).
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
mkdir -p "$ROOT/logs"
SY=(qqq nvda smh mu aapl msft)
while true; do
  for i in {1..6}; do
    p=$((8079 + i)); s=${SY[$i]}
    z=$(lsof -tnP -iTCP:$p -sTCP:LISTEN 2>/dev/null)
    [[ -n $z ]] && continue
    cid=$((71 + i - 1))
    "$ROOT/venv-chart/bin/python" scripts/chart_bridge.py --sym $s --http-port $p --client-id $cid >>"$ROOT/logs/bridge_chart_$s.log" 2>&1 &
  done
  sleep 20
done
