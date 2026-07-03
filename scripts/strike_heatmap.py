#!/usr/bin/env python3
"""strike_heatmap.py — Strike activity concentration by price strata (ITM/ATM/OTM).

Agrupa strikes por ventiles, suma volumen calls vs puts → detecta coladas de gamma.
Output: data/strike_heatmap_<sym>.json {ventile: {calls_vol, puts_vol, dominance}}.

Uso: python3 scripts/strike_heatmap.py [SYM] (o loop por fleet).
"""
import json, os, sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load_fleet():
    with open("data/fleet.txt") as f:
        return f.read().split()

def heatmap_sym(sym):
    """Volumen calls/puts por decil de precio."""
    try:
        with open(f"data/opt_chain_{sym.lower()}.txt") as f:
            spot = None
            rows = []
            for ln in f:
                if ln.startswith("#"):
                    if "spot" in ln:
                        try:
                            spot = float(ln.split("spot ")[1].split()[0])
                        except Exception:
                            pass
                    continue
                p = ln.split()
                if len(p) >= 7:
                    try:
                        strike, right, vol = float(p[0]), p[1], int(p[5])
                        rows.append({"strike": strike, "right": right, "vol": vol})
                    except Exception:
                        pass
        if not spot or not rows:
            return None
        
        # Ventiles por precio
        strikes = sorted(set(r["strike"] for r in rows))
        if len(strikes) < 2:
            return None
        lo, hi = min(strikes), max(strikes)
        deciles = []
        for i in range(10):
            th = lo + (hi - lo) * (i + 1) / 10
            deciles.append((lo + (hi - lo) * i / 10, th))
        
        out = {}
        for dec_lo, dec_hi in deciles:
            c_vol = sum(r["vol"] for r in rows if dec_lo <= r["strike"] <= dec_hi and r["right"] == "C")
            p_vol = sum(r["vol"] for r in rows if dec_lo <= r["strike"] <= dec_hi and r["right"] == "P")
            tot = c_vol + p_vol
            if tot > 0:
                label = f"${dec_lo:.0f}-${dec_hi:.0f}"
                dominance = "CALLS" if c_vol > p_vol * 1.5 else "PUTS" if p_vol > c_vol * 1.5 else "MIXED"
                out[label] = {
                    "calls_vol": c_vol, "puts_vol": p_vol, "total": tot,
                    "dominance": dominance, "ratio": round(c_vol / max(1, p_vol), 2)
                }
        return out if out else None
    except Exception:
        return None

def main():
    args = sys.argv[1:] or load_fleet()
    for sym in args[:30]:
        h = heatmap_sym(sym.upper())
        if h:
            tmp = f"data/strike_heatmap_{sym.lower()}.json.tmp"
            with open(tmp, "w") as f:
                json.dump(h, f, indent=1)
            os.replace(tmp, f"data/strike_heatmap_{sym.lower()}.json")
    print(f"[strike_heatmap] {len(args)} símbolos procesados")

if __name__ == "__main__":
    main()
