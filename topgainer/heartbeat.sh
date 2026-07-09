#!/bin/zsh
# heartbeat.sh — audible proof-of-life every minute so Yunior KNOWS the
# top-gainer system is running (his explicit ask: "beep every minute").
# Soft tick normally; a louder double-beep + spoken status when a position is
# open (money at risk). Writes a heartbeat line to the log too.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
INTERVAL="${HEARTBEAT_INTERVAL:-60}"
TICK="${HEARTBEAT_SOUND:-/System/Library/Sounds/Tink.aiff}"
ALERT="${HEARTBEAT_ALERT_SOUND:-/System/Library/Sounds/Submarine.aiff}"

while true; do
  SYM=$("$PY" "$ROOT/topgainer/state.py" pos 2>/dev/null)
  if [[ -n "$SYM" ]]; then
    afplay "$ALERT" >/dev/null 2>&1 &
    say -v Daniel -r 180 "holding $SYM, watchdog active" >/dev/null 2>&1 &
    echo "$(date +%T) heartbeat: POSITION OPEN ($SYM), watchdog managing" >> "$ROOT/topgainer/heartbeat.log"
  else
    afplay "$TICK" >/dev/null 2>&1 &
    echo "$(date +%T) heartbeat: alive, flat" >> "$ROOT/topgainer/heartbeat.log"
  fi
  sleep "$INTERVAL"
done
