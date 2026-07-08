#!/usr/bin/env python3
"""Real-price bridge for momentum_bot (C++), 24/5.

REAL data (no delayed): batch-pulls the latest 1m bars for the favorite
tickers from Yahoo (same real source as every backtest), emits
"SYMBOL PRICE EPOCH" lines for the C++ detector AND stores every tick
locally in trades.db (price_stream table). Covers pre/post market too
(prepost=True) so the detector runs whenever US equities print."""

import sqlite3
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import yfinance as yf  # noqa: E402

FAVORITES = ["TSM", "AMD", "DRAM", "ASML", "SPCX", "TSLA", "NVDA", "NOK",
             "AAPL", "INTC", "TXN", "MU", "GOOGL", "QCOM", "SMH", "SPY", "QQQ"]
POLL_SECONDS = 30


def main():
    db = sqlite3.connect("trades.db")
    db.execute("""CREATE TABLE IF NOT EXISTS price_stream (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, symbol TEXT, price REAL)""")
    db.commit()
    print("bridge: Yahoo real 1m, %d tickers, poll %ds, storing to trades.db"
          % (len(FAVORITES), POLL_SECONDS), file=sys.stderr)
    last_emitted = {}
    while True:
        try:
            df = yf.download(" ".join(FAVORITES), period="1d", interval="1m",
                             prepost=True, progress=False, threads=True)
            now = time.time()
            closes = df["Close"] if "Close" in df else df
            for sym in FAVORITES:
                try:
                    series = closes[sym].dropna()
                    if series.empty:
                        continue
                    px = float(series.iloc[-1])
                    bar_ts = series.index[-1].timestamp()
                    if px > 0 and last_emitted.get(sym) != (bar_ts, px):
                        last_emitted[sym] = (bar_ts, px)
                        sys.stdout.write(f"{sym} {px:.4f} {now:.0f}\n")
                        db.execute("INSERT INTO price_stream (ts,symbol,price) VALUES (?,?,?)",
                                   (now, sym, px))
                except Exception:
                    continue
            sys.stdout.flush()
            db.commit()
        except Exception as e:
            print(f"bridge error: {str(e)[:80]}", file=sys.stderr)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
