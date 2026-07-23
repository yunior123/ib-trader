#!/usr/bin/env python3
"""optgate.py — gate de spread de OPCIONES para las alarmas (2026-07-22,
orden Yunior: "dram bid/ask difference is too high, verify always before
sounding any alarm — we could loss a lot of money").

Regla (CLAUDE.md #4): spread <= 5% del premium o NO se paga.
Uso desde cualquier vigia:
    from optgate import opt_vehicle
    veredicto = opt_vehicle("DRAM")   # str listo para pegar al mensaje

Devuelve p.ej.:
  "OPCIONES OK (spread 1%)"                        -> ok=True
  "OPCIONES VETADAS spread 15% — usar ACCIONES o ETF apalancado"
  "OPCIONES s/d (sin cadena fresca) — default acciones"
Lee data/opt_chain_<sym>.txt (cache IBKR, primer OTM ambos lados <= $3).
"""
import os, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_SPREAD_PCT = 5.0
MAX_AGE_S = 900

def opt_spread_pct(sym):
    """spread% del mejor primer-OTM liquido; None si no hay data usable."""
    path = os.path.join(REPO, "data", f"opt_chain_{sym.lower()}.txt")
    try:
        lines = open(path).readlines()
    except Exception:
        return None
    spot = epoch = None
    best = None
    for ln in lines:
        if ln.startswith("#"):
            if "epoch " in ln:
                try:
                    epoch = int(ln.split("epoch ")[1].split(" |")[0])
                    spot = float(ln.split("spot ")[1].split(" |")[0].split()[0])
                except Exception:
                    pass
            continue
        if not spot or (epoch and time.time() - epoch > MAX_AGE_S):
            continue
        f = ln.split()
        if len(f) < 7:
            continue
        try:
            k, r, bid, ask, oi = float(f[0]), f[1], float(f[3]), float(f[4]), float(f[6])
        except ValueError:
            continue
        if bid <= 0 or ask <= 0 or ask > 3.5 or oi < 200:
            continue
        otm = k < spot if r == "P" else k > spot
        if not otm:
            continue
        dist = abs(k - spot) / spot
        pct = (ask - bid) / ask * 100
        if best is None or dist < best[0]:
            best = (dist, pct)
    return best[1] if best else None

def opt_vehicle(sym):
    pct = opt_spread_pct(sym)
    if pct is None:
        return "OPCIONES s/d (sin cadena fresca) — default ACCIONES"
    if pct <= MAX_SPREAD_PCT:
        return f"OPCIONES OK (spread {pct:.0f}%)"
    return f"OPCIONES VETADAS spread {pct:.0f}% — usar ACCIONES o ETF apalancado"

def opt_ok(sym):
    pct = opt_spread_pct(sym)
    return pct is not None and pct <= MAX_SPREAD_PCT

if __name__ == "__main__":
    import sys
    for s in (sys.argv[1:] or ["DRAM", "QQQ", "MU", "SKHY"]):
        print(s.upper(), "->", opt_vehicle(s))
