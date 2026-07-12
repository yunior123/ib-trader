#!/usr/bin/env python3
"""Re-run MANDATORY TradingAgents vetting on today's already-written watchlist
(for when the 6AM research timed out) and rewrite it with ta_action attached.
Usage: venv/bin/python screener/revet_watchlist.py [TOPN]"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import research  # noqa: E402
import state  # noqa: E402


def main():
    topn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    day = datetime.now().astimezone().strftime("%Y%m%d")
    path = f"data/screener/watchlist_{day}.json"
    data = json.load(open(path))
    cands = data.get("candidates", [])
    if not cands:
        print("no candidates to vet")
        return 0
    date_str = datetime.now().astimezone().strftime("%Y-%m-%d")
    os.environ["TA_RESEARCH"] = "1"
    enriched = research.enrich_candidates(cands, date_str, topn=topn)
    vetted = [c for c in enriched if c.get("ta_action") == "BUY"]
    print(f"TradingAgents re-vet: {len(vetted)}/{min(topn, len(enriched))} researched names rated BUY")
    data["candidates"] = vetted or enriched  # keep flagged list if none blessed
    data["revetted_at"] = state.now_iso()
    state.write_watchlist(data)
    for c in data["candidates"]:
        print(f"  {c['sym']:6s} ta={c.get('ta_action', '?')} {str(c.get('ta_note', ''))[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
