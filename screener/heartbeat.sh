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
  SYM=$("$PY" "$ROOT/screener/state.py" pos 2>/dev/null)
  # nunca apilar audio: si ya suena afplay/say, saltar este beep, y correr en
  # foreground (autolimitado) — los & huerfanos saturaban coreaudiod (fix 2026-07-09)
  if [[ -n "$SYM" ]]; then
    pgrep -x afplay >/dev/null || afplay "$ALERT" >/dev/null 2>&1
    # voz serializada (orden 2026-07-18): speak.sh encola, el daemon habla con la
    # voz Siri del sistema — nada de say -v directo (se pisaba con otras alertas)
    bash "$ROOT/scripts/speak.sh" INFO "holding $SYM, watchdog active" >/dev/null 2>&1
    echo "$(date +%T) heartbeat: POSITION OPEN ($SYM), watchdog managing" >> "$ROOT/screener/heartbeat.log"
  else
    pgrep -x afplay >/dev/null || afplay "$TICK" >/dev/null 2>&1
    echo "$(date +%T) heartbeat: alive, flat" >> "$ROOT/screener/heartbeat.log"
  fi
  sleep "$INTERVAL"
done
