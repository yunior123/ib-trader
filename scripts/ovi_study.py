#!/usr/bin/env python3
"""ovi_study.py — prueba A FONDO del Option Volume Imbalance (arXiv 2201.09319).

El primer pase (scripts/ovi.py) dejo dos cosas: el signo sale CONTRARIAN y con el test
transversal se queda en t=-1,75. Aqui se prueban las afirmaciones CONCRETAS del paper, cada
una por separado, con percentil PROPIO de cada simbolo (expandido, sin mirar el futuro),
t agrupada por DIA y BH-FDR sobre toda la rejilla:

  (1) el horizonte con señal es el OVERNIGHT (cierre -> apertura siguiente)
  (2) las PUTS predicen mejor que las calls
  (3) las opciones de IV alta (aqui: OTM) informan mas
  (4) direccion: seguir el desequilibrio (el paper) vs fadearlo (lo que salio aqui)

Variantes medidas por (sym, dia) desde uw_flow_per_strike:
  ovi_cp     (call - put) / (call + put)                       ingenuo
  ovi_vista  (alcista - bajista) / (alcista + bajista)         el del paper (por agresor)
  ovi_otm    solo volumen fuera del dinero                     proxy de IV alta
  ovi_put    (put_ask - put_bid) / (put_ask + put_bid)         SOLO puts, firmado
  ovi_call   (call_ask - call_bid) / (call_ask + call_bid)     SOLO calls, firmado

LOTE FUERA DE SESION. Salida: data/research/ovi_study.json
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import sqlite3
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from delta_imbalance_study import bh_fdr  # noqa: E402

OUT = "data/research/ovi_study.json"
MIN_VOL = 5000
MIN_HIST = 20          # dias propios antes de percentilar (el archivo son 84 sesiones)
COLAS = (20, 30)


def _i(r, k):
    v = r.get(k)
    return int(v) if v is not None else 0


def variantes(path):
    try:
        with open(path) as f:
            rows = json.load(f)["rows"]
    except (OSError, ValueError, KeyError):
        return None
    if not rows:
        return None
    cv = pv = ca = cb = pa = pb = cotm = potm = 0
    for r in rows:
        cv += _i(r, "call_volume"); pv += _i(r, "put_volume")
        ca += _i(r, "call_volume_ask_side"); cb += _i(r, "call_volume_bid_side")
        pa += _i(r, "put_volume_ask_side"); pb += _i(r, "put_volume_bid_side")
        cotm += _i(r, "call_otm_volume"); potm += _i(r, "put_otm_volume")
    if cv + pv < MIN_VOL:
        return None
    n = lambda a, b: (a - b) / (a + b) if (a + b) > 0 else None
    return {"ovi_cp": n(cv, pv), "ovi_vista": n(ca + pb, pa + cb), "ovi_otm": n(cotm, potm),
            "ovi_put": n(pa, pb), "ovi_call": n(ca, cb)}


def precios(con, sym):
    q = con.execute("select ts,o,h,l,c from poly_bars where sym=? order by ts", (sym,)).fetchall()
    if not q:
        return None
    d = {}
    for t, o, h, l, c in q:
        k = dt.datetime.utcfromtimestamp(t // 1000).strftime("%Y-%m-%d")
        if k not in d:
            d[k] = [o, h, l, c]
        d[k][3] = c
    return d


def construye():
    con = sqlite3.connect("file:data/trades.db?mode=ro", uri=True)
    bruto = collections.defaultdict(dict)
    for path in sorted(glob.glob("data/history/*/uw_flow_per_strike_*.json")):
        dia = os.path.basename(os.path.dirname(path))
        sym = os.path.basename(path)[len("uw_flow_per_strike_"):-len(".json")].upper()
        v = variantes(path)
        if v:
            bruto[sym][dia] = v
    px = {}
    obs = []
    for sym, porfecha in bruto.items():
        if sym not in px:
            px[sym] = precios(con, sym) or {}
        b = px[sym]
        ds = sorted(b)
        hist = collections.defaultdict(list)
        for dia in sorted(porfecha):
            v = porfecha[dia]
            if dia not in b:
                continue
            i = ds.index(dia)
            if i + 1 >= len(ds):
                continue
            nd = ds[i + 1]
            cierre = b[dia][3]
            ap, _, _, ci = b[nd]
            fila = {"sym": sym, "dia": dia,
                    "overnight": 100 * (ap / cierre - 1),
                    "intradia": 100 * (ci / ap - 1),
                    "total": 100 * (ci / cierre - 1)}
            usable = False
            for k, x in v.items():
                if x is None:
                    continue
                h = hist[k]
                if len(h) >= MIN_HIST:          # percentil EXPANDIDO, sin futuro
                    fila[k] = 100.0 * sum(1 for y in h if y <= x) / len(h)
                    usable = True
                h.append(x)
            if usable:
                obs.append(fila)
    return obs


def celda(obs, campo, ret, cola, modo):
    v = [(o[campo], o[ret], o["dia"]) for o in obs if campo in o]
    if len(v) < 300:
        return None
    pct = np.array([x[0] for x in v])
    r = np.array([x[1] for x in v])
    dias = np.array([x[2] for x in v])
    s = np.where(pct >= 100 - cola, 1, np.where(pct <= cola, -1, 0))
    if modo == "fade":
        s = -s
    m = s != 0
    if m.sum() < 200:
        return None
    pnl = s[m] * r[m]
    ud = np.unique(dias[m])
    md = np.array([pnl[dias[m] == d].mean() for d in ud])
    if len(md) < 20:
        return None
    t = md.mean() / (md.std(ddof=1) / np.sqrt(len(md)))
    p = 2 * (1 - 0.5 * (1 + __import__("math").erf(abs(t) / np.sqrt(2)))) if abs(t) < 40 else 0.0
    return dict(campo=campo, ret=ret, cola=cola, modo=modo, n=int(m.sum()), dias=int(len(ud)),
                wr=float(np.mean(pnl > 0)), media=float(pnl.mean()), t=float(t), p=float(p))


def main():
    ap = argparse.ArgumentParser(description="prueba a fondo del OVI")
    ap.add_argument("--top", type=int, default=16)
    a = ap.parse_args()
    obs = construye()
    if not obs:
        sys.exit("ovi_study ROTO: sin observaciones")
    print("OVI: %d observaciones · %d syms · %d dias"
          % (len(obs), len({o["sym"] for o in obs}), len({o["dia"] for o in obs})))

    celdas = []
    for campo in ("ovi_cp", "ovi_vista", "ovi_otm", "ovi_put", "ovi_call"):
        for ret in ("overnight", "intradia", "total"):
            for cola in COLAS:
                for modo in ("sigue", "fade"):
                    c = celda(obs, campo, ret, cola, modo)
                    if c:
                        celdas.append(c)
    if not celdas:
        sys.exit("sin celdas con muestra")
    keep = bh_fdr([c["p"] for c in celdas], q=0.10)
    for c, k in zip(celdas, keep):
        c["fdr_pass"] = bool(k)
    celdas.sort(key=lambda c: -c["t"])
    json.dump({"n_cells": len(celdas), "fdr_pass": int(keep.sum()), "cells": celdas},
              open(OUT, "w"), indent=1)

    print("\n%-10s %-10s %5s %-6s %6s %5s %8s %9s %7s %s"
          % ("variante", "retorno", "cola", "modo", "n", "dias", "win rate", "media%", "t", "FDR"))
    for c in celdas[:a.top]:
        print("%-10s %-10s %5d %-6s %6d %5d %7.1f%% %+9.4f %+7.2f %s"
              % (c["campo"], c["ret"], c["cola"], c["modo"], c["n"], c["dias"],
                 100 * c["wr"], c["media"], c["t"], "si" if c["fdr_pass"] else ""))
    print("\nceldas=%d  pasan BH-FDR q=0,10 = %d" % (len(celdas), int(keep.sum())))
    print("\nafirmaciones del paper:")
    for nom, campo in (("(2) puts mejor que calls", None), ("(3) OTM informa mas", None)):
        pass
    best = {}
    for c in celdas:
        best.setdefault(c["campo"], c)
        if abs(c["t"]) > abs(best[c["campo"]]["t"]):
            best[c["campo"]] = c
    for campo, c in sorted(best.items(), key=lambda kv: -abs(kv[1]["t"])):
        print("   %-10s mejor |t| = %+.2f  (%s %s cola%d, %d dias)"
              % (campo, c["t"], c["ret"], c["modo"], c["cola"], c["dias"]))
    print("-> %s" % OUT)


if __name__ == "__main__":
    main()
