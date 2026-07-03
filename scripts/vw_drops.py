#!/usr/bin/env python3
"""vw_drops.py — ficha 4 (designs-trendspider.md) `vw-drops`: series OHLC ponderadas
por volumen (matematica raindrop, sin el chart). `open=leftVWAP`, `close=rightVWAP`,
`oc2=(L+R)/2`, `mass=VWAP del periodo completo`. Solo se roba la mecanica: el propio
white paper de raindrop mide sus PATRONES a -0.16% en 66 trades, asi que esos NO se
copian aqui.

Periodo minimo 10m (no hay datos sub-1m persistidos). Balloon test y `flip`/migracion
temprana son heuristicas propias, documentadas como tal (el vendor no publica la
formula exacta).

SEÑAL-SOLAMENTE. Ningun `except` de este fichero devuelve 0/0.0/0.5/{} — None o levanta.

Uso:
  python3 scripts/vw_drops.py                 # data/vwdrops_<sym>.json (ultimos periodos)
  python3 scripts/vw_drops.py --validate       # %B precio vs %B VW, veredicto medido
"""
from __future__ import annotations

import argparse
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gaps as G  # noqa: E402  (fleet, _ro, load_daily, load_session_1m, atomic_write, _wilson)

DATA = os.path.join(REPO, "data")

MIN_SUBBARS = 5
BALLOON_FRAC = 0.60
BALLOON_VOLFRAC = 0.80
FLIP_FULL = 0.50
FLIP_PARTIAL = 0.33
PCTB_N = 20
PCTB_K = 2.0
EXTREME_HI = 0.95
EXTREME_LO = 0.05
REVERT_H = 8          # periodos (15m) para juzgar reversion = ~2h
KEEP_EDGE = 0.03       # +3pp minimo para KEEP (ficha 4)


# ------------------------------------------------------------------- raindrop
def _typ(b):
    return (b[2] + b[3] + b[4]) / 3.0


def _vwap(bars):
    v = [b[5] or 0.0 for b in bars]
    tv = sum(v)
    if tv <= 0:
        return None
    return sum(_typ(b) * w for b, w in zip(bars, v)) / tv


def _vol_frac_above(bars, threshold):
    tot = 0.0
    above = 0.0
    for b in bars:
        h, lo, v = b[2], b[3], (b[5] or 0.0)
        tot += v
        if v <= 0:
            continue
        if h <= lo:
            above += v if lo >= threshold else 0.0
            continue
        frac = max(0.0, min(1.0, (h - max(lo, threshold)) / (h - lo)))
        above += v * frac
    if tot <= 0:
        return None
    return above / tot


def raindrop(bars):
    """Un periodo. `bars` = [(ts,o,h,l,c,v), ...] 1m, cronologico, UNA sesion.
    None si no hay volumen o hay menos de MIN_SUBBARS sub-barras por mitad."""
    n = len(bars)
    half = n // 2
    if half < 2 or (n - half) < 2:
        return None
    left, right = bars[:half], bars[half:]
    lv, rv = _vwap(left), _vwap(right)
    if lv is None or rv is None:
        return None
    hi = max(b[2] for b in bars)
    lo = min(b[3] for b in bars)
    rng = hi - lo
    if rng <= 0:
        return None
    mass = _vwap(bars)
    if mass is None:
        return None
    oc2 = (lv + rv) / 2.0
    flip = (rv - lv) / rng
    color = "GREEN" if rv > lv else ("RED" if rv < lv else "DOJI")
    flip_state = "FULL" if abs(flip) >= FLIP_FULL else (
        "PARTIAL" if abs(flip) >= FLIP_PARTIAL else "NONE")
    threshold = lo + BALLOON_FRAC * rng
    vf = _vol_frac_above(bars, threshold)
    balloon = bool(lv > threshold and rv > threshold and vf is not None
                   and vf >= BALLOON_VOLFRAC)
    return dict(t=bars[0][0], lv=round(lv, 4), rv=round(rv, 4), h=round(hi, 4),
                l=round(lo, 4), mass=round(mass, 4), oc2=round(oc2, 4), color=color,
                flip=round(flip, 4), flip_state=flip_state, balloon=balloon,
                n_bars=n, vol=round(sum((b[5] or 0.0) for b in bars), 2))


def migration_live(partial_second_half, left_vwap, hi, lo):
    """Migracion LEIBLE a mitad de periodo: (rightVWAP parcial - leftVWAP) / rango.
    None si no hay barras o volumen en la mitad derecha vista hasta ahora."""
    rng = hi - lo
    if rng <= 0 or not partial_second_half:
        return None
    rv = _vwap(partial_second_half)
    if rv is None:
        return None
    return (rv - left_vwap) / rng


def session_periods(bars1m, period_min=15):
    """Trocea `bars1m` (UNA sesion) en bloques de `period_min` minutos. Descarta el
    ultimo bloque si tiene <MIN_SUBBARS barras (no es un periodo completo)."""
    if period_min < 10:
        raise ValueError("period_min < 10: no hay datos sub-1m, prohibido inventar")
    out = []
    for i in range(0, len(bars1m), period_min):
        chunk = bars1m[i:i + period_min]
        if len(chunk) >= MIN_SUBBARS:
            out.append(chunk)
    return out


def raindrop_series_session(bars1m, period_min=15):
    return [d for c in session_periods(bars1m, period_min)
            if (d := raindrop(c)) is not None]


# ------------------------------------------------------------------------ %B
def rolling_pctb(vals, n=PCTB_N, k=PCTB_K):
    """%B = (x - lower)/(upper-lower) sobre SMA/std poblacional de ventana `n`.
    None donde no hay ventana completa o la banda es plana (std<=0)."""
    out = [None] * len(vals)
    for i in range(len(vals)):
        if i + 1 < n:
            continue
        w = vals[i - n + 1:i + 1]
        m = sum(w) / n
        var = sum((x - m) ** 2 for x in w) / n
        sd = math.sqrt(var)
        if sd <= 0:
            continue
        lo, hi = m - k * sd, m + k * sd
        out[i] = (vals[i] - lo) / (hi - lo)
    return out


# ------------------------------------------------------------------- historia
def _all_sessions_drops(conn, sym, period_min=15):
    """Todas las sesiones (dia -> lista de raindrops) de `sym` desde poly_bars."""
    daily = G.load_daily(conn, sym)
    out = []
    for d in daily:
        bars = G.load_session_1m(conn, sym, d["date"])
        if len(bars) < period_min * MIN_SUBBARS:
            continue
        drops = raindrop_series_session(bars, period_min)
        if drops:
            out.append((d["date"], drops))
    return out


def _label_reversion(pctb, i, side, horizon=REVERT_H):
    """side=+1 (extremo alto): reversion = %B cruza <=0.5 dentro de `horizon`.
    side=-1: cruza >=0.5. None si no hay suficientes periodos por delante (timeout
    NO se cuenta como win NI como loss: se excluye, igual que barrier_labels)."""
    end = i + horizon
    if end >= len(pctb):
        return None
    window = pctb[i + 1:end + 1]
    if any(x is None for x in window):
        return None
    if side > 0:
        return any(x <= 0.5 for x in window)
    return any(x >= 0.5 for x in window)


def _events_for_series(dates_drops, extractor):
    """`extractor(drop)->float` (precio close o oc2). El %B rolling y el horizonte
    de reversion corren CONTINUOS sobre la concatenacion cronologica de periodos de
    todas las sesiones (20 periodos de warmup + 8 de horizonte no caben dentro de
    una sola sesion de ~26 periodos de 15m: resetear por sesion deja CERO eventos
    medibles, verificado). Un evento cerca del cierre puede mirar al dia siguiente
    para su reversion -- se documenta, no se oculta."""
    flat = []
    for date, drops in dates_drops:
        for d in drops:
            flat.append((date, extractor(d)))
    if not flat:
        return []
    pb = rolling_pctb([v for _, v in flat])
    ev = []
    for i, p in enumerate(pb):
        if p is None:
            continue
        side = 1 if p >= EXTREME_HI else (-1 if p <= EXTREME_LO else 0)
        if side == 0:
            continue
        hit = _label_reversion(pb, i, side)
        if hit is None:
            continue
        ev.append((flat[i][0], side, hit))
    return ev


def _bootstrap_edge(price_by_day, vw_by_day, all_days, n_boot=2000, seed=20260726):
    """Bootstrap por BLOQUE-DIA (respeta la correlacion intra-sesion y entre-flota):
    remuestrea dias con reemplazo, recalcula price_rate/vw_rate/edge cada vez."""
    import random
    rng = random.Random(seed)
    days = list(all_days)
    if not days:
        return None
    edges = []
    for _ in range(n_boot):
        sample = [days[rng.randrange(len(days))] for _ in range(len(days))]
        pn = ph = vn = vh = 0
        for d in sample:
            pn += len(price_by_day.get(d, []))
            ph += sum(1 for x in price_by_day.get(d, []) if x)
            vn += len(vw_by_day.get(d, []))
            vh += sum(1 for x in vw_by_day.get(d, []) if x)
        if pn == 0 or vn == 0:
            continue
        edges.append(vh / vn - ph / pn)
    if not edges:
        return None
    edges.sort()
    lo_i = int(0.025 * len(edges))
    hi_i = int(0.975 * len(edges))
    return edges[lo_i], edges[min(hi_i, len(edges) - 1)]


def validate(syms=None, period_min=15, db=G.DB):
    conn = G._ro(db)
    syms = syms or G.fleet()
    price_by_day, vw_by_day = {}, {}
    n_price_raw = n_vw_raw = 0
    price_hits = vw_hits = 0
    per_sym = {}
    for sym in syms:
        dd = _all_sessions_drops(conn, sym, period_min)
        if len(dd) < 30:
            per_sym[sym] = {"n_sessions": len(dd), "why": "historia insuficiente (<30 sesiones)"}
            continue
        # precio de referencia = rv (rightVWAP, cierre del periodo); VW = oc2
        pe = _events_for_series(dd, lambda d: d["rv"])
        ve = _events_for_series(dd, lambda d: d["oc2"])
        for date, _side, hit in pe:
            price_by_day.setdefault(date, []).append(hit)
            n_price_raw += 1
            price_hits += 1 if hit else 0
        for date, _side, hit in ve:
            vw_by_day.setdefault(date, []).append(hit)
            n_vw_raw += 1
            vw_hits += 1 if hit else 0
        per_sym[sym] = {"n_sessions": len(dd), "price_events": len(pe), "vw_events": len(ve)}
    conn.close()

    all_days = sorted(set(price_by_day) | set(vw_by_day))
    n_dias = len(all_days)
    if n_price_raw == 0 or n_vw_raw == 0 or n_dias == 0:
        return dict(verdict="DATA-INSUFFICIENT", per_sym=per_sym, n_dias=n_dias)

    price_rate = price_hits / n_price_raw
    vw_rate = vw_hits / n_vw_raw
    edge = vw_rate - price_rate
    # Wilson CRUDO sobre n_raw (eventos): el sym-dia NO es independiente (mismo
    # patron que gaps.py), asi que esto es ANTICONSERVADOR y se etiqueta como tal.
    # `n_dias` (dias distintos con >=1 evento) se reporta aparte como el n honesto.
    p_p, p_lo, p_hi = G._wilson(price_hits, n_price_raw)
    v_p, v_lo, v_hi = G._wilson(vw_hits, n_vw_raw)
    sep_lb = v_lo - p_hi        # separacion CONSERVADORA (LB-UB), igual que gaps.py
    boot = _bootstrap_edge(price_by_day, vw_by_day, all_days)
    edge_lo, edge_hi = boot if boot else (None, None)

    if edge_lo is not None and edge_lo >= KEEP_EDGE:
        verdict = "KEEP"
    elif edge_hi is not None and edge_hi < 0:
        verdict = "DEAD"
    else:
        verdict = "UNPROVEN"

    return dict(
        verdict=verdict,
        n_price_raw=n_price_raw, n_vw_raw=n_vw_raw, n_dias=n_dias,
        price_rate=round(price_rate, 4), vw_rate=round(vw_rate, 4),
        price_wilson_raw=[round(price_rate, 4), round(p_lo, 4), round(p_hi, 4)],
        vw_wilson_raw=[round(vw_rate, 4), round(v_lo, 4), round(v_hi, 4)],
        sep_lb_raw=round(sep_lb, 4),
        edge=round(edge, 4), edge_ci_boot_by_day=[round(edge_lo, 4), round(edge_hi, 4)]
        if edge_lo is not None else None,
        horizon_periods=REVERT_H, period_min=period_min,
        extreme_hi=EXTREME_HI, extreme_lo=EXTREME_LO,
        method="%B extremo (rolling n=20) -> reversion <=8 periodos, precio(rv) vs VW(oc2). "
               "Wilson RAW sobre n_price_raw/n_vw_raw es anticonservador (sym-dia "
               "correlacionado); veredicto se decide por el bootstrap por bloque-dia "
               "(2000 remuestreos, respeta correlacion intra-sesion y entre-flota).",
        per_sym=per_sym,
    )


# ------------------------------------------------------------------------- live
def build_live(syms=None, period_min=15, lookback_periods=40, db=G.DB):
    conn = G._ro(db)
    syms = syms or G.fleet()
    out = {"_meta": {"period_min": period_min, "src": "poly_bars (ultima sesion archivada)"}}
    for sym in syms:
        daily = G.load_daily(conn, sym)
        if not daily:
            out[sym] = None
            continue
        last_date = daily[-1]["date"]
        bars = G.load_session_1m(conn, sym, last_date)
        drops = raindrop_series_session(bars, period_min)
        if not drops:
            out[sym] = None
            continue
        drops = drops[-lookback_periods:]
        close_series = [d["rv"] for d in drops]
        vw_series = [d["oc2"] for d in drops]
        pctb_price = rolling_pctb(close_series)
        pctb_vw = rolling_pctb(vw_series)
        out[sym] = {
            "date": last_date, "drops": drops,
            "pctB_price": pctb_price[-1], "pctB_vw": pctb_vw[-1],
        }
    conn.close()
    G.atomic_write(os.path.join(DATA, "vwdrops.json"), out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--period-min", type=int, default=15)
    ap.add_argument("--sym", default=None)
    a = ap.parse_args()
    syms = [a.sym.upper()] if a.sym else None
    if a.validate:
        res = validate(syms, a.period_min)
        print(f"veredicto={res.get('verdict')} n_dias={res.get('n_dias')} "
              f"price_rate={res.get('price_rate')} vw_rate={res.get('vw_rate')} "
              f"edge={res.get('edge')} ci={res.get('edge_ci')}")
        G.atomic_write(os.path.join(DATA, "vwdrops_validate.json"), res)
    else:
        build_live(syms, a.period_min)


if __name__ == "__main__":
    main()
