#!/usr/bin/env python3
"""trace_cube.py — eje de tiempo REAL para el panel TRACE del terminal mit.

Recorre las fotos de cadena de un dia (data/history/<fecha>/opt_chain_<sym>_HHMM.txt, una
cada 5 min que deja opt_chain_cache) con el lector oficial chain_cube_archive.day_snapshots
y calcula, por (strike, epoch), GEX y Net OI. Escribe data/trace_cube_<sym>.json.

REGLAS (ley anti-cero-plausible de ~/CLAUDE.md):
  - GEX solo con griegas MEDIDAS. Foto sin ninguna gamma -> columna VACIA en gex (no ceros,
    no reconstruccion con IV plana). El % de filas con gamma se publica por columna.
  - Foto sin spot -> se descarta entera (no se puede firmar el GEX sin spot).
  - oi < 0 (sentinela de TWS) -> fila fuera; nunca cuenta como 0.
  - Cero fotos utilizables -> levanta ValueError. Jamas una matriz de ceros.

Signo de la casa (igual que mit/backend/app/analytics/options_positioning.py): call +, put -.

Uso:
  ./venv/bin/python scripts/trace_cube.py SPY                 # hoy
  ./venv/bin/python scripts/trace_cube.py SPY 2026-07-31
  ./venv/bin/python scripts/trace_cube.py SPY 2026-07-31 --stdout   # no escribe nada
"""
import argparse
import contextlib
import importlib.util
import json
import os
import statistics
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_archive():
    path = os.path.join(REPO, "scripts", "chain_cube_archive.py")
    spec = importlib.util.spec_from_file_location("ibt_chain_cube_archive", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ARCHIVE = _load_archive()

CONTRACT_MULTIPLIER = 100
DEFAULT_BAND = 0.12  # misma banda que MATRIX_BAND del terminal mit
METRICS = ("gex", "netoi")


@contextlib.contextmanager
def _hist(hist_dir):
    """Apunta el lector oficial a otro data/history (tests)."""
    if hist_dir is None:
        yield
        return
    prev = ARCHIVE.HIST
    ARCHIVE.HIST = str(hist_dir)
    try:
        yield
    finally:
        ARCHIVE.HIST = prev


def _skey(strike):
    return "%g" % strike


def build_cube(sym, date, band=DEFAULT_BAND, hist_dir=None):
    """Cubo (strike x epoch) de un dia. Levanta ValueError si no hay fotos utilizables."""
    sym = sym.upper()
    read = skipped = 0
    cols = []  # (epoch, spot, {strike: {"gex": v|None, "netoi": v|None}}, greeks_pct, n_rows)
    with _hist(hist_dir):
        for snap in ARCHIVE.day_snapshots(date, sym):
            read += 1
            meta = snap.meta
            epoch, spot = meta.get("ts"), meta.get("spot")
            if not epoch or spot is None or spot <= 0 or not snap.rows:
                skipped += 1
                continue
            cols.append((int(epoch), float(spot), snap.rows))
    if not cols:
        raise ValueError(
            "%s %s: cero fotos utilizables en %s (leidas %d, descartadas %d)"
            % (sym, date, hist_dir or ARCHIVE.HIST, read, skipped)
        )

    cols.sort(key=lambda c: c[0])
    by_epoch = {c[0]: c for c in cols}  # epoch duplicado: gana la ultima foto
    cols = [by_epoch[e] for e in sorted(by_epoch)]

    lo, hi = 0.0, float("inf")
    spots = [c[1] for c in cols]
    if band and band > 0:
        mid = statistics.median(spots)
        lo, hi = mid * (1 - band), mid * (1 + band)

    epochs, labels, col_spots, greeks_pct = [], [], [], []
    cells = {m: {} for m in METRICS}
    strikes = set()
    for epoch, spot, rows in cols:
        in_band = [r for r in rows if lo <= r.strike <= hi]
        if not in_band:
            skipped += 1
            continue
        gex_col, oi_col = {}, {}
        n_gamma = 0
        for r in in_band:
            sign = 1 if r.right == "C" else -1
            if r.oi is None or r.oi < 0:
                continue
            if r.gamma is not None:
                n_gamma += 1
                gex_col[r.strike] = gex_col.get(r.strike, 0.0) + (
                    sign * r.gamma * r.oi * CONTRACT_MULTIPLIER * spot * spot * 0.01
                )
            oi_col[r.strike] = oi_col.get(r.strike, 0.0) + sign * r.oi
        epochs.append(epoch)
        labels.append(time.strftime("%H:%M", time.localtime(epoch)))
        col_spots.append(round(spot, 4))
        greeks_pct.append(round(n_gamma / len(in_band), 4))
        for strike, value in gex_col.items():  # vacio si la foto no traia gamma: columna VACIA
            cells["gex"]["%s|%d" % (_skey(strike), epoch)] = value
            strikes.add(strike)
        for strike, value in oi_col.items():
            cells["netoi"]["%s|%d" % (_skey(strike), epoch)] = value
            strikes.add(strike)

    if not epochs:
        raise ValueError("%s %s: ninguna foto dejo filas dentro de la banda %.2f" % (sym, date, band))

    return {
        "meta": dict(_meta(sym, date, band, epochs, labels, col_spots, greeks_pct, strikes,
                           read, skipped), intraday_variation=_variation(cells)),
        "cells": cells,
    }


def _variation(cells):
    """Fraccion MEDIDA de strikes cuyo valor cambia a lo largo del dia, por metrica.
    (El OI de IBKR es T+1: no se mueve intradia. Se publica, no se supone.)"""
    out = {}
    for metric, grid in cells.items():
        per_strike = {}
        for key, value in grid.items():
            per_strike.setdefault(key.rsplit("|", 1)[0], []).append(round(value, 6))
        multi = [v for v in per_strike.values() if len(v) >= 2]
        out[metric] = round(sum(1 for v in multi if len(set(v)) > 1) / len(multi), 4) if multi else None
    return out


def _meta(sym, date, band, epochs, labels, col_spots, greeks_pct, strikes, read, skipped):
    return {
        "sym": sym,
        "date": date,
        "generated_epoch": int(time.time()),
        "source": "ibkr_tws chain snapshots (data/history/<date>/opt_chain_<sym>_HHMM.txt)",
        "band": band,
        "epochs": epochs,
        "labels": labels,
        "spots": col_spots,
        "greeks_ok_pct": greeks_pct,
        "strikes": sorted(strikes, reverse=True),
        "columns": len(epochs),
        "columns_with_gex": sum(1 for p in greeks_pct if p > 0),
        "snapshots_read": read,
        "snapshots_skipped": skipped,
    }


def cube_path(sym, data_dir=None):
    return os.path.join(data_dir or os.path.join(REPO, "data"), "trace_cube_%s.json" % sym.lower())


def write_cube(cube, data_dir=None):
    """Escritura atomica (tmp + os.replace): el terminal lo lee en vivo."""
    path = cube_path(cube["meta"]["sym"], data_dir)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(cube, f, separators=(",", ":"), sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def main():
    ap = argparse.ArgumentParser(description="Cubo strike x tiempo desde las fotos de cadena")
    ap.add_argument("sym")
    ap.add_argument("date", nargs="?", default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--band", type=float, default=DEFAULT_BAND)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--stdout", action="store_true", help="imprime el JSON y no escribe nada")
    a = ap.parse_args()
    cube = build_cube(a.sym, a.date, band=a.band)
    if a.stdout:
        json.dump(cube, sys.stdout, indent=1, sort_keys=True)
        sys.stdout.write("\n")
        return
    path = write_cube(cube, a.data_dir)
    m = cube["meta"]
    print("%s %s -> %s | %d columnas (%s..%s), %d strikes, %d con GEX medido, celdas gex=%d netoi=%d"
          % (m["sym"], m["date"], path, m["columns"], m["labels"][0], m["labels"][-1],
             len(m["strikes"]), m["columns_with_gex"],
             len(cube["cells"]["gex"]), len(cube["cells"]["netoi"])))


if __name__ == "__main__":
    main()
