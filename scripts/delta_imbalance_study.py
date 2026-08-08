#!/usr/bin/env python3
"""delta_imbalance_study.py — ¿el DESEQUILIBRIO DE DELTA de opciones (UW) predice el precio?

LOTE FUERA DE SESION. Metodo obligatorio de la casa (skill measured-probability):
triple barrera con timeout=NULL, null de entrada aleatoria emparejada por sym x hora,
n_eff corregida por correlacion, seleccion por Wilson-LB de la EXPECTANCIA, BH-FDR q=0.10.

Entrada: data/research/delta_imbalance.npz (delta_imbalance_prep.py)
Salida:  data/research/delta_imbalance_study.json + tabla por stdout
"""
import argparse
import json
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

NPZ = "data/research/delta_imbalance.npz"
OUT = "data/research/delta_imbalance_study.json"

WINDOWS = (1, 5, 15)                 # minutos de acumulacion del delta
THETAS = (1.5, 2.0, 3.0)             # z minimo para que exista señal
K_TP = (0.75, 1.0, 1.5)
K_SL = (0.75, 1.0)
HORIZONS = (10, 30, 60)
ATR_N = 14
MIN_CLUSTERS = 40                    # (sym,dia) minimos para publicar una celda
RHO_DEFAULT = 0.412                  # correlacion media medida en la flota (2026-07-25)
BOOT_N = 2000
BOOT_BLOCK = 30


# ---------------------------------------------------------------- utilidades

def wilson(w, n, z=1.96, p=None):
    """CI de Wilson. `p` explicito permite la proporcion de la muestra CRUDA con la `n`
    EFECTIVA — que es como manda la casa (n_eff solo ensancha el intervalo, no cambia p)."""
    if n <= 0:
        return 0.0, 0.0, 0.0
    if p is None:
        p = w / n
    p = min(1.0, max(0.0, p))
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, (c - m) / d, (c + m) / d


def effective_n(n, n_clusters, rho=RHO_DEFAULT):
    """n_eff = n/(1+(k-1)rho), topada por el numero de clusters (sym,dia)."""
    if n <= 0 or n_clusters <= 0:
        return 0.0
    k = n / float(n_clusters)
    return min(float(n_clusters), n / (1.0 + (k - 1.0) * rho))


def bh_fdr(pvals, q=0.10):
    """Benjamini-Hochberg. Devuelve mascara de rechazos."""
    p = np.asarray(pvals, dtype=float)
    n = p.size
    if n == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    thresh = q * (np.arange(1, n + 1) / n)
    passed = p[order] <= thresh
    keep = np.zeros(n, dtype=bool)
    if passed.any():
        kmax = np.max(np.nonzero(passed)[0])
        keep[order[:kmax + 1]] = True
    return keep


def two_prop_p(w1, n1, w2, n2):
    """p bilateral de dos proporciones (normal). n<=0 -> 1.0."""
    if n1 <= 0 or n2 <= 0:
        return 1.0
    p1, p2 = w1 / n1, w2 / n2
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(max(p * (1 - p) * (1.0 / n1 + 1.0 / n2), 1e-18))
    zz = abs(p1 - p2) / se
    return math.erfc(zz / math.sqrt(2.0))


# ---------------------------------------------------------------- carga

class Panel(object):
    """Minutos alineados, ordenados por (sym, dia, ts), con indices de bloque."""

    def __init__(self, path=NPZ):
        z = np.load(path, allow_pickle=True)
        self.symbols = [str(s) for s in z["symbols"]]
        self.days = [str(d) for d in z["days"]]
        order = np.lexsort((z["ts"], z["day"], z["sym"]))
        self.sym = z["sym"][order]
        self.day = z["day"][order]
        self.ts = z["ts"][order]
        for k in ("o", "h", "l", "c", "v", "uw_vol", "uw_tx",
                  "dir_delta_flow", "total_delta_flow", "otm_dir_delta_flow",
                  "otm_total_delta_flow"):
            setattr(self, k, z[k][order].astype(np.float64))
        blk = self.sym.astype(np.int64) * 100000 + self.day.astype(np.int64)
        self.block = blk
        self.new_block = np.empty(blk.size, dtype=bool)
        self.new_block[0] = True
        self.new_block[1:] = blk[1:] != blk[:-1]
        self.block_id = np.cumsum(self.new_block) - 1
        self.n_blocks = int(self.block_id[-1]) + 1
        # minuto del dia ET (los ts son UTC; ET = UTC-4 en toda la ventana abr-ago)
        self.minute_et = ((self.ts % 86400) // 60 - 240).astype(np.int64)

    def block_bounds(self):
        starts = np.nonzero(self.new_block)[0]
        ends = np.append(starts[1:], self.sym.size)
        return starts, ends


def rolling_sum_blockwise(x, block_id, w):
    """Suma movil de w minutos que NUNCA cruza (sym,dia). NaN mientras no hay w barras."""
    if w == 1:
        return x.copy()
    cs = np.concatenate(([0.0], np.cumsum(x)))
    out = np.full(x.size, np.nan)
    idx = np.arange(x.size)
    # posicion dentro del bloque
    starts, ends = np.nonzero(np.concatenate(([True], block_id[1:] != block_id[:-1])))[0], None
    pos = idx - np.repeat(starts, np.diff(np.append(starts, x.size)))
    ok = pos >= (w - 1)
    out[ok] = cs[idx[ok] + 1] - cs[idx[ok] + 1 - w]
    return out


def atr_wilder(panel, n=ATR_N):
    """ATR de Wilder 1m por bloque. NaN durante el calentamiento."""
    h, l, c = panel.h, panel.l, panel.c
    prev_c = np.concatenate(([np.nan], c[:-1]))
    prev_c[panel.new_block] = np.nan
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr[np.isnan(tr)] = (h - l)[np.isnan(tr)]
    out = np.full(tr.size, np.nan)
    starts, ends = panel.block_bounds()
    for s, e in zip(starts, ends):
        seg = tr[s:e]
        if seg.size < n:
            continue
        a = np.empty(seg.size)
        a[:n - 1] = np.nan
        a[n - 1] = seg[:n].mean()
        for i in range(n, seg.size):
            a[i] = (a[i - 1] * (n - 1) + seg[i]) / n
        out[s:e] = a
    return out


# ---------------------------------------------------------------- etiquetado

def triple_barrier(panel, entry_idx, direction, atr, k_tp, k_sl, H):
    """1 = TP primero, 0 = SL primero, -1 = timeout (NULL, no cuenta).

    Barra ambigua (toca TP y SL en el mismo minuto) -> SL (conservador). Se cuenta aparte.
    Camino t+1..t+H y SOLO dentro del mismo (sym,dia)."""
    n = entry_idx.size
    entry = panel.c[entry_idx]
    a = atr[entry_idx]
    tp = entry + direction * k_tp * a
    sl = entry - direction * k_sl * a
    res = np.full(n, -1, dtype=np.int8)
    amb = np.zeros(n, dtype=bool)
    live = np.ones(n, dtype=bool)
    blk = panel.block_id[entry_idx]
    last = panel.sym.size - 1
    for j in range(1, H + 1):
        idx = np.minimum(entry_idx + j, last)
        same = (panel.block_id[idx] == blk) & (entry_idx + j <= last)
        active = live & same
        if not active.any():
            break
        hi = panel.h[idx]
        lo = panel.l[idx]
        up = np.where(direction > 0, hi >= tp, lo <= tp) if False else None
        hit_tp = np.where(direction > 0, hi >= tp, lo <= tp)
        hit_sl = np.where(direction > 0, lo <= sl, hi >= sl)
        both = active & hit_tp & hit_sl
        only_tp = active & hit_tp & ~hit_sl
        only_sl = active & hit_sl & ~hit_tp
        res[only_tp] = 1
        res[only_sl] = 0
        res[both] = 0
        amb[both] = True
        live &= ~(only_tp | only_sl | both)
        live &= ~(~same)          # se acabo el dia: timeout
        if not live.any():
            break
    return res, amb


# ---------------------------------------------------------------- señales

def build_signals(panel):
    """{nombre: (z_score, descripcion)} — z SIN mirar el futuro: sigma del sym con los
    minutos ANTERIORES (expandiendo por bloques, arranque tras 3 sesiones)."""
    sigs = {}
    for w in WINDOWS:
        dd = rolling_sum_blockwise(panel.dir_delta_flow, panel.block_id, w)
        # sigma por simbolo con SOLO dias previos (media 0 por construccion del flujo neto)
        z = np.full(dd.size, np.nan)
        for si in range(len(panel.symbols)):
            m = panel.sym == si
            if not m.any():
                continue
            d_idx = panel.day[m]
            vals = dd[m]
            order_days = np.unique(d_idx)
            acc_sq, acc_n = 0.0, 0
            zz = np.full(vals.size, np.nan)
            for di in order_days:
                sel = d_idx == di
                if acc_n >= 3 * 300:
                    s = math.sqrt(acc_sq / acc_n)
                    if s > 0:
                        zz[sel] = vals[sel] / s
                good = vals[sel][~np.isnan(vals[sel])]
                acc_sq += float(np.sum(good * good))
                acc_n += good.size
            z[m] = zz
        sigs["dd%dm" % w] = (z, "suma %d min de dir_delta_flow, z con sigma de dias previos" % w)
    # OTM direccional: la version "conviccion" (apuestas fuera del dinero)
    for w in (5,):
        od = rolling_sum_blockwise(panel.otm_dir_delta_flow, panel.block_id, w)
        z = np.full(od.size, np.nan)
        for si in range(len(panel.symbols)):
            m = panel.sym == si
            vals = od[m]
            d_idx = panel.day[m]
            acc_sq, acc_n = 0.0, 0
            zz = np.full(vals.size, np.nan)
            for di in np.unique(d_idx):
                sel = d_idx == di
                if acc_n >= 3 * 300:
                    s = math.sqrt(acc_sq / acc_n)
                    if s > 0:
                        zz[sel] = vals[sel] / s
                good = vals[sel][~np.isnan(vals[sel])]
                acc_sq += float(np.sum(good * good))
                acc_n += good.size
            z[m] = zz
        sigs["otm%dm" % w] = (z, "suma %d min de otm_dir_delta_flow, z con sigma previa" % w)
    return sigs


def entries_for(z, theta, atr, minute_et, mode):
    """Indices y direccion. mode='sigue' opera EN el sentido del delta, 'fade' en contra."""
    ok = np.isfinite(z) & np.isfinite(atr) & (atr > 0)
    ok &= (minute_et >= 585) & (minute_et < 940)     # 09:45-15:40 ET (doctrina de horarios)
    fire = ok & (np.abs(z) >= theta)
    idx = np.nonzero(fire)[0]
    d = np.sign(z[idx]).astype(np.int8)
    if mode == "fade":
        d = (-d).astype(np.int8)
    return idx, d


def matched_random(panel, entry_idx, seed, atr):
    """Null A: misma cantidad de entradas por (sym, bucket horario), direccion barajada."""
    rng = np.random.default_rng(seed)
    bucket = (panel.minute_et // 30)
    key_all = panel.sym.astype(np.int64) * 1000 + bucket
    pool_ok = np.isfinite(atr) & (atr > 0) & (panel.minute_et >= 585) & (panel.minute_et < 940)
    out_idx, out_dir = [], []
    keys, counts = np.unique(key_all[entry_idx], return_counts=True)
    for k, cnt in zip(keys, counts):
        cand = np.nonzero((key_all == k) & pool_ok)[0]
        if cand.size == 0:
            continue
        pick = rng.choice(cand, size=int(cnt), replace=cand.size < cnt)
        out_idx.append(pick)
        out_dir.append(rng.choice(np.array([-1, 1], dtype=np.int8), size=int(cnt)))
    if not out_idx:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    return np.concatenate(out_idx), np.concatenate(out_dir)


def block_bootstrap_edge(sig, rnd, n_boot=BOOT_N, block=BOOT_BLOCK, seed=11):
    """CI de la DIFERENCIA de win rate por bootstrap estacionario por bloques."""
    rng = np.random.default_rng(seed)
    if sig.size == 0 or rnd.size == 0:
        return None
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        a = _boot_blocks(sig, block, rng)
        c = _boot_blocks(rnd, block, rng)
        diffs[b] = a.mean() - c.mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return dict(edge=float(sig.mean() - rnd.mean()), lo=float(lo), hi=float(hi))


def _boot_blocks(x, block, rng):
    n = x.size
    nb = max(1, n // block)
    starts = rng.integers(0, max(1, n - block + 1), size=nb)
    take = (starts[:, None] + np.arange(block)[None, :]).ravel() % n
    return x[take]


# ---------------------------------------------------------------- barrido

def run(limit_syms=None, verbose=True):
    p = Panel()
    if verbose:
        print("panel: %d minutos, %d syms, %d dias, %d bloques (sym,dia)"
              % (p.sym.size, len(p.symbols), len(p.days), p.n_blocks))
    atr = atr_wilder(p)
    sigs = build_signals(p)

    cells = []
    for sname, (z, sdesc) in sigs.items():
        for theta in THETAS:
            for mode in ("sigue", "fade"):
                idx, direc = entries_for(z, theta, atr, p.minute_et, mode)
                if idx.size < 200:
                    continue
                ridx, rdir = matched_random(p, idx, seed=hash((sname, theta, mode)) % 2**31, atr=atr)
                for k_tp in K_TP:
                    for k_sl in K_SL:
                        for H in HORIZONS:
                            lab, amb = triple_barrier(p, idx, direc, atr, k_tp, k_sl, H)
                            rlab, _ = triple_barrier(p, ridx, rdir, atr, k_tp, k_sl, H)
                            keep = lab >= 0
                            rkeep = rlab >= 0
                            n = int(keep.sum())
                            rn = int(rkeep.sum())
                            if n < 100 or rn < 100:
                                continue
                            wins = int((lab[keep] == 1).sum())
                            rwins = int((rlab[rkeep] == 1).sum())
                            clusters = int(np.unique(p.block_id[idx[keep]]).size)
                            n_eff = effective_n(n, clusters)
                            pw, lo, hi = wilson(wins, max(1.0, n_eff), p=wins / n)
                            exp_of = lambda q: q * k_tp - (1 - q) * k_sl
                            boot = block_bootstrap_edge(
                                (lab[keep] == 1).astype(float), (rlab[rkeep] == 1).astype(float))
                            cells.append(dict(
                                sig=sname, desc=sdesc, theta=theta, mode=mode,
                                k_tp=k_tp, k_sl=k_sl, H=H,
                                n=n, wins=wins, wr=pw, wr_lo=lo, wr_hi=hi,
                                clusters=clusters, n_eff=round(n_eff, 1),
                                exp=exp_of(pw), exp_lo=exp_of(lo), exp_hi=exp_of(hi),
                                timeouts=int((lab < 0).sum()), ambig=float(amb.mean()),
                                null_wr=rwins / rn, null_n=rn,
                                edge=boot["edge"] if boot else None,
                                edge_lo=boot["lo"] if boot else None,
                                edge_hi=boot["hi"] if boot else None,
                                p=two_prop_p(wins, n, rwins, rn)))
                if verbose:
                    print("  %-8s th=%.1f %-5s -> %d entradas" % (sname, theta, mode, idx.size))

    if not cells:
        print("SIN CELDAS: ninguna combinacion alcanzo el minimo de muestra")
        return {"cells": [], "verdict": "DATA-INSUFFICIENT"}

    keep = bh_fdr([c["p"] for c in cells], q=0.10)
    for c, k in zip(cells, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = verdict(c)
    cells.sort(key=lambda c: (-c["exp_lo"], -c["n_eff"]))
    res = {"n_cells": len(cells), "fdr_pass": int(keep.sum()),
           "rho": RHO_DEFAULT, "min_clusters": MIN_CLUSTERS, "cells": cells}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    return res


def verdict(c):
    if c["clusters"] < MIN_CLUSTERS or c["n_eff"] < 50:
        return "DATA-INSUFFICIENT"
    if c["edge_hi"] is not None and c["edge_hi"] <= 0:
        return "DEAD"
    if not c["fdr_pass"]:
        return "UNPROVEN"
    if c["exp_lo"] > 0 and c["edge_lo"] is not None and c["edge_lo"] > 0:
        return "PROVEN"
    return "UNPROVEN"


def main():
    ap = argparse.ArgumentParser(description="estudio medido del desequilibrio de delta UW")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    res = run()
    cells = res.get("cells", [])
    print("\n%-8s %-5s %-5s %4s %4s %3s | %6s %6s %6s | %7s %7s | %6s %7s %7s | %s"
          % ("sig", "th", "modo", "ktp", "ksl", "H", "n", "n_eff", "clu",
             "wr", "wr_lo", "null", "edge", "edge_lo", "veredicto"))
    for c in cells[:a.top]:
        print("%-8s %-5.1f %-5s %4.2f %4.2f %3d | %6d %6.1f %3d | %7.3f %7.3f | %6.3f %7.3f %7.3f | %s"
              % (c["sig"], c["theta"], c["mode"], c["k_tp"], c["k_sl"], c["H"],
                 c["n"], c["n_eff"], c["clusters"], c["wr"], c["wr_lo"],
                 c["null_wr"], c["edge"] or 0, c["edge_lo"] or 0, c["veredicto"]))
    print("\nceldas=%d  pasan BH-FDR=%d  -> %s"
          % (res["n_cells"], res["fdr_pass"], OUT))


if __name__ == "__main__":
    main()
