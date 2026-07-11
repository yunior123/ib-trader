#!/bin/zsh
# fleet_keepalive_start.sh — arranca los 4 keepalives de los signal bots
# (13 bots: dram/nok/spcx/tsla + nvda/txn/tsm/amd/intc/asml/aapl + gld/qqq). Idempotente: si un keepalive ya corre, no lo duplica
# (dos keepalives del mismo bot se matarian el bot mutuamente). launchd lo
# re-ejecuta cada 5 min (StartInterval) = watchdog de los watchdogs.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
for b in dram nok spcx tsla nvda txn tsm amd intc asml aapl gld qqq; do
  if ! pgrep -f "scripts/${b}_keepalive.sh" >/dev/null; then
    nohup zsh "$ROOT/scripts/${b}_keepalive.sh" >/dev/null 2>&1 &
    echo "$(date) fleet: ${b}_keepalive lanzado (pid $!)" >> "$ROOT/fleet_autostart.log"
  fi
done
