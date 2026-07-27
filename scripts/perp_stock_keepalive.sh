#!/bin/zsh
# perp_stock_keepalive.sh -- perp_stock_fetch.py es one-shot; este loop lo
# relanza cada 15s (patron bargain_keepalive.sh) para mantener data/perp_stocks.json vivo.
cd "$(dirname "$0")/.." || exit 1
while true; do
  ./venv/bin/python scripts/perp_stock_fetch.py >> perp_stock_fetch.log 2>&1
  sleep 15
done
