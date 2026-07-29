#!/bin/zsh
cd "$(dirname "$0")/.."
# opt_sentinel keepalive (2026-07-16). SEÑAL-SOLAMENTE.
# 2026-07-28: exit 78 = RETIRADO (guard de frescura EXP vencido) -> NO relanzar.
while true; do
  pkill -f "scripts/opt_sentinel.py" 2>/dev/null
  sleep 1
  ./venv/bin/python scripts/opt_sentinel.py >> logs/opt_sentinel.log 2>&1
  rc=$?
  if [ "$rc" -eq 78 ]; then
    echo "$(date) opt_sentinel RETIRADO (exit 78, datos 2026-07-16 vencidos) — keepalive se apaga" >> logs/opt_sentinel.log
    exit 0
  fi
  echo "$(date) opt_sentinel salio (rc $rc); relanzando" >> logs/opt_sentinel.log
  sleep 20
done
