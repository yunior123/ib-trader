#!/bin/zsh
# DRAM bot runner for launchd. Paper trading by default (port 7497).
# The bot itself handles: Sun 8pm -> Fri 8pm Toronto window (--schedule),
# waiting for TWS if it's not up (--wait-tws), and IBKR reconnection.
cd "$(dirname "$0")/.."
exec venv/bin/python dram_dip_bot.py \
  --mode trade \
  --port "${IB_PORT:-7497}" \
  --schedule \
  --wait-tws
