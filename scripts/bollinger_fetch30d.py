#!/usr/bin/env python3
"""bollinger_fetch30d.py — descarga 30 dias de barras 1m RTH para la flota
(yfinance, ventanas de 7d encadenadas, pausa 2s). Cache:
data/backtest/bars30d_<sym>.csv con "epoch,o,h,l,c,v". Degradacion limpia:
ticker sin data se registra y se sigue. SEÑAL-SOLAMENTE (solo datos)."""
import datetime as dt
import os, sys, time, warnings

warnings.filterwarnings("ignore")
REPO = "/Users/yuniorrodriguezosorio/ib-trader"
OUT = os.path.join(REPO, "data", "backtest")
os.makedirs(OUT, exist_ok=True)

import yfinance as yf

fleet = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
today = dt.date.today()
start30 = today - dt.timedelta(days=30)

# ventanas de 7 dias encadenadas (yfinance limita 1m a ~7d por request y 30d hacia atras)
windows = []
s = start30
while s < today:
    e = min(s + dt.timedelta(days=7), today + dt.timedelta(days=1))
    windows.append((s, e))
    s = e

failures, ok = [], []
for sym in fleet:
    rows = {}
    err = None
    for (ws, we) in windows:
        try:
            df = yf.download(sym, start=ws.isoformat(), end=we.isoformat(),
                             interval="1m", prepost=False, progress=False,
                             auto_adjust=False, threads=False)
            if df is not None and len(df):
                if hasattr(df.columns, "levels"):   # MultiIndex (yf>=0.2.x)
                    df.columns = [c[0] for c in df.columns]
                for ts, r in df.iterrows():
                    ep = int(ts.timestamp())
                    try:
                        rows[ep] = (float(r["Open"]), float(r["High"]),
                                    float(r["Low"]), float(r["Close"]),
                                    int(r["Volume"]) if r["Volume"] == r["Volume"] else 0)
                    except Exception:
                        pass
        except Exception as e:
            err = str(e)[:120]
        time.sleep(2)
    if not rows:
        failures.append((sym, err or "sin data"))
        print(f"FAIL {sym}: {err or 'sin data'}", flush=True)
        continue
    path = os.path.join(OUT, f"bars30d_{sym.lower()}.csv")
    with open(path, "w") as f:
        f.write("epoch,o,h,l,c,v\n")
        for ep in sorted(rows):
            o, h, l, c, v = rows[ep]
            f.write(f"{ep},{o:.4f},{h:.4f},{l:.4f},{c:.4f},{v}\n")
    ok.append((sym, len(rows)))
    print(f"OK {sym}: {len(rows)} barras", flush=True)

print("\nRESUMEN")
for sym, n in ok:
    print(f"  {sym}: {n}")
for sym, e in failures:
    print(f"  FAIL {sym}: {e}")
