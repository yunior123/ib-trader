#!/bin/zsh
cd "$(dirname "$0")/.."
# bargain_scan keepalive (creado 2026-07-15, orden "create a bot to send
# bargain alerts on the tickers of our fleet based on trading agents research,
# finviz, etc" + "bargain bot on topgainers... be selective").
# Corre cada 10 min en RTH; el propio script gatea 09:30-16:00 ET L-V.
# SIGNAL-ONLY: solo banners+log, jamas ordena.
while true; do
  ./venv/bin/python screener/bargain_scan.py >> screener/bargain.log 2>&1
  sleep 600
done
