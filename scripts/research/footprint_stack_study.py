#!/usr/bin/env python3
"""footprint_stack_study.py — ¿el STACKED IMBALANCE del footprint separa del azar?

LOTE FUERA DE SESION. Metodo obligatorio (skill measured-probability):
triple barrera con timeout=NULL, null de entrada aleatoria EMPAREJADA (sym x bucket horario)
con la MISMA mezcla largo/corto, muestra EFECTIVA por clusters (sym,dia), bootstrap de
CLUSTERS sobre la DIFERENCIA, y BH-FDR q=0.10 sobre toda la rejilla.

Celda PRE-REGISTRADA (declarada ANTES de mirar resultados, sin penalizacion de multiplicidad):
  receta de vendor de Sierra Chart -> ratio 400%, K=3, min_vol 50, tick-rule incluida,
  direccion = la del apilamiento, barrera 1.0 ATR / 1.0 ATR / H=30 min, barras de 1 min.

Entrada: data/research/footprint_cells.npz  (footprint_core.py --build)
Salida : data/research/footprint_stack_study.json
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from footprint_core import Footprint, diagonal_imbalance, stacks, RTH_MINUTES  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "data", "research", "footprint_stack_study.json")

BARSIZES = (1, 5)
RATIOS = (2.0, 3.0, 4.0)
KS = (3, 4, 5)
MIN_VOLS = (0, 50)
INCLUDE_TICK = (True, False)
MODES = ("sigue", "fade")
K_TP = (0.75, 1.0, 1.5)
K_SL = (0.75, 1.0)
TICK_BRACKETS = ((10, 10), (20, 20), (30, 15))     # centavos (tp, sl)
HORIZONS = (10, 30, 60)

ATR_N = 14
RHO = 0.412                       # correlacion media medida en la flota (2026-07-25)
MIN_CLUSTERS = 40
MIN_N = 100
NULL_MULT = 5                     # el null se sobre-muestrea para que no meta ruido
NULL_MIN = 2000
BOOT = 2000
ENTRY_MIN_LO = 15                 # 09:45 ET (doctrina de horarios)
ENTRY_MIN_HI = 370                # 15:40 ET

PRIMARY = dict(nmin=1, ratio=4.0, K=3, min_vol=50, inc_tick=True, mode="sigue",
               barrier="atr", k_tp=1.0, k_sl=1.0, H=30)


def die(msg):
    sys.stderr.write("FATAL footprint_stack_study: %s\n" % msg)
    sys.exit(1)


def wilson(p, n, z=1.96):
    if n <= 0:
        return 0.0, 0.0
    p = min(1.0, max(0.0, p))
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def effective_n(n, n_clusters, rho=RHO):
    if n <= 0 or n_clusters <= 0:
        return 0.0
    k = n / float(n_clusters)
    return min(float(n_clusters), n / (1.0 + (k - 1.0) * rho))


def bh_fdr(pvals, q=0.10):
    p = np.asarray(pvals, dtype=float)
    n = p.size
    if n == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    passed = p[order] <= q * (np.arange(1, n + 1) / n)
    keep = np.zeros(n, dtype=bool)
    if passed.any():
        keep[order[:int(np.max(np.nonzero(passed)[0])) + 1]] = True
    return keep


def two_prop_p(w1, n1, w2, n2):
    if n1 <= 0 or n2 <= 0:
        return 1.0
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(max(p * (1 - p) * (1.0 / n1 + 1.0 / n2), 1e-18))
    return math.erfc(abs(w1 / n1 - w2 / n2) / se / math.sqrt(2.0))


# ------------------------------------------------------------------ panel 1m

class Panel(object):
    def __init__(self, fp):
        self.nb = fp.n_blocks
        self.M = RTH_MINUTES
        self.o = fp.bar_o.ravel()
        self.h = fp.bar_h.ravel()
        self.l = fp.bar_l.ravel()
        self.c = fp.bar_c.ravel()
        self.block = np.repeat(np.arange(self.nb), self.M)
        self.minute = np.tile(np.arange(self.M), self.nb)
        self.sym = fp.block_sym[self.block]
        self.day = fp.block_day[self.block]
        self.atr = self._atr()

    def _atr(self):
        out = np.full(self.o.size, np.nan)
        for b in range(self.nb):
            s, e = b * self.M, (b + 1) * self.M
            h, l, c = self.h[s:e], self.l[s:e], self.c[s:e]
            pc = np.concatenate(([np.nan], c[:-1]))
            tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
            tr[0] = h[0] - l[0]
            if np.isnan(tr).any():
                die("bloque %d con TR NaN: hay minutos sin barra" % b)
            a = np.full(tr.size, np.nan)
            a[ATR_N - 1] = tr[:ATR_N].mean()
            for i in range(ATR_N, tr.size):
                a[i] = (a[i - 1] * (ATR_N - 1) + tr[i]) / ATR_N
            out[s:e] = a
        return out

    def idx(self, block, minute):
        return block * self.M + minute


def triple_barrier(panel, idx, direction, tp_abs, sl_abs, H):
    """1 = TP primero, 0 = SL primero, -1 = timeout (NULL). Barra ambigua -> SL."""
    n = idx.size
    entry = panel.c[idx]
    tp = entry + direction * tp_abs
    sl = entry - direction * sl_abs
    res = np.full(n, -1, dtype=np.int8)
    amb = np.zeros(n, dtype=bool)
    live = np.ones(n, dtype=bool)
    mfe = np.zeros(n)
    mae = np.zeros(n)
    blk = panel.block[idx]
    last = panel.c.size - 1
    for j in range(1, H + 1):
        nx = np.minimum(idx + j, last)
        same = (panel.block[nx] == blk) & (idx + j <= last)
        act = live & same
        if not act.any():
            break
        hi, lo = panel.h[nx], panel.l[nx]
        up = np.where(direction > 0, hi - entry, entry - lo)
        dn = np.where(direction > 0, entry - lo, hi - entry)
        mfe = np.where(act, np.maximum(mfe, up), mfe)
        mae = np.where(act, np.maximum(mae, dn), mae)
        hit_tp = np.where(direction > 0, hi >= tp, lo <= tp)
        hit_sl = np.where(direction > 0, lo <= sl, hi >= sl)
        both = act & hit_tp & hit_sl
        only_tp = act & hit_tp & ~hit_sl
        only_sl = act & hit_sl & ~hit_tp
        res[only_tp] = 1
        res[only_sl] = 0
        res[both] = 0
        amb[both] = True
        live &= ~(only_tp | only_sl | both) & same
        if not live.any():
            break
    return res, amb, mfe, mae


# ------------------------------------------------------------------ deteccion

def detect(fp, nmin, inc_tick, ratio, min_vol):
    """Por barra: longitud de la mayor racha diagonal de compra y de venta."""
    bars = fp.bars(nmin, include_tick_rule=inc_tick)
    n = len(bars)
    blk = np.empty(n, dtype=np.int32)
    lastmin = np.empty(n, dtype=np.int32)
    runb = np.zeros(n, dtype=np.int16)
    runs = np.zeros(n, dtype=np.int16)
    volb = np.zeros(n)
    vols = np.zeros(n)
    for i, (b, _bi, lm, _t0, ad, bd) in enumerate(bars):
        blk[i] = b
        lastmin[i] = lm
        buy, sell = diagonal_imbalance(ad, bd, ratio, min_vol)
        sb = stacks(buy, 2)
        ss = stacks(sell, 2)
        if sb:
            j = int(np.argmax([x[1] for x in sb]))
            runb[i] = sb[j][1]
            volb[i] = float(ad[sb[j][0]:sb[j][0] + sb[j][1]].sum())
        if ss:
            j = int(np.argmax([x[1] for x in ss]))
            runs[i] = ss[j][1]
            vols[i] = float(bd[ss[j][0]:ss[j][0] + ss[j][1]].sum())
    return dict(block=blk, lastmin=lastmin, runb=runb, runs=runs, volb=volb, vols=vols,
                n_bars=n)


def entries(det, panel, K, mode):
    """Indices 1m de entrada (cierre de la barra) y direccion. Ambiguos -> racha mayor."""
    okb = det["runb"] >= K
    oks = det["runs"] >= K
    both = okb & oks
    tie = both & (det["runb"] == det["runs"])
    winb = both & ((det["runb"] > det["runs"]) | (tie & (det["volb"] >= det["vols"])))
    wins = both & ~winb
    sig_up = (okb & ~both) | winb
    sig_dn = (oks & ~both) | wins
    fire = sig_up | sig_dn
    lm = det["lastmin"]
    fire &= (lm >= ENTRY_MIN_LO) & (lm <= ENTRY_MIN_HI)
    idx = panel.idx(det["block"][fire].astype(np.int64), lm[fire].astype(np.int64))
    d = np.where(sig_up[fire], 1, -1).astype(np.int8)
    if mode == "fade":
        d = (-d).astype(np.int8)
    ok = np.isfinite(panel.atr[idx]) & (panel.atr[idx] > 0) & np.isfinite(panel.c[idx])
    ambig = float(both.sum()) / max(1, int((okb | oks).sum()))
    return idx[ok], d[ok], ambig


def null_matched(panel, idx, d, seed):
    """Null A: barras aleatorias emparejadas por (sym, bucket de 30 min) con la MISMA
    mezcla largo/corto dentro de cada bucket (drift-confound: la direccion no se sortea)."""
    rng = np.random.default_rng(seed)
    bucket = panel.minute // 30
    key = panel.sym.astype(np.int64) * 1000 + bucket
    pool = (np.isfinite(panel.atr) & (panel.atr > 0) &
            (panel.minute >= ENTRY_MIN_LO) & (panel.minute <= ENTRY_MIN_HI))
    out_i, out_d = [], []
    ks, counts = np.unique(key[idx], return_counts=True)
    for k, cnt in zip(ks, counts):
        cand = np.nonzero((key == k) & pool)[0]
        if cand.size == 0:
            continue
        take = max(int(cnt) * NULL_MULT, 1)
        frac_up = float((d[key[idx] == k] > 0).mean())
        pick = rng.choice(cand, size=take, replace=True)
        nup = int(round(frac_up * take))
        dd = np.concatenate((np.ones(nup, dtype=np.int8), -np.ones(take - nup, dtype=np.int8)))
        rng.shuffle(dd)
        out_i.append(pick)
        out_d.append(dd)
    if not out_i:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    return np.concatenate(out_i), np.concatenate(out_d)


def cluster_boot(win_s, clu_s, win_n, clu_n, n_clusters, seed=7, nboot=BOOT):
    """Bootstrap de CLUSTERS (sym,dia) sobre la DIFERENCIA de win rate.

    Remuestrea los clusters con reemplazo (senal y null a la vez, manteniendo el
    emparejamiento) usando los agregados por cluster -> exacto y vectorizado.
    p bilateral por aproximacion normal sobre la distribucion bootstrap (sin suelo de
    resolucion, que es lo que exige un BH-FDR sobre miles de celdas)."""
    ws = np.bincount(clu_s, weights=win_s, minlength=n_clusters)
    ns = np.bincount(clu_s, minlength=n_clusters).astype(float)
    wn = np.bincount(clu_n, weights=win_n, minlength=n_clusters)
    nn = np.bincount(clu_n, minlength=n_clusters).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, n_clusters, size=(nboot, n_clusters))
    a_w, a_n = ws[pick].sum(1), ns[pick].sum(1)
    b_w, b_n = wn[pick].sum(1), nn[pick].sum(1)
    ok = (a_n > 0) & (b_n > 0)
    if ok.sum() < nboot // 2:
        return None
    diffs = a_w[ok] / a_n[ok] - b_w[ok] / b_n[ok]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    sd = float(diffs.std(ddof=1))
    obs = float(win_s.mean() - win_n.mean())
    p = 1.0 if sd <= 0 else math.erfc(abs(obs) / sd / math.sqrt(2.0))
    return dict(lo=float(lo), hi=float(hi), p=float(min(1.0, p)), sd=sd)


# ------------------------------------------------------------------ barrido

def run(verbose=True):
    fp = Footprint()
    panel = Panel(fp)
    n_clusters_tot = fp.n_blocks
    if verbose:
        print("bloques(sym,dia)=%d  minutos 1m=%d  syms=%s dias=%d"
              % (n_clusters_tot, panel.c.size, fp.symbols, len(fp.days)))

    cells = []
    for nmin in BARSIZES:
        for inc in INCLUDE_TICK:
            for ratio in RATIOS:
                for mv in MIN_VOLS:
                    det = detect(fp, nmin, inc, ratio, mv)
                    for K in KS:
                        for mode in MODES:
                            idx, d, ambig = entries(det, panel, K, mode)
                            if idx.size < MIN_N:
                                continue
                            nidx, nd = null_matched(
                                panel, idx, d,
                                seed=abs(hash((nmin, inc, ratio, mv, K, mode))) % 2**31)
                            if nidx.size < NULL_MIN:
                                continue
                            brs = [("atr", kt, ks) for kt in K_TP for ks in K_SL]
                            brs += [("tick", t / 100.0, s / 100.0) for t, s in TICK_BRACKETS]
                            for kind, a_tp, a_sl in brs:
                                for H in HORIZONS:
                                    if kind == "atr":
                                        tp_s = a_tp * panel.atr[idx]
                                        sl_s = a_sl * panel.atr[idx]
                                        tp_n = a_tp * panel.atr[nidx]
                                        sl_n = a_sl * panel.atr[nidx]
                                    else:
                                        tp_s = np.full(idx.size, a_tp)
                                        sl_s = np.full(idx.size, a_sl)
                                        tp_n = np.full(nidx.size, a_tp)
                                        sl_n = np.full(nidx.size, a_sl)
                                    lab, amb, mfe, mae = triple_barrier(
                                        panel, idx, d, tp_s, sl_s, H)
                                    nlab, _, _, _ = triple_barrier(
                                        panel, nidx, nd, tp_n, sl_n, H)
                                    keep = lab >= 0
                                    nkeep = nlab >= 0
                                    n = int(keep.sum())
                                    nn = int(nkeep.sum())
                                    if n < MIN_N or nn < 500:
                                        continue
                                    w = (lab[keep] == 1).astype(float)
                                    wn = (nlab[nkeep] == 1).astype(float)
                                    wr = float(w.mean())
                                    wrn = float(wn.mean())
                                    clu = panel.block[idx[keep]]
                                    nclu = panel.block[nidx[nkeep]]
                                    ncl = int(np.unique(clu).size)
                                    n_eff = effective_n(n, ncl)
                                    lo, hi = wilson(wr, max(1.0, n_eff))
                                    bs = cluster_boot(w, clu, wn, nclu, n_clusters_tot,
                                                      seed=abs(hash((kind, H, K))) % 2**31)
                                    atrm = float(np.nanmean(panel.atr[idx[keep]]))
                                    rr = (a_tp / a_sl) if kind == "tick" else (a_tp / a_sl)
                                    exp_ = lambda q: q * rr - (1 - q)   # en unidades de stop
                                    cells.append(dict(
                                        nmin=nmin, inc_tick=bool(inc), ratio=ratio,
                                        min_vol=mv, K=K, mode=mode, barrier=kind,
                                        tp=a_tp, sl=a_sl, H=H,
                                        n=n, wins=int(w.sum()), wr=wr,
                                        wr_lo=lo, wr_hi=hi, clusters=ncl,
                                        n_eff=round(n_eff, 1),
                                        timeouts=int((lab < 0).sum()),
                                        ambig_bar_pct=round(100.0 * ambig, 2),
                                        ambig_bar_tp_sl_pct=round(100.0 * float(amb.mean()), 2),
                                        null_wr=wrn, null_n=nn,
                                        edge=wr - wrn,
                                        edge_lo=bs["lo"] if bs else None,
                                        edge_hi=bs["hi"] if bs else None,
                                        p_cluster=bs["p"] if bs else 1.0,
                                        p_naive=two_prop_p(int(w.sum()), n,
                                                           int(wn.sum()), nn),
                                        rr=rr, exp_stop=exp_(wr), exp_stop_lo=exp_(lo),
                                        mfe_atr_p60=float(np.percentile(mfe[keep], 60) / atrm),
                                        mae_atr_p75=float(np.percentile(mae[keep], 75) / atrm),
                                        atr_mean=atrm,
                                        entries_total=int(idx.size)))
                    if verbose:
                        print("  nmin=%d tick=%d ratio=%.0f%% minvol=%d -> barras=%d "
                              "(K>=3 compra %d / venta %d)"
                              % (nmin, inc, ratio * 100, mv, det["n_bars"],
                                 int((det["runb"] >= 3).sum()), int((det["runs"] >= 3).sum())))

    if not cells:
        die("SIN CELDAS: ninguna combinacion alcanzo el minimo de muestra")

    keep = bh_fdr([c["p_cluster"] for c in cells], q=0.10)
    for c, k in zip(cells, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = verdict(c)

    prim = [c for c in cells if all(c[k] == v for k, v in
                                    dict(nmin=PRIMARY["nmin"], ratio=PRIMARY["ratio"],
                                         K=PRIMARY["K"], min_vol=PRIMARY["min_vol"],
                                         inc_tick=PRIMARY["inc_tick"], mode=PRIMARY["mode"],
                                         barrier=PRIMARY["barrier"], tp=PRIMARY["k_tp"],
                                         sl=PRIMARY["k_sl"], H=PRIMARY["H"]).items())]
    cells.sort(key=lambda c: (c["p_cluster"], -abs(c["edge"])))
    res = dict(generado_utc=__import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(),
        n_cells=len(cells), fdr_pass=int(keep.sum()), rho=RHO,
        n_clusters_total=n_clusters_tot, min_clusters=MIN_CLUSTERS,
        primary_preregistrada=PRIMARY, primary_result=(prim[0] if prim else None),
        cells=cells)
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
    if c["exp_stop_lo"] > 0 and c["edge_lo"] is not None and c["edge_lo"] > 0:
        return "PROVEN"
    return "UNPROVEN"


def main():
    ap = argparse.ArgumentParser(description="stacked imbalance del footprint, medido")
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    res = run()
    print("\n%-3s %-4s %-5s %-3s %-2s %-5s %-5s %5s %4s %3s | %6s %6s %5s | %6s %7s %7s %8s | %s"
          % ("N", "tick", "ratio", "mv", "K", "modo", "barr", "tp/sl", "H", "clu",
             "n", "n_eff", "wr", "null", "edge", "edge_lo", "p_clu", "veredicto"))
    for c in res["cells"][:a.top]:
        print("%-3d %-4d %-5.0f %-3d %-2d %-5s %-5s %.2f/%.2f %3d %3d | %6d %6.1f %.3f | %.3f "
              "%+7.4f %+7.4f %8.2e | %s"
              % (c["nmin"], c["inc_tick"], c["ratio"] * 100, c["min_vol"], c["K"], c["mode"],
                 c["barrier"], c["tp"], c["sl"], c["H"], c["clusters"], c["n"], c["n_eff"],
                 c["wr"], c["null_wr"], c["edge"], c["edge_lo"] or 0, c["p_cluster"],
                 c["veredicto"]))
    p = res["primary_result"]
    print("\nPRE-REGISTRADA %s" % json.dumps(PRIMARY))
    if p:
        print("  n=%d clusters=%d n_eff=%.1f  wr=%.4f [%.4f,%.4f]  null=%.4f  "
              "edge=%+.4f CI[%+.4f,%+.4f] p=%.4f -> %s"
              % (p["n"], p["clusters"], p["n_eff"], p["wr"], p["wr_lo"], p["wr_hi"],
                 p["null_wr"], p["edge"], p["edge_lo"], p["edge_hi"], p["p_cluster"],
                 p["veredicto"]))
    else:
        print("  NO PRODUJO CELDA (muestra insuficiente)")
    print("\nceldas=%d  pasan BH-FDR q=0.10 = %d  -> %s"
          % (res["n_cells"], res["fdr_pass"], OUT))


if __name__ == "__main__":
    main()
