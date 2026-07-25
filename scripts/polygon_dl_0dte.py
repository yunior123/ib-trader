#!/usr/bin/env python3
"""Baja barras 5m de contratos 0DTE (exp = el mismo dia) para QQQ/SPY/NVDA, dias 07-15..07-24.
Reusa polygon_dl.poly() + tabla poly_opt_bars."""
import os, sys, time, sqlite3, datetime as dt
os.environ['TZ'] = 'America/New_York'; time.tzset()
REPO = "/Users/yuniorrodriguezosorio/ib-trader"
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("POLY_SLEEP", "0.6")
import polygon_dl as P
P.SLEEP = 0.6

DAYS = ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21",
        "2026-07-22", "2026-07-23", "2026-07-24"]
BAND = {"QQQ": 0.012, "SPY": 0.012, "NVDA": 0.035}

c = sqlite3.connect("trades.db", timeout=60)
c.execute("PRAGMA journal_mode=WAL")


def spot(sym, day):
    d0 = int(dt.datetime.strptime(day + " 09:35", "%Y-%m-%d %H:%M").timestamp()) * 1000
    r = c.execute("SELECT c FROM poly_bars WHERE sym=? AND ts<=? ORDER BY ts DESC LIMIT 1",
                  (sym, d0)).fetchone()
    if r:
        return r[0]
    # 07-24: barras IBKR
    p = f"data/bars_{sym.lower()}_ibkr.txt"
    best = None
    for ln in open(p):
        q = ln.split()
        if len(q) >= 5 and int(q[0]) <= d0 // 1000:
            best = float(q[4])
    return best


tot = 0
for sym in ("QQQ", "SPY", "NVDA"):
    for day in DAYS:
        sp = spot(sym, day)
        if not sp:
            print(f"! {sym} {day}: sin spot"); continue
        lo, hi = sp * (1 - BAND[sym]), sp * (1 + BAND[sym])
        d = P.poly(f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={sym}"
                   f"&expired=true&expiration_date={day}"
                   f"&strike_price.gte={lo:.1f}&strike_price.lte={hi:.1f}&limit=250")
        cons = (d or {}).get("results") or []
        if not cons:
            print(f"! {sym} {day}: sin contratos 0DTE (spot {sp:.2f})"); continue
        n_day = 0
        for k in cons:
            otk = k["ticker"]
            have = c.execute("SELECT COUNT(*) FROM poly_opt_bars WHERE otk=? AND ts>=?",
                             (otk, int(dt.datetime.strptime(day, "%Y-%m-%d").timestamp()) * 1000)).fetchone()[0]
            if have:
                continue
            url = (f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/5/minute/"
                   f"{day}/{day}?adjusted=true&sort=asc&limit=50000")
            dd = P.poly(url)
            for b in (dd or {}).get("results") or []:
                c.execute("INSERT OR IGNORE INTO poly_opt_bars VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (otk, sym, k.get("expiration_date"), k.get("strike_price"),
                           k.get("contract_type"), int(b["t"]), b["o"], b["h"], b["l"], b["c"], b.get("v", 0)))
                n_day += 1
            time.sleep(0.6)
        c.commit(); tot += n_day
        print(f"{sym} {day} spot {sp:.2f} contratos {len(cons)} +{n_day} barras", flush=True)
print("TOTAL", tot)
