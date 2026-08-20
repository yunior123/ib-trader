#!/usr/bin/env python3
"""footprint_colinear.py — TEST DE COLINEALIDAD: ¿el footprint añade algo sobre "la barra se
movio mucho"?

El apilamiento diagonal se dispara justo cuando la barra ha empujado fuerte en una direccion.
Fade de apilamiento y fade de barra-grande son casi el mismo boleto. La killlist de la casa
exige que la colinealidad se pruebe ANTES que nada: si fadear CUALQUIER barra de 5m del mismo
tamaño da el mismo edge, el footprint es decoracion cara y el tape de Databento no hace falta.

Control 1 (azar):      barra aleatoria del mismo sym/dia/media hora, misma direccion.
Control 2 (COLINEAL):  barra NO-señal del mismo sym/dia/media hora, con |retorno de barra| en
                       el MISMO decil, fadeada contra su propio retorno.
Si edge(señal vs control 2) ~ 0 -> el footprint no aporta nada sobre el retorno de la barra.

Tambien mide el lado "sigue" (la doctrina de vendor) para publicarlo como VETO.

Salida: data/research/footprint_colinear.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import footprint_stack_study as S                                        # noqa: E402
from footprint_core import Footprint                                     # noqa: E402
from footprint_final import null_within_day, boot_diff, boot_wr          # noqa: E402
from footprint_exec import barrier_exec                                  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "data", "research", "footprint_colinear.json")

N_SEEDS = 25
MULT = 10
TICK = 0.01
NDEC = 5          # deciles -> quintiles de |retorno| (con 40 dias no da para 10)

CFG = dict(nmin=5, inc_tick=True, ratio=2.0, min_vol=0, K=4, tp=1.5, sl=1.0, H=60)


def bar5_features(panel, nmin):
    """Para cada barra de nmin minutos: idx del ultimo minuto, retorno de barra / ATR."""
    nb = panel.nb
    M = panel.M
    nbar = M // nmin
    idx = np.empty(nb * nbar, dtype=np.int64)
    ret = np.empty(nb * nbar)
    for b in range(nb):
        base = b * M
        for j in range(nbar):
            s = base + j * nmin
            e = s + nmin - 1
            k = b * nbar + j
            idx[k] = e
            a = panel.atr[e]
            ret[k] = (panel.c[e] - panel.o[s]) / a if (np.isfinite(a) and a > 0) else np.nan
    return idx, ret


def colinear_control(panel, sig_idx, sig_d, all_idx, all_ret, seed, mult=MULT):
    """Barras NO-señal del mismo (bloque, media hora) con |ret| en el mismo quintil,
    fadeadas contra su propio retorno."""
    rng = np.random.default_rng(seed)
    ok = np.isfinite(all_ret) & np.isfinite(panel.atr[all_idx]) & (panel.atr[all_idx] > 0)
    ok &= (panel.minute[all_idx] >= S.ENTRY_MIN_LO) & (panel.minute[all_idx] <= S.ENTRY_MIN_HI)
    ok &= all_ret != 0.0
    pool_idx = all_idx[ok]
    pool_ret = all_ret[ok]
    issig = np.isin(pool_idx, sig_idx)
    pool_idx, pool_ret = pool_idx[~issig], pool_ret[~issig]
    if pool_idx.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    # quintiles de |ret| definidos sobre TODAS las barras (señal incluida) para que el
    # emparejamiento sea comparable
    absall = np.abs(all_ret[ok])
    edges = np.percentile(absall, np.linspace(0, 100, NDEC + 1)[1:-1])
    dec_pool = np.searchsorted(edges, np.abs(pool_ret))
    blk_pool = panel.block[pool_idx]
    buc_pool = panel.minute[pool_idx] // 30
    key_pool = blk_pool.astype(np.int64) * 1000 + buc_pool * 10 + dec_pool

    sig_ret = np.full(sig_idx.size, np.nan)
    m = {int(i): r for i, r in zip(all_idx, all_ret)}
    for j, i in enumerate(sig_idx):
        sig_ret[j] = m.get(int(i), np.nan)
    dec_sig = np.searchsorted(edges, np.abs(sig_ret))
    key_sig = (panel.block[sig_idx].astype(np.int64) * 1000 +
               (panel.minute[sig_idx] // 30) * 10 + dec_sig)

    order = np.argsort(key_pool, kind="stable")
    kp_s = key_pool[order]
    out_i, out_d = [], []
    uk, cnt = np.unique(key_sig, return_counts=True)
    for k, c in zip(uk, cnt):
        lo = np.searchsorted(kp_s, k, "left")
        hi = np.searchsorted(kp_s, k, "right")
        if hi <= lo:
            continue
        cand = order[lo:hi]
        take = int(c) * mult
        pick = rng.choice(cand, size=take, replace=True)
        out_i.append(pool_idx[pick])
        out_d.append(-np.sign(pool_ret[pick]).astype(np.int8))   # fade de su propio retorno
    if not out_i:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    return np.concatenate(out_i), np.concatenate(out_d).astype(np.int8)


def run_side(fp, panel, mode, det, all_idx, all_ret, seeds, mode_exec, cost):
    cfg = dict(CFG)
    idx, d, _ = S.entries(det, panel, CFG["K"], mode)
    tp_s, sl_s = cfg["tp"] * panel.atr[idx], cfg["sl"] * panel.atr[idx]
    lab, mfe, mae = barrier_exec(panel, idx, d, tp_s, sl_s, cfg["H"], mode_exec, cost)
    k = lab >= 0
    w = (lab[k] == 1).astype(float)
    clu = panel.block[idx[k]]
    ncl_tot = fp.n_blocks
    wr = float(w.mean())
    qlo, qhi = boot_wr(w, clu, ncl_tot, seed=23)
    rr = cfg["tp"] / cfg["sl"]
    res = dict(mode=mode, n=int(k.sum()), clusters=int(np.unique(clu).size),
               wr=round(wr, 4), wr_boot_ci=[round(qlo, 4), round(qhi, 4)],
               rr=rr, expectancia_stop=round(wr * rr - (1 - wr), 4),
               expectancia_stop_LB=round(qlo * rr - (1 - qlo), 4),
               mfe_atr_p60=round(float(np.percentile(mfe[k], 60)) /
                                 float(np.nanmean(panel.atr[idx[k]])), 3),
               mae_atr_p75=round(float(np.percentile(mae[k], 75)) /
                                 float(np.nanmean(panel.atr[idx[k]])), 3))
    for cname, fn in (("vs_azar", "azar"), ("vs_colineal", "colineal")):
        eds, nws, ps, los, his = [], [], [], [], []
        for sd in seeds:
            if fn == "azar":
                nidx, nd = null_within_day(panel, idx, d, sd, mult=MULT)
            else:
                nidx, nd = colinear_control(panel, idx, d, all_idx, all_ret, sd, mult=MULT)
            if nidx.size < 500:
                continue
            tp_n, sl_n = cfg["tp"] * panel.atr[nidx], cfg["sl"] * panel.atr[nidx]
            nlab, _, _ = barrier_exec(panel, nidx, nd, tp_n, sl_n, cfg["H"], mode_exec, cost)
            nk = nlab >= 0
            if int(nk.sum()) < 500:
                continue
            wn = (nlab[nk] == 1).astype(float)
            nclu = panel.block[nidx[nk]]
            lo, hi, p, _ = boot_diff(w, clu, wn, nclu, ncl_tot, seed=sd + 41)
            eds.append(wr - float(wn.mean()))
            nws.append(float(wn.mean()))
            ps.append(p)
            los.append(lo)
            his.append(hi)
        if not eds:
            res[cname] = "muestra insuficiente"
            continue
        e = np.array(eds)
        res[cname] = dict(control_wr=round(float(np.mean(nws)), 4),
                          edge=round(float(e.mean()), 4),
                          edge_sd=round(float(e.std(ddof=1)), 4),
                          edge_ci=[round(float(np.median(los)), 4),
                                   round(float(np.median(his)), 4)],
                          pct_sorteos_positivo=round(100.0 * float((e > 0).mean()), 1),
                          p_mediana=float("%.4g" % float(np.median(ps))),
                          p_max=float("%.4g" % float(np.max(ps))))
    return res


def main():
    fp = Footprint()
    panel = S.Panel(fp)
    panel.o = fp.bar_o.ravel()
    seeds = list(range(4000, 4000 + N_SEEDS))
    det = S.detect(fp, CFG["nmin"], CFG["inc_tick"], CFG["ratio"], CFG["min_vol"])
    all_idx, all_ret = bar5_features(panel, CFG["nmin"])
    out = []
    for mode_exec, cost, tag in (("open", TICK, "B+coste (implementable)"),):
        for mode in ("fade", "sigue"):
            r = run_side(fp, panel, mode, det, all_idx, all_ret, seeds, mode_exec, cost)
            r["ejecucion"] = tag
            out.append(r)
            print("%s  %s" % (tag, mode.upper()))
            print("   n=%d wr=%.4f  exp_stop=%+.4f (LB %+.4f)"
                  % (r["n"], r["wr"], r["expectancia_stop"], r["expectancia_stop_LB"]))
            for c in ("vs_azar", "vs_colineal"):
                q = r[c]
                if isinstance(q, dict):
                    print("   %-12s control_wr=%.4f edge=%+.4f CI[%+.4f,%+.4f] p=%.3g pos=%.0f%%"
                          % (c, q["control_wr"], q["edge"], q["edge_ci"][0], q["edge_ci"][1],
                             q["p_mediana"], q["pct_sorteos_positivo"]))
                else:
                    print("   %-12s %s" % (c, q))
    res = dict(generado_utc=__import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(),
        cfg=CFG, n_seeds=N_SEEDS, quintiles_ret=NDEC,
        nota=("vs_colineal = control de barras NO-señal del mismo sym/dia/media hora con "
              "|retorno de barra| en el mismo quintil, fadeadas contra su propio retorno. "
              "Si el edge contra ESE control es ~0, el footprint no añade nada sobre el "
              "retorno de la barra y el tape no hace falta."),
        lados=out)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
