#!/usr/bin/env python3
"""adhoc_chain_2w.py — pull PUNTUAL (Yunior 2026-07-28: "jala dos semanas en adelante"),
NO toca opt_chain_cache.py (ese se queda fijo en las 2 expiries mas cercanas para no
gastar lineas de mercado compartidas). Este es solo para responder la pregunta de HOY:
strikes ATM de MU y DRAM para cada expiry real dentro de ~15 dias, incluyendo 6-ago si
existe. clientId 91, desconecta al salir. SEÑAL-SOLAMENTE, solo lectura."""
import datetime as dt
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from ib_mode import get_port
from ib_insync import IB, Stock, Option

SYMS = os.environ.get("ADHOC_SYMS", "MU,DRAM").split(",")
HORIZON_DAYS = 15

ib = IB()
ib.connect("127.0.0.1", get_port(), clientId=91, readonly=True, timeout=15)
ib.reqMarketDataType(1)

today = dt.date.today()
cutoff = (today + dt.timedelta(days=HORIZON_DAYS)).strftime("%Y%m%d")
today_s = today.strftime("%Y%m%d")

for sym in SYMS:
    stk = Stock(sym, "SMART", "USD")
    ib.qualifyContracts(stk)
    [tkr] = [ib.reqMktData(stk, "", False, False)]
    ib.sleep(2.0)
    spot = tkr.marketPrice() if tkr.marketPrice() == tkr.marketPrice() else tkr.last
    ib.cancelMktData(stk)
    if not spot or spot != spot:
        print(f"{sym}: sin spot, salto"); continue
    ch = ib.reqSecDefOptParams(sym, "", "STK", stk.conId)
    pool = [c for c in ch if c.exchange == "SMART" and c.tradingClass == sym] \
        or [c for c in ch if c.exchange == "SMART"]
    if not pool:
        print(f"{sym}: sin secdef"); continue
    exps = sorted({e for c in pool for e in c.expirations if today_s <= e <= cutoff})
    strikes_all = sorted({k for c in pool for k in c.strikes})
    tc = pool[0].tradingClass
    print(f"\n=== {sym} spot {spot:.2f} — expiries hasta {HORIZON_DAYS}d: {exps} ===")
    for exp in exps:
        ks = sorted(strikes_all, key=lambda k: abs(k - spot))[:6]
        opts = [Option(sym, exp, k, r, "SMART", tradingClass=tc) for k in ks for r in "CP"]
        ok = ib.qualifyContracts(*opts)
        if not ok:
            print(f"  {exp}: sin contratos cualificados"); continue
        tks = [ib.reqMktData(c, "100,101,106", False, False) for c in ok]
        ib.sleep(3.0)
        rows = []
        for t in tks:
            c = t.contract
            bid = t.bid if t.bid == t.bid and t.bid > 0 else -1
            ask = t.ask if t.ask == t.ask and t.ask > 0 else -1
            oi = t.callOpenInterest if c.right == "C" else t.putOpenInterest
            oi = oi if oi == oi else 0
            greeks = t.modelGreeks
            iv = greeks.impliedVol if greeks else None
            delta = greeks.delta if greeks else None
            rows.append((c.strike, c.right, bid, ask, int(oi), iv, delta))
            ib.cancelMktData(c)
        rows.sort(key=lambda r: (r[0], r[1]))
        print(f"  --- exp {exp} ---")
        for k, r, bid, ask, oi, iv, delta in rows:
            spread = (ask - bid) / ((ask + bid) / 2) * 100 if bid > 0 and ask > 0 else None
            print(f"  {k:8.2f} {r}  bid={bid:.2f} ask={ask:.2f} "
                  f"spread={'%.1f%%' % spread if spread is not None else 's/d'} "
                  f"OI={oi} iv={'%.3f' % iv if iv else 's/d'} "
                  f"delta={'%.3f' % delta if delta is not None else 's/d'}")

ib.disconnect()
