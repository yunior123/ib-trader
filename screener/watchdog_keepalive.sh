#!/bin/zsh
# Keeps the position watchdog alive forever. Single instance.
# C++ primary (screener_watchdog, Yunior 2026-07-09: avoid python in the fleet);
# python watchdog.py is the tested fallback if the binary is missing.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
WD_BIN="$ROOT/screener/screener_watchdog"
while true; do
  pkill -f "screener/watchdog.py" 2>/dev/null
  pkill -x screener_watchdog 2>/dev/null
  sleep 1
  if [[ -x "$WD_BIN" ]]; then
    "$WD_BIN" >>"$ROOT/screener/watchdog.log" 2>&1
  else
    "$PY" "$ROOT/screener/watchdog.py" >>"$ROOT/screener/watchdog.log" 2>&1
  fi
  echo "[keepalive] watchdog exited $(date +%T), relaunch in 5s" >>"$ROOT/screener/watchdog.log"
  sleep 5
done
