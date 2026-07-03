#!/usr/bin/env python3
"""reconstruct_flow.py — reconstruye FLUJO DIARIO histórico (P/C por volumen)
desde Polygon para los capitanes+líderes, 3 meses (2026-07-23).

Por cada viernes de vencimiento semanal en la ventana, baja los contratos ±8%
ATM y el volumen DIARIO de cada uno (una llamada por contrato cubre su semana),
y suma volumen call vs put por día -> P/C diario real. Salida:
data/backtest/flow_daily_<sym>.csv (date,volC,volP,pc,spot).
"""
import json, urllib.request, time, os, csv, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
K = None
for ln in open(os.path.join(REPO, "config", "feeds.env")):
    if ln.startswith("POLYGON_KEY"):
        K = ln.split("=", 1)[1].strip().strip('"')

_cache = {}
def poly(u):
    if u in _cache: return _cache[u]
    full = u + ("&" if "?" in u else "?") + "apiKey=" + K
    for _ in range(3):
        try:
            d = json.load(urllib.request.urlopen(full, timeout=30)); _cache[u] = d; return d
        except Exception:
            time.sleep(1.2)
    return {}

def spot_of(sym):
    """cierres diarios del subyacente desde bars3mo5m -> dict date->close (ultimo del dia)."""
    out = {}
    try:
        for r in csv.reader(open(f"data/backtest/bars3mo5m_{sym.lower()}.csv")):
            try:
                t = int(r[0]); c = float(r[4])
                out[time.strftime("%Y-%m-%d", time.localtime(t))] = c
            except Exception:
                continue
    except Exception:
        pass
    return out

def fridays(d0, d1):
    """viernes YYYY-MM-DD entre d0 y d1 (epochs)."""
    out = []
    t = d0
    while t <= d1:
        lt = time.localtime(t)
        if lt.tm_wday == 4:
            out.append(time.strftime("%Y-%m-%d", lt))
        t += 86400
    return out

def recon(sym):
    sp = spot_of(sym)
    if not sp:
        return
    dates = sorted(sp)
    d0 = time.mktime(time.strptime(dates[0], "%Y-%m-%d"))
    d1 = time.mktime(time.strptime(dates[-1], "%Y-%m-%d"))
    # dia -> [volC, volP]
    daily = {}
    for exp in fridays(d0, d1 + 7 * 86400):
        # spot de referencia ~ el del lunes de esa semana (aprox con el ultimo <= exp)
        ref = None
        for dd in dates:
            if dd <= exp: ref = sp[dd]
        if not ref: ref = sp[dates[-1]]
        contracts = []
        for typ in ("call", "put"):
            d = poly(f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={sym.upper()}"
                     f"&expiration_date={exp}&contract_type={typ}&strike_price.gte={ref*0.92:.0f}"
                     f"&strike_price.lte={ref*1.08:.0f}&expired=true&limit=250")
            contracts += [(r["ticker"], typ) for r in d.get("results", [])]
        # una llamada por contrato: volumen diario de toda su vida
        wk_from = time.strftime("%Y-%m-%d", time.localtime(time.mktime(time.strptime(exp, "%Y-%m-%d")) - 7 * 86400))
        for otk, typ in contracts:
            d = poly(f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/1/day/{wk_from}/{exp}?adjusted=true&limit=60")
            for r in d.get("results", []):
                dd = time.strftime("%Y-%m-%d", time.localtime(r["t"] // 1000))
                b = daily.setdefault(dd, [0, 0])
                b[0 if typ == "call" else 1] += r.get("v", 0)
    path = f"data/backtest/flow_daily_{sym.lower()}.csv"
    with open(path, "w") as f:
        f.write("date,volC,volP,pc,spot\n")
        for dd in sorted(daily):
            vc, vp = daily[dd]
            f.write(f"{dd},{vc:.0f},{vp:.0f},{vp/max(vc,1):.4f},{sp.get(dd,0):.2f}\n")
    n = len(daily)
    print(f"{sym.upper()}: {n} dias de flujo reconstruido -> {path}")

if __name__ == "__main__":
    for s in (sys.argv[1:] or ["spy", "qqq", "smh", "nvda", "mu"]):
        recon(s)
