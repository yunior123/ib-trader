#!/usr/bin/env python3
"""delta_setups.py — mide DELTA DIVERGENCE / ABSORCION / CVD DIVERGENCE / DELTA FLIP.

LOTE FUERA DE SESION (Python legitimo, CLAUDE.md).

Entrada : data/research/delta_bars_1m.npz  (lo produce scripts/research/delta_bars.py
          desde el tape XNAS.ITCH tbbo de Databento; delta firmado con el campo `side`
          NATIVO del exchange, convencion verificada en databento/MANIFEST.json)
          data/research/footprint_cells.npz (opcional, de footprint_core.py) -> solo
          para AUDITAR que el delta nativo y el delta por quote-rule coinciden.
Salida  : data/research/delta_setups_backtest.json
          data/research/DELTA-SETUPS-<fecha>.md

Metodologia obligatoria (skill measured-probability):
  - Etiquetado TRIPLE BARRERA (objetivo, stop, tiempo). Nunca retorno a horizonte fijo.
  - Entrada en la APERTURA de la barra SIGUIENTE a la señal. Cero look-ahead: todos los
    percentiles y maximos se calculan con barras CERRADAS antes de la señal.
  - Control de entrada ALEATORIA emparejado por (simbolo, hora del dia, direccion),
    n_null >= 2000 por celda.
  - Wilson 95% sobre muestra EFECTIVA (design effect por solape temporal).
  - BH-FDR q=0,10 sobre TODAS las celdas probadas.
  - n < 30 -> MUESTRA INSUFICIENTE, no se publica win rate.
"""
import json
import math
import os
import sys
import datetime as dt

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RES = os.path.join(REPO, "data", "research")
BARS = os.path.join(RES, "delta_bars_1m.npz")
CELLS = os.path.join(RES, "footprint_cells.npz")
OUT_JSON = os.path.join(RES, "delta_setups_backtest.json")

RTH_START_MIN = 13 * 60 + 30
NBARS = 390
WARMUP = 60          # barras de calentamiento por sesion (percentiles causales + ATR)
ATR_N = 30
K_NULL = 25          # replicas aleatorias por señal
N_NULL_MIN = 2000
FDR_Q = 0.10

# (objetivo_ATR, stop_ATR, horizonte_barras)
BARRIERS = [(1.0, 1.0, 15), (1.0, 1.0, 30), (1.0, 1.0, 60),
            (1.5, 1.5, 15), (1.5, 1.5, 30), (1.5, 1.5, 60),
            (2.0, 2.0, 15), (2.0, 2.0, 30), (2.0, 2.0, 60)]


def die(msg):
    sys.stderr.write("FATAL delta_setups: %s\n" % msg)
    sys.exit(1)


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# ------------------------------------------------------------------ estadistica

def wilson(k, n, z=1.96):
    """Intervalo de Wilson al 95%. n es la muestra EFECTIVA."""
    if n <= 0:
        return (None, None)
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def norm_sf(x):
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def two_prop_p(p1, n1, p2, n2):
    """p-valor bilateral de la diferencia de dos proporciones (n efectivos)."""
    if n1 <= 0 or n2 <= 0:
        return 1.0
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(max(1e-12, p * (1 - p) * (1.0 / n1 + 1.0 / n2)))
    z = (p1 - p2) / se
    return 2.0 * norm_sf(abs(z))


def bh_fdr(pvals, q):
    """Devuelve mascara de rechazos Benjamini-Hochberg."""
    n = len(pvals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvals[i])
    thr = -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / n:
            thr = rank
    keep = [False] * n
    for rank, i in enumerate(order, start=1):
        if rank <= thr:
            keep[i] = True
    return keep


def icc_design_effect(blocks, idxs, outcomes, H):
    """n efectivo por solape temporal: agrupa señales del mismo bloque a <H barras y
    aplica el design effect de la ANOVA de una via sobre el resultado binario."""
    n = len(outcomes)
    if n < 3:
        return float(n), 1.0, 0.0
    order = sorted(range(n), key=lambda i: (blocks[i], idxs[i]))
    clusters = []
    cur = [order[0]]
    for a, b in zip(order, order[1:]):
        if blocks[b] == blocks[a] and (idxs[b] - idxs[a]) < H:
            cur.append(b)
        else:
            clusters.append(cur)
            cur = [b]
    clusters.append(cur)
    k = len(clusters)
    if k < 2 or k == n:
        return float(n), float(n) / max(1, k), 0.0
    y = np.asarray(outcomes, dtype=np.float64)
    gm = y.mean()
    sizes = np.array([len(c) for c in clusters], dtype=np.float64)
    means = np.array([y[np.array(c)].mean() for c in clusters])
    ssb = float((sizes * (means - gm) ** 2).sum())
    ssw = float(sum(((y[np.array(c)] - means[j]) ** 2).sum() for j, c in enumerate(clusters)))
    msb = ssb / (k - 1)
    msw = ssw / (n - k) if n > k else 0.0
    m0 = (n - (sizes ** 2).sum() / n) / (k - 1)
    denom = msb + (m0 - 1) * msw
    icc = 0.0 if denom <= 0 else (msb - msw) / denom
    icc = min(max(icc, 0.0), 1.0)
    mbar = n / k
    deff = 1.0 + (mbar - 1.0) * icc
    return max(1.0, n / deff), mbar, icc


# ------------------------------------------------------------------ datos

class Tape(object):
    def __init__(self):
        z = np.load(BARS, allow_pickle=False)
        arr = z["bars"]
        cols = [str(c) for c in z["cols"]]
        self.syms = [str(s) for s in z["syms"]]
        self.days = [str(d) for d in z["days"]]
        ci = {c: i for i, c in enumerate(cols)}
        nb = len(self.syms) * len(self.days)
        shape = (nb, NBARS)
        self.o = np.full(shape, np.nan)
        self.h = np.full(shape, np.nan)
        self.l = np.full(shape, np.nan)
        self.c = np.full(shape, np.nan)
        self.vol = np.zeros(shape)
        self.delta = np.zeros(shape)
        self.delta_lr = np.zeros(shape)
        self.voln = np.zeros(shape)
        self.block_sym = np.zeros(nb, dtype=int)
        self.block_day = np.zeros(nb, dtype=int)
        seen = set()
        for row in arr:
            si, di, mod = int(row[ci["sym"]]), int(row[ci["day"]]), int(row[ci["mod"]])
            b = si * len(self.days) + di
            m = mod - RTH_START_MIN
            if m < 0 or m >= NBARS:
                die("minuto fuera de RTH: %d" % mod)
            self.block_sym[b], self.block_day[b] = si, di
            seen.add(b)
            self.o[b, m] = row[ci["o"]]
            self.h[b, m] = row[ci["h"]]
            self.l[b, m] = row[ci["l"]]
            self.c[b, m] = row[ci["c"]]
            self.vol[b, m] = row[ci["vol"]]
            self.voln[b, m] = row[ci["vol_n"]]
            self.delta[b, m] = row[ci["vol_b"]] - row[ci["vol_a"]]
            self.delta_lr[b, m] = row[ci["lr_b"]] - row[ci["lr_a"]]
        if len(seen) != nb:
            die("faltan bloques: %d de %d" % (len(seen), nb))
        if np.isnan(self.c).any():
            die("hay barras 1m vacias: el tape no cubre los 390 minutos")
        self.nb = nb
        self.mod = np.arange(NBARS) + RTH_START_MIN
        self.hour = (self.mod // 60).astype(int)
        self.atr = self._atr()

    def _atr(self):
        tr = np.empty((self.nb, NBARS))
        tr[:, 0] = self.h[:, 0] - self.l[:, 0]
        pc = self.c[:, :-1]
        tr[:, 1:] = np.maximum(self.h[:, 1:] - self.l[:, 1:],
                               np.maximum(np.abs(self.h[:, 1:] - pc),
                                          np.abs(self.l[:, 1:] - pc)))
        out = np.full((self.nb, NBARS), np.nan)
        cs = np.cumsum(tr, axis=1)
        for i in range(ATR_N, NBARS):
            out[:, i] = (cs[:, i] - cs[:, i - ATR_N]) / ATR_N
        return out


# ------------------------------------------------------------------ triple barrera

def label_all(tp_atr, sl_atr, H, tape):
    """label[b,i,d] en {+1 objetivo, -1 stop, 0 tiempo} y R realizado en unidades ATR.
    Señal en la barra i -> ENTRADA en la apertura de i+1. Cero look-ahead.
    Empate (objetivo y stop en la misma barra) = STOP (conservador)."""
    nb = tape.nb
    lab = np.zeros((nb, NBARS, 2), dtype=np.int8)
    rr = np.full((nb, NBARS, 2), np.nan)
    o, h, l, c, atr = tape.o, tape.h, tape.l, tape.c, tape.atr
    for b in range(nb):
        ob, hb, lb, cb, ab = o[b], h[b], l[b], c[b], atr[b]
        for i in range(ATR_N, NBARS - 1):
            a = ab[i]
            if not (a > 0):
                continue
            entry = ob[i + 1]
            end = min(i + H, NBARS - 1)
            for d in (0, 1):                       # 0 = largo, 1 = corto
                sgn = 1.0 if d == 0 else -1.0
                tp = entry + sgn * tp_atr * a
                sl = entry - sgn * sl_atr * a
                res, r = 0, None
                for j in range(i + 1, end + 1):
                    hit_tp = (hb[j] >= tp) if d == 0 else (lb[j] <= tp)
                    hit_sl = (lb[j] <= sl) if d == 0 else (hb[j] >= sl)
                    if hit_sl:                      # empate -> stop
                        res, r = -1, -sl_atr
                        break
                    if hit_tp:
                        res, r = 1, tp_atr
                        break
                if res == 0:
                    r = sgn * (cb[end] - entry) / a
                lab[b, i, d] = res
                rr[b, i, d] = r
    return lab, rr


# ------------------------------------------------------------------ setups

def causal_pct_flags(x, q, warm=WARMUP):
    """Para cada i>=warm: percentil q de x[0..i-1] (expandiente, causal)."""
    n = x.size
    out = np.full(n, np.nan)
    for i in range(warm, n):
        out[i] = np.percentile(x[:i], q)
    return out


def gen_signals(tape):
    """Devuelve (sig, anti): dict nombre_variante -> lista de (block, i, dir), 0=largo 1=corto.

    `anti` es el CONTROL ESTRUCTURAL: barras con el MISMO patron de PRECIO pero SIN la
    condicion de delta. Es el unico control que aisla la aportacion del delta; el control
    de entrada aleatoria no basta porque las barras extremas tienen mas volatilidad futura
    y por tanto tocan cualquier barrera ATR mas a menudo, en las DOS direcciones.
    """
    sig, anti = {}, {}
    for M in (5, 10, 20):
        sig["DIVERG_M%d" % M] = []
        anti["DIVERG_M%d" % M] = []
    sig["ABSORCION"] = []
    anti["ABSORCION"] = []
    for X in (5, 10, 20, 30):
        sig["CVD_DIV_X%d" % X] = []
        anti["CVD_DIV_X%d" % X] = []
    sig["DELTA_FLIP"] = []
    anti["DELTA_FLIP"] = []

    for b in range(tape.nb):
        h, l, d, v = tape.h[b], tape.l[b], tape.delta[b], tape.vol[b]
        cvd = np.cumsum(d)
        c = tape.c[b]
        ad = np.abs(d)
        p90 = causal_pct_flags(ad, 90.0)
        p25 = causal_pct_flags(h - l, 25.0)
        p75v = causal_pct_flags(v, 75.0)
        rng = h - l

        # 1) DELTA DIVERGENCE. ANTI = mismo extremo de precio, delta NO divergente.
        for M in (5, 10, 20):
            key = "DIVERG_M%d" % M
            for i in range(max(WARMUP, M), NBARS - 1):
                w0, w1 = i - M, i
                if h[i] > h[w0:w1].max():
                    j = w0 + int(np.argmax(h[w0:w1]))
                    (sig if d[i] < d[j] else anti)[key].append((b, i, 1))
                if l[i] < l[w0:w1].min():
                    j = w0 + int(np.argmin(l[w0:w1]))
                    (sig if d[i] > d[j] else anti)[key].append((b, i, 0))

        # 2) ABSORCION: |delta| p>=90 y rango p<=25 -> CONTRARIO al delta.
        #    ANTI = mismo rango estrecho, delta NORMAL (|delta| < p90).
        for i in range(WARMUP, NBARS - 1):
            if rng[i] <= p25[i] and d[i] != 0:
                dirn = 1 if d[i] > 0 else 0
                (sig if ad[i] >= p90[i] else anti)["ABSORCION"].append((b, i, dirn))

        # 3) CVD DIVERGENCE en la TRANSICION. ANTI = misma direccion de precio con el CVD
        #    CONFIRMANDO (no divergiendo).
        for X in (5, 10, 20, 30):
            key = "CVD_DIV_X%d" % X
            prev = {(u, dv): False for u in (True, False) for dv in (True, False)}
            for i in range(max(WARMUP, X), NBARS - 1):
                dp = c[i] - c[i - X]
                dc = cvd[i] - cvd[i - X]
                for u in (True, False):
                    for dv in (True, False):
                        on = (dp != 0 and dc != 0 and (dp > 0) == u
                              and (((dc < 0) if u else (dc > 0)) == dv))
                        if on and not prev[(u, dv)]:
                            (sig if dv else anti)[key].append((b, i, 1 if u else 0))
                        prev[(u, dv)] = on

        # 4) DELTA FLIP: cambio de signo con volumen p>=75 -> a favor del nuevo signo.
        #    ANTI = mismo volumen alto SIN cambio de signo.
        for i in range(WARMUP, NBARS - 1):
            if d[i] == 0 or d[i - 1] == 0 or v[i] < p75v[i]:
                continue
            flip = (d[i] > 0) != (d[i - 1] > 0)
            (sig if flip else anti)["DELTA_FLIP"].append((b, i, 0 if d[i] > 0 else 1))
    return sig, anti


# ------------------------------------------------------------------ control aleatorio

class NullPool(object):
    def __init__(self, tape, rng):
        self.rng = rng
        self.pool = {}
        for b in range(tape.nb):
            s = int(tape.block_sym[b])
            for i in range(WARMUP, NBARS - 1):
                if not (tape.atr[b, i] > 0):
                    continue
                self.pool.setdefault((s, int(tape.hour[i])), []).append((b, i))
        self.pool = {k: np.array(v, dtype=np.int32) for k, v in self.pool.items()}

    def draw(self, strata, k):
        """strata: lista de (sym, hour, dir). Devuelve arrays (b, i, dir)."""
        bb, ii, dd = [], [], []
        for (s, hr, d) in strata:
            p = self.pool.get((s, hr))
            if p is None or len(p) == 0:
                die("estrato vacio sym=%d hora=%d" % (s, hr))
            idx = self.rng.integers(0, len(p), size=k)
            bb.append(p[idx, 0])
            ii.append(p[idx, 1])
            dd.append(np.full(k, d, dtype=np.int32))
        return np.concatenate(bb), np.concatenate(ii), np.concatenate(dd)


# ------------------------------------------------------------------ estudio

def main():
    t0 = dt.datetime.now()
    tape = Tape()
    rng = np.random.default_rng(20260808)

    # --- auditoria del delta contra la clasificacion quote-rule de footprint_core
    audit = {"footprint_cells": None}
    if os.path.exists(CELLS):
        try:
            sys.path.insert(0, HERE)
            import footprint_core as fc
            fp = fc.Footprint(CELLS)
            dq = np.zeros((tape.nb, NBARS))
            covered = np.zeros((tape.nb, NBARS), dtype=bool)
            net = fp.ask_q - fp.bid_q
            for k in range(fp.n_blocks):
                m = fp.cell_block == k
                sym = str(fp.symbols[int(fp.block_sym[k])])
                day = str(fp.days[int(fp.block_day[k])])
                if sym not in tape.syms or day not in tape.days:
                    continue
                bidx = tape.syms.index(sym) * len(tape.days) + tape.days.index(day)
                np.add.at(dq[bidx], fp.cell_min[m], net[m])
                covered[bidx, :] = True
            a = tape.delta.ravel()
            c = dq.ravel()
            # footprint_cells puede cubrir menos símbolos/fechas que delta_bars. Antes
            # de este guard, al añadir NVDA se comparaba contra ceros y la auditoría de
            # signo caía falsamente de 0.91 a 0.10.
            ok = covered.ravel() & np.isfinite(a) & np.isfinite(c)
            corr = float(np.corrcoef(a[ok], c[ok])[0, 1])
            agree = float(np.mean(np.sign(a[ok]) == np.sign(c[ok])))
            audit["footprint_cells"] = {
                "corr_delta_nativo_vs_quoterule": round(corr, 5),
                "acuerdo_de_signo": round(agree, 5),
                "nota": ("delta nativo = side A/B de XNAS.ITCH; quote-rule = clasificacion "
                         "de footprint_core (price vs bid/ask + tick rule); comparación "
                         "restringida a símbolos/fechas presentes en ambos archivos")}
        except Exception as e:                       # auditoria, no camino de señal
            audit["footprint_cells"] = {"error": repr(e)}

    corr_lr = float(np.corrcoef(tape.delta.ravel(), tape.delta_lr.ravel())[0, 1])
    audit["corr_delta_nativo_vs_leeready"] = round(corr_lr, 5)
    audit["pct_volumen_sin_clasificar_N"] = round(
        100.0 * tape.voln.sum() / tape.vol.sum(), 3)

    sys.stderr.write("generando señales...\n")
    sig, anti = gen_signals(tape)
    npool = NullPool(tape, rng)

    sys.stderr.write("etiquetando triple barrera (%d configuraciones)...\n" % len(BARRIERS))
    labels = {}
    for (a, bsl, H) in BARRIERS:
        labels[(a, bsl, H)] = label_all(a, bsl, H, tape)
        sys.stderr.write("  barrera %.1f/%.1f/%d lista\n" % (a, bsl, H))

    # baseline incondicional: entrada aleatoria pura (sin condicionar a nada)
    baselines = {}
    pool_all = np.concatenate([v for v in npool.pool.values()])
    ridx = rng.integers(0, len(pool_all), size=20000)
    rb, ri = pool_all[ridx, 0], pool_all[ridx, 1]
    for cfg in BARRIERS:
        lab, _ = labels[cfg]
        for d in (0, 1):
            baselines["%s|%s" % ("/".join(str(x) for x in cfg), "LARGO" if d == 0 else "CORTO")] = \
                round(float(np.mean(lab[rb, ri, d] == 1)), 5)

    cells = []
    for variant in sorted(sig):
        allsig = sig[variant]
        if not allsig:
            continue
        aa = anti.get(variant, [])
        groups = {"ALL": allsig,
                  "LARGO": [s for s in allsig if s[2] == 0],
                  "CORTO": [s for s in allsig if s[2] == 1]}
        agroups = {"ALL": aa,
                   "LARGO": [s for s in aa if s[2] == 0],
                   "CORTO": [s for s in aa if s[2] == 1]}
        for side, ss in groups.items():
            if not ss:
                continue
            bb = np.array([s[0] for s in ss], dtype=np.int32)
            ii = np.array([s[1] for s in ss], dtype=np.int32)
            dd = np.array([s[2] for s in ss], dtype=np.int32)
            n = len(ss)
            av = agroups[side]
            ab = np.array([s[0] for s in av], dtype=np.int32) if av else np.array([], dtype=np.int32)
            ai = np.array([s[1] for s in av], dtype=np.int32) if av else np.array([], dtype=np.int32)
            ad_ = np.array([s[2] for s in av], dtype=np.int32) if av else np.array([], dtype=np.int32)
            strata = [(int(tape.block_sym[b]), int(tape.hour[i]), int(d))
                      for b, i, d in zip(bb, ii, dd)]
            k = max(K_NULL, int(math.ceil(N_NULL_MIN / float(n))))
            nb_, ni_, nd_ = npool.draw(strata, k)
            for cfg in BARRIERS:
                lab, rr = labels[cfg]
                out = (lab[bb, ii, dd] == 1).astype(np.float64)
                res = lab[bb, ii, dd]
                r = rr[bb, ii, dd]
                nout = (lab[nb_, ni_, nd_] == 1).astype(np.float64)
                nr = rr[nb_, ni_, nd_]
                p = float(out.mean())
                pn = float(nout.mean())
                n_eff, mbar, icc = icc_design_effect(bb, ii, out, cfg[2])
                lo, hi = wilson(p * n_eff, n_eff)
                n_null_eff = float(len(set(zip(nb_.tolist(), ni_.tolist()))))
                pv = two_prop_p(p, n_eff, pn, n_null_eff)
                # diagnostico 1: la MISMA barra operada al REVES. Si ambas direcciones
                # ganan al azar, el "edge" es que la barra extrema toca cualquier barrera.
                opp = float((lab[bb, ii, 1 - dd] == 1).mean())
                # diagnostico 2 (decisivo): control ESTRUCTURAL, mismo patron de precio
                # sin la condicion de delta.
                if ab.size >= 30:
                    aout = (lab[ab, ai, ad_] == 1).astype(np.float64)
                    pa = float(aout.mean())
                    a_eff, _, _ = icc_design_effect(ab, ai, aout, cfg[2])
                    pva = two_prop_p(p, n_eff, pa, a_eff)
                    ar = float(np.nanmean(rr[ab, ai, ad_]))
                else:
                    pa, a_eff, pva, ar = None, None, None, None
                # expectancia en R sobre muestra efectiva
                mr = float(np.nanmean(r))
                sr = float(np.nanstd(r, ddof=1)) if n > 1 else float("nan")
                se = sr / math.sqrt(n_eff) if n_eff > 0 else float("nan")
                cells.append(dict(
                    setup=variant, lado=side,
                    barrera="%.1fATR/%.1fATR/%dm" % cfg,
                    tp_atr=cfg[0], sl_atr=cfg[1], horizonte_barras=cfg[2],
                    n=n, n_eff=round(n_eff, 1), icc=round(icc, 4),
                    solape_medio=round(mbar, 2),
                    win_rate=round(p, 5), null_wr=round(pn, 5),
                    edge_pp=round(100.0 * (p - pn), 3),
                    wilson_lo=round(lo, 5), wilson_hi=round(hi, 5),
                    p_valor=pv, n_null=int(len(nb_)), n_null_eff=int(n_null_eff),
                    pct_objetivo=round(float(np.mean(res == 1)), 4),
                    pct_stop=round(float(np.mean(res == -1)), 4),
                    pct_tiempo=round(float(np.mean(res == 0)), 4),
                    R_medio=round(mr, 4),
                    R_lb95=round(mr - 1.96 * se, 4) if se == se else None,
                    R_medio_null=round(float(np.nanmean(nr)), 4),
                    wr_direccion_opuesta=round(opp, 5),
                    suma_ambas_direcciones=round(p + opp, 5),
                    artefacto_volatilidad=bool(p + opp > 2.0 * pn + 0.02),
                    n_anti=int(ab.size),
                    n_anti_eff=None if a_eff is None else round(a_eff, 1),
                    anti_wr=None if pa is None else round(pa, 5),
                    edge_vs_anti_pp=None if pa is None else round(100.0 * (p - pa), 3),
                    p_valor_anti=pva,
                    R_medio_anti=None if ar is None else round(ar, 4)))

    keep = bh_fdr([c["p_valor"] for c in cells], FDR_Q)
    ai_idx = [i for i, c in enumerate(cells) if c["p_valor_anti"] is not None]
    keep_a = bh_fdr([cells[i]["p_valor_anti"] for i in ai_idx], FDR_Q)
    akeep = {i: k for i, k in zip(ai_idx, keep_a)}
    for i, (c, k) in enumerate(zip(cells, keep)):
        c["fdr_pass"] = bool(k)
        c["fdr_pass_anti"] = bool(akeep.get(i, False))
        if c["n"] < 30:
            c["veredicto"] = "MUESTRA INSUFICIENTE"
        elif not k:
            c["veredicto"] = "NO SEPARA DEL AZAR"
        elif c["edge_pp"] < 0:
            c["veredicto"] = "SEPARA EN CONTRA (edge negativo) -> candidato a VETO"
        elif c["artefacto_volatilidad"]:
            c["veredicto"] = ("ARTEFACTO DE VOLATILIDAD: las DOS direcciones ganan al azar "
                              "(wr+wr_opuesta=%.3f vs 2*null=%.3f); la barra extrema toca "
                              "cualquier barrera, no hay direccion"
                              % (c["suma_ambas_direcciones"], 2 * c["null_wr"]))
        elif c["anti_wr"] is None:
            c["veredicto"] = "SIN CONTROL ESTRUCTURAL (anti n<30) -> NO CONCLUYENTE"
        elif not c["fdr_pass_anti"] or c["edge_vs_anti_pp"] <= 0:
            c["veredicto"] = ("EL DELTA NO APORTA: mismo patron de precio SIN condicion de "
                              "delta da %.4f (vs %.4f); el edge es del PRECIO"
                              % (c["anti_wr"], c["win_rate"]))
        elif c["R_lb95"] is not None and c["R_lb95"] > 0:
            c["veredicto"] = "MEDIDO: SEPARA DEL AZAR, SUPERA AL PATRON DE PRECIO Y PAGA"
        else:
            c["veredicto"] = "SEPARA PERO NO PAGA (expectancia no positiva)"

    cells.sort(key=lambda c: (c["p_valor"], -abs(c["edge_pp"])))
    resumen = {}
    for v in sorted(sig):
        sub = [c for c in cells if c["setup"] == v]
        best = min(sub, key=lambda c: c["p_valor"]) if sub else None
        resumen[v] = {
            "n_señales": len(sig[v]),
            "celdas": len(sub),
            "celdas_fdr_pass": sum(1 for c in sub if c["fdr_pass"]),
            "celdas_medido_rentable": sum(1 for c in sub
                                          if c["veredicto"].startswith("MEDIDO")),
            "mejor_celda": None if best is None else {
                k: best[k] for k in ("lado", "barrera", "n", "n_eff", "win_rate",
                                     "null_wr", "edge_pp", "wilson_lo", "wilson_hi",
                                     "p_valor", "R_medio", "R_lb95", "fdr_pass",
                                     "wr_direccion_opuesta", "artefacto_volatilidad",
                                     "n_anti", "anti_wr", "edge_vs_anti_pp",
                                     "p_valor_anti", "fdr_pass_anti", "veredicto")},
            "n_anti_estructural": len(anti.get(v, []))}

    doc = {
        "generado_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fuente": {
            "tape": "Databento XNAS.ITCH tbbo (RTH 13:30-20:00 UTC)",
            "simbolos": tape.syms, "dias": tape.days, "n_sesiones": tape.nb,
            "barras_1m": int(tape.nb * NBARS),
            "delta": "vol(side=B) - vol(side=A), campo `side` NATIVO del exchange",
            "limitacion": ("XNAS.ITCH es la cinta de Nasdaq SOLAMENTE, no el SIP consolidado. "
                           "El delta medido describe el flujo lit "
                           "de Nasdaq, no el mercado entero. NO extrapolar."),
            "auditoria_clasificacion": audit},
        "metodo": {
            "etiqueta": "triple barrera (objetivo ATR, stop ATR, tiempo en barras)",
            "entrada": "apertura de la barra SIGUIENTE a la señal",
            "empate_tp_y_sl_en_la_misma_barra": "cuenta como STOP (conservador)",
            "atr": "media de True Range de las %d barras 1m previas" % ATR_N,
            "warmup_por_sesion": WARMUP,
            "percentiles": "expandientes y CAUSALES (solo barras cerradas antes de la señal)",
            "control_1_azar": ("entrada aleatoria emparejada por (simbolo, hora del dia, "
                               "direccion), n_null >= %d por celda" % N_NULL_MIN),
            "control_2_estructural": ("MISMO patron de precio SIN la condicion de delta "
                                      "(ANTI). Aisla la aportacion del delta: el control "
                                      "aleatorio no basta porque la barra extrema tiene mas "
                                      "volatilidad futura y toca cualquier barrera ATR."),
            "control_3_direccion_opuesta": ("la misma barra operada al reves. Si wr + "
                                            "wr_opuesta > 2*null, el edge es de TOQUE "
                                            "(volatilidad), no de DIRECCION."),
            "wilson": "95% sobre n EFECTIVO (design effect por solape: 1+(m-1)*ICC)",
            "multiplicidad": "BH-FDR q=%.2f sobre las %d celdas" % (FDR_Q, len(cells)),
            "umbral_publicacion": "n < 30 -> MUESTRA INSUFICIENTE"},
        "baseline_entrada_aleatoria_incondicional": baselines,
        "resumen_por_setup": resumen,
        "celdas": cells}
    atomic_write(OUT_JSON, json.dumps(doc, indent=1))
    sys.stderr.write("OK %d celdas -> %s (%.0fs)\n"
                     % (len(cells), OUT_JSON, (dt.datetime.now() - t0).total_seconds()))


if __name__ == "__main__":
    main()
