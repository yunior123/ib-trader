#!/usr/bin/env python3
"""NOK 1m bar bridge (Alpaca IEX real-time primary, Yahoo fallback).
Emits "EPOCH O H L C V" lines; stores bars in trades.db (nok_bars)."""
import os, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
import requests

for line in open(os.path.join(os.path.dirname(__file__), "..", "alpaca.env")):
    k, _, v = line.strip().partition("=")
    os.environ.setdefault(k, v)
H = {"APCA-API-KEY-ID": os.environ["ALPACA_KEY"],
     "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"]}
POLL = 30

def fetch_alpaca():
    r = requests.get("https://data.alpaca.markets/v2/stocks/NOK/bars",
                     params={"timeframe": "1Min", "limit": 1000, "feed": "iex"},
                     headers=H, timeout=15)
    r.raise_for_status()
    return r.json().get("bars") or []

def main():
    db = sqlite3.connect("trades.db")
    db.execute("""CREATE TABLE IF NOT EXISTS nok_bars (
        ts REAL PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL)""")
    db.commit()
    print("nok bridge: Alpaca IEX 1m real", file=sys.stderr)
    last = 0.0
    while True:
        try:
            bars = fetch_alpaca()
            src = "alpaca"
            if not bars:
                import yfinance as yf
                d = yf.Ticker("NOK").history(period="2d", interval="1m", prepost=True)
                bars = [{"t": ts.isoformat(), "o": r.Open, "h": r.High, "l": r.Low,
                         "c": r.Close, "v": r.Volume} for ts, r in d.iterrows()]
                src = "yahoo"
            emitted = 0
            for b in bars[:-1]:  # exclude possibly-forming last bar
                from datetime import datetime
                ts = b["t"]
                ep = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if isinstance(ts, str) else ts.timestamp()
                if ep <= last: continue
                sys.stdout.write(f"{ep:.0f} {b['o']:.4f} {b['h']:.4f} {b['l']:.4f} {b['c']:.4f} {b['v']:.0f}\n")
                db.execute("INSERT OR IGNORE INTO nok_bars VALUES (?,?,?,?,?,?)",
                           (ep, b['o'], b['h'], b['l'], b['c'], float(b['v'])))
                last = ep; emitted += 1
            if emitted:
                sys.stdout.flush(); db.commit()
                print(f"src={src} +{emitted}", file=sys.stderr)
        except Exception as e:
            print(f"bridge error: {str(e)[:80]}", file=sys.stderr)
        time.sleep(POLL)

if __name__ == "__main__":
    main()
