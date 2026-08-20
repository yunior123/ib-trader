#!/usr/bin/env python3
"""footprint_final.py — veredicto final del STACKED IMBALANCE. Verificacion, no barrido.

El barrido (footprint_stack_study.py) deja tres dudas que aqui se resuelven MIDIENDO:

  1) NULL DEBIL. El null del barrido empareja (sym, bucket 30m) pero mezcla los 20 dias:
     si la señal se dispara larga en los dias que suben, cobra la deriva del DIA y el null no.
     Aqui se añade el null ESTRICTO: barras aleatorias del MISMO sym, MISMO dia y MISMA
     media hora, con la MISMA direccion. Controla deriva de dia y de sesion. (skill drift-confound)
  2) UN SOLO SORTEO. El barrido fija una semilla. Aqui 25 sorteos independientes por celda:
     si el signo del edge cambia entre sorteos, era varianza del control.
  3) ESPEJO. Si "sigue" y "fade" pierden LAS DOS contra el null, no hay señal: es artefacto
     de etiquetado (barra que toca TP y SL -> se puntua perdida en ambas direcciones).

Salida: data/research/footprint_final.json
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import footprint_stack_study as S                                        # noqa: E402
from footprint_core import Footprint                                     # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STUDY = os.path.join(REPO, "data", "research", "footprint_stack_study.json")
OUT = os.path.join(REPO, "data", "research", "footprint_final.json")

N_SEEDS = 25
MULT = 10
BOOT = 4000

# celda PRE-REGISTRADA: la receta de vendor de Sierra Chart, declarada antes de mirar nada.
PRIM = dict(nmin=1, inc_tick=True, ratio=4.0, min_vol=50, K=3, mode="sigue",
            barrier="atr", tp=1.0, sl=0.75, H=30)


def die(m):
    sys.stderr.write("FATAL footprint_final: %s\n" % m)
    sys.exit(1)


def null_within_day(panel, idx, d, seed, mult=MULT):
    """Null ESTRICTO: mismo (bloque = sym-dia, bucket de 30 min) y MISMA direccion.

    Responde a la pregunta correcta: 'a esa misma media hora de ese mismo dia, ¿una entrada
    cualquiera lo habria hecho igual de bien?'. Al sortear dentro del dia, la deriva del dia
    es identica para señal y control y no puede fabricar edge.
    """
    rng = np.random.default_rng(seed)
    bucket = panel.minute // 30
    key = panel.block.astype(np.int64) * 100 + bucket
    pool = (np.isfinite(panel.atr) & (panel.atr > 0) &
            (panel.minute >= S.ENTRY_MIN_LO) & (panel.minute <= S.ENTRY_MIN_HI))
    ks = key[idx]
    out_i, out_d = [], []
    for k in np.unique(ks):
        m = ks == k
        cand = np.nonzero((key == k) & pool)[0]
        if cand.size == 0:
            continue
        dirs = d[m]
        take = int(m.sum()) * mult
        pick = rng.choice(cand, size=take, replace=True)
        dd = np.repeat(dirs, mult)               # misma mezcla EXACTA de direccion
        out_i.append(pick)
        out_d.append(dd)
    if not out_i:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int8)
    return np.concatenate(out_i), np.concatenate(out_d).astype(np.int8)


def null_pooled(panel, idx, d, seed, mult=MULT):
    old = S.NULL_MULT
    S.NULL_MULT = mult
    try:
        return S.null_matched(panel, idx, d, seed)
    finally:
        S.NULL_MULT = old


def label(panel, idx, d, cfg):
    if cfg["barrier"] == "atr":
        tp, sl = cfg["tp"] * panel.atr[idx], cfg["sl"] * panel.atr[idx]
    else:
        tp, sl = np.full(idx.size, cfg["tp"]), np.full(idx.size, cfg["sl"])
    lab, amb, mfe, mae = S.triple_barrier(panel, idx, d, tp, sl, cfg["H"])
    k = lab >= 0
    return (lab[k] == 1).astype(float), panel.block[idx[k]], k, amb, mfe, mae


def boot_diff(win_s, clu_s, win_n, clu_n, ncl, seed, nboot=BOOT):
    """Bootstrap de clusters (sym,dia) sobre la DIFERENCIA, manteniendo el emparejamiento."""
    ws = np.bincount(clu_s, weights=win_s, minlength=ncl)
    ns = np.bincount(clu_s, minlength=ncl).astype(float)
    wn = np.bincount(clu_n, weights=win_n, minlength=ncl)
    nn = np.bincount(clu_n, minlength=ncl).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, ncl, size=(nboot, ncl))
    aw, an = ws[pick].sum(1), ns[pick].sum(1)
    bw, bn = wn[pick].sum(1), nn[pick].sum(1)
    ok = (an > 0) & (bn > 0)
    diffs = aw[ok] / an[ok] - bw[ok] / bn[ok]
    sd = float(diffs.std(ddof=1))
    obs = float(win_s.mean() - win_n.mean())
    p = 1.0 if sd <= 0 else math.erfc(abs(obs) / sd / math.sqrt(2.0))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi), float(min(1.0, p)), sd


def boot_wr(win_s, clu_s, ncl, seed, nboot=BOOT):
    """Bootstrap de clusters sobre el win rate PROPIO (para la LB de expectancia)."""
    ws = np.bincount(clu_s, weights=win_s, minlength=ncl)
    ns = np.bincount(clu_s, minlength=ncl).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, ncl, size=(nboot, ncl))
    aw, an = ws[pick].sum(1), ns[pick].sum(1)
    ok = an > 0
    q = aw[ok] / an[ok]
    return float(np.percentile(q, 2.5)), float(np.percentile(q, 97.5))


def evaluate(fp, panel, cfg, seeds, det_cache):
    ck = (cfg["nmin"], cfg["inc_tick"], cfg["ratio"], cfg["min_vol"])
    if ck not in det_cache:
        det_cache[ck] = S.detect(fp, *ck)
    det = det_cache[ck]
    idx, d, ambig_bar = S.entries(det, panel, cfg["K"], cfg["mode"])
    if idx.size < S.MIN_N:
        return None
    w, clu, keep, amb, mfe, mae = label(panel, idx, d, cfg)
    n = int(w.size)
    if n < S.MIN_N:
        return None
    ncl_tot = fp.n_blocks
    ncl = int(np.unique(clu).size)
    wr = float(w.mean())
    q_lo, q_hi = boot_wr(w, clu, ncl_tot, seed=11)
    rr = cfg["tp"] / cfg["sl"]
    res = dict(cfg=dict(cfg), n=n, clusters=ncl,
               n_eff_rho=round(S.effective_n(n, ncl), 1),
               timeouts=int((~keep).sum()),
               wr=round(wr, 4), wr_boot_ci=[round(q_lo, 4), round(q_hi, 4)],
               rr=rr,
               expectancia_stop=round(wr * rr - (1 - wr), 4),
               expectancia_stop_LB=round(q_lo * rr - (1 - q_lo), 4),
               doble_toque_pct=round(100.0 * float(amb.mean()), 2),
               mfe_atr_p60=round(float(np.percentile(mfe[keep], 60)) /
                                 float(np.nanmean(panel.atr[idx[keep]])), 3),
               mae_atr_p75=round(float(np.percentile(mae[keep], 75)) /
                                 float(np.nanmean(panel.atr[idx[keep]])), 3),
               barras_con_ambos_lados_pct=round(100.0 * ambig_bar, 2))
    for name, fn in (("null_pooled", null_pooled), ("null_within_day", null_within_day)):
        eds, nws, ps = [], [], []
        lo_l, hi_l = [], []
        for sd in seeds:
            nidx, nd = fn(panel, idx, d, sd)
            if nidx.size < 500:
                continue
            wn, nclu, _, _, _, _ = label(panel, nidx, nd, cfg)
            if wn.size < 500:
                continue
            lo, hi, p, _ = boot_diff(w, clu, wn, nclu, ncl_tot, seed=sd + 3)
            eds.append(wr - float(wn.mean()))
            nws.append(float(wn.mean()))
            ps.append(p)
            lo_l.append(lo)
            hi_l.append(hi)
        if not eds:
            res[name] = "muestra insuficiente"
            continue
        e = np.array(eds)
        res[name] = dict(
            null_wr=round(float(np.mean(nws)), 4),
            null_wr_sd_entre_sorteos=round(float(np.std(nws, ddof=1)), 4),
            edge=round(float(e.mean()), 4),
            edge_sd=round(float(e.std(ddof=1)), 4),
            edge_min=round(float(e.min()), 4), edge_max=round(float(e.max()), 4),
            pct_sorteos_edge_positivo=round(100.0 * float((e > 0).mean()), 1),
            edge_ci_mediana=[round(float(np.median(lo_l)), 4),
                             round(float(np.median(hi_l)), 4)],
            p_mediana=float("%.4g" % float(np.median(ps))),
            p_max=float("%.4g" % float(np.max(ps))))
    return res


def verdict(r):
    """Veredicto honesto. El null ESTRICTO manda: es el unico sin deriva de dia."""
    nd = r.get("null_within_day")
    if not isinstance(nd, dict):
        return "DATA-INSUFFICIENT"
    lo, hi = nd["edge_ci_mediana"]
    if r["clusters"] < 40:
        return "DATA-INSUFFICIENT"
    if hi <= 0:
        return "DEAD"
    if lo > 0 and nd["p_max"] < 0.05 and nd["pct_sorteos_edge_positivo"] == 100.0 \
            and r["expectancia_stop_LB"] > 0:
        return "PROVEN"
    return "UNPROVEN"


def main():
    fp = Footprint()
    panel = S.Panel(fp)
    st = json.load(open(STUDY))
    cells = st["cells"]
    seeds = list(range(2000, 2000 + N_SEEDS))
    det_cache = {}

    # candidatas: la pre-registrada + las de menor p con etiqueta LIMPIA (barrera ATR).
    clean = sorted([c for c in cells if c["barrier"] == "atr"], key=lambda c: c["p_cluster"])
    cand = [PRIM]
    seen = {tuple(sorted(PRIM.items()))}
    for c in clean:
        cfg = {q: c[q] for q in ("nmin", "inc_tick", "ratio", "min_vol", "K", "mode",
                                 "barrier", "tp", "sl", "H")}
        t = tuple(sorted(cfg.items()))
        if t in seen:
            continue
        seen.add(t)
        cand.append(cfg)
        if len(cand) >= 9:
            break

    out = []
    for cfg in cand:
        r = evaluate(fp, panel, cfg, seeds, det_cache)
        if r is None:
            continue
        r["veredicto"] = verdict(r)
        out.append(r)
        p = r["null_pooled"]
        wd = r["null_within_day"]
        print("%-96s n=%5d wr=%.4f | pooled edge=%+.4f p=%.3g | DIA edge=%+.4f "
              "CI[%+.4f,%+.4f] p=%.3g pos=%.0f%% -> %s"
              % (json.dumps(cfg), r["n"], r["wr"],
                 p["edge"] if isinstance(p, dict) else 0,
                 p["p_mediana"] if isinstance(p, dict) else 1,
                 wd["edge"], wd["edge_ci_mediana"][0], wd["edge_ci_mediana"][1],
                 wd["p_mediana"], wd["pct_sorteos_edge_positivo"], r["veredicto"]))

    # ---- ESPEJO: sigue vs fade con los MISMOS parametros de deteccion ----
    print("\n=== ESPEJO (si las dos direcciones pierden, es artefacto de etiquetado) ===")
    mirror = []
    base = [dict(PRIM),
            dict(nmin=1, inc_tick=True, ratio=3.0, min_vol=0, K=4, mode="sigue",
                 barrier="tick", tp=0.10, sl=0.10, H=30),
            dict(nmin=5, inc_tick=True, ratio=4.0, min_vol=0, K=3, mode="sigue",
                 barrier="tick", tp=0.10, sl=0.10, H=30)]
    for b in base:
        pair = {}
        for mode in ("sigue", "fade"):
            cfg = dict(b)
            cfg["mode"] = mode
            r = evaluate(fp, panel, cfg, seeds[:8], det_cache)
            if r is None:
                continue
            pair[mode] = dict(n=r["n"], wr=r["wr"],
                              edge_pooled=r["null_pooled"]["edge"],
                              edge_dia=r["null_within_day"]["edge"],
                              doble_toque_pct=r["doble_toque_pct"])
        if len(pair) == 2:
            s_, f_ = pair["sigue"], pair["fade"]
            pair["suma_edges_dia"] = round(s_["edge_dia"] + f_["edge_dia"], 4)
            pair["ambas_pierden"] = bool(s_["edge_dia"] < 0 and f_["edge_dia"] < 0)
            pair["cfg_deteccion"] = {k: b[k] for k in ("nmin", "inc_tick", "ratio", "min_vol",
                                                       "K", "barrier", "tp", "sl", "H")}
            mirror.append(pair)
            print("  %s -> sigue edge_dia=%+.4f (wr %.4f) | fade edge_dia=%+.4f (wr %.4f) | "
                  "suma=%+.4f dobletoque=%.1f%% ambas_pierden=%s"
                  % (json.dumps(pair["cfg_deteccion"]), s_["edge_dia"], s_["wr"],
                     f_["edge_dia"], f_["wr"], pair["suma_edges_dia"],
                     s_["doble_toque_pct"], pair["ambas_pierden"]))

    res = dict(
        generado_utc=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        n_seeds=N_SEEDS, null_mult=MULT, boot=BOOT,
        n_clusters=fp.n_blocks, symbols=fp.symbols, n_dias=len(fp.days),
        nota=("null_within_day = control ESTRICTO (mismo sym, mismo DIA, misma media hora, "
              "misma direccion). Es el que manda: el pooled puede cobrar deriva de dia."),
        preregistrada=PRIM, celdas=out, espejo=mirror)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
