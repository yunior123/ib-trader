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
    path = os.path.join("data", "screener", f"watchlist_{day}.json")
    if os.path.exists(path):
        data = json.load(open(path))
    else:
        data = {"date": state.now_iso(), "generated_by": "fastscan",
                "premarket": now.strftime("%H:%M") < "09:30", "candidates": []}
    # SOLO-TA al watchlist (Yunior 2026-07-15 "only send notifications on
    # finviz trading agents selected candidates"): los movers nuevos van a
    # pending_ta_*.json (staging, SIN banner); revet_watchlist corre TA en
    # background y promueve al watchlist — y bannerea — solo los BUY.
    pending = state.read_pending_ta(day)
    have = ({c["sym"] for c in data.get("candidates", [])}
            | {c["sym"] for c in pending})
    added = []
    for row in rows:
        if row["sym"] in have:
            continue
        r = scanner.evaluate(row)          # same filters: junk never gets in
        if r:
            r["merged_by"] = "fastscan"
            r["merged_at"] = state.now_iso()
            pending.append(r)
            have.add(r["sym"])
            added.append(r)
    if added:
        state.write_pending_ta(pending, day)
        for r in added:
            print(f"fastscan +{r['sym']} +{r['gain_pct']}% ${r['price']} "
                  f"score {r['score']} -> pending TA")
        # registro para validacion EOD (Yunior 2026-07-15 "u store all signals")
        try:
            with open(os.path.join("data", "screener", f"scan_log_{day}.jsonl"), "a") as f:
                f.write(json.dumps({"ts": state.now_iso(), "src": "fastscan",
                                    "pending_ta": added}) + "\n")
        except Exception:
            pass
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subprocess.Popen(
            f'pgrep -f "revet_watchlist|screener/scanner.py" >/dev/null || '
            f'nohup "{root}/venv/bin/python" "{root}/screener/revet_watchlist.py" 3 '
            f'>> "{root}/screener/rescan.log" 2>&1 &',
            shell=True, cwd=root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
