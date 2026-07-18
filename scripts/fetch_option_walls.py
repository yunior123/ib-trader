#!/usr/bin/env python
"""Muros de opciones (OI por strike) via TWS local — fallback cuando el MCP
claude.ai get_option_data falla (roto server-side 2026-07-17).

Uso: ./venv/bin/python scripts/fetch_option_walls.py 20260724 NVDA:200:215 AMD:460:510
     (expiry YYYYMMDD, luego SYM:min_strike:max_strike ...)
Requiere TWS live en 7496. OI = generic tick 101 (call/putOpenInterest).
"""
import sys
from collections import defaultdict
from ib_insync import IB, Option

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    exp = sys.argv[1]
    ib = IB()
    ib.connect('127.0.0.1', 7496, clientId=87, timeout=10)
    rows = []
    for spec in sys.argv[2:]:
        sym, lo, hi = spec.split(':')
        lo, hi = float(lo), float(hi)
        chains = [c for c in ib.reqSecDefOptParams(sym, '', 'STK',
                  ib.qualifyContracts(__import__('ib_insync').Stock(sym, 'SMART', 'USD'))[0].conId)
                  if c.exchange == 'SMART' and c.tradingClass == sym]
        strikes = sorted(k for k in chains[0].strikes if lo <= k <= hi) if chains else []
        cons = [Option(sym, exp, k, r, 'SMART', tradingClass=sym)
                for k in strikes for r in ('C', 'P')]
        qual = ib.qualifyContracts(*cons)
        tickers = [ib.reqMktData(c, genericTickList='101') for c in qual]
        ib.sleep(6)
        for c, t in zip(qual, tickers):
            oi = t.callOpenInterest if c.right == 'C' else t.putOpenInterest
            vol = t.volume if t.volume == t.volume else 0
            rows.append((sym, c.strike, c.right,
                         oi if oi == oi else -1, int(vol)))
            ib.cancelMktData(c)
    d = defaultdict(dict)
    for sym, k, r, oi, vol in rows:
        d[(sym, k)][r] = (oi, vol)
    print(f"{'SYM':5} {'strike':>7} {'C_OI':>9} {'P_OI':>9} {'C_vol':>8} {'P_vol':>8}")
    for (sym, k), v in sorted(d.items()):
        c = v.get('C', (-1, 0)); p = v.get('P', (-1, 0))
        print(f"{sym:5} {k:7.1f} {c[0]:9.0f} {p[0]:9.0f} {c[1]:8d} {p[1]:8d}")
    ib.disconnect()

main()
