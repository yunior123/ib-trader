#!/usr/bin/env python3
"""Alpaca tape bridge for scan_server (C++). REST fast-poll mode: the account's
single free websocket is owned 24/5 by the NOK signal bot ("connection limit
exceeded" on a 2nd connect), so the scanner polls REST instead:

  every ~1s : /v2/stocks/{sym}/trades  since last cursor  -> FULL tape (nothing
              missed between polls) + /quotes/latest      -> top-of-book
  every ~5s : /v2/stocks/{sym}/snapshot                   -> day stats (OHLC,
              prev close, REAL day volume)

~130 req/min, under the 200/min free cap. Active symbol switched by writing
"SUB XYZ" to stdin. Output lines (flushed per event):
  T <sym> <price> <size> <epoch_ms>
  Q <sym> <bid> <bidsz> <ask> <asksz> <epoch_ms>
  D <sym> <open> <high> <low> <prevclose> <dayvol>
  S <msg>
Keys: alpaca.env (gitignored)."""
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://data.alpaca.markets/v2/stocks"


def load_keys():
    env = {}
    for line in open(os.path.join(REPO, "alpaca.env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env["ALPACA_KEY"], env["ALPACA_SECRET"]


KEY, SEC = load_keys()


def get(url):
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC})
    return json.loads(urllib.request.urlopen(req, timeout=4).read())


def out(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def iso_ms(ts):
    try:
        s = ts.replace("Z", "+00:00")
        if "." in s:                       # trim ns -> us for fromisoformat
            head, tail = s.split(".", 1)
            frac = tail[:6].ljust(6, "0")
            tz = tail[len(tail.rstrip("+-0123456789:")):] if "+" in tail or "-" in tail else "+00:00"
            tz = tail[tail.find("+"):] if "+" in tail else "+00:00"
            s = f"{head}.{frac}{tz}"
        return int(datetime.fromisoformat(s).timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


class Scanner:
    def __init__(self, sym):
        self.sym = sym.upper()
        self.cursor = (datetime.now(timezone.utc) - timedelta(seconds=5)) \
            .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.last_quote = None

    def switch(self, sym):
        self.sym = sym.upper()
        self.cursor = (datetime.now(timezone.utc) - timedelta(seconds=5)) \
            .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.last_quote = None
        out(f"S subscribed {self.sym}")

    def poll_trades(self):
        sym = self.sym
        url = f"{BASE}/{sym}/trades?start={self.cursor}&limit=1000&feed=iex"
        d = get(url)
        trades = d.get("trades") or []
        for t in trades:
            out(f"T {sym} {t['p']} {t['s']} {iso_ms(t['t'])}")
        if trades and sym == self.sym:
            last_ts = trades[-1]["t"]
            # advance cursor 1us past the last trade to avoid re-emitting it
            ms = iso_ms(last_ts)
            self.cursor = datetime.fromtimestamp(ms / 1000 + 0.001, timezone.utc) \
                .strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def poll_quote(self):
        sym = self.sym
        d = get(f"{BASE}/{sym}/quotes/latest?feed=iex").get("quote") or {}
        key = (d.get("bp"), d.get("bs"), d.get("ap"), d.get("as"))
        if d and key != self.last_quote:
            self.last_quote = key
            out(f"Q {sym} {d.get('bp', 0)} {d.get('bs', 0)} "
                f"{d.get('ap', 0)} {d.get('as', 0)} {iso_ms(d.get('t', ''))}")

    def poll_snapshot(self):
        sym = self.sym
        d = get(f"{BASE}/{sym}/snapshot?feed=iex")
        day = d.get("dailyBar") or {}
        prev = d.get("prevDailyBar") or {}
        if day:
            out(f"D {sym} {day.get('o', 0)} {day.get('h', 0)} {day.get('l', 0)} "
                f"{prev.get('c', 0)} {day.get('v', 0)}")


def stdin_loop(sc):
    for line in sys.stdin:
        line = line.strip()
        if line.upper().startswith("SUB "):
            sc.switch(line.split(None, 1)[1])


def main():
    sc = Scanner(sys.argv[1] if len(sys.argv) > 1 else "NVDA")
    threading.Thread(target=stdin_loop, args=(sc,), daemon=True).start()
    out(f"S subscribed {sc.sym} (REST fast-poll)")
    n = 0
    while True:
        t0 = time.time()
        try:
            sc.poll_trades()
            sc.poll_quote()
            if n % 5 == 0:
                sc.poll_snapshot()
        except Exception as e:
            out(f"S poll error {str(e)[:80]}")
            time.sleep(2)
        n += 1
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))


if __name__ == "__main__":
    main()
