#!/bin/zsh
# Keep x_whale_bot --daemon alive (09:00 America/Toronto daily post).
# SEÑAL-SOLAMENTE. No broker calls.
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=./x_whale_bot
LOG=x_whale_bot.log

if [[ ! -x "$BIN" ]]; then
  echo "$(date '+%F %T') | building x_whale_bot" | tee -a "$LOG"
  OPENSSL="${OPENSSL_PREFIX:-/opt/homebrew/opt/openssl@3}"
  clang++ -std=c++17 -O2 \
    -I"$OPENSSL/include" -L"$OPENSSL/lib" \
    -o x_whale_bot scripts/x_whale_bot.cpp -lcurl -lcrypto
fi

# fleet_sleep candado
if [[ -f data/fleet_sleep ]]; then
  echo "$(date '+%F %T') | fleet_sleep on — x whale bot idle" | tee -a "$LOG"
  exit 0
fi

if pgrep -f './x_whale_bot --daemon' >/dev/null 2>&1; then
  exit 0
fi

echo "$(date '+%F %T') | starting x_whale_bot --daemon" | tee -a "$LOG"
nohup "$BIN" --daemon >>"$LOG" 2>&1 &
echo $! > data/x_whale_bot.pid
