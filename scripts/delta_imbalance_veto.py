#!/usr/bin/env python3
"""delta_imbalance_veto.py — el uso HONESTO de la divergencia de delta acumulado.

El barrido de patrones midio que DIVERG_BAJISTA (precio en maximo de w min y el delta
ACUMULADO sin hacer maximo) bate al azar por ~1,1 pp con CI positivo y p<1e-4. Un 51,0%
a 1:1 NO es una entrada (la expectancia Wilson-LB es negativa). Lo que SI puede ser un
+1,1 pp es un VETO: no aguantar largos dentro de la divergencia.

Aqui se mide exactamente eso, y ademas los percentiles de MFE/MAE/t_touch que fijan el
objetivo y el stop del ticket (doctrina: el bracket sale de la muestra, no de una opinion).

LOTE FUERA DE SESION. Salida: data/research/delta_imbalance_veto.json
"""
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from delta_imbalance_study import (  # noqa: E402
    Panel, atr_wilder, wilson, effective_n, two_prop_p, block_bootstrap_edge)
from delta_imbalance_patterns import cum_delta, rolling_extreme  # noqa: E402

OUT = "data/research/delta_imbalance_veto.json"
W_DIV = 15
H = 30
K_TP = K_SL = 1.0


def barrier_with_paths(p, idx, direction, atr, k_tp, k_sl, H):
    """Etiqueta + MFE/MAE en ATR + minuto del primer toque. Un solo recorrido."""
    n = idx.size
    entry = p.c[idx]
    a = atr[idx]
    tp = entry + direction * k_tp * a
    sl = entry - direction * k_sl * a
    res = np.full(n, -1, dtype=np.int8)
    mfe = np.zeros(n)
    mae = np.zeros(n)
    t_touch = np.full(n, -1, dtype=np.int32)
    live = np.ones(n, dtype=bool)
    blk = p.block_id[idx]
    last = p.sym.size - 1
    for j in range(1, H + 1):
        nx = np.minimum(idx + j, last)
        same = (p.block_id[nx] == blk) & (idx + j <= last)
        act = live & same
        if not act.any():
            break
        fav = np.where(direction > 0, p.h[nx] - entry, entry - p.l[nx]) / a
        adv = np.where(direction > 0, entry - p.l[nx], p.h[nx] - entry) / a
        mfe[act] = np.maximum(mfe[act], fav[act])
        mae[act] = np.maximum(mae[act], adv[act])
        hit_tp = np.where(direction > 0, p.h[nx] >= tp, p.l[nx] <= tp)
        hit_sl = np.where(direction > 0, p.l[nx] <= sl, p.h[nx] >= sl)
        done_tp = act & hit_tp & ~hit_sl
        done_sl = act & (hit_sl | (hit_tp & hit_sl))
        res[done_tp] = 1
        res[done_sl] = 0
        t_touch[done_tp | done_sl] = j
        live &= ~(done_tp | done_sl) & same
        if not live.any():
            break
    return res, mfe, mae, t_touch


def main():
    p = Panel()
    atr = atr_wilder(p)
    cd = cum_delta(p)
    hi_p = rolling_extreme(p.h, p.block_id, W_DIV, "max")
    hi_d = rolling_extreme(cd, p.block_id, W_DIV, "max")
    lo_p = rolling_extreme(p.l, p.block_id, W_DIV, "min")
    lo_d = rolling_extreme(cd, p.block_id, W_DIV, "min")

    tradable = (np.isfinite(atr) & (atr > 0) & np.isfinite(hi_p) & np.isfinite(hi_d)
                & (p.minute_et >= 585) & (p.minute_et < 940))
    div_bear = tradable & (p.h >= hi_p - 1e-9) & (cd < hi_d - 1e-9)
    div_bull = tradable & (p.l <= lo_p + 1e-9) & (cd > lo_d + 1e-9)

    res = {"w_div": W_DIV, "H": H, "k_tp": K_TP, "k_sl": K_SL,
           "n_minutos": int(tradable.sum()), "bloques": p.n_blocks, "tests": []}

    def cell(name, mask, direc):
        idx = np.nonzero(mask)[0]
        if idx.size < 500:
            return None
        d = np.full(idx.size, direc, dtype=np.int8)
        lab, mfe, mae, tt = barrier_with_paths(p, idx, d, atr, K_TP, K_SL, H)
        keep = lab >= 0
        n = int(keep.sum())
        if n < 500:
            return None
        wins = int((lab[keep] == 1).sum())
        clusters = int(np.unique(p.block_id[idx[keep]]).size)
        n_eff = effective_n(n, clusters)
        pw, lo, hi = wilson(wins, max(1.0, n_eff), p=wins / n)
        q = lambda x, v: float(np.percentile(x, v))
        return dict(nombre=name, n=n, wins=wins, wr=pw, wr_lo=lo, wr_hi=hi,
                    clusters=clusters, n_eff=round(n_eff, 1),
                    labels=(lab[keep] == 1).astype(float),
                    mfe_p50=q(mfe[keep], 50), mfe_p60=q(mfe[keep], 60), mfe_p75=q(mfe[keep], 75),
                    mae_p50=q(mae[keep], 50), mae_p75=q(mae[keep], 75), mae_p90=q(mae[keep], 90),
                    t_p50=float(np.median(tt[keep][tt[keep] > 0])) if (tt[keep] > 0).any() else None)

    # ---- VETO: largos DENTRO vs FUERA de la divergencia bajista (misma poblacion, mismo horario)
    pruebas = [
        ("LARGO dentro de divergencia BAJISTA", div_bear, +1),
        ("LARGO fuera de divergencia BAJISTA", tradable & ~div_bear, +1),
        ("CORTO dentro de divergencia BAJISTA", div_bear, -1),
        ("CORTO fuera de divergencia BAJISTA", tradable & ~div_bear, -1),
        ("CORTO dentro de divergencia ALCISTA", div_bull, -1),
        ("CORTO fuera de divergencia ALCISTA", tradable & ~div_bull, -1),
        ("LARGO dentro de divergencia ALCISTA", div_bull, +1),
        ("LARGO fuera de divergencia ALCISTA", tradable & ~div_bull, +1),
    ]
    out = {}
    for name, mask, direc in pruebas:
        c = cell(name, mask, direc)
        if c:
            out[name] = c

    print("%-38s %8s %7s %6s %7s %7s | %6s %6s %6s | %5s"
          % ("prueba", "n", "clusters", "wr", "wr_lo", "wr_hi", "MFEp60", "MAEp75", "MAEp90", "t50"))
    for name, c in out.items():
        print("%-38s %8d %7d %6.4f %7.4f %7.4f | %6.2f %6.2f %6.2f | %5.0f"
              % (name, c["n"], c["clusters"], c["wr"], c["wr_lo"], c["wr_hi"],
                 c["mfe_p60"], c["mae_p75"], c["mae_p90"], c["t_p50"] or 0))

    pares = [("LARGO dentro de divergencia BAJISTA", "LARGO fuera de divergencia BAJISTA"),
             ("CORTO dentro de divergencia BAJISTA", "CORTO fuera de divergencia BAJISTA"),
             ("CORTO dentro de divergencia ALCISTA", "CORTO fuera de divergencia ALCISTA"),
             ("LARGO dentro de divergencia ALCISTA", "LARGO fuera de divergencia ALCISTA")]
    print("\n%-46s %8s %10s %20s %9s" % ("contraste (dentro - fuera)", "delta", "p", "CI bootstrap", "n dentro"))
    for a, b in pares:
        if a not in out or b not in out:
            continue
        ca, cb = out[a], out[b]
        boot = block_bootstrap_edge(ca["labels"], cb["labels"])
        pv = two_prop_p(ca["wins"], ca["n"], cb["wins"], cb["n"])
        print("%-46s %+8.4f %10.2e   [%+.4f, %+.4f] %9d"
              % (a.split(" dentro")[0] + " " + a.split("divergencia ")[1],
                 boot["edge"], pv, boot["lo"], boot["hi"], ca["n"]))
        res["tests"].append(dict(dentro=a, fuera=b, delta_wr=boot["edge"],
                                 ci=[boot["lo"], boot["hi"]], p=pv,
                                 n_dentro=ca["n"], n_fuera=cb["n"],
                                 wr_dentro=ca["wr"], wr_fuera=cb["wr"]))
    res["celdas"] = {k: {kk: vv for kk, vv in v.items() if kk != "labels"} for k, v in out.items()}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, OUT)
    print("\n-> %s" % OUT)


if __name__ == "__main__":
    main()
