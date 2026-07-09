#!/bin/zsh
# claude_trader_loop.sh — the RALPH loop that solves "Claude stops looping".
#
# The loop lives HERE, in bash, NOT inside Claude's own agency. Each iteration
# is ONE fast headless `claude -p` decision that returns and is immediately
# re-invoked. Even if a given Claude call stalls or refuses to "keep looping",
# the next iteration starts fresh in seconds. And the deterministic watchdog
# (topgainer/watchdog.py) owns the SELL regardless of Claude — so a stalled
# session can never make us lose money.
#
# Fast + minimal context: slim settings dir (no hooks/audio/MCP/skills),
# restricted tools, latest Claude 5 model. Runs only during the trade window.
#
# Usage:  topgainer/claude_trader_loop.sh
# Env:    TG_MODEL (default claude-fable-5), TG_WIN_START/END, TG_INTERVAL,
#         TG_MAX_TURNS, TG_BUDGET_USD
set -u
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

MODEL="${TG_MODEL:-claude-fable-5}"      # latest Claude 5
WIN_START="${TG_WIN_START:-09:30}"
WIN_END="${TG_WIN_END:-10:00}"
INTERVAL="${TG_INTERVAL:-8}"             # seconds between decision cycles
MAX_TURNS="${TG_MAX_TURNS:-12}"
BUDGET="${TG_BUDGET_USD:-2.00}"
SETTINGS="$ROOT/topgainer/claude_settings/settings.json"
PROMPT_FILE="$ROOT/topgainer/decision_prompt.md"

in_window() {
  local now; now=$(date +%H:%M)
  local dow; dow=$(date +%u)          # 1..7 Mon..Sun
  [[ $dow -le 5 && "$now" > "$WIN_START" && "$now" < "$WIN_END" ]] || \
  [[ $dow -le 5 && ( "$now" == "$WIN_START" || "$now" == "$WIN_END" ) ]]
}

echo "[trader_loop] model=$MODEL window=$WIN_START-$WIN_END interval=${INTERVAL}s"
PROMPT="$(cat "$PROMPT_FILE")"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
ALIVE="$ROOT/data/topgainer/claude_alive"   # dead-man ping the watchdog monitors

while true; do
  # Claude is ALWAYS the decision-maker while a position is open: run cycles
  # inside the buy window OR whenever we hold shares (management mode).
  POS_SYM="$("$PY" "$ROOT/topgainer/state.py" pos 2>/dev/null)"
  if in_window || [[ -n "$POS_SYM" ]]; then
    # ONE decision cycle, fresh context, hard turn/budget caps.
    timeout 120 claude -p "$PROMPT" \
      --model "$MODEL" \
      --settings "$SETTINGS" \
      --max-turns "$MAX_TURNS" \
      --permission-mode acceptEdits \
      --add-dir "$ROOT" \
      2>>"$ROOT/topgainer/trader_loop.err" \
      | tee -a "$ROOT/topgainer/trader_loop.log"
    rc=${pipestatus[1]}
    # touch the dead-man file ONLY on a healthy cycle; a hung/killed/errored
    # claude leaves it stale so the watchdog flattens the position.
    if [[ $rc -eq 0 ]]; then
      touch "$ALIVE"
    fi
    echo "[trader_loop] cycle done $(date +%T) rc=$rc" >> "$ROOT/topgainer/trader_loop.log"
    sleep "$INTERVAL"
  else
    # outside window and flat: idle cheaply.
    sleep 30
  fi
done
