#!/usr/bin/env python3
"""architect_profit.py — win rate de @astocks92 sobre la PRIMA REAL del contrato.

Orden de Yunior: *"win rate pero en vez de objetivo que haya variado almenos 10% para
profit"*. O sea: no "tocar el strike", sino que la OPCION diera al menos +10% en algun
momento antes de vencer. Eso exige el precio del contrato, no un proxy del subyacente:
se baja de Polygon `/v2/aggs/ticker/O:<contrato>` (agregados por contrato, historicos).

  ENTRADA = cierre del contrato el dia del tuit (si el tuit es de sesion) o la apertura
            de la siguiente sesion con cotizacion.
  GANA    = max(high) desde la entrada hasta el vencimiento >= entrada * (1 + UMBRAL)

NULL DE TEMPORIZACION (el que importa): el MISMO contrato comprado un dia AL AZAR de su
vida cotizada anterior al vencimiento. Mide exactamente lo que se quiere saber — si su
momento de entrada aporta algo sobre entrar en ese contrato en cualquier otro momento.

LOTE FUERA DE SESION. Salida: data/research/architect_profit.json
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

SRC = "data/research/architect_target.json"
CACHE = "data/research/opt_px.json"
OUT = "data/research/architect_profit.json"


def key_polygon():
    for ln in open("feeds.env"):
        if ln.startswith("POLYGON_KEY=") or ln.startswith("POLYGON="):
            return ln.strip().split("=", 1)[1]
    return None


def occ(sym, exp, cp, strike):
    y, m, d = exp.split("-")
    return "O:%s%s%s%s%s%08d" % (sym, y[2:], m, d, cp, round(strike * 1000))


def bajar(contrato, key, cache):
    """{fecha -> (o,h,l,c,v)} del contrato. {} si no existe (y NO se cachea el vacio)."""
    if contrato in cache:
        return cache[contrato]
    u = ("https://api.polygon.io/v2/aggs/ticker/%s/range/1/day/2026-04-01/2026-08-08"
         "?adjusted=true&limit=400&apiKey=%s" % (contrato, key))
    d = None
    for i in range(5):
        try:
            with urllib.request.urlopen(u, timeout=30) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15)
                continue
            return {}
        except Exception:
            time.sleep(3)
    if d is None:
        return {}
    out = {}
    for b in d.get("results") or []:
        f = dt.datetime.utcfromtimestamp(b["t"] / 1000).strftime("%Y-%m-%d")
        out[f] = (b["o"], b["h"], b["l"], b["c"], b.get("v", 0))
    if not out:
        return {}
    cache[contrato] = out
    time.sleep(13)                 # Polygon Starter = 5 req/min
    return out


def main():
    ap = argparse.ArgumentParser(description="win rate sobre la prima real")
    ap.add_argument("--umbral", type=float, default=10.0, help="%% de beneficio que cuenta como acierto")
    a = ap.parse_args()
    U = a.umbral / 100.0
    if not os.path.exists(SRC):
        sys.exit("architect_profit ROTO: corre antes scripts/architect_target.py")
    ops = json.load(open(SRC))["ops"]
    key = key_polygon()
    if not key:
        sys.exit("architect_profit ROTO: sin POLYGON_KEY")
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    res, sin = [], []
    rng = np.random.default_rng(31)
    for o in ops:
        c = occ(o["sym"], o["exp"], o["cp"], o["strike"])
        px = bajar(c, key, cache)
        if not px:
            sin.append(dict(o, contrato=c, motivo="Polygon no tiene ese contrato"))
            continue
        ds = sorted(px)
        post = [d for d in ds if d >= o["fecha"]]
        if len(post) < 2:
            sin.append(dict(o, contrato=c, motivo="sin cotizacion tras el tuit"))
            continue
        i0 = ds.index(post[0])
        entrada = px[ds[i0]][3] if ds[i0] == o["fecha"] else px[ds[i0]][0]
        if not entrada or entrada <= 0:
            sin.append(dict(o, contrato=c, motivo="prima de entrada no valida"))
            continue
        camino = ds[i0 + 1:]
        if not camino:
            sin.append(dict(o, contrato=c, motivo="sin camino tras la entrada"))
            continue
        mfe = max(px[d][1] for d in camino) / entrada - 1
        final = px[camino[-1]][3] / entrada - 1
        gano = bool(mfe >= U)
        # NULL de temporizacion: el MISMO contrato, entrada en un dia al azar de su vida
        aciertos = tot = 0
        for j in range(len(ds) - 1):
            e = px[ds[j]][3]
            if not e or e <= 0:
                continue
            resto = ds[j + 1:]
            if not resto:
                continue
            m = max(px[d][1] for d in resto) / e - 1
            tot += 1
            aciertos += (m >= U)
        base = aciertos / tot if tot else None
        res.append(dict(sym=o["sym"], fecha=o["fecha"], contrato=c, strike=o["strike"],
                        cp=o["cp"], exp=o["exp"], regla=o["regla"], entrada=round(entrada, 2),
                        mfe=round(100 * mfe, 1), final=round(100 * final, 1),
                        gano=gano, base=base, dias=len(camino), txt=o["txt"][:100]))

    json.dump(cache, open(CACHE, "w"))
    json.dump({"umbral_pct": a.umbral, "ops": res, "sin_datos": sin}, open(OUT, "w"), indent=1)

    if not res:
        print("sin contratos con precio (%d intentos)" % len(sin))
        return
    g = np.array([r["gano"] for r in res], dtype=float)
    b = np.array([r["base"] for r in res if r["base"] is not None], dtype=float)
    print("contratos con precio: %d de %d  (%d sin datos en Polygon)"
          % (len(res), len(ops), len(sin)))
    print("\n%-52s %.1f%%  (%d de %d)"
          % ("GANO >= +%.0f%% DE PRIMA antes de vencer" % a.umbral, 100 * g.mean(),
             int(g.sum()), g.size))
    print("%-52s %.1f%%" % ("MISMO contrato, entrada en dia AL AZAR de su vida", 100 * b.mean()))
    print("%-52s %+.1f pp" % ("EDGE de su temporizacion", 100 * (g.mean() - b.mean())))
    dif = np.array([r["gano"] - r["base"] for r in res if r["base"] is not None])
    if dif.size > 2:
        print("%-52s %+.2f  (n=%d)" % ("t emparejado", dif.mean() / (dif.std(ddof=1) / np.sqrt(dif.size)), dif.size))
    mfe = np.array([r["mfe"] for r in res])
    fin = np.array([r["final"] for r in res])
    print("\n%-52s %+.0f%%  (mediana %+.0f%%)" % ("MFE: lo mas que llego a valer", mfe.mean(), np.median(mfe)))
    print("%-52s %+.0f%%  (mediana %+.0f%%)" % ("al VENCIMIENTO, si se aguanta", fin.mean(), np.median(fin)))
    print("\n%-10s %-6s %10s %8s %8s %7s %7s" % ("fecha", "sym", "strike", "prima", "MFE%", "final%", "base%"))
    for r in sorted(res, key=lambda x: x["fecha"]):
        print("%-10s %-6s %9.1f%s %8.2f %+8.0f %+7.0f %6.0f%%  %s"
              % (r["fecha"], r["sym"], r["strike"], r["cp"], r["entrada"], r["mfe"],
                 r["final"], 100 * (r["base"] or 0), "GANA" if r["gano"] else ""))
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
