#!/usr/bin/env python3
"""zerolag_backtest.py — mide el Zero Lag Trend Signals (MTF) [AlgoAlpha] antes de enchufarlo.

Port fiel del Pine v5 que pego Yunior:
    lag        = floor((length-1)/2)
    zlema      = EMA(src + (src - src[lag]), length)
    volatility = highest(ATR(length), length*3) * mult
    trend      = +1 al cruzar close por encima de zlema+volatility
                 -1 al cruzar close por debajo de zlema-volatility   (persistente)
    ENTRADA alcista: close cruza zlema POR ENCIMA con trend==1 y trend[1]==1
    ENTRADA bajista: close cruza zlema POR DEBAJO con trend==-1 y trend[1]==-1

Se miden las DOS señales del indicador por separado (el cambio de tendencia y la entrada
fina), con la vara de la casa: triple barrera timeout=NULL, null de entrada aleatoria
emparejada por sym y hora, n_eff topada por clusters (sym,dia), BH-FDR.

LOTE FUERA DE SESION. Salida: data/research/zerolag_backtest.json
"""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from delta_imbalance_study import (Panel, atr_wilder, triple_barrier, matched_random,  # noqa: E402
                                   wilson, effective_n, bh_fdr, two_prop_p,
                                   block_bootstrap_edge, MIN_CLUSTERS)

OUT = "data/research/zerolag_backtest.json"
LENGTH = 70
MULT = 1.2
K_TP = (1.0, 1.5)
K_SL = (1.0,)
HORIZONS = (30, 60, 120)


def ema(x, n, reset):
    """EMA de Pine, reiniciada en cada bloque (sym,dia): no cruza sesiones."""
    a = 2.0 / (n + 1.0)
    out = np.full(x.size, np.nan)
    prev = np.nan
    for i in range(x.size):
        if reset[i] or np.isnan(prev):
            prev = x[i]
        else:
            prev = a * x[i] + (1 - a) * prev
        out[i] = prev
    return out


def rolling_max(x, w, block_id):
    out = np.full(x.size, np.nan)
    idx = np.arange(x.size)
    starts = np.nonzero(np.concatenate(([True], block_id[1:] != block_id[:-1])))[0]
    pos = idx - np.repeat(starts, np.diff(np.append(starts, x.size)))
    ok = pos >= (w - 1)
    if ok.any():
        win = np.lib.stride_tricks.sliding_window_view(x, w)
        out[ok] = win.max(axis=1)[idx[ok] - (w - 1)]
    return out


def zerolag(p, length=LENGTH, mult=MULT):
    """Devuelve (zlema, banda, trend, entrada_alcista, entrada_bajista)."""
    c = p.c
    lag = (length - 1) // 2
    src2 = c.copy()
    idx = np.arange(c.size)
    ok = idx - lag >= 0
    mismo = np.zeros(c.size, dtype=bool)
    mismo[ok] = p.block_id[idx[ok] - lag] == p.block_id[idx[ok]]
    src2[mismo] = c[mismo] + (c[mismo] - c[idx[mismo] - lag])
    z = ema(src2, length, p.new_block)
    atr = atr_wilder(p, n=length)
    vol = rolling_max(np.nan_to_num(atr, nan=0.0), length * 3, p.block_id) * mult
    up, dn = z + vol, z - vol
    prev_c = np.concatenate(([np.nan], c[:-1]))
    prev_c[p.new_block] = np.nan
    cross_up = (c > up) & (prev_c <= np.concatenate(([np.nan], up[:-1])))
    cross_dn = (c < dn) & (prev_c >= np.concatenate(([np.nan], dn[:-1])))
    trend = np.zeros(c.size, dtype=np.int8)
    cur = 0
    for i in range(c.size):
        if p.new_block[i]:
            cur = 0
        if cross_up[i]:
            cur = 1
        elif cross_dn[i]:
            cur = -1
        trend[i] = cur
    prev_t = np.concatenate(([0], trend[:-1]))
    xz_up = (c > z) & (prev_c <= np.concatenate(([np.nan], z[:-1])))
    xz_dn = (c < z) & (prev_c >= np.concatenate(([np.nan], z[:-1])))
    ent_alc = xz_up & (trend == 1) & (prev_t == 1)
    ent_baj = xz_dn & (trend == -1) & (prev_t == -1)
    giro_alc = (trend == 1) & (prev_t != 1)
    giro_baj = (trend == -1) & (prev_t != -1)
    return z, vol, trend, ent_alc, ent_baj, giro_alc, giro_baj, atr


def main():
    ap = argparse.ArgumentParser(description="backtest del Zero Lag Trend Signals")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    p = Panel()
    print("panel %d minutos · %d syms · %d dias" % (p.sym.size, len(p.symbols), len(p.days)))
    z, vol, trend, ea, eb, ga, gb, atr = zerolag(p)
    hora = (p.minute_et >= 585) & (p.minute_et < 940)
    base = np.isfinite(atr) & (atr > 0) & np.isfinite(z) & hora
    señales = {
        "ENTRADA (flecha pequeña)": (base & (ea | eb), np.where(ea, 1, -1)),
        "GIRO DE TENDENCIA (flecha grande)": (base & (ga | gb), np.where(ga, 1, -1)),
        "ENTRADA solo alcista": (base & ea, np.ones(p.c.size, dtype=np.int8)),
        "ENTRADA solo bajista": (base & eb, -np.ones(p.c.size, dtype=np.int8)),
    }
    celdas = []
    for nom, (mask, dirs) in señales.items():
        idx = np.nonzero(mask)[0]
        print("  %-36s %6d disparos" % (nom, idx.size))
        if idx.size < 200:
            continue
        d = dirs[idx].astype(np.int8)
        ridx, rdir = matched_random(p, idx, seed=abs(hash(nom)) % 2**31, atr=atr)
        for k_tp in K_TP:
            for k_sl in K_SL:
                for H in HORIZONS:
                    lab, _ = triple_barrier(p, idx, d, atr, k_tp, k_sl, H)
                    rlab, _ = triple_barrier(p, ridx, rdir, atr, k_tp, k_sl, H)
                    keep, rkeep = lab >= 0, rlab >= 0
                    n, rn = int(keep.sum()), int(rkeep.sum())
                    if n < 100 or rn < 100:
                        continue
                    w, rw = int((lab[keep] == 1).sum()), int((rlab[rkeep] == 1).sum())
                    clu = int(np.unique(p.block_id[idx[keep]]).size)
                    ne = effective_n(n, clu)
                    pw, lo, hi = wilson(w, max(1.0, ne), p=w / n)
                    ex = lambda q: q * k_tp - (1 - q) * k_sl
                    b = block_bootstrap_edge((lab[keep] == 1).astype(float),
                                             (rlab[rkeep] == 1).astype(float))
                    celdas.append(dict(señal=nom, k_tp=k_tp, k_sl=k_sl, H=H, n=n, wins=w,
                                       wr=pw, wr_lo=lo, clusters=clu, n_eff=round(ne, 1),
                                       exp_lo=ex(lo), null_wr=rw / rn,
                                       edge=b["edge"], edge_lo=b["lo"], edge_hi=b["hi"],
                                       p=two_prop_p(w, n, rw, rn)))
    if not celdas:
        sys.exit("sin celdas con muestra suficiente")
    keep = bh_fdr([c["p"] for c in celdas], q=0.10)
    for c, k in zip(celdas, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = ("DEAD" if c["edge_hi"] <= 0 else
                          "DATA-INSUFFICIENT" if c["clusters"] < MIN_CLUSTERS or c["n_eff"] < 50 else
                          "PROVEN" if (k and c["exp_lo"] > 0 and c["edge_lo"] > 0) else "UNPROVEN")
    celdas.sort(key=lambda c: -c["edge_lo"])
    json.dump({"n_cells": len(celdas), "fdr_pass": int(keep.sum()), "cells": celdas},
              open(OUT, "w"), indent=1)
    print("\n%-36s %4s %4s %4s | %6s %6s %5s | %6s %6s | %8s %8s | %s"
          % ("señal", "ktp", "ksl", "H", "n", "n_eff", "clu", "wr", "null", "edge", "edge_lo", "veredicto"))
    for c in celdas[:a.top]:
        print("%-36s %4.1f %4.1f %4d | %6d %6.0f %5d | %6.3f %6.3f | %+8.4f %+8.4f | %s"
              % (c["señal"], c["k_tp"], c["k_sl"], c["H"], c["n"], c["n_eff"], c["clusters"],
                 c["wr"], c["null_wr"], c["edge"], c["edge_lo"], c["veredicto"]))
    print("\nceldas=%d  pasan BH-FDR=%d -> %s" % (len(celdas), int(keep.sum()), OUT))


if __name__ == "__main__":
    main()
