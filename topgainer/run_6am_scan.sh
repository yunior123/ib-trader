#!/bin/zsh
# run_6am_scan.sh — the 6 AM premarket research routine (Yunior's friend's habit).
# MANDATORY TradingAgents: scans real premarket top-gainer penny movers, then runs
# the TradingAgents multi-agent framework (NVIDIA NIM) on the finalists and keeps
# only names it blesses. Writes today's watchlist + pushes a summary to the phone.
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"

# load NVIDIA/LLM config for TradingAgents
[[ -f "$ROOT/llm.env" ]] && set -a && source "$ROOT/llm.env" && set +a

export TA_RESEARCH=1                       # research is MANDATORY (Yunior's order)
export TA_RESEARCH_TOPN="${TA_RESEARCH_TOPN:-3}"
export TA_TIMEOUT="${TA_TIMEOUT:-900}"     # generous — runs ~3.5h before the open

echo "[6am] $(date) premarket scan + MANDATORY TradingAgents research" \
     >> "$ROOT/topgainer/scan_6am.log"
"$PY" "$ROOT/topgainer/scanner.py" --premarket >> "$ROOT/topgainer/scan_6am.log" 2>&1
echo "[6am] done $(date)" >> "$ROOT/topgainer/scan_6am.log"
