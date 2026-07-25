#!/usr/bin/env python3
"""fri_bars_prep.py — arma CSVs compuestos (historico + dias recientes de IBKR)
para backtestear los engines sobre un DIA concreto sin perder el contexto de
SMA20 diaria / 1H que los detectores necesitan.

Fuentes:
  - data/backtest/bars3mo5m_<sym>.csv  (yfinance 5m, ~3 meses, RTH, hasta 7/22)
  - data/backtest/bars30d_<sym>.csv    (yfinance 1m, 30 dias, RTH, hasta 7/22)
  - data/history/<YYYY-MM-DD>/bars/<sym>.txt  ("EPOCH O H L C V" espaciado, IBKR
    1m con premarket) para los dias que faltan.

Salida: data/backtest/fri/bars5m_<sym>.csv y bars1m_<sym>.csv (mismo formato CSV
que los engines/scripts ya esperan: epoch,o,h,l,c,v).

Filtro RTH 09:30-15:59 ET en los dias IBKR para ser homogeneo con yfinance
(el premarket distorsionaria las barras diarias/VWAP). Sin look-ahead: solo se
concatena, no se altera nada.
"""
import csv, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
os.environ["TZ"] = "America/New_York"; time.tzset()

OUT = "data/backtest/fri"
os.makedirs(OUT, exist_ok=True)


def read_csv(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for r in csv.reader(open(path)):
        if not r or r[0] == "epoch":
            continue
        try:
            rows.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
        except Exception:
            continue
    return rows


def read_ibkr(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for ln in open(path):
        p = ln.split()
        if len(p) < 6:
            continue
        try:
            t = int(p[0]); o, h, l, c = (float(x) for x in p[1:5]); v = float(p[5])
        except Exception:
            continue
        lt = time.localtime(t)
        mins = lt.tm_hour * 60 + lt.tm_min
        if mins < 570 or mins >= 960:        # RTH 09:30 <= t < 16:00
            continue
        if h <= 0 or c <= 0:
            continue
        rows.append((t, o, h, l, c, v))
    return rows


def agg(rows, secs):
    out = {}
    for t, o, h, l, c, v in rows:
        k = t - t % secs
        if k not in out:
            out[k] = [k, o, h, l, c, v]
        else:
            b = out[k]; b[2] = max(b[2], h); b[3] = min(b[3], l); b[4] = c; b[5] += v
    return [tuple(b) for k, b in sorted(out.items())]


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "o", "h", "l", "c", "v"])
        for r in rows:
            w.writerow([r[0], f"{r[1]:.4f}", f"{r[2]:.4f}", f"{r[3]:.4f}", f"{r[4]:.4f}", int(r[5])])


def main():
    days = os.environ.get("FRI_DAYS", "2026-07-23,2026-07-24").split(",")
    syms = sys.argv[1:]
    if not syms:
        syms = sorted(os.path.basename(p).split("bars3mo5m_")[1][:-4]
                      for p in __import__("glob").glob("data/backtest/bars3mo5m_*.csv"))
    n_ok = 0
    for sym in syms:
        base5 = read_csv(f"data/backtest/bars3mo5m_{sym}.csv")
        base1 = read_csv(f"data/backtest/bars30d_{sym}.csv")
        if not base5:
            print(f"  {sym:6s} SIN base 5m — saltado"); continue
        extra = []
        for d in days:
            extra += read_ibkr(f"data/history/{d}/bars/{sym}.txt")
        if not extra:
            print(f"  {sym:6s} SIN barras IBKR de {days} — saltado"); continue
        cut = max(b[0] for b in base5)
        extra = [b for b in extra if b[0] > cut]
        m5 = {b[0]: b for b in base5}
        for b in agg(extra, 300):
            m5[b[0]] = b
        cut1 = max((b[0] for b in base1), default=0)
        m1 = {b[0]: b for b in base1}
        for b in extra:
            if b[0] > cut1:
                m1[b[0]] = b
        r5 = [m5[k] for k in sorted(m5)]
        r1 = [m1[k] for k in sorted(m1)]
        write(f"{OUT}/bars5m_{sym}.csv", r5)
        write(f"{OUT}/bars1m_{sym}.csv", r1)
        n_ok += 1
        print(f"  {sym:6s} 5m={len(r5):6d} (+{len(agg(extra,300))})  1m={len(r1):6d} (+{len(extra)})  "
              f"ultimo={time.strftime('%Y-%m-%d %H:%M', time.localtime(r5[-1][0]))}")
    print(f"\n{n_ok} simbolos -> {OUT}/")


if __name__ == "__main__":
    main()
