#!/bin/zsh
# Mide A QUE HORA resetea la cuota diaria de LSE. El 429 no trae ninguna cabecera de reset
# (medido 2026-08-24: solo date/cf-ray), y de esa hora depende todo el reparto Mac/worker.
cd "$(dirname "$0")/.."
KEY=$(grep -E '^LSE_API_KEY=' feeds.env | cut -d= -f2-)
LOG=logs/lse_reset_probe.log
while true; do
  COD=$(curl -s -o /dev/null -w "%{http_code}" -H "x-api-key: $KEY" \
        "https://api.londonstrategicedge.com/vault/usage")
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $(date +%H:%M) HTTP $COD" >> "$LOG"
  if [[ "$COD" == "200" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) CUOTA VIVA -> reset detectado" >> "$LOG"
    ./venv/bin/python scripts/lse_budget.py --reset >> "$LOG" 2>&1
    exit 0
  fi
  sleep 600
done
