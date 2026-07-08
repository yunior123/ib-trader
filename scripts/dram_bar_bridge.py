#!/usr/bin/env python3
"""DRAM 1m bar bridge for dram_signal_bot (C++).
Streams REAL Yahoo 1m completed bars: "EPOCH OPEN HIGH LOW CLOSE VOLUME".
Stores every bar locally in trades.db (dram_bars table). 24/5 loop."""

import sqlite3
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import yfinance as yf  # noqa: E402

POLL = 30


def main():
    db = sqlite3.connect("trades.db")
    db.execute("""CREATE TABLE IF NOT EXISTS dram_bars (
        ts REAL PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL)""")
    db.commit()
    print("dram bridge: Yahoo 1m real, almacenando en trades.db", file=sys.stderr)
    last = None
    # warm-up: emit the last 2 days so indicators are hot at startup
    while True:
        try:
            df = yf.Ticker("DRAM").history(period="2d", interval="1m", prepost=True)
            if not df.empty and len(df) >= 3:
                completed = df.iloc[:-1]  # exclude the forming bar
                new = completed if last is None else completed[completed.index > last]
                for ts, r in new.iterrows():
                    ep = ts.timestamp()
                    sys.stdout.write(f"{ep:.0f} {r.Open:.4f} {r.High:.4f} {r.Low:.4f} "
                                     f"{r.Close:.4f} {r.Volume:.0f}\n")
                    db.execute("INSERT OR IGNORE INTO dram_bars VALUES (?,?,?,?,?,?)",
                               (ep, r.Open, r.High, r.Low, r.Close, float(r.Volume)))
                if len(completed):
                    last = completed.index[-1]
                sys.stdout.flush()
                db.commit()
        except Exception as e:
            print(f"bridge error: {str(e)[:80]}", file=sys.stderr)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
