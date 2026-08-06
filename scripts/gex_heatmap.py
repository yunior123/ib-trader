#!/usr/bin/env python3
"""gex_heatmap.py — matriz Net GEX strike x vencimiento para el widget del cockpit.

Fuentes en CASCADA (el JSON declara `src` con la que de verdad se uso):
  uw          UW /greek-exposure/strike-expiry (call_gex+put_gex crudos = gamma x OI x 100)
  polygon     /v3/snapshot/options/{SYM} completo via poly_client (misma escala cruda)
  chain_local data/opt_chain_<sym>.txt (~4 vencimientos -> partial:true; edad >900s -> stale:true)
Si TODO falla: el fichero anterior queda intacto y se grita a stderr. Jamas un cero plausible.

Horizonte: todos los vencimientos con expiry <= hoy+100 dias (cap 24 columnas).
Salida atomica: data/gex_heatmap_<sym>.json. El widget PINTA edad y src; celda sin dato = null.

Uso:
  python3 scripts/gex_heatmap.py AAPL
  python3 scripts/gex_heatmap.py --loop 45          # daemon; cada pasada suma el focus_ticker
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

HORIZON_DAYS = 110  # 3 meses + margen: 100d dejaba fuera el monthly del 3er mes (NOK 11-20 a 106d)
MAX_EXPIRIES = 24
MAX_ROWS = 17
STALE_S = 900
OUTDIR = os.path.join(REPO, "data")


def atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    os.replace(tmp, path)


def _horizon():
    today = dt.date.today().isoformat()
    return today, (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()


def _matrix(sym, spot, grid, exps, date_seen, src):
    """grid: {strike:{exp_iso:net}}. Solo strikes con dato vivo, ventana centrada en spot."""
    live = [k for k, row in grid.items() if any(row.get(e) is not None and abs(row[e]) > 0 for e in exps)]
    if not live:
        raise RuntimeError("%s toda la gamma a cero (%s)" % (sym, src))
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
    return {
        "sym": sym, "spot": spot, "date": date_seen,
        "ts": int(time.time()), "wall": dt.datetime.now().strftime("%H:%M:%S"),
        "expiries": exps, "strikes": strikes, "cells": cells,
        "mvc": {"strike": mvc[0], "expiry": mvc[1], "net_gex": mvc[2]} if mvc else None,
        "col_totals": col_tot, "net_total": sum(col_tot),
        "src": src,
    }


def build_uw(sym, tok):
    st = get("/api/stock/%s/stock-state" % sym, tok)
    st = st[0] if isinstance(st, list) else st
    spot = f(st.get("close")) or f(st.get("last"))
    if spot is None:
        raise RuntimeError("%s sin spot" % sym)

    exps_raw = get("/api/stock/%s/greek-exposure/expiry" % sym, tok)
    today, lim = _horizon()
    exps = sorted({r["expiry"] for r in exps_raw
                   if r.get("expiry") and today <= r["expiry"] <= lim})[:MAX_EXPIRIES]
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
    return _matrix(sym, spot, grid, exps, date_seen, "uw")


def _chain_header(sym):
    """(epoch, spot, path) de la cabecera de opt_chain_<sym>.txt, o levanta."""
    p = os.path.join(OUTDIR, "opt_chain_%s.txt" % sym.lower())
    if not os.path.exists(p):
        raise RuntimeError("sin %s" % p)
    head = open(p).readline()
    epoch, spot = None, None
    for part in head.lstrip("# ").split("|"):
        t = part.split()
        if len(t) >= 2 and t[0] == "epoch":
            epoch = int(t[1])
        elif len(t) >= 2 and t[0] == "spot":
            spot = f(t[1])
    if epoch is None or spot is None:
        raise RuntimeError("cabecera de %s sin epoch/spot" % p)
    return epoch, spot, p


def build_polygon(sym):
    from poly_client import Polygon
    cli = Polygon(verbose=False)
    today, lim = _horizon()
    grid, spot, kept = {}, None, 0
    url = "https://api.polygon.io/v3/snapshot/options/%s?limit=250" % sym
    for page in cli.paginate(url):
        for c in page.get("results") or []:
            det = c.get("details") or {}
            if spot is None:
                spot = f((c.get("underlying_asset") or {}).get("price"))
            k = f(det.get("strike_price"))
            e = det.get("expiration_date")
            typ = det.get("contract_type")
            g = f((c.get("greeks") or {}).get("gamma"))
            oi = f(c.get("open_interest"))
            if k is None or not e or typ not in ("call", "put") or g is None or oi is None:
                continue
            if not (today <= e <= lim):
                continue
            row = grid.setdefault(k, {})
            row[e] = (row.get(e) or 0.0) + (1.0 if typ == "call" else -1.0) * g * oi * 100.0
            kept += 1
    if not grid:
        raise RuntimeError("%s polygon sin contratos con gamma+OI" % sym)
    if spot is None:
        spot = _chain_header(sym)[1]  # levanta si tampoco hay cadena -> cae a chain_local
    exps = sorted({e for row in grid.values() for e in row})[:MAX_EXPIRIES]
    return _matrix(sym, spot, grid, exps, today, "polygon")


def build_chain_local(sym):
    epoch, spot, p = _chain_header(sym)
    today, lim = _horizon()
    grid = {}
    for ln in open(p):
        if ln.startswith("#") or not ln.strip():
            continue
        t = ln.split()
        if len(t) < 10 or t[1] not in ("C", "P"):
            continue
        k, oi, g = f(t[0]), f(t[6]), f(t[9])
        if k is None or oi is None or g is None or g < 0:
            continue
        e = "%s-%s-%s" % (t[2][:4], t[2][4:6], t[2][6:8])
        if not (today <= e <= lim):
            continue
        row = grid.setdefault(k, {})
        row[e] = (row.get(e) or 0.0) + (1.0 if t[1] == "C" else -1.0) * g * oi * 100.0
    if not grid:
        raise RuntimeError("%s cadena local sin filas con gamma+OI" % sym)
    exps = sorted({e for row in grid.values() for e in row})[:MAX_EXPIRIES]
    d = _matrix(sym, spot, grid, exps, dt.date.fromtimestamp(epoch).isoformat(), "chain_local")
    d["partial"] = True
    d["note"] = "cadena local: solo %d vencimientos" % len(exps)
    d["chain_epoch"] = epoch
    d["chain_age_s"] = int(time.time() - epoch)
    if d["chain_age_s"] > STALE_S:
        d["stale"] = True
    return d


def build(sym, tok):
    errs = []
    if tok:
        try:
            return build_uw(sym, tok)
        except Exception as e:
            errs.append("uw: %s" % str(e)[:90])
    else:
        errs.append("uw: sin token")
    try:
        return build_polygon(sym)
    except Exception as e:
        errs.append("polygon: %s" % str(e)[:90])
    try:
        return build_chain_local(sym)
    except Exception as e:
        errs.append("chain_local: %s" % str(e)[:90])
    raise RuntimeError(" | ".join(errs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--loop", type=int, default=0, help="segundos entre pasadas (0 = una vez)")
    a = ap.parse_args()

    try:
        from uw_premium import token
        tok = token()
    except Exception as e:
        tok = None
        print("[gex_heatmap] sin token UW (%s) -> cascada polygon/cadena" % str(e)[:80],
              file=sys.stderr, flush=True)

    base = [s.upper() for s in a.syms]
    while True:
        syms = list(base) or _focus()
        if a.loop:
            fs = _focus_sym()
            if fs and fs not in syms:
                syms.append(fs)
        for s in syms:
            path = os.path.join(OUTDIR, "gex_heatmap_%s.json" % s.lower())
            try:
                d = build(s, tok)
                atomic(path, d)
                print("[gex_heatmap] %s ok src=%s exps=%d" % (s, d["src"], len(d["expiries"])),
                      flush=True)
            except Exception as e:
                # fichero anterior INTACTO: mejor viejo declarado que vacio fingido
                print("[gex_heatmap] %s FALLO: %s" % (s, str(e)[:300]), file=sys.stderr, flush=True)
        if not a.loop:
            return
        time.sleep(a.loop)


def _focus_sym():
    p = os.path.join(OUTDIR, "focus_ticker.txt")
    if os.path.exists(p):
        s = open(p).read().split()
        if s:
            return s[0].upper()
    return None


def _focus():
    """Simbolo del chart si existe, si no el primero de la flota. Sin fallback inventado."""
    fs = _focus_sym()
    if fs:
        return [fs]
    return [open(os.path.join(OUTDIR, "fleet.txt")).read().split()[0]]


if __name__ == "__main__":
    main()
