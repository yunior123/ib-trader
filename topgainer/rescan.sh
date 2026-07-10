#!/bin/zsh
# rescan.sh — research AUTONOMO intradia (Yunior 2026-07-10: "it should be
# doing all that by itself"). launchd lo corre cada 15 min (com.ibtrader.rescan):
# en horario de mercado (6:00-16:00 ET, L-V) re-ejecuta el scanner completo —
# Finviz Elite realtime top gainers + vetting TradingAgents OBLIGATORIO — y
# reescribe el watchlist del dia. El alert bot relee el watchlist en cada poll,
# asi que los nombres nuevos entran solos al motor de breakout confirmado.
# Guard pgrep: nunca dos scans a la vez (TA tarda minutos).
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
LOG="$ROOT/topgainer/rescan.log"

DOW=$(date +%u); HM=$(date +%H%M)
[[ $DOW -le 5 ]] || exit 0
[[ $HM -ge 0600 && $HM -le 1600 ]] || exit 0

# no solapar: si un scanner (6am o rescan) sigue corriendo, saltar este tick
if pgrep -f "topgainer/scanner.py" >/dev/null; then
  echo "$(date '+%F %T') rescan: scanner ya corriendo, salto" >> "$LOG"
  exit 0
fi

[[ -f "$ROOT/llm.env" ]] && set -a && source "$ROOT/llm.env" && set +a
export TA_RESEARCH=1
export TA_RESEARCH_TOPN="${TA_RESEARCH_TOPN:-3}"
export TA_TIMEOUT="${TA_TIMEOUT:-300}"

FLAG=""
[[ $HM -lt 0930 ]] && FLAG="--premarket"
echo "$(date '+%F %T') rescan: scanner $FLAG (Finviz+TA)" >> "$LOG"
"$PY" "$ROOT/topgainer/scanner.py" $FLAG >> "$LOG" 2>&1
echo "$(date '+%F %T') rescan: done" >> "$LOG"
