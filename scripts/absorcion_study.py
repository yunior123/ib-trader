#!/usr/bin/env python3
"""absorcion_study.py — deteccion de reversion por ABSORCION, refinada y medida.

Lo que se midio antes ("ABSORCION" en delta_imbalance_patterns.py) era pobre: solo pedia
delta fuerte y que el precio no acompañara. La definicion de la calle es mas exigente y
tiene TRES piezas, no una:

  1. AGRESION PESADA      -> |z| del delta acumulado en W minutos por encima de theta
  2. INEFICIENCIA         -> el precio APENAS se movio para tanta agresion:
                             eficiencia = |Δprecio en ATR| / |z_delta|   (baja = absorcion)
  3. REPETICION EN ZONA   -> k minutos seguidos absorbiendo dentro de un rango estrecho
                             ("repeatedly holds the same area")

La direccion se opera CONTRA el delta: al lado agresor lo estan tapando.

Se prueba cada pieza por separado y acumulandolas, para ver cual aporta. Metodo de la casa:
triple barrera timeout=NULL, null emparejado por sym y hora, n_eff topada por clusters,
BH-FDR — y ADEMAS el control de deriva de [[drift-confound]]: balance largo/corto y
comparacion contra "siempre largo"/"siempre corto" en las mismas barras.

LOTE FUERA DE SESION. Salida: data/research/absorcion_study.json
"""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from delta_imbalance_study import (Panel, atr_wilder, rolling_sum_blockwise, triple_barrier,  # noqa: E402
                                   matched_random, wilson, effective_n, bh_fdr, two_prop_p,
                                   block_bootstrap_edge, MIN_CLUSTERS)
from delta_imbalance_patterns import zscore_prev_days, rolling_extreme  # noqa: E402

OUT = "data/research/absorcion_study.json"
W = 5                      # ventana de agresion (min)
THETA = (2.0, 3.0)         # |z| del delta
EFIC = (0.10, 0.20)        # |Δprecio en ATR| / |z| por debajo de esto = ineficiente
K_REP = 3                  # minutos seguidos para "repeticion"
BANDA_REP = 0.35           # rango de la zona durante la repeticion, en ATR
K_TP = (1.0, 1.5)
K_SL = (1.0,)
HORIZONS = (15, 30, 60)


def construye(p):
    atr = atr_wilder(p)
    dd = rolling_sum_blockwise(p.dir_delta_flow, p.block_id, W)
    z = zscore_prev_days(dd, p.sym, p.day)
    ov = rolling_sum_blockwise(p.uw_vol, p.block_id, W)
    zv = zscore_prev_days(ov, p.sym, p.day)
    idx = np.arange(p.c.size)
    ok = idx - W >= 0
    prev = np.full(p.c.size, np.nan)
    prev[ok] = p.c[idx[ok] - W]
    same = np.zeros(p.c.size, dtype=bool)
    same[ok] = p.block_id[idx[ok] - W] == p.block_id[idx[ok]]
    prev[~same] = np.nan
    mov = np.abs(p.c - prev) / np.where(atr > 0, atr, np.nan)     # progreso en ATR
    efic = mov / np.maximum(np.abs(z), 1e-9)                      # baja = absorcion
    return atr, z, zv, mov, efic


def repeticion(mask, p, atr, k=K_REP, banda=BANDA_REP):
    """k minutos seguidos con la mascara activa Y el precio dentro de `banda` ATR."""
    hi = rolling_extreme(p.h, p.block_id, k, "max")
    lo = rolling_extreme(p.l, p.block_id, k, "min")
    estrecho = (hi - lo) <= banda * np.where(atr > 0, atr, np.inf)
    out = mask.copy()
    idx = np.arange(mask.size)
    for j in range(1, k):
        sh = np.zeros(mask.size, dtype=bool)
        okj = idx - j >= 0
        sh[okj] = mask[idx[okj] - j]
        mismo = np.zeros(mask.size, dtype=bool)
        mismo[okj] = p.block_id[idx[okj] - j] == p.block_id[idx[okj]]
        out &= sh & mismo
    return out & estrecho


def evalua(p, atr, nombre, mask, dirs, celdas):
    idx = np.nonzero(mask)[0]
    if idx.size < 200:
        print("  %-40s %6d disparos (pocos)" % (nombre, idx.size))
        return
    d = dirs[idx].astype(np.int8)
    d[d == 0] = 1
    largos = int((d > 0).sum())
    ridx, rdir = matched_random(p, idx, seed=abs(hash(nombre)) % 2**31, atr=atr)
    print("  %-40s %6d disparos  (%.0f%% largos)" % (nombre, idx.size, 100 * largos / idx.size))
    for k_tp in K_TP:
        for k_sl in K_SL:
            for H in HORIZONS:
                lab, _ = triple_barrier(p, idx, d, atr, k_tp, k_sl, H)
                rlab, _ = triple_barrier(p, ridx, rdir, atr, k_tp, k_sl, H)
                # controles de deriva: las MISMAS barras, direccion fija
                slab, _ = triple_barrier(p, idx, np.ones(idx.size, np.int8), atr, k_tp, k_sl, H)
                clab, _ = triple_barrier(p, idx, -np.ones(idx.size, np.int8), atr, k_tp, k_sl, H)
                keep, rkeep = lab >= 0, rlab >= 0
                n, rn = int(keep.sum()), int(rkeep.sum())
                if n < 150 or rn < 150:
                    continue
                w, rw = int((lab[keep] == 1).sum()), int((rlab[rkeep] == 1).sum())
                clu = int(np.unique(p.block_id[idx[keep]]).size)
                ne = effective_n(n, clu)
                pw, lo, hi = wilson(w, max(1.0, ne), p=w / n)
                ex = lambda q: q * k_tp - (1 - q) * k_sl
                b = block_bootstrap_edge((lab[keep] == 1).astype(float),
                                         (rlab[rkeep] == 1).astype(float))
                sm, cm = slab >= 0, clab >= 0
                celdas.append(dict(
                    patron=nombre, k_tp=k_tp, k_sl=k_sl, H=H, n=n, wins=w, wr=pw, wr_lo=lo,
                    clusters=clu, n_eff=round(ne, 1), exp_lo=ex(lo), pct_largos=largos / idx.size,
                    null_wr=rw / rn, edge=b["edge"], edge_lo=b["lo"], edge_hi=b["hi"],
                    siempre_largo=float((slab[sm] == 1).mean()) if sm.sum() > 50 else None,
                    siempre_corto=float((clab[cm] == 1).mean()) if cm.sum() > 50 else None,
                    p=two_prop_p(w, n, rw, rn)))


def main():
    ap = argparse.ArgumentParser(description="absorcion refinada, medida")
    ap.add_argument("--top", type=int, default=16)
    a = ap.parse_args()
    p = Panel()
    atr, z, zv, mov, efic = construye(p)
    hora = (p.minute_et >= 585) & (p.minute_et < 940)
    base = np.isfinite(atr) & (atr > 0) & np.isfinite(z) & np.isfinite(efic) & hora
    sgn = np.sign(np.nan_to_num(z))
    contra = (-sgn).astype(np.int8)

    celdas = []
    for th in THETA:
        pesado = base & (np.abs(z) >= th)
        # 1) solo agresion pesada (lo que ya se sabia que no vale) — control interno
        evalua(p, atr, "1 AGRESION th=%.0f (contra el delta)" % th, pesado, contra, celdas)
        for ef in EFIC:
            inef = pesado & (efic <= ef)
            # 2) agresion + ineficiencia = ABSORCION propiamente dicha
            evalua(p, atr, "2 ABSORCION th=%.0f efic<=%.2f" % (th, ef), inef, contra, celdas)
            # 3) + volumen de opciones elevado
            convol = inef & np.isfinite(zv) & (zv >= 1.0)
            evalua(p, atr, "3 ABSORCION+VOL th=%.0f efic<=%.2f" % (th, ef), convol, contra, celdas)
            # 4) + repeticion en zona estrecha
            rep = repeticion(inef, p, atr)
            evalua(p, atr, "4 ABSORCION+REPETIDA th=%.0f efic<=%.2f" % (th, ef), rep, contra, celdas)
            # 5) control: la MISMA absorcion pero operando CON el delta
            evalua(p, atr, "5 CONTROL con-el-delta th=%.0f ef<=%.2f" % (th, ef), inef,
                   sgn.astype(np.int8), celdas)
    if not celdas:
        sys.exit("sin celdas")
    keep = bh_fdr([c["p"] for c in celdas], q=0.10)
    for c, k in zip(celdas, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = ("DEAD" if c["edge_hi"] <= 0 else
                          "DATA-INSUFFICIENT" if c["clusters"] < MIN_CLUSTERS or c["n_eff"] < 50 else
                          "PROVEN" if (k and c["exp_lo"] > 0 and c["edge_lo"] > 0) else "UNPROVEN")
    celdas.sort(key=lambda c: -c["edge_lo"])
    json.dump({"n_cells": len(celdas), "fdr_pass": int(keep.sum()), "cells": celdas},
              open(OUT, "w"), indent=1)
    print("\n%-40s %4s %3s | %5s %5s | %6s %6s | %8s %8s | %5s %5s | %s"
          % ("patron", "ktp", "H", "n", "clu", "wr", "null", "edge", "edge_lo",
             "sLar", "sCor", "FDR"))
    for c in celdas[:a.top]:
        print("%-40s %4.1f %3d | %5d %5d | %6.3f %6.3f | %+8.4f %+8.4f | %5.3f %5.3f | %s"
              % (c["patron"], c["k_tp"], c["H"], c["n"], c["clusters"], c["wr"], c["null_wr"],
                 c["edge"], c["edge_lo"], c["siempre_largo"] or 0, c["siempre_corto"] or 0,
                 "si" if c["fdr_pass"] else ""))
    print("\nceldas=%d  pasan BH-FDR=%d -> %s" % (len(celdas), int(keep.sum()), OUT))


if __name__ == "__main__":
    main()
