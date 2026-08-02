#!/usr/bin/env python3
"""reversal_grade.py — GRADUA (no cablea) el reversal_router contra 2 años de barras 1m.

reversal_router es SHADOW/UNVALIDATED: sin edge MEDIDO no puede hablar. Esto lo mide.
Replay historico bar a bar sobre poly_bars (data/trades.db, READ-ONLY, 8.9M barras 1m
2024-07→2026-07) — no sobre data/bars_*_ibkr.txt, que son cortas y por eso el router en
vivo dice INSUFFICIENT_DATA. Emite un evento por cada TRANSICION a REVERSAL_CONFIRMED o
CONTINUATION_ACTIVE_DO_NOT_FADE y lo grada con scripts/event_study.py (first-touch triple
barrera ±ATR de Wilder, Wilson SOLO sobre la muestra RESUELTA, desglose por año).

No-repaint: usa reversal_router.features()/state_at(), cuyas series dependen solo de x[0..i]
(buckets HTF COMPLETOS). El estado en la barra i es el que el router habria dicho en vivo.

FAIL-LOUD: si n resuelta < min_n el veredicto es DATA-INSUFFICIENT y NO se publica ninguna
probabilidad (el bucket sale sin win_rate). Ningun except devuelve 0/0.5/50.
SEÑAL-SOLAMENTE / SIN CABLEAR: escribe data/reversal_grade.json con wired=false. No importa
ni emite a fleet_notify / fleet_consensus / order_engine ni a voz.

  ./venv/bin/python scripts/reversal_grade.py [SYMS...] [--out data/reversal_grade.json]
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import event_study as es  # noqa: E402
import reversal_router as rr  # noqa: E402

DB = os.path.join(DATA, "trades.db")
OUT = os.path.join(DATA, "reversal_grade.json")

GRADED_STATES = ("REVERSAL_CONFIRMED", "CONTINUATION_ACTIVE_DO_NOT_FADE")
NULL_P = 0.50   # barrera simetrica ±1 ATR => la moneda es 0.50; PASS exige que Wilson lo supere
VERDICT_RULE = ("PASS si wilson_lo > %.2f (el CI excluye la moneda); FAIL si no; "
                "DATA-INSUFFICIENT si n resuelta < min_n (sin probabilidad publicada)" % NULL_P)


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


# ------------------------------------------------------------------ resolucion (event_study como libreria)
def resolve_symbol(sym: str, bars_1m: np.ndarray, events, *, horizon, atr_frac, atr_period):
    """Resuelve los eventos de un simbolo contra SUS barras 1m con las primitivas de
    event_study (misma triple barrera que el resto de la casa). Devuelve (resueltos, stats)
    con un motivo contado por cada descarte."""
    from collections import defaultdict
    st = defaultdict(int)
    ts = bars_1m[:, 0].astype(np.int64)
    h, l, c = bars_1m[:, 2], bars_1m[:, 3], bars_1m[:, 4]
    ts_list = ts.tolist()
    resolved = []
    for ev in events:
        st["total"] += 1
        i = bisect.bisect_right(ts_list, int(ev["ts"])) - 1
        if i < 0:
            st["skip_no_prior_bar"] += 1
            continue
        if int(ev["ts"]) - ts_list[i] > es.ENTRY_MAX_STALE_S:
            st["skip_entry_stale"] += 1
            continue
        entry = float(c[i])
        if not (entry > 0):
            st["skip_entry_nonpositive"] += 1
            continue
        atr = es.wilder_atr_at(h, l, c, i, atr_period)
        if atr is None or not (atr > 0):
            st["skip_atr_insufficient"] += 1
            continue
        if i + 1 >= len(c):
            st["skip_no_forward_bars"] += 1
            continue
        r = es.resolve_event(c, i, ev["direction"], entry + atr_frac * atr,
                             entry - atr_frac * atr, horizon, entry=entry)
        r.update(symbol=sym.upper(), entry_epoch=int(ev["ts"]), direction=ev["direction"],
                 entry=entry, atr=round(atr, 6), state=ev["state"],
                 year=time.gmtime(int(ev["ts"])).tm_year)
        resolved.append(r)
        st["resolved" if r["outcome"] != "unresolved" else "unresolved"] += 1
        st["graded"] += 1
    return resolved, dict(st)


# ------------------------------------------------------------------ grading + veredicto
def bucket_grade(resolved, min_n):
    """Grada un bucket. Sin muestra suficiente NO publica probabilidad: solo n y veredicto."""
    g = es.grade_signal(resolved, min_n)
    n_res = sum(1 for e in resolved if e.get("outcome") in ("favorable", "adverse"))
    if g is None:
        return dict(verdict="DATA-INSUFFICIENT", n_events=len(resolved), n_resolved=n_res,
                    n_unresolved=sum(1 for e in resolved if e.get("outcome") == "unresolved"),
                    min_n=min_n)
    out = dict(g)
    out["verdict"] = "PASS" if g["wilson_lo"] > NULL_P else "FAIL"
    out["n_events"] = len(resolved)
    return out


def build_report(resolved, *, symbols, discards, horizon, atr_frac, atr_period, min_n,
                 events_raw, per_symbol):
    buckets = {"ALL": bucket_grade(resolved, min_n)}
    for stname in GRADED_STATES:
        buckets[stname] = bucket_grade([e for e in resolved if e.get("state") == stname], min_n)
    return dict(
        generated=datetime.now(timezone.utc).isoformat(),
        epoch=int(time.time()),
        wired=False,          # el router sigue en SOMBRA: esto no lo cablea a nada
        shadow=True,
        source="poly_bars (data/trades.db, read-only) — barras 1m 04:00-19:59 ET",
        params=dict(horizon_bars_1m=horizon, atr_frac=atr_frac, atr_period=atr_period,
                    min_n=min_n, null_p=NULL_P, verdict_rule=VERDICT_RULE,
                    graded_states=list(GRADED_STATES),
                    event_def="transicion de estado (no cada barra en estado)",
                    entry_def="close de la barra 1m que cierra el bucket 5m del evento"),
        symbols=symbols,
        events_raw=events_raw,
        discards=discards,
        buckets=buckets,
        per_symbol=per_symbol,
    )


def atomic_write(path: str, obj: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


# ------------------------------------------------------------------ CLI
def _universe(argv):
    if argv:
        return [s.upper() for s in argv]
    p = os.path.join(DATA, "fleet.txt")
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return [s.upper() for s in open(p).read().split()]


def run(syms, *, horizon, atr_frac, atr_period, min_n, out):
    from collections import defaultdict
    conn = open_db(DB)
    all_resolved = []
    discards = defaultdict(int)
    per_symbol = {}
    used = []
    events_raw = 0
    try:
        for sym in syms:
            t0 = time.time()
            bars = load_poly_1m(sym, conn)
            if bars is None:
                discards["skip_no_bars_in_db"] += 1
                print("%-6s sin barras en poly_bars" % sym, flush=True)
                continue
            evs = replay_events(bars)
            events_raw += len(evs)
            res, st = resolve_symbol(sym, bars, evs, horizon=horizon, atr_frac=atr_frac,
                                     atr_period=atr_period)
            for k, v in st.items():
                discards[k] += v
            all_resolved.extend(res)
            used.append(sym)
            counts = defaultdict(int)
            for e in res:
                counts[e["state"]] += 1
            per_symbol[sym] = dict(n_bars_1m=int(len(bars)), n_events=len(evs),
                                   n_graded=len(res), by_state=dict(counts))
            print("%-6s bars=%7d eventos=%4d graduados=%4d  (%.1fs)"
                  % (sym, len(bars), len(evs), len(res), time.time() - t0), flush=True)
    finally:
        conn.close()
    rep = build_report(all_resolved, symbols=used, discards=dict(discards), horizon=horizon,
                       atr_frac=atr_frac, atr_period=atr_period, min_n=min_n,
                       events_raw=events_raw, per_symbol=per_symbol)
    atomic_write(out, rep)
    return rep


def _print(rep):
    print("=== reversal_grade === (wired=%s)" % rep["wired"])
    for name, b in rep["buckets"].items():
        if b["verdict"] == "DATA-INSUFFICIENT":
            print("  %-32s %s (n resuelta=%d < %d) — SIN probabilidad"
                  % (name, b["verdict"], b["n_resolved"], b["min_n"]))
            continue
        print("  %-32s %s  WR %.3f Wilson [%.3f, %.3f] n=%d (sin resolver %d) MFE>MAE %s%%"
              % (name, b["verdict"], b["win_rate"], b["wilson_lo"], b["wilson_hi"],
                 b["n_resolved"], b["n_unresolved"], b["mfe_gt_mae_pct"]))
        for y, s in b["by_year"].items():
            if s.get("win_rate") is None:
                print("      %s INSUFFICIENT_N (n=%d)" % (y, s["n_resolved"]))
            else:
                print("      %s WR %.3f [%.3f,%.3f] n=%d"
                      % (y, s["win_rate"], s["wilson_lo"], s["wilson_hi"], s["n_resolved"]))


def main():
    ap = argparse.ArgumentParser(description="grada reversal_router contra poly_bars")
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--horizon", type=int, default=es.HORIZON)
    ap.add_argument("--atr-frac", type=float, default=es.ATR_FRAC)
    ap.add_argument("--atr-period", type=int, default=es.ATR_PERIOD)
    ap.add_argument("--min-n", type=int, default=es.MIN_N)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    rep = run(_universe(a.syms), horizon=a.horizon, atr_frac=a.atr_frac,
              atr_period=a.atr_period, min_n=a.min_n, out=a.out)
    _print(rep)
    print("  -> %s" % a.out)


if __name__ == "__main__":
    main()
