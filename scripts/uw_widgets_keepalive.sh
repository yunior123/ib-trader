#!/bin/zsh
cd "$(dirname "$0")/.."
# Los 3 feeders de los widgets UW del cockpit (2026-08-03). Señal-solamente, cero voz.
#   uw_darkpool   -> data/uw_darkpool.json    (wgt-dark,   DESCRIPTIVO, killlist #3)
#   uw_net_prem   -> data/uw_net_prem.json    (wgt-prem,   premium neto firmado)
#   uw_gex_expiry -> data/uw_gex_expiry.json  (wgt-gexexp, GEX por vencimiento, EOD)
# Cada uno lleva su propio portero horario dentro: aqui solo se vigila que no mueran.
FEEDERS=(uw_darkpool uw_net_prem uw_gex_expiry)

while true; do
  for f in $FEEDERS; do
    if ! pgrep -f "scripts/$f.py" >/dev/null; then
      nohup ./venv/bin/python -u "scripts/$f.py" >> "logs/$f.log" 2>&1 &
      echo "$(date) $f relanzado (pid $!)" >> "logs/$f.log"
    fi
  done
  sleep 60
done
