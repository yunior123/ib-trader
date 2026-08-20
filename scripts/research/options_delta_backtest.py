#!/usr/bin/env python3
"""options_delta_backtest.py — DELTA IMBALANCE DE OPCIONES (UW) medido de verdad.

LOTE FUERA DE SESION (CLAUDE.md autoriza Python aqui). Metodo obligatorio de la casa
(skill measured-probability + skill drift-confound):
  - triple barrera (TP/SL en ATR, tiempo) con timeout = NULL, jamas retorno a horizonte fijo
  - entrada al OPEN del minuto SIGUIENTE al de la señal -> cero look-ahead
  - DOS nulls: A = direccion aleatoria (azar puro), B = MISMA direccion y misma hora
    (controla la deriva del periodo; el null A solo no basta, skill drift-confound)
  - Wilson 95% sobre la n EFECTIVA (clusters sym x dia, rho medido 0.412)
  - BH-FDR q=0.10 sobre TODAS las celdas del barrido

Diferencia con scripts/delta_imbalance_study.py (ya existente): alli el z usa la sigma de
los DIAS PREVIOS; aqui el z es contra la VENTANA MOVIL DE LA SESION (mu y sigma de los W
minutos ANTERIORES del mismo sym-dia). Es otra señal, no una reejecucion.

Entrada : data/research/delta_imbalance.npz   (scripts/delta_imbalance_prep.py)
Salidas : data/research/options_delta_backtest.json
          data/research/options_delta_backtest.md
"""
import json
import math
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import delta_imbalance_study as dis          # noqa: E402  (wilson, bh_fdr, Panel, ATR...)

NPZ = "data/research/delta_imbalance.npz"
OUT_JSON = "data/research/options_delta_backtest.json"
OUT_MD = "data/research/options_delta_backtest.md"

# ---- rejilla del barrido -----------------------------------------------------
SIGFIELDS = {"dd": "dir_delta_flow", "otm": "otm_dir_delta_flow"}
WINDOWS = (30, 60)                    # ventana movil intrasesion para mu/sigma
THETAS = (1.5, 2.0, 2.5, 3.0)         # umbral de z pedido
MODES = ("sigue", "fade")
K_TP = (1.0, 1.5)
K_SL = (1.0,)
HORIZONS = (15, 30, 60)
ATR_N = 14
MIN_ET, MAX_ET = 585, 940             # 09:45 - 15:40 ET (doctrina de horarios)
RHO = dis.RHO_DEFAULT                 # 0.412 medido en la flota
MIN_CLUSTERS = 40
MIN_N = 100
NULL_MIN = 500                        # exigencia del brief para el control aleatorio
BOOT_N = 1000                         # remuestreos del bootstrap por bloques
BOOT_BLOCK = 30

# ---- capitanes (CLAUDE.md regla 12) -----------------------------------------
CAP_MKT = ("SPY", "QQQ")
CAP_SEMIS = "SMH"
TROPA_SEMIS = {"MU", "SKHY", "DRAM", "SNDK", "WDC", "STX", "LRCX", "NVDA", "AMD",
               "TSM", "ASML", "AVGO", "TXN", "QCOM", "INTC"}
CAP_ALL = set(CAP_MKT) | {CAP_SEMIS}
CAP_Z_MIN = 1.0                       # el capitan solo "esta vigente" si su z supera esto
CAP_W = 5                             # suma de 5 min del capitan (flujo, no ruido de 1 min)


# ------------------------------------------------------------------ numerica

def block_pos(new_block, n):
    starts = np.nonzero(new_block)[0]
    return np.arange(n) - np.repeat(starts, np.diff(np.append(starts, n)))


def rolling_sum_prior_ok(x, pos, w):
    """Suma movil de w minutos TERMINADA EN t (incluye t). NaN si no caben w barras."""
    cs = np.concatenate(([0.0], np.cumsum(x)))
    idx = np.arange(x.size)
    out = np.full(x.size, np.nan)
    ok = pos >= (w - 1)
    out[ok] = cs[idx[ok] + 1] - cs[idx[ok] + 1 - w]
    return out


def rolling_z_prior(x, pos, w):
    """z_t = (x_t - mu) / sd con mu,sd de x[t-w .. t-1] del MISMO bloque.

    Solo datos CERRADOS anteriores al minuto t: no hay look-ahead ni auto-inflado de sigma.
    NaN si no hay w minutos previos o si sd == 0."""
    cs = np.concatenate(([0.0], np.cumsum(x)))
    cs2 = np.concatenate(([0.0], np.cumsum(x * x)))
    idx = np.arange(x.size)
    z = np.full(x.size, np.nan)
    ok = pos >= w
    i = idx[ok]
    s1 = cs[i] - cs[i - w]
    s2 = cs2[i] - cs2[i - w]
    mu = s1 / w
    var = s2 / w - mu * mu
    sd = np.sqrt(np.maximum(var, 0.0))
    good = sd > 0
    zz = np.full(i.size, np.nan)
    zz[good] = (x[i][good] - mu[good]) / sd[good]
    z[i] = zz
    return z


# ------------------------------------------------------------------ etiquetado

def triple_barrier_next_open(p, sig_idx, direction, atr, k_tp, k_sl, H):
    """Señal en la barra CERRADA sig_idx -> entrada al OPEN de sig_idx+1.

    1 = TP primero, 0 = SL primero, -1 = timeout / fin de sesion (NULL, fuera del
    denominador). Barra que toca TP y SL en el mismo minuto -> SL (conservador)."""
    n = sig_idx.size
    e = sig_idx + 1
    entry = p.o[e]
    a = atr[sig_idx]                       # ATR conocido en el momento de la señal
    tp = entry + direction * k_tp * a
    sl = entry - direction * k_sl * a
    res = np.full(n, -1, dtype=np.int8)
    amb = np.zeros(n, dtype=bool)
    live = np.ones(n, dtype=bool)
    blk = p.block_id[e]
    last = p.sym.size - 1
    for j in range(0, H):
        k = np.minimum(e + j, last)
        same = (p.block_id[k] == blk) & (e + j <= last)
        active = live & same
        if not active.any():
            break
        hi, lo = p.h[k], p.l[k]
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
        live &= same
        if not live.any():
            break
    return res, amb


# ------------------------------------------------------------------ nulls

def build_pool(p, pool_ok):
    """Candidatos del null agrupados por (sym, bucket de 30 min). Se calcula UNA vez."""
    key = p.sym.astype(np.int64) * 1000 + (p.minute_et // 30)
    pool = {}
    valid = np.nonzero(pool_ok)[0]
    kv = key[valid]
    order = np.argsort(kv, kind="stable")
    kv, valid = kv[order], valid[order]
    bounds = np.nonzero(np.concatenate(([True], kv[1:] != kv[:-1])))[0]
    for s, e in zip(bounds, np.append(bounds[1:], kv.size)):
        pool[int(kv[s])] = valid[s:e]
    return key, pool


def null_random_dir(key, pool, sig_idx, seed):
    """NULL A: mismo reparto (sym, bucket de 30 min), direccion 50/50 al azar."""
    rng = np.random.default_rng(seed)
    out_i, out_d = [], []
    ks, cnts = np.unique(key[sig_idx], return_counts=True)
    for k, c in zip(ks, cnts):
        cand = pool.get(int(k))
        if cand is None or cand.size == 0:
            continue
        out_i.append(rng.choice(cand, size=int(c), replace=cand.size < c))
        out_d.append(rng.choice(np.array([-1, 1], dtype=np.int8), size=int(c)))
    if not out_i:
        return np.zeros(0, np.int64), np.zeros(0, np.int8)
    return np.concatenate(out_i), np.concatenate(out_d).astype(np.int8)


def null_matched_dir(key, pool, sig_idx, direc, seed):
    """NULL B (el estricto): mismo reparto (sym, bucket, DIRECCION) que la señal, pero en
    minutos al azar. Absorbe la deriva del periodo y el sesgo largo/corto de la señal."""
    rng = np.random.default_rng(seed)
    out_i, out_d = [], []
    for d in (-1, 1):
        m = direc == d
        if not m.any():
            continue
        ks, cnts = np.unique(key[sig_idx[m]], return_counts=True)
        for k, c in zip(ks, cnts):
            cand = pool.get(int(k))
            if cand is None or cand.size == 0:
                continue
            out_i.append(rng.choice(cand, size=int(c), replace=cand.size < c))
            out_d.append(np.full(int(c), d, dtype=np.int8))
    if not out_i:
        return np.zeros(0, np.int64), np.zeros(0, np.int8)
    return np.concatenate(out_i), np.concatenate(out_d).astype(np.int8)


# ------------------------------------------------------------------ capitanes

def captain_states(p, pos):
    """Estado {-1,0,+1} de cada capitan por MINUTO ABSOLUTO (ts), alineado a todo el panel.

    Capitan vigente <=> |z de su suma de 5 min de dir_delta_flow| >= CAP_Z_MIN, con z de
    ventana movil de 30 min previos (mismo criterio no-look-ahead que la señal)."""
    dd5 = rolling_sum_prior_ok(p.dir_delta_flow, pos, CAP_W)
    dd5 = np.nan_to_num(dd5, nan=0.0)
    z5 = rolling_z_prior(dd5, pos, 30)
    z5[pos < 30 + CAP_W] = np.nan          # los ceros del calentamiento no entran en mu/sd
    ts_sorted = np.unique(p.ts)
    states = {}
    zmap = {}
    for name in list(CAP_MKT) + [CAP_SEMIS]:
        if name not in p.symbols:
            states[name] = None
            continue
        si = p.symbols.index(name)
        m = p.sym == si
        zz = np.full(ts_sorted.size, np.nan)
        loc = np.searchsorted(ts_sorted, p.ts[m])
        zz[loc] = z5[m]
        zmap[name] = zz
        st = np.zeros(ts_sorted.size, dtype=np.int8)
        fin = np.isfinite(zz)
        st[fin & (zz >= CAP_Z_MIN)] = 1
        st[fin & (zz <= -CAP_Z_MIN)] = -1
        states[name] = st
    # mercado = SPY + QQQ combinados: suma de z / sqrt(k) con k = capitanes con dato
    mkt = np.zeros(ts_sorted.size, dtype=np.int8)
    have = [zmap[nm] for nm in CAP_MKT if nm in zmap]
    if have:
        stack = np.vstack(have)
        fin = np.isfinite(stack)
        k = fin.sum(axis=0)
        s = np.where(fin, stack, 0.0).sum(axis=0)
        zs = np.divide(s, np.sqrt(np.maximum(k, 1)), out=np.zeros_like(s), where=k > 0)
        mkt[(k > 0) & (zs >= CAP_Z_MIN)] = 1
        mkt[(k > 0) & (zs <= -CAP_Z_MIN)] = -1
    return ts_sorted, mkt, states.get(CAP_SEMIS, np.zeros(ts_sorted.size, np.int8))


def captain_veto(p, ts_sorted, mkt, smh, idx, direc):
    """True donde la doctrina ANULA la señal del nombre (capitan opuesto vigente).

    Los propios capitanes (SPY/QQQ/SMH) quedan fuera del filtro: no se anulan a si mismos."""
    loc = np.searchsorted(ts_sorted, p.ts[idx])
    m = mkt[loc]
    s = smh[loc]
    names = np.array(p.symbols)
    sym_name = names[p.sym[idx]]
    is_cap = np.isin(sym_name, list(CAP_ALL))
    is_tropa = np.isin(sym_name, list(TROPA_SEMIS))
    veto = (m == -direc)
    veto |= is_tropa & (s == -direc)
    veto &= ~is_cap
    return veto, is_cap


# ------------------------------------------------------------------ celdas

def score(labels, clusters_of):
    keep = labels >= 0
    n = int(keep.sum())
    if n == 0:
        return None
    wins = int((labels[keep] == 1).sum())
    clu = int(np.unique(clusters_of[keep]).size)
    n_eff = dis.effective_n(n, clu, RHO)
    wr, lo, hi = dis.wilson(wins, max(1.0, n_eff), p=wins / n)
    return dict(n=n, wins=wins, wr=wr, wr_lo=lo, wr_hi=hi, clusters=clu,
                n_eff=round(float(n_eff), 1), timeouts=int((labels < 0).sum()))


def main():
    t0 = time.time()
    p = dis.Panel(NPZ)
    n = p.sym.size
    pos = block_pos(p.new_block, n)
    print("panel: %d minutos | %d syms | %d dias (%s -> %s) | %d bloques sym-dia"
          % (n, len(p.symbols), len(p.days), p.days[0], p.days[-1], p.n_blocks))

    atr = dis.atr_wilder(p, ATR_N)
    pool_ok = (np.isfinite(atr) & (atr > 0) & (p.minute_et >= MIN_ET) & (p.minute_et < MAX_ET))
    # la entrada es al open de t+1: exige que t+1 exista y sea del mismo bloque
    nxt_ok = np.zeros(n, dtype=bool)
    nxt_ok[:-1] = p.block_id[1:] == p.block_id[:-1]
    pool_ok &= nxt_ok
    print("pool valido (ATR + horario + t+1 mismo dia): %d minutos" % int(pool_ok.sum()))

    key, pool = build_pool(p, pool_ok)
    ts_sorted, mkt, smh = captain_states(p, pos)
    print("capitan mercado vigente en %.1f%% de los minutos; SMH en %.1f%%"
          % (100.0 * (mkt != 0).mean(), 100.0 * (smh != 0).mean()))

    zcache = {}
    for tag, field in SIGFIELDS.items():
        x = getattr(p, field)
        for w in WINDOWS:
            zcache[(tag, w)] = rolling_z_prior(x, pos, w)

    cells = []
    for tag in SIGFIELDS:
        for w in WINDOWS:
            z = zcache[(tag, w)]
            for theta in THETAS:
                fire = pool_ok & np.isfinite(z) & (np.abs(z) >= theta)
                idx = np.nonzero(fire)[0]
                if idx.size < MIN_N:
                    print("  %s z%d th=%.1f -> %d entradas (pocas, saltada)"
                          % (tag, w, theta, idx.size))
                    continue
                base_dir = np.sign(z[idx]).astype(np.int8)
                veto, is_cap = captain_veto(p, ts_sorted, mkt, smh, idx, base_dir)
                seed0 = abs(hash((tag, w, theta))) % (2 ** 31)
                nA_i, nA_d = null_random_dir(key, pool, idx, seed0)
                print("  %-4s z%-2d th=%.1f -> %6d entradas | capitan veta %5.1f%% | null A %d"
                      % (tag, w, theta, idx.size, 100.0 * veto.mean(), nA_i.size))
                for mode in MODES:
                    direc = base_dir if mode == "sigue" else (-base_dir).astype(np.int8)
                    nB_i, nB_d = null_matched_dir(key, pool, idx, direc, seed0 + 7)
                    for k_tp in K_TP:
                        for k_sl in K_SL:
                            for H in HORIZONS:
                                lab, amb = triple_barrier_next_open(p, idx, direc, atr,
                                                                    k_tp, k_sl, H)
                                labA, _ = triple_barrier_next_open(p, nA_i, nA_d, atr,
                                                                   k_tp, k_sl, H)
                                labB, _ = triple_barrier_next_open(p, nB_i, nB_d, atr,
                                                                   k_tp, k_sl, H)
                                cl = p.block_id[idx]
                                s = score(lab, cl)
                                sA = score(labA, p.block_id[nA_i])
                                sB = score(labB, p.block_id[nB_i])
                                if s is None or sA is None or sB is None:
                                    continue
                                if s["n"] < MIN_N or sA["n"] < NULL_MIN or sB["n"] < NULL_MIN:
                                    continue
                                # split por capitan
                                sk = score(lab[~veto], cl[~veto]) if (~veto).any() else None
                                sv = score(lab[veto], cl[veto]) if veto.any() else None
                                pcap = (dis.two_prop_p(sk["wins"], sk["n"], sv["wins"], sv["n"])
                                        if (sk and sv) else None)
                                ex = lambda q: q * k_tp - (1 - q) * k_sl
                                bootB = dis.block_bootstrap_edge(
                                    (lab[lab >= 0] == 1).astype(float),
                                    (labB[labB >= 0] == 1).astype(float),
                                    n_boot=BOOT_N, block=BOOT_BLOCK)
                                cells.append(dict(
                                    sig=tag, zwin=w, theta=theta, mode=mode,
                                    k_tp=k_tp, k_sl=k_sl, H=H,
                                    n=s["n"], wins=s["wins"], wr=s["wr"],
                                    wr_lo=s["wr_lo"], wr_hi=s["wr_hi"],
                                    clusters=s["clusters"], n_eff=s["n_eff"],
                                    timeouts=s["timeouts"],
                                    timeout_frac=round(s["timeouts"] /
                                                       float(s["timeouts"] + s["n"]), 4),
                                    ambig=round(float(amb.mean()), 4),
                                    exp=ex(s["wr"]), exp_lo=ex(s["wr_lo"]),
                                    nullA_wr=sA["wr"], nullA_n=sA["n"],
                                    nullB_wr=sB["wr"], nullB_n=sB["n"],
                                    edge_vs_A=s["wr"] - sA["wr"],
                                    edge_vs_B=s["wr"] - sB["wr"],
                                    edge_lo=bootB["lo"] if bootB else None,
                                    edge_hi=bootB["hi"] if bootB else None,
                                    p_vs_A=dis.two_prop_p(s["wins"], s["n"],
                                                          sA["wins"], sA["n"]),
                                    p=dis.two_prop_p(s["wins"], s["n"], sB["wins"], sB["n"]),
                                    cap_keep_n=sk["n"] if sk else None,
                                    cap_keep_wr=sk["wr"] if sk else None,
                                    cap_keep_neff=sk["n_eff"] if sk else None,
                                    cap_veto_n=sv["n"] if sv else None,
                                    cap_veto_wr=sv["wr"] if sv else None,
                                    cap_veto_neff=sv["n_eff"] if sv else None,
                                    cap_delta=(sk["wr"] - sv["wr"]) if (sk and sv) else None,
                                    cap_p=pcap))
    if not cells:
        res = {"veredicto": "DATA-INSUFFICIENT", "n_cells": 0}
        write_atomic(OUT_JSON, json.dumps(res, indent=1))
        print("SIN CELDAS")
        return res

    keep = dis.bh_fdr([c["p"] for c in cells], q=0.10)
    for c, k in zip(cells, keep):
        c["fdr_pass"] = bool(k)
        c["veredicto"] = verdict(c)

    # test agregado del filtro CAPITAN (una sola prueba, sobre la celda de referencia)
    cap = captain_summary(cells)

    cells.sort(key=lambda c: (-(c["exp_lo"]), -c["n_eff"]))
    res = dict(
        generado=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        panel=dict(minutos=int(n), syms=len(p.symbols), dias=len(p.days),
                   desde=p.days[0], hasta=p.days[-1], bloques=int(p.n_blocks),
                   symbols=list(p.symbols)),
        metodo=dict(entrada="open del minuto t+1 (señal en la barra cerrada t)",
                    barrera="triple: TP=k_tp*ATR14(1m), SL=k_sl*ATR, tiempo=H min; "
                            "timeout=NULL fuera del denominador",
                    z="ventana movil intrasesion: mu,sd de los W minutos ANTERIORES "
                      "del mismo sym-dia",
                    nullA="entradas al azar, mismo (sym, bucket 30min), direccion 50/50",
                    nullB="entradas al azar, mismo (sym, bucket 30min) y MISMA direccion "
                          "(controla la deriva del periodo)",
                    wilson="95%% sobre n_eff = n/(1+(k-1)rho), rho=%.3f, topada por clusters"
                           % RHO,
                    fdr="BH q=0.10 sobre las %d celdas, p contra NULL B" % len(cells),
                    horario="09:45-15:40 ET"),
        n_cells=len(cells), fdr_pass=int(keep.sum()), rho=RHO,
        capitan=cap, cells=cells)
    write_atomic(OUT_JSON, json.dumps(res, indent=1))
    print_table(res)
    write_md(res)
    print("\n%.1fs -> %s + %s" % (time.time() - t0, OUT_JSON, OUT_MD))
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


REF = dict(sig="dd", zwin=30, theta=2.0, mode="sigue", k_tp=1.0, k_sl=1.0, H=30)


def captain_summary(cells):
    """¿El veto del capitan separa, o es folklore?

    Tres lecturas: (1) UNA celda de referencia con estadistica limpia y n independiente,
    (2) consistencia del SIGNO en todas las celdas (test de signos, descriptivo porque las
    celdas se solapan), (3) agregado por theta, tambien descriptivo."""
    ref = None
    for c in cells:
        if all(c[k] == v for k, v in REF.items()) and c["cap_keep_n"]:
            kw = round(c["cap_keep_wr"] * c["cap_keep_n"])
            vw = round(c["cap_veto_wr"] * c["cap_veto_n"])
            _, klo, khi = dis.wilson(kw, max(1.0, c["cap_keep_neff"]), p=c["cap_keep_wr"])
            _, vlo, vhi = dis.wilson(vw, max(1.0, c["cap_veto_neff"]), p=c["cap_veto_wr"])
            ref = dict(celda={k: c[k] for k in REF},
                       keep_n=c["cap_keep_n"], keep_neff=c["cap_keep_neff"],
                       keep_wr=c["cap_keep_wr"], keep_lo=klo, keep_hi=khi,
                       veto_n=c["cap_veto_n"], veto_neff=c["cap_veto_neff"],
                       veto_wr=c["cap_veto_wr"], veto_lo=vlo, veto_hi=vhi,
                       delta_pp=100.0 * (c["cap_keep_wr"] - c["cap_veto_wr"]),
                       p=c["cap_p"],
                       nota="p de dos proporciones sobre la n CRUDA; con n_eff (clusters "
                            "sym-dia) el intervalo es el de arriba y se solapan")
            break
    pos = sum(1 for c in cells if c["cap_delta"] is not None and c["cap_delta"] > 0)
    neg = sum(1 for c in cells if c["cap_delta"] is not None and c["cap_delta"] < 0)
    kw = kn = vw = vn = 0
    per_theta = {}
    for c in cells:
        if c["cap_keep_n"] is None or c["cap_veto_n"] is None:
            continue
        kw += round(c["cap_keep_wr"] * c["cap_keep_n"])
        kn += c["cap_keep_n"]
        vw += round(c["cap_veto_wr"] * c["cap_veto_n"])
        vn += c["cap_veto_n"]
        d = per_theta.setdefault(c["theta"], [0, 0, 0, 0])
        d[0] += round(c["cap_keep_wr"] * c["cap_keep_n"]); d[1] += c["cap_keep_n"]
        d[2] += round(c["cap_veto_wr"] * c["cap_veto_n"]); d[3] += c["cap_veto_n"]
    if kn == 0 or vn == 0:
        return {"nota": "sin split capitan"}
    out = dict(
        referencia=ref,
        celdas_filtro_mejora=pos, celdas_filtro_empeora=neg,
        aviso="agregado sobre celdas SOLAPADAS (mismas entradas con distintas barreras): "
              "la n de aqui NO es independiente, sirve para el SIGNO y el orden de "
              "magnitud, no para el intervalo",
        keep_n=int(kn), keep_wr=kw / kn, veto_n=int(vn), veto_wr=vw / vn,
        delta_pp=100.0 * (kw / kn - vw / vn),
        p_naive=dis.two_prop_p(kw, kn, vw, vn),
        por_theta={str(k): dict(keep_wr=v[0] / v[1] if v[1] else None, keep_n=v[1],
                                veto_wr=v[2] / v[3] if v[3] else None, veto_n=v[3],
                                delta_pp=100.0 * ((v[0] / v[1]) - (v[2] / v[3]))
                                if v[1] and v[3] else None)
                   for k, v in sorted(per_theta.items())})
    return out


def print_table(res):
    print("\n%-4s %-3s %-4s %-5s %4s %3s | %7s %7s %4s | %6s %6s | %6s %6s | %8s | %s"
          % ("sig", "zw", "th", "modo", "ktp", "H", "n", "n_eff", "clu",
             "wr", "wr_lo", "nullB", "edge", "p", "veredicto"))
    for c in res["cells"][:25]:
        print("%-4s %-3d %-4.1f %-5s %4.2f %3d | %7d %7.1f %4d | %6.4f %6.4f | %6.4f %+6.4f | %8.2g | %s"
              % (c["sig"], c["zwin"], c["theta"], c["mode"], c["k_tp"], c["H"],
                 c["n"], c["n_eff"], c["clusters"], c["wr"], c["wr_lo"],
                 c["nullB_wr"], c["edge_vs_B"], c["p"], c["veredicto"]))
    print("\nceldas=%d  pasan BH-FDR(q=0.10)=%d" % (res["n_cells"], res["fdr_pass"]))
    cap = res["capitan"]
    if "keep_n" in cap:
        print("CAPITAN: sin veto wr=%.4f (n=%d) | vetadas wr=%.4f (n=%d) | delta=%+.2f pp"
              % (cap["keep_wr"], cap["keep_n"], cap["veto_wr"], cap["veto_n"],
                 cap["delta_pp"]))


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def best_by(cells, **flt):
    sub = [c for c in cells if all(c[k] == v for k, v in flt.items())]
    if not sub:
        return None
    return max(sub, key=lambda c: c["edge_vs_B"])


def write_md(res):
    c = res["cells"]
    pan = res["panel"]
    L = []
    L.append("# Delta imbalance de OPCIONES (UW) — medicion\n")
    L.append("Generado %s · `scripts/research/options_delta_backtest.py`\n" % res["generado"])
    L.append("## Muestra\n")
    L.append("- %d minutos, %d simbolos, **%d sesiones** (%s -> %s), %d bloques sym-dia."
             % (pan["minutos"], pan["syms"], pan["dias"], pan["desde"], pan["hasta"],
                pan["bloques"]))
    L.append("- %d sesiones >= 30 => el resultado ES medido, no indicativo." % pan["dias"])
    L.append("- Lo que NO entra y por que: el archivo UW tiene 2607 ficheros en 94 dias "
             "(2026-03-24 -> 2026-08-07), pero `poly_bars` se queda en la barra del "
             "2026-07-24. Se pierden **195 ficheros de 9 sesiones** (07-25 -> 08-07) por "
             "falta de barras 1m, no por falta de flujo. De los 2412 ficheros con dia "
             "utilizable entran 2407 bloques: solo 5 se caen. Refrescar `poly_bars` "
             "añadiria ~11% de muestra.\n")
    L.append("## Metodo\n")
    for k, v in res["metodo"].items():
        L.append("- **%s**: %s" % (k, v))
    L.append("")
    L.append("## Resultado\n")
    L.append("- Celdas barridas: **%d**. Pasan BH-FDR q=0.10 contra el null de misma "
             "direccion: **%d**." % (res["n_cells"], res["fdr_pass"]))
    proven = [x for x in c if x["veredicto"] == "PROVEN"]
    L.append("- Celdas PROVEN (FDR + Wilson-LB de expectancia > 0 + edge_lo > 0): **%d**.\n"
             % len(proven))
    L.append("### Top 15 por Wilson-LB de la expectancia\n")
    L.append("| sig | zwin | theta | modo | ktp/ksl | H | n | n_eff | clu | wr | wr_lo | "
             "nullA | nullB | edge vs B | p | veredicto |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for x in c[:15]:
        L.append("| %s | %d | %.1f | %s | %.2f/%.2f | %d | %d | %.0f | %d | %.4f | %.4f | "
                 "%.4f | %.4f | %+.4f | %.2g | %s |"
                 % (x["sig"], x["zwin"], x["theta"], x["mode"], x["k_tp"], x["k_sl"],
                    x["H"], x["n"], x["n_eff"], x["clusters"], x["wr"], x["wr_lo"],
                    x["nullA_wr"], x["nullB_wr"], x["edge_vs_B"], x["p"], x["veredicto"]))
    L.append("")
    L.append("### OTM vs TOTAL (mejor celda de cada familia por edge vs null B)\n")
    L.append("| familia | sig | zwin | theta | modo | H | n | wr | nullB | edge vs B | p |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for tag, name in (("dd", "TOTAL dir_delta_flow"), ("otm", "OTM otm_dir_delta_flow")):
        b = best_by(c, sig=tag)
        if b:
            L.append("| %s | %s | %d | %.1f | %s | %d | %d | %.4f | %.4f | %+.4f | %.2g |"
                     % (name, b["sig"], b["zwin"], b["theta"], b["mode"], b["H"],
                        b["n"], b["wr"], b["nullB_wr"], b["edge_vs_B"], b["p"]))
    L.append("")
    L.append("### Filtro CAPITAN (CLAUDE.md regla 12)\n")
    cap = res["capitan"]
    if "keep_n" in cap:
        r = cap.get("referencia")
        if r:
            L.append("**Celda de referencia** (%s, la unica lectura con n independiente):\n"
                     % ", ".join("%s=%s" % kv for kv in r["celda"].items()))
            L.append("| subconjunto | n | n_eff | wr | Wilson 95% (n_eff) |")
            L.append("|---|---|---|---|---|")
            L.append("| señal NO vetada | %d | %.0f | %.4f | [%.4f, %.4f] |"
                     % (r["keep_n"], r["keep_neff"], r["keep_wr"], r["keep_lo"], r["keep_hi"]))
            L.append("| señal VETADA por capitan | %d | %.0f | %.4f | [%.4f, %.4f] |"
                     % (r["veto_n"], r["veto_neff"], r["veto_wr"], r["veto_lo"], r["veto_hi"]))
            L.append("")
            L.append("- Diferencia %+.2f pp, p=%.2g. %s\n"
                     % (r["delta_pp"], r["p"], r["nota"]))
        L.append("- Consistencia del signo: el filtro MEJORA en %d celdas y EMPEORA en %d "
                 "de %d.\n" % (cap["celdas_filtro_mejora"], cap["celdas_filtro_empeora"],
                               res["n_cells"]))
        L.append("- %s\n" % cap["aviso"])
        L.append("- Señales **NO vetadas** por el capitan: wr %.4f (n=%d)."
                 % (cap["keep_wr"], cap["keep_n"]))
        L.append("- Señales **VETADAS** (capitan opuesto vigente): wr %.4f (n=%d)."
                 % (cap["veto_wr"], cap["veto_n"]))
        L.append("- Diferencia: **%+.2f pp** (p naive %.2g).\n"
                 % (cap["delta_pp"], cap["p_naive"]))
        L.append("| theta | wr sin veto | n | wr vetadas | n | delta pp |")
        L.append("|---|---|---|---|---|---|")
        for k, v in cap["por_theta"].items():
            L.append("| %s | %.4f | %d | %.4f | %d | %+.2f |"
                     % (k, v["keep_wr"], v["keep_n"], v["veto_wr"], v["veto_n"],
                        v["delta_pp"]))
    else:
        L.append("- sin datos de split capitan")
    L.append("")
    write_atomic(OUT_MD, "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
