#!/bin/zsh
# perp_nbbo_bridge_keepalive.sh -- watchdog de perp_nbbo_bridge.py (patron opt_chain_keepalive.sh).
cd "$(dirname "$0")/.." || exit 1
while true; do
  if ! pgrep -f "scripts/perp_nbbo_bridge.py" >/dev/null; then
    nohup ./venv/bin/python scripts/perp_nbbo_bridge.py >> perp_nbbo_bridge.log 2>&1 &
    echo "$(date) perp_nbbo_bridge lanzado (pid $!)" >> perp_nbbo_bridge.log
  fi
  sleep 30
done
