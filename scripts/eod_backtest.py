#!/usr/bin/env python3
"""eod_backtest.py — backtest de las señales de HOY contra el precio real posterior.

Para cada señal de trades.db (source whale/flow/dip/bollinger/structural/cusum), determina
la TESIS (qué predice), toma el precio en el instante de la señal desde las barras 1m reales
(data/bars_<sym>_ibkr.txt), mide el resultado a +5/+15/+30/+60min (MFE/MAE + retorno en la
dirección de la tesis) y agrega WR por fuente (Wilson CI). Diagnostica las EQUIVOCADAS:
BB %B en el instante, band-walk vs rebote, contra-tendencia.

Uso: python3 scripts/eod_backtest.py [YYYY-MM-DD]   (default: hoy)
SEÑAL-SOLAMENTE: solo lee BD + barras. Sin red, sin órdenes.
"""
import os, sys, sqlite3, math, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
FLEET = open("data/fleet.txt").read().split() if os.path.exists("data/fleet.txt") else []
HOR = [5, 15, 30, 60]   # minutos

# ---- barras ----
_barcache = {}
def load_bars(sym):
    if sym in _barcache:
        return _barcache[sym]
    path = f"data/bars_{sym.lower()}_ibkr.txt"
    rows = []
    if os.path.exists(path):
        for ln in open(path):
            p = ln.split()
            if len(p) >= 5:
                try:
                    rows.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4])))
                except Exception:
                    pass
    rows.sort()
    _barcache[sym] = rows
    return rows

def price_at(bars, ep):
    """close de la barra <= ep (o la más cercana)."""
    lo, hi, best = 0, len(bars) - 1, None
    if not bars:
        return None
    for ts, o, h, l, c in bars:
        if ts <= ep:
            best = (ts, o, h, l, c)
        else:
            break
    return best

def window(bars, ep0, mins):
    """barras en (ep0, ep0+mins*60] -> (hi, lo, last_close)."""
    end = ep0 + mins * 60
    hs, ls, lastc = [], [], None
    for ts, o, h, l, c in bars:
        if ep0 < ts <= end:
            hs.append(h); ls.append(l); lastc = c
    if not hs:
        return None
    return max(hs), min(ls), lastc

def bb_pctb(bars, ep, n=20):
    """%B(20,2) en 1m en el instante ep (0=banda baja, 1=alta)."""
    seq = [c for ts, o, h, l, c in bars if ts <= ep]
    if len(seq) < n:
        return None
    w = seq[-n:]; m = sum(w) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    if sd == 0:
        return 0.5
    up, dn = m + 2 * sd, m - 2 * sd
    return (seq[-1] - dn) / (up - dn)

def wilson(k, n):
    if n == 0:
        return (0, 0, 0)
    p = k / n; z = 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p), round(100 * (c - hw)), round(100 * (c + hw)))

# ---- tesis por señal: +1 espera SUBIR, -1 espera BAJAR, 0 indefinido ----
def thesis(source, kind, msg):
    up = (kind + " " + msg).upper()
    if source == "whale":
        if "PUTS" in up:  return +1, "piso (puts masivos = rebote)"
        if "CALLS" in up: return -1, "techo (calls masivos = pullback, ley 13)"
    if source == "flow":
        if "CALLS" in up: return -1, "clímax comprador -> rebote a la baja"
        if "PUTS" in up:  return +1, "clímax vendedor -> rebote al alza"
    if source == "dip":   return +1, "dip real -> rebote"
    if source == "bollinger":
        if "REBOTE" in up or "RE-ENTRADA" in up:
            return (+1, "rebote banda ABAJO -> media") if "ABAJO" in up else (-1, "rebote banda ARRIBA -> media")
        if "BAND-WALK" in up or "CAMINA" in up:
            return (-1, "band-walk ABAJO (continuación)") if "ABAJO" in up else (+1, "band-walk ARRIBA")
    if source == "structural":
        return (+1, "imán arriba") if "↑" in msg or "UP" in up else (-1, "imán abajo")
    if source == "cusum":
        return (+1, "terremoto alza") if "ALZA" in up or "SUB" in up else (-1, "terremoto baja")
    return 0, "indefinido"

def extract_symbol(kind, msg):
    import re
    for tok in re.findall(r"\b[A-Z]{1,5}\b", (kind or "") + " " + (msg or "")):
        if tok in FLEET:
            return tok
    return None


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().strftime("%Y-%m-%d")
    c = sqlite3.connect("trades.db")
    rows = c.execute("SELECT ts_epoch, ts_txt, kind, source, symbol, msg FROM signals "
                     "WHERE date=? ORDER BY ts_epoch", (day,)).fetchall()
    c.close()
    print(f"=== EOD BACKTEST {day} — {len(rows)} señales ===\n")
    # acumuladores: source -> {n, win@15, win@30, contra-tendencia, mfe/mae}
    agg = {}
    losers = []
    H = 15   # horizonte principal (scalp)
    for ep, ts_txt, kind, source, sym, msg in rows:
        if not ep:
            continue
        if not sym:
            sym = extract_symbol(kind or "", msg or "")
        if not sym:
            continue
        th, why = thesis(source or "", kind or "", msg or "")
        if th == 0:
            continue
        bars = load_bars(sym)
        pa = price_at(bars, int(ep))
        if not pa:
            continue
        entry = pa[4]
        w = window(bars, int(ep), H)
        if not w:
            continue
        hi, lo, lastc = w
        # retorno en la dirección de la tesis (a +Hmin) y MFE/MAE
        ret = (lastc - entry) / entry * 100 * th
        mfe = ((hi - entry) if th > 0 else (entry - lo)) / entry * 100
        mae = ((entry - lo) if th > 0 else (hi - entry)) / entry * 100
        win = ret > 0.05   # ganó si se movió >0.05% en la dirección de la tesis
        a = agg.setdefault(source, {"n": 0, "win": 0, "ret": 0.0, "mfe": 0.0, "mae": 0.0})
        a["n"] += 1; a["win"] += 1 if win else 0
        a["ret"] += ret; a["mfe"] += mfe; a["mae"] += mae
        if not win:
            pb = bb_pctb(bars, int(ep))
            losers.append((source, ts_txt, sym, th, round(ret, 2), round(mae, 2),
                           round(pb, 2) if pb is not None else None, (kind or "").strip()))
    # ---- reporte por fuente ----
    print(f"{'fuente':11s} {'n':>3s} {'WR@15m':>18s} {'ret medio':>9s} {'MFE':>6s} {'MAE':>6s}")
    print("-" * 62)
    for src, a in sorted(agg.items(), key=lambda x: -x[1]["n"]):
        n = a["n"]; wr, lo, hi = wilson(a["win"], n)
        print(f"{src:11s} {n:>3d}   {wr:>3d}% [{lo:>2d},{hi:>3d}]   "
              f"{a['ret']/n:>+7.2f}% {a['mfe']/n:>+5.2f} {a['mae']/n:>+5.2f}")
    tn = sum(a["n"] for a in agg.values()); tw = sum(a["win"] for a in agg.values())
    if tn:
        wr, lo, hi = wilson(tw, tn)
        print("-" * 62)
        print(f"{'TOTAL':11s} {tn:>3d}   {wr:>3d}% [{lo:>2d},{hi:>3d}]")
    # ---- diagnóstico de las EQUIVOCADAS ----
    print(f"\n=== SEÑALES EQUIVOCADAS (perdieron a +{H}min) — {len(losers)} ===")
    print("dividido por fuente + %B en el instante (BB context):")
    from collections import defaultdict
    byl = defaultdict(list)
    for l in losers:
        byl[l[0]].append(l)
    for src, ls in sorted(byl.items(), key=lambda x: -len(x[1])):
        # ¿cuántas eran band-walk (%B extremo en la dirección de continuación)?
        extreme = sum(1 for l in ls if l[6] is not None and (l[6] >= 0.95 or l[6] <= 0.05))
        avg_mae = sum(l[5] for l in ls) / len(ls)
        print(f"\n  {src}: {len(ls)} perdedoras · MAE medio {avg_mae:+.2f}% · "
              f"{extreme} con %B extremo (banda reventada = posible band-walk mal etiquetado)")
        for l in ls[:6]:
            pb = f"%B {l[6]}" if l[6] is not None else "%B s/d"
            print(f"    {l[1]} {l[2]:5s} tesis {'UP' if l[3]>0 else 'DN'} ret {l[4]:+.2f}% MAE {l[5]:+.2f}% {pb} | {l[7][:32]}")


if __name__ == "__main__":
    main()
