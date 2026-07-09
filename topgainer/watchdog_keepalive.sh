#!/bin/zsh
# Keeps the position watchdog alive forever. Single instance.
# C++ primary (topgainer_watchdog, Yunior 2026-07-09: avoid python in the fleet);
# python watchdog.py is the tested fallback if the binary is missing.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
WD_BIN="$ROOT/topgainer/topgainer_watchdog"
while true; do
  pkill -f "topgainer/watchdog.py" 2>/dev/null
  pkill -x topgainer_watchdog 2>/dev/null
  sleep 1
  if [[ -x "$WD_BIN" ]]; then
    "$WD_BIN" >>"$ROOT/topgainer/watchdog.log" 2>&1
  else
    "$PY" "$ROOT/topgainer/watchdog.py" >>"$ROOT/topgainer/watchdog.log" 2>&1
  fi
  echo "[keepalive] watchdog exited $(date +%T), relaunch in 5s" >>"$ROOT/topgainer/watchdog.log"
  sleep 5
done
