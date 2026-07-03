#!/usr/bin/env python3
"""Local replica backtest of tradingview/confluence_master.pine.

Replicates the Pine v6 logic bar-for-bar on real Alpaca SIP daily history
(adjustment=all, so dividends/splits are total-return correct):
  - Wilder (RMA) RSI fast/slow divergence
  - Supertrend with the classic v4 nz/ratchet semantics
  - DEMA, regime EMA200, Bollinger 20/2
  - Monthly-anchored VWAP +/- stdev bands (hlc3)
  - Relative volume vs 20d SMA
Execution model (punitive on purpose — backtest-expert: add friction):
  - signal on close -> fill next bar OPEN
  - 0.05% commission per side + 0.05% adverse slippage per side
  - ATR initial stop, optional Supertrend-line ratchet trail; stop becomes
    active the bar AFTER the entry fill (matches Pine strategy.exit timing);
    gap through stop fills at the open, not the stop.

Usage:
  python3 bt.py fetch [SYMS...]          # pull daily bars 2015->now into data/
  python3 bt.py run   [SYMS...]          # baseline config, full period
  python3 bt.py grid  [SYMS...]          # param grid, train<=2023-12-31 / OOS 2024+
"""
import csv
import json
import math
import os
import sys
import urllib.request
from itertools import product

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(HERE, "data")
SYMS_DEFAULT = ["QQQ", "SPY", "TQQQ", "NVDA", "AAPL", "AMD", "TSLA"]
START = "2015-01-01"
TRAIN_END = "2023-12-31"          # OOS = 2024-01-01 onward (walk-forward gate)
COMMISSION = 0.0005               # 0.05% per side
SLIPPAGE = 0.0005                 # 0.05% adverse per side


def _load_env():
    for name in ("config/alpaca.env", "config/feeds.env", "config/llm.env"):
        p = os.path.join(REPO, name)
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


# ---------------------------------------------------------------- data -----
def fetch(sym):
    _load_env()
    key = os.environ.get("ALPACA_KEY") or os.environ.get("APCA_API_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET") or os.environ.get("APCA_API_SECRET_KEY")
    if not key:
        sys.exit("no ALPACA_KEY in alpaca.env")
    os.makedirs(DATA, exist_ok=True)
    bars, token = [], None
    while True:
        url = (f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Day"
               f"&start={START}&adjustment=all&feed=sip&limit=10000")
        if token:
            url += f"&page_token={token}"
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        bars += d.get("bars") or []
        token = d.get("next_page_token")
        if not token:
            break
    path = os.path.join(DATA, f"{sym.lower()}_daily.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"]])
    print(f"{sym}: {len(bars)} daily bars -> {path}")
    return path


def load(sym):
    path = os.path.join(DATA, f"{sym.lower()}_daily.csv")
    if not os.path.exists(path):
        fetch(sym)
    rows = list(csv.DictReader(open(path)))
    return {
        "date": [r["date"] for r in rows],
        "o": [float(r["open"]) for r in rows],
        "h": [float(r["high"]) for r in rows],
        "l": [float(r["low"]) for r in rows],
        "c": [float(r["close"]) for r in rows],
        "v": [float(r["volume"]) for r in rows],
    }


# ---------------------------------------------------------- indicators -----
def rma(src, length):
    """Pine ta.rma: SMA seed, then Wilder smoothing."""
    out, s = [None] * len(src), None
    for i, x in enumerate(src):
        if x is None:
            continue
        if s is None:
            window = [v for v in src[max(0, i - length + 1):i + 1] if v is not None]
            if len(window) >= length:
                s = sum(window[-length:]) / length
                out[i] = s
        else:
            s = (x + (length - 1) * s) / length
            out[i] = s
    return out


def rsi(close, length):
    ups = [None] + [max(close[i] - close[i - 1], 0) for i in range(1, len(close))]
    dns = [None] + [max(close[i - 1] - close[i], 0) for i in range(1, len(close))]
    u, d = rma(ups, length), rma(dns, length)
    out = []
    for uu, dd in zip(u, d):
        if uu is None or dd is None:
            out.append(None)
        elif dd == 0:
            out.append(100.0)
        elif uu == 0:
            out.append(0.0)
        else:
            out.append(100 - 100 / (1 + uu / dd))
    return out


def ema(src, length):
    out, s, a = [None] * len(src), None, 2 / (length + 1)
    for i, x in enumerate(src):
        if s is None:
            if i + 1 >= length:
                s = sum(src[i - length + 1:i + 1]) / length
                out[i] = s
        else:
            s = a * x + (1 - a) * s
            out[i] = s
    return out


def sma(src, length):
    out, run = [None] * len(src), 0.0
    for i, x in enumerate(src):
        run += x
        if i >= length:
            run -= src[i - length]
        if i >= length - 1:
            out[i] = run / length
    return out


def stdev(src, length):
    out = [None] * len(src)
    for i in range(length - 1, len(src)):
        w = src[i - length + 1:i + 1]
        m = sum(w) / length
        out[i] = math.sqrt(sum((x - m) ** 2 for x in w) / length)
    return out


def atr(d, length):
    trs = [d["h"][0] - d["l"][0]]
    for i in range(1, len(d["c"])):
        trs.append(max(d["h"][i] - d["l"][i], abs(d["h"][i] - d["c"][i - 1]),
                       abs(d["l"][i] - d["c"][i - 1])))
    return rma(trs, length)


def compute(d, p):
    n = len(d["c"])
    c, h, l, v = d["c"], d["h"], d["l"], d["v"]
    rf, rs = rsi(c, p["lenFast"]), rsi(c, p["lenSlow"])
    div = [None if (a is None or b is None) else a - b for a, b in zip(rf, rs)]
    e1 = ema(c, p["demaLen"])
    e2 = ema([x if x is not None else c[i] for i, x in enumerate(e1)], p["demaLen"])
    dema = [None if (a is None or b is None) else 2 * a - b for a, b in zip(e1, e2)]
    reg = ema(c, p["regimeLen"])
    basis = sma(c, p["bbLen"])
    dev = stdev(c, p["bbLen"])
    bbU = [None if (a is None or b is None) else a + p["bbMult"] * b for a, b in zip(basis, dev)]
    bbL = [None if (a is None or b is None) else a - p["bbMult"] * b for a, b in zip(basis, dev)]
    volsma = sma(v, p["rvolLen"])
    rvol = [None if (s is None or s == 0) else v[i] / s for i, s in enumerate(volsma)]

    # supertrend (v4 semantics)
    a = atr(d, p["stPeriod"])
    up = [None] * n
    dn = [None] * n
    trend = [1] * n
    for i in range(n):
        if a[i] is None:
            continue
        src = (h[i] + l[i]) / 2
        u = src - p["stMult"] * a[i]
        dd = src + p["stMult"] * a[i]
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

    # monthly-anchored VWAP + stdev bands on hlc3
    vwap = [None] * n
    vwU = [None] * n
    vwL = [None] * n
    pv = vv = p2 = 0.0
    for i in range(n):
        if i == 0 or d["date"][i][:7] != d["date"][i - 1][:7]:
            pv = vv = p2 = 0.0
        hlc3 = (h[i] + l[i] + c[i]) / 3
        pv += hlc3 * v[i]
        vv += v[i]
        p2 += v[i] * hlc3 * hlc3
        if vv > 0:
            m = pv / vv
            sd = math.sqrt(max(p2 / vv - m * m, 0))
            vwap[i], vwU[i], vwL[i] = m, m + p["vwapDev"] * sd, m - p["vwapDev"] * sd

    score = [0] * n
    ready = [False] * n
    for i in range(n):
        if None in (dema[i], div[i], reg[i], vwap[i], rvol[i], basis[i], bbL[i]):
            continue
        ready[i] = True
        score[i] = ((c[i] > dema[i]) + (div[i] > 0) + (c[i] > reg[i]) +
                    (c[i] > vwap[i]) + (rvol[i] >= p["rvolThresh"]) + (c[i] > basis[i]))
    return {"trend": trend, "up": up, "atr": a, "score": score, "ready": ready,
            "rsiSlow": rs, "bbL": bbL, "reg": reg}


# ----------------------------------------------------------- simulation ----
BASE = dict(lenFast=5, lenSlow=14, demaLen=200, regimeLen=200, bbLen=20, bbMult=2.0,
            vwapDev=2.0, rvolLen=20, rvolThresh=1.2, stPeriod=10, stMult=3.0,
            minScore=4, exitScore=2, atrStop=3.0, trail=True, dip=True, dipRsi=38)


def simulate(d, p, start=None, end=None):
    ind = compute(d, p)
    n = len(d["c"])
    cash, pos_qty = 10000.0, 0.0
    entry_px = stop_active = stop_next = None
    pending_entry = pending_exit = False
    entry_stop_seed = None
    trades, equity, dates = [], [], []
    in_range = lambda i: (start is None or d["date"][i] >= start) and (end is None or d["date"][i] <= end)
    bars_in_pos = 0

    for i in range(n):
        o = d["o"][i]
        # 1) fills from yesterday's decisions
        if pending_entry and pos_qty == 0 and in_range(i):
            px = o * (1 + SLIPPAGE)
            pos_qty = cash * (1 - COMMISSION) / px
            cash = 0.0
            entry_px = px
            stop_active, stop_next = None, entry_stop_seed  # stop live next bar
        elif pending_exit and pos_qty > 0:
            px = o * (1 - SLIPPAGE)
            cash = pos_qty * px * (1 - COMMISSION)
            trades.append(px / entry_px - 1)
            pos_qty = 0.0
        pending_entry = pending_exit = False

        # 2) intrabar stop
        if pos_qty > 0 and stop_active is not None:
            hit = None
            if o <= stop_active:
                hit = o
            elif d["l"][i] <= stop_active:
                hit = stop_active
            if hit is not None:
                px = hit * (1 - SLIPPAGE)
                cash = pos_qty * px * (1 - COMMISSION)
                trades.append(px / entry_px - 1)
                pos_qty = 0.0

        # 3) decisions on close
        if ind["ready"][i]:
            c = d["c"][i]
            if pos_qty == 0:
                mom = ind["trend"][i] == 1 and ind["score"][i] >= p["minScore"]
                dip = (p["dip"] and ind["trend"][i] == 1 and c > ind["reg"][i]
                       and ind["rsiSlow"][i] is not None and ind["rsiSlow"][i] <= p["dipRsi"]
                       and ind["bbL"][i] is not None and c <= ind["bbL"][i])
                if (mom or dip) and in_range(i):
                    pending_entry = True
                    entry_stop_seed = c - p["atrStop"] * ind["atr"][i]
            else:
                bars_in_pos += 1
                if ind["trend"][i] == -1 or ind["score"][i] < p["exitScore"]:
                    pending_exit = True
                s = stop_next if stop_next is not None else stop_active
                if s is not None and p["trail"] and ind["trend"][i] == 1 and ind["up"][i] is not None:
                    s = max(s, ind["up"][i])
                stop_active, stop_next = s, None

        if in_range(i):
            equity.append(cash + pos_qty * d["c"][i])
            dates.append(d["date"][i])

    if pos_qty > 0:  # mark last position closed at final close
        trades.append(d["c"][n - 1] / entry_px - 1)
    return metrics(trades, equity, dates, bars_in_pos)


def metrics(trades, equity, dates, bars_in_pos):
    if not equity:
        return None
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gp = sum(wins)
    gl = -sum(losses)
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    years = max(len(equity) / 252, 1e-9)
    cagr = (equity[-1] / equity[0]) ** (1 / years) - 1
    return {
        "trades": len(trades),
        "wr": 100 * len(wins) / len(trades) if trades else 0,
        "pf": gp / gl if gl > 0 else float("inf"),
        "avg_win": 100 * (sum(wins) / len(wins)) if wins else 0,
        "avg_loss": 100 * (sum(losses) / len(losses)) if losses else 0,
        "ret": 100 * (equity[-1] / equity[0] - 1),
        "cagr": 100 * cagr,
        "mdd": 100 * mdd,
        "exposure": 100 * bars_in_pos / len(equity),
    }


def buyhold(d, start=None, end=None):
    idx = [i for i in range(len(d["c"]))
           if (start is None or d["date"][i] >= start) and (end is None or d["date"][i] <= end)]
    eq = [d["c"][i] for i in idx]
    return metrics([eq[-1] / eq[0] - 1], eq, [d["date"][i] for i in idx], len(eq))


def fmt(sym, tag, m, bh=None):
    if m is None:
        return f"{sym:5s} {tag:10s} (no data)"
    s = (f"{sym:5s} {tag:10s} trades {m['trades']:3d}  WR {m['wr']:5.1f}%  PF {m['pf']:5.2f}  "
         f"ret {m['ret']:8.1f}%  CAGR {m['cagr']:6.1f}%  maxDD {m['mdd']:5.1f}%  expo {m['exposure']:5.1f}%")
    if bh:
        s += f"   [B&H ret {bh['ret']:.0f}% DD {bh['mdd']:.0f}%]"
    return s


# ----------------------------------------------------------------- grid ----
def grid(syms):
    combos = list(product([10, 14], [2.5, 3.0, 3.5], [3, 4, 5], [2.0, 3.0, 4.0],
                          [True, False], [True, False]))
    results = []
    data = {s: load(s) for s in syms}
    for stP, stM, ms, astp, dip, trail in combos:
        p = dict(BASE, stPeriod=stP, stMult=stM, minScore=ms, atrStop=astp,
                 dip=dip, trail=trail)
        agg_pf, agg_wr, agg_tr, agg_ret, agg_dd = [], [], 0, [], []
        for s in syms:
            m = simulate(data[s], p, end=TRAIN_END)
            if not m or m["trades"] < 5:
                continue
            agg_pf.append(min(m["pf"], 10))
            agg_wr.append(m["wr"])
            agg_ret.append(m["cagr"])
            agg_dd.append(m["mdd"])
            agg_tr += m["trades"]
        if not agg_pf:
            continue
        # robust score: median-ish PF + CAGR/DD, punish few trades
        pf = sorted(agg_pf)[len(agg_pf) // 2]
        car_dd = sum(agg_ret) / len(agg_ret) / max(sum(agg_dd) / len(agg_dd), 1)
        results.append((pf * 2 + car_dd + min(agg_tr, 200) / 200,
                        dict(stPeriod=stP, stMult=stM, minScore=ms, atrStop=astp,
                             dip=dip, trail=trail),
                        pf, sum(agg_wr) / len(agg_wr), agg_tr))
    results.sort(key=lambda r: -r[0])
    print("top-10 train configs (score | params | medPF | avgWR | trades):")
    for sc, p, pf, wr, tr in results[:10]:
        print(f"  {sc:5.2f} | st({p['stPeriod']},{p['stMult']}) minScore={p['minScore']} "
              f"atrStop={p['atrStop']} dip={int(p['dip'])} trail={int(p['trail'])} "
              f"| PF {pf:4.2f} WR {wr:4.1f}% n={tr}")
    print("\nOOS validation (2024-01-01 ->) of top-3:")
    for sc, p, *_ in results[:3]:
        pp = dict(BASE, **p)
        print(f"  config st({p['stPeriod']},{p['stMult']}) minScore={p['minScore']} "
              f"atrStop={p['atrStop']} dip={int(p['dip'])} trail={int(p['trail'])}")
        for s in syms:
            m = simulate(data[s], pp, start="2024-01-01")
            bh = buyhold(data[s], start="2024-01-01")
            print("   " + fmt(s, "OOS", m, bh))
    return results


def run(syms, p=None, start=None, end=None, tag="full"):
    p = p or BASE
    for s in syms:
        d = load(s)
        print(fmt(s, tag, simulate(d, p, start, end), buyhold(d, start, end)))


if __name__ == "__main__":
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    syms = [a.upper() for a in args] or SYMS_DEFAULT
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "fetch":
        for s in syms:
            fetch(s)
    elif cmd == "grid":
        grid(syms)
    else:
        run(syms)
