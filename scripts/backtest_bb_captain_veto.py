#!/usr/bin/env python3
"""backtest_bb_captain_veto.py — mide retroactivamente el VETO CAPITAN sobre los
fades bb-rebote SHORT de un dia (banda superior). LOTE FUERA DE SESION, solo mide.

Veto (regla 12): capitan SOBRE su gamma flip (data/gex_snapshot.json) -> el fade
del nombre callaria. Mapa: semis->SMH, resto->SPY/QQQ. Variante 'both' = SPY y QQQ
sobre flip vetan a toda la flota. W/L a +30m con cierre de barra 1m local.

Uso: ./venv/bin/python scripts/backtest_bb_captain_veto.py --day 2026-08-04
"""
import argparse, datetime as dt, json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMIS = {"MU", "SKHY", "DRAM", "SMH", "NVDA", "TSM", "ASML", "AMD", "INTC",
         "AVGO", "TXN", "QCOM", "LRCX", "SNDK", "WDC", "STX", "EWY"}
PAT = re.compile(r"^(\d\d:\d\d:\d\d) \| (.*?) \| (\w+) reventó la banda (ARRIBA|ABAJO) y re-entró en ")


def bars(sym):
    d = {}
    try:
        for line in open(os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")):
            r = line.split()
            if len(r) >= 6:
                d[int(float(r[0]))] = float(r[4])
    except FileNotFoundError:
        pass
    return d


def close_at(cache, sym, t):
    if sym not in cache:
        cache[sym] = bars(sym)
    d = cache[sym]
    k = t - t % 60
    for back in range(6):
        if k - back * 60 in d:
            return d[k - back * 60]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    args = ap.parse_args()
    day = dt.date.fromisoformat(args.day)
    sig_path = os.path.join(REPO, "data", "trading-signals", f"{args.day}.txt")
    if not os.path.exists(sig_path):
        sys.exit(f"sin registro de señales: {sig_path}")
    snap = json.load(open(os.path.join(REPO, "data", "gex_snapshot.json")))
    flips = {}
    for cap in ("SPY", "QQQ", "SMH"):
        flip = (snap.get(cap) or {}).get("flip")
        if not isinstance(flip, (int, float)):
            sys.exit(f"sin flip de {cap} en gex_snapshot.json — no se mide con dato inventado")
        flips[cap] = flip

    sigs = []
    for line in open(sig_path):
        m = PAT.match(line)
        if not m:
            continue
        hms, title, sym, lado = m.groups()
        if "BB REBOTE" not in title or "[VETO" in title or "MUTED" in title:
            continue
        h, mi, s = map(int, hms.split(":"))
        t = int(dt.datetime(day.year, day.month, day.day, h, mi, s).timestamp())
        sigs.append({"t": t, "sym": sym, "side": "SHORT" if lado == "ARRIBA" else "LONG"})

    last, ded = {}, []
    for r in sorted(sigs, key=lambda x: x["t"]):
        k = (r["sym"], r["side"])
        if r["t"] - last.get(k, -1e18) > 900:
            ded.append(r)
            last[k] = r["t"]
    shorts = [r for r in ded if r["side"] == "SHORT"]

    cache = {}
    for r in shorts:
        e = close_at(cache, r["sym"], r["t"])
        x = close_at(cache, r["sym"], r["t"] + 1800)
        r["ret30"] = None if e is None or x is None else (e - x) / e * 100

    def above(cap, t):
        s = close_at(cache, cap, t)
        return s is not None and s > flips[cap]

    def vetoed(r, variant):
        if variant == "sector":
            return above("SMH", r["t"]) if r["sym"] in SEMIS else (above("SPY", r["t"]) or above("QQQ", r["t"]))
        return above("SPY", r["t"]) and above("QQQ", r["t"])

    wins = [r for r in shorts if r["ret30"] is not None and r["ret30"] > 0]
    loss = [r for r in shorts if r["ret30"] is not None and r["ret30"] <= 0]
    print(f"{args.day} bb-rebote SHORT dedup15m: n={len(shorts)} W={len(wins)} L={len(loss)} "
          f"sin-barras={len(shorts) - len(wins) - len(loss)}")
    for variant in ("sector", "both"):
        v = [r for r in shorts if vetoed(r, variant)]
        vw = sum(1 for r in v if r in wins)
        vl = sum(1 for r in v if r in loss)
        pct = 100 * vw / len(wins) if wins else 0
        print(f"  veto {variant:6s}: calla {len(v)}/{len(shorts)} | perdedoras {vl}/{len(loss)} "
              f"| ganadoras {vw}/{len(wins)} ({pct:.0f}% de lo bueno)")


if __name__ == "__main__":
    main()
