#!/usr/bin/env python3
"""skew_rr_fetch.py — baja el RISK REVERSAL 25 DELTA historico de UW y lo archiva.

Es la metrica de @astocks92 ("85th Percentile CALL SKEW 25 Delta"). El endpoint
/api/stock/{t}/historical-risk-reversal-skew devuelve la serie DIARIA de UN vencimiento
mientras estuvo listado; con una escalera de vencimientos mensuales se cubre un año
(medido: expiry 2026-03-20 -> 154 dias desde 2025-08-11).

PUENTE TONTO: baja y escribe. Cero computo de señal aqui.
Salida: data/research/rr25_<sym>.json  {expiry: [{date, risk_reversal}, ...]}
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from uw_premium import token  # noqa: E402

BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (skew rr25 research)"
OUT = "data/research"
PAUSA_S = 0.7                 # ~85 req/min de cupo: por debajo del limite con margen
DELTA = "0.25"


def terceros_viernes(desde="2025-08", hasta="2026-12"):
    """Vencimientos mensuales (3er viernes) del rango — la escalera de la serie."""
    import calendar
    y0, m0 = (int(x) for x in desde.split("-"))
    y1, m1 = (int(x) for x in hasta.split("-"))
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        c = calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(y, m)
        vs = [d for w in c for d in w if d.weekday() == 4 and d.month == m]
        out.append(vs[2].isoformat())
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def get(path, tok, **q):
    u = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(u, headers={"Authorization": "Bearer " + tok,
                                             "Accept": "application/json", "User-Agent": UA})
    for intento in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read()).get("data")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                time.sleep((5, 15, 40, 60)[intento])
                continue
            if e.code == 401:
                sys.exit("skew_rr_fetch ROTO: 401, token caducado")
            return None
        except Exception:
            time.sleep(2)
    return None


def fleet():
    return open("data/fleet.txt").read().split()


def main():
    ap = argparse.ArgumentParser(description="RR 25 delta historico de UW")
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--desde", default="2025-08")
    ap.add_argument("--hasta", default="2026-12")
    a = ap.parse_args()
    syms = [s.upper() for s in (a.syms or fleet())]
    tok = token()
    if not tok:
        sys.exit("skew_rr_fetch ROTO: sin UW_TOKEN")
    exps = terceros_viernes(a.desde, a.hasta)
    os.makedirs(OUT, exist_ok=True)
    print("%d syms x %d vencimientos = %d peticiones (~%.0f min)"
          % (len(syms), len(exps), len(syms) * len(exps), len(syms) * len(exps) * PAUSA_S / 60))
    for sym in syms:
        path = os.path.join(OUT, "rr25_%s.json" % sym.lower())
        acc = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    acc = json.load(f)
            except ValueError:
                acc = {}
        nuevos = 0
        for e in exps:
            if acc.get(e):                      # ya bajado y no vacio: no se re-pide
                continue
            rows = get("/api/stock/%s/historical-risk-reversal-skew" % sym, tok,
                       expiry=e, delta=DELTA)
            acc[e] = [{"date": r["date"], "rr": float(r["risk_reversal"])}
                      for r in (rows or []) if r.get("risk_reversal") is not None]
            nuevos += len(acc[e])
            time.sleep(PAUSA_S)
        dias = {d["date"] for v in acc.values() for d in v}
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(acc, f, separators=(",", ":"))
        os.replace(tmp, path)
        print("  %-5s %2d vencimientos, %4d dias distintos (%s..%s)  +%d filas"
              % (sym, sum(1 for v in acc.values() if v), len(dias),
                 min(dias) if dias else "-", max(dias) if dias else "-", nuevos))


if __name__ == "__main__":
    main()
