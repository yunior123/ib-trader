#!/bin/zsh
# options_enrich_keepalive.sh — watchdog del overlay de opciones (M4, V6_SPEC §5).
# Patron estandar: pgrep, relaunch cada 30 s, log a options_enrich.log.
# SOLO LECTURA: options_enrich.py conecta readonly=True — jamas ordenes (ley).
cd "$(dirname "$0")/.." || exit 1
while true; do
  if ! pgrep -f "scripts/options_enrich.py" >/dev/null; then
    nohup ./venv/bin/python scripts/options_enrich.py >> options_enrich.log 2>&1 &
    echo "$(date) options_enrich lanzado (pid $!)" >> options_enrich.log
  fi
  sleep 30
done
