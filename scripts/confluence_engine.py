#!/usr/bin/env python3
"""confluence_engine.py — MISION 2 (2026-07-23). Motor multi-herramienta de
CONFLUENCIA sobre data/backtest/bars3mo5m_<sym>.csv (5m agregado a 15m/1H).

Herramientas (cada una vota LONG/SHORT/0 de forma CAUSAL, sin look-ahead):
  1. Bollinger(20,2)  : %B en extremo -> voto de reversion a la SMA20 (Yoel).
  2. RSI(14)          : <=30 long, >=70 short (reversion).
  3. MACD(12,26,9)    : cruce de la linea de señal + signo del histograma (momentum).
  4. Velas            : engulfing / martillo / estrella fugaz / doji en extremo.
  5. Trendline break  : ruptura del max/min de N barras (pivotes causales, logica
                        conceptual de combo_tl.pine — momentum/continuacion).
  6. Volumen>MA50     : confirmacion de Yoel en la direccion de la vela.
  7. VWAP (dia)       : recuperacion/perdida del VWAP de la sesion.

Señal SOLO si >=2 herramientas se alinean en el mismo lado (para poder graduar
2 vs 3 vs 4). Emite formato compartido epoch,sym,side,kind,ref_px,target_px,stop_px
con kind = C2/C3/C4/C5+ (numero EXACTO de herramientas alineadas). Ademas emite el
baseline BB-solo. Puntua con:
  (a) scorer de SUBYACENTE (scalp) embebido aqui: primer toque target/stop en H
      barras adelante, ATR-based, sin look-ahead.
  (b) scripts/real_option_scorer.py sobre la opcion ATM semanal REAL (aparte).

Señal-solamente. Sin look-ahead: indicadores hasta la barra i (cierre), evaluacion
desde i+1. Muestra chica se declara.
"""
import csv, math, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

# ----------------------------- carga / agregacion -----------------------------
BARS5M = os.environ.get("BARS5M_TMPL", "data/backtest/bars3mo5m_{sym}.csv")

def load5m(sym):
    rows = []
    p = BARS5M.format(sym=sym)
    if not os.path.exists(p):
        return rows
    for r in csv.reader(open(p)):
        if not r or r[0] == "epoch":
            continue
        try:
            rows.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        except Exception:
            continue
    rows.sort(key=lambda x: x[0])
    return rows

def aggregate(bars5, mins):
    """Agrega barras 5m a bloques de `mins` minutos, alineado por bucket de epoch.
    No mezcla dias (usa el bucket de tiempo absoluto; huecos overnight caen en
    buckets separados de forma natural)."""
    step = mins * 60
    out = {}
    order = []
    for t, o, h, l, c, v in bars5:
        b = (t // step) * step
        if b not in out:
            out[b] = [b, o, h, l, c, v]
            order.append(b)
        else:
            a = out[b]
            a[2] = max(a[2], h); a[3] = min(a[3], l); a[4] = c; a[5] += v
    return [out[b] for b in sorted(order)]

# ------------------------------- indicadores ---------------------------------
def sma(vals, n, i):
    if i + 1 < n: return None
    return sum(vals[i - n + 1:i + 1]) / n

def stdev(vals, n, i, m):
    if i + 1 < n: return None
    s = sum((vals[j] - m) ** 2 for j in range(i - n + 1, i + 1))
    return math.sqrt(s / n)

def ema_series(vals, n):
    k = 2.0 / (n + 1); out = [None] * len(vals); e = None
    for i, v in enumerate(vals):
        e = v if e is None else v * k + e * (1 - k)
        out[i] = e
    return out

def rsi_series(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n: return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0); losses += max(-ch, 0)
    ag = gains / n; al = losses / n
    out[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0)) / n
        al = (al * (n - 1) + max(-ch, 0)) / n
        out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out

def atr_series(bars, n=14):
    out = [None] * len(bars); trs = []
    for i in range(len(bars)):
        h, l, c = bars[i][2], bars[i][3], bars[i][4]
        if i == 0:
            tr = h - l
        else:
            pc = bars[i - 1][4]
            tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        if i + 1 >= n:
            out[i] = sum(trs[i - n + 1:i + 1]) / n
    return out

# ------------------------------ votos por barra ------------------------------
def votes_for_series(bars):
    """Devuelve por barra i un dict de votos causales de cada herramienta y
    contexto. bars: [epoch,o,h,l,c,v]."""
    n = len(bars)
    closes = [b[4] for b in bars]
    opens = [b[1] for b in bars]
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    vols = [b[5] for b in bars]
    macd_line = None
    e12 = ema_series(closes, 12); e26 = ema_series(closes, 26)
    macd = [(e12[i] - e26[i]) if (e12[i] is not None and e26[i] is not None) else None for i in range(n)]
    macd_sig = ema_series([m if m is not None else 0.0 for m in macd], 9)
    rsi = rsi_series(closes, 14)
    atr = atr_series(bars, 14)
    # VWAP diario (reset por dia local)
    vwap = [None] * n; cumPV = 0.0; cumV = 0.0; cur_day = None
    for i in range(n):
        day = time.strftime("%Y-%m-%d", time.localtime(bars[i][0]))
        if day != cur_day:
            cur_day = day; cumPV = 0.0; cumV = 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cumPV += tp * vols[i]; cumV += vols[i]
        vwap[i] = cumPV / cumV if cumV > 0 else None

    votes = []
    for i in range(n):
        v = {"bb": 0, "rsi": 0, "macd": 0, "candle": 0, "tl": 0, "vol": 0, "vwap": 0,
             "pctb": None, "atr": atr[i]}
        # 1) Bollinger
        m = sma(closes, 20, i)
        if m is not None:
            sd = stdev(closes, 20, i, m)
            if sd and sd > 0:
                up = m + 2 * sd; lo = m - 2 * sd
                pb = (closes[i] - lo) / (up - lo)
                v["pctb"] = pb
                if pb <= 0.05: v["bb"] = 1
                elif pb >= 0.95: v["bb"] = -1
        # 2) RSI
        if rsi[i] is not None:
            if rsi[i] <= 30: v["rsi"] = 1
            elif rsi[i] >= 70: v["rsi"] = -1
        # 3) MACD: cruce de linea de señal (causal, i vs i-1)
        if i >= 1 and macd[i] is not None and macd_sig[i] is not None and macd[i - 1] is not None:
            d0 = macd[i - 1] - macd_sig[i - 1]; d1 = macd[i] - macd_sig[i]
            if d0 <= 0 < d1: v["macd"] = 1
            elif d0 >= 0 > d1: v["macd"] = -1
        # 4) Velas (reversion en extremo de 10 barras)
        if i >= 10:
            o, c, h, l = opens[i], closes[i], highs[i], lows[i]
            po, pc = opens[i - 1], closes[i - 1]
            rng = h - l if h > l else 1e-9
            body = abs(c - o); upper = h - max(c, o); lower = min(c, o) - l
            near_low = l <= min(lows[i - 10:i]) * 1.001
            near_high = h >= max(highs[i - 10:i]) * 0.999
            bull_eng = c > o and pc < po and c >= po and o <= pc
            bear_eng = c < o and pc > po and c <= po and o >= pc
            hammer = lower >= 2 * body and upper <= body and body > 0
            star = upper >= 2 * body and lower <= body and body > 0
            doji = body <= 0.1 * rng
            if (bull_eng or hammer or (doji and near_low)) and near_low: v["candle"] = 1
            elif (bear_eng or star or (doji and near_high)) and near_high: v["candle"] = -1
        # 5) Trendline break (ruptura del extremo de N=20 barras previas, causal)
        if i >= 21:
            hh = max(highs[i - 20:i]); ll = min(lows[i - 20:i])
            if closes[i] > hh: v["tl"] = 1
            elif closes[i] < ll: v["tl"] = -1
        # 6) Volumen > MA50 confirma direccion de la vela
        vm = sma(vols, 50, i)
        if vm is not None and vols[i] > vm:
            if closes[i] > opens[i]: v["vol"] = 1
            elif closes[i] < opens[i]: v["vol"] = -1
        # 7) VWAP: recuperacion/perdida (cruce causal)
        if i >= 1 and vwap[i] is not None and vwap[i - 1] is not None:
            a0 = closes[i - 1] - vwap[i - 1]; a1 = closes[i] - vwap[i]
            if a0 <= 0 < a1: v["vwap"] = 1
            elif a0 >= 0 > a1: v["vwap"] = -1
        votes.append(v)
    return votes

TOOLS = ["bb", "rsi", "macd", "candle", "tl", "vol", "vwap"]

# ---------------------------- generacion de señales ---------------------------
def gen_signals(sym, bars):
    """1 señal por barra 15m con >=2 herramientas alineadas. Ademas baseline BB."""
    votes = votes_for_series(bars)
    sigs = []      # confluencia
    bb_sigs = []   # baseline BB-solo
    last_epoch_side = {}  # dedup: no repetir mismo lado en la misma barra
    for i in range(len(bars)):
        v = votes[i]
        t, o, h, l, c, vol = bars[i]
        longs = sum(1 for k in TOOLS if v[k] == 1)
        shorts = sum(1 for k in TOOLS if v[k] == -1)
        atr = v["atr"] or (h - l) or c * 0.003
        # baseline BB-solo
        if v["bb"] != 0:
            side = "LONG" if v["bb"] == 1 else "SHORT"
            tgt = c + 1.5 * atr if side == "LONG" else c - 1.5 * atr
            stp = c - 1.0 * atr if side == "LONG" else c + 1.0 * atr
            bb_sigs.append((t, sym, side, "BB", round(c, 2), round(tgt, 2), round(stp, 2)))
        # confluencia
        if longs >= 2 and longs > shorts:
            cnt = longs; side = "LONG"
        elif shorts >= 2 and shorts > longs:
            cnt = shorts; side = "SHORT"
        else:
            continue
        kind = f"C{cnt}" if cnt < 5 else "C5+"
        tgt = c + 1.5 * atr if side == "LONG" else c - 1.5 * atr
        stp = c - 1.0 * atr if side == "LONG" else c + 1.0 * atr
        sigs.append((t, sym, side, kind, round(c, 2), round(tgt, 2), round(stp, 2)))
    return sigs, bb_sigs

# ------------------------ scorer SUBYACENTE (scalp) --------------------------
def scalp_score(sigs, bars_by_sym, horizon=8):
    """Primer toque target/stop en `horizon` barras adelante (i+1..i+H). Sin
    look-ahead. Si ninguno toca, liquida al cierre de i+H (pnl con signo).
    Devuelve buckets por kind -> [wins, n, sum_pnl_R] donde R = |ref-stop|."""
    buckets = {}
    idx = {}  # (sym) -> {epoch: index}
    for sym, bars in bars_by_sym.items():
        idx[sym] = {b[0]: k for k, b in enumerate(bars)}
    for (t, sym, side, kind, ref, tgt, stp) in sigs:
        bars = bars_by_sym[sym]; i = idx[sym].get(t)
        if i is None: continue
        R = abs(ref - stp) or ref * 0.003
        outcome = None
        for j in range(i + 1, min(i + 1 + horizon, len(bars))):
            hh, ll = bars[j][2], bars[j][3]
            if side == "LONG":
                if ll <= stp: outcome = -1.0; break
                if hh >= tgt: outcome = (tgt - ref) / R; break
            else:
                if hh >= stp: outcome = -1.0; break
                if ll <= tgt: outcome = (ref - tgt) / R; break
        if outcome is None:
            j = min(i + horizon, len(bars) - 1)
            cl = bars[j][4]
            outcome = ((cl - ref) if side == "LONG" else (ref - cl)) / R
        b = buckets.setdefault(kind, [0, 0, 0.0])
        b[0] += int(outcome > 0); b[1] += 1; b[2] += outcome
    return buckets

def wilson(w, n):
    if n == 0: return 0.0
    p = w / n; z = 1.96; d = 1 + z * z / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)

def print_buckets(title, buckets, cumulative_from=None):
    print(f"\n### {title}")
    order = ["BB", "C2", "C3", "C4", "C5+"]
    keys = [k for k in order if k in buckets] + [k for k in buckets if k not in order]
    for k in keys:
        w, n, s = buckets[k]
        if n:
            print(f"  {k:5s} n={n:5d} | WR {w/n*100:5.1f}% | avgR {s/n:+.3f} | wilson {wilson(w,n)*100:4.1f}%")
    # cumulativo por nivel de confluencia (C>=x)
    if cumulative_from:
        print("  -- cumulativo (confluencia >= x) --")
        for lvl in (2, 3, 4):
            w = n = 0; s = 0.0
            for k, (kw, kn, ks) in buckets.items():
                if k.startswith("C"):
                    num = 5 if k == "C5+" else int(k[1:])
                    if num >= lvl:
                        w += kw; n += kn; s += ks
            if n:
                print(f"  C>={lvl} n={n:5d} | WR {w/n*100:5.1f}% | avgR {s/n:+.3f} | wilson {wilson(w,n)*100:4.1f}%")

# ----------------------------------- main ------------------------------------
def main():
    syms = sys.argv[1:] or ["qqq", "spy", "nvda", "mu", "smh", "amd", "aapl", "meta"]
    tf = int(os.environ.get("CONF_TF", "15"))  # timeframe en minutos
    all_sigs = []; all_bb = []; bars_by_sym = {}
    for sym in syms:
        b5 = load5m(sym)
        if not b5:
            print(f"  (sin datos {sym})"); continue
        bars = aggregate(b5, tf)
        bars_by_sym[sym] = bars
        s, bb = gen_signals(sym, bars)
        all_sigs += s; all_bb += bb
        print(f"  {sym:5s} {tf}m barras={len(bars)} | conf-señales={len(s)} | bb-señales={len(bb)}")
    # escribir CSVs compartidos
    hdr = ["epoch", "sym", "side", "kind", "ref_px", "target_px", "stop_px"]
    p_conf = "data/backtest/signals_confluence.csv"
    p_bb = "data/backtest/signals_bb_baseline.csv"
    with open(p_conf, "w", newline="") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(sorted(all_sigs))
    with open(p_bb, "w", newline="") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(sorted(all_bb))
    print(f"\n-> {p_conf} ({len(all_sigs)})   -> {p_bb} ({len(all_bb)})")

    # scorer subyacente (scalp)
    H = int(os.environ.get("CONF_H", "8"))
    bconf = scalp_score(all_sigs, bars_by_sym, H)
    bbb = scalp_score(all_bb, bars_by_sym, H)
    merged = dict(bconf); merged["BB"] = bbb.get("BB", [0, 0, 0.0])
    print_buckets(f"SCALP SUBYACENTE (target 1.5*ATR / stop 1.0*ATR, {H} barras, R-multiplo)",
                  merged, cumulative_from=True)

if __name__ == "__main__":
    main()
