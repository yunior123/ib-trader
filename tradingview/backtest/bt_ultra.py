#!/usr/bin/env python3
"""Ultra Trend — local replica backtest (pairs with tradingview/ultra_trend.pine).

Design synthesized from a 4-lens design panel (turtle / squeeze / structure /
devil's-advocate) on top of the PROVEN confluence core (see README):
  KEEP byte-for-byte (all 4 lenses agreed): Supertrend(10,3.5) gate, 6-check
    confluence score, wide 4xATR NON-trailing stop, exit on flip / score<2.
  NEW, each rule grid-tested to earn its place:
  - EVENT entries: Donchian-20 close breakout OR bullish-pattern resumption
    (engulfing/hammer/inside-break closing above BB mid) — anti-chop fix
  - pattern bonus: +1 score if bull pattern within last 3 bars (never a veto)
  - double-extension veto: skip entry if close > BB upper AND > VWAP+2sigma
  - post-loss cooldown: 5 bars, overridden by a fresh Donchian breakout
  - bear tightening: below falling EMA200 -> need score>=5 AND breakout
  - breakeven floor: at +5xATR open profit, stop ratchets to entry*1.002 only
  REJECTED by panel AND confirmed empirically (previous grid): ADX gate (lags),
  squeeze precondition (starves: n=154, OOS medPF 1.27), chandelier trail,
  QQQ market filter (couples all names), tight trailing of any kind.

Same punitive friction as bt.py (0.05%+0.05% per side, next-open fills, gaps
through stop fill at open, stop inactive on entry bar). GENERIC mandate: one
config for all 25 tickers, judged on the MEDIAN ticker.

Usage:
  python3 bt_ultra.py run    [SYMS...]   # shipped config: full + OOS + recent
  python3 bt_ultra.py grid   [SYMS...]   # 128-config design grid, train/OOS
  python3 bt_ultra.py recent [SYMS...]   # recent-data report (2025->)
  python3 bt_ultra.py ablate [SYMS...]   # one-out ablation of shipped config
"""
import sys
from itertools import product

import bt
from bt import (load, rma, ema, sma, stdev, atr, metrics, buyhold,
                COMMISSION, SLIPPAGE)

SYMS_ALL = ["QQQ", "SPY", "IWM", "DIA", "TQQQ", "AAPL", "MSFT", "NVDA", "AMD",
            "TSLA", "META", "GOOGL", "AMZN", "NFLX", "ASML", "TSM", "INTC",
            "TXN", "GLD", "SLV", "USO", "CPER", "COIN", "PLTR", "MSTR"]
TRAIN_END = "2023-12-31"
OOS = "2024-01-01"
RECENT = "2025-01-01"


# ---------------------------------------------------------- indicators -----
def adx(d, length=14):
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    plus_dm, minus_dm, trs = [0.0], [0.0], [h[0] - l[0]]
    for i in range(1, n):
        upm = h[i] - h[i - 1]
        dnm = l[i - 1] - l[i]
        plus_dm.append(upm if (upm > dnm and upm > 0) else 0.0)
        minus_dm.append(dnm if (dnm > upm and dnm > 0) else 0.0)
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    atr_s, pdm_s, mdm_s = rma(trs, length), rma(plus_dm, length), rma(minus_dm, length)
    dx = [None] * n
    for i in range(n):
        if atr_s[i] and pdm_s[i] is not None and mdm_s[i] is not None:
            pdi = 100 * pdm_s[i] / atr_s[i]
            mdi = 100 * mdm_s[i] / atr_s[i]
            dx[i] = 100 * abs(pdi - mdi) / max(pdi + mdi, 1e-9)
    return rma(dx, length)


def donchian_high(d, length=20):
    """Max del high de las `length` barras ANTERIORES (excluye la actual —
    breakout = close sobre el canal de ayer, cero look-ahead)."""
    h = d["h"]
    out = [None] * len(h)
    for i in range(length, len(h)):
        out[i] = max(h[i - length:i])
    return out


def patterns_bull(d):
    """Patron alcista en la barra: engulfing, hammer o inside-bar-break."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    out = [False] * len(c)
    for i in range(2, len(c)):
        body = abs(c[i] - o[i])
        rng = max(h[i] - l[i], 1e-9)
        engulf = (c[i] > o[i] and c[i - 1] < o[i - 1]
                  and c[i] > o[i - 1] and o[i] < c[i - 1])
        lower_wick = min(o[i], c[i]) - l[i]
        hammer = lower_wick > 2 * body and (c[i] - l[i]) / rng > 0.66
        inside_prev = h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2]
        ib_break = inside_prev and c[i] > h[i - 2]
        out[i] = engulf or hammer or ib_break
    return out


def anchored_vwap(d, yearly=False):
    """VWAP anclado (mensual o anual) sobre hlc3 + banda superior 2sigma."""
    n = len(d["c"])
    h, l, c, v = d["h"], d["l"], d["c"], d["v"]
    cut = 4 if yearly else 7          # YYYY o YYYY-MM
    vw = [None] * n
    u2 = [None] * n
    pv = vv = p2 = 0.0
    for i in range(n):
        if i == 0 or d["date"][i][:cut] != d["date"][i - 1][:cut]:
            pv = vv = p2 = 0.0
        hlc3 = (h[i] + l[i] + c[i]) / 3
        pv += hlc3 * v[i]
        vv += v[i]
        p2 += v[i] * hlc3 * hlc3
        if vv > 0:
            m = pv / vv
            sd = (max(p2 / vv - m * m, 0)) ** 0.5
            vw[i], u2[i] = m, m + 2.0 * sd
    return vw, u2


# --------------------------------------------------- static per-ticker -----
_STATIC = {}


def static_ind(sym, d):
    if sym in _STATIC:
        return _STATIC[sym]
    c, v = d["c"], d["v"]
    rf, rs = bt.rsi(c, 5), bt.rsi(c, 14)
    div = [None if (a is None or b is None) else a - b for a, b in zip(rf, rs)]
    e1 = ema(c, 200)
    e2 = ema([x if x is not None else c[i] for i, x in enumerate(e1)], 200)
    dema = [None if (a is None or b is None) else 2 * a - b for a, b in zip(e1, e2)]
    reg = ema(c, 200)
    basis = sma(c, 20)
    dev = stdev(c, 20)
    bbL = [None if (a is None or b is None) else a - 2.0 * b for a, b in zip(basis, dev)]
    bbU = [None if (a is None or b is None) else a + 2.0 * b for a, b in zip(basis, dev)]
    volsma = sma(v, 20)
    rvol = [None if (s is None or s == 0) else v[i] / s for i, s in enumerate(volsma)]
    vwM, vwM2 = anchored_vwap(d, yearly=False)
    vwY, vwY2 = anchored_vwap(d, yearly=True)
    out = {"div": div, "dema": dema, "reg": reg, "basis": basis, "bbL": bbL,
           "bbU": bbU, "rvol": rvol, "rsiSlow": rs, "adx": adx(d, 14),
           "don": donchian_high(d, 20), "pat": patterns_bull(d),
           "atr14": atr(d, 14), "vwM": vwM, "vwM2": vwM2,
           "vwY": vwY, "vwY2": vwY2}
    _STATIC[sym] = out
    return out


_ST_CACHE = {}


def supertrend(sym, d, period, mult):
    key = (sym, period, mult)
    if key in _ST_CACHE:
        return _ST_CACHE[key]
    n = len(d["c"])
    c, h, l = d["c"], d["h"], d["l"]
    a = atr(d, period)
    up = [None] * n
    dn = [None] * n
    trend = [1] * n
    for i in range(n):
        if a[i] is None:
            continue
        src = (h[i] + l[i]) / 2
        u = src - mult * a[i]
        dd = src + mult * a[i]
        u1 = up[i - 1] if i > 0 and up[i - 1] is not None else u
        d1 = dn[i - 1] if i > 0 and dn[i - 1] is not None else dd
        up[i] = max(u, u1) if c[i - 1] > u1 else u
        dn[i] = min(dd, d1) if c[i - 1] < d1 else dd
        t = trend[i - 1]
        if t == -1 and c[i] > d1:
            t = 1
        elif t == 1 and c[i] < u1:
            t = -1
        trend[i] = t
    _ST_CACHE[key] = (trend, up)
    return trend, up


# ----------------------------------------------------------- simulation ----
BASE = dict(stPeriod=10, stMult=3.5, minScore=5, exitScore=2, atrStop=4.0,
            entryMode="event",   # state (proven control) | event (panel design)
            extVeto=False,        # panel idea; NO gano su lugar en el grid 25-ticker
            cooldown=False,       # idem — la mediana no mejora
            bearTight=True,       # below falling EMA200: score>=5 + breakout only
            beFloor=True,         # +5xATR profit -> stop to entry*1.002
            vwapY=True,           # ancla ANUAL gano el A/B (top-12 completo)
            exitMode="flip+score",
            adxMin=0,             # ablation only — panel rejected
            rvolThresh=1.2, dipRsi=38, dip=True, patBonus=True)


def simulate(sym, d, p, start=None, end=None):
    st_trend, _ = supertrend(sym, d, p["stPeriod"], p["stMult"])
    s = static_ind(sym, d)
    vw = s["vwY"] if p["vwapY"] else s["vwM"]
    vw2 = s["vwY2"] if p["vwapY"] else s["vwM2"]
    n = len(d["c"])
    cash, qty = 10000.0, 0.0
    entry_px = stop_active = stop_next = None
    entry_atr = None
    pending_entry = pending_exit = False
    entry_stop_seed = entry_atr_seed = None
    last_loss_bar = -10**9
    trades, equity, dates = [], [], []
    bars_in_pos = 0
    in_range = lambda i: (start is None or d["date"][i] >= start) and (end is None or d["date"][i] <= end)

    def close_pos(i, px):
        nonlocal cash, qty, last_loss_bar
        cash = qty * px * (1 - COMMISSION)
        r = px / entry_px - 1
        trades.append(r)
        if r <= 0:
            last_loss_bar = i
        qty = 0.0

    for i in range(n):
        o = d["o"][i]
        if pending_entry and qty == 0 and in_range(i):
            px = o * (1 + SLIPPAGE)
            qty = cash * (1 - COMMISSION) / px
            cash = 0.0
            entry_px, entry_atr = px, entry_atr_seed
            # stop vivo desde la barra del fill (audit fix: gap en la barra de
            # entrada queda protegido; el .pine coloca strategy.exit igual)
            stop_active, stop_next = entry_stop_seed, None
        elif pending_exit and qty > 0:
            close_pos(i, o * (1 - SLIPPAGE))
        pending_entry = pending_exit = False

        if qty > 0 and stop_active is not None:
            hit = o if o <= stop_active else (stop_active if d["l"][i] <= stop_active else None)
            if hit is not None:
                close_pos(i, hit * (1 - SLIPPAGE))

        c = d["c"][i]
        ok = None not in (s["dema"][i], s["div"][i], s["reg"][i], vw[i], vw2[i],
                          s["rvol"][i], s["basis"][i], s["bbL"][i], s["bbU"][i],
                          s["don"][i], s["atr14"][i])
        if ok:
            score = ((c > s["dema"][i]) + (s["div"][i] > 0) + (c > s["reg"][i]) +
                     (c > vw[i]) + (s["rvol"][i] >= p["rvolThresh"]) +
                     (c > s["basis"][i]))
            if p["patBonus"] and any(s["pat"][max(0, i - 2):i + 1]):
                score += 1
            gate = st_trend[i] == 1
            if p["adxMin"] and (s["adx"][i] is None or s["adx"][i] < p["adxMin"]):
                gate = False
            brk = c > s["don"][i]
            bear = (i >= 20 and s["reg"][i - 20] is not None
                    and c < s["reg"][i] and s["reg"][i] < s["reg"][i - 20])
            if qty == 0:
                if p["entryMode"] == "state":
                    fire = gate and score >= p["minScore"]
                    dip = (p["dip"] and gate and c > s["reg"][i]
                           and s["rsiSlow"][i] is not None
                           and s["rsiSlow"][i] <= p["dipRsi"] and c <= s["bbL"][i])
                else:  # event
                    resum = s["pat"][i] and c > s["basis"][i]
                    fire = gate and score >= p["minScore"] and (brk or resum)
                    dip = (p["dip"] and gate and c > s["reg"][i] and s["pat"][i]
                           and s["rsiSlow"][i] is not None
                           and s["rsiSlow"][i] <= p["dipRsi"] and c <= s["basis"][i])
                if p["bearTight"] and bear:
                    fire = gate and score >= 5 and brk
                    dip = False
                if p["extVeto"] and c > s["bbU"][i] and c > vw2[i]:
                    fire = dip = False
                if p["cooldown"] and i - last_loss_bar <= 5 and not brk:
                    fire = dip = False
                if (fire or dip) and in_range(i):
                    pending_entry = True
                    entry_stop_seed = c - p["atrStop"] * s["atr14"][i]
                    entry_atr_seed = s["atr14"][i]
            else:
                bars_in_pos += 1
                if st_trend[i] != 1:
                    pending_exit = True
                elif p["exitMode"] == "flip+score" and score < p["exitScore"]:
                    pending_exit = True
                stp = stop_next if stop_next is not None else stop_active
                if (p["beFloor"] and stp is not None and entry_atr
                        and c - entry_px >= 5 * entry_atr):
                    stp = max(stp, entry_px * 1.002)
                stop_active, stop_next = stp, None

        if in_range(i):
            equity.append(cash + qty * d["c"][i])
            dates.append(d["date"][i])

    if qty > 0:
        trades.append(d["c"][n - 1] / entry_px - 1)
    return metrics(trades, equity, dates, bars_in_pos)


# ------------------------------------------------------------- reports -----
def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0


def evaluate(syms, p, start=None, end=None, label=""):
    rows, pfs, wrs, cagrs, dds = [], [], [], [], []
    for sym in syms:
        d = load(sym)
        m = simulate(sym, d, p, start, end)
        if m is None or m["trades"] < 3:
            continue
        rows.append((sym, m))
        pfs.append(min(m["pf"], 10))
        wrs.append(m["wr"])
        cagrs.append(m["cagr"])
        dds.append(m["mdd"])
    if label:
        for sym, m in rows:
            bh = buyhold(load(sym), start, end)
            print(bt.fmt(sym, label, m, bh))
        print(f"  MEDIAN: PF {median(pfs):4.2f}  WR {median(wrs):4.1f}%  "
              f"CAGR {median(cagrs):5.1f}%  maxDD {median(dds):4.1f}%  "
              f"({len(rows)} tickers, {sum(m['trades'] for _, m in rows)} trades)")
    return dict(medPF=median(pfs), medWR=median(wrs), medCAGR=median(cagrs),
                medDD=median(dds), n=sum(m["trades"] for _, m in rows), k=len(rows))


def _cfg_str(p):
    return (f"{p['entryMode']:5s} ext={int(p['extVeto'])} cd={int(p['cooldown'])} "
            f"bear={int(p['bearTight'])} be={int(p['beFloor'])} "
            f"vwY={int(p['vwapY'])} ms={p['minScore']} {p['exitMode']}")


def grid(syms):
    combos = list(product(["state", "event"], [False, True], [False, True],
                          [False, True], [False, True], [False, True], [4, 5]))
    res = []
    for em, ev, cd, btgt, be, vy, ms in combos:
        p = dict(BASE, entryMode=em, extVeto=ev, cooldown=cd, bearTight=btgt,
                 beFloor=be, vwapY=vy, minScore=ms)
        r = evaluate(syms, p, end=TRAIN_END)
        if r["k"] < len(syms) * 0.7 or r["n"] < 300:
            continue   # starving configs are auto-fails for a generic system
        sc = (r["medPF"] + r["medCAGR"] / 8
              + 2 * r["medCAGR"] / max(r["medDD"], 1) + min(r["n"], 700) / 700)
        res.append((sc, p, r))
    res.sort(key=lambda x: -x[0])
    print("top-12 train (score | config | median PF/WR/CAGR/DD | trades):")
    for sc, p, r in res[:12]:
        print(f"  {sc:5.2f} | {_cfg_str(p)} | PF {r['medPF']:4.2f} WR {r['medWR']:4.1f}% "
              f"CAGR {r['medCAGR']:5.1f}% DD {r['medDD']:4.1f}% n={r['n']}")
    print("\nOOS 2024-> top-3 (median-only):")
    for sc, p, r in res[:3]:
        ro = evaluate(syms, p, start=OOS)
        rr = evaluate(syms, p, start=RECENT)
        print(f"  {_cfg_str(p)}\n    OOS   : PF {ro['medPF']:4.2f} WR {ro['medWR']:4.1f}% "
              f"CAGR {ro['medCAGR']:5.1f}% DD {ro['medDD']:4.1f}% n={ro['n']}"
              f"\n    recent: PF {rr['medPF']:4.2f} WR {rr['medWR']:4.1f}% "
              f"CAGR {rr['medCAGR']:5.1f}% DD {rr['medDD']:4.1f}% n={rr['n']}")
    return res


def ablate(syms):
    print("shipped:", _cfg_str(BASE))
    base_tr = evaluate(syms, BASE, end=TRAIN_END)
    base_oos = evaluate(syms, BASE, start=OOS)
    print(f"  train PF {base_tr['medPF']:4.2f} CAGR {base_tr['medCAGR']:5.1f}% | "
          f"OOS PF {base_oos['medPF']:4.2f} CAGR {base_oos['medCAGR']:5.1f}%")
    flips = [("entryMode", "state"), ("extVeto", False), ("cooldown", False),
             ("bearTight", False), ("beFloor", False), ("vwapY", True),
             ("patBonus", False), ("dip", False), ("exitMode", "flip"),
             ("adxMin", 18), ("minScore", 5)]
    for k, v in flips:
        p = dict(BASE, **{k: v})
        tr = evaluate(syms, p, end=TRAIN_END)
        oo = evaluate(syms, p, start=OOS)
        print(f"  {k}={v!s:6.6s} -> train PF {tr['medPF']:4.2f} CAGR {tr['medCAGR']:5.1f}% "
              f"| OOS PF {oo['medPF']:4.2f} CAGR {oo['medCAGR']:5.1f}% n={tr['n']}/{oo['n']}")


if __name__ == "__main__":
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    syms = [a.upper() for a in args] or SYMS_ALL
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "grid":
        grid(syms)
    elif cmd == "ablate":
        ablate(syms)
    elif cmd == "recent":
        evaluate(syms, BASE, start=RECENT, label="recent")
    else:
        print("== FULL 2015->2026 ==")
        evaluate(syms, BASE, label="full")
        print("\n== OOS 2024-> ==")
        evaluate(syms, BASE, start=OOS, label="OOS")
        print("\n== RECENT 2025-> ==")
        evaluate(syms, BASE, start=RECENT, label="recent")
