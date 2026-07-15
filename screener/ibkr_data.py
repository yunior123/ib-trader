#!/usr/bin/env python3
"""ibkr_data — datos de mercado IBKR para el screener (orden Yunior
2026-07-15 "no alpaca all over, just ibkr").

Reemplaza los REST de Alpaca en el camino vivo: spread NBBO (gate del
scanner) y movimiento del dia previo (filtro blowoff). Conexion perezosa
readonly a TWS 7496 con clientId unico por proceso (scanner y fastscan
corren simultaneos). Subs NA reales compradas 2026-07-15 -> reqMktData
streaming (marketDataType=1, delayed PROHIBIDO). Cache por simbolo por
proceso. Si TWS no responde: None y a gritar — jamas degradar a delayed.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ib = None
_spread_cache = {}      # sym -> (ts, dict)
_prior_cache = {}       # sym -> (day, pct)


def _conn():
    global _ib
    if _ib is not None and _ib.isConnected():
        return _ib
    try:
        from ib_insync import IB
        ib = IB()
        cid = 90 + (os.getpid() % 40)
        ib.connect("127.0.0.1", 7496, clientId=cid, readonly=True, timeout=8)
        ib.reqMarketDataType(1)          # REALTIME. Delayed PROHIBIDO.
        _ib = ib
        return _ib
    except Exception as e:
        print(f"[ibkr_data] TWS no disponible ({repr(e)[:80]}) — SIN datos "
              f"(delayed prohibido)", file=sys.stderr)
        return None


def spread(symbol: str):
    """Bid/ask NBBO vivo. Returns {bid, ask, spread_pct} | None."""
    c = _spread_cache.get(symbol)
    if c and time.time() - c[0] < 20:
        return c[1]
    ib = _conn()
    if not ib:
        return None
    try:
        from ib_insync import Stock
        con = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(con)
        t = ib.reqMktData(con, "", False, False)
        for _ in range(16):              # hasta ~4s a que aterrice el NBBO
            ib.sleep(0.25)
            if t.bid and t.ask and t.bid > 0 and t.ask > t.bid:
                break
        ib.cancelMktData(con)
        if not (t.bid and t.ask and t.bid > 0 and t.ask > t.bid):
            return None
        mid = (t.bid + t.ask) / 2
        out = {"bid": float(t.bid), "ask": float(t.ask),
               "spread_pct": (t.ask - t.bid) / mid * 100}
        _spread_cache[symbol] = (time.time(), out)
        return out
    except Exception:
        return None


def prior_day_move(symbol: str) -> float:
    """% de la SESION PREVIA (filtro blowoff del scanner). IBKR daily bars."""
    day = time.strftime("%Y%m%d")
    c = _prior_cache.get(symbol)
    if c and c[0] == day:
        return c[1]
    ib = _conn()
    if not ib:
        return 0.0
    try:
        from ib_insync import Stock
        con = Stock(symbol, "SMART", "USD")
        ib.qualifyContracts(con)
        bars = ib.reqHistoricalData(con, "", "5 D", "1 day", "TRADES",
                                    useRTH=True, formatDate=2)
        pct = 0.0
        # bars[-1] = HOY (parcial) -> sesion previa = bars[-2] vs bars[-3]
        if len(bars) >= 3 and bars[-3].close > 0:
            pct = (bars[-2].close - bars[-3].close) / bars[-3].close * 100
        elif len(bars) == 2 and bars[-2].close > 0:
            pct = (bars[-1].close - bars[-2].close) / bars[-2].close * 100
        _prior_cache[symbol] = (day, pct)
        return pct
    except Exception:
        return 0.0
