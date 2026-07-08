#!/bin/zsh
# dram_signal_bot (C++) 24/5 keepalive — EL UNICO BOT CONECTADO
cd "$(dirname "$0")/.."
while true; do
  ./dram_signal_bot >> dram_signals.log 2>&1
  echo "$(date) dram_signal_bot salio; relanzando en 30s" >> dram_signals.log
  sleep 30
done
