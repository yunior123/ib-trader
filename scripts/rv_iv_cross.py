#!/usr/bin/env python3
"""rv_iv_cross.py — Realized vs Implied Volatility cross detector.

Calcula RV (20-bar 1m) vs IV (cache IBKR) → spread → oportunidad de short/long vol.
Output: data/rv_iv_spread.json {sym: {rv, iv, spread_pct, signal}}.

Uso: python3 scripts/rv_iv_cross.py (4am cron o manual).
"""
import json, os, sys, statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load_fleet():
    with open("data/fleet.txt") as f:
        return f.read().split()

def rv_20bar(sym):
    """Realized vol from last 20 bars 1m."""
    try:
        closes = []
        with open(f"data/bars_{sym.lower()}_ibkr.txt") as f:
            for ln in f:
                if not ln.strip() or ln.startswith("#"):
                    continue
                p = ln.split()
                if len(p) >= 5:
                    closes.append(float(p[4]))
        if len(closes) < 21:
            return None
        closes = closes[-20:]
        rets = [st.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
        rv_daily = st.stdev(rets) * 100 * (252 ** 0.5)
        return round(rv_daily, 2)
    except Exception:
        return None

def iv_cache(sym):
    """IV from opt_chain_<sym>.txt (cache IBKR)."""
    try:
        with open(f"data/opt_chain_{sym.lower()}.txt") as f:
            for ln in f:
                if ln.startswith("#"):
                    continue
                p = ln.split()
                if len(p) > 7:
                    try:
                        iv = float(p[7]) * 100
                        if iv > 0:
                            return round(iv, 2)
                    except Exception:
                        pass
        return None
    except Exception:
        return None

def compute_cross(sym):
    rv = rv_20bar(sym)
    iv = iv_cache(sym)
    if rv is None or iv is None:
        return None
    spread = iv - rv
    signal = "SHORT_VOL" if spread > 5 else "LONG_VOL" if spread < -5 else "FAIR"
    return {
        "rv": rv, "iv": iv, "spread_pct": round(spread, 1),
        "signal": signal
    }

def main():
    out = {}
    for sym in load_fleet():
        r = compute_cross(sym)
        if r:
            out[sym] = r
    tmp = "data/rv_iv_spread.json.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, "data/rv_iv_spread.json")
    print(f"[rv_iv_cross] {len(out)}/{len(load_fleet())} símbolos medidos")

if __name__ == "__main__":
    main()
