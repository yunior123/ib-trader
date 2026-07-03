#!/usr/bin/env python3
"""delta_imbalance_prep.py — junta el archivo UW de delta por minuto con las barras 1m
y escribe data/research/delta_imbalance.npz. LOTE FUERA DE SESION (CLAUDE.md).

Fuentes MEDIDAS, cero relleno:
  data/history/<dia>/uw_greek_flow_<sym>.json  -> dir_delta_flow, total_delta_flow,
      otm_dir_delta_flow, volume, transactions (una fila por MINUTO, no acumulado)
  data/trades.db poly_bars                     -> o/h/l/c/v 1m del mismo minuto UTC

Un minuto sin barra o sin fila UW NO se rellena: se descarta y se cuenta en el informe.
"""
import datetime as dt
import glob
import json
import os
import sqlite3
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
OUT = "data/research/delta_imbalance.npz"
DB = "data/trades.db"

FIELDS = ("dir_delta_flow", "total_delta_flow", "otm_dir_delta_flow",
          "otm_total_delta_flow", "dir_vega_flow", "total_vega_flow")


def iso_to_epoch(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_uw(path):
    """{epoch_min -> (campos..., volume, transactions)} o None si el fichero no sirve."""
    try:
        with open(path) as f:
            d = json.load(f)
        rows = d["rows"]
    except (OSError, ValueError, KeyError):
        return None
    if not rows:
        return None
    out = {}
    for r in rows:
        try:
            t = int(iso_to_epoch(r["timestamp"]))
            vals = [float(r[k]) for k in FIELDS]
            vals.append(float(r["volume"]))
            vals.append(float(r["transactions"]))
        except (KeyError, TypeError, ValueError):
            continue          # fila malformada se SALTA; jamas se rellena con 0
        out[t - t % 60] = vals
    return out or None


def load_bars(con, sym, day):
    """{epoch_min -> (o,h,l,c,v)} de poly_bars para ese dia UTC."""
    t0 = int(dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
    q = con.execute("select ts,o,h,l,c,v from poly_bars where sym=? and ts>=? and ts<?",
                    (sym, t0 * 1000, (t0 + 86400) * 1000))
    return {int(ts // 1000): (o, h, l, c, v) for ts, o, h, l, c, v in q}


def main():
    con = sqlite3.connect(DB)
    files = sorted(glob.glob("data/history/*/uw_greek_flow_*.json"))
    if not files:
        sys.exit("delta_imbalance_prep ROTO: no hay data/history/*/uw_greek_flow_*.json")

    cols = {k: [] for k in ("sym", "day", "ts", "o", "h", "l", "c", "v", "uw_vol", "uw_tx")}
    for k in FIELDS:
        cols[k] = []
    syms, days = [], []
    rep = {"ficheros": len(files), "sin_uw": 0, "sin_barras": 0, "minutos": 0,
           "minutos_descartados_sin_barra": 0}

    bars_cache = {}
    for path in files:
        day = os.path.basename(os.path.dirname(path))
        sym = os.path.basename(path)[len("uw_greek_flow_"):-len(".json")].upper()
        uw = load_uw(path)
        if uw is None:
            rep["sin_uw"] += 1
            continue
        key = (sym, day)
        if key not in bars_cache:
            if len(bars_cache) > 4:
                bars_cache.clear()
            bars_cache[key] = load_bars(con, sym, day)
        bars = bars_cache[key]
        if not bars:
            rep["sin_barras"] += 1
            continue
        si = syms.index(sym) if sym in syms else (syms.append(sym) or len(syms) - 1)
        di = days.index(day) if day in days else (days.append(day) or len(days) - 1)
        for t, vals in sorted(uw.items()):
            b = bars.get(t)
            if b is None:
                rep["minutos_descartados_sin_barra"] += 1
                continue
            cols["sym"].append(si)
            cols["day"].append(di)
            cols["ts"].append(t)
            for name, val in zip(FIELDS, vals[:len(FIELDS)]):
                cols[name].append(val)
            cols["uw_vol"].append(vals[len(FIELDS)])
            cols["uw_tx"].append(vals[len(FIELDS) + 1])
            for name, val in zip(("o", "h", "l", "c", "v"), b):
                cols[name].append(val)
            rep["minutos"] += 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    arrays = {k: np.asarray(v, dtype=np.int64 if k in ("sym", "day", "ts") else np.float64)
              for k, v in cols.items()}
    np.savez_compressed(OUT, symbols=np.asarray(syms), days=np.asarray(days), **arrays)
    print(json.dumps(rep, indent=1))
    print("syms=%d dias=%d minutos=%d -> %s" % (len(syms), len(days), rep["minutos"], OUT))


if __name__ == "__main__":
    main()
