#!/usr/bin/env python3
"""footprint_grid_strict.py — la MISMA rejilla de footprint_stack_study.py, pero contra el
null ESTRICTO (mismo sym, mismo DIA, misma media hora, misma direccion).

Por que se repite el barrido entero: el null del barrido original mezcla los 20 dias, asi que
una señal que se dispara larga los dias que suben cobra la deriva del DIA y el control no.
Aqui esa via esta cerrada por construccion. Si el numero de celdas que pasan BH-FDR se
desploma al cambiar SOLO el control, el hallazgo original era deriva.

Ademas se mide el ESPEJO de cada celda (misma deteccion, direccion opuesta): si "sigue" y
"fade" pierden LAS DOS contra el mismo control, la celda es artefacto de etiquetado, no señal.

Salida: data/research/footprint_grid_strict.json
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
OUT = os.path.join(REPO, "data", "research", "footprint_grid_strict.json")

MULT = 5
BOOT = 2000


def main():
    fp = Footprint()
    panel = S.Panel(fp)
    ncl_tot = fp.n_blocks
    print("bloques(sym,dia)=%d syms=%s dias=%d" % (ncl_tot, fp.symbols, len(fp.days)))

    cells = []
    for nmin in S.BARSIZES:
        for inc in S.INCLUDE_TICK:
            for ratio in S.RATIOS:
                for mv in S.MIN_VOLS:
                    det = S.detect(fp, nmin, inc, ratio, mv)
                    for K in S.KS:
                        # etiquetas de las DOS direcciones con el MISMO control -> espejo
                        for mode in S.MODES:
                            idx, d, ambig = S.entries(det, panel, K, mode)
                            if idx.size < S.MIN_N:
                                continue
                            seed = abs(hash((nmin, inc, ratio, mv, K, mode))) % 2**31
                            nidx, nd = null_within_day(panel, idx, d, seed, mult=MULT)
                            if nidx.size < 500:
                                continue
                            brs = [("atr", kt, ks) for kt in S.K_TP for ks in S.K_SL]
                            brs += [("tick", t / 100.0, s / 100.0)
                                    for t, s in S.TICK_BRACKETS]
                            for kind, a_tp, a_sl in brs:
                                for H in S.HORIZONS:
                                    if kind == "atr":
                                        tp_s, sl_s = a_tp * panel.atr[idx], a_sl * panel.atr[idx]
                                        tp_n, sl_n = a_tp * panel.atr[nidx], a_sl * panel.atr[nidx]
                                    else:
                                        tp_s = np.full(idx.size, a_tp)
                                        sl_s = np.full(idx.size, a_sl)
                                        tp_n = np.full(nidx.size, a_tp)
                                        sl_n = np.full(nidx.size, a_sl)
                                    lab, amb, mfe, mae = S.triple_barrier(
                                        panel, idx, d, tp_s, sl_s, H)
                                    nlab, _, _, _ = S.triple_barrier(
                                        panel, nidx, nd, tp_n, sl_n, H)
                                    keep, nkeep = lab >= 0, nlab >= 0
                                    n, nn = int(keep.sum()), int(nkeep.sum())
                                    if n < S.MIN_N or nn < 500:
                                        continue
                                    w = (lab[keep] == 1).astype(float)
                                    wn = (nlab[nkeep] == 1).astype(float)
                                    clu = panel.block[idx[keep]]
                                    nclu = panel.block[nidx[nkeep]]
                                    lo, hi, p, _ = boot_diff(w, clu, wn, nclu, ncl_tot,
                                                             seed=seed + 5, nboot=BOOT)
                                    qlo, qhi = boot_wr(w, clu, ncl_tot, seed=seed + 9,
                                                       nboot=BOOT)
                                    wr = float(w.mean())
                                    rr = a_tp / a_sl
                                    ncl = int(np.unique(clu).size)
                                    atrm = float(np.nanmean(panel.atr[idx[keep]]))
                                    cells.append(dict(
                                        nmin=nmin, inc_tick=bool(inc), ratio=ratio,
                                        min_vol=mv, K=K, mode=mode, barrier=kind,
                                        tp=a_tp, sl=a_sl, H=H, n=n, clusters=ncl,
                                        n_eff_rho=round(S.effective_n(n, ncl), 1),
                                        wr=round(wr, 5), null_wr=round(float(wn.mean()), 5),
                                        edge=round(wr - float(wn.mean()), 5),
                                        edge_lo=round(lo, 5), edge_hi=round(hi, 5),
                                        p_cluster=p,
                                        wr_boot_lo=round(qlo, 5), wr_boot_hi=round(qhi, 5),
                                        rr=rr,
                                        exp_stop=round(wr * rr - (1 - wr), 5),
                                        exp_stop_LB=round(qlo * rr - (1 - qlo), 5),
                                        doble_toque_pct=round(100.0 * float(amb.mean()), 2),
                                        timeouts=int((~keep).sum()),
                                        mfe_atr_p60=round(float(
                                            np.percentile(mfe[keep], 60)) / atrm, 3),
                                        mae_atr_p75=round(float(
                                            np.percentile(mae[keep], 75)) / atrm, 3)))
                    print("  nmin=%d tick=%d ratio=%.0f%% mv=%d -> celdas acumuladas %d"
                          % (nmin, inc, ratio * 100, mv, len(cells)))

    if not cells:
        sys.exit("SIN CELDAS")
    keep = S.bh_fdr([c["p_cluster"] for c in cells], q=0.10)
    for c, k in zip(cells, keep):
        c["fdr_pass"] = bool(k)

    # espejo: por cada (deteccion, barrera, H) comparar sigue vs fade
    idxmap = {}
    for c in cells:
        key = (c["nmin"], c["inc_tick"], c["ratio"], c["min_vol"], c["K"],
               c["barrier"], c["tp"], c["sl"], c["H"])
        idxmap.setdefault(key, {})[c["mode"]] = c
    ambas_pierden = 0
    pares = 0
    for key, pr in idxmap.items():
        if len(pr) != 2:
            continue
        pares += 1
        s_, f_ = pr["sigue"], pr["fade"]
        both_lose = s_["edge"] < 0 and f_["edge"] < 0
        if both_lose:
            ambas_pierden += 1
        for c in pr.values():
            c["espejo_suma_edges"] = round(s_["edge"] + f_["edge"], 5)
            c["espejo_ambas_pierden"] = bool(both_lose)

    surv = [c for c in cells if c["fdr_pass"]]
    surv_clean = [c for c in surv if not c.get("espejo_ambas_pierden")
                  and c["edge"] > 0 and c["doble_toque_pct"] < 5.0]
    cells.sort(key=lambda c: c["p_cluster"])

    res = dict(
        generado_utc=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        control="null ESTRICTO: mismo sym, mismo DIA, misma media hora, misma direccion",
        null_mult=MULT, boot=BOOT, n_clusters=ncl_tot,
        symbols=fp.symbols, n_dias=len(fp.days),
        n_cells=len(cells), fdr_pass=int(keep.sum()),
        fdr_pass_limpias=len(surv_clean),
        pares_espejo=pares, pares_ambas_direcciones_pierden=ambas_pierden,
        celdas_limpias_supervivientes=sorted(
            surv_clean, key=lambda c: c["p_cluster"])[:20],
        cells=cells)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)

    print("\nceldas=%d  pasan BH-FDR q=0.10 = %d  (de esas, LIMPIAS = %d)"
          % (len(cells), int(keep.sum()), len(surv_clean)))
    print("pares espejo=%d  con AMBAS direcciones perdiendo=%d (%.1f%%)"
          % (pares, ambas_pierden, 100.0 * ambas_pierden / max(1, pares)))
    print("\nTOP 15 por p:")
    for c in cells[:15]:
        print(" n=%d r=%.0f mv=%d K=%d %-5s %-4s %.2f/%.2f H=%2d | n=%5d wr=%.4f null=%.4f "
              "edge=%+.4f CI[%+.4f,%+.4f] p=%.2e fdr=%s dt=%.1f%% ambas_pierden=%s"
              % (c["nmin"], c["ratio"] * 100, c["min_vol"], c["K"], c["mode"], c["barrier"],
                 c["tp"], c["sl"], c["H"], c["n"], c["wr"], c["null_wr"], c["edge"],
                 c["edge_lo"], c["edge_hi"], c["p_cluster"], c["fdr_pass"],
                 c["doble_toque_pct"], c.get("espejo_ambas_pierden")))
    print("-> %s" % OUT)


if __name__ == "__main__":
    main()
