#!/usr/bin/env python3
"""premarket_calibrate.py — LOTE FUERA DE SESION. Mide empiricamente la relacion
premarket no consolidado -> apertura, a partir de lo archivado por
scripts/premarket_unconsolidated.py. No dispara nada: SEÑAL-SOLAMENTE.

Features (una observacion = sym x fecha):
  SIGNED_VOL  volumen firmado Lee-Ready del premarket / volumen premarket MEDIANO del
              propio simbolo (sin mediana > 0 la observacion se descarta, no se fabrica)
  IMBALANCE   imbalance_ratio FIRMADO (side B=+, A=-) del ultimo mensaje antes de 09:29 ET
  GAP         (ultimo precio premarket - cierre anterior) / cierre anterior
Etiqueta: el signo de (open -> open+30min) coincide con el signo de la feature.
Buckets q1..q5 por quintiles del PROPIO simbolo sobre el historico disponible.

Wilson 95% sobre muestra EFECTIVA (Kish con rho MEDIDO entre simbolos; si no se puede
medir, n_eff = numero de FECHAS distintas). `medido: true` solo con n_eff >= 30.

Uso: ./venv/bin/python scripts/premarket_calibrate.py
"""
import argparse
import glob
import json
import math
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from backtest_alertas_flota import wilson  # noqa: E402  fuente unica de Wilson en el repo

HISTDIR = os.path.join(REPO, "data", "history")
OUT_PATH = os.path.join(REPO, "data", "premarket_calib.json")
FEATURES = ("SIGNED_VOL", "IMBALANCE", "GAP")
N_BUCKETS = 5
MIN_NEFF = 30
IMB_CUTOFF_MIN = 9 * 60 + 29     # ultimo mensaje ANTES de 09:29 ET
MIN_DATES_FOR_RHO = 5


def atomic_write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_docs(histdir):
    docs = []
    for path in sorted(glob.glob(os.path.join(histdir, "*", "premkt_unconsolidated_*.json"))):
        try:
            with open(path) as fh:
                docs.append(json.load(fh))
        except (OSError, ValueError) as exc:
            print("AVISO: %s ilegible (%s) -> excluido" % (path, exc), file=sys.stderr)
    return docs


# ------------------------------------------------------------------- features

def _hhmm_to_min(s):
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (AttributeError, ValueError):
        return None


def imbalance_signed(doc):
    """Ratio FIRMADO del ultimo mensaje antes de 09:29 ET. None si no lo hay."""
    best = None
    for p in doc.get("imbalance") or []:
        mod = _hhmm_to_min(p.get("hhmm"))
        if mod is None or mod >= IMB_CUTOFF_MIN:
            continue
        if p.get("imbalance_ratio") is None:
            continue
        if best is None or mod >= _hhmm_to_min(best["hhmm"]):
            best = p
    if best is None:
        return None
    side = (best.get("side") or "").upper()
    if side.startswith("B"):
        return float(best["imbalance_ratio"])
    if side.startswith("A") or side.startswith("S"):
        return -float(best["imbalance_ratio"])
    return None                     # lado desconocido: no se firma a ojo


def observation(doc, median_vol):
    """doc -> dict con las features y la etiqueta. Valores ausentes = None, jamas 0."""
    total = doc.get("tape_total") or {}
    res = doc.get("resultado") or {}
    op, px30 = res.get("open"), res.get("px_30m")
    ret_bps = None
    if op not in (None, 0) and px30 is not None:
        ret_bps = (px30 - op) / op * 1e4

    signed_vol = None
    if median_vol and total.get("signed_vol") is not None:
        signed_vol = total["signed_vol"] / float(median_vol)

    gap = None
    prev_close, last_px = res.get("prev_close"), total.get("last_px")
    if prev_close not in (None, 0) and last_px is not None:
        gap = (last_px - prev_close) / prev_close

    return {
        "sym": doc.get("meta", {}).get("sym"),
        "fecha": doc.get("meta", {}).get("fecha"),
        "ret_bps": ret_bps,
        "SIGNED_VOL": signed_vol,
        "IMBALANCE": imbalance_signed(doc),
        "GAP": gap,
    }


def build_observations(docs):
    by_sym_vol = {}
    for d in docs:
        sym = d.get("meta", {}).get("sym")
        vol = (d.get("tape_total") or {}).get("vol")
        if sym and vol:
            by_sym_vol.setdefault(sym, []).append(vol)
    median_vol = {}
    for sym, vols in by_sym_vol.items():
        vols = sorted(vols)
        n = len(vols)
        median_vol[sym] = vols[n // 2] if n % 2 else (vols[n // 2 - 1] + vols[n // 2]) / 2.0
    return [observation(d, median_vol.get(d.get("meta", {}).get("sym"))) for d in docs]


# ------------------------------------------------------------------ estadistica

def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in xs))
    sy = math.sqrt(sum((v - my) ** 2 for v in ys))
    if sx <= 0 or sy <= 0:
        return None
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (sx * sy)


def measure_rho(obs):
    """Correlacion media por pares de los retornos open->+30 entre simbolos. None si
    no hay suficientes fechas comunes (entonces NO se inventa: el consumidor usa fechas)."""
    grid = {}
    for o in obs:
        if o["ret_bps"] is None:
            continue
        grid.setdefault(o["sym"], {})[o["fecha"]] = o["ret_bps"]
    syms = sorted(grid)
    corrs = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = grid[syms[i]], grid[syms[j]]
            common = sorted(set(a) & set(b))
            if len(common) < MIN_DATES_FOR_RHO:
                continue
            c = _pearson([a[k] for k in common], [b[k] for k in common])
            if c is not None:
                corrs.append(c)
    if not corrs:
        return None
    return sum(corrs) / len(corrs)


def n_effective(n, n_dates, rho):
    """Kish: n/(1+(k-1)rho) con k = simbolos por fecha. Sin rho medido, una FECHA es
    una observacion (lo mas conservador que se puede decir sin inventar)."""
    if n <= 0 or n_dates <= 0:
        return 0.0
    if rho is None:
        return float(n_dates)
    k = n / float(n_dates)
    r = min(1.0, max(0.0, rho))
    return n / (1.0 + (k - 1.0) * r)


def quintile_buckets(values):
    """values ordenados por rango -> q1..q5 (reparto por rango, robusto con n pequeño)."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    out = [None] * n
    for pos, idx in enumerate(order):
        q = int(pos * N_BUCKETS / n) + 1
        out[idx] = "q%d" % min(N_BUCKETS, q)
    return out


# ------------------------------------------------------------------ calibracion

def calibrate(docs):
    obs = build_observations(docs)
    fechas = sorted({o["fecha"] for o in obs if o["fecha"]})
    syms = sorted({o["sym"] for o in obs if o["sym"]})
    rho = measure_rho(obs)
    datasets = sorted({d.get("meta", {}).get("dataset") for d in docs
                       if d.get("meta", {}).get("dataset")})

    buckets = {}
    n_empates = 0
    for feat in FEATURES:
        # bucket por quintiles del PROPIO simbolo
        rows = []
        by_sym = {}
        for o in obs:
            if o[feat] is None or o["ret_bps"] is None:
                continue
            by_sym.setdefault(o["sym"], []).append(o)
        for sym, lst in by_sym.items():
            qs = quintile_buckets([o[feat] for o in lst])
            for o, q in zip(lst, qs):
                rows.append((q, o))

        agg = {}
        for q, o in rows:
            fsign = 1 if o[feat] > 0 else (-1 if o[feat] < 0 else 0)
            if fsign == 0:
                continue            # la feature no afirma direccion: fuera del denominador
            msign = 1 if o["ret_bps"] > 0 else (-1 if o["ret_bps"] < 0 else 0)
            if msign == 0:
                n_empates += 1
                continue            # movimiento exactamente 0: empate, se declara y no se cuenta
            a = agg.setdefault(q, {"n": 0, "wins": 0, "bps": [], "fechas": set()})
            a["n"] += 1
            a["wins"] += 1 if fsign == msign else 0
            a["bps"].append(fsign * o["ret_bps"])
            a["fechas"].add(o["fecha"])

        for q in sorted(agg):
            a = agg[q]
            n, wins = a["n"], a["wins"]
            neff = n_effective(n, len(a["fechas"]), rho)
            wr = wins / float(n)
            _p, lo, _hi = wilson(int(round(wr * neff)), int(round(neff)))
            buckets["%s|%s" % (feat, q)] = {
                "n": n,
                "n_eff": int(round(neff)),
                "wr": round(wr, 4),
                "lo": round(lo, 4) if lo is not None else None,
                "mean_bps": round(sum(a["bps"]) / len(a["bps"]), 2),
                "medido": neff >= MIN_NEFF,
            }

    metodo = ("obs = sym x fecha; buckets q1..q5 por rango dentro del PROPIO simbolo; "
              "exito = signo(feature) == signo(open->open+30m) del MISMO dataset; "
              "n_eff Kish con rho=%s medido entre simbolos sobre >=%d fechas comunes "
              "(sin rho medible, n_eff = nº de FECHAS distintas: los sym-dias de la flota "
              "estan correlacionados y no son independientes); Wilson 95%% sobre n_eff; "
              "medido solo con n_eff>=%d; %d observaciones con movimiento exactamente 0 "
              "excluidas por empate."
              % ("%.3f" % rho if rho is not None else "NO MEDIBLE",
                 MIN_DATES_FOR_RHO, MIN_NEFF, n_empates))

    return {
        "_meta": {
            "ts": int(time.time()),
            "n_dias": len(fechas),
            "n_simbolos": len(syms),
            "fuente": "databento %s" % (" ".join(datasets) if datasets else "sin datos"),
            "clase_dato": "unconsolidated_direct",
            "metodo": metodo,
        },
        "buckets": buckets,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="calibra premarket no consolidado -> apertura")
    ap.add_argument("--hist-dir", default=HISTDIR)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args(argv)

    docs = load_docs(args.hist_dir)
    out = calibrate(docs)
    atomic_write(args.out, json.dumps(out, indent=1) + "\n")

    med = sum(1 for b in out["buckets"].values() if b["medido"])
    print("%s: n_dias=%d n_simbolos=%d buckets=%d (medido=%d, doctrina=%d)"
          % (args.out, out["_meta"]["n_dias"], out["_meta"]["n_simbolos"],
             len(out["buckets"]), med, len(out["buckets"]) - med))
    return 0


if __name__ == "__main__":
    sys.exit(main())
