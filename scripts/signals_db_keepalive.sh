#!/bin/bash
# signals_db_keepalive.sh — mantiene vivo el tailer feed->trades.db (fix 2026-07-28:
# el daemon murio el 25-jul y bollinger/whale/flow/cusum dejaron de entrar a la BD).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
while true; do
  if ! pgrep -f "scripts/signals_db.py --daemon" >/dev/null 2>&1; then
    nohup python3 -u scripts/signals_db.py --daemon \
      >> "$ROOT/logs/signals_db.log" 2>&1 &
    echo "$(date) signals_db.py relanzado" >> "$ROOT/logs/signals_db.log"
  fi
  sleep 15
done
