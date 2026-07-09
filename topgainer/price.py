#!/usr/bin/env python3
"""Fast last-price lookups for the top-gainer system.

The watchdog needs a price roughly every second. We do NOT have an IBKR
real-time data subscription (reqMktData blocked, Error 10089 — see memory),
so we use the same real feeds the fleet already uses, in priority order:
  1) Finnhub /quote REST (free key in feeds.env) — sub-second, includes
     premarket; this is the primary per-second source.
  2) yfinance 1m prepost — universal fallback (handles 4:00-20:00).
Both return REAL prices (delayed IBKR data was explicitly rejected by Yunior).
"""
import os
import time
import warnings

warnings.filterwarnings("ignore")

_FINNHUB_KEY = None


def _load_finnhub_key():
    global _FINNHUB_KEY
    if _FINNHUB_KEY is not None:
        return _FINNHUB_KEY
    _FINNHUB_KEY = ""
    envp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feeds.env")
    if os.path.exists(envp):
        for line in open(envp):
            line = line.strip()
            if line.startswith("FINNHUB_KEY="):
                _FINNHUB_KEY = line.split("=", 1)[1].strip().strip('"')
    return _FINNHUB_KEY


def finnhub_quote(symbol: str):
    """Returns dict {price, prev_close, high, low, ts} or None. Sub-second."""
    key = _load_finnhub_key()
    if not key:
        return None
    try:
        import urllib.request
        import json
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={key}"
        with urllib.request.urlopen(url, timeout=4) as r:
            q = json.load(r)
        if not q or not q.get("c"):
            return None
        return {"price": float(q["c"]), "prev_close": float(q.get("pc") or 0),
                "high": float(q.get("h") or 0), "low": float(q.get("l") or 0),
                "ts": float(q.get("t") or time.time()), "src": "finnhub"}
    except Exception:
        return None


def yahoo_last(symbol: str):
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period="1d", interval="1m", prepost=True)
        if df.empty:
            return None
        last = df.iloc[-1]
        return {"price": float(last.Close), "prev_close": float(df.iloc[0].Open),
                "high": float(df.High.max()), "low": float(df.Low.min()),
                "ts": df.index[-1].timestamp(), "src": "yahoo"}
    except Exception:
        return None


def usdcad(default: float = 1.45) -> float:
    """USD->CAD rate. TFSA base is CAD; USD buys draw CAD via auto-FX, so we need
    this to size orders against the CAD balance. Biased slightly HIGH by callers
    (fewer USD, more conservative) to avoid ever overspending. Yahoo primary."""
    try:
        import yfinance as yf
        v = float(yf.Ticker("CAD=X").history(period="1d").Close.iloc[-1])
        if 1.0 < v < 2.0:
            return v
    except Exception:
        pass
    return default


def last_price(symbol: str):
    """Best-available real last price. Finnhub first (fast), Yahoo fallback."""
    q = finnhub_quote(symbol)
    if q and q["price"] > 0:
        return q
    return yahoo_last(symbol)


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "DRAM"
    print(last_price(sym))
