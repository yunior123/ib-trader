#!/usr/bin/env python3
"""koru_overnight_feed.py — quotes overnight de KORU (3x bull Corea) y KORZ
(3x bear) a data/nbbo_{koru,korz}.txt para price_alarm/sirenas durante la
sesion KRX (dom-jue 20:00-02:30 ET). Creado 2026-07-19, KORZ añadido misma
noche (orden "avisame para comprar koru o korz"). Señal-solamente.
clientId 96. reqMarketDataType(1) — delayed PROHIBIDO."""
import sys, time
sys.path.insert(0, "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader")
import os
os.chdir("/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader")
from ib_insync import IB, Stock

SYMS = ["KORU", "SOXS", "SQQQ", "SOXL", "TQQQ"]

while True:
    try:
        ib = IB(); ib.connect("127.0.0.1", int(__import__("os").environ.get("IBKR_PORT","4002")), clientId=96, readonly=True, timeout=15)
        ib.reqMarketDataType(1)
        tickers = {}
        for sym in SYMS:
            try:
                c = Stock(sym, "OVERNIGHT", "USD")
                if ib.qualifyContracts(c):
                    tickers[sym.lower()] = ib.reqMktData(c, "", False, False)
                    print(f"{sym} feed: OVERNIGHT suscrito", file=sys.stderr)
                else:
                    print(f"{sym}: no cualifica en OVERNIGHT", file=sys.stderr)
            except Exception as e:
                print(f"{sym}: subscribe fallo ({e})", file=sys.stderr)
        while ib.isConnected():
            ib.sleep(2)
            for name, t in tickers.items():
                if t.bid and t.ask and t.bid > 0 and t.ask > t.bid:
                    with open(f"data/nbbo_{name}.txt", "w") as f:
                        f.write(f"{time.time():.0f} {t.bid:.4f} {t.ask:.4f}\n")
        raise ConnectionError("TWS desconectado")
    except Exception as e:
        print(f"koru/korz feed caido: {e} — retry 15s", file=sys.stderr)
        time.sleep(15)
