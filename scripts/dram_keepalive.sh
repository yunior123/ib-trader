#!/bin/zsh
# dram_signal_bot (C++) 24/5 — instancia UNICA, limpia huerfanos en cada ciclo
cd "$(dirname "$0")/.."
while true; do
  pkill -x dram_signal_bot 2>/dev/null      # nunca dos motores
  pkill -f dram_bar_bridge 2>/dev/null      # nunca bridges huerfanos
  sleep 1
  ./dram_signal_bot >> dram_signals.log 2>&1
  echo "$(date) dram_signal_bot salio; relanzando en 30s" >> dram_signals.log
  sleep 30
done
