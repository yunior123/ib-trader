#!/usr/bin/env python3
"""
reversal_router.py — Bento/Trinity/Router signal engine ported to a standalone fleet analyzer.

Ported from mit/backend/app/analytics/technical.py (analyze_signals) with the NO-REPAINT
higher-timeframe technique from mit/research/cross_asset_event_study.py live_htf():
completed-bucket shift(1), NOT pandas resample (resample repaints the forming HTF bar).

Base timeframe = 5m (aggregated from the 1m bars in data/bars_<sym>_ibkr.txt). HTF (15/30/60/
240m + daily) EMA5, Bollinger and RSI are evaluated at each 5m bar using ONLY completed higher
buckets plus the current live price — so the latest reading never repaints.

Router states (per symbol):
  CONTINUATION_ACTIVE_DO_NOT_FADE | REVERSAL_ARMED_WAIT | REVERSAL_CONFIRMED |
  NEUTRAL_CONFLICT | INSUFFICIENT_DATA

CRITICAL — SHADOW / UNVALIDATED:
  This engine has NO measured edge yet. The measured-probability doctrine forbids publishing a
  signal below validation. Therefore this script ONLY writes data/reversal_<sym>.json. It MUST
  NOT emit to fleet_notify, fleet_consensus, order_engine or voice. It is a research shadow.

FAIL-LOUD (house rule): in the signal path an except returns None / raises; it NEVER fabricates a
plausible number. The gold's fail-soft defaults (bento_score 0.5 sentinel, rsi.fillna(50),
daily_atr->0, "INSUFFICIENT DATA" string returns, adx.fillna(0)) are reworked here: if the data
is short (< ~260 5m-equivalent bars) or any required last-bar indicator is NaN, the state is the
explicit sentinel INSUFFICIENT_DATA — never a fabricated NEUTRAL / 0.5 / 0.0.

Note on history: the daily timeframe features (d1 EMA5, previous-day ATR14 used for Trinity
energy) genuinely need ~15 RTH sessions. Below that the analyzer honestly reports
INSUFFICIENT_DATA rather than inventing an energy value.

CLI:
  reversal_router.py --once [SYMS...]
  reversal_router.py --daemon [SYMS...]
Default symbol universe: data/provider_syms.txt if present, else data/fleet.txt.
Grading (still shadow, wires nothing): scripts/reversal_grade.py -> data/reversal_grade.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - environment without tzdata
    _ET = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")

REQUIRED_5M_BARS = 260           # ~gold threshold, expressed in 5m-equivalent bars
DAEMON_INTERVAL_S = 20           # shadow refresh cadence

RTH_OPEN_MIN = 9 * 60 + 30       # 09:30 ET in minutes
RTH_CLOSE_MIN = 16 * 60          # 16:00 ET (exclusive)


# ------------------------------------------------------------------ numpy helpers
def _ema(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1)
    out = np.full(len(x), np.nan)
    prev = np.nan
    for i, v in enumerate(x):
        if np.isnan(v):
            out[i] = prev
            continue
        prev = v if np.isnan(prev) else alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def _wilder(x: np.ndarray, length: int) -> np.ndarray:
    """Wilder EWM (alpha=1/length, adjust=False, min_periods=length): NaN until `length` obs."""
    alpha = 1.0 / length
    out = np.full(len(x), np.nan)
    prev = np.nan
    cnt = 0
    for i, v in enumerate(x):
        if np.isnan(v):
            out[i] = prev if cnt >= length else np.nan
            continue
        prev = v if np.isnan(prev) else alpha * v + (1 - alpha) * prev
        cnt += 1
        out[i] = prev if cnt >= length else np.nan
    return out


def _roll_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if not np.isnan(w).any():
            out[i] = w.mean()
    return out


def _shift1(x: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    out[1:] = x[:-1]
    return out


def _factorize_ordered(keys: np.ndarray) -> np.ndarray:
    """Sequential contiguous ids 0..K-1 in order of appearance (keys are time-sorted, contiguous)."""
    ids = np.empty(len(keys), dtype=np.int64)
    cur = -1
    for i in range(len(keys)):
        if i == 0 or keys[i] != keys[i - 1]:
            cur += 1
        ids[i] = cur
    return ids


# ------------------------------------------------------------------ bar loading / 5m aggregation
def _load_1m(sym: str):
    path = os.path.join(DATA, f"bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(path):
        return None
    epochs, o, h, l, c, v = [], [], [], [], [], []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 6:
                continue
            try:
                epochs.append(int(float(p[0])))
                o.append(float(p[1])); h.append(float(p[2]))
                l.append(float(p[3])); c.append(float(p[4])); v.append(float(p[5]))
            except ValueError:
                continue
    if not epochs:
        return None
    arr = np.array(sorted(zip(epochs, o, h, l, c, v)), dtype=float)
    return arr  # columns: epoch, o, h, l, c, v


def _to_5m_base(bars_1m: np.ndarray):
    """Aggregate RTH 1m bars into 5m base bars. Returns dict of numpy arrays or None."""
    if _ET is None:
        raise RuntimeError("no zoneinfo/tzdata — cannot resolve ET session buckets")
    epoch = bars_1m[:, 0]
    date_ord = np.empty(len(epoch), dtype=np.int64)
    mins = np.empty(len(epoch), dtype=np.int64)
    keep = np.zeros(len(epoch), dtype=bool)
    for i, e in enumerate(epoch):
        dt = datetime.fromtimestamp(int(e), _ET)
        m = dt.hour * 60 + dt.minute
        if RTH_OPEN_MIN <= m < RTH_CLOSE_MIN:
            keep[i] = True
            date_ord[i] = dt.date().toordinal()
            mins[i] = m - RTH_OPEN_MIN
    if not keep.any():
        return None
    b = bars_1m[keep]
    date_ord = date_ord[keep]
    mins = mins[keep]
    bucket = mins // 5
    key = date_ord * 100000 + bucket
    bid = _factorize_ordered(key)
    K = int(bid.max()) + 1
    O = np.empty(K); H = np.full(K, -np.inf); L = np.full(K, np.inf)
    C = np.empty(K); V = np.zeros(K); EP = np.empty(K, dtype=np.int64)
    DO = np.empty(K, dtype=np.int64); MI = np.empty(K, dtype=np.int64)
    seen = np.zeros(K, dtype=bool)
    for i in range(len(b)):
        k = bid[i]
        if not seen[k]:
            O[k] = b[i, 1]; seen[k] = True
        H[k] = max(H[k], b[i, 2]); L[k] = min(L[k], b[i, 3])
        C[k] = b[i, 4]; V[k] += b[i, 5]; EP[k] = int(b[i, 0])
        DO[k] = date_ord[i]; MI[k] = bucket[i] * 5
    return dict(epoch=EP, o=O, h=H, l=L, c=C, v=V, date_ord=DO, mins=MI)


# ------------------------------------------------------------------ no-repaint HTF (live_htf port)
def _live_htf(c_base, date_ord, mins, minutes, ema_len=5, bb_len=20, bb_mult=2.0, rsi_len=14):
    n = len(c_base)
    bucket_num = np.zeros(n, dtype=np.int64) if minutes is None else (mins // minutes).astype(np.int64)
    key = date_ord * 1000000 + bucket_num
    bid = _factorize_ordered(key)
    K = int(bid.max()) + 1

    completed = np.full(K, np.nan)          # last close of each completed/forming bucket
    for i in range(n):
        completed[bid[i]] = c_base[i]

    completed_ema = _ema(completed, ema_len)
    prev_ema = _shift1(completed_ema)
    prev_close = _shift1(completed)
    alpha = 2.0 / (ema_len + 1)
    live_ema = alpha * c_base + (1 - alpha) * prev_ema[bid]

    # Bollinger: previous (bb_len-1) completed closes + current live price.
    nprev = bb_len - 1
    comp_prev = _shift1(completed)
    psum = np.full(K, np.nan)
    psq = np.full(K, np.nan)
    sq = comp_prev * comp_prev
    for k in range(nprev, K):
        w = comp_prev[k - nprev + 1:k + 1]
        if not np.isnan(w).any():
            psum[k] = w.sum()
            psq[k] = sq[k - nprev + 1:k + 1].sum()
    basis = (psum[bid] + c_base) / bb_len
    var = (psq[bid] + c_base * c_base) / bb_len - basis * basis
    sd = np.sqrt(np.maximum(var, 0.0))

    # RSI (Wilder) live: prior completed averages advanced one step by the live price.
    delta = np.concatenate([[np.nan], np.diff(completed)])
    gain = np.where(np.isnan(delta), np.nan, np.maximum(delta, 0.0))
    loss = np.where(np.isnan(delta), np.nan, np.maximum(-delta, 0.0))
    ag = _shift1(_wilder(gain, rsi_len))[bid]
    al = _shift1(_wilder(loss, rsi_len))[bid]
    pc = prev_close[bid]
    cd = c_base - pc
    cg = np.maximum(cd, 0.0)
    cl = np.maximum(-cd, 0.0)
    lag = (ag * (rsi_len - 1) + cg) / rsi_len
    lal = (al * (rsi_len - 1) + cl) / rsi_len
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = lag / lal
        lrsi = 100 - 100 / (1 + rs)
    lrsi = np.where((lal == 0) & (lag > 0), 100.0, lrsi)
    lrsi = np.where((lal == 0) & (lag == 0), 50.0, lrsi)

    return dict(ema5=live_ema, bb_basis=basis, bb_upper=basis + bb_mult * sd,
                bb_lower=basis - bb_mult * sd, rsi=lrsi)


# ------------------------------------------------------------------ base 5m enrichment
def _dmi(h, l, c, length=14):
    up = np.concatenate([[np.nan], np.diff(h)])
    down = np.concatenate([[np.nan], -np.diff(l)])
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm[0] = np.nan
    minus_dm[0] = np.nan
    prev = _shift1(c)
    tr = np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])
    atr = _wilder(tr, length)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus = 100 * _wilder(plus_dm, length) / atr
        minus = 100 * _wilder(minus_dm, length) / atr
        dx = 100 * np.abs(plus - minus) / (plus + minus)
    adx = _wilder(dx, length)
    return plus, minus, adx


def _enrich_base(base: dict) -> dict:
    o, h, l, c = base["o"], base["h"], base["l"], base["c"]
    ema5 = _ema(c, 5)
    rsi = _wilder_rsi(c, 14)
    rsi_basis = _roll_mean(rsi, 20)
    ribbon_high = _roll_mean(h, 20)
    ribbon_low = _roll_mean(l, 20)
    prev = _shift1(c)
    tr = np.maximum.reduce([h - l, np.abs(h - prev), np.abs(l - prev)])
    atr = _wilder(tr, 14)
    plus_di, minus_di, adx = _dmi(h, l, c, 14)
    return dict(ema5=ema5, rsi=rsi, rsi_basis=rsi_basis, ribbon_high=ribbon_high,
                ribbon_low=ribbon_low, atr=atr, plus_di=plus_di, minus_di=minus_di, adx=adx,
                open=o, high=h, low=l, close=c)


def _wilder_rsi(c: np.ndarray, length: int = 14) -> np.ndarray:
    delta = np.concatenate([[np.nan], np.diff(c)])
    gain = np.where(np.isnan(delta), np.nan, np.maximum(delta, 0.0))
    loss = np.where(np.isnan(delta), np.nan, np.maximum(-delta, 0.0))
    ag = _wilder(gain, length)
    al = _wilder(loss, length)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = ag / al
        out = 100 - 100 / (1 + rs)
    out = np.where((al == 0) & (ag > 0), 100.0, out)
    out = np.where((al == 0) & (ag == 0), 50.0, out)
    return out


def _daily_prev_atr(base: dict) -> dict:
    """previous-day ATR14 keyed by date_ord (no-repaint: uses only completed prior days)."""
    do = base["date_ord"]
    uniq = []
    O, H, L, C = [], [], [], []
    cur = None
    for i in range(len(do)):
        if do[i] != cur:
            uniq.append(do[i]); cur = do[i]
            O.append(base["o"][i]); H.append(base["h"][i]); L.append(base["l"][i]); C.append(base["c"][i])
        else:
            H[-1] = max(H[-1], base["h"][i]); L[-1] = min(L[-1], base["l"][i]); C[-1] = base["c"][i]
    H = np.array(H); L = np.array(L); C = np.array(C)
    prevc = _shift1(C)
    tr = np.maximum.reduce([H - L, np.abs(H - prevc), np.abs(L - prevc)])
    atr14 = _wilder(tr, 14)
    prev_atr = _shift1(atr14)
    return {int(d): (float(prev_atr[i]) if not np.isnan(prev_atr[i]) else None)
            for i, d in enumerate(uniq)}


# ------------------------------------------------------------------ router state machine
def _finite(x) -> bool:
    return x is not None and np.isfinite(x)


def features(bars_1m: np.ndarray):
    """Todas las series causales del router en un pase. None si no hay barras RTH.

    Cada indicador aqui depende SOLO de x[0..i] (EMA/Wilder recursivos, medias rodantes
    traseras, live_htf con buckets COMPLETOS): por eso state_at(f, i) reproduce exactamente
    lo que el router habria dicho en vivo en la barra i (no-repaint), y el replay historico
    no necesita recomputar por barra."""
    base = _to_5m_base(bars_1m)
    if base is None:
        return None
    return dict(
        base=base,
        enr=_enrich_base(base),
        m15=_live_htf(base["c"], base["date_ord"], base["mins"], 15),
        m30=_live_htf(base["c"], base["date_ord"], base["mins"], 30),
        h1=_live_htf(base["c"], base["date_ord"], base["mins"], 60),
        h4=_live_htf(base["c"], base["date_ord"], base["mins"], 240),
        d1=_live_htf(base["c"], base["date_ord"], base["mins"], None),
        prev_atr=_daily_prev_atr(base),
    )


def state_at(f: dict, i: int) -> dict:
    """Estado del router en la barra base i, usando solo historia hasta i."""
    base, enr = f["base"], f["enr"]
    m15, m30, h1, h4, d1 = f["m15"], f["m30"], f["h1"], f["h4"], f["d1"]
    n5 = i + 1
    bar_epoch = int(base["epoch"][i])
    if n5 < REQUIRED_5M_BARS:
        return dict(state="INSUFFICIENT_DATA", scores={},
                    reasons=[f"n_bars {n5} < required {REQUIRED_5M_BARS} (5m-equivalent)"],
                    bar_epoch=bar_epoch, n_bars=n5)

    prev_atr = f["prev_atr"]
    close = float(enr["close"][i])
    day_prev_atr = prev_atr.get(int(base["date_ord"][i]))
    energy = (float(enr["atr"][i]) / day_prev_atr) if (day_prev_atr and _finite(enr["atr"][i])) else None

    # Required last-bar features — any missing => fail-loud INSUFFICIENT_DATA (no fabrication).
    required = {
        "base_ema5": enr["ema5"][i], "base_rsi": enr["rsi"][i], "base_rsi_prev": enr["rsi"][i - 1],
        "base_rsi_basis": enr["rsi_basis"][i], "ribbon_high": enr["ribbon_high"][i],
        "ribbon_low": enr["ribbon_low"][i], "base_atr": enr["atr"][i], "plus_di": enr["plus_di"][i],
        "minus_di": enr["minus_di"][i], "adx": enr["adx"][i],
        "m15_bb_upper": m15["bb_upper"][i], "m15_bb_lower": m15["bb_lower"][i], "m15_rsi": m15["rsi"][i],
        "m30_bb_upper": m30["bb_upper"][i], "m30_bb_lower": m30["bb_lower"][i], "m30_rsi": m30["rsi"][i],
        "m15_ema5": m15["ema5"][i], "h1_ema5": h1["ema5"][i], "h4_ema5": h4["ema5"][i],
        "d1_ema5": d1["ema5"][i], "energy": energy,
    }
    missing = [k for k, val in required.items() if not _finite(val)]
    if missing:
        return dict(state="INSUFFICIENT_DATA",
                    scores={"n_bars": n5},
                    reasons=["missing indicators (need ~15 RTH sessions): " + ",".join(missing)],
                    bar_epoch=bar_epoch, n_bars=n5)

    # --- Bento: opening-reversal extreme on 15m & 30m (no-repaint) ---
    def extreme(bb_upper, bb_lower, rsi_v):
        if close > bb_upper and rsi_v >= 70:
            return -1
        if close < bb_lower and rsi_v <= 30:
            return 1
        return 0

    ext15 = extreme(m15["bb_upper"][i], m15["bb_lower"][i], m15["rsi"][i])
    ext30 = extreme(m30["bb_upper"][i], m30["bb_lower"][i], m30["rsi"][i])
    bento_dir = 0
    bento_score = 0.0
    if ext15 == ext30 != 0:
        bento_dir = 1 if ext15 == 1 else -1
        bento_score = 1.0
    elif ext15 != 0 or ext30 != 0:
        bento_dir = 1 if (ext15 or ext30) == 1 else -1
        bento_score = 0.5

    # --- Trinity: 5-timeframe EMA5 alignment + ribbon/RSI/DMI/ADX/energy quality ---
    tf_ema5 = [enr["ema5"][i], m15["ema5"][i], h1["ema5"][i], h4["ema5"][i], d1["ema5"][i]]
    above = sum(close > e for e in tf_ema5)
    below = sum(close < e for e in tf_ema5)
    long_facts = [above == 5, close > enr["ribbon_high"][i],
                  enr["rsi"][i] > max(50.0, enr["rsi_basis"][i]),
                  enr["plus_di"][i] > enr["minus_di"][i], enr["adx"][i] >= 20, energy >= 0.14]
    short_facts = [below == 5, close < enr["ribbon_low"][i],
                   enr["rsi"][i] < min(50.0, enr["rsi_basis"][i]),
                   enr["minus_di"][i] > enr["plus_di"][i], enr["adx"][i] >= 20, energy >= 0.14]
    long_score = sum(long_facts) / 6.0
    short_score = sum(short_facts) / 6.0
    if long_score >= 5 / 6:
        trinity_dir, trinity_active, trinity_score = 1, True, long_score
    elif short_score >= 5 / 6:
        trinity_dir, trinity_active, trinity_score = -1, True, short_score
    else:
        trinity_dir = 1 if long_score > short_score else -1 if short_score > long_score else 0
        trinity_active = False
        trinity_score = max(long_score, short_score)

    # --- Router: decide fade vs continuation ---
    reasons = []
    reversal_score = 0
    state = "NEUTRAL_CONFLICT"
    if bento_dir != 0:
        up = bento_dir == 1
        facts = [
            (close > m15["bb_lower"][i]) if up else (close < m15["bb_upper"][i]),
            (close > enr["ribbon_low"][i]) if up else (close < enr["ribbon_high"][i]),
            (enr["rsi"][i] > enr["rsi"][i - 1]) if up else (enr["rsi"][i] < enr["rsi"][i - 1]),
            (enr["plus_di"][i] > enr["minus_di"][i]) if up else (enr["minus_di"][i] > enr["plus_di"][i]),
            (above < 5) if up else (below < 5),
            (close > enr["open"][i]) if up else (close < enr["open"][i]),
        ]
        labels = ["price re-entered Bollinger", "price entered ribbon", "RSI turned",
                  "DMI flipped", "MTF trend broke", "reversal candle"]
        reversal_score = int(sum(facts))
        reasons.extend(lbl for lbl, ok in zip(labels, facts) if ok)
        continuation_opposes = trinity_active and trinity_dir != bento_dir
        if continuation_opposes and reversal_score < 5:
            state = "CONTINUATION_ACTIVE_DO_NOT_FADE"
            reasons.append("Trinity continuation veto")
        elif reversal_score >= 5:
            state = "REVERSAL_CONFIRMED"
        else:
            state = "REVERSAL_ARMED_WAIT"
    elif trinity_active:
        state = "CONTINUATION_ACTIVE_DO_NOT_FADE"
        reasons.append("5-timeframe EMA5, ribbon, RSI, DMI/ADX and energy aligned")

    return dict(
        state=state,
        scores=dict(
            bento_dir=int(bento_dir), bento_score=round(float(bento_score), 3),
            trinity_dir=int(trinity_dir), trinity_active=bool(trinity_active),
            trinity_score=round(float(trinity_score), 3),
            long_score=round(float(long_score), 3), short_score=round(float(short_score), 3),
            reversal_score=int(reversal_score), energy=round(float(energy), 4),
            above=int(above), below=int(below), n_bars=int(n5),
        ),
        reasons=reasons,
        bar_epoch=bar_epoch,
        n_bars=n5,
    )


def evaluate(bars_1m: np.ndarray) -> dict:
    """Estado del router en la ULTIMA barra de `bars_1m` (sin IO, sin simbolo)."""
    f = features(bars_1m)
    if f is None:
        return dict(state="INSUFFICIENT_DATA", scores={}, reasons=["no RTH bars"],
                    bar_epoch=int(bars_1m[-1, 0]), n_bars=0)
    return state_at(f, len(f["base"]["c"]) - 1)


def _compute(sym: str) -> dict:
    bars_1m = _load_1m(sym)
    if bars_1m is None:
        return dict(symbol=sym.upper(), state="INSUFFICIENT_DATA", scores={},
                    reasons=["no bars file / unparseable"], bar_epoch=None, n_bars=0)
    return dict(symbol=sym.upper(), **evaluate(bars_1m))


def _write(sym: str, result: dict) -> str:
    result = dict(result)
    result["updated_utc"] = datetime.now(timezone.utc).isoformat()
    result["shadow"] = True  # UNVALIDATED — json only, never published to fleet
    path = os.path.join(DATA, f"reversal_{sym.upper()}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(result, f, indent=1)
    os.replace(tmp, path)
    return path


def _symbols(argv):
    if argv:
        return [s.upper() for s in argv]
    for name in ("provider_syms.txt", "fleet.txt"):
        p = os.path.join(DATA, name)
        if os.path.exists(p):
            return open(p).read().split()
    raise RuntimeError("no symbol universe (provider_syms.txt / fleet.txt)")


def _run_once(syms):
    for s in syms:
        try:
            res = _compute(s)
        except Exception as e:  # fail-loud: record the failure, never a fabricated state
            res = dict(symbol=s.upper(), state="INSUFFICIENT_DATA", scores={},
                       reasons=[f"error: {type(e).__name__}: {e}"], bar_epoch=None, n_bars=0)
        _write(s, res)
        print(f"{s.upper():6s} {res['state']:32s} {res.get('reasons', [])}")


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("--once", "--daemon"):
        print(__doc__)
        sys.exit(2)
    mode = args[0]
    syms = _symbols(args[1:])
    if mode == "--once":
        _run_once(syms)
        return
    while True:
        _run_once(syms)
        time.sleep(DAEMON_INTERVAL_S)


if __name__ == "__main__":
    main()
