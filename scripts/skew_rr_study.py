#!/usr/bin/env python3
"""skew_rr_study.py — ¿el SKEW EXTREMO predice? La hipotesis de @astocks92, medida.

Su metrica: risk reversal 25 delta, percentilado contra su propia historia
("$QCOM: 85th Percentile CALL SKEW 25 Delta"). Su lectura, deducida de su operacion del
2026-08-04 (AAPL con el put mas caro -> compro CALLS): **compra el lado BARATO**, o sea
FADEA el skew.

Aqui se mide esa hipotesis con la vara de la casa: triple barrera con timeout=NULL sobre el
camino 1m real, null de entrada aleatoria emparejado por sym y por dia, n_eff topada por
clusters, Wilson-LB de la expectancia y BH-FDR q=0,10.

SERIE DE MADUREZ CONSTANTE: para cada dia se toma el vencimiento con DTE mas cercano a
`--dte` (30 por defecto). Mezclar vencimientos sin normalizar la madurez seria comparar
peras con manzanas: el RR se aplana con el DTE.

PERCENTIL SIN MIRAR EL FUTURO: expandiendo, solo con los dias ANTERIORES del propio simbolo.

Entrada: data/research/rr25_<sym>.json (skew_rr_fetch.py) + poly_bars 1m
Salida:  data/research/skew_rr_study.json
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import sqlite3
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from delta_imbalance_study import wilson, effective_n, bh_fdr, two_prop_p, block_bootstrap_edge  # noqa: E402

OUT = "data/research/skew_rr_study.json"
DB = "data/trades.db"
ATR_N = 14
MIN_HIST = 60          # dias propios antes de poder percentilar (percentil de n<60 es ruido)
K_TP = (1.0, 1.5)
K_SL = (1.0,)
HORIZONS = (1, 3, 5)   # dias de mercado
COLAS = (10, 20)       # decil / quintil extremo


def cargar_rr(sym, dte_objetivo):
    """{fecha -> rr} de madurez constante: el vencimiento con DTE mas cercano al objetivo."""
    p = "data/research/rr25_%s.json" % sym.lower()
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        acc = json.load(f)
    mejor = {}
    for exp, rows in acc.items():
        try:
            e = dt.date.fromisoformat(exp)
        except ValueError:
            continue
        for r in rows:
            try:
                d = dt.date.fromisoformat(r["date"])
            except (ValueError, KeyError, TypeError):
                continue
            dte = (e - d).days
            if dte < 5 or dte > 120:          # ni 0DTE ni LEAPS: fuera de la madurez util
                continue
            dist = abs(dte - dte_objetivo)
            if r["date"] not in mejor or dist < mejor[r["date"]][0]:
                mejor[r["date"]] = (dist, float(r["rr"]), dte)
    return {k: (v[1], v[2]) for k, v in mejor.items()}


def barras_dia(con, sym):
    """{fecha -> (idx_inicio, idx_fin)} sobre arrays 1m ordenados, + los arrays."""
    q = con.execute("select ts,o,h,l,c from poly_bars where sym=? order by ts", (sym,)).fetchall()
    if not q:
        return None
    ts = np.array([r[0] // 1000 for r in q], dtype=np.int64)
    o = np.array([r[1] for r in q]); h = np.array([r[2] for r in q])
    l = np.array([r[3] for r in q]); c = np.array([r[4] for r in q])
    dias = np.array([dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d") for t in ts])
    idx = {}
    ini = 0
    for i in range(1, len(dias) + 1):
        if i == len(dias) or dias[i] != dias[ini]:
            idx[dias[ini]] = (ini, i)
            ini = i
    return dict(ts=ts, o=o, h=h, l=l, c=c, dias=dias, idx=idx)


def atr_diario(B, fechas, n=ATR_N):
    """ATR de Wilder sobre barras DIARIAS construidas de las 1m. {fecha -> atr}."""
    ds = sorted(B["idx"])
    hi = np.array([B["h"][B["idx"][d][0]:B["idx"][d][1]].max() for d in ds])
    lo = np.array([B["l"][B["idx"][d][0]:B["idx"][d][1]].min() for d in ds])
    cl = np.array([B["c"][B["idx"][d][1] - 1] for d in ds])
    tr = np.empty(len(ds))
    tr[0] = hi[0] - lo[0]
    for i in range(1, len(ds)):
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
    a = np.full(len(ds), np.nan)
    if len(ds) > n:
        a[n - 1] = tr[:n].mean()
        for i in range(n, len(ds)):
            a[i] = (a[i - 1] * (n - 1) + tr[i]) / n
    return {d: a[i] for i, d in enumerate(ds)}, ds


def triple_barrera(B, ds, d0, direccion, atr, k_tp, k_sl, H):
    """Entrada al ABRIR el dia siguiente a la señal (el RR es de cierre: cero look-ahead).
    Camino 1m real de H dias de mercado. 1 = TP, 0 = SL, None = timeout."""
    try:
        i0 = ds.index(d0)
    except ValueError:
        return None, None, None
    if i0 + 1 >= len(ds):
        return None, None, None
    dent = ds[i0 + 1]
    a, b = B["idx"][dent]
    entrada = B["o"][a]
    if not (atr > 0):
        return None, None, None
    tp = entrada + direccion * k_tp * atr
    sl = entrada - direccion * k_sl * atr
    fin = ds[min(i0 + H, len(ds) - 1)]
    j_fin = B["idx"][fin][1]
    hs, ls = B["h"][a:j_fin], B["l"][a:j_fin]
    if direccion > 0:
        htp = np.nonzero(hs >= tp)[0]
        hsl = np.nonzero(ls <= sl)[0]
    else:
        htp = np.nonzero(ls <= tp)[0]
        hsl = np.nonzero(hs >= sl)[0]
    t_tp = htp[0] if htp.size else None
    t_sl = hsl[0] if hsl.size else None
    mfe = (np.max(hs - entrada) if direccion > 0 else np.max(entrada - ls)) / atr
    if t_tp is None and t_sl is None:
        return None, mfe, entrada
    if t_sl is None:
        return 1, mfe, entrada
    if t_tp is None:
        return 0, mfe, entrada
    return (1 if t_tp < t_sl else 0), mfe, entrada


def segment_stats(rows, k_tp, k_sl):
    """Stats for paired ``(date, signal_label, random_label)`` observations."""
    n = len(rows)
    if not n:
        return {"n": 0, "clusters": 0, "n_eff": 0.0, "wr": None,
                "wr_lo": None, "null_wr": None, "edge": None, "exp_lo": None}
    wins = sum(row[1] for row in rows)
    random_wins = sum(row[2] for row in rows)
    clusters = len({row[0] for row in rows})
    n_eff = effective_n(n, clusters)
    wr, lo, _ = wilson(wins, max(1.0, n_eff), p=wins / n)
    null_wr = random_wins / n
    return {"n": n, "clusters": clusters, "n_eff": round(n_eff, 1),
            "wr": wr, "wr_lo": lo, "null_wr": null_wr,
            "edge": wr - null_wr, "exp_lo": lo * k_tp - (1 - lo) * k_sl}


def main():
    ap = argparse.ArgumentParser(description="¿el skew extremo predice? (hipotesis Architect)")
    ap.add_argument("--dte", type=int, default=30)
    ap.add_argument("--top", type=int, default=24)
    a = ap.parse_args()

    syms = sorted(os.path.basename(p)[len("rr25_"):-5].upper()
                  for p in glob.glob("data/research/rr25_*.json"))
    # The 3.8GB archive is cold/immutable during research.  SQLite otherwise tries to
    # create sidecars and fails with SQLITE_CANTOPEN on this macOS volume.
    con = sqlite3.connect("file:%s?mode=ro&immutable=1" % os.path.abspath(DB), uri=True)
    entradas = []           # (sym, fecha, rr, pct, atr, B, ds)
    cache = {}
    for sym in syms:
        rr = cargar_rr(sym, a.dte)
        if len(rr) < MIN_HIST + 20:
            continue
        B = barras_dia(con, sym)
        if B is None:
            continue
        atrs, ds = atr_diario(B, sorted(rr))
        cache[sym] = (B, ds)
        fechas = sorted(set(rr) & set(ds))
        serie = []
        for d in fechas:
            v = rr[d][0]
            if len(serie) >= MIN_HIST:                  # percentil EXPANDIENDO, sin futuro
                pct = 100.0 * sum(1 for x in serie if x <= v) / len(serie)
                atr = atrs.get(d, float("nan"))
                if atr == atr:
                    entradas.append((sym, d, v, pct, atr))
            serie.append(v)
    print("simbolos con serie usable: %d | observaciones con percentil: %d"
          % (len(cache), len(entradas)))
    if not entradas:
        sys.exit("sin muestra: baja mas historia con skew_rr_fetch.py")

    celdas = []
    for cola in COLAS:
        for modo in ("fade", "sigue"):
            for k_tp in K_TP:
                for k_sl in K_SL:
                    for H in HORIZONS:
                        lab, clusters, rnd, paired = [], set(), [], []
                        rng = np.random.default_rng(7)
                        for (sym, d, v, pct, atr) in entradas:
                            B, ds = cache[sym]
                            if pct <= cola:
                                # RR en la cola BAJA = puts caros / calls baratas
                                dir_fade, dir_sigue = +1, -1
                            elif pct >= 100 - cola:
                                dir_fade, dir_sigue = -1, +1
                            else:
                                continue
                            direccion = dir_fade if modo == "fade" else dir_sigue
                            r, _, _ = triple_barrera(B, ds, d, direccion, atr, k_tp, k_sl, H)
                            if r is None:
                                continue
                            lab.append(r)
                            # cluster por FECHA, no por (sym,fecha): 30 nombres correlacionados
                            # el mismo dia son ~1 observacion, no 30 (rho medido 0,412)
                            clusters.add(d)
                            rr_, _, _ = triple_barrera(B, ds, d,
                                                       int(rng.choice([-1, 1])), atr, k_tp, k_sl, H)
                            if rr_ is not None:
                                rnd.append(rr_)
                                paired.append((d, r, rr_))
                        n, rn = len(lab), len(rnd)
                        if n < 100 or rn < 100:
                            continue
                        wins, rwins = sum(lab), sum(rnd)
                        n_eff = effective_n(n, len(clusters))
                        pw, lo, hi = wilson(wins, max(1.0, n_eff), p=wins / n)
                        ex = lambda q: q * k_tp - (1 - q) * k_sl
                        boot = block_bootstrap_edge(np.array(lab, float), np.array(rnd, float))
                        dates = sorted({row[0] for row in paired})
                        cut = max(1, int(len(dates) * 0.60))
                        train_dates = set(dates[:cut])
                        train = segment_stats([row for row in paired if row[0] in train_dates],
                                              k_tp, k_sl)
                        oos = segment_stats([row for row in paired if row[0] not in train_dates],
                                            k_tp, k_sl)
                        celdas.append(dict(cola=cola, modo=modo, k_tp=k_tp, k_sl=k_sl, H=H,
                                           n=n, wins=wins, wr=pw, wr_lo=lo, clusters=len(clusters),
                                           n_eff=round(n_eff, 1), exp_lo=ex(lo), exp=ex(pw),
                                           null_wr=rwins / rn, null_n=rn,
                                           edge=boot["edge"], edge_lo=boot["lo"], edge_hi=boot["hi"],
                                           p=two_prop_p(wins, n, rwins, rn),
                                           split_date=(dates[cut] if cut < len(dates) else None),
                                           train=train, oos=oos))
    if not celdas:
        sys.exit("ninguna celda alcanzo el minimo de muestra")
    keep = bh_fdr([c["p"] for c in celdas], q=0.10)
    for c, k in zip(celdas, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = ("DEAD" if c["edge_hi"] <= 0 else
                          "DATA-INSUFFICIENT" if c["n_eff"] < 50 else
                          "PROVEN" if (k and c["exp_lo"] > 0 and c["edge_lo"] > 0) else "UNPROVEN")
    candidates = [c for c in celdas if c["train"]["n"] >= 100 and c["oos"]["n"] >= 50]
    tuned = max(candidates, key=lambda c: (c["train"]["exp_lo"], c["train"]["edge"])) \
        if candidates else None
    if tuned:
        oos = tuned["oos"]
        tuned_summary = {
            "selection": "max train Wilson-LB expectancy; chronological 60/40 dates",
            "params": {k: tuned[k] for k in ("cola", "modo", "k_tp", "k_sl", "H")},
            "split_date": tuned["split_date"], "train": tuned["train"], "oos": oos,
            "verdict": ("OOS_POSITIVE_CANDIDATE" if oos["n_eff"] >= 50
                         and oos["exp_lo"] > 0 and oos["edge"] > 0 else "REJECTED_OOS"),
        }
    else:
        tuned_summary = {"verdict": "DATA_INSUFFICIENT_FOR_60_40_TUNING"}
    celdas.sort(key=lambda c: -c["edge_lo"])
    with open(OUT + ".tmp", "w") as f:
        json.dump({"dte": a.dte, "n_cells": len(celdas), "fdr_pass": int(keep.sum()),
                   "obs": len(entradas), "tuned_60_40": tuned_summary,
                   "cells": celdas}, f, indent=1)
    os.replace(OUT + ".tmp", OUT)

    print("\n%-5s %-5s %4s %4s %2s | %5s %6s %5s | %6s %6s | %8s %8s %7s | %s"
          % ("cola", "modo", "ktp", "ksl", "H", "n", "n_eff", "clu", "wr", "null",
             "edge", "edge_lo", "p", "veredicto"))
    for c in celdas[:a.top]:
        print("%-5d %-5s %4.1f %4.1f %2d | %5d %6.0f %5d | %6.3f %6.3f | %+8.4f %+8.4f %7.4f | %s"
              % (c["cola"], c["modo"], c["k_tp"], c["k_sl"], c["H"], c["n"], c["n_eff"],
                 c["clusters"], c["wr"], c["null_wr"], c["edge"], c["edge_lo"], c["p"],
                 c["veredicto"]))
    print("\nTUNED 60/40: %s" % json.dumps(tuned_summary, ensure_ascii=False))
    print("\nceldas=%d  pasan BH-FDR=%d -> %s" % (len(celdas), int(keep.sum()), OUT))


if __name__ == "__main__":
    main()
