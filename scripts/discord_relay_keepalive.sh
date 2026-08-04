#!/bin/zsh
cd "$(dirname "$0")/.."
# Espejo notify_push.txt -> Discord. Consumidor independiente: si muere, ntfy/voz siguen.
LOG=logs/discord_relay.log
mkdir -p logs
FAILS=0
while true; do
  pkill -f "scripts/discord_relay.py" 2>/dev/null
  sleep 1
  if [[ ! -s config/discord_webhooks.json ]]; then
    echo "$(date) sin config/discord_webhooks.json — corre scripts/discord_webhooks.py" >> $LOG
    sleep 300
    continue
  fi
  ./venv/bin/python -u scripts/discord_relay.py >> $LOG 2>&1
  RC=$?
  FAILS=$((FAILS+1))
  echo "$(date) discord_relay salio (rc=$RC); relanzando (fallo $FAILS)" >> $LOG
  # GRITA si el hijo muere 3 veces seguidas: un relé mudo no se nota hasta que hace falta.
  if (( FAILS % 3 == 0 )); then
    ./venv/bin/python scripts/notify_short.py "⚠ DISCORD RELÉ" \
      "caido ${FAILS} veces seguidas (rc=$RC) — el espejo a Discord no publica" 2>/dev/null
  fi
  sleep 30
done
