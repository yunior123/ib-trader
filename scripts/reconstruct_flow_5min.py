#!/usr/bin/env python3
"""reconstruct_flow_intraday.py — flujo INTRADIA reconstruido (P/C horario) desde
Polygon para capitanes+lideres, 3 meses (2026-07-23). MISMO costo que el diario
(~1800 llamadas): mismos contratos, barras horarias en vez de diarias.

Por cada contrato ±8% ATM de cada viernes semanal, baja sus barras HORARIAS y
suma volumen call vs put por (fecha, hora) -> P/C horario real. Salida:
data/backtest/flow_5min_<sym>.csv (epoch_hora,volC_acum_dia,volP_acum_dia,pc,spot).
El volumen es ACUMULADO del dia (como la grabadora en vivo) para que el detector
de spikes vea el RITMO de acumulacion igual que flow_pulse.
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
            d = json.load(urllib.request.urlopen(full, timeout=45)); _cache[u] = d; return d
        except Exception:
            time.sleep(1.2)
    return {}

def spot_daily(sym):
    out = {}
    try:
        for r in csv.reader(open(f"data/backtest/bars3mo5m_{sym.lower()}.csv")):
            if r and r[0][0].isdigit():
                out[time.strftime("%Y-%m-%d", time.localtime(int(r[0])))] = float(r[4])
    except Exception:
        pass
    return out

def fridays(d0, d1):
    out = []; t = d0
    while t <= d1:
        if time.localtime(t).tm_wday == 4:
            out.append(time.strftime("%Y-%m-%d", time.localtime(t)))
        t += 86400
    return out

def recon(sym):
    sp = spot_daily(sym)
    if not sp: return
    dates = sorted(sp)
    d0 = time.mktime(time.strptime(dates[0], "%Y-%m-%d"))
    d1 = time.mktime(time.strptime(dates[-1], "%Y-%m-%d"))
    hourly = {}   # epoch_bucket5m -> [volC, volP]
    for exp in fridays(d0, d1 + 7 * 86400):
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
        wk_from = time.strftime("%Y-%m-%d", time.localtime(time.mktime(time.strptime(exp, "%Y-%m-%d")) - 7 * 86400))
        for otk, typ in contracts:
            d = poly(f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/5/minute/{wk_from}/{exp}?adjusted=true&limit=5000&sort=asc")
            for r in d.get("results", []):
                he = (r["t"] // 1000) // 300 * 300   # bucket de 5 minutos (FIX 2026-07-23: era //3600)
                b = hourly.setdefault(he, [0, 0])
                b[0 if typ == "call" else 1] += r.get("v", 0)
    # volumen ACUMULADO por dia (como la grabadora en vivo)
    path = f"data/backtest/flow_5min_{sym.lower()}.csv"
    rows = sorted(hourly)
    with open(path, "w") as f:
        f.write("epoch,volC,volP,pc,spot\n")
        cur_day = None; cc = cp = 0
        for he in rows:
            day = time.strftime("%Y-%m-%d", time.localtime(he))
            if day != cur_day:
                cur_day = day; cc = cp = 0
            cc += hourly[he][0]; cp += hourly[he][1]
            f.write(f"{he},{cc:.0f},{cp:.0f},{cp/max(cc,1):.4f},{sp.get(day,0):.2f}\n")
    print(f"{sym.upper()}: {len(rows)} buckets 5-min de flujo intradia -> {path}")

if __name__ == "__main__":
    for s in (sys.argv[1:] or ["spy", "qqq", "smh", "nvda", "mu"]):
        recon(s)
