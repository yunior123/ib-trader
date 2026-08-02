#!/usr/bin/env python3
"""reversal_grade.py — BARRIDO parametrico que GRADUA (no cablea) el reversal_router.

Replay historico bar a bar sobre poly_bars (data/trades.db, READ-ONLY, barras 1m 2024-07→
2026-07). Emite un evento por cada TRANSICION a REVERSAL_CONFIRMED / CONTINUATION_ACTIVE_
DO_NOT_FADE y lo grada con triple barrera first-touch.

POR QUE UN BARRIDO Y NO UN PUNTO (retirada del veredicto FAIL del 2026-08-02):
La version anterior publicaba un FAIL seco medido en UN SOLO punto: barrera ±1×ATR14 de
barras de 1 MINUTO (mediana 0,064% del precio en QQQ) y horizonte 30 barras 1m. El router
opera en 5m/15m/30m/1h/4h/1D: esa barrera medía MICROESTRUCTURA, no su tesis, y el WR salía
invariante al horizonte porque lo que ataba era la barrera. Al escalar barrera y horizonte
el MISMO codigo cambiaba de veredicto. Un veredicto que depende del parametro NO es un
veredicto: es una superficie. Aqui se publica la superficie entera (rejilla `celdas`) y un
`veredicto_agregado` que dice "SENSIBLE AL PARAMETRO — no concluyente" cuando lo es.

Doctrina measured-probability aplicada:
  - ATR calculado sobre el TIMEFRAME que el router usa (5m base / 60m HTF), no solo 1m.
  - Wilson SOLO sobre la muestra RESUELTA y sobre n_eff = n/(1+(k−1)ρ̄) (null_control.effective_n),
    con la sesion como cluster: 30 semis correlacionados no son 30 muestras.
  - Null de ENTRADA ALEATORIA emparejada por simbolo, bucket horario y exposicion (mismo
    horizonte y misma barrera) -> edge = p_señal − p_aleatoria, z-test sobre n_eff.
  - BH-FDR q=0.10 sobre TODAS las celdas del barrido (el barrido ES multiple testing).
  - Por debajo de min_n / min_n_eff no se publica probabilidad: DATA-INSUFFICIENT.
  Lo que NO se implementa aqui viaja declarado en el campo `limitaciones` del JSON.

FAIL-LOUD: ningun except devuelve 0/0.0/0.5/50. Sin ρ̄ no hay n_eff y no hay CI.
SEÑAL-SOLAMENTE / SIN CABLEAR: escribe data/reversal_grade.json con wired=false. No importa
ni emite a fleet_notify / fleet_consensus / order_engine ni a voz.

  ./venv/bin/python scripts/reversal_grade.py [SYMS...] \\
      [--horizons 30,120,390,780] [--atr-mults 1,2,4,10,20] [--atr-tfs 1,5,60] \\
      [--null-draws 1000] [--seed 7] [--single] [--out data/reversal_grade.json]
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import event_study as es  # noqa: E402
import null_control as nc  # noqa: E402
import reversal_router as rr  # noqa: E402

DB = os.path.join(DATA, "trades.db")
OUT = os.path.join(DATA, "reversal_grade.json")

GRADED_STATES = ("REVERSAL_CONFIRMED", "CONTINUATION_ACTIVE_DO_NOT_FADE")
GROUPS = ("ALL",) + GRADED_STATES
NULL_P = 0.50        # barrera simetrica => la moneda es 0.50
MIN_N_EFF = 30.0     # n EFECTIVA minima para publicar (K::CALIB_MIN_N)
FDR_Q = 0.10
RHO_FALLBACK = 0.41  # ρ̄ MEDIDA en la flota (docs/NULL-CONTROL-2026-07-25.md), no un prior

DEFAULT_HORIZONS_MIN = (30, 120, 390, 780)
DEFAULT_ATR_MULTS = (1.0, 2.0, 4.0, 10.0, 20.0)
DEFAULT_ATR_TFS_MIN = (1, 5, 60)   # 1m = punto original retirado; 5m = base del router; 60m = HTF
REF_CELL = (1, 1.0, 30)            # (atr_tf_min, atr_mult, horizon_min) del veredicto retirado

TOD_BUCKET_MIN = 30  # granularidad del emparejamiento horario del null

VERDICT_RULE = (
    "por celda: PASS si wilson_lo(n_eff) > %.2f, FAIL si wilson_hi(n_eff) <= %.2f, "
    "UNPROVEN si el CI cruza la moneda, DATA-INSUFFICIENT si n_eff < %.0f. "
    "AGREGADO: solo PASS-CONSISTENTE / FAIL-CONSISTENTE si TODAS las celdas publicables "
    "coinciden; si no, 'SENSIBLE AL PARAMETRO — no concluyente'."
    % (NULL_P, NULL_P, MIN_N_EFF))

LIMITACIONES = [
    "el null aleatorio empareja simbolo, bucket horario de %d min y exposicion (mismo "
    "horizonte y misma barrera), pero NO el regimen de sesion (skill measured-probability "
    "§4A pide dias del mismo regimen): no implementado." % TOD_BUCKET_MIN,
    "n_eff usa la SESION como cluster con rho medida entre simbolos; no hay correccion "
    "de autocorrelacion INTRA-dia (varios eventos del mismo simbolo en la misma sesion "
    "cuentan via k=ceil(n/n_clusters), que es una aproximacion de Kish, no un bloque).",
    "sin DSR/PSR/MinTRL: el barrido corrige multiplicidad por BH-FDR pero no deflacta un "
    "Sharpe; ninguna celda de aqui autoriza dimensionar.",
    "la ruta de resolucion camina cierres 1m de 04:00-19:59 ET: un horizonte de 390/780 "
    "barras cruza el cierre de RTH y resuelve en horario extendido (liquidez distinta).",
    "barrera simetrica k_tp = k_sl; no hay barrido de k_tp != k_sl ni de expectancia en ATR, "
    "solo win rate (la skill avisa de que el WR es la metrica que engaña).",
    "sin walk-forward con purging/embargo: el barrido mide IN-SAMPLE sobre 2024-07→2026-07.",
]


# ------------------------------------------------------------------ barras historicas
def load_poly_1m(sym: str, conn: sqlite3.Connection):
    """Barras 1m de poly_bars como el array (epoch_s, o, h, l, c, v) que espera el router.
    None si el simbolo no tiene barras — jamas un array vacio disfrazado."""
    rows = conn.execute(
        "SELECT ts, o, h, l, c, v FROM poly_bars WHERE sym=? ORDER BY ts", (sym.upper(),)
    ).fetchall()
    if not rows:
        return None
    arr = np.asarray(rows, dtype=float)
    arr[:, 0] = np.floor(arr[:, 0] / 1000.0)  # ts en ms -> epoch segundos
    return arr


def open_db(path: str = DB) -> sqlite3.Connection:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


# ------------------------------------------------------------------ replay del router
def replay_events(bars_1m: np.ndarray, states=GRADED_STATES):
    """Camina las barras base 5m y devuelve un evento por TRANSICION a uno de `states`.
    Cada evento: dict(ts, state, direction, bar_index). Lista vacia = no disparo nunca."""
    f = rr.features(bars_1m)
    if f is None:
        return []
    base = f["base"]
    n = len(base["c"])
    out = []
    prev_state = None
    for i in range(n):
        res = rr.state_at(f, i)
        st = res["state"]
        if st in states and st != prev_state:
            sc = res["scores"]
            direction = int(sc["trinity_dir"]) if st == "CONTINUATION_ACTIVE_DO_NOT_FADE" \
                else int(sc["bento_dir"])
            if direction != 0:
                out.append(dict(ts=int(res["bar_epoch"]), state=st,
                                direction=direction, bar_index=i))
        prev_state = st
    return out


# ------------------------------------------------------------------ ATR en el TIMEFRAME del router
def wilder_atr_series(h, l, c, period=es.ATR_PERIOD):
    """ATR de Wilder CAUSAL para toda la serie (NaN antes de `period`). Identico barra a barra
    a event_study.wilder_atr_at — el test lo prueba; aqui es O(n) en vez de O(n) por evento."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    n = len(c)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    prev = c[:-1]
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev), np.abs(l[1:] - prev)])
    atr = tr[1:period + 1].mean()
    out[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + tr[i]) / period
        out[i] = atr
    return out


def et_fields(epoch):
    """(date_ord, minuto_del_dia) en ET para cada barra. Levanta sin tzdata (no inventa UTC)."""
    if rr._ET is None:
        raise RuntimeError("sin zoneinfo/tzdata no hay rejilla ET — fail-loud")
    n = len(epoch)
    do = np.empty(n, dtype=np.int64)
    mi = np.empty(n, dtype=np.int64)
    for i in range(n):
        dt = datetime.fromtimestamp(int(epoch[i]), rr._ET)
        do[i] = dt.date().toordinal()
        mi[i] = dt.hour * 60 + dt.minute
    return do, mi


def agg_tf(bars_1m, do, mi, tf_min):
    """Barras de `tf_min` minutos ancladas a 09:30 ET (la MISMA rejilla RTH que el router).
    tf_min<=1 devuelve las 1m tal cual (reproduce el punto original, extendido incluido).
    -> (end_idx_1m, h, l, c) o None si no hay barras RTH."""
    if tf_min <= 1:
        return np.arange(len(bars_1m)), bars_1m[:, 2], bars_1m[:, 3], bars_1m[:, 4]
    keep = (mi >= rr.RTH_OPEN_MIN) & (mi < rr.RTH_CLOSE_MIN)
    idx = np.flatnonzero(keep)
    if idx.size == 0:
        return None
    b = (mi[idx] - rr.RTH_OPEN_MIN) // int(tf_min)
    key = do[idx] * 100000 + b
    new = np.empty(len(key), dtype=bool)
    new[0] = True
    new[1:] = key[1:] != key[:-1]
    starts = np.flatnonzero(new)
    H = np.maximum.reduceat(bars_1m[idx, 2], starts)
    L = np.minimum.reduceat(bars_1m[idx, 3], starts)
    last = np.flatnonzero(np.append(new[1:], True))   # ultima barra 1m de cada bucket
    return idx[last], H, L, bars_1m[idx[last], 4]


def atr_map_1m(bars_1m, do, mi, tf_min, period=es.ATR_PERIOD):
    """ATR de Wilder del timeframe `tf_min` mapeado a CADA indice 1m: el valor del ultimo
    bucket COMPLETADO en o antes de i (causal). NaN donde aun no hay ATR."""
    agg = agg_tf(bars_1m, do, mi, tf_min)
    if agg is None:
        return None
    end_idx, H, L, C = agg
    a = wilder_atr_series(H, L, C, period)
    if tf_min <= 1:
        return a
    j = np.searchsorted(end_idx, np.arange(len(bars_1m)), side="right") - 1
    out = np.full(len(bars_1m), np.nan)
    ok = j >= 0
    out[ok] = a[j[ok]]
    return out


# ------------------------------------------------------------------ resolucion vectorizada
def resolve_batch(c, entry_idx, entry_px, direction, up, dn, horizon):
    """first-touch + MFE/MAE por evento. MISMA semantica que event_study.resolve_event
    (cierres, ventana (i, i+H], empate en la misma barra -> barrera geometrica de arriba).
    -> (outcome, mfe_gt_mae): outcome 1=favorable 0=adverse -1=unresolved."""
    c = np.asarray(c, float)
    m = len(entry_idx)
    outcome = np.full(m, -1, dtype=np.int8)
    mfe_gt = np.zeros(m, dtype=bool)
    H = int(horizon)
    BIG = np.iinfo(np.int64).max
    for k in range(m):
        i = int(entry_idx[k])
        seg = c[i + 1:i + 1 + H]
        if seg.size == 0:
            continue
        u = np.flatnonzero(seg >= up[k])
        d = np.flatnonzero(seg <= dn[k])
        iu = int(u[0]) if u.size else BIG
        idn = int(d[0]) if d.size else BIG
        if iu == BIG and idn == BIG:
            geo = -1
        elif iu <= idn:
            geo = 1
        else:
            geo = 0
        if geo != -1 and direction[k] == -1:
            geo = 1 - geo
        outcome[k] = geo
        fav = direction[k] * (seg - entry_px[k])
        mfe_gt[k] = max(0.0, float(fav.max())) > max(0.0, float((-fav).max()))
    return outcome, mfe_gt


# ------------------------------------------------------------------ preparacion por simbolo
def prepare_symbol(sym, bars_1m, events, *, atr_tfs, atr_period, null_draws, seed):
    """Todo lo que NO depende de (mult, horizonte): entradas validas, ATR por timeframe y el
    juego de entradas ALEATORIAS emparejadas. None si el simbolo no aporta ninguna entrada."""
    stats = defaultdict(int)
    ts_list = bars_1m[:, 0].astype(np.int64).tolist()
    c = bars_1m[:, 4]
    n = len(c)
    do, mi = et_fields(bars_1m[:, 0])

    e_idx, e_px, e_dir, e_state, e_year, e_date, e_tod = [], [], [], [], [], [], []
    for ev in events:
        stats["total"] += 1
        i = bisect.bisect_right(ts_list, int(ev["ts"])) - 1
        if i < 0:
            stats["skip_no_prior_bar"] += 1
            continue
        if int(ev["ts"]) - ts_list[i] > es.ENTRY_MAX_STALE_S:
            stats["skip_entry_stale"] += 1
            continue
        if not (float(c[i]) > 0):
            stats["skip_entry_nonpositive"] += 1
            continue
        if i + 1 >= n:
            stats["skip_no_forward_bars"] += 1
            continue
        e_idx.append(i); e_px.append(float(c[i])); e_dir.append(int(ev["direction"]))
        e_state.append(ev["state"]); e_year.append(time.gmtime(int(ev["ts"])).tm_year)
        e_date.append(int(do[i])); e_tod.append(int(mi[i]) // TOD_BUCKET_MIN)
    if not e_idx:
        return None, dict(stats)

    atr = {}
    for tf in atr_tfs:
        a = atr_map_1m(bars_1m, do, mi, tf, atr_period)
        if a is None:
            stats["skip_no_atr_tf_%d" % tf] += 1
            continue
        atr[tf] = a
    if not atr:
        return None, dict(stats)

    # --- null: entradas aleatorias emparejadas en simbolo + bucket horario + direccion ---
    rng = np.random.default_rng(abs(hash((sym.upper(), int(seed)))) % (2 ** 32))
    tod_all = (mi[:n - 1] // TOD_BUCKET_MIN)    # n-1: hace falta al menos una barra delante
    pools = {}
    for b in np.unique(tod_all):
        pools[int(b)] = np.flatnonzero(tod_all == b)
    r_idx, r_dir, r_year, r_date = [], [], [], []
    picks = rng.integers(0, len(e_idx), size=int(null_draws))
    for p in picks:
        b = e_tod[int(p)]
        arr = pools.get(b)
        if arr is None or arr.size == 0:
            stats["null_skip_empty_bucket"] += 1
            continue
        j = int(arr[rng.integers(0, arr.size)])
        r_idx.append(j); r_dir.append(e_dir[int(p)])
        r_year.append(time.gmtime(int(bars_1m[j, 0])).tm_year); r_date.append(int(do[j]))

    prep = dict(
        sym=sym.upper(), c=c, atr=atr,
        idx=np.asarray(e_idx, dtype=np.int64), px=np.asarray(e_px, float),
        dir=np.asarray(e_dir, dtype=np.int64), state=np.asarray(e_state, dtype=object),
        year=np.asarray(e_year, dtype=np.int64), date=np.asarray(e_date, dtype=np.int64),
        r_idx=np.asarray(r_idx, dtype=np.int64), r_dir=np.asarray(r_dir, dtype=np.int64),
        r_px=c[np.asarray(r_idx, dtype=np.int64)] if r_idx else np.zeros(0),
        r_year=np.asarray(r_year, dtype=np.int64), r_date=np.asarray(r_date, dtype=np.int64),
    )
    return prep, dict(stats)


# ------------------------------------------------------------------ estadistica de celda
def n_effective(n_res, dates, rho):
    """Kish con la SESION como cluster: n_eff = n/(1+(k−1)ρ̄), k = ceil(n/n_clusters).
    None si no hay rho o no hay muestra — sin rho no se publica CI (null_control)."""
    if n_res <= 0 or not dates:
        return None
    n_clusters = len(dates)
    k = math.ceil(n_res / n_clusters)
    return nc.effective_n(n_res, k, rho)


def cell_stats(outcome, mfe_gt, years, dates, rho, min_n):
    """Estadistica de una celda YA resuelta. None si la muestra resuelta < min_n
    (fail-loud: sin muestra no se publica probabilidad)."""
    res = (outcome >= 0)
    n_res = int(res.sum())
    if n_res < min_n:
        return None
    k_fav = int((outcome == 1).sum())
    p, lo_raw, hi_raw = es.wilson(k_fav, n_res)
    n_eff = n_effective(n_res, set(dates[res].tolist()), rho)
    out = dict(n_events=int(len(outcome)), n_resolved=n_res,
               n_unresolved=int((outcome < 0).sum()), favorable=k_fav,
               win_rate=round(p, 4), wilson_lo_crudo=round(lo_raw, 4),
               wilson_hi_crudo=round(hi_raw, 4),
               mfe_gt_mae_pct=round(100.0 * float(mfe_gt.mean()), 2) if len(mfe_gt) else None,
               n_clusters=len(set(dates[res].tolist())))
    if n_eff is None:
        out.update(n_eff=None, wilson_lo=None, wilson_hi=None)
        return out
    k_eff = p * n_eff
    _, lo, hi = es.wilson(k_eff, n_eff)
    out.update(n_eff=round(n_eff, 1), wilson_lo=round(lo, 4), wilson_hi=round(hi, 4))
    return out


def by_year(outcome, years, min_n):
    """Desglose anual CRUDO (diagnostico de estabilidad). Los años flacos se marcan."""
    res = (outcome >= 0)
    out = {}
    for y in sorted(set(years[res].tolist())):
        m = res & (years == y)
        ny = int(m.sum())
        if ny < min_n:
            out[str(y)] = dict(status="INSUFFICIENT_N", n_resolved=ny, win_rate=None)
            continue
        ky = int((outcome[m] == 1).sum())
        py, loy, hiy = es.wilson(ky, ny)
        out[str(y)] = dict(win_rate=round(py, 4), wilson_lo_crudo=round(loy, 4),
                           wilson_hi_crudo=round(hiy, 4), n_resolved=ny)
    return out


def cell_verdict(st):
    """Veredicto de la celda CONTRA LA MONEDA (0.50), sobre n_eff. Nunca contra n cruda."""
    if st is None:
        return "DATA-INSUFFICIENT"
    if st.get("n_eff") is None or st["n_eff"] < MIN_N_EFF:
        return "DATA-INSUFFICIENT"
    if st["wilson_lo"] > NULL_P:
        return "PASS"
    if st["wilson_hi"] <= NULL_P:
        return "FAIL"
    return "UNPROVEN"


def crude_verdict(st):
    """El mismo veredicto SIN corregir por correlacion. Existe solo para MEDIR cuanto muerde
    la correccion: si crudo y n_eff coinciden, la correccion no se esta aplicando."""
    if st is None:
        return "DATA-INSUFFICIENT"
    if st["wilson_lo_crudo"] > NULL_P:
        return "PASS"
    if st["wilson_hi_crudo"] <= NULL_P:
        return "FAIL"
    return "UNPROVEN"


def aggregate_verdict(cells, key="verdict_moneda"):
    """Veredicto HONESTO del barrido. Si el veredicto depende del parametro se dice."""
    pub = [c for c in cells if c[key] != "DATA-INSUFFICIENT"]
    if not pub:
        return ("DATA-INSUFFICIENT",
                "ninguna celda del barrido alcanza n_eff >= %.0f" % MIN_N_EFF)
    vs = {c[key] for c in pub}
    n_pass = sum(1 for c in pub if c[key] == "PASS")
    n_fail = sum(1 for c in pub if c[key] == "FAIL")
    n_unp = sum(1 for c in pub if c[key] == "UNPROVEN")
    detail = ("%d celdas publicables: %d PASS, %d FAIL, %d UNPROVEN"
              % (len(pub), n_pass, n_fail, n_unp))
    if vs == {"PASS"}:
        return "PASS-CONSISTENTE", detail + " — unanime en todo el barrido"
    if vs == {"FAIL"}:
        return "FAIL-CONSISTENTE", detail + " — unanime en todo el barrido"
    if vs == {"UNPROVEN"}:
        return ("UNPROVEN-CONSISTENTE",
                detail + " — en TODAS las celdas el CI(n_eff) cruza la moneda: no se "
                         "distingue del azar, y tampoco se puede declarar peor que el azar")
    return ("SENSIBLE AL PARAMETRO — no concluyente",
            detail + " — el veredicto CAMBIA con (timeframe del ATR, multiplo, horizonte): "
                     "no hay hallazgo, ni a favor ni en contra")


# ------------------------------------------------------------------ rho medida
def measure_rho(conn, syms, dates, max_dates=20):
    """ρ̄ por pares medida en las barras 1m de los propios simbolos/fechas. Si el solape no da,
    cae al valor MEDIDO de la flota y lo DECLARA en rho_meta (nunca un 0 plausible). Un fallo
    real de la BD LEVANTA: no se tapa con una constante."""
    ds = sorted(dates)
    if len(ds) > max_dates:
        step = len(ds) / float(max_dates)
        ds = [ds[int(i * step)] for i in range(max_dates)]
    rho, k_used, npts = nc.mean_pairwise_rho(conn, syms, ds)
    if rho is None:
        return RHO_FALLBACK, dict(source="RHO_FLOTA (medida 2026-07-25)",
                                  reason="solape 1m insuficiente", dates=len(ds))
    return rho, dict(source="medida in-situ (mean_pairwise_rho)", syms=k_used,
                     puntos=npts, dates=len(ds))


# ------------------------------------------------------------------ barrido
def sweep(preps, *, horizons, mults, atr_tfs, rho, min_n, atr_period):
    """Rejilla (atr_tf × multiplo × horizonte) × grupo de estado. Devuelve la lista de celdas
    con Wilson sobre n_eff, edge contra el null aleatorio y BH-FDR sobre TODO el barrido."""
    cells = []
    for tf in atr_tfs:
        usable = [p for p in preps if tf in p["atr"]]
        if not usable:
            continue
        for mult in mults:
            for H in horizons:
                sig = defaultdict(list)
                nul = defaultdict(list)
                for p in usable:
                    a = p["atr"][tf]
                    for tag, idx, px, dr, yr, dt in (
                            ("s", p["idx"], p["px"], p["dir"], p["year"], p["date"]),
                            ("n", p["r_idx"], p["r_px"], p["r_dir"], p["r_year"], p["r_date"])):
                        if len(idx) == 0:
                            continue
                        av = a[idx]
                        ok = np.isfinite(av) & (av > 0) & (px > 0)
                        if not ok.any():
                            continue
                        i2, px2, d2, a2 = idx[ok], px[ok], dr[ok], av[ok]
                        o, mg = resolve_batch(p["c"], i2, px2, d2,
                                              px2 + mult * a2, px2 - mult * a2, H)
                        tgt = sig if tag == "s" else nul
                        tgt["o"].append(o); tgt["m"].append(mg)
                        tgt["y"].append(yr[ok]); tgt["d"].append(dt[ok])
                        if tag == "s":
                            tgt["st"].append(p["state"][ok])
                if not sig["o"]:
                    continue
                so = np.concatenate(sig["o"]); sm = np.concatenate(sig["m"])
                sy = np.concatenate(sig["y"]); sd = np.concatenate(sig["d"])
                ss = np.concatenate(sig["st"])
                if nul["o"]:
                    no = np.concatenate(nul["o"]); nm = np.concatenate(nul["m"])
                    ny = np.concatenate(nul["y"]); nd = np.concatenate(nul["d"])
                else:
                    no = nm = ny = nd = None
                for grp in GROUPS:
                    m = np.ones(len(so), dtype=bool) if grp == "ALL" else (ss == grp)
                    if not m.any():
                        continue
                    st = cell_stats(so[m], sm[m], sy[m], sd[m], rho, min_n)
                    nst = (cell_stats(no, nm, ny, nd, rho, min_n)
                           if no is not None else None)
                    cell = dict(grupo=grp,
                                params=dict(atr_tf_min=int(tf), atr_mult=float(mult),
                                            horizon_min=int(H), atr_period=int(atr_period)),
                                es_punto_original=bool((tf, mult, H) == REF_CELL),
                                senal=st, null_aleatorio=nst,
                                by_year=by_year(so[m], sy[m], min_n))
                    cell["verdict_moneda"] = cell_verdict(st)
                    cell.update(_edge(st, nst))
                    cells.append(cell)
    _apply_fdr(cells)
    return cells


def _edge(st, nst):
    """edge = p_señal − p_aleatoria con z-test de dos proporciones sobre n_eff.
    None (no 0.0) cuando falta cualquiera de las dos muestras efectivas."""
    if st is None or nst is None or st.get("n_eff") is None or nst.get("n_eff") is None:
        return dict(edge=None, edge_p=None)
    p1, p2 = st["win_rate"], nst["win_rate"]
    p = nc.two_prop_p(p1 * st["n_eff"], st["n_eff"], p2 * nst["n_eff"], nst["n_eff"])
    return dict(edge=round(p1 - p2, 4), edge_p=(None if p is None else round(p, 6)))


def _apply_fdr(cells):
    """BH-FDR q=0.10 sobre TODAS las celdas con p calculable: el barrido ES multiple testing."""
    idx = [i for i, c in enumerate(cells) if c.get("edge_p") is not None]
    for c in cells:
        c["fdr_q"] = None
        c["fdr_pass"] = None
        c["verdict_vs_null"] = "DATA-INSUFFICIENT"
    if not idx:
        return
    bh = nc.stats()["mt"].benjamini_hochberg
    rej, adj = bh([cells[i]["edge_p"] for i in idx], alpha=FDR_Q)
    for j, i in enumerate(idx):
        cells[i]["fdr_q"] = round(float(adj[j]), 6)
        cells[i]["fdr_pass"] = bool(rej[j]) and cells[i]["edge"] > 0
        cells[i]["verdict_vs_null"] = (
            "PROBADO" if cells[i]["fdr_pass"] and cells[i]["verdict_moneda"] == "PASS"
            else "DEAD" if cells[i]["edge"] is not None and cells[i]["edge"] < 0
            and bool(rej[j]) else "UNPROVEN")


# ------------------------------------------------------------------ orquestacion
def atomic_write(path: str, obj: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _universe(argv):
    if argv:
        return [s.upper() for s in argv]
    p = os.path.join(DATA, "fleet.txt")
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return [s.upper() for s in open(p).read().split()]


def run(syms, *, horizons=DEFAULT_HORIZONS_MIN, mults=DEFAULT_ATR_MULTS,
        atr_tfs=DEFAULT_ATR_TFS_MIN, atr_period=es.ATR_PERIOD, min_n=es.MIN_N,
        null_draws=1000, seed=7, out=OUT, nota=None, quiet=False):
    conn = open_db(DB)
    preps, per_symbol, used = [], {}, []
    discards = defaultdict(int)
    events_raw = 0
    all_dates = set()
    try:
        for sym in syms:
            t0 = time.time()
            bars = load_poly_1m(sym, conn)
            if bars is None:
                discards["skip_no_bars_in_db"] += 1
                if not quiet:
                    print("%-6s sin barras en poly_bars" % sym, flush=True)
                continue
            evs = replay_events(bars)
            events_raw += len(evs)
            prep, st = prepare_symbol(sym, bars, evs, atr_tfs=atr_tfs, atr_period=atr_period,
                                      null_draws=null_draws, seed=seed)
            for k, v in st.items():
                discards[k] += v
            if prep is None:
                per_symbol[sym] = dict(n_bars_1m=int(len(bars)), n_events=len(evs),
                                       n_entradas=0, by_state={})
                if not quiet:
                    print("%-6s sin entradas validas" % sym, flush=True)
                continue
            preps.append(prep)
            used.append(sym)
            counts = defaultdict(int)
            for s in prep["state"]:
                counts[s] += 1
            per_symbol[sym] = dict(n_bars_1m=int(len(bars)), n_events=len(evs),
                                   n_entradas=int(len(prep["idx"])),
                                   n_null=int(len(prep["r_idx"])), by_state=dict(counts))
            all_dates |= set(prep["date"].tolist())
            if not quiet:
                print("%-6s bars=%7d eventos=%4d entradas=%4d null=%4d (%.1fs)"
                      % (sym, len(bars), len(evs), len(prep["idx"]), len(prep["r_idx"]),
                         time.time() - t0), flush=True)
        if not preps:
            raise SystemExit("ninguna entrada valida en %d simbolos — nada que graduar" % len(syms))
        dates_str = sorted({datetime.fromordinal(d).strftime("%Y-%m-%d") for d in all_dates})
        rho, rho_meta = measure_rho(conn, used, dates_str)
    finally:
        conn.close()

    cells = sweep(preps, horizons=horizons, mults=mults, atr_tfs=atr_tfs, rho=rho,
                  min_n=min_n, atr_period=atr_period)
    v_all = [c for c in cells if c["grupo"] == "ALL"]
    verdicto, why = aggregate_verdict(v_all)
    rep = dict(
        generated=datetime.now(timezone.utc).isoformat(),
        epoch=int(time.time()),
        wired=False,          # el router sigue en SOMBRA: esto no lo cablea a nada
        shadow=True,
        source="poly_bars (data/trades.db, read-only) — barras 1m 04:00-19:59 ET",
        veredicto_agregado=verdicto,
        veredicto_detalle=why,
        veredicto_por_grupo={g: dict(zip(("veredicto", "detalle"),
                                         aggregate_verdict([c for c in cells
                                                            if c["grupo"] == g])))
                             for g in GROUPS},
        limitaciones=LIMITACIONES,
        params=dict(horizons_min=list(horizons), atr_mults=list(mults),
                    atr_tfs_min=list(atr_tfs), atr_period=atr_period, min_n=min_n,
                    min_n_eff=MIN_N_EFF, null_p=NULL_P, fdr_q=FDR_Q,
                    null_draws_por_simbolo=null_draws, seed=seed,
                    tod_bucket_min=TOD_BUCKET_MIN,
                    rho=round(float(rho), 4), rho_meta=rho_meta,
                    verdict_rule=VERDICT_RULE,
                    graded_states=list(GRADED_STATES),
                    celda_punto_original=dict(atr_tf_min=REF_CELL[0], atr_mult=REF_CELL[1],
                                              horizon_min=REF_CELL[2]),
                    event_def="transicion de estado (no cada barra en estado)",
                    entry_def="close de la barra 1m que cierra el bucket 5m del evento",
                    atr_def="ATR14 de Wilder del timeframe atr_tf_min (rejilla RTH anclada "
                            "a 09:30 ET); atr_tf_min=1 usa las 1m tal cual"),
        symbols=used,
        nota=nota or ("barrido sobre %d simbolos de la flota" % len(used)),
        events_raw=events_raw,
        discards=dict(discards),
        celdas=cells,
        per_symbol=per_symbol,
    )
    atomic_write(out, rep)
    return rep


def run_single(syms, *, horizon, atr_frac, atr_period, min_n, out):
    """Modo legado: UN punto parametrico. Existe para reproducir el veredicto RETIRADO;
    su salida lleva la advertencia dentro y no publica veredicto agregado."""
    rep = run(syms, horizons=(horizon,), mults=(atr_frac,), atr_tfs=(1,),
              atr_period=atr_period, min_n=min_n, out=out,
              nota="MODO --single: UN punto parametrico. Un veredicto de un solo punto "
                   "NO es un veredicto (ver cabecera del script).")
    return rep


def _print(rep):
    print("=== reversal_grade === (wired=%s)" % rep["wired"])
    print("  VEREDICTO AGREGADO: %s" % rep["veredicto_agregado"])
    print("  %s" % rep["veredicto_detalle"])
    print("  rho=%.3f (%s)  simbolos=%d  celdas=%d"
          % (rep["params"]["rho"], rep["params"]["rho_meta"]["source"],
             len(rep["symbols"]), len(rep["celdas"])))
    hdr = "  %-28s %4s %6s %5s  %-17s %6s %8s %7s %s"
    print(hdr % ("grupo", "tf", "xATR", "H", "WR / Wilson(n_eff)", "n_eff", "edge", "fdr_q",
                 "veredicto"))
    for c in rep["celdas"]:
        if c["grupo"] != "ALL":
            continue
        s = c["senal"]
        p = c["params"]
        if s is None or s.get("n_eff") is None:
            print(hdr % (c["grupo"], p["atr_tf_min"], "%.0f" % p["atr_mult"],
                         p["horizon_min"], "—", "—", "—", "—", c["verdict_moneda"]))
            continue
        print(hdr % (c["grupo"], p["atr_tf_min"], "%.0f" % p["atr_mult"], p["horizon_min"],
                     "%.3f [%.3f,%.3f]" % (s["win_rate"], s["wilson_lo"], s["wilson_hi"]),
                     "%.1f" % s["n_eff"],
                     "—" if c["edge"] is None else "%+.4f" % c["edge"],
                     "—" if c["fdr_q"] is None else "%.3f" % c["fdr_q"],
                     c["verdict_moneda"] + ("*" if c["es_punto_original"] else "")))
    print("  (* = punto parametrico del veredicto RETIRADO)")


def _csv_ints(s):
    return tuple(int(x) for x in str(s).replace(" ", "").split(",") if x)


def _csv_floats(s):
    return tuple(float(x) for x in str(s).replace(" ", "").split(",") if x)


def main():
    ap = argparse.ArgumentParser(description="barrido parametrico del reversal_router")
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--horizons", type=_csv_ints, default=DEFAULT_HORIZONS_MIN,
                    help="horizontes en MINUTOS (barras 1m), csv")
    ap.add_argument("--atr-mults", type=_csv_floats, default=DEFAULT_ATR_MULTS,
                    help="multiplos de ATR de la barrera, csv")
    ap.add_argument("--atr-tfs", type=_csv_ints, default=DEFAULT_ATR_TFS_MIN,
                    help="timeframes en MINUTOS sobre los que se calcula el ATR, csv")
    ap.add_argument("--atr-period", type=int, default=es.ATR_PERIOD)
    ap.add_argument("--min-n", type=int, default=es.MIN_N)
    ap.add_argument("--null-draws", type=int, default=1000,
                    help="entradas aleatorias emparejadas POR SIMBOLO")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--nota", default=None, help="se escribe tal cual en el JSON")
    ap.add_argument("--single", action="store_true",
                    help="modo legado de UN punto (--horizons/--atr-mults toman el primero)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    syms = _universe(a.syms)
    if a.single:
        rep = run_single(syms, horizon=a.horizons[0], atr_frac=a.atr_mults[0],
                         atr_period=a.atr_period, min_n=a.min_n, out=a.out)
    else:
        rep = run(syms, horizons=a.horizons, mults=a.atr_mults, atr_tfs=a.atr_tfs,
                  atr_period=a.atr_period, min_n=a.min_n, null_draws=a.null_draws,
                  seed=a.seed, out=a.out, nota=a.nota)
    _print(rep)
    print("  -> %s" % a.out)


if __name__ == "__main__":
    main()
