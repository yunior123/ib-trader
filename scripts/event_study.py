#!/usr/bin/env python3
"""event_study.py — arnes REUSABLE de event-study / grading de señales.

Mide una señal como la casa la mide (doctrina measured-probability): FIRST-TOUCH
(que barrera se toca primero, favorable vs adversa — no retorno a horizonte, que
no ve el stop en el camino), MFE>MAE como metrica de honestidad, Wilson SOLO
sobre la muestra RESUELTA (el timeout/unresolved NO cuenta en el denominador), y
un loop de estabilidad por año. Se usa para GRADUAR una señal antes de darle voz
(p.ej. gatear reversal_router): si n resuelta < min_n, NO se publica probabilidad.

Distinto de barrier_labels.py (triple barrera sobre trades.db signals -> tabla
SQLite con coste) y de backtest_harness.py (WR neto): esto es una libreria
liviana, sin BD, que grada CUALQUIER lista de eventos (symbol, epoch, direccion)
contra las barras 1m vivas data/bars_<sym>_ibkr.txt. Comparte la doctrina, no el
almacenamiento.

FAIL-LOUD (~/CLAUDE.md): ninguna funcion devuelve 0/0.5/50/{} ante datos
ausentes. wilson levanta si n<=0; grade_signal devuelve None por debajo de min_n
(no una probabilidad fabricada); mfe_mae/first_touch devuelven None/'unresolved'
si no hay ruta. Cada evento descartado en el CLI se cuenta con su motivo.
SEÑAL-SOLAMENTE: solo lee barras; jamas ordena nada.

  python3 scripts/event_study.py grade events.json          # events.json = lista de eventos
  python3 scripts/event_study.py grade - < events.csv       # SYM,EPOCH,DIR por linea
  python3 scripts/event_study.py grade events.json --out data/grade.json
"""
import argparse
import bisect
import json
import math
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")

MIN_N = 30              # n RESUELTA minima para publicar prob (doctrina n>=30)
ATR_PERIOD = 14        # barras para el Wilder ATR
ATR_FRAC = 1.0         # barrera = entry +/- ATR_FRAC * ATR
HORIZON = 30           # barras hacia delante (1m -> 30 min)
ENTRY_MAX_STALE_S = 900  # el close-entry no puede estar a mas de 15 min del epoch


# ============================================================================
# Primitivas
# ============================================================================
def wilson(k, n, z=1.96):
    """Wilson CI. Devuelve (p, lo, hi) en FRACCION (misma convencion que
    calibration_ledger.wilson). Levanta si n<=0: no hay tasa que inventar."""
    if n <= 0:
        raise ValueError("wilson: n<=0, no hay muestra (fail-loud, no 0.5)")
    if not (0 <= k <= n):
        raise ValueError("wilson: k=%r fuera de [0,%r]" % (k, n))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, (c - m) / d, (c + m) / d


def first_touch(prices, entry_idx, up_thr, dn_thr, horizon):
    """Que barrera de PRECIO se toca primero en (entry_idx, entry_idx+horizon].
    up_thr = barrera favorable (arriba), dn_thr = barrera adversa (abajo), en
    niveles ABSOLUTOS. Devuelve 'favorable' | 'adverse' | 'unresolved'.
    Camino close-based (sin ambiguedad intrabar). Para eventos direccionales usa
    resolve_event, que fija up/dn y mapea la etiqueta segun la direccion."""
    prices = np.asarray(prices, dtype=float)
    n = len(prices)
    if entry_idx < 0 or entry_idx >= n:
        raise IndexError("entry_idx %d fuera de rango (n=%d)" % (entry_idx, n))
    if not (up_thr > dn_thr):
        raise ValueError("up_thr (%r) debe ser > dn_thr (%r)" % (up_thr, dn_thr))
    end = min(n, entry_idx + 1 + int(horizon))
    for i in range(entry_idx + 1, end):
        p = prices[i]
        if p >= up_thr:
            return "favorable"
        if p <= dn_thr:
            return "adverse"
    return "unresolved"


def mfe_mae(prices, entry_idx, horizon, direction=1, entry=None):
    """Excursion favorable/adversa maxima en la ventana, en unidades de PRECIO.
    direction +1 = tesis alcista, -1 = bajista. Devuelve
    dict(mfe, mae, mfe_gt_mae) o None si no hay ruta (jamas 0 fabricado)."""
    if direction not in (1, -1):
        raise ValueError("direction debe ser +1 o -1, no %r" % (direction,))
    prices = np.asarray(prices, dtype=float)
    n = len(prices)
    if entry_idx < 0 or entry_idx >= n:
        raise IndexError("entry_idx %d fuera de rango (n=%d)" % (entry_idx, n))
    if entry is None:
        entry = float(prices[entry_idx])
    seg = prices[entry_idx + 1: entry_idx + 1 + int(horizon)]
    if len(seg) == 0:
        return None
    d = direction
    fav = d * (seg - entry)          # excursion a favor de la tesis
    mfe = float(max(0.0, fav.max()))
    mae = float(max(0.0, (-fav).max()))
    return dict(mfe=mfe, mae=mae, mfe_gt_mae=bool(mfe > mae))


def resolve_event(prices, entry_idx, direction, up_thr, dn_thr, horizon,
                  entry=None):
    """Resuelve un evento direccional: first-touch mapeado por direccion +
    MFE/MAE. up_thr/dn_thr son niveles de precio (up_thr>dn_thr). Para un short
    (-1) la etiqueta geometrica se invierte (tocar abajo = favorable)."""
    geo = first_touch(prices, entry_idx, up_thr, dn_thr, horizon)
    if direction == -1:
        geo = {"favorable": "adverse", "adverse": "favorable",
               "unresolved": "unresolved"}[geo]
    mm = mfe_mae(prices, entry_idx, horizon, direction, entry)
    out = dict(outcome=geo)
    if mm is not None:
        out.update(mm)
    return out


# ============================================================================
# Grading
# ============================================================================
def grade_signal(events, min_n=MIN_N):
    """Grada una lista de eventos ya resueltos. Cada evento: dict con 'outcome'
    ('favorable'|'adverse'|'unresolved'), opcional 'mfe_gt_mae' (bool) y 'year'.
    Wilson SOLO sobre la muestra resuelta (favorable+adverse). Devuelve None si
    n_resolved < min_n (fail-loud: sin muestra no se publica probabilidad).

    -> {win_rate, wilson_lo, wilson_hi, n_resolved, n_total, n_unresolved,
        mfe_gt_mae_pct, by_year, min_n}
    by_year: {año: stats|{'status':'INSUFFICIENT_N',...}} — diagnostico de
    estabilidad; los años flacos se marcan, no se publican."""
    resolved = [e for e in events if e.get("outcome") in ("favorable", "adverse")]
    n = len(resolved)
    n_total = len(events)
    n_unresolved = sum(1 for e in events if e.get("outcome") == "unresolved")
    if n < min_n:
        return None
    k = sum(1 for e in resolved if e["outcome"] == "favorable")
    p, lo, hi = wilson(k, n)
    mfe_flags = [bool(e["mfe_gt_mae"]) for e in events if e.get("mfe_gt_mae") is not None]
    mfe_pct = (100.0 * sum(mfe_flags) / len(mfe_flags)) if mfe_flags else None
    return dict(
        win_rate=round(p, 4), wilson_lo=round(lo, 4), wilson_hi=round(hi, 4),
        n_resolved=n, n_total=n_total, n_unresolved=n_unresolved,
        favorable=k,
        mfe_gt_mae_pct=(round(mfe_pct, 2) if mfe_pct is not None else None),
        by_year=_by_year(resolved, min_n), min_n=min_n)


def _by_year(resolved, min_n):
    years = {}
    for e in resolved:
        y = e.get("year")
        if y is None:
            continue
        years.setdefault(y, []).append(e)
    out = {}
    for y in sorted(years):
        g = years[y]
        n = len(g)
        if n < min_n:
            out[y] = dict(status="INSUFFICIENT_N", n_resolved=n, win_rate=None)
            continue
        k = sum(1 for e in g if e["outcome"] == "favorable")
        p, lo, hi = wilson(k, n)
        out[y] = dict(win_rate=round(p, 4), wilson_lo=round(lo, 4),
                      wilson_hi=round(hi, 4), n_resolved=n)
    return out


# ============================================================================
# Barras + ATR (para el CLI)
# ============================================================================
def bars_path(symbol):
    return os.path.join(DATA, "bars_%s_ibkr.txt" % symbol.lower())


def load_bars(path):
    """Lee 'epoch o h l c v' por linea. Devuelve (ts, o, h, l, c) como arrays
    numpy ordenados por ts. Levanta si el fichero no existe (fail-loud)."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ts, o, h, l, c = [], [], [], [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 5:
                continue
            ts.append(int(float(p[0]))); o.append(float(p[1]))
            h.append(float(p[2])); l.append(float(p[3])); c.append(float(p[4]))
    idx = np.argsort(ts)
    A = lambda v: np.asarray(v)[idx]
    return A(ts), A(o), A(h), A(l), A(c)


def wilder_atr_at(h, l, c, idx, period=ATR_PERIOD):
    """ATR14 de Wilder causal en la barra idx (incluida). None si no hay period
    barras previas suficientes — jamas un ATR inventado."""
    if idx < period:
        return None
    tr = np.empty(idx + 1)
    tr[0] = h[0] - l[0]
    hl = h[1:idx + 1] - l[1:idx + 1]
    hc = np.abs(h[1:idx + 1] - c[0:idx])
    lc = np.abs(l[1:idx + 1] - c[0:idx])
    tr[1:] = np.maximum.reduce([hl, hc, lc])
    atr = tr[1:period + 1].mean()
    for i in range(period + 1, idx + 1):
        atr = (atr * (period - 1) + tr[i]) / period
    return float(atr)


def _dir(v):
    """Normaliza direccion: +1 (long/call/bull) | -1 (short/put/bear) | None."""
    if isinstance(v, (int, float)):
        return 1 if v > 0 else (-1 if v < 0 else None)
    s = str(v).strip().lower()
    if s in ("1", "+1", "long", "call", "bull", "up", "buy"):
        return 1
    if s in ("-1", "short", "put", "bear", "down", "sell"):
        return -1
    return None


def grade_events(raw, horizon=HORIZON, atr_frac=ATR_FRAC, atr_period=ATR_PERIOD,
                 min_n=MIN_N):
    """raw: lista de (symbol, entry_epoch, direction). Resuelve cada uno contra
    bars_<sym>_ibkr.txt y grada. Devuelve (grade, resolved_events, stats).
    Cada descarte se cuenta con motivo — nunca un except silencioso."""
    from collections import defaultdict
    st = defaultdict(int)
    bars_cache = {}
    resolved = []
    for symbol, epoch, direction in raw:
        st["total"] += 1
        d = _dir(direction)
        if d is None:
            st["skip_no_direction"] += 1
            continue
        sym = str(symbol)
        if sym not in bars_cache:
            try:
                bars_cache[sym] = load_bars(bars_path(sym))
            except FileNotFoundError:
                bars_cache[sym] = None
        b = bars_cache[sym]
        if b is None:
            st["skip_no_bars_file"] += 1
            continue
        ts, o, h, l, c = b
        if len(ts) == 0:
            st["skip_empty_bars"] += 1
            continue
        i = bisect.bisect_right(ts.tolist(), int(epoch)) - 1
        if i < 0:
            st["skip_no_prior_bar"] += 1
            continue
        if int(epoch) - int(ts[i]) > ENTRY_MAX_STALE_S:
            st["skip_entry_stale"] += 1
            continue
        entry = float(c[i])
        if not (entry > 0):
            st["skip_entry_nonpositive"] += 1
            continue
        atr = wilder_atr_at(h, l, c, i, atr_period)
        if atr is None or not (atr > 0):
            st["skip_atr_insufficient"] += 1
            continue
        if i + 1 >= len(c):
            st["skip_no_forward_bars"] += 1
            continue
        up = entry + atr_frac * atr
        dn = entry - atr_frac * atr
        ev = resolve_event(c, i, d, up, dn, horizon, entry=entry)
        ev.update(symbol=sym, entry_epoch=int(epoch), direction=d, entry=entry,
                  atr=round(atr, 6), year=time.gmtime(int(epoch)).tm_year)
        resolved.append(ev)
        st["resolved" if ev["outcome"] != "unresolved" else "unresolved"] += 1
        st["graded"] += 1
    grade = grade_signal(resolved, min_n)
    return grade, resolved, dict(st)


# ============================================================================
# CLI
# ============================================================================
def _read_events(spec):
    """spec: ruta a JSON (lista de [sym,epoch,dir] o dicts) o '-' para stdin CSV
    'SYM,EPOCH,DIR'. Devuelve lista de tuplas (sym, epoch, dir)."""
    if spec == "-":
        text = sys.stdin.read()
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = [x.strip() for x in line.split(",")]
            if len(p) < 3:
                raise SystemExit("linea invalida (SYM,EPOCH,DIR): %r" % line)
            rows.append((p[0], float(p[1]), p[2]))
        return rows
    with open(spec) as f:
        data = json.load(f)
    rows = []
    for e in data:
        if isinstance(e, dict):
            rows.append((e["symbol"], float(e["entry_epoch"]),
                         e.get("direction", e.get("dir"))))
        else:
            rows.append((e[0], float(e[1]), e[2]))
    return rows


def _atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def cmd_grade(args):
    raw = _read_events(args.events)
    grade, resolved, st = grade_events(
        raw, horizon=args.horizon, atr_frac=args.atr_frac,
        atr_period=args.atr_period, min_n=args.min_n)
    print("=== event_study grade === (horizon=%d bars, atr_frac=%.2f, min_n=%d)"
          % (args.horizon, args.atr_frac, args.min_n))
    print("  eventos ................... %d" % st.get("total", 0))
    for k in ("skip_no_direction", "skip_no_bars_file", "skip_empty_bars",
              "skip_no_prior_bar", "skip_entry_stale", "skip_entry_nonpositive",
              "skip_atr_insufficient", "skip_no_forward_bars"):
        if st.get(k):
            print("  %-26s %d" % (k, st[k]))
    print("  GRADUADOS ................. %d (resueltos %d, sin resolver %d)"
          % (st.get("graded", 0), st.get("resolved", 0), st.get("unresolved", 0)))
    if grade is None:
        n = sum(1 for e in resolved if e["outcome"] in ("favorable", "adverse"))
        print("  -> INSUFFICIENT_N: %d resueltos < min_n=%d — SIN probabilidad"
              % (n, args.min_n))
    else:
        print("  win_rate ..... %.3f  Wilson [%.3f, %.3f]  (n resuelta=%d)"
              % (grade["win_rate"], grade["wilson_lo"], grade["wilson_hi"],
                 grade["n_resolved"]))
        print("  MFE>MAE ...... %s%%   (honestidad)"
              % (grade["mfe_gt_mae_pct"] if grade["mfe_gt_mae_pct"] is not None else "—"))
        if grade["by_year"]:
            print("  estabilidad por año:")
            for y, s in grade["by_year"].items():
                if s.get("win_rate") is None:
                    print("    %s  INSUFFICIENT_N (n=%d)" % (y, s["n_resolved"]))
                else:
                    print("    %s  WR %.3f [%.3f,%.3f] n=%d"
                          % (y, s["win_rate"], s["wilson_lo"], s["wilson_hi"],
                             s["n_resolved"]))
    if args.out:
        _atomic_write(args.out, dict(grade=grade, n_events=len(raw),
                                     discards=st, params=dict(
                                         horizon=args.horizon,
                                         atr_frac=args.atr_frac,
                                         atr_period=args.atr_period,
                                         min_n=args.min_n)))
        print("  -> %s" % args.out)


def main():
    ap = argparse.ArgumentParser(description="event-study / signal grading harness")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("grade", help="grada eventos (symbol,epoch,dir) vs barras")
    g.add_argument("events", help="ruta JSON o '-' para CSV por stdin")
    g.add_argument("--horizon", type=int, default=HORIZON)
    g.add_argument("--atr-frac", type=float, default=ATR_FRAC)
    g.add_argument("--atr-period", type=int, default=ATR_PERIOD)
    g.add_argument("--min-n", type=int, default=MIN_N)
    g.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "grade":
        cmd_grade(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
