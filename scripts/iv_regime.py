#!/usr/bin/env python3
"""iv_regime.py — IV Regime Tracker: where current IV sits vs 60-day percentile.

Input: data/history/<fecha>/chain_full_*.json (Polygon snapshots with IV).
Output: data/iv_regime.json {sym: {iv_current, iv_p10, iv_p50, iv_p90, percentile, regime}}.

Regimes: COMPRESSED (<P10), NORMAL (P10-P90), EXPANDED (>P90).
Corre 4am (auto) o manual: python3 scripts/iv_regime.py
"""
import json, os, sys, glob, time
from collections import defaultdict
import statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load_fleet():
    with open("data/fleet.txt") as f:
        return f.read().split()

def build_iv_history(sym, days=60):
    """Carga IV histórico de snapshots, últimos N días."""
    hist_dir = "data/history"
    ivs = []
    cutoff = time.time() - days * 86400
    for f in sorted(glob.glob(f"{hist_dir}/*/chain_full_{sym.lower()}.json")):
        try:
            ts = int(os.path.basename(os.path.dirname(f)).replace('-', ''))
            if ts < cutoff / 1e6:
                continue
            with open(f) as src:
                data = json.load(src)
            for row in data.get("rows", []):
                iv = row.get("iv")
                if iv and iv > 0:
                    ivs.append(iv)
        except Exception:
            pass
    return ivs

def compute_regime(sym):
    """IV percentile vs histórico."""
    try:
        # Último IV de opt_chain_<sym>.txt (cache fresco)
        chain_path = f"data/opt_chain_{sym.lower()}.txt"
        iv_now = None
        with open(chain_path) as f:
            for ln in f:
                if ln.startswith("#"):
                    continue
                p = ln.split()
                if len(p) > 7:
                    try:
                        iv_now = float(p[7])
                        break
                    except Exception:
                        pass
        if not iv_now:
            return None
        
        # Histórico
        ivs = build_iv_history(sym, days=60)
        if len(ivs) < 20:
            return None
        
        p10 = st.quantiles(ivs, n=10)[0] if len(ivs) > 10 else min(ivs)
        p50 = st.median(ivs)
        p90 = st.quantiles(ivs, n=10)[-1] if len(ivs) > 10 else max(ivs)
        
        pct = sum(1 for x in ivs if x <= iv_now) / len(ivs) * 100
        regime = "COMPRESSED" if pct < 10 else "EXPANDED" if pct > 90 else "NORMAL"
        
        return {
            "iv_current": round(iv_now, 2),
            "iv_p10": round(p10, 2),
            "iv_p50": round(p50, 2),
            "iv_p90": round(p90, 2),
            "percentile": round(pct, 0),
            "regime": regime,
            "n_samples": len(ivs)
        }
    except Exception:
        return None

def main():
    out = {}
    for sym in load_fleet():
        r = compute_regime(sym)
        if r:
            out[sym] = r
    tmp = "data/iv_regime.json.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, "data/iv_regime.json")
    print(f"[iv_regime] {len(out)}/{len(load_fleet())} símbolos medidos")

if __name__ == "__main__":
    main()
