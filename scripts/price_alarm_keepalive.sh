#!/bin/zsh
# price_alarm_keepalive.sh — mantiene vivo el watcher de alarmas de precio
# (M5, spec V6 §6). Patron estandar de la flota: pkill + relaunch + sleep 30.
# El watcher es SEÑAL-SOLAMENTE: solo lee archivos y emite audio/banner/mirror.
cd "$(dirname "$0")/.."
while true; do
  pkill -x price_alarm 2>/dev/null
  sleep 1
  ./price_alarm >> price_alarm.log 2>&1
  echo "$(date) price_alarm salio; relanzando" >> price_alarm.log
  sleep 30
done
