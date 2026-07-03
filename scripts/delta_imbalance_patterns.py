#!/usr/bin/env python3
"""delta_imbalance_patterns.py — los PATRONES condicionales del desequilibrio de delta.

El barrido crudo (delta_imbalance_study.py) ya midió que el delta a secas no bate al azar
(edge +0,3..+0,8 pp, CI cruza 0). La literatura de order flow no usa el delta crudo: usa
CONDICIONES. Aquí se miden esas, una por una, con el mismo metodo (triple barrera,
null emparejado, n_eff, BH-FDR).

Patrones probados (nombre = como lo llama la calle -> como se mide aqui):
  ABSORCION   "delta divergence": delta fuerte a un lado y el precio NO acompaña en la misma
              ventana -> se opera CONTRA el delta (al lado absorbido lo estan tapando).
  APILADO     "stacked imbalance": k minutos seguidos con el delta del mismo signo por encima
              del umbral -> se opera CON el delta.
  CONVICCION  delta por CONTRATO alto (|dd|/volumen de opciones en el decil superior).
  RELEVANCIA  delta grande frente al volumen de ACCIONES del minuto (el flujo de opciones
              importa cuando es grande PARA ESE subyacente, no en dolares absolutos).
  ORO         solo 09:45-11:00 ET (ventana de oro de la doctrina).
  PICADORA    solo 11:30-14:00 ET (control negativo: si el edge aparece aqui, es ruido).

LOTE FUERA DE SESION. Salida: data/research/delta_imbalance_patterns.json
"""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from delta_imbalance_study import (  # noqa: E402
    Panel, atr_wilder, rolling_sum_blockwise, triple_barrier, matched_random,
    wilson, effective_n, bh_fdr, block_bootstrap_edge, two_prop_p, MIN_CLUSTERS)

CACHE = "data/research/delta_imbalance_cache.npz"
OUT = "data/research/delta_imbalance_patterns.json"

W_GRID = (5, 15)
THETA = (2.0, 3.0)
BARRIERS = ((1.0, 1.0), (1.5, 1.0))
HORIZONS = (30, 60)
STACK_K = 3
MIN_N = 300


def zscore_prev_days(vals, sym, day, warm=900):
    """z con la sigma de los dias ANTERIORES del mismo simbolo. Sin mirar el futuro."""
    z = np.full(vals.size, np.nan)
    for si in np.unique(sym):
        m = sym == si
        v, d = vals[m], day[m]
        zz = np.full(v.size, np.nan)
        acc_sq, acc_n = 0.0, 0
        for di in np.unique(d):
            sel = d == di
            if acc_n >= warm:
                s = np.sqrt(acc_sq / acc_n)
                if s > 0:
                    zz[sel] = v[sel] / s
            good = v[sel][np.isfinite(v[sel])]
            acc_sq += float(np.sum(good * good))
            acc_n += good.size
        z[m] = zz
    return z


def build_cache():
    p = Panel()
    atr = atr_wilder(p)
    out = {"atr": atr}
    for w in W_GRID:
        dd = rolling_sum_blockwise(p.dir_delta_flow, p.block_id, w)
        ov = rolling_sum_blockwise(p.uw_vol, p.block_id, w)
        sv = rolling_sum_blockwise(p.v, p.block_id, w)
        out["dd%d" % w] = dd
        out["z%d" % w] = zscore_prev_days(dd, p.sym, p.day)
        # retorno del MISMO tramo (precio de hace w minutos -> cierre actual), sin cruzar dia
        prev_c = np.full(p.c.size, np.nan)
        idx = np.arange(p.c.size)
        ok = idx - w >= 0
        prev_c[ok] = p.c[idx[ok] - w]
        same = np.zeros(p.c.size, dtype=bool)
        same[ok] = p.block_id[idx[ok] - w] == p.block_id[idx[ok]]
        prev_c[~same] = np.nan
        out["ret%d" % w] = (p.c - prev_c) / np.where(atr > 0, atr, np.nan)
        out["conv%d" % w] = np.abs(dd) / np.where(ov > 0, ov, np.nan)
        out["rel%d" % w] = np.abs(dd) / np.where(sv > 0, sv, np.nan)
    np.savez_compressed(CACHE, **out)
    return p, out


def load_cache():
    p = Panel()
    if os.path.exists(CACHE):
        z = np.load(CACHE)
        return p, {k: z[k] for k in z.files}
    return build_cache()


def decile_cut(x, sym, q=0.80):
    """Umbral por SIMBOLO al percentil q (la escala de MU no es la de NOK)."""
    cut = np.full(x.size, np.nan)
    for si in np.unique(sym):
        m = sym == si
        v = x[m]
        good = v[np.isfinite(v)]
        if good.size < 500:
            continue
        cut[m] = np.quantile(good, q)
    return cut


def cum_delta(p):
    """Delta ACUMULADO de la sesion (la linea que la calle llama CVD / HIRO). Por bloque."""
    cs = np.cumsum(np.nan_to_num(p.dir_delta_flow))
    starts, ends = p.block_bounds()
    base = np.zeros(cs.size)
    for s, e in zip(starts, ends):
        base[s:e] = cs[s] - np.nan_to_num(p.dir_delta_flow[s])
    return cs - base


def rolling_extreme(x, block_id, w, kind):
    """max/min movil de w barras SIN cruzar (sym,dia). NaN durante el calentamiento."""
    n = x.size
    out = np.full(n, np.nan)
    idx = np.arange(n)
    starts = np.nonzero(np.concatenate(([True], block_id[1:] != block_id[:-1])))[0]
    pos = idx - np.repeat(starts, np.diff(np.append(starts, n)))
    ok = pos >= (w - 1)
    sel = idx[ok]
    if sel.size == 0:
        return out
    win = np.lib.stride_tricks.sliding_window_view(x, w)
    out[ok] = (win.max(axis=1) if kind == "max" else win.min(axis=1))[sel - (w - 1)]
    return out


def divergence_patterns(p, C, w=30):
    """Divergencia CANONICA: el precio hace extremo nuevo de w barras y el delta ACUMULADO
    NO lo acompaña -> reversion. Es la definicion de la literatura de footprint/CVD, que usa
    la LINEA acumulada, no el incremento por minuto."""
    cd = cum_delta(p)
    hi_p = rolling_extreme(p.h, p.block_id, w, "max")
    lo_p = rolling_extreme(p.l, p.block_id, w, "min")
    hi_d = rolling_extreme(cd, p.block_id, w, "max")
    lo_d = rolling_extreme(cd, p.block_id, w, "min")
    ok = (np.isfinite(C["atr"]) & (C["atr"] > 0) & np.isfinite(hi_p) & np.isfinite(hi_d)
          & (p.minute_et >= 585) & (p.minute_et < 940))
    # bajista: precio en maximo de w, delta acumulado por DEBAJO de su maximo de w
    bear = ok & (p.h >= hi_p - 1e-9) & (cd < hi_d - 1e-9)
    bull = ok & (p.l <= lo_p + 1e-9) & (cd > lo_d + 1e-9)
    conf_up = ok & (p.h >= hi_p - 1e-9) & (cd >= hi_d - 1e-9)
    conf_dn = ok & (p.l <= lo_p + 1e-9) & (cd <= lo_d + 1e-9)
    one = np.ones(p.h.size, dtype=np.int8)
    return {
        "DIVERG_BAJISTA_w%d" % w: (bear, -one,
            "precio en maximo de %d min y el delta acumulado NO hace maximo -> corto" % w),
        "DIVERG_ALCISTA_w%d" % w: (bull, one,
            "precio en minimo de %d min y el delta acumulado NO hace minimo -> largo" % w),
        "CVD_CONFIRMA_ARRIBA_w%d" % w: (conf_up, one,
            "precio Y delta acumulado hacen maximo de %d min a la vez -> continuacion" % w),
        "CVD_CONFIRMA_ABAJO_w%d" % w: (conf_dn, -one,
            "precio Y delta acumulado hacen minimo de %d min a la vez -> continuacion" % w),
    }


def patterns(p, C):
    """{nombre: (mascara, direccion, descripcion)} — direccion +1 largo / -1 corto."""
    base_ok = np.isfinite(C["atr"]) & (C["atr"] > 0)
    hora = (p.minute_et >= 585) & (p.minute_et < 940)
    out = {}
    for w in W_GRID:
        z, ret = C["z%d" % w], C["ret%d" % w]
        conv, rel = C["conv%d" % w], C["rel%d" % w]
        fin = base_ok & hora & np.isfinite(z) & np.isfinite(ret)
        for th in THETA:
            big = fin & (np.abs(z) >= th)
            sgn = np.sign(z)
            # ABSORCION: el delta empuja y el precio va al REVES (o no se mueve) -> contra el delta
            absorb = big & (sgn * ret <= 0.0)
            out["ABSORCION_w%d_t%.0f" % (w, th)] = (
                absorb, -sgn,
                "delta |z|>=%.0f en %dm y el precio NO acompaña -> se opera CONTRA el delta" % (th, w))
            # CONFIRMACION: delta y precio del mismo lado -> con el delta
            confirm = big & (sgn * ret > 0.0)
            out["CONFIRMA_w%d_t%.0f" % (w, th)] = (
                confirm, sgn,
                "delta |z|>=%.0f en %dm y el precio acompaña -> se opera CON el delta" % (th, w))
            # APILADO: k minutos seguidos con el mismo signo por encima del umbral
            hit = (np.abs(z) >= th).astype(np.int8) * np.nan_to_num(sgn).astype(np.int8)
            stack = np.ones(z.size, dtype=bool)
            for j in range(STACK_K):
                shifted = np.full(z.size, 0, dtype=np.int8)
                idx = np.arange(z.size)
                ok = idx - j >= 0
                shifted[ok] = hit[idx[ok] - j]
                same_blk = np.zeros(z.size, dtype=bool)
                same_blk[ok] = p.block_id[idx[ok] - j] == p.block_id[idx[ok]]
                stack &= same_blk & (shifted == hit) & (hit != 0)
            out["APILADO_w%d_t%.0f" % (w, th)] = (
                fin & stack, sgn, "%d minutos seguidos con |z|>=%.0f del mismo signo (%dm)" % (STACK_K, th, w))
            # CONVICCION: delta por contrato en el quintil alto del propio simbolo
            cut = decile_cut(conv, p.sym, 0.80)
            out["CONVICCION_w%d_t%.0f" % (w, th)] = (
                big & np.isfinite(cut) & (conv >= cut), sgn,
                "delta |z|>=%.0f (%dm) y delta/contrato en el quintil alto del simbolo" % (th, w))
            # RELEVANCIA: delta grande frente al volumen de ACCIONES del propio simbolo
            cutr = decile_cut(rel, p.sym, 0.80)
            out["RELEVANCIA_w%d_t%.0f" % (w, th)] = (
                big & np.isfinite(cutr) & (rel >= cutr), sgn,
                "delta |z|>=%.0f (%dm) y |delta|/volumen de acciones en el quintil alto" % (th, w))
            # ventanas horarias sobre la señal cruda
            oro = big & (p.minute_et >= 585) & (p.minute_et < 660)
            out["ORO_w%d_t%.0f" % (w, th)] = (oro, sgn, "delta |z|>=%.0f (%dm) solo 09:45-11:00 ET" % (th, w))
            pic = big & (p.minute_et >= 690) & (p.minute_et < 840)
            out["PICADORA_w%d_t%.0f" % (w, th)] = (
                pic, sgn, "control negativo: mismo gatillo solo 11:30-14:00 ET" % ())
            # ABSORCION en la ventana de oro (la interaccion que la doctrina predice)
            out["ABSORCION_ORO_w%d_t%.0f" % (w, th)] = (
                absorb & (p.minute_et >= 585) & (p.minute_et < 660), -sgn,
                "absorcion |z|>=%.0f (%dm) dentro de la ventana de oro" % (th, w))
    return out


def evaluate(p, C, name, mask, direction, desc, cells):
    idx = np.nonzero(mask)[0]
    if idx.size < MIN_N:
        return
    d = direction[idx].astype(np.int8)
    d[d == 0] = 1
    atr = C["atr"]
    ridx, rdir = matched_random(p, idx, seed=abs(hash(name)) % 2**31, atr=atr)
    for k_tp, k_sl in BARRIERS:
        for H in HORIZONS:
            lab, amb = triple_barrier(p, idx, d, atr, k_tp, k_sl, H)
            rlab, _ = triple_barrier(p, ridx, rdir, atr, k_tp, k_sl, H)
            keep, rkeep = lab >= 0, rlab >= 0
            n, rn = int(keep.sum()), int(rkeep.sum())
            if n < MIN_N or rn < MIN_N:
                continue
            wins, rwins = int((lab[keep] == 1).sum()), int((rlab[rkeep] == 1).sum())
            clusters = int(np.unique(p.block_id[idx[keep]]).size)
            n_eff = effective_n(n, clusters)
            pw, lo, hi = wilson(wins, max(1.0, n_eff), p=wins / n)
            exp_of = lambda q: q * k_tp - (1 - q) * k_sl
            boot = block_bootstrap_edge((lab[keep] == 1).astype(float),
                                        (rlab[rkeep] == 1).astype(float))
            cells.append(dict(
                patron=name, desc=desc, k_tp=k_tp, k_sl=k_sl, H=H,
                n=n, wins=wins, wr=pw, wr_lo=lo, wr_hi=hi, clusters=clusters,
                n_eff=round(n_eff, 1), exp=exp_of(pw), exp_lo=exp_of(lo), exp_hi=exp_of(hi),
                timeouts=int((lab < 0).sum()), ambig=float(amb.mean()),
                null_wr=rwins / rn, null_n=rn,
                edge=boot["edge"], edge_lo=boot["lo"], edge_hi=boot["hi"],
                p=two_prop_p(wins, n, rwins, rn)))


def verdict(c):
    if c["clusters"] < MIN_CLUSTERS or c["n_eff"] < 50:
        return "DATA-INSUFFICIENT"
    if c["edge_hi"] <= 0:
        return "DEAD"
    if not c["fdr_pass"]:
        return "UNPROVEN"
    if c["exp_lo"] > 0 and c["edge_lo"] > 0:
        return "PROVEN"
    return "UNPROVEN"


def main():
    ap = argparse.ArgumentParser(description="patrones condicionales del delta imbalance")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if a.rebuild and os.path.exists(CACHE):
        os.remove(CACHE)
    p, C = load_cache()
    print("panel %d minutos · %d syms · %d dias" % (p.sym.size, len(p.symbols), len(p.days)))
    pats = patterns(p, C)
    for w in (15, 30, 60):
        pats.update(divergence_patterns(p, C, w))
    cells = []
    for name, (mask, direc, desc) in sorted(pats.items()):
        n = int(mask.sum())
        print("  %-26s %7d disparos" % (name, n))
        evaluate(p, C, name, mask, direc, desc, cells)
    if not cells:
        print("SIN CELDAS")
        return
    keep = bh_fdr([c["p"] for c in cells], q=0.10)
    for c, k in zip(cells, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = verdict(c)
    cells.sort(key=lambda c: -c["edge_lo"])
    res = {"n_cells": len(cells), "fdr_pass": int(keep.sum()), "cells": cells}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)

    print("\n%-26s %4s %4s %3s | %6s %6s %5s | %6s %6s | %7s %7s %7s | %s"
          % ("patron", "ktp", "ksl", "H", "n", "n_eff", "clu", "wr", "null",
             "edge", "edge_lo", "p", "veredicto"))
    for c in cells[:a.top]:
        print("%-26s %4.2f %4.2f %3d | %6d %6.0f %5d | %6.3f %6.3f | %+7.4f %+7.4f %7.4f | %s"
              % (c["patron"], c["k_tp"], c["k_sl"], c["H"], c["n"], c["n_eff"], c["clusters"],
                 c["wr"], c["null_wr"], c["edge"], c["edge_lo"], c["p"], c["veredicto"]))
    print("\nceldas=%d  pasan BH-FDR=%d -> %s" % (res["n_cells"], res["fdr_pass"], OUT))


if __name__ == "__main__":
    main()
