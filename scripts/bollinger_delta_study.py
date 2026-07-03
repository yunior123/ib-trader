#!/usr/bin/env python3
"""bollinger_delta_study.py — ¿la reversion de delta REFUERZA el rebote de Bollinger?

Idea de Yunior (2026-08-08): *"lets use delta reversion to reinforce bollinger reversals"*.
Es la pregunta correcta: bollinger SOLO ya se midio y quedo UNPROVEN (edge -0,014, 0 de 117
celdas pasan BH-FDR, docs/NULL-CONTROL-2026-07-25.md), y el delta SOLO tambien. La pregunta
viva es si la INTERSECCION vale mas que las partes.

SETUP BASE (regla 1 de la casa): el cierre 1m sale de la banda BB(20,2) -> se opera la
REVERSION (banda reventada = rebote elastico). Arriba -> corto. Abajo -> largo.

REFUERZOS que se prueban, cada uno en el sentido de la reversion:
  A) DIVERGENCIA del delta ACUMULADO (lo unico que sobrevivio de esa linea, ver
     [[delta-divergence-veto]]): precio en extremo de 15 min y el delta acumulado no acompaña
  B) ABSORCION: agresion pesada (|z| del delta a 5 min) + ineficiencia (el precio apenas se
     movio para tanta agresion), operando contra el lado agresor
  C) delta acumulado del dia con signo CONTRARIO a la ruptura (el flujo ya se dio la vuelta)

CONTROLES obligatorios: bollinger SOLO (la parte), y el refuerzo INVERTIDO (si el refuerzo
sirve, la version invertida tiene que ir peor). Ver [[drift-confound]].

LOTE FUERA DE SESION. Salida: data/research/bollinger_delta_study.json
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
from delta_imbalance_patterns import zscore_prev_days, cum_delta, rolling_extreme  # noqa: E402

OUT = "data/research/bollinger_delta_study.json"
BB_N, BB_K = 20, 2.0
W_DIV = 15
W_AGR = 5
K_TP = (1.0, 1.5)
K_SL = (1.0,)
HORIZONS = (15, 30, 60)


def bollinger(p, n=BB_N, k=BB_K):
    """media y sigma moviles por bloque (sym,dia). NaN durante el calentamiento."""
    c = p.c
    cs = np.concatenate(([0.0], np.cumsum(c)))
    cs2 = np.concatenate(([0.0], np.cumsum(c * c)))
    idx = np.arange(c.size)
    starts = np.nonzero(np.concatenate(([True], p.block_id[1:] != p.block_id[:-1])))[0]
    pos = idx - np.repeat(starts, np.diff(np.append(starts, c.size)))
    ok = pos >= (n - 1)
    mid = np.full(c.size, np.nan)
    sd = np.full(c.size, np.nan)
    i = idx[ok]
    s1 = cs[i + 1] - cs[i + 1 - n]
    s2 = cs2[i + 1] - cs2[i + 1 - n]
    m = s1 / n
    var = np.maximum(s2 / n - m * m, 0.0)
    mid[ok] = m
    sd[ok] = np.sqrt(var)
    return mid, mid + k * sd, mid - k * sd


def evalua(p, atr, nombre, mask, dirs, celdas):
    idx = np.nonzero(mask)[0]
    if idx.size < 200:
        print("  %-44s %6d (pocos)" % (nombre, idx.size))
        return
    d = dirs[idx].astype(np.int8)
    d[d == 0] = 1
    ridx, rdir = matched_random(p, idx, seed=abs(hash(nombre)) % 2**31, atr=atr)
    print("  %-44s %6d disparos (%.0f%% largos)" % (nombre, idx.size, 100 * (d > 0).mean()))
    for k_tp in K_TP:
        for k_sl in K_SL:
            for H in HORIZONS:
                lab, _ = triple_barrier(p, idx, d, atr, k_tp, k_sl, H)
                rlab, _ = triple_barrier(p, ridx, rdir, atr, k_tp, k_sl, H)
                sl_, _ = triple_barrier(p, idx, np.ones(idx.size, np.int8), atr, k_tp, k_sl, H)
                cl_, _ = triple_barrier(p, idx, -np.ones(idx.size, np.int8), atr, k_tp, k_sl, H)
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
                sm, cm = sl_ >= 0, cl_ >= 0
                celdas.append(dict(patron=nombre, k_tp=k_tp, k_sl=k_sl, H=H, n=n, wins=w,
                                   wr=pw, wr_lo=lo, clusters=clu, n_eff=round(ne, 1),
                                   exp_lo=ex(lo), null_wr=rw / rn, edge=b["edge"],
                                   edge_lo=b["lo"], edge_hi=b["hi"],
                                   pct_largos=float((d > 0).mean()),
                                   siempre_largo=float((sl_[sm] == 1).mean()) if sm.sum() > 50 else None,
                                   siempre_corto=float((cl_[cm] == 1).mean()) if cm.sum() > 50 else None,
                                   p=two_prop_p(w, n, rw, rn)))


def main():
    ap = argparse.ArgumentParser(description="bollinger + reversion de delta")
    ap.add_argument("--top", type=int, default=18)
    a = ap.parse_args()
    p = Panel()
    atr = atr_wilder(p)
    mid, up, dn = bollinger(p)
    hora = (p.minute_et >= 585) & (p.minute_et < 940)
    base = np.isfinite(atr) & (atr > 0) & np.isfinite(up) & hora

    prev_c = np.concatenate(([np.nan], p.c[:-1]))
    prev_c[p.new_block] = np.nan
    rompe_arriba = base & (p.c > up) & (prev_c <= np.concatenate(([np.nan], up[:-1])))
    rompe_abajo = base & (p.c < dn) & (prev_c >= np.concatenate(([np.nan], dn[:-1])))
    rev = np.where(rompe_arriba, -1, np.where(rompe_abajo, 1, 0)).astype(np.int8)  # fade
    bb = rompe_arriba | rompe_abajo

    # A) divergencia sobre el delta ACUMULADO
    cd = cum_delta(p)
    hp = rolling_extreme(p.h, p.block_id, W_DIV, "max")
    lp = rolling_extreme(p.l, p.block_id, W_DIV, "min")
    hd = rolling_extreme(cd, p.block_id, W_DIV, "max")
    ld = rolling_extreme(cd, p.block_id, W_DIV, "min")
    div_baj = np.isfinite(hp) & (p.h >= hp - 1e-9) & (cd < hd - 1e-9)
    div_alc = np.isfinite(lp) & (p.l <= lp + 1e-9) & (cd > ld + 1e-9)
    A = (rompe_arriba & div_baj) | (rompe_abajo & div_alc)
    A_inv = (rompe_arriba & div_alc) | (rompe_abajo & div_baj)

    # B) absorcion: agresion pesada + ineficiencia, con el lado agresor = el de la ruptura
    dd = rolling_sum_blockwise(p.dir_delta_flow, p.block_id, W_AGR)
    z = zscore_prev_days(dd, p.sym, p.day)
    idx = np.arange(p.c.size)
    okw = idx - W_AGR >= 0
    prevw = np.full(p.c.size, np.nan)
    prevw[okw] = p.c[idx[okw] - W_AGR]
    same = np.zeros(p.c.size, dtype=bool)
    same[okw] = p.block_id[idx[okw] - W_AGR] == p.block_id[idx[okw]]
    prevw[~same] = np.nan
    mov = np.abs(p.c - prevw) / np.where(atr > 0, atr, np.nan)
    efic = mov / np.maximum(np.abs(z), 1e-9)
    absor = np.isfinite(z) & (np.abs(z) >= 2.0) & np.isfinite(efic) & (efic <= 0.20)
    B = (rompe_arriba & absor & (z > 0)) | (rompe_abajo & absor & (z < 0))

    # C) el delta acumulado del dia ya va CONTRA la ruptura
    C = (rompe_arriba & (cd < 0)) | (rompe_abajo & (cd > 0))
    C_inv = (rompe_arriba & (cd > 0)) | (rompe_abajo & (cd < 0))

    celdas = []
    evalua(p, atr, "BASE bollinger solo (fade la banda)", bb, rev, celdas)
    evalua(p, atr, "A + divergencia delta acumulado", A, rev, celdas)
    evalua(p, atr, "A-INV + divergencia al reves (control)", A_inv, rev, celdas)
    evalua(p, atr, "B + absorcion en la ruptura", B, rev, celdas)
    evalua(p, atr, "C + delta del dia ya en contra", C, rev, celdas)
    evalua(p, atr, "C-INV + delta del dia a favor (control)", C_inv, rev, celdas)
    evalua(p, atr, "A+C divergencia Y delta en contra", A & C, rev, celdas)

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
    print("\n%-42s %4s %3s | %6s %5s | %6s %6s | %8s %8s | %s"
          % ("patron", "ktp", "H", "n", "clu", "wr", "null", "edge", "edge_lo", "FDR"))
    for c in celdas[:a.top]:
        print("%-42s %4.1f %3d | %6d %5d | %6.3f %6.3f | %+8.4f %+8.4f | %s"
              % (c["patron"], c["k_tp"], c["H"], c["n"], c["clusters"], c["wr"],
                 c["null_wr"], c["edge"], c["edge_lo"], "si" if c["fdr_pass"] else ""))
    print("\nceldas=%d  pasan BH-FDR=%d -> %s" % (len(celdas), int(keep.sum()), OUT))


if __name__ == "__main__":
    main()
