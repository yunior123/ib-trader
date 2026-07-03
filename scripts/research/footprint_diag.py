#!/usr/bin/env python3
"""footprint_diag.py — diagnostico del estudio de stacked imbalance.

Tres preguntas que deciden si lo que sobrevive al BH-FDR es señal o artefacto:
  1) DOBLE TOQUE: ¿las barras con apilamiento tocan TP y SL en la MISMA barra mas a menudo
     que las barras aleatorias? (con brackets de ticks fijos la regla conservadora las
     puntua a TODAS como perdida -> las dos direcciones pierden y parece "edge").
  2) VOLATILIDAD: rango 1m / ATR de la barra de señal vs la barra aleatoria.
  3) ESTABILIDAD de la mejor celda limpia (barrera ATR): por simbolo y por mitad temporal.

Salida: data/research/footprint_diag.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from footprint_core import Footprint                                   # noqa: E402
from footprint_stack_study import (Panel, detect, entries, null_matched,   # noqa: E402
                                   triple_barrier, cluster_boot, wilson,
                                   effective_n)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "data", "research", "footprint_diag.json")

# celda con el p mas bajo entre las de etiqueta LIMPIA (barrera ATR)
BEST = dict(nmin=1, inc_tick=False, ratio=2.0, min_vol=0, K=5, mode="sigue",
            k_tp=1.0, k_sl=0.75, H=30)
# celda pre-registrada (receta de vendor Sierra Chart)
PRIM = dict(nmin=1, inc_tick=True, ratio=4.0, min_vol=50, K=3, mode="sigue",
            k_tp=1.0, k_sl=0.75, H=30)


def dbl_touch_rate(panel, idx, direction, tp_abs, sl_abs, H):
    """Fraccion de entradas cuya PRIMERA barra resuelta toca TP y SL a la vez."""
    _, amb, _, _ = triple_barrier(panel, idx, direction, tp_abs, sl_abs, H)
    return float(amb.mean())


def wr_block(panel, idx, d, tp, sl, H):
    lab, _, mfe, mae = triple_barrier(panel, idx, d, tp, sl, H)
    k = lab >= 0
    return (lab[k] == 1).astype(float), panel.block[idx[k]], int(k.sum()), mfe[k], mae[k]


def main():
    fp = Footprint()
    panel = Panel(fp)
    res = {}

    # ---------------- 1 + 2: artefacto del doble toque -----------------------
    det = detect(fp, 1, True, 4.0, 50)
    idx, d, _ = entries(det, panel, 3, "sigue")
    nidx, nd = null_matched(panel, idx, d, seed=1234)
    rng = np.arange(panel.c.size)
    rows = []
    for tp_c, sl_c in ((0.10, 0.10), (0.20, 0.20), (0.30, 0.15)):
        a = dbl_touch_rate(panel, idx, d, np.full(idx.size, tp_c),
                           np.full(idx.size, sl_c), 30)
        b = dbl_touch_rate(panel, nidx, nd, np.full(nidx.size, tp_c),
                           np.full(nidx.size, sl_c), 30)
        rows.append(dict(bracket="ticks %.2f/%.2f" % (tp_c, sl_c),
                         doble_toque_señal=round(100 * a, 2),
                         doble_toque_aleatorio=round(100 * b, 2),
                         exceso_pp=round(100 * (a - b), 2)))
    for kt, ks in ((1.0, 1.0), (1.0, 0.75)):
        a = dbl_touch_rate(panel, idx, d, kt * panel.atr[idx], ks * panel.atr[idx], 30)
        b = dbl_touch_rate(panel, nidx, nd, kt * panel.atr[nidx], ks * panel.atr[nidx], 30)
        rows.append(dict(bracket="ATR %.2f/%.2f" % (kt, ks),
                         doble_toque_señal=round(100 * a, 2),
                         doble_toque_aleatorio=round(100 * b, 2),
                         exceso_pp=round(100 * (a - b), 2)))
    res["doble_toque"] = rows

    rng_sig = (panel.h[idx] - panel.l[idx]) / panel.atr[idx]
    rng_nul = (panel.h[nidx] - panel.l[nidx]) / panel.atr[nidx]
    res["volatilidad_barra_señal"] = dict(
        rango_sobre_atr_señal=round(float(np.nanmean(rng_sig)), 4),
        rango_sobre_atr_aleatorio=round(float(np.nanmean(rng_nul)), 4),
        ratio=round(float(np.nanmean(rng_sig) / np.nanmean(rng_nul)), 4),
        n_señal=int(idx.size), n_aleatorio=int(nidx.size))

    # ---------------- 3: estabilidad de las celdas limpias -------------------
    for name, cfg in (("mejor_limpia", BEST), ("pre_registrada", PRIM)):
        det = detect(fp, cfg["nmin"], cfg["inc_tick"], cfg["ratio"], cfg["min_vol"])
        idx, d, _ = entries(det, panel, cfg["K"], cfg["mode"])
        nidx, nd = null_matched(panel, idx, d, seed=99)
        H = cfg["H"]
        w, clu, n, mfe, mae = wr_block(panel, idx, d, cfg["k_tp"] * panel.atr[idx],
                                       cfg["k_sl"] * panel.atr[idx], H)
        wn, nclu, nn, _, _ = wr_block(panel, nidx, nd, cfg["k_tp"] * panel.atr[nidx],
                                      cfg["k_sl"] * panel.atr[nidx], H)
        bs = cluster_boot(w, clu, wn, nclu, fp.n_blocks, seed=5)
        ncl = int(np.unique(clu).size)
        neff = effective_n(n, ncl)
        lo, hi = wilson(float(w.mean()), max(1.0, neff))
        out = dict(cfg=cfg, n=n, wr=round(float(w.mean()), 4), null_wr=round(float(wn.mean()), 4),
                   edge=round(float(w.mean() - wn.mean()), 4),
                   edge_ci=[round(bs["lo"], 4), round(bs["hi"], 4)],
                   p_cluster=float("%.4g" % bs["p"]), clusters=ncl, n_eff=round(neff, 1),
                   wr_wilson_neff=[round(lo, 4), round(hi, 4)],
                   mfe_atr_p60=round(float(np.percentile(mfe, 60)) /
                                     float(np.nanmean(panel.atr[idx])), 3),
                   mae_atr_p75=round(float(np.percentile(mae, 75)) /
                                     float(np.nanmean(panel.atr[idx])), 3))
        # cortes: por simbolo y por mitad temporal
        sym_of = fp.block_sym
        day_of = fp.block_day
        med = int(np.median(np.unique(day_of)))
        cuts = {}
        for cname, mask_s, mask_n in (
                ("QQQ", sym_of[clu] == 0, sym_of[nclu] == 0),
                ("SPY", sym_of[clu] == 1, sym_of[nclu] == 1),
                ("dias_1a10", day_of[clu] <= med, day_of[nclu] <= med),
                ("dias_11a20", day_of[clu] > med, day_of[nclu] > med)):
            if mask_s.sum() < 100 or mask_n.sum() < 100:
                cuts[cname] = "muestra insuficiente"
                continue
            cuts[cname] = dict(n=int(mask_s.sum()), wr=round(float(w[mask_s].mean()), 4),
                               null=round(float(wn[mask_n].mean()), 4),
                               edge=round(float(w[mask_s].mean() - wn[mask_n].mean()), 4))
        out["cortes"] = cuts
        res[name] = out
        _ = rng

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    print(json.dumps(res, indent=1))
    print("-> %s" % OUT)


if __name__ == "__main__":
    main()
