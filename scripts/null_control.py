#!/usr/bin/env python3
"""null_control.py — ficha #2 de docs/FEATURES-MINED-2026-07-25.md.

La ÚNICA feature cuya salida es una RESTA: retira fuentes en vez de añadir otra
opinión, y es lo único que se interpone entre 30 features nuevas y una catástrofe
de multiple testing.

QUE HACE
--------
1. **Null de entrada aleatoria**: por fuente, N entradas SINTÉTICAS emparejadas en
   símbolo, bucket horario (`timeofday_calib.BUCKETS`) y régimen de sesión,
   sacadas de sesiones DISTINTAS de las de la señal real.
2. Las dos ramas se etiquetan con **exactamente el mismo código** de triple
   barrera (`barrier_labels`), la misma ventana de barras y la misma regla de
   ATR. Un null asimétrico mide el sesgo del cargador de datos, no el edge.
3. `edge = p_señal − p_random`, con **bootstrap ESTACIONARIO sobre la DIFERENCIA**
   (bloque medio 30 barras, 2000 remuestreos).
4. **Corrección de muestra efectiva, obligatoria**:
       n_eff = n / (1 + (k−1)·ρ̄)      k = símbolos agrupados
                                       ρ̄ = corr media por pares de retornos 1m
   En semis ρ≈0.7–0.9 → los Wilson sobre sym-días agrupados son
   anticonservadores 3–4×. Además se topa con `n_clusters` = (sym,fecha)
   distintos, que es el techo duro de información independiente.
5. **BH-FDR q=0.10** sobre `fuente × símbolo × bucket`, luego **DSR / PSR /
   MinTRL** con la skill `stats-trading-risk`.
6. Propuesta de apagado en `data/signal_enable.PROPUESTO.json` — fichero
   PARALELO. **NO se toca `data/signal_enable.json`**: silenciar una alarma en
   vivo lo decide Yunior.

HONESTIDAD
----------
Ninguna función devuelve 0 / 0.5 / 50 ante datos insuficientes: devuelve None y
el veredicto es `DATA-INSUFFICIENT`. Ese es un resultado válido y se publica.

USO
    python3 scripts/null_control.py run [--n 2000] [--seed 7]
    python3 scripts/null_control.py selftest     # las dos puertas de cordura

SEÑAL-SOLAMENTE.
"""
import argparse
import json
import math
import os
import random
import sqlite3
import sys
import time
from bisect import bisect_right
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
if os.path.join(REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "scripts"))

import barrier_labels as BL                      # noqa: E402  (misma casa, ficha #1)
from timeofday_calib import BUCKETS, bucket_of   # noqa: E402

DB = os.path.join(REPO, "trades.db")
DB_RO = "file:" + DB + "?mode=ro"

SKILL_DIR = os.path.expanduser("~/.claude/skills/stats-trading-risk/scripts")

# celda de barrera PRE-COMPROMETIDA para el titular (no se elige a posteriori)
REF_K_TP, REF_K_SL, REF_H = 1.0, 1.0, 30
N_RANDOM = 2000
BOOT_BLOCK = 30
BOOT_N = 2000
FDR_Q = 0.10
MIN_N_EFF = 50          # ficha #1: sin 50 observaciones EFECTIVAS no se publica
DSR_PASS = 0.95
N_TRIALS_PER_SOURCE = len(BL.K_TP) * len(BL.K_SL) * len(BL.HORIZONS)

OUT_JSON = os.path.join(REPO, "data", "null_control.json")
OUT_PROPOSAL = os.path.join(REPO, "data", "signal_enable.PROPUESTO.json")
REGIME_CACHE = os.path.join(REPO, "data", "session_regime.json")
DOC_SUFFIX = ""                 # informe vivo: docs/NULL-CONTROL-<fecha>.md (sin sufijo)

BUCKET_WINDOW = {name: (lo, hi) for name, lo, hi in BUCKETS}


def _retarget(name):
    """Reapunta la fuente de señales (y por tanto la tabla de barrera de BL) y las
    salidas. Sin argumento -> comportamiento por defecto BYTE-IDENTICO al de siempre."""
    global OUT_JSON, OUT_PROPOSAL, REGIME_CACHE
    BL.use_signals_table(name)
    if not name or name == "signals":
        return
    OUT_JSON = os.path.join(REPO, "data", "null_control.%s.json" % name)
    global DOC_SUFFIX
    DOC_SUFFIX = "." + name
    OUT_PROPOSAL = os.path.join(REPO, "data", "signal_enable.PROPUESTO.%s.json" % name)
    REGIME_CACHE = os.path.join(REPO, "data", "session_regime.%s.json" % name)


# ============================================================================
# skill stats-trading-risk (BH-FDR / bootstrap / DSR / PSR / MinTRL)
# ============================================================================
_STATS = {}


def stats():
    """Carga la skill `stats-trading-risk`. Si no está, LEVANTA: no hay
    corrección de multiple testing improvisada que valga."""
    if _STATS:
        return _STATS
    if not os.path.isdir(SKILL_DIR):
        raise SystemExit("falta la skill stats-trading-risk en %s — sin ella no hay "
                         "BH-FDR/DSR/MinTRL y este script NO debe emitir veredictos"
                         % SKILL_DIR)
    if SKILL_DIR not in sys.path:
        sys.path.insert(0, SKILL_DIR)
    import multiple_testing, ratios, resampling, _special
    _STATS.update(mt=multiple_testing, ra=ratios, rs=resampling, sp=_special)
    return _STATS


# ============================================================================
# 1. Régimen de sesión (medido, no adivinado)
# ============================================================================
def session_regime(conn, use_cache=True):
    """{(sym,date): {"metric":x,"regime":"LOW|MID|HIGH"}} + {sym:[fechas]}.

    Métrica de régimen = rango de la sesión / precio medio de la sesión
    (`(max(h)-min(l))/avg(c)`), calculable en UNA pasada de SQL sobre las 540
    sesiones de poly_bars. Es un PROXY de volatilidad y se declara como tal en el
    JSON de salida (`regime_metric`). Terciles POR SÍMBOLO (cada nombre contra su
    propia historia, jamás contra la de otro)."""
    if use_cache and os.path.exists(REGIME_CACHE):
        try:
            d = json.load(open(REGIME_CACHE))
            reg = {tuple(k.split("|")): v for k, v in d["cells"].items()}
            return reg, d["sessions"]
        except (ValueError, KeyError) as e:
            print("[null_control] cache de regimen ilegible (%s), recalculando" % e)
    rows = conn.execute(
        "SELECT sym, date(ts/1000,'unixepoch','localtime') d, MAX(h), MIN(l), "
        "AVG(c), COUNT(*) FROM poly_bars GROUP BY sym, d").fetchall()
    by_sym = defaultdict(list)
    for sym, d, hi, lo, avg, n in rows:
        if not (avg and avg > 0) or n < 60:
            continue                      # sesión mutilada: fuera, no se rellena
        by_sym[sym].append((d, (hi - lo) / avg))
    cells, sessions = {}, {}
    for sym, lst in by_sym.items():
        lst.sort()
        vals = sorted(v for _d, v in lst)
        if len(vals) < 9:
            continue                      # sin terciles creíbles: el sym no entra
        t1 = vals[len(vals) // 3]
        t2 = vals[2 * len(vals) // 3]
        sessions[sym] = [d for d, _v in lst]
        for d, v in lst:
            cells[(sym, d)] = dict(metric=round(v, 6),
                                   regime="LOW" if v <= t1 else ("HIGH" if v > t2 else "MID"))
    tmp = REGIME_CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(cells={"%s|%s" % k: v for k, v in cells.items()},
                       sessions=sessions,
                       regime_metric="session_range_over_avg_price",
                       at=time.strftime("%Y-%m-%d %H:%M:%S")), f)
    os.replace(tmp, REGIME_CACHE)
    return cells, sessions


# ============================================================================
# 2. Correlación media por pares y muestra efectiva
# ============================================================================
def mean_pairwise_rho(conn, syms, dates):
    """ρ̄ = correlación Pearson media por pares de los retornos 1m de `syms`
    sobre `dates`, en marcas de tiempo COMUNES. Devuelve (rho, k, n_puntos) o
    (None, k, 0) si no hay solape suficiente — jamás un 0.0 plausible."""
    import numpy as np
    syms = sorted(set(syms))
    if len(syms) < 2 or not dates:
        return None, len(syms), 0
    ph = ",".join("?" * len(dates))
    closes = defaultdict(dict)
    for sym, ts, c in conn.execute(
            "SELECT sym, ts, c FROM poly_bars WHERE sym IN (%s) AND "
            "date(ts/1000,'unixepoch','localtime') IN (%s)"
            % (",".join("?" * len(syms)), ph), tuple(syms) + tuple(dates)):
        closes[sym][ts] = c
    common = None
    for sym in syms:
        s = set(closes.get(sym, {}))
        common = s if common is None else (common & s)
    if not common or len(common) < 60:
        return None, len(syms), 0 if not common else len(common)
    ts_sorted = sorted(common)
    mat = []
    keep = []
    for sym in syms:
        px = np.array([closes[sym][t] for t in ts_sorted], dtype=float)
        if (px <= 0).any():
            continue
        r = np.diff(np.log(px))
        if r.std() == 0:
            continue
        mat.append(r)
        keep.append(sym)
    if len(mat) < 2:
        return None, len(keep), len(ts_sorted)
    C = np.corrcoef(np.vstack(mat))
    iu = np.triu_indices(C.shape[0], k=1)
    vals = C[iu]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return None, len(keep), len(ts_sorted)
    return float(vals.mean()), len(keep), len(ts_sorted)


def effective_n(n, k, rho, n_clusters=None):
    """n_eff = n / (1 + (k−1)·ρ̄), topado por `n_clusters` (techo duro de
    información independiente). Devuelve None si ρ̄ es desconocida: sin ρ̄ no se
    publica un CI, porque el Wilson crudo es anticonservador 3–4×."""
    if n <= 0:
        return None
    if rho is None:
        return None
    k = max(1, int(k))
    rho_eff = max(0.0, min(0.999, rho))
    ne = n / (1.0 + (k - 1) * rho_eff)
    if n_clusters:
        ne = min(ne, float(n_clusters))
    return max(1.0, ne)


# ============================================================================
# 3. Etiquetado SIMÉTRICO de las dos ramas
# ============================================================================
def et_midnight(date_str):
    y, m, d = (int(x) for x in date_str.split("-"))
    return time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))


class BarLoader(object):
    """Carga la sesión (sym,date) + la sesión anterior (lookback del ATR) y las
    cachea de una en una. Grupos ordenados => una sola query por (sym,date)."""

    def __init__(self, conn, sessions):
        self.conn = conn
        self.sessions = sessions
        self.key = None
        self.bars = None
        self.queries = 0

    def get(self, sym, date):
        if self.key == (sym, date):
            return self.bars
        ds = self.sessions.get(sym) or []
        i = bisect_right(ds, date) - 1
        prev = ds[i - 1] if i >= 1 else date
        t0 = et_midnight(prev)
        t1 = et_midnight(date) + 24 * 3600
        rows = self.conn.execute(
            "SELECT ts,o,h,l,c FROM poly_bars WHERE sym=? AND ts>=? AND ts<? ORDER BY ts",
            (sym, int(t0 * 1000), int(t1 * 1000))).fetchall()
        self.queries += 1
        self.key = (sym, date)
        self.bars = [(r[0] / 1000.0, r[1], r[2], r[3], r[4]) for r in rows]
        return self.bars


def label_entry(bars, ts, direction, k_tp=REF_K_TP, k_sl=REF_K_SL, H=REF_H):
    """Etiqueta UNA entrada con la triple barrera de la ficha #1.
    Devuelve (resultado, motivo). resultado None => no etiquetable, con motivo."""
    if not bars:
        return None, "no_bars"
    ts_list = [b[0] for b in bars]
    i = bisect_right(ts_list, ts) - 1
    if i < 0:
        return None, "no_prior_bar"
    if ts - ts_list[i] > BL.ENTRY_MAX_STALE_S:
        return None, "entry_stale"
    entry = bars[i][4]
    if not (entry > 0):
        return None, "entry_nonpositive"
    atr = BL.atr_at(bars, i)
    if atr is None or not (atr > 0):
        return None, "atr_insufficient"
    j = bisect_right(ts_list, ts + H * 60)
    path = bars[i + 1:j]
    if not path:
        return None, "no_forward_bars"
    return BL.triple_barrier(path, entry, direction, entry + k_tp * atr * direction,
                             entry - k_sl * atr * direction, atr, ts), "ok"


def label_batch(loader, entries, k_tp=REF_K_TP, k_sl=REF_K_SL, H=REF_H):
    """entries: [(sym,date,ts,direction,tag)] -> (obs, motivos).
    Se ORDENA por (sym,date) para que el loader haga una query por sesión."""
    obs = []
    why = defaultdict(int)
    for sym, date, ts, d, tag in sorted(entries, key=lambda e: (e[0], e[1], e[2])):
        bars = loader.get(sym, date)
        r, reason = label_entry(bars, ts, d, k_tp, k_sl, H)
        why[reason] += 1
        if r is None:
            continue
        obs.append(dict(sym=sym, date=date, ts=ts, direction=d, tag=tag,
                        label=r["label"], mfe=r["mfe"], mae=r["mae"],
                        t_touch=r["t_touch"], ambig=r["ambig"]))
    return obs, dict(why)


def real_entries(conn):
    """Entradas REALES por fuente, con su bucket horario y régimen de sesión.
    Se re-etiquetan aquí (no se reusa barrier_outcomes) para que las dos ramas
    pasen por el MISMO cargador y la MISMA regla de ATR."""
    E_rows, st = BL.load_signals(conn)
    out = defaultdict(list)
    for s in E_rows:
        b = bucket_of(s["ts_txt"] or "")
        if b is None:
            st["skip_no_bucket"] = st.get("skip_no_bucket", 0) + 1
            continue
        out[s["source"]].append(dict(sym=s["sym"], date=s["date"], ts=s["ts"],
                                     direction=s["direction"], bucket=b, id=s["id"]))
    return dict(out), st


# ADITIVO 2026-07-25 (regeneracion de señales). Con `signals` (11 fechas) excluir la
# FECHA entera era gratis. Con `signals_regen` (501 fechas) NO queda ni una sesion limpia:
# `exclude_dates` vaciaba el pool y las 2000 tiradas salian `no_candidate_session` -> p_rand
# None -> DATA-INSUFFICIENT por construccion, no por falta de datos. Medido: 2000/2000.
# El emparejamiento del null es por (sym, bucket, regimen); lo que hay que evitar es meter
# una entrada "aleatoria" donde ESE simbolo si tuvo señal. Excluir (sym,fecha) en vez de la
# fecha entera hace exactamente eso y conserva el pool. Default = comportamiento de siempre.
EXCLUDE_MODES = ("date", "sym-date")
EXCLUDE_MODE = "date"


def draw_random(real_by_source, regime, sessions, n_draws, seed,
                exclude_dates, exclude_pairs=None, mode=None):
    """Null de entrada aleatoria EMPAREJADO. Por fuente se muestrea la joint
    empírica (sym, bucket, régimen, dirección) de sus señales reales y se coloca
    la entrada en un minuto uniforme dentro del MISMO bucket, en una sesión
    DISTINTA (excluye las fechas con señales reales) y del MISMO régimen.

    La exposición queda emparejada por construcción: la misma barrera y el mismo
    H que la rama real."""
    rng = random.Random(seed)
    out = {}
    diag = {}
    # sesiones candidatas por (sym, régimen), sin las fechas de señales reales
    cand = defaultdict(list)
    mode = mode or EXCLUDE_MODE
    if mode not in EXCLUDE_MODES:
        raise SystemExit("--null-exclude debe ser %s" % "|".join(EXCLUDE_MODES))
    exclude_pairs = exclude_pairs or set()
    for (sym, d), v in regime.items():
        if mode == "date":
            if d in exclude_dates:
                continue
        elif (sym, d) in exclude_pairs:
            continue
        cand[(sym, v["regime"])].append(d)
    for k in cand:
        cand[k].sort()
    for source, rows in real_by_source.items():
        pool = []
        for r in rows:
            reg = regime.get((r["sym"], r["date"]))
            if reg is None:
                continue
            pool.append((r["sym"], r["bucket"], reg["regime"], r["direction"]))
        if not pool:
            out[source] = []
            diag[source] = dict(pool=0, no_candidate_session=0)
            continue
        entries = []
        no_sess = 0
        for _i in range(n_draws):
            sym, bucket, reg, d = pool[rng.randrange(len(pool))]
            days = cand.get((sym, reg))
            if not days:
                no_sess += 1
                continue
            date = days[rng.randrange(len(days))]
            lo, hi = BUCKET_WINDOW[bucket]
            minute = rng.randrange(lo, hi)
            ts = et_midnight(date) + minute * 60 + rng.randrange(0, 60)
            entries.append((sym, date, ts, d, bucket))
        out[source] = entries
        diag[source] = dict(pool=len(pool), no_candidate_session=no_sess,
                            attempts=n_draws)
    return out, diag


# ============================================================================
# 4. Inferencia: bootstrap estacionario sobre la DIFERENCIA
# ============================================================================
def bootstrap_edge(sig_labels, rnd_labels, n_boot=BOOT_N, block=BOOT_BLOCK, seed=11):
    """edge = p_señal − p_random con bootstrap estacionario en CADA rama y la
    diferencia formada por remuestreo. Devuelve dict o None si falta muestra."""
    import numpy as np
    S = stats()
    a = np.array([x for x in sig_labels if x is not None], dtype=float)
    b = np.array([x for x in rnd_labels if x is not None], dtype=float)
    if a.size < 10 or b.size < 10:
        return None
    ba = S["rs"].stationary_bootstrap(a, avg_block=block, n_boot=n_boot, seed=seed)
    bb = S["rs"].stationary_bootstrap(b, avg_block=block, n_boot=n_boot, seed=seed + 1)
    diff = ba.mean(axis=1) - bb.mean(axis=1)
    lo, hi = np.percentile(diff, [2.5, 97.5])
    # p bilateral desde la propia distribución bootstrap
    p_side = min((diff <= 0).mean(), (diff >= 0).mean())
    pval = min(1.0, 2.0 * max(p_side, 1.0 / n_boot))
    return dict(edge=float(a.mean() - b.mean()), ci=[float(lo), float(hi)],
                p_boot=float(pval), n_sig=int(a.size), n_rand=int(b.size),
                p_sig=float(a.mean()), p_rand=float(b.mean()),
                boot_mean=float(diff.mean()), boot_sd=float(diff.std(ddof=1)))


def two_prop_p(w1, n1, w2, n2):
    """z-test de dos proporciones (bilateral). n1/n2 pueden ser EFECTIVAS
    (fraccionarias). Devuelve None si la muestra no permite el test."""
    S = stats()
    if n1 <= 0 or n2 <= 0:
        return None
    p1, p2 = w1 / n1, w2 / n2
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(max(p * (1 - p) * (1.0 / n1 + 1.0 / n2), 0.0))
    if se == 0:
        return None
    z = (p1 - p2) / se
    return float(2.0 * (1.0 - S["sp"].norm_cdf(abs(z))))


def payoff_series(obs, k_tp=REF_K_TP, k_sl=REF_K_SL):
    """Serie de pagos en unidades de ATR, en orden temporal: +k_tp si TP, −k_sl
    si SL. Los timeouts NO entran (no hay pago definido sin salida)."""
    return [k_tp if o["label"] == 1 else -k_sl
            for o in sorted(obs, key=lambda x: x["ts"]) if o["label"] is not None]


def sharpe_of(labels, k_tp, k_sl):
    import numpy as np
    r = np.array([k_tp if x == 1 else -k_sl for x in labels if x is not None], float)
    if r.size < 2 or r.std(ddof=1) == 0:
        return None
    return float(r.mean() / r.std(ddof=1))


# ============================================================================
# 5. Veredictos
# ============================================================================
def naive_verdict(boot, n_raw):
    """Veredicto que se habría dado SIN la corrección: Wilson/CI sobre la n CRUDA
    y sin BH-FDR ni DSR. Existe solo para MEDIR cuánto muerde la corrección
    (segunda puerta de cordura de la ficha: si nada cambia, no se está
    aplicando)."""
    if boot is None:
        return "DATA-INSUFFICIENT"
    if n_raw < MIN_N_EFF:
        return "DATA-INSUFFICIENT"
    if boot["ci"][1] <= 0:
        return "DEAD"
    return "PROBADO" if boot["ci"][0] > 0 else "UNPROVEN"


def verdict_of(boot, n_eff, fdr_pass, dsr):
    """Tabla de la skill measured-probability. DATA-INSUFFICIENT es un resultado
    válido y se publica; no se afloja el umbral para que salga algo."""
    if boot is None:
        return "DATA-INSUFFICIENT", "sin muestra suficiente para el bootstrap"
    if n_eff is None:
        return "DATA-INSUFFICIENT", "rho desconocida: sin n_eff no se publica CI"
    if n_eff < MIN_N_EFF:
        return "DATA-INSUFFICIENT", "n_eff %.1f < %d" % (n_eff, MIN_N_EFF)
    if boot["ci"][1] <= 0:
        return "DEAD", "CI del edge entero <= 0 (peor que entrada aleatoria)"
    if boot["ci"][0] > 0 and fdr_pass and dsr is not None and dsr > DSR_PASS:
        return "PROBADO", "edge>0 tras bootstrap, BH-FDR y DSR"
    why = []
    if boot["ci"][0] <= 0:
        why.append("el CI del edge cruza 0")
    if not fdr_pass:
        why.append("no pasa BH-FDR q=%.2f" % FDR_Q)
    if dsr is None:
        why.append("DSR no calculable")
    elif dsr <= DSR_PASS:
        why.append("DSR %.3f <= %.2f" % (dsr, DSR_PASS))
    return "UNPROVEN", "; ".join(why)


# ============================================================================
# 6. Orquestación
# ============================================================================
def run(n_draws=N_RANDOM, seed=7, verbose=True):
    import numpy as np
    S = stats()
    ro = sqlite3.connect(DB_RO, uri=True, timeout=60)
    regime, sessions = session_regime(ro)
    real, st = real_entries(ro)
    if not real:
        raise SystemExit("sin señales con dirección derivable — nada que contrastar")
    sig_dates = sorted(set(r["date"] for rows in real.values() for r in rows))
    loader = BarLoader(ro, sessions)

    # --- rama real (mismo cargador y misma regla de ATR que la sintética) ---
    real_obs, real_why = {}, {}
    for source, rows in real.items():
        ent = [(r["sym"], r["date"], r["ts"], r["direction"], r["bucket"]) for r in rows]
        real_obs[source], real_why[source] = label_batch(loader, ent)
    # --- rama sintética ---
    draws, draw_diag = draw_random(real, regime, sessions, n_draws, seed,
                                   exclude_dates=set(sig_dates),
                                   exclude_pairs={(r["sym"], r["date"])
                                                  for rows in real.values() for r in rows})
    rnd_obs, rnd_why = {}, {}
    for source, ent in draws.items():
        rnd_obs[source], rnd_why[source] = label_batch(loader, ent)
    if verbose:
        print("[null_control] %d queries de barras, %d fuentes" % (loader.queries, len(real)))

    # --- rho por fuente (símbolos del propio conjunto, fechas de las señales) ---
    out = {}
    fdr_cells = []
    for source in sorted(real_obs):
        so = real_obs[source]
        ro_ = rnd_obs.get(source, [])
        syms = sorted(set(o["sym"] for o in so))
        rho, k_used, npts = mean_pairwise_rho(ro, syms, sig_dates)
        n_res = sum(1 for o in so if o["label"] is not None)
        n_clusters = len(set((o["sym"], o["date"]) for o in so if o["label"] is not None))
        ne = effective_n(n_res, len(syms), rho, n_clusters)
        boot = bootstrap_edge([o["label"] for o in so], [o["label"] for o in ro_])
        # PSR / MinTRL / DSR sobre la serie de pagos de la rama real
        pay = payoff_series(so)
        psr = mtrl = dsr = sr0 = None
        if len(pay) >= 10:
            arr = np.array(pay, float)
            if arr.std(ddof=1) > 0:
                psr = float(S["ra"].probabilistic_sharpe_ratio(arr, 0.0))
                mtrl = S["ra"].min_track_record_length(arr, 0.0, 0.95)
                mtrl = None if not math.isfinite(mtrl) else float(mtrl)
                trial_sr = _trial_sharpes(ro, source)
                if trial_sr is not None and len(trial_sr) >= 2:
                    d = S["ra"].deflated_sharpe_ratio(arr, N_TRIALS_PER_SOURCE,
                                                      trial_sharpes=trial_sr)
                    dsr, sr0 = float(d["dsr"]), float(d["sr0"])
        out[source] = dict(
            n=n_res, n_raw_obs=len(so), n_clusters=n_clusters, k_syms=len(syms),
            rho=(None if rho is None else round(rho, 4)),
            rho_pairs_from_bars=npts,
            n_eff=(None if ne is None else round(ne, 1)),
            timeouts=sum(1 for o in so if o["label"] is None),
            ambig=sum(o["ambig"] for o in so),
            n_rand=sum(1 for o in ro_ if o["label"] is not None),
            rand_attrition=rnd_why.get(source, {}),
            real_attrition=real_why.get(source, {}),
            draw_diag=draw_diag.get(source, {}),
            psr=(None if psr is None else round(psr, 4)),
            mtrl_trades=(None if mtrl is None else int(math.ceil(mtrl))),
            dsr=(None if dsr is None else round(dsr, 4)),
            dsr_sr0=(None if sr0 is None else round(sr0, 4)),
            n_trials=N_TRIALS_PER_SOURCE)
        if boot:
            out[source].update(p=round(boot["p_sig"], 4), p_rand=round(boot["p_rand"], 4),
                               edge=round(boot["edge"], 4),
                               ci=[round(boot["ci"][0], 4), round(boot["ci"][1], 4)],
                               p_boot=round(boot["p_boot"], 4))
        else:
            out[source].update(p=None, p_rand=None, edge=None, ci=None, p_boot=None)
        out[source]["_boot"] = boot

        # --- celdas fuente x símbolo x bucket para el BH-FDR ---
        cs = defaultdict(lambda: [0, 0])
        cr = defaultdict(lambda: [0, 0])
        for o in so:
            if o["label"] is None:
                continue
            cs[(o["sym"], o["tag"])][0] += 1
            cs[(o["sym"], o["tag"])][1] += o["label"]
        for o in ro_:
            if o["label"] is None:
                continue
            cr[(o["sym"], o["tag"])][0] += 1
            cr[(o["sym"], o["tag"])][1] += o["label"]
        for cell, (n1, w1) in cs.items():
            n2, w2 = cr.get(cell, [0, 0])
            if n1 < 5 or n2 < 5:
                continue
            pv = two_prop_p(w1, n1, w2, n2)
            if pv is None:
                continue
            fdr_cells.append(dict(source=source, sym=cell[0], bucket=cell[1],
                                  n=n1, wins=w1, n_rand=n2, wins_rand=w2,
                                  p=w1 / n1, p_rand=w2 / n2, pval=pv))

    # --- BH-FDR q=0.10 sobre TODAS las celdas de TODAS las fuentes ---
    if fdr_cells:
        rej, adj = S["mt"].benjamini_hochberg([c["pval"] for c in fdr_cells], alpha=FDR_Q)
        for c, r, q in zip(fdr_cells, rej, adj):
            c["fdr_reject"] = bool(r)
            c["fdr_q"] = float(q)
    src_fdr = defaultdict(lambda: dict(cells=0, passed=0, min_q=1.0))
    for c in fdr_cells:
        d = src_fdr[c["source"]]
        d["cells"] += 1
        d["min_q"] = min(d["min_q"], c["fdr_q"])
        if c["fdr_reject"] and c["p"] > c["p_rand"]:
            d["passed"] += 1

    # --- veredictos ---
    for source, o in out.items():
        f = src_fdr.get(source, dict(cells=0, passed=0, min_q=1.0))
        o["fdr_cells"] = f["cells"]
        o["fdr_cells_passed"] = f["passed"]
        o["fdr_q"] = round(f["min_q"], 4)
        boot = o.pop("_boot")
        v, why = verdict_of(boot, o["n_eff"], f["passed"] > 0, o["dsr"])
        o["verdict"] = v
        o["why"] = why
        o["verdict_sin_correccion"] = naive_verdict(boot, o["n"])

    meta = dict(at=time.strftime("%Y-%m-%d %H:%M:%S"), ts=time.time(),
                ref_cell=dict(k_tp=REF_K_TP, k_sl=REF_K_SL, H=REF_H),
                n_draws=n_draws, seed=seed, boot=dict(n=BOOT_N, avg_block=BOOT_BLOCK),
                fdr_q=FDR_Q, min_n_eff=MIN_N_EFF, dsr_pass=DSR_PASS,
                regime_metric="session_range_over_avg_price",
                signal_dates=sig_dates,
                n_eff_formula="n/(1+(k-1)*rho_bar), topado por n_clusters (sym,fecha)",
                note=("celda de barrera PRE-COMPROMETIDA; las dos ramas se etiquetan "
                      "con el mismo cargador y la misma regla de ATR"),
                signals_load=st)
    res = dict(_meta=meta, **out)
    _atomic_json(OUT_JSON, res)
    _write_proposal(res)
    doc = write_doc(res, fdr_cells)
    return res, fdr_cells, doc


def _trial_sharpes(conn, source):
    """Sharpes por celda (k_tp,k_sl,H) de la ficha #1 para esta fuente -> la
    varianza que necesita el DSR. None si barrier_outcomes no está."""
    have = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                        "name='barrier_outcomes'").fetchone()
    if not have:
        return None
    cells = defaultdict(list)
    for k_tp, k_sl, H, label in conn.execute(
            "SELECT k_tp,k_sl,H,label FROM barrier_outcomes WHERE source=?", (source,)):
        cells[(k_tp, k_sl, H)].append(label)
    srs = []
    for (k_tp, k_sl, _H), labels in cells.items():
        s = sharpe_of(labels, k_tp, k_sl)
        if s is not None:
            srs.append(s)
    return srs or None


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, path)


def _write_proposal(res):
    """PROPUESTA de apagado. Fichero PARALELO: `data/signal_enable.json` NO se
    toca. Silenciar una alarma en vivo lo decide Yunior."""
    prop = {"_meta": dict(
        at=res["_meta"]["at"],
        WARNING=("PROPUESTA — este fichero NO lo lee ningun daemon. El real es "
                 "data/signal_enable.json y NO se ha tocado."),
        rule=("DEAD -> propone apagar. UNPROVEN -> banner solamente (jamas voz, "
              "jamas dimensiona). DATA-INSUFFICIENT -> se dice 'todavia no "
              "sabemos', en voz alta."))}
    for source, o in res.items():
        if source.startswith("_"):
            continue
        prop[source] = dict(verdict=o["verdict"],
                            propose_enabled=(o["verdict"] != "DEAD"),
                            propose_voice=(o["verdict"] == "PROBADO"),
                            n=o["n"], n_eff=o["n_eff"], edge=o["edge"], ci=o["ci"],
                            why=o["why"])
    _atomic_json(OUT_PROPOSAL, prop)


def write_doc(res, fdr_cells):
    m = res["_meta"]
    L = ["# NULL CONTROL — %s" % m["at"], ""]
    L.append("La única salida de todo el roster que es una **RESTA**. `edge = "
             "p_señal − p_random`, con entradas aleatorias EMPAREJADAS en símbolo, "
             "bucket horario y régimen de sesión, sacadas de sesiones distintas.")
    L.append("")
    L.append("- Celda de barrera **pre-comprometida**: `k_tp=%s, k_sl=%s, H=%s min` "
             "(no se elige a posteriori)." % (m["ref_cell"]["k_tp"], m["ref_cell"]["k_sl"],
                                              m["ref_cell"]["H"]))
    L.append("- Ambas ramas pasan por el **mismo** cargador de barras y la **misma** "
             "regla de ATR14 Wilder. Un null asimétrico mide el cargador, no el edge.")
    L.append("- `N` intentos sintéticos por fuente: %d · bootstrap estacionario "
             "%d remuestreos, bloque medio %d." % (m["n_draws"], m["boot"]["n"],
                                                   m["boot"]["avg_block"]))
    L.append("- `n_eff = %s`. Régimen = `%s` (proxy declarado), terciles por símbolo "
             "sobre sus propias sesiones." % (m["n_eff_formula"], m["regime_metric"]))
    L.append("- Fechas con señales: %s" % ", ".join(m["signal_dates"]))
    L.append("")
    L.append("## Veredictos por fuente")
    L.append("")
    L.append("| fuente | n | n_clusters | k syms | ρ̄ | **n_eff** | p señal | p random | **edge** | CI 95% del edge | p boot | BH-FDR (celdas ok/tot) | DSR | PSR | MinTRL | **veredicto** |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for source in sorted(k for k in res if not k.startswith("_")):
        o = res[source]
        f = lambda x, d=3: ("—" if x is None else ("%.*f" % (d, x)))
        L.append("| %s | %d | %d | %d | %s | **%s** | %s | %s | **%s** | %s | %s | %d/%d | %s | %s | %s | **%s** |"
                 % (source, o["n"], o["n_clusters"], o["k_syms"], f(o["rho"]),
                    f(o["n_eff"], 1), f(o["p"]), f(o["p_rand"]), f(o["edge"]),
                    ("—" if not o["ci"] else "[%+.3f, %+.3f]" % tuple(o["ci"])),
                    f(o["p_boot"]), o["fdr_cells_passed"], o["fdr_cells"],
                    f(o["dsr"]), f(o["psr"]),
                    ("—" if o["mtrl_trades"] is None else str(o["mtrl_trades"])),
                    o["verdict"]))
    L.append("")
    L.append("Motivo de cada veredicto:")
    L.append("")
    for source in sorted(k for k in res if not k.startswith("_")):
        L.append("- **%s** → `%s`: %s" % (source, res[source]["verdict"], res[source]["why"]))
    L.append("")
    L.append("## Efecto de la corrección de muestra efectiva")
    L.append("")
    L.append("| fuente | n cruda | n_eff | factor de inflación del CI que se estaba aplicando |")
    L.append("|---|---|---|---|")
    for source in sorted(k for k in res if not k.startswith("_")):
        o = res[source]
        if o["n_eff"]:
            L.append("| %s | %d | %.1f | **×%.1f** |" % (source, o["n"], o["n_eff"],
                                                         math.sqrt(o["n"] / o["n_eff"])))
        else:
            L.append("| %s | %d | — | ρ̄ desconocida |" % (source, o["n"]))
    L.append("")
    L.append("El factor es cuánto se estaba ESTRECHANDO cada intervalo de confianza "
             "por tratar símbolos correlacionados como muestras independientes.")
    L.append("")
    L.append("### Segunda puerta de cordura: ¿muerde la corrección?")
    L.append("")
    L.append("La ficha exige demostrar que `n_eff` + BH-FDR **cambia** veredictos. "
             "Si no cambiara nada, la corrección no se estaría aplicando.")
    L.append("")
    L.append("| fuente | veredicto SIN corrección (n cruda, sin FDR/DSR) | veredicto CON corrección | cambió |")
    L.append("|---|---|---|---|")
    changed = 0
    for source in sorted(k for k in res if not k.startswith("_")):
        o = res[source]
        ch = o["verdict"] != o["verdict_sin_correccion"]
        changed += 1 if ch else 0
        L.append("| %s | %s | **%s** | %s |" % (source, o["verdict_sin_correccion"],
                                                o["verdict"], "SÍ" if ch else "no"))
    L.append("")
    L.append("**%d de %d fuentes cambian de veredicto** al aplicar la muestra efectiva "
             "y el multiple testing. %s"
             % (changed, len([k for k in res if not k.startswith("_")]),
                "La puerta está activa." if changed else
                "AVISO: si esto es 0, revisar que la corrección se esté aplicando."))
    L.append("")
    L.append("## Celdas fuente × símbolo × bucket que SOBREVIVEN BH-FDR q=%.2f" % FDR_Q)
    L.append("")
    win = [c for c in fdr_cells if c.get("fdr_reject") and c["p"] > c["p_rand"]]
    if not win:
        L.append("> **NINGUNA.** Cero celdas de %d baten a la entrada aleatoria tras "
                 "corregir el multiple testing. Con %s fechas de señales ése es el "
                 "resultado esperable y es el resultado que se publica."
                 % (len(fdr_cells), len(m["signal_dates"])))
    else:
        L.append("| fuente | sym | bucket | n | p | p random | q BH |")
        L.append("|---|---|---|---|---|---|---|")
        for c in sorted(win, key=lambda x: x["fdr_q"]):
            L.append("| %s | %s | %s | %d | %.3f | %.3f | %.4f |"
                     % (c["source"], c["sym"], c["bucket"], c["n"], c["p"],
                        c["p_rand"], c["fdr_q"]))
    L.append("")
    L.append("## Qué se APAGARÍA (propuesta, NO aplicada)")
    L.append("")
    dead = [s for s in res if not s.startswith("_") and res[s]["verdict"] == "DEAD"]
    unp = [s for s in res if not s.startswith("_") and res[s]["verdict"] == "UNPROVEN"]
    ins = [s for s in res if not s.startswith("_") and res[s]["verdict"] == "DATA-INSUFFICIENT"]
    L.append("- **DEAD (propone apagar en `signal_enable.json`)**: %s"
             % (", ".join("`%s`" % s for s in sorted(dead)) or "ninguna"))
    L.append("- **UNPROVEN (banner solamente: jamás voz, jamás dimensiona)**: %s"
             % (", ".join("`%s`" % s for s in sorted(unp)) or "ninguna"))
    L.append("- **DATA-INSUFFICIENT (se dice 'todavía no sabemos', en voz alta)**: %s"
             % (", ".join("`%s`" % s for s in sorted(ins)) or "ninguna"))
    L.append("")
    L.append("> La propuesta está en `data/signal_enable.PROPUESTO.json`. "
             "**`data/signal_enable.json` NO se ha tocado**: silenciar una alarma en "
             "vivo lo decide Yunior. Compromiso previo de la ficha: los veredictos "
             "UNPROVEN se aceptan; el test no se afloja nunca.")
    L.append("")
    path = os.path.join(REPO, "docs", "NULL-CONTROL-%s%s.md"
                        % (time.strftime("%Y-%m-%d"), DOC_SUFFIX))
    BL.atomic_write(path, "\n".join(L) + "\n")
    return path


# ============================================================================
# 7. Puertas de cordura del propio null-control
# ============================================================================
def selftest(seed=3, n=1200):
    """(a) fuente moneda-al-aire -> edge ~ 0 con CI estrecho.
       (b) n_eff < n con ρ̄>0 y n_eff == n con ρ̄=0.
    Si (a) falla, el null no está midiendo lo que dice medir."""
    rng = random.Random(seed)
    coin_a = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    coin_b = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    b = bootstrap_edge(coin_a, coin_b, n_boot=600, block=BOOT_BLOCK, seed=5)
    ok_a = b is not None and abs(b["edge"]) < 0.06 and b["ci"][0] < 0 < b["ci"][1] \
        and (b["ci"][1] - b["ci"][0]) < 0.20
    ne_corr = effective_n(300, 10, 0.8)
    ne_indep = effective_n(300, 10, 0.0)
    ok_b = ne_corr is not None and ne_corr < 300 and ne_indep == 300
    print("selftest (a) moneda-al-aire: edge %+.4f CI [%+.4f,%+.4f] -> %s"
          % (b["edge"], b["ci"][0], b["ci"][1], "OK" if ok_a else "FALLA"))
    print("selftest (b) n_eff: rho=0.8,k=10 -> %.1f ; rho=0 -> %.1f -> %s"
          % (ne_corr, ne_indep, "OK" if ok_b else "FALLA"))
    return ok_a and ok_b


def main():
    ap = argparse.ArgumentParser(description="null de entrada aleatoria (ficha #2)")
    # ADITIVO 2026-07-25: por defecto identico a siempre (`signals`). Con
    # `--signals-table signals_regen` la MISMA maquinaria mide las señales regeneradas
    # sobre las 501 sesiones de poly_bars, y sus salidas van a ficheros PARALELOS
    # (data/null_control.<tabla>.json) para no pisar la medicion viva.
    ap.add_argument("--signals-table", default="signals")
    ap.add_argument("--null-exclude", default="date", choices=list(EXCLUDE_MODES),
                    help="que se excluye del pool del null: la FECHA entera (default, "
                         "conducta de siempre) o solo el par (simbolo,fecha) con señal")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--n", type=int, default=N_RANDOM)
    r.add_argument("--seed", type=int, default=7)
    sub.add_parser("selftest")
    a = ap.parse_args()
    _retarget(a.signals_table)
    global EXCLUDE_MODE
    EXCLUDE_MODE = a.null_exclude
    if a.cmd == "selftest":
        raise SystemExit(0 if selftest() else 2)
    if a.cmd != "run":
        ap.print_help()
        return
    res, cells, doc = run(a.n, a.seed)
    print("\n=== NULL CONTROL ===")
    print("%-11s %6s %8s %7s %8s %8s %9s %-20s %s"
          % ("fuente", "n", "n_eff", "rho", "p", "p_rand", "edge", "CI edge", "veredicto"))
    for source in sorted(k for k in res if not k.startswith("_")):
        o = res[source]
        ci = "—" if not o["ci"] else "[%+.3f,%+.3f]" % tuple(o["ci"])
        print("%-11s %6d %8s %7s %8s %8s %9s %-20s %s"
              % (source, o["n"],
                 "—" if o["n_eff"] is None else "%.1f" % o["n_eff"],
                 "—" if o["rho"] is None else "%.2f" % o["rho"],
                 "—" if o["p"] is None else "%.3f" % o["p"],
                 "—" if o["p_rand"] is None else "%.3f" % o["p_rand"],
                 "—" if o["edge"] is None else "%+.3f" % o["edge"], ci, o["verdict"]))
    nwin = sum(1 for c in cells if c.get("fdr_reject") and c["p"] > c["p_rand"])
    print("\nceldas fuente×sym×bucket: %d probadas, %d sobreviven BH-FDR q=%.2f"
          % (len(cells), nwin, FDR_Q))
    print("-> %s" % OUT_JSON)
    print("-> %s  (PROPUESTA — signal_enable.json NO se ha tocado)" % OUT_PROPOSAL)
    print("-> %s" % doc)


if __name__ == "__main__":
    main()
