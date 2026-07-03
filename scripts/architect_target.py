#!/usr/bin/env python3
"""architect_target.py — win rate de @astocks92 medido COMO SE OPERA UNA OPCION.

Correccion de Yunior (2026-08-08): *"el win rate da igual la fecha de las opciones, es solo
q llegue a su objetivo asi sea antes, mide por ahi"*. Tiene razon: una opcion comprada no se
juzga a un horizonte fijo — se juzga por si el subyacente ALCANZO el strike en ALGUN momento
antes del vencimiento. Ahi es donde se cobra.

  GANA  = el subyacente TOCO el strike entre la entrada y el vencimiento
          (call: maximo >= strike · put: minimo <= strike)
  PIERDE= vencio sin tocarlo

Y con el control que hace falta para que el numero signifique algo: **el mismo ticker, la
misma distancia porcentual al strike y los mismos dias hasta vencimiento, pero con la fecha
de entrada elegida al azar**. Sin eso, "tocar un nivel al 6% en 3 semanas" tiene una tasa
base alta y cualquiera parece un genio.

Vencimiento: el publicado; si no, se deduce del texto (WEEKLIES/FRIDAY -> proximo viernes,
NdTE -> N sesiones, LEAPS -> 90 dias) y, en ultimo caso, viernes de la semana siguiente,
que es su estilo por defecto. La regla usada va en el JSON, operacion a operacion.

LOTE FUERA DE SESION. Salida: data/research/architect_target.json
"""
import datetime as dt
import json
import os
import re
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

BT = "data/research/architect_backtest.json"
PX = "data/research/px_daily.json"
OUT = "data/research/architect_target.json"
N_NULL = 400          # entradas aleatorias por operacion


def deduce_exp(o):
    """(fecha_iso, regla). Nunca inventa en silencio: la regla se publica."""
    if o.get("exp"):
        return o["exp"], "publicado"
    t = o["txt"]
    d0 = dt.date.fromisoformat(o["fecha"])
    m = re.search(r"(\d+)\s*DTE", t, re.I)
    if m:
        return (d0 + dt.timedelta(days=int(m.group(1)) + 1)).isoformat(), "%sDTE" % m.group(1)
    if re.search(r"leaps?", t, re.I):
        return (d0 + dt.timedelta(days=90)).isoformat(), "LEAPS -> 90 dias"
    viernes = d0 + dt.timedelta(days=(4 - d0.weekday()) % 7 or 7)
    if re.search(r"weekl|friday", t, re.I):
        return viernes.isoformat(), "WEEKLIES -> proximo viernes"
    return (viernes + dt.timedelta(days=7)).isoformat(), "sin vencimiento -> viernes siguiente"


def toca(px, ds, i0, i1, strike, cp):
    """¿Toco el strike entre los indices [i0, i1] de la serie diaria?"""
    if i1 <= i0:
        return None
    hi = max(px[ds[j]][1] for j in range(i0, i1 + 1))
    lo = min(px[ds[j]][2] for j in range(i0, i1 + 1))
    return bool(hi >= strike) if cp == "C" else bool(lo <= strike)


def main():
    if not (os.path.exists(BT) and os.path.exists(PX)):
        sys.exit("architect_target ROTO: corre antes scripts/architect_backtest.py")
    ops = json.load(open(BT))
    px_all = json.load(open(PX))
    rng = np.random.default_rng(17)

    res, saltadas = [], []
    for o in ops:
        if not o["entrada"] or "entry_px" not in o:
            continue
        px = px_all.get(o["sym"]) or {}
        ds = sorted(px)
        post = [d for d in ds if d >= o["fecha"]]
        if not post:
            continue
        i0 = ds.index(post[0])
        exp, regla = deduce_exp(o)
        fin = [d for d in ds if d <= exp]
        if not fin:
            continue
        i1 = ds.index(fin[-1])
        dias = i1 - i0
        if dias < 1:
            saltadas.append(dict(o, motivo="vencimiento el mismo dia o antes"))
            continue
        entrada = o["entry_px"]
        dist = (o["strike"] / entrada - 1) * (1 if o["cp"] == "C" else -1)   # + = OTM
        if dist <= 0:
            saltadas.append(dict(o, motivo="ya estaba ITM al entrar (%.1f%%)" % (100 * dist)))
            continue
        gano = toca(px, ds, i0, i1, o["strike"], o["cp"])

        # NULL: mismo ticker, misma distancia %, mismos dias, fecha de entrada al azar
        aciertos = 0
        validos = 0
        for _ in range(N_NULL):
            j0 = int(rng.integers(0, max(1, len(ds) - dias - 1)))
            j1 = j0 + dias
            if j1 >= len(ds):
                continue
            base = px[ds[j0]][3]
            k = base * (1 + dist) if o["cp"] == "C" else base * (1 - dist)
            t = toca(px, ds, j0, j1, k, o["cp"])
            if t is None:
                continue
            validos += 1
            aciertos += t
        base_rate = aciertos / validos if validos else None
        res.append(dict(sym=o["sym"], fecha=o["fecha"], strike=o["strike"], cp=o["cp"],
                        entrada=entrada, exp=exp, regla=regla, dias=dias,
                        dist_pct=round(100 * dist, 2), gano=gano,
                        base_rate=base_rate, txt=o["txt"][:110]))

    json.dump({"ops": res, "saltadas": saltadas}, open(OUT, "w"), indent=1)
    g = np.array([r["gano"] for r in res], dtype=float)
    b = np.array([r["base_rate"] for r in res if r["base_rate"] is not None], dtype=float)
    print("operaciones evaluadas: %d   (saltadas %d: %s)"
          % (len(res), len(saltadas),
             ", ".join(sorted({s["motivo"].split("(")[0].strip() for s in saltadas})) or "-"))
    print("\n%-46s %s" % ("LLEGO AL STRIKE ANTES DE VENCER", "%.1f%%  (%d de %d)"
                          % (100 * g.mean(), int(g.sum()), g.size)))
    print("%-46s %.1f%%" % ("MISMO TICKER, MISMA DISTANCIA Y DIAS, FECHA AL AZAR", 100 * b.mean()))
    print("%-46s %+.1f pp" % ("EDGE", 100 * (g.mean() - b.mean())))
    # t emparejado: cada operacion contra SU propia tasa base
    dif = np.array([r["gano"] - r["base_rate"] for r in res if r["base_rate"] is not None])
    if dif.size > 2:
        t = dif.mean() / (dif.std(ddof=1) / np.sqrt(dif.size))
        print("%-46s %+.2f  (n=%d)" % ("t emparejado (cada una contra su base)", t, dif.size))
    print("\n%-32s %s" % ("distancia media al strike", "%.1f%%" % np.mean([r["dist_pct"] for r in res])))
    print("%-32s %.0f sesiones" % ("dias hasta vencimiento (mediana)",
                                   np.median([r["dias"] for r in res])))
    print("\n%-10s %-6s %9s %6s %5s %7s %8s %s"
          % ("fecha", "sym", "strike", "dist%", "dias", "gano", "base%", "regla venc."))
    for r in sorted(res, key=lambda x: x["fecha"]):
        print("%-10s %-6s %8.1f%s %+6.1f %5d %7s %7.0f%% %s"
              % (r["fecha"], r["sym"], r["strike"], r["cp"], r["dist_pct"], r["dias"],
                 "SI" if r["gano"] else "no", 100 * (r["base_rate"] or 0), r["regla"]))
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
