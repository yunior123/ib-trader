#!/usr/bin/env python3
"""Aggregate the most-recent trading week of UW premium flow into per-symbol JSON.
OUT-OF-SESSION BATCH job — no signal path, no network."""
import json
import os
import sys
import time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_PATH = os.path.join(BASE, "data", "uw_premium_flow_hist.jsonl")
OUT_PATH = os.path.join(BASE, "data", "whale_week.json")
WEEK_S = 7 * 24 * 3600
BIAS_MIN = 50000.0


def main():
    if not os.path.exists(IN_PATH):
        print(f"ERROR: input missing: {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(IN_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                # skip malformed line ONLY — never swallow real logic errors
                continue
            rows.append(obj)

    if not rows:
        print(f"ERROR: 0 parseable rows in {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    # window derived from data's own max ts (deterministic, not wall clock)
    max_ts = max(int(r["ts"]) for r in rows)
    cutoff = max_ts - WEEK_S

    agg = {}
    kept_min_ts = None
    n_rows = 0
    for r in rows:
        ts = int(r["ts"])
        if ts < cutoff:
            continue
        sym = r["sym"]
        n_rows += 1
        kept_min_ts = ts if kept_min_ts is None else min(kept_min_ts, ts)
        a = agg.setdefault(sym, {
            "net_call_premium": 0.0, "net_put_premium": 0.0,
            "signed_premium": 0.0, "n": 0, "last_ts": 0,
        })
        a["net_call_premium"] += float(r["net_call_premium"])
        a["net_put_premium"] += float(r["net_put_premium"])
        a["signed_premium"] += float(r["signed_premium"])
        a["n"] += 1
        a["last_ts"] = max(a["last_ts"], ts)

    if not agg:
        print(f"ERROR: 0 rows within last 7 days of max ts {max_ts}", file=sys.stderr)
        sys.exit(1)

    for sym, a in agg.items():
        s = a["signed_premium"]
        if s > 0 and abs(s) >= BIAS_MIN:
            a["bias"] = "calls"
        elif s < 0 and abs(s) >= BIAS_MIN:
            a["bias"] = "puts"
        else:
            a["bias"] = "mixed"

    out = {
        "_meta": {
            "generado_por": "scripts/whale_week_agg.py",
            "asof_local": datetime.fromtimestamp(max_ts).strftime("%Y-%m-%d %H:%M local"),
            "week_start": datetime.fromtimestamp(kept_min_ts).strftime("%Y-%m-%d"),
            "week_end": datetime.fromtimestamp(max_ts).strftime("%Y-%m-%d"),
            "source": "data/uw_premium_flow_hist.jsonl (Unusual Whales trial feed — DELAYED, not realtime)",
            "n_rows": n_rows,
        },
    }
    out.update(agg)

    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, OUT_PATH)

    print(f"OK wrote {OUT_PATH}: {len(agg)} syms, {n_rows} rows, "
          f"{out['_meta']['week_start']}..{out['_meta']['week_end']}")


if __name__ == "__main__":
    main()
