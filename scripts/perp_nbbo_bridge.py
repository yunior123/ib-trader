#!/usr/bin/env python3
"""perp_nbbo_bridge.py -- puente tonto: data/perp_stocks.json (bybit) -> data/nbbo_<sym>usdt.txt
para que price_alarm.cpp (que solo sabe leer data/nbbo_<sym>.txt) arme alarmas sobre perps.
Cero computo de senal. SOLO LECTURA de perp_stocks.json, solo ESCRITURA de nbbo_*usdt.txt.

Si perp_stock_fetch.py muere, feed_ts de la fuente deja de avanzar: al pasar MAX_SRC_AGE_S
este puente deja de refrescar el nbbo derivado (nunca fabrica frescura), y price_alarm lo
descarta solo por su propio chequeo de <=10s -- fail-loud, no un precio plausible pero viejo.
"""
import os, sys, json, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SRC = "data/perp_stocks.json"
INTERVAL_S = 3
MAX_SRC_AGE_S = 60


def write_nbbo(sym, bid, ask):
    dst = f"data/nbbo_{sym.lower()}usdt.txt"
    tmp = f"{dst}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(f"{int(time.time())} {bid:.4f} {ask:.4f}\n")
    os.replace(tmp, dst)


def one_pass():
    with open(SRC) as f:
        data = json.load(f)
    now = time.time()
    for sym, row in data.items():
        ts, bid, ask = row.get("feed_ts"), row.get("bid"), row.get("ask")
        if not ts or not bid or not ask or bid <= 0 or ask < bid:
            continue
        if now - ts > MAX_SRC_AGE_S:
            continue
        write_nbbo(sym, bid, ask)


def main():
    while True:
        try:
            one_pass()
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[warn] {e}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
