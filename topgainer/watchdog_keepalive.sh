#!/bin/zsh
# Keeps the never-loss watchdog alive forever. Single instance.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
while true; do
  pkill -f "topgainer/watchdog.py" 2>/dev/null
  sleep 1
  "$PY" "$ROOT/topgainer/watchdog.py" >>"$ROOT/topgainer/watchdog.log" 2>&1
  echo "[keepalive] watchdog exited $(date +%T), relaunch in 5s" >>"$ROOT/topgainer/watchdog.log"
  sleep 5
done
