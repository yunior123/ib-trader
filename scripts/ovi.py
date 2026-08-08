#!/usr/bin/env python3
"""ovi.py — OPTION VOLUME IMBALANCE (OVI): construccion y prueba MEDIDA.

Fuente conceptual: "Option Volume Imbalance as a predictor for equity market returns"
(arXiv 2201.09319). Lo que el paper afirma y que aqui se prueba con nuestros datos:
  - el desequilibrio NORMALIZADO entre volumen de opciones de vision alcista y bajista
    predice el retorno DIRECCIONAL del subyacente,
  - el horizonte con señal es el **OVERNIGHT** (cierre -> apertura siguiente),
  - las opciones de IV alta (aqui: OTM) aportan mas informacion,
  - el volumen de PUTS predice mejor que el de calls.

OJO — no confundirlo con el "OVI" de Guy Cohen, que es propietario, oscila -1..+1 y mezcla
volumen con cambio de OI. El que se implementa aqui es el academico, que es reproducible.

Tres variantes, todas en [-1, +1]:
  OVI_cp    = (vol_call - vol_put) / (vol_call + vol_put)                 el ingenuo
  OVI_vista = (alcista - bajista) / (alcista + bajista)                   el del paper:
              alcista = calls compradas (ask) + puts vendidas (bid)
              bajista = puts compradas (ask) + calls vendidas (bid)
  OVI_otm   = igual que OVI_cp pero SOLO volumen fuera del dinero (proxy de IV alta)

Datos: data/history/<dia>/uw_flow_per_strike_<sym>.json (acumulado de la sesion, por strike)
       + poly_bars 1m para el retorno overnight e intradia.
LOTE FUERA DE SESION. Salida: data/research/ovi.json
"""
import argparse
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
from delta_imbalance_study import wilson, block_bootstrap_edge, two_prop_p  # noqa: E402

OUT = "data/research/ovi.json"
MIN_VOL = 5000          # sin volumen el cociente no significa nada (mismo espiritu que VMIN)


def _i(r, k):
    v = r.get(k)
    return int(v) if v is not None else 0


def ovi_del_dia(path):
    """Las tres variantes para un (sym, dia), o None si el fichero no sirve."""
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
    alc, baj = ca + pb, pa + cb
    norm = lambda a, b: (a - b) / (a + b) if (a + b) > 0 else None
    return {"vol": cv + pv, "ovi_cp": norm(cv, pv), "ovi_vista": norm(alc, baj),
            "ovi_otm": norm(cotm, potm),
            "put_share": pv / (cv + pv) if (cv + pv) else None}


def barras(con, sym):
    q = con.execute("select ts,o,h,l,c from poly_bars where sym=? order by ts", (sym,)).fetchall()
    if not q:
        return None
    d = {}
    for t, o, h, l, c in q:
        k = dt.datetime.utcfromtimestamp(t // 1000).strftime("%Y-%m-%d")
        if k not in d:
            d[k] = [o, h, l, c]
        d[k][1] = max(d[k][1], h); d[k][2] = min(d[k][2], l); d[k][3] = c
    return d


def construye():
    con = sqlite3.connect("file:data/trades.db?mode=ro", uri=True)
    px = {}
    obs = []
    for path in sorted(glob.glob("data/history/*/uw_flow_per_strike_*.json")):
        dia = os.path.basename(os.path.dirname(path))
        sym = os.path.basename(path)[len("uw_flow_per_strike_"):-len(".json")].upper()
        o = ovi_del_dia(path)
        if o is None:
            continue
        if sym not in px:
            px[sym] = barras(con, sym) or {}
        b = px[sym]
        ds = sorted(b)
        if dia not in b:
            continue
        i = ds.index(dia)
        if i + 1 >= len(ds):
            continue
        nd = ds[i + 1]
        cierre = b[dia][3]
        ap, _, _, ci = b[nd]
        obs.append(dict(sym=sym, dia=dia, **o,
                        overnight=100 * (ap / cierre - 1),          # cierre -> apertura
                        intradia=100 * (ci / ap - 1),               # apertura -> cierre
                        total=100 * (ci / cierre - 1)))
    return obs


def evalua(obs, campo, retorno, cola=20):
    """Cola alta -> largo, cola baja -> corto. Devuelve la celda medida."""
    v = np.array([o[campo] for o in obs if o.get(campo) is not None])
    r = np.array([o[retorno] for o in obs if o.get(campo) is not None])
    dias = np.array([o["dia"] for o in obs if o.get(campo) is not None])
    if v.size < 200:
        return None
    lo, hi = np.percentile(v, cola), np.percentile(v, 100 - cola)
    sig = np.where(v >= hi, 1, np.where(v <= lo, -1, 0))
    m = sig != 0
    pnl = sig[m] * r[m]
    # t con n de DIAS (30 nombres del mismo dia no son 30 observaciones)
    ud = np.unique(dias[m])
    md = np.array([pnl[dias[m] == d].mean() for d in ud])
    t = md.mean() / (md.std(ddof=1) / np.sqrt(len(md))) if len(md) > 2 else 0.0
    base = r[~m]
    return dict(campo=campo, retorno=retorno, n=int(m.sum()), dias=int(len(ud)),
                wr=float(np.mean(pnl > 0)), media=float(pnl.mean()), t=float(t),
                base_wr=float(np.mean(base > 0)) if base.size else None,
                base_media=float(base.mean()) if base.size else None)


def main():
    ap = argparse.ArgumentParser(description="Option Volume Imbalance: construir y probar")
    ap.add_argument("--cola", type=int, default=20)
    a = ap.parse_args()
    obs = construye()
    if not obs:
        sys.exit("ovi ROTO: sin observaciones (¿falta el archivo uw_flow_per_strike?)")
    syms = {o["sym"] for o in obs}
    dias = {o["dia"] for o in obs}
    print("OVI: %d observaciones · %d simbolos · %d dias (%s..%s)"
          % (len(obs), len(syms), len(dias), min(dias), max(dias)))
    for c in ("ovi_cp", "ovi_vista", "ovi_otm"):
        v = [o[c] for o in obs if o.get(c) is not None]
        print("   %-10s media %+.3f  p10 %+.3f  p90 %+.3f" % (c, np.mean(v),
                                                              np.percentile(v, 10), np.percentile(v, 90)))
    cells = []
    print("\n%-10s %-10s %6s %5s %8s %9s %8s | %9s %9s"
          % ("variante", "retorno", "n", "dias", "win rate", "media%", "t", "base wr", "base %"))
    for c in ("ovi_cp", "ovi_vista", "ovi_otm"):
        for ret in ("overnight", "intradia", "total"):
            e = evalua(obs, c, ret, a.cola)
            if not e:
                continue
            cells.append(e)
            print("%-10s %-10s %6d %5d %7.1f%% %+9.4f %+8.2f | %8.1f%% %+9.4f"
                  % (c, ret, e["n"], e["dias"], 100 * e["wr"], e["media"], e["t"],
                     100 * e["base_wr"], e["base_media"]))
    json.dump({"obs": obs, "cells": cells}, open(OUT, "w"))
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
