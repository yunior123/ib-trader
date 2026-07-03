#!/usr/bin/env python3
"""footprint_verify.py — verificacion final de las celdas candidatas de stacked imbalance.

El barrido fija UN sorteo del null; si el resultado cambia al re-sortearlo, la celda no es
señal, es la varianza del control. Aqui cada celda se mide contra 25 nulls independientes
(sobre-muestreo x20) y se reporta la distribucion del edge, no un solo numero.

Salida: data/research/footprint_verify.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import footprint_stack_study as S                                        # noqa: E402
from footprint_core import Footprint                                     # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STUDY = os.path.join(REPO, "data", "research", "footprint_stack_study.json")
OUT = os.path.join(REPO, "data", "research", "footprint_verify.json")

N_SEEDS = 25
TOP_CLEAN = 8


def measure(panel, fp, c, seeds):
    det = S.detect(fp, c["nmin"], c["inc_tick"], c["ratio"], c["min_vol"])
    idx, d, _ = S.entries(det, panel, c["K"], c["mode"])
    if c["barrier"] == "atr":
        tp_s, sl_s = c["tp"] * panel.atr[idx], c["sl"] * panel.atr[idx]
    else:
        tp_s, sl_s = np.full(idx.size, c["tp"]), np.full(idx.size, c["sl"])
    lab, _, mfe, mae = S.triple_barrier(panel, idx, d, tp_s, sl_s, c["H"])
    k = lab >= 0
    w = (lab[k] == 1).astype(float)
    clu = panel.block[idx[k]]
    edges, nulls, ps = [], [], []
    for sd in seeds:
        nidx, nd = S.null_matched(panel, idx, d, seed=sd)
        if c["barrier"] == "atr":
            tp_n, sl_n = c["tp"] * panel.atr[nidx], c["sl"] * panel.atr[nidx]
        else:
            tp_n, sl_n = np.full(nidx.size, c["tp"]), np.full(nidx.size, c["sl"])
        nlab, _, _, _ = S.triple_barrier(panel, nidx, nd, tp_n, sl_n, c["H"])
        nk = nlab >= 0
        wn = (nlab[nk] == 1).astype(float)
        nclu = panel.block[nidx[nk]]
        bs = S.cluster_boot(w, clu, wn, nclu, fp.n_blocks, seed=sd + 7)
        edges.append(float(w.mean() - wn.mean()))
        nulls.append(float(wn.mean()))
        ps.append(bs["p"] if bs else 1.0)
    e = np.array(edges)
    ncl = int(np.unique(clu).size)
    neff = S.effective_n(int(k.sum()), ncl)
    lo, hi = S.wilson(float(w.mean()), max(1.0, neff))
    atrm = float(np.nanmean(panel.atr[idx[k]]))
    rr = c["tp"] / c["sl"]
    return dict(
        cfg={q: c[q] for q in ("nmin", "inc_tick", "ratio", "min_vol", "K", "mode",
                               "barrier", "tp", "sl", "H")},
        n=int(k.sum()), clusters=ncl, n_eff=round(neff, 1),
        wr=round(float(w.mean()), 4), wr_wilson_neff=[round(lo, 4), round(hi, 4)],
        null_wr_medio=round(float(np.mean(nulls)), 4),
        null_wr_sd=round(float(np.std(nulls, ddof=1)), 4),
        edge_medio=round(float(e.mean()), 4), edge_sd=round(float(e.std(ddof=1)), 4),
        edge_min=round(float(e.min()), 4), edge_max=round(float(e.max()), 4),
        pct_sorteos_edge_positivo=round(100.0 * float((e > 0).mean()), 1),
        p_cluster_mediana=float("%.4g" % float(np.median(ps))),
        p_cluster_max=float("%.4g" % float(np.max(ps))),
        rr=rr,
        expectancia_stop=round(float(w.mean()) * rr - (1 - float(w.mean())), 4),
        expectancia_stop_wilsonLB=round(lo * rr - (1 - lo), 4),
        mfe_atr_p60=round(float(np.percentile(mfe[k], 60)) / atrm, 3),
        mae_atr_p75=round(float(np.percentile(mae[k], 75)) / atrm, 3))


def main():
    fp = Footprint()
    panel = S.Panel(fp)
    st = json.load(open(STUDY))
    cells = st["cells"]
    clean = [c for c in cells if c["barrier"] == "atr"]
    clean.sort(key=lambda c: c["p_cluster"])
    cand = clean[:TOP_CLEAN]
    prim = st["primary_result"]
    if prim is not None:
        cand = [prim] + cand
    seeds = list(range(1000, 1000 + N_SEEDS))
    old_mult = S.NULL_MULT
    S.NULL_MULT = 20
    out = []
    for c in cand:
        r = measure(panel, fp, c, seeds)
        out.append(r)
        print("%-70s n=%5d wr=%.4f null=%.4f+-%.4f edge=%+.4f+-%.4f [%+.4f,%+.4f] "
              "pos=%.0f%% p_med=%.3f"
              % (json.dumps(r["cfg"]), r["n"], r["wr"], r["null_wr_medio"], r["null_wr_sd"],
                 r["edge_medio"], r["edge_sd"], r["edge_min"], r["edge_max"],
                 r["pct_sorteos_edge_positivo"], r["p_cluster_mediana"]))
    S.NULL_MULT = old_mult
    res = dict(n_seeds=N_SEEDS, null_mult=20,
               nota=("celda 0 = pre-registrada (receta Sierra Chart); el resto = las de menor "
                     "p entre las de etiqueta LIMPIA (barrera ATR, doble toque <1%)"),
               celdas=out)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    print("-> %s" % OUT)


if __name__ == "__main__":
    main()
