#!/usr/bin/env python3
"""footprint_exec.py — ¿el FADE de 5m sobrevive a una ejecucion REALISTA?

El barrido entra al CIERRE de la barra de señal. Eso es una entrada imposible: el cierre de una
barra con apilamiento de compra es, casi por definicion, un print agresivo EN EL ASK, y el fade
consiste en VENDER ahi. Un vendedor real cruza al BID. Si el edge es medio spread, muere aqui.

Tres ejecuciones, de la fantasia a lo implementable:
  A  cierre de la barra de señal        (lo que hizo el barrido; NO implementable)
  B  apertura de la barra SIGUIENTE     (implementable: la señal se conoce al cierre)
  C  apertura siguiente + coste         (1 tick adverso ida y vuelta = spread real de SPY/QQQ)

Ademas: cortes por simbolo y por mitad temporal, y 25 sorteos del null estricto.

Salida: data/research/footprint_exec.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import footprint_stack_study as S                                        # noqa: E402
from footprint_core import Footprint                                     # noqa: E402
from footprint_final import null_within_day, boot_diff, boot_wr          # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "data", "research", "footprint_exec.json")

N_SEEDS = 25
MULT = 10
TICK = 0.01

# la familia que sobrevivio al null estricto (footprint_grid_strict.py)
FAMILY = [
    dict(nmin=5, inc_tick=True, ratio=2.0, min_vol=0, K=4, mode="fade", tp=1.5, sl=1.0, H=60),
    dict(nmin=5, inc_tick=True, ratio=2.0, min_vol=0, K=4, mode="fade", tp=1.5, sl=1.0, H=30),
    dict(nmin=5, inc_tick=True, ratio=3.0, min_vol=0, K=4, mode="fade", tp=1.5, sl=1.0, H=60),
    dict(nmin=5, inc_tick=True, ratio=2.0, min_vol=0, K=3, mode="fade", tp=1.5, sl=1.0, H=60),
    dict(nmin=5, inc_tick=True, ratio=2.0, min_vol=50, K=4, mode="fade", tp=1.5, sl=1.0, H=60),
    dict(nmin=1, inc_tick=True, ratio=4.0, min_vol=50, K=3, mode="fade", tp=1.5, sl=1.0, H=30),
]


def barrier_exec(panel, idx, d, tp_abs, sl_abs, H, mode_exec, cost_ticks=0.0):
    """Triple barrera con punto de entrada explicito.

    mode_exec='close' : entrada al cierre de la barra de señal, camino desde idx+1 (fantasia)
    mode_exec='open'  : entrada a la APERTURA de idx+1, camino desde idx+1 (implementable)
    El coste se cobra moviendo TP mas lejos y SL mas cerca (ida y vuelta).
    """
    last = panel.c.size - 1
    if mode_exec == "close":
        entry = panel.c[idx].copy()
        first = 1
    elif mode_exec == "open":
        nx = np.minimum(idx + 1, last)
        entry = panel.o[nx].copy()
        first = 1
    else:
        raise ValueError(mode_exec)
    n = idx.size
    tp = entry + d * (tp_abs + cost_ticks)
    sl = entry - d * np.maximum(sl_abs - cost_ticks, TICK)
    res = np.full(n, -1, dtype=np.int8)
    live = np.ones(n, dtype=bool)
    mfe = np.zeros(n)
    mae = np.zeros(n)
    blk = panel.block[idx]
    valid = np.ones(n, dtype=bool)
    if mode_exec == "open":
        nx = np.minimum(idx + 1, last)
        valid = (panel.block[nx] == blk) & (idx + 1 <= last) & np.isfinite(entry)
        live &= valid
    for j in range(first, H + 1):
        nxt = np.minimum(idx + j, last)
        same = (panel.block[nxt] == blk) & (idx + j <= last)
        act = live & same
        if not act.any():
            break
        hi, lo = panel.h[nxt], panel.l[nxt]
        up = np.where(d > 0, hi - entry, entry - lo)
        dn = np.where(d > 0, entry - lo, hi - entry)
        mfe = np.where(act, np.maximum(mfe, up), mfe)
        mae = np.where(act, np.maximum(mae, dn), mae)
        hit_tp = np.where(d > 0, hi >= tp, lo <= tp)
        hit_sl = np.where(d > 0, lo <= sl, hi >= sl)
        both = act & hit_tp & hit_sl
        only_tp = act & hit_tp & ~hit_sl
        only_sl = act & hit_sl & ~hit_tp
        res[only_tp] = 1
        res[only_sl] = 0
        res[both] = 0
        live &= ~(only_tp | only_sl | both) & same
        if not live.any():
            break
    res[~valid] = -1
    return res, mfe, mae


def measure(fp, panel, cfg, seeds, det_cache, mode_exec, cost):
    ck = (cfg["nmin"], cfg["inc_tick"], cfg["ratio"], cfg["min_vol"])
    if ck not in det_cache:
        det_cache[ck] = S.detect(fp, *ck)
    idx, d, _ = S.entries(det_cache[ck], panel, cfg["K"], cfg["mode"])
    if idx.size < S.MIN_N:
        return None
    tp_s, sl_s = cfg["tp"] * panel.atr[idx], cfg["sl"] * panel.atr[idx]
    lab, mfe, mae = barrier_exec(panel, idx, d, tp_s, sl_s, cfg["H"], mode_exec, cost)
    k = lab >= 0
    if int(k.sum()) < S.MIN_N:
        return None
    w = (lab[k] == 1).astype(float)
    clu = panel.block[idx[k]]
    ncl_tot = fp.n_blocks
    wr = float(w.mean())
    qlo, qhi = boot_wr(w, clu, ncl_tot, seed=17)
    rr = cfg["tp"] / cfg["sl"]
    eds, nws, ps, los, his = [], [], [], [], []
    for sd in seeds:
        nidx, nd = null_within_day(panel, idx, d, sd, mult=MULT)
        if nidx.size < 500:
            continue
        tp_n, sl_n = cfg["tp"] * panel.atr[nidx], cfg["sl"] * panel.atr[nidx]
        nlab, _, _ = barrier_exec(panel, nidx, nd, tp_n, sl_n, cfg["H"], mode_exec, cost)
        nk = nlab >= 0
        if int(nk.sum()) < 500:
            continue
        wn = (nlab[nk] == 1).astype(float)
        nclu = panel.block[nidx[nk]]
        lo, hi, p, _ = boot_diff(w, clu, wn, nclu, ncl_tot, seed=sd + 31)
        eds.append(wr - float(wn.mean()))
        nws.append(float(wn.mean()))
        ps.append(p)
        los.append(lo)
        his.append(hi)
    if not eds:
        return None
    e = np.array(eds)
    out = dict(n=int(k.sum()), clusters=int(np.unique(clu).size),
               wr=round(wr, 4), wr_boot_ci=[round(qlo, 4), round(qhi, 4)],
               null_wr=round(float(np.mean(nws)), 4),
               edge=round(float(e.mean()), 4), edge_sd=round(float(e.std(ddof=1)), 4),
               edge_ci=[round(float(np.median(los)), 4), round(float(np.median(his)), 4)],
               pct_sorteos_positivo=round(100.0 * float((e > 0).mean()), 1),
               p_mediana=float("%.4g" % float(np.median(ps))),
               p_max=float("%.4g" % float(np.max(ps))),
               rr=rr, expectancia_stop=round(wr * rr - (1 - wr), 4),
               expectancia_stop_LB=round(qlo * rr - (1 - qlo), 4),
               timeouts=int((~k).sum()))
    # cortes
    sym_of, day_of = fp.block_sym, fp.block_day
    med = int(np.median(np.unique(day_of)))
    cuts = {}
    nidx, nd = null_within_day(panel, idx, d, seeds[0], mult=MULT)
    tp_n, sl_n = cfg["tp"] * panel.atr[nidx], cfg["sl"] * panel.atr[nidx]
    nlab, _, _ = barrier_exec(panel, nidx, nd, tp_n, sl_n, cfg["H"], mode_exec, cost)
    nk = nlab >= 0
    wn_all = (nlab[nk] == 1).astype(float)
    nclu_all = panel.block[nidx[nk]]
    for cname, ms, mn in (("QQQ", sym_of[clu] == 0, sym_of[nclu_all] == 0),
                          ("SPY", sym_of[clu] == 1, sym_of[nclu_all] == 1),
                          ("dias_1a10", day_of[clu] <= med, day_of[nclu_all] <= med),
                          ("dias_11a20", day_of[clu] > med, day_of[nclu_all] > med)):
        if ms.sum() < 100 or mn.sum() < 100:
            cuts[cname] = "muestra insuficiente"
            continue
        cuts[cname] = dict(n=int(ms.sum()), wr=round(float(w[ms].mean()), 4),
                           null=round(float(wn_all[mn].mean()), 4),
                           edge=round(float(w[ms].mean() - wn_all[mn].mean()), 4))
    out["cortes"] = cuts
    return out


def main():
    fp = Footprint()
    panel = S.Panel(fp)
    seeds = list(range(3000, 3000 + N_SEEDS))
    det_cache = {}
    rows = []
    for cfg in FAMILY:
        row = dict(cfg=cfg)
        for name, mex, cost in (("A_cierre_fantasia", "close", 0.0),
                                ("B_apertura_siguiente", "open", 0.0),
                                ("C_apertura_mas_coste_1tick", "open", TICK)):
            r = measure(fp, panel, cfg, seeds, det_cache, mex, cost)
            row[name] = r if r else "muestra insuficiente"
        rows.append(row)
        a = row["A_cierre_fantasia"]
        b = row["B_apertura_siguiente"]
        c = row["C_apertura_mas_coste_1tick"]
        print("%-92s" % json.dumps(cfg))
        for nm, r in (("A cierre   ", a), ("B apertura ", b), ("C apert+cst", c)):
            if isinstance(r, dict):
                print("   %s n=%5d wr=%.4f null=%.4f edge=%+.4f CI[%+.4f,%+.4f] p=%.3g "
                      "pos=%.0f%% expLB=%+.3f"
                      % (nm, r["n"], r["wr"], r["null_wr"], r["edge"], r["edge_ci"][0],
                         r["edge_ci"][1], r["p_mediana"], r["pct_sorteos_positivo"],
                         r["expectancia_stop_LB"]))
            else:
                print("   %s %s" % (nm, r))
    res = dict(generado_utc=__import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(),
        n_seeds=N_SEEDS, null_mult=MULT, tick=TICK,
        nota=("A entra al cierre de la barra de señal (NO implementable: ese print es el "
              "agresivo). B entra a la apertura de la barra siguiente. C añade 1 tick de "
              "coste ida y vuelta. Solo B y C son operables."),
        familia=rows)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
