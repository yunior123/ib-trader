#!/usr/bin/env python3
"""v5_backtest — backtest del motor v5 sobre bars reales de 1m (orden Yunior
2026-07-15: "backtest the whole fucking thing, no excuses... test all with
real data before booting them up").

Corre <bot> --stdin con {SYM}_V5=1 sobre data/hist/bars_<sym>_1m_30d.txt,
parsea los marcadores '*** SYM V5 BUY/SELL *** score S prob P ... t=EPOCH' y
evalua cada señal contra los MISMOS bars:
  exito BUY  = precio toca +1.0*ATR15 antes que -1.0*ATR15 en <=60 min
  exito SELL = espejo
Reporta WR por bucket de score y ajusta la logistica prob=1/(1+e^-(A+B*s))
por IRLS -> imprime V5_A/V5_B calibrados para el keepalive.
Uso: venv/bin/python scripts/v5_backtest.py NVDA QQQ [--vmin 4.0]
"""
import math
import os
import re
import subprocess
import sys

ROOT = "/Users/yuniorrodriguezosorio/ib-trader"
os.chdir(ROOT)
HORIZON = 3600          # 60 min
ATR_N = 15              # ATR de 15 bars de 1m ~ rango de 15 min


def load_bars(path):
    out = []
    for ln in open(path):
        p = ln.split()
        if len(p) == 6:
            out.append(tuple(float(x) for x in p))
    return out


def atr_at(bars, i):
    lo = max(1, i - ATR_N + 1)
    trs = []
    for j in range(lo, i + 1):
        h, l, pc = bars[j][2], bars[j][3], bars[j - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0


def outcome(bars, idx, side):
    """1 si toca +1 ATR antes que -1 ATR en HORIZON; 0 si al reves; None si ni."""
    px = bars[idx][4]
    a = atr_at(bars, idx)
    if a <= 0:
        return None
    up, dn = px + a, px - a
    t0 = bars[idx][0]
    for j in range(idx + 1, len(bars)):
        if bars[j][0] - t0 > HORIZON:
            break
        hi, lo = bars[j][2], bars[j][3]
        hit_up, hit_dn = hi >= up, lo <= dn
        if hit_up and hit_dn:            # bar ambiguo: cuenta contra la señal
            return 0
        if hit_up:
            return 1 if side == "BUY" else 0
        if hit_dn:
            return 0 if side == "BUY" else 1
    return None


def run_sym(sym, vmin):
    s = sym.lower()
    hist = f"data/hist/bars_{s}_1m_30d.txt"
    if not os.path.exists(hist):
        print(f"{sym}: sin {hist} — correr scripts/fetch_hist_1m.py primero")
        return []
    bars = load_bars(hist)
    idx_by_t = {b[0]: i for i, b in enumerate(bars)}
    env = dict(os.environ)
    pref = sym.upper()
    env[f"{pref}_V5"] = "1"
    env[f"{pref}_V5_MIN"] = str(vmin)
    env[f"{pref}_V5_COOL"] = "1800"
    env[f"{pref}_SCORE_MIN"] = "9"       # motor viejo mudo: aislar v5
    env[f"{pref}_QUAKE_BANNER"] = "0"
    r = subprocess.run([f"./{s}_signal_bot", "--stdin"],
                       input="".join(f"{b[0]:.0f} {b[1]:.4f} {b[2]:.4f} {b[3]:.4f} {b[4]:.4f} {b[5]:.0f}\n" for b in bars),
                       capture_output=True, text=True, env=env, timeout=300)
    events = []
    for m in re.finditer(r"\*\*\* \S+ V5 (BUY|SELL) \*\*\* score ([\d.]+) prob (\d+)% .*t=(\d+)", r.stdout):
        side, score, prob, t = m.group(1), float(m.group(2)), int(m.group(3)), float(m.group(4))
        i = idx_by_t.get(t)
        if i is None or i + 5 >= len(bars):
            continue
        oc = outcome(bars, i, side)
        if oc is not None:
            events.append((sym, side, score, oc))
    return events


def fit_logistic(events):
    """IRLS simple sobre (score, hit)."""
    if len(events) < 10:
        return None
    xs = [e[2] for e in events]
    ys = [e[3] for e in events]
    a, b = -3.0, 0.6
    for _ in range(60):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-(a + b * x)))
            w = p * (1 - p)
            ga += y - p
            gb += (y - p) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab
        if abs(det) < 1e-9:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a += da
        b += db
        if abs(da) + abs(db) < 1e-8:
            break
    return a, b


def main():
    syms = [a.upper() for a in sys.argv[1:] if not a.startswith("--")] or ["NVDA", "QQQ"]
    vmin = 4.0
    if "--vmin" in sys.argv:
        vmin = float(sys.argv[sys.argv.index("--vmin") + 1])
    allev = []
    for sym in syms:
        ev = run_sym(sym, vmin)
        n = len(ev)
        w = sum(e[3] for e in ev)
        print(f"{sym}: {n} señales v5 (vmin {vmin}), WR {w}/{n}"
              f" = {w / n * 100 if n else 0:.0f}%")
        allev += ev
    if not allev:
        print("sin señales — bajar --vmin o mas datos")
        return
    print("\n--- WR por bucket de score ---")
    buckets = {}
    for _, _, s, y in allev:
        k = round(s * 2) / 2
        buckets.setdefault(k, []).append(y)
    for k in sorted(buckets):
        v = buckets[k]
        print(f"  score {k:4.1f}: {sum(v)}/{len(v)} = {sum(v) / len(v) * 100:.0f}%")
    fit = fit_logistic(allev)
    if fit:
        a, b = fit
        print(f"\nCALIBRACION: V5_A={a:.2f} V5_B={b:.2f}")
        for s in (4, 5, 6, 7):
            print(f"  score {s} -> prob {100 / (1 + math.exp(-(a + b * s))):.0f}%")
    n = len(allev)
    w = sum(e[3] for e in allev)
    print(f"\nTOTAL: {n} señales, WR global {w / n * 100:.0f}% "
          f"(exito = +1 ATR15 antes que -1 ATR15 en 60 min)")


if __name__ == "__main__":
    main()
