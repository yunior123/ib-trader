#!/usr/bin/env python3
"""gex_heatmap.py — matriz Net GEX strike x vencimiento para el widget del cockpit.

Fuente: UW /api/stock/{S}/greek-exposure/strike-expiry?expiry=X (call_gex + put_gex por strike
de ESE vencimiento) + /greek-exposure/expiry para elegir los vencimientos vivos.
Salida atomica: data/gex_heatmap_<sym>.json

FRESCURA: el JSON declara `date` (el que devuelve UW), `ts` de escritura y `age_s`. El widget
PINTA la edad. Ningun campo se rellena: strike sin dato = null, y la celda sale vacia.

Uso:
  python3 scripts/gex_heatmap.py AAPL
  python3 scripts/gex_heatmap.py --loop 45          # daemon, todos los del focus + fleet corta
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from fleet_cp_scan import f, get  # noqa: E402
from uw_premium import token  # noqa: E402

N_EXPIRIES = 5
MAX_ROWS = 15
OUTDIR = os.path.join(REPO, "data")


def atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    os.replace(tmp, path)


def build(sym, tok):
    st = get("/api/stock/%s/stock-state" % sym, tok)
    st = st[0] if isinstance(st, list) else st
    spot = f(st.get("close")) or f(st.get("last"))
    if spot is None:
        raise RuntimeError("%s sin spot" % sym)

    exps_raw = get("/api/stock/%s/greek-exposure/expiry" % sym, tok)
    today = dt.date.today().isoformat()
    exps = [r["expiry"] for r in exps_raw if r.get("expiry") and r["expiry"] >= today][:N_EXPIRIES]
    if not exps:
        raise RuntimeError("%s sin vencimientos futuros" % sym)

    grid, date_seen = {}, None
    for e in exps:
        rows = get("/api/stock/%s/greek-exposure/strike-expiry?expiry=%s" % (sym, e), tok)
        for r in rows:
            k = f(r.get("strike"))
            cg, pg = f(r.get("call_gex")), f(r.get("put_gex"))
            if k is None or cg is None or pg is None:
                continue
            date_seen = date_seen or r.get("date")
            grid.setdefault(k, {})[e] = cg + pg

    if not grid:
        raise RuntimeError("%s sin gamma por strike" % sym)

    # filas: ventana centrada en el spot, pero solo strikes CON dato en algun vencimiento
    live = [k for k, row in grid.items() if any(abs(v) > 0 for v in row.values())]
    if not live:
        raise RuntimeError("%s toda la gamma a cero" % sym)
    live.sort(key=lambda k: abs(k - spot))
    strikes = sorted(live[:MAX_ROWS], reverse=True)

    cells, mvc = [], None
    for k in strikes:
        row = []
        for e in exps:
            v = grid.get(k, {}).get(e)
            row.append(v)
            if v is not None and (mvc is None or abs(v) > abs(mvc[2])):
                mvc = (k, e, v)
        cells.append(row)

    col_tot = [sum(grid.get(k, {}).get(e) or 0.0 for k in grid) for e in exps]
    net_all = sum(col_tot)
    return {
        "sym": sym, "spot": spot, "date": date_seen,
        "ts": int(time.time()), "wall": dt.datetime.now().strftime("%H:%M:%S"),
        "expiries": exps, "strikes": strikes, "cells": cells,
        "mvc": {"strike": mvc[0], "expiry": mvc[1], "net_gex": mvc[2]} if mvc else None,
        "col_totals": col_tot, "net_total": net_all,
        "src": "UW greek-exposure/strike-expiry",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--loop", type=int, default=0, help="segundos entre pasadas (0 = una vez)")
    a = ap.parse_args()

    tok = token()
    syms = [s.upper() for s in a.syms] or _focus()
    while True:
        for s in syms:
            path = os.path.join(OUTDIR, "gex_heatmap_%s.json" % s.lower())
            try:
                atomic(path, build(s, tok))
                print("[gex_heatmap] %s ok" % s, flush=True)
            except Exception as e:
                print("[gex_heatmap] %s FALLO: %s" % (s, str(e)[:140]), file=sys.stderr, flush=True)
        if not a.loop:
            return
        if not a.syms:
            syms = _focus()
        time.sleep(a.loop)


def _focus():
    """Simbolo del chart si existe, si no el primero de la flota. Sin fallback inventado."""
    p = os.path.join(OUTDIR, "focus_ticker.txt")
    if os.path.exists(p):
        s = open(p).read().split()
        if s:
            return [s[0].upper()]
    return [open(os.path.join(OUTDIR, "fleet.txt")).read().split()[0]]


if __name__ == "__main__":
    main()
