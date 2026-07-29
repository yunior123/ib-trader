#!/usr/bin/env python3
"""opt_book_quality.py — Order book depth quality: detecta "THIN" (bid=ask=0) vs líquido.

Lee opt_chain_<sym>.txt → marca strikes sin cotización válida.
Output: complemento a opt_flow.txt (opcional, para auditoría solo-lectura).

Uso: python3 scripts/opt_book_quality.py SYM (o cron loop).
"""
import json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

def assess_book(sym):
    """Evalúa calidad del libro de opciones por cantidad de strikes ilíquidos."""
    try:
        with open(f"data/opt_chain_{sym.lower()}.txt") as f:
            rows = []
            for ln in f:
                if ln.startswith("#"):
                    continue
                p = ln.split()
                if len(p) >= 5:
                    try:
                        bid, ask = float(p[3]), float(p[4])
                        rows.append({"bid": bid, "ask": ask})
                    except Exception:
                        pass
        if not rows:
            return None
        thin = sum(1 for r in rows if r["bid"] <= 0 or r["ask"] <= 0)
        pct_thin = round(100 * thin / len(rows), 1)
        quality = "EXCELLENT" if pct_thin < 5 else "GOOD" if pct_thin < 15 else "WEAK" if pct_thin < 30 else "THIN"
        return {"total_strikes": len(rows), "iliquids": thin, "pct_thin": pct_thin, "quality": quality}
    except Exception:
        return None

def main():
    if len(sys.argv) < 2:
        sys.exit("uso: opt_book_quality.py SYM [SYM2 ...]")
    for sym in sys.argv[1:]:
        q = assess_book(sym.upper())
        if q:
            print(f"{sym}: {q['quality']} ({q['pct_thin']:.0f}% thin, {q['iliquids']}/{q['total_strikes']})")

if __name__ == "__main__":
    main()
