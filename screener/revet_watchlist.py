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
    data = json.load(open(path)) if os.path.exists(path) else {
        "date": state.now_iso(), "generated_by": "revet", "candidates": []}
    # candidatos = watchlist actual + staging de fastscan (pending_ta):
    # desde 2026-07-15 el watchlist es SOLO-TA-BUY; los movers nuevos esperan
    # en pending hasta que TradingAgents los bendiga (orden "only send
    # notifications on finviz trading agents selected candidates").
    pending = state.read_pending_ta(day)
    cands = data.get("candidates", []) + pending
    if not cands:
        print("no candidates to vet")
        return 0
    date_str = datetime.now().astimezone().strftime("%Y-%m-%d")
    os.environ["TA_RESEARCH"] = "1"
    enriched = research.enrich_candidates(cands, date_str, topn=topn)
    vetted = [c for c in enriched if c.get("ta_action") == "BUY"]
    print(f"TradingAgents re-vet: {len(vetted)}/{min(topn, len(enriched))} researched names rated BUY")
    prev_syms = {c["sym"] for c in data.get("candidates", [])}
    data["candidates"] = vetted            # SOLO BUY — cero fallback sin vetar
    data["revetted_at"] = state.now_iso()
    state.write_watchlist(data)
    # pending: quedan solo los aun-sin-veredicto; los evaluados salen (BUY ya
    # esta en watchlist; no-BUY queda registrado en scan_log)
    state.write_pending_ta([c for c in enriched if not c.get("ta_action")], day)
    judged = [c for c in enriched if c.get("ta_action")]
    try:
        with open(f"data/screener/scan_log_{day}.jsonl", "a") as f:
            f.write(json.dumps({"ts": state.now_iso(), "src": "revet",
                                "judged": judged}) + "\n")
    except Exception:
        pass
    # banner SOLO para BUYs nuevos (ta-selected candidates)
    fresh = [c for c in vetted if c["sym"] not in prev_syms]
    if fresh:
        short = ", ".join(f"{c['sym']}+{c.get('gain_pct', 0):.0f}%" for c in fresh)
        state.notify_mac("TA BUY nuevo (finviz)", short)
    for c in data["candidates"]:
        print(f"  {c['sym']:6s} ta={c.get('ta_action', '?')} {str(c.get('ta_note', ''))[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
