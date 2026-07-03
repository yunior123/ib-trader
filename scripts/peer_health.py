#!/usr/bin/env python3
"""peer_health.py — ENDURECIMIENTO MEDIDO de `trades.db peer_weights` (ficha 29).

Este script NO es una feature nueva: es la MEDICIÓN que decide si alguna relación
lead-lag de la flota sobrevive un null correcto. Entregable = el conteo de pares
supervivientes, INCLUIDO EL CERO.

Matemática (ficha 29, sin cambios):
 1. Retornos de 1 minuto inner-joined POR EPOCH, con tasa de descarte publicada por par.
 2. `corr` con errores estándar HAC (Newey-West, Bartlett lag 5) y t-stats.
 3. `lead_min` de la correlación cruzada aceptado SOLO si el pico sobrevive AMBOS:
      (a) null de 1000x timestamps barajados, y
      (b) control de factor común: regresar AMBAS patas sobre SMH y QQQ y luego
          cross-correlacionar los RESIDUOS. Las cotizaciones asíncronas en activos
          que co-mueven producen picos espurios a lag no-cero POR CONSTRUCCIÓN.
 4. `beta` por OLS sobre retornos residualizados, con `n` y `R²`.
 5. Publicar CUÁNTOS pares sobreviven.

Regla de decisión: cualquier consumidor puede usar SOLO pares con `lead_survives=1`.
Si CERO sobreviven, `governing_captain()` sigue siendo DOCTRINA (SPY/QQQ = mercado,
SMH = semis) SIN ninguna afirmación de lead medido adjunta.

LEYES: SEÑAL-SOLAMENTE. Ningún `except` devuelve 0/0.0/0.5/50/{} — solo None o levanta.
BD abierta SOLO LECTURA. Escritura atómica (tmp + os.rename).

Uso:
  python3 scripts/peer_health.py            # mide los pares de peer_weights y publica
  python3 scripts/peer_health.py --shuffles 200 --limit 3   # corrida rápida
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "trades.db")
OUT_JSON = os.path.join(REPO, "data", "peer_health.json")

BAR_MS = 60_000          # barras de 1 minuto
MAX_LAG = 5              # ±5 minutos
HAC_LAG = 5              # Newey-West Bartlett lag 5
N_SHUFFLE = 1000         # null de timestamps barajados
MIN_N = 500              # por debajo de esto NO se afirma nada (todo None)
ALPHA = 0.05
CONTROLS = ("SMH", "QQQ")   # factor común de la flota


# ---------------------------------------------------------------- datos

def db_uri(path: str = DB) -> str:
    return f"file:{path}?mode=ro"


def load_returns(syms, db_path: str = DB, limit: int | None = None):
    """Retornos log de 1 minuto por símbolo desde poly_bars.

    TRAMPA CRÍTICA: `ts` está en MILISEGUNDOS. Solo se forma un retorno cuando dos
    barras son consecutivas (gap == 60000 ms), de modo que jamás se cuela un salto
    overnight o un hueco de datos como si fuera un retorno de un minuto.

    Devuelve {sym: (ts_int64, ret_float64)}. Un símbolo sin datos NO aparece
    (no se fabrica una serie vacía ni ceros).
    """
    conn = sqlite3.connect(db_uri(db_path), uri=True)
    try:
        out = {}
        for sym in syms:
            q = "SELECT ts, c FROM poly_bars WHERE sym=? ORDER BY ts"
            if limit:
                q += f" LIMIT {int(limit)}"
            rows = conn.execute(q, (sym,)).fetchall()
            if len(rows) < 2:
                continue
            ts = np.asarray([r[0] for r in rows], dtype=np.int64)
            c = np.asarray([r[1] for r in rows], dtype=np.float64)
            good = (np.diff(ts) == BAR_MS) & (c[:-1] > 0) & (c[1:] > 0)
            r_ts = ts[1:][good]
            r = np.log(c[1:][good] / c[:-1][good])
            if r_ts.size:
                out[sym] = (r_ts, r)
        return out
    finally:
        conn.close()


def inner_join(series: dict, keys):
    """Inner join POR EPOCH de varias series de retornos.

    Devuelve (ts_comun, {k: valores}, drop_rate) donde drop_rate = 1 - n_join/n_union
    sobre los timestamps de TODAS las claves pedidas. None si falta alguna serie.
    """
    if any(k not in series for k in keys):
        return None
    common = series[keys[0]][0]
    union = series[keys[0]][0]
    for k in keys[1:]:
        common = np.intersect1d(common, series[k][0], assume_unique=True)
        union = np.union1d(union, series[k][0])
    if common.size == 0 or union.size == 0:
        return None
    vals = {}
    for k in keys:
        ts_k, r_k = series[k]
        idx = np.searchsorted(ts_k, common)
        vals[k] = r_k[idx]
    drop_rate = 1.0 - common.size / union.size
    return common, vals, drop_rate


# ---------------------------------------------------------------- estadística

def hac_corr(x: np.ndarray, y: np.ndarray, lag: int = HAC_LAG):
    """Correlación con SE HAC (Newey-West, kernel Bartlett).

    corr se estima como la pendiente OLS de y estandarizada sobre x estandarizada.
    Devuelve dict(corr, se, tstat, n, n_eff) o None si no se puede estimar.
    """
    n = x.size
    if n < 30 or y.size != n:
        return None
    sx, sy = x.std(ddof=1), y.std(ddof=1)
    if not np.isfinite(sx) or not np.isfinite(sy) or sx <= 0 or sy <= 0:
        return None
    xs = (x - x.mean()) / sx
    ys = (y - y.mean()) / sy
    xx = float(xs @ xs)
    if xx <= 0:
        return None
    b = float(xs @ ys) / xx           # == corr de Pearson
    e = ys - b * xs
    u = xs * e
    omega_iid = float(u @ u)
    omega = omega_iid
    for l in range(1, min(lag, n - 1) + 1):
        w = 1.0 - l / (lag + 1.0)
        g = float(u[l:] @ u[:-l])
        omega += 2.0 * w * g
    if omega <= 0 or not np.isfinite(omega):
        return None
    var_b = omega / (xx * xx)
    se = float(np.sqrt(var_b))
    if se <= 0 or not np.isfinite(se):
        return None
    n_eff = float(n * omega_iid / omega) if omega > 0 else None
    return dict(corr=b, se=se, tstat=b / se, n=int(n), n_eff=n_eff)


def _lag_pairs(ts: np.ndarray, lag: int):
    """Índices (i_target, i_peer) tales que ts[i_peer] == ts[i_target] - lag*60000.

    El desfase se hace POR TIEMPO, no por posición: así un hueco de datos o el
    cierre de sesión no se convierten en un lag falso.
    """
    if lag == 0:
        idx = np.arange(ts.size)
        return idx, idx
    want = ts - lag * BAR_MS
    pos = np.searchsorted(ts, want)
    pos_c = np.clip(pos, 0, ts.size - 1)
    ok = ts[pos_c] == want
    return np.nonzero(ok)[0], pos_c[ok]


def xcorr_profile(ts, tgt, peer, max_lag=MAX_LAG):
    """corr(target[t], peer[t-lag]) para lag en [-max_lag, max_lag].

    lag > 0  =>  el PEER adelanta al target.
    Devuelve (lags, corrs, counts); corrs con NaN donde no hay muestra suficiente.
    """
    lags = np.arange(-max_lag, max_lag + 1)
    corrs = np.full(lags.size, np.nan)
    counts = np.zeros(lags.size, dtype=np.int64)
    for j, lag in enumerate(lags):
        it, ip = _lag_pairs(ts, int(lag))
        counts[j] = it.size
        if it.size < MIN_N:
            continue
        a, b = tgt[it], peer[ip]
        sa, sb = a.std(), b.std()
        if sa <= 0 or sb <= 0:
            continue
        corrs[j] = float(((a - a.mean()) @ (b - b.mean())) / (a.size * sa * sb))
    return lags, corrs, counts


def _peak(lags, corrs, exclude_zero=False):
    """Lag del pico de |corr|. None si no hay ninguna corr finita."""
    c = np.abs(corrs).astype(float)
    if exclude_zero:
        c[lags == 0] = np.nan
    if not np.any(np.isfinite(c)):
        return None
    j = int(np.nanargmax(c))
    return int(lags[j]), float(corrs[j])


def shuffle_null(ts, tgt, peer, max_lag=MAX_LAG, n_shuffle=N_SHUFFLE, seed=20260725,
                 chunk=25):
    """Null de timestamps barajados: p de que el pico observado a lag != 0 sea ruido.

    Estadístico = max_{lag != 0} |corr|. Se baraja la pata del peer n_shuffle veces
    (lo que destruye toda estructura temporal) y se recalcula el mismo estadístico.
    p = (1 + #{null >= obs}) / (1 + n_shuffle).
    Devuelve (p, obs_stat, lag_obs) o None si no hay muestra.
    """
    lags, corrs, _ = xcorr_profile(ts, tgt, peer, max_lag)
    pk = _peak(lags, corrs, exclude_zero=True)
    if pk is None:
        return None
    lag_obs, corr_obs = pk
    obs = abs(corr_obs)

    pairs = []
    for lag in lags:
        if lag == 0:
            continue
        it, ip = _lag_pairs(ts, int(lag))
        if it.size < MIN_N:
            continue
        a = tgt[it]
        sa = a.std()
        if sa <= 0:
            continue
        pairs.append((ip, (a - a.mean()) / (sa * a.size), a.size))
    if not pairs:
        return None

    rng = np.random.default_rng(seed)
    n = peer.size
    ge = 0
    done = 0
    base = np.tile(peer, (chunk, 1))
    while done < n_shuffle:
        m = min(chunk, n_shuffle - done)
        perm = rng.permuted(base[:m], axis=1)          # (m, n)
        best = np.zeros(m)
        for ip, aw, nk in pairs:
            B = perm[:, ip]                             # (m, nk)
            mu = B.mean(axis=1, keepdims=True)
            sd = B.std(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                c = np.abs((B - mu) @ aw / np.where(sd > 0, sd, np.nan))
            c = np.nan_to_num(c, nan=0.0)
            best = np.maximum(best, c)
        ge += int(np.sum(best >= obs))
        done += m
    p = (1.0 + ge) / (1.0 + n_shuffle)
    return float(p), float(corr_obs), int(lag_obs)


def residualize(y: np.ndarray, controls: list[np.ndarray]):
    """Residuos de y tras OLS sobre los controles (con intercepto).

    Devuelve (resid, r2) o None si el sistema no se puede resolver.
    """
    if not controls:
        return None
    X = np.column_stack([np.ones(y.size)] + list(controls))
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    fit = X @ beta
    resid = y - fit
    sst = float(((y - y.mean()) ** 2).sum())
    if sst <= 0:
        return None
    r2 = 1.0 - float((resid ** 2).sum()) / sst
    return resid, r2


def ols_beta(y: np.ndarray, x: np.ndarray):
    """beta = d(target)/d(peer) por OLS con intercepto, + R². None si no se puede."""
    if x.size < 2 or y.size != x.size:
        return None
    vx = float(((x - x.mean()) ** 2).sum())
    if vx <= 0:
        return None
    b = float(((x - x.mean()) @ (y - y.mean())) / vx)
    a = float(y.mean() - b * x.mean())
    resid = y - (a + b * x)
    sst = float(((y - y.mean()) ** 2).sum())
    if sst <= 0:
        return None
    return b, 1.0 - float((resid ** 2).sum()) / sst


# ---------------------------------------------------------------- por par

def pair_health(ts, tgt, peer, controls=None, max_lag=MAX_LAG, n_shuffle=N_SHUFFLE,
                seed=20260725, drop_rate=None):
    """Salud MEDIDA de un par (target, peer). Núcleo testeable — sin BD ni red.

    controls: lista de series de factor común (SMH, QQQ) ya alineadas, o None/[]
    (si no hay control disponible NO se puede descartar el pico espurio y el par
    NO puede sobrevivir: se marca con `note`).

    Ningún campo se rellena con un número plausible ante un fallo: sale None.
    """
    res = dict(
        n=int(tgt.size), drop_rate=drop_rate,
        corr=None, se=None, tstat=None, n_eff=None,
        lead_min=None, lead_corr=None, shuffle_p=None,
        resid_corr=None, resid_lead_min=None, resid_shuffle_p=None,
        resid_lag0_corr=None, beta=None, r2=None,
        lead_survives=0, note=None,
    )
    if tgt.size < MIN_N:
        res["note"] = f"muestra insuficiente (n={tgt.size} < {MIN_N})"
        return res

    h = hac_corr(tgt, peer, HAC_LAG)
    if h is not None:
        res.update(corr=h["corr"], se=h["se"], tstat=h["tstat"], n_eff=h["n_eff"])

    # ---- (1) correlación cruzada CRUDA
    lags, corrs, _ = xcorr_profile(ts, tgt, peer, max_lag)
    pk = _peak(lags, corrs)                       # pico global (puede ser lag 0)
    if pk is None:
        res["note"] = "sin correlación cruzada estimable"
        return res
    raw_lag, raw_corr = pk
    res["lead_min"] = raw_lag
    res["lead_corr"] = raw_corr

    # ---- (2) null de barajado sobre el pico a lag != 0
    sh = shuffle_null(ts, tgt, peer, max_lag, n_shuffle, seed)
    if sh is not None:
        res["shuffle_p"] = sh[0]

    # ---- (3) control de factor común: residualizar AMBAS patas y re-correlacionar
    ctrl = [c for c in (controls or [])]
    if not ctrl:
        res["note"] = "sin control de factor común disponible — pico no verificable"
    else:
        rt = residualize(tgt, ctrl)
        rp = residualize(peer, ctrl)
        if rt is None or rp is None:
            res["note"] = "residualización fallida"
        else:
            tr, pr = rt[0], rp[0]
            rlags, rcorrs, _ = xcorr_profile(ts, tr, pr, max_lag)
            rpk = _peak(rlags, rcorrs)
            j0 = int(np.nonzero(rlags == 0)[0][0])
            if np.isfinite(rcorrs[j0]):
                res["resid_lag0_corr"] = float(rcorrs[j0])
            if rpk is not None:
                res["resid_lead_min"] = rpk[0]
                res["resid_corr"] = rpk[1]
            rsh = shuffle_null(ts, tr, pr, max_lag, n_shuffle, seed + 1)
            if rsh is not None:
                res["resid_shuffle_p"] = rsh[0]
            # beta OLS sobre retornos RESIDUALIZADOS
            ob = ols_beta(tr, pr)
            if ob is not None:
                res["beta"], res["r2"] = ob

    # ---- veredicto: el pico debe sobrevivir AMBOS controles
    ok = (
        res["lead_min"] not in (None, 0)
        and res["shuffle_p"] is not None and res["shuffle_p"] < ALPHA
        and res["resid_lead_min"] is not None and res["resid_lead_min"] == res["lead_min"]
        and res["resid_shuffle_p"] is not None and res["resid_shuffle_p"] < ALPHA
        and res["resid_corr"] is not None and res["resid_lag0_corr"] is not None
        and abs(res["resid_corr"]) > abs(res["resid_lag0_corr"])
    )
    res["lead_survives"] = 1 if ok else 0
    if not ok and res["note"] is None:
        if res["lead_min"] == 0:
            res["note"] = "pico en lag 0: coincidente, no hay lead"
        elif res["shuffle_p"] is not None and res["shuffle_p"] >= ALPHA:
            res["note"] = "pico crudo indistinguible del null de barajado"
        elif res["resid_lead_min"] != res["lead_min"]:
            res["note"] = "el pico desaparece o se mueve al residualizar sobre SMH/QQQ"
        else:
            res["note"] = "el lead residual no supera al contemporáneo residual"
    return res


# ---------------------------------------------------------------- persistencia

PEER_COLS = [("se", "REAL"), ("tstat", "REAL"), ("lead_survives", "INTEGER"),
             ("shuffle_p", "REAL"), ("resid_corr", "REAL"), ("n_eff", "REAL")]


def ensure_columns(conn):
    """ALTER TABLE ADD COLUMN con guarda de 'ya existe'. NUNCA borra ni recrea."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(peer_weights)").fetchall()}
    if not have:
        raise RuntimeError("peer_weights no existe — no se crea aquí (no destruir)")
    for name, typ in PEER_COLS:
        if name not in have:
            conn.execute(f"ALTER TABLE peer_weights ADD COLUMN {name} {typ}")
    conn.commit()


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=False, allow_nan=False)
    os.rename(tmp, path)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (int,)):
        return int(v)
    f = float(v)
    return f if np.isfinite(f) else None


# ---------------------------------------------------------------- main

def run(n_shuffle=N_SHUFFLE, limit_pairs=None, bar_limit=None, verbose=True):
    conn_ro = sqlite3.connect(db_uri(), uri=True)
    pairs = conn_ro.execute(
        "SELECT target, peer FROM peer_weights ORDER BY target, abs(weight) DESC"
    ).fetchall()
    conn_ro.close()
    if limit_pairs:
        pairs = pairs[:limit_pairs]
    if not pairs:
        raise RuntimeError("peer_weights vacía — nada que endurecer")

    syms = sorted({p for pair in pairs for p in pair} | set(CONTROLS))
    if verbose:
        print(f"cargando retornos 1m de {len(syms)} símbolos...")
    series = load_returns(syms, limit=bar_limit)
    missing = [s for s in syms if s not in series]
    if verbose and missing:
        print(f"  sin datos en poly_bars: {missing}")

    detail = []
    t0 = time.time()
    for i, (tgt_sym, peer_sym) in enumerate(pairs, 1):
        ctrl_syms = [c for c in CONTROLS if c not in (tgt_sym, peer_sym) and c in series]
        keys = [tgt_sym, peer_sym] + ctrl_syms
        j = inner_join(series, keys)
        row = dict(target=tgt_sym, peer=peer_sym, controls=ctrl_syms)
        if j is None:
            row.update(n=0, drop_rate=None, lead_survives=0,
                       note="sin solape de timestamps o símbolo ausente")
            detail.append(row)
            continue
        ts, vals, drop = j
        # tasa de descarte del join SOLO entre las dos patas del par (lo que pide la ficha)
        j2 = inner_join(series, [tgt_sym, peer_sym])
        pair_drop = j2[2] if j2 is not None else None
        h = pair_health(ts, vals[tgt_sym], vals[peer_sym],
                        controls=[vals[c] for c in ctrl_syms],
                        n_shuffle=n_shuffle, drop_rate=pair_drop)
        h["drop_rate_with_controls"] = drop
        row.update(h)
        detail.append(row)
        if verbose:
            print(f"[{i}/{len(pairs)}] {tgt_sym}<-{peer_sym:5s} n={row['n']:>7} "
                  f"drop={_fmt(pair_drop)} corr={_fmt(row['corr'])} t={_fmt(row['tstat'])} "
                  f"lead={row['lead_min']} p={_fmt(row['shuffle_p'])} "
                  f"resid={_fmt(row['resid_corr'])} surv={row['lead_survives']}")

    survived = sum(1 for r in detail if r.get("lead_survives") == 1)
    drops = [r["drop_rate"] for r in detail if r.get("drop_rate") is not None]
    out = dict(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source="trades.db poly_bars (1m, ts en MILISEGUNDOS)",
        method=dict(hac_lag=HAC_LAG, max_lag_min=MAX_LAG, n_shuffle=n_shuffle,
                    alpha=ALPHA, min_n=MIN_N, controls=list(CONTROLS)),
        pairs_total=len(detail),
        pairs_survived=survived,
        drop_rate=(float(np.mean(drops)) if drops else None),
        drop_rate_min=(float(np.min(drops)) if drops else None),
        drop_rate_max=(float(np.max(drops)) if drops else None),
        decision_rule=("Cualquier consumidor puede usar SOLO pares con lead_survives=1. "
                       "Con CERO supervivientes, governing_captain() es DOCTRINA "
                       "(SPY/QQQ = mercado, SMH = semis) SIN afirmación de lead medido."),
        elapsed_s=round(time.time() - t0, 1),
        pairs=[{k: (_clean(v) if isinstance(v, (int, float, np.floating, np.integer))
                    else v) for k, v in r.items()} for r in detail],
    )
    atomic_write_json(OUT_JSON, out)

    conn_w = sqlite3.connect(DB, timeout=30)
    try:
        ensure_columns(conn_w)
        for r in detail:
            conn_w.execute(
                "UPDATE peer_weights SET se=?, tstat=?, lead_survives=?, shuffle_p=?, "
                "resid_corr=?, n_eff=? WHERE target=? AND peer=?",
                (_clean(r.get("se")), _clean(r.get("tstat")), int(r.get("lead_survives", 0)),
                 _clean(r.get("shuffle_p")), _clean(r.get("resid_corr")),
                 _clean(r.get("n_eff")), r["target"], r["peer"]))
        conn_w.commit()
    finally:
        conn_w.close()

    print(f"\n=== SALUD DE PEER_WEIGHTS === {survived}/{len(detail)} pares con lead_survives=1")
    print(f"    descarte del join por epoch: media {_fmt(out['drop_rate'])} "
          f"[{_fmt(out['drop_rate_min'])} .. {_fmt(out['drop_rate_max'])}]")
    print(f"    escrito {OUT_JSON}")
    return out


def _fmt(v):
    return "None" if v is None else f"{v:.4f}"


def main():
    ap = argparse.ArgumentParser(description="Endurecimiento medido de peer_weights")
    ap.add_argument("--shuffles", type=int, default=N_SHUFFLE)
    ap.add_argument("--limit", type=int, default=None, help="solo los N primeros pares")
    ap.add_argument("--bar-limit", type=int, default=None, help="LIMIT de barras por símbolo")
    a = ap.parse_args()
    run(n_shuffle=a.shuffles, limit_pairs=a.limit, bar_limit=a.bar_limit)


if __name__ == "__main__":
    main()
