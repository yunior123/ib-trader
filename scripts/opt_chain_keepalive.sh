#!/bin/zsh
# opt_chain_keepalive.sh — watchdog del cache de cadenas de opciones (v6.1).
# Patron estandar: pgrep, relaunch cada 30 s, log a opt_chain_cache.log.
# SOLO LECTURA: opt_chain_cache.py conecta readonly=True clientId 48 — jamas ordenes (ley #0).
cd "$(dirname "$0")/.." || exit 1
while true; do
  if ! pgrep -f "scripts/opt_chain_cache.py" >/dev/null; then
    nohup ./venv/bin/python scripts/opt_chain_cache.py >> logs/opt_chain_cache.log 2>&1 &
    echo "$(date) opt_chain_cache lanzado (pid $!)" >> logs/opt_chain_cache.log
  fi
  sleep 30
done
