#!/usr/bin/env python3
"""fastscan — the 1-MINUTE Finviz fast lane (Yunior 2026-07-10: "every 1 min it
should be fetching from finviz... monitoring buy symbols with a lot of potential
for profit during the day").

Every 60s (launchd com.ibtrader.fastscan) during market hours: pull the Finviz
Elite realtime top-gainers screen, run each NEW symbol through the scanner's
validated selectivity filters (penny range, real gain, liquidity, <40% intraday
cap, no prior-day blowoff) and MERGE the survivors into today's watchlist.
The alert bot re-reads the watchlist every poll, so a fresh mover is under
confirmed-breakout tracking within ~1 minute of appearing on Finviz.

TA vetting stays on the 15-min rescan lane (TradingAgents takes minutes; the
fast lane never blocks on it — new names arrive ta=? and the next rescan vets
the leaders).
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
import scanner  # noqa: E402  (evaluate() = the validated selectivity filters)
from sources import finviz_elite_gainers  # noqa: E402


def main():
    now = datetime.now().astimezone()
    if now.weekday() > 4 or not ("06:00" <= now.strftime("%H:%M") <= "16:00"):
        return 0
    rows = finviz_elite_gainers(max_price=scanner.PENNY_MAX)
    if not rows:
        return 0
    day = now.strftime("%Y%m%d")
    path = os.path.join("data", "topgainer", f"watchlist_{day}.json")
    if os.path.exists(path):
        data = json.load(open(path))
    else:
        data = {"date": state.now_iso(), "generated_by": "fastscan",
                "premarket": now.strftime("%H:%M") < "09:30", "candidates": []}
    have = {c["sym"] for c in data.get("candidates", [])}
    added = []
    for row in rows:
        if row["sym"] in have:
            continue
        r = scanner.evaluate(row)          # same filters: junk never gets in
        if r:
            r["merged_by"] = "fastscan"
            r["merged_at"] = state.now_iso()
            data["candidates"].append(r)
            have.add(r["sym"])
            added.append(r)
    if added:
        data["candidates"].sort(key=lambda c: c.get("score", 0), reverse=True)
        data["fastscan_at"] = state.now_iso()
        state.write_watchlist(data)
        for r in added:
            print(f"fastscan +{r['sym']} +{r['gain_pct']}% ${r['price']} score {r['score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
