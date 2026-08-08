#!/usr/bin/env python3
"""architect_backtest.py — win rate REAL de las operaciones publicadas por @astocks92.

Se extraen de sus tuits las operaciones CONCRETAS (ticker + strike + C/P) y se evalua cada una
contra el precio del subyacente (diarios de Polygon). SIN precios de opcion no se puede medir
el P&L del contrato, asi que se miden las dos cosas que SI son medibles y se publican por
separado, sin mezclarlas:

  1. DIRECCION: ¿el subyacente se movio a favor de la pata (C=arriba, P=abajo) al cierre de
     H sesiones?  -> win rate direccional.
  2. ITM: ¿el subyacente CRUZO el strike en algun momento antes del vencimiento (o dentro de
     H sesiones si no publico vencimiento)? Es el minimo necesario para que la opcion valga.

Se EXCLUYEN los tuits que no son una entrada suya: reportes de P&L ("ya va 300%"), flujo de
otro ("WILD FLOW $2.2M") y menciones de terceros. La clasificacion va en el JSON para que se
pueda auditar tuit a tuit.

LOTE FUERA DE SESION. Salida: data/research/architect_backtest.json
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

POSTS = os.environ.get("ARCHI_POSTS", "data/research/astocks92_posts.json")
OUT = "data/research/architect_backtest.json"
CACHE = "data/research/px_daily.json"
HORIZONTES = (1, 3, 5, 10)

# un tuit es ENTRADA salvo que hable en pasado o del flujo de otro
NO_ENTRADA = re.compile(
    r"\b(went|now|already|closed|trim|took|up \d|100%|200%|300%|\d+%\+|congrats|"
    r"wild flow|who is hitting|hitting it for|since|worked|almost itm|itm!!|"
    r"roll ?ups? became|expired|was anyone|did you)\b", re.I)
OP = re.compile(r'\$([A-Z]{1,5})\b[^$\n]{0,60}?\$?(\d{2,5}(?:\.\d{1,2})?)\s*([CP])\b')
EXP = re.compile(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2}))?\b')


def key_polygon():
    for ln in open("feeds.env"):
        if ln.startswith("POLYGON_KEY=") or ln.startswith("POLYGON="):
            return ln.strip().split("=", 1)[1]
    return None


def diarios(sym, key, cache):
    """{fecha -> (o,h,l,c)} diarios de Polygon, cacheados en disco."""
    if sym in cache:
        return cache[sym]
    u = ("https://api.polygon.io/v2/aggs/ticker/%s/range/1/day/2026-04-01/2026-08-08"
         "?adjusted=true&limit=400&apiKey=%s" % (sym, key))
    # Polygon Starter = 5 peticiones/minuto. Sin esto los 429 se cachean como "sin precio"
    # y el backtest se queda con 8 operaciones de 50 (pasó en el primer intento).
    d = None
    for intento in range(5):
        try:
            with urllib.request.urlopen(u, timeout=30) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15)
                continue
            return {}                      # 404/403: NO se cachea el vacio, se reintenta otro dia
        except Exception:
            time.sleep(3)
    if d is None:
        return {}
    out = {}
    for b in d.get("results") or []:
        f = dt.datetime.utcfromtimestamp(b["t"] / 1000).strftime("%Y-%m-%d")
        out[f] = (b["o"], b["h"], b["l"], b["c"])
    if not out:
        return {}                      # vacio no se cachea
    cache[sym] = out
    time.sleep(13)                     # 5 req/min del plan Starter
    return out


def extrae(posts):
    ops = []
    for t in posts:
        txt = t["text"]
        vistos = set()
        for m in OP.finditer(txt):
            sym, strike, cp = m.group(1), float(m.group(2)), m.group(3)
            if (sym, strike, cp) in vistos:
                continue
            vistos.add((sym, strike, cp))
            entrada = not NO_ENTRADA.search(txt)
            # vencimiento publicado (dd/mm del propio tuit), si lo hay
            exp = None
            for e in EXP.finditer(txt):
                a, b = int(e.group(1)), int(e.group(2))
                if 1 <= a <= 12 and 1 <= b <= 31:
                    try:
                        exp = dt.date(2026, a, b).isoformat()
                    except ValueError:
                        exp = None
                    break
            ops.append(dict(id=t["id"], fecha=t["created_at"][:10], sym=sym, strike=strike,
                            cp=cp, exp=exp, entrada=entrada,
                            txt=" ".join(txt.split())[:180]))
    return ops


def main():
    if not os.path.exists(POSTS):
        sys.exit("architect_backtest ROTO: falta %s (exportar los tuits antes)" % POSTS)
    posts = json.load(open(POSTS))
    key = key_polygon()
    if not key:
        sys.exit("architect_backtest ROTO: sin POLYGON en feeds.env")
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except ValueError:
            cache = {}

    ops = extrae(posts)
    res = []
    for o in ops:
        px = diarios(o["sym"], key, cache)
        if not px:
            o["motivo"] = "sin precios de %s en Polygon" % o["sym"]
            res.append(o)
            continue
        ds = sorted(px)
        post = [d for d in ds if d >= o["fecha"]]
        if not post:
            o["motivo"] = "el tuit es posterior al ultimo dia con precio"
            res.append(o)
            continue
        d0 = post[0]
        entrada_px = px[d0][3] if d0 == o["fecha"] else px[d0][0]   # cierre del dia, o apertura siguiente
        dirn = 1 if o["cp"] == "C" else -1
        o["entry_px"] = round(entrada_px, 2)
        # ¿cruzo el strike antes del vencimiento (o en H=10 si no hay vencimiento)?
        lim = o["exp"] if o["exp"] and o["exp"] >= d0 else None
        ventana = [d for d in post if (d <= lim if lim else True)][:60 if lim else 11]
        if ventana:
            hi = max(px[d][1] for d in ventana)
            lo = min(px[d][2] for d in ventana)
            o["itm"] = bool(hi >= o["strike"]) if o["cp"] == "C" else bool(lo <= o["strike"])
            o["dist_pct"] = round(100 * (o["strike"] / entrada_px - 1), 2)
        for H in HORIZONTES:
            if len(post) > H:
                r = (px[post[H]][3] / entrada_px - 1) * 100 * dirn
                o["ret_h%d" % H] = round(r, 2)
        res.append(o)

    json.dump(cache, open(CACHE, "w"))
    json.dump(res, open(OUT, "w"), indent=1)

    ent = [o for o in res if o["entrada"] and "entry_px" in o]
    print("tuits analizados: %d | operaciones extraidas: %d | ENTRADAS con precio: %d"
          % (len(posts), len(ops), len(ent)))
    print("  (descartadas %d por no ser entrada suya, %d sin precio)"
          % (sum(1 for o in res if not o["entrada"]), sum(1 for o in res if "motivo" in o)))
    print("\n%-6s %6s %8s %8s" % ("horiz.", "n", "win rate", "ret medio"))
    for H in HORIZONTES:
        v = [o["ret_h%d" % H] for o in ent if "ret_h%d" % H in o]
        if not v:
            continue
        print("%-6s %6d %7.1f%% %+8.2f%%" % ("H=%d" % H, len(v),
                                             100 * sum(1 for x in v if x > 0) / len(v),
                                             sum(v) / len(v)))
    itm = [o for o in ent if "itm" in o]
    if itm:
        print("\nITM antes del vencimiento: %d de %d (%.1f%%)  |  distancia media al strike %+.1f%%"
              % (sum(1 for o in itm if o["itm"]), len(itm),
                 100 * sum(1 for o in itm if o["itm"]) / len(itm),
                 sum(o["dist_pct"] for o in itm) / len(itm)))
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
