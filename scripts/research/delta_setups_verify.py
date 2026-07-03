#!/usr/bin/env python3
"""delta_setups_verify.py — verificacion INDEPENDIENTE de delta_setups_backtest.json.

Reimplementa desde cero (codigo distinto, vectorizado) la triple barrera y dos de los
setups, y contrasta n / win_rate / null_wr contra el JSON ya publicado. Ademas comprueba
la CONVENCION DE SIGNO del delta contra el retorno de la propia barra.

No escribe nada en data/research salvo el informe de verificacion.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RES = os.path.join(REPO, "data", "research")
BARS = os.path.join(RES, "delta_bars_1m.npz")
JSONP = os.path.join(RES, "delta_setups_backtest.json")
OUT = os.path.join(RES, "delta_setups_verify.json")

RTH0 = 13 * 60 + 30
NB = 390
WARM = 60
ATR_N = 30


def die(m):
    sys.stderr.write("FATAL verify: %s\n" % m)
    sys.exit(1)


def load():
    z = np.load(BARS, allow_pickle=False)
    arr, cols = z["bars"], [str(c) for c in z["cols"]]
    syms, days = [str(s) for s in z["syms"]], [str(d) for d in z["days"]]
    ci = {c: i for i, c in enumerate(cols)}
    nb = len(syms) * len(days)
    A = {k: np.full((nb, NB), np.nan) for k in ("o", "h", "l", "c")}
    V = np.zeros((nb, NB))
    D = np.zeros((nb, NB))
    filled = np.zeros((nb, NB), dtype=bool)
    for row in arr:
        b = int(row[ci["sym"]]) * len(days) + int(row[ci["day"]])
        m = int(row[ci["mod"]]) - RTH0
        for k in ("o", "h", "l", "c"):
            A[k][b, m] = row[ci[k]]
        V[b, m] = row[ci["vol"]]
        D[b, m] = row[ci["vol_b"]] - row[ci["vol_a"]]
        filled[b, m] = True
    if not filled.all():
        die("npz incompleto: %d celdas vacias" % int((~filled).sum()))
    return A["o"], A["h"], A["l"], A["c"], V, D, syms, days, nb


def atr_of(h, l, c):
    """Media movil simple de True Range de 30 barras, INCLUYENDO la barra actual."""
    tr = np.empty_like(h)
    tr[:, 0] = h[:, 0] - l[:, 0]
    pc = c[:, :-1]
    tr[:, 1:] = np.maximum(h[:, 1:] - l[:, 1:],
                           np.maximum(np.abs(h[:, 1:] - pc), np.abs(l[:, 1:] - pc)))
    out = np.full_like(h, np.nan)
    ker = np.ones(ATR_N)
    for b in range(h.shape[0]):
        s = np.convolve(tr[b], ker, mode="full")[:NB]
        out[b, ATR_N - 1:] = s[ATR_N - 1:] / ATR_N
    return out


def label_vec(o, h, l, c, atr, tp_a, sl_a, H, d):
    """Triple barrera VECTORIZADA por desplazamiento j (implementacion distinta a la
    del estudio: alli se recorre señal a señal). Devuelve label en {+1,-1,0}.
    Señal en i -> entrada en o[i+1]. Empate objetivo/stop en la misma barra = STOP."""
    nb, n = h.shape
    sgn = 1.0 if d == 0 else -1.0
    entry = np.full((nb, n), np.nan)
    entry[:, :-1] = o[:, 1:]
    tp = entry + sgn * tp_a * atr
    sl = entry - sgn * sl_a * atr
    lab = np.zeros((nb, n), dtype=np.int8)
    done = np.zeros((nb, n), dtype=bool)
    idx = np.arange(n)
    for off in range(1, H + 1):
        j = idx + off
        ok = j <= (n - 1)
        jj = np.where(ok, j, n - 1)
        hj, lj = h[:, jj], l[:, jj]
        if d == 0:
            hit_tp, hit_sl = hj >= tp, lj <= sl
        else:
            hit_tp, hit_sl = lj <= tp, hj >= sl
        live = (~done) & ok[None, :] & np.isfinite(tp)
        s = live & hit_sl
        t = live & (~hit_sl) & hit_tp
        lab[s] = -1
        lab[t] = 1
        done |= (s | t)
    lab[~np.isfinite(entry)] = 0
    return lab, done


def causal_pct(x, q, warm=WARM):
    out = np.full(x.size, np.nan)
    for i in range(warm, x.size):
        out[i] = np.percentile(x[:i], q)
    return out


def sig_diverg(h, l, D, M):
    """nuevo extremo vs las M barras previas + delta menos favorable que en el extremo
    anterior. dir 1 = corto (maximos), dir 0 = largo (minimos)."""
    out = []
    for b in range(h.shape[0]):
        hb, lb, db = h[b], l[b], D[b]
        for i in range(max(WARM, M), NB - 1):
            w = slice(i - M, i)
            if hb[i] > hb[w].max():
                j = i - M + int(np.argmax(hb[w]))
                if db[i] < db[j]:
                    out.append((b, i, 1))
            if lb[i] < lb[w].min():
                j = i - M + int(np.argmin(lb[w]))
                if db[i] > db[j]:
                    out.append((b, i, 0))
    return out


def sig_absorcion(h, l, D):
    """|delta| >= p90 causal y rango <= p25 causal -> CONTRARIO al delta."""
    out = []
    for b in range(h.shape[0]):
        rng = h[b] - l[b]
        ad = np.abs(D[b])
        p90, p25 = causal_pct(ad, 90.0), causal_pct(rng, 25.0)
        for i in range(WARM, NB - 1):
            if rng[i] <= p25[i] and D[b, i] != 0 and ad[i] >= p90[i]:
                out.append((b, i, 1 if D[b, i] > 0 else 0))
    return out


def main():
    o, h, l, c, V, D, syms, days, nb = load()
    atr = atr_of(h, l, c)
    ref = json.load(open(JSONP))
    rep = {"fuente_npz": BARS, "n_bloques": nb, "checks": []}

    def chk(name, mine, theirs, tol, extra=None):
        ok = (theirs is not None) and abs(mine - theirs) <= tol
        rec = {"check": name, "mio": mine, "publicado": theirs, "tol": tol, "ok": bool(ok)}
        if extra:
            rec.update(extra)
        rep["checks"].append(rec)
        print("%-56s mio=%-12s pub=%-12s %s" % (name, round(mine, 5),
              "None" if theirs is None else round(theirs, 5), "OK" if ok else "MISMATCH"))
        return ok

    # ---- 0. convencion de signo del delta: contemporaneo debe ser POSITIVO
    ret = (c - o) / o
    m = np.isfinite(ret)
    r_same = float(np.corrcoef(D[m], ret[m])[0, 1])
    nxt = np.full_like(ret, np.nan)
    nxt[:, :-1] = ret[:, 1:]
    m2 = np.isfinite(nxt)
    r_next = float(np.corrcoef(D[m2], nxt[m2])[0, 1])
    print("corr(delta, retorno MISMA barra)   = %+.4f  (debe ser >0 si el signo es correcto)" % r_same)
    print("corr(delta, retorno barra SIGUIENTE)= %+.4f  (predictivo)" % r_next)
    rep["corr_delta_ret_misma_barra"] = round(r_same, 5)
    rep["corr_delta_ret_barra_siguiente"] = round(r_next, 5)
    if r_same <= 0:
        die("convencion de signo del delta INVERTIDA: corr contemporanea %.4f" % r_same)

    # ---- 1. recuento de señales independiente
    cells = {(x["setup"], x["lado"], x["barrera"]): x for x in ref["celdas"]}
    for M in (5, 10, 20):
        mine = sig_diverg(h, l, D, M)
        chk("n_señales DIVERG_M%d" % M, float(len(mine)),
            float(ref["resumen_por_setup"]["DIVERG_M%d" % M]["n_señales"]), 0.0)
    abso = sig_absorcion(h, l, D)
    chk("n_señales ABSORCION", float(len(abso)),
        float(ref["resumen_por_setup"]["ABSORCION"]["n_señales"]), 0.0)

    # ---- 2. win rate de celdas cabecera, con etiqueta reimplementada
    labs = {}
    for (tp, sl, H) in [(1.5, 1.5, 15), (2.0, 2.0, 15), (2.0, 2.0, 30), (1.5, 1.5, 30)]:
        for d in (0, 1):
            labs[(tp, sl, H, d)] = label_vec(o, h, l, c, atr, tp, sl, H, d)[0]

    def wr_of(sigs, tp, sl, H, lado):
        ss = [s for s in sigs if (lado == "ALL" or (lado == "LARGO") == (s[2] == 0))]
        if not ss:
            return None, 0
        bb = np.array([s[0] for s in ss]); ii = np.array([s[1] for s in ss])
        dd = np.array([s[2] for s in ss])
        w = np.zeros(len(ss))
        for d in (0, 1):
            k = dd == d
            if k.any():
                w[k] = (labs[(tp, sl, H, d)][bb[k], ii[k]] == 1)
        return float(w.mean()), len(ss)

    sig20 = sig_diverg(h, l, D, 20)
    for (lado, tp, sl, H) in [("LARGO", 2.0, 2.0, 15), ("LARGO", 1.5, 1.5, 15),
                              ("LARGO", 2.0, 2.0, 30), ("ALL", 1.5, 1.5, 15)]:
        key = ("DIVERG_M20", lado, "%.1fATR/%.1fATR/%dm" % (tp, sl, H))
        pub = cells.get(key)
        w, n = wr_of(sig20, tp, sl, H, lado)
        chk("DIVERG_M20 %s %s n" % (lado, key[2]), float(n), float(pub["n"]), 0.0)
        chk("DIVERG_M20 %s %s win_rate" % (lado, key[2]), w, pub["win_rate"], 0.004)

    key = ("ABSORCION", "LARGO", "2.0ATR/2.0ATR/30m")
    pub = cells[key]
    w, n = wr_of(abso, 2.0, 2.0, 30, "LARGO")
    chk("ABSORCION LARGO 2.0/2.0/30 n", float(n), float(pub["n"]), 0.0)
    chk("ABSORCION LARGO 2.0/2.0/30 win_rate", w, pub["win_rate"], 0.004)

    # ---- 3. null aleatorio EXACTO (sin Monte Carlo): para cada señal se promedia la
    # etiqueta sobre TODO el estrato (sym, hora, direccion). Es la esperanza del
    # estimador que el estudio aproxima por muestreo, con error de muestreo CERO.
    hour = ((np.arange(NB) + RTH0) // 60).astype(int)
    bsym = np.repeat(np.arange(len(syms)), len(days))
    pool = {}
    for b in range(nb):
        for i in range(WARM, NB - 1):
            if atr[b, i] > 0:
                pool.setdefault((int(bsym[b]), int(hour[i])), []).append((b, i))
    pool = {k: np.array(v) for k, v in pool.items()}
    rep["estratos_null"] = {"n_estratos": len(pool),
                            "tam_medio": round(float(np.mean([len(v) for v in pool.values()])), 1)}

    def null_exact(sigs, tp, sl, H, lado):
        ss = [s for s in sigs if (lado == "ALL" or (lado == "LARGO") == (s[2] == 0))]
        per = [float((labs[(tp, sl, H, d)][pool[(int(bsym[b]), int(hour[i]))][:, 0],
                                           pool[(int(bsym[b]), int(hour[i]))][:, 1]] == 1).mean())
               for (b, i, d) in ss]
        return float(np.mean(per)), len(ss)

    # el error de Monte Carlo del null del estudio (k=25 replicas) se mide aparte: con
    # pocos estratos (12) y pocas señales el null muestreado tiene sd de ~0,7 pp.
    for (setup, sigs, lado, tp, sl, H, mc_sd) in [
            ("DIVERG_M20", sig20, "LARGO", 2.0, 2.0, 15, 0.0034),
            ("ABSORCION", abso, "LARGO", 2.0, 2.0, 30, 0.0073)]:
        pub = cells[(setup, lado, "%.1fATR/%.1fATR/%dm" % (tp, sl, H))]
        nw, nn = null_exact(sigs, tp, sl, H, lado)
        chk("%s %s null EXACTO vs publicado (mc_sd=%.4f)" % (setup, lado, mc_sd), nw,
            pub["null_wr"], 3.0 * mc_sd,
            {"edge_pp_recalculado": round(100.0 * (pub["win_rate"] - nw), 3),
             "edge_pp_publicado": pub["edge_pp"]})

    # ---- 4. el diagnostico decisivo: direccion opuesta sobre las MISMAS barras
    for (setup, sigs, lado, tp, sl, H) in [("DIVERG_M20", sig20, "LARGO", 2.0, 2.0, 15),
                                           ("ABSORCION", abso, "LARGO", 2.0, 2.0, 30)]:
        ss = [s for s in sigs if (s[2] == 0)]
        bb = np.array([s[0] for s in ss]); ii = np.array([s[1] for s in ss])
        wr_l = float((labs[(tp, sl, H, 0)][bb, ii] == 1).mean())
        wr_s = float((labs[(tp, sl, H, 1)][bb, ii] == 1).mean())
        pub = cells[(setup, lado, "%.1fATR/%.1fATR/%dm" % (tp, sl, H))]
        chk("%s %s wr_direccion_opuesta" % (setup, lado), wr_s,
            pub["wr_direccion_opuesta"], 0.004,
            {"wr_a_favor": round(wr_l, 5), "suma": round(wr_l + wr_s, 5),
             "2x_null": round(2 * pub["null_wr"], 5)})

    # ---- 5. el delta, ¿predice algo por si mismo? test AGRUPADO POR SESION (las barras
    # de un mismo dia estan correlacionadas: el t de 15.560 barras sueltas mentiria).
    per_ses = []
    for b in range(nb):
        x, y = D[b, WARM:NB - 1], nxt[b, WARM:NB - 1]
        g = np.isfinite(x) & np.isfinite(y)
        if g.sum() > 30 and x[g].std() > 0 and y[g].std() > 0:
            per_ses.append(float(np.corrcoef(x[g], y[g])[0, 1]))
    per_ses = np.array(per_ses)
    mu, sd = float(per_ses.mean()), float(per_ses.std(ddof=1))
    t = mu / (sd / np.sqrt(len(per_ses)))
    rep["delta_predice_barra_siguiente"] = {
        "corr_media_por_sesion": round(mu, 5),
        "sd_entre_sesiones": round(sd, 5), "n_sesiones": int(len(per_ses)),
        "t_agrupado": round(float(t), 3),
        "R2_implicito_pct": round(100.0 * mu * mu, 4),
        "corr_misma_barra_pooled": round(r_same, 5),
        "R2_misma_barra_pct": round(100.0 * r_same * r_same, 3),
        "nota": ("contemporaneo vs predictivo: el delta explica el pasado inmediato y "
                 "casi nada del futuro, igual que la literatura OFI (Cont et al.)")}
    print("delta->barra siguiente: corr media por sesion %+.4f (sd %.4f, n=%d) t=%+.2f R2=%.3f%%"
          % (mu, sd, len(per_ses), t, 100.0 * mu * mu))

    ok = all(x["ok"] for x in rep["checks"])
    rep["verificacion_global"] = "OK" if ok else "MISMATCH"
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, indent=1)
    os.replace(tmp, OUT)
    print("\nVERIFICACION GLOBAL: %s  (%d checks) -> %s"
          % (rep["verificacion_global"], len(rep["checks"]), OUT))
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
