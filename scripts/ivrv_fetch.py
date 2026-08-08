#!/usr/bin/env python3
"""ivrv_fetch.py — IV vs RV diario (un año) por simbolo desde UW. PUENTE TONTO.

/api/stock/{t}/volatility/realized devuelve 251 filas: `implied_volatility` del dia y
`realized_volatility` REALIZADA DESPUES (el campo `unshifted_rv_date` va ~30 dias por delante),
o sea la prima de riesgo de varianza alineada sin look-ahead al reves. Las ultimas ~30 filas
traen rv=null porque la ventana futura aun no cerro: se guardan tal cual, jamas se rellenan.

Salida: data/research/ivrv_<sym>.json
"""
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

OUT = "data/research"
UA = "ib-trader/1.0 (ivrv research)"


def get(path, tok):
    req = urllib.request.Request("https://api.unusualwhales.com" + path,
                                 headers={"Authorization": "Bearer " + tok,
                                          "Accept": "application/json", "User-Agent": UA})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read()).get("data")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                time.sleep((5, 15, 40, 60)[i])
                continue
            if e.code == 401:
                sys.exit("ivrv_fetch ROTO: 401")
            return None
        except Exception:
            time.sleep(2)
    return None


def main():
    syms = [s.upper() for s in (sys.argv[1:] or open("data/fleet.txt").read().split())]
    tok = token()
    if not tok:
        sys.exit("ivrv_fetch ROTO: sin UW_TOKEN")
    os.makedirs(OUT, exist_ok=True)
    for sym in syms:
        rows = get("/api/stock/%s/volatility/realized" % sym, tok)
        if not rows:
            print("  %-5s SIN DATOS" % sym)
            continue
        out = []
        for r in rows:
            try:
                out.append({"date": r["date"], "px": float(r["price"]),
                            "iv": float(r["implied_volatility"]),
                            "rv": (float(r["realized_volatility"])
                                   if r.get("realized_volatility") is not None else None),
                            "rv_date": r.get("unshifted_rv_date")})
            except (KeyError, TypeError, ValueError):
                continue
        p = os.path.join(OUT, "ivrv_%s.json" % sym.lower())
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f, separators=(",", ":"))
        os.replace(tmp, p)
        con_rv = sum(1 for r in out if r["rv"] is not None)
        print("  %-5s %3d dias (%d con RV futura cerrada)  %s..%s"
              % (sym, len(out), con_rv, out[0]["date"], out[-1]["date"]))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
