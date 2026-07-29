#!/usr/bin/env python3
"""yoel_real_options_backtest.py — el test DEFINITIVO del rebote de Yoel con
PRIMAS REALES de Polygon (2026-07-23, "just bought the options package").

Adios a la sintesis Black-Scholes: para cada señal de rebote-punto-medio
(detectada fiel: DIA=tendencia, HORA=correccion, toque SMA20 diaria) resuelve
el contrato ATM semanal REAL via Polygon, baja su camino de prima a 5m, y mide
el TP de +100% de Yoel con precios de mercado verdaderos (theta y spread reales
ya incluidos en los precios cotizados).

Requiere POLYGON_KEY en feeds.env. Señal-solamente.
"""
import csv, glob, math, os, time, json, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
K = None
for ln in open(os.path.join(REPO, "config", "feeds.env")):
    if ln.startswith("POLYGON_KEY"):
        K = ln.split("=", 1)[1].strip().strip('"')
if not K:
    raise SystemExit("falta POLYGON_KEY en feeds.env")

_cache = {}
def poly(url):
    if url in _cache:
        return _cache[url]
    full = url + ("&" if "?" in url else "?") + "apiKey=" + K
    for attempt in range(3):
        try:
            with urllib.request.urlopen(full, timeout=30) as r:
                d = json.load(r)
            _cache[url] = d
            return d
        except Exception:
            time.sleep(1.5)
    return {}

def load(sym):
    R = []
    try:
        for r in csv.reader(open(f"data/backtest/bars3mo5m_{sym}.csv")):
            try:
                R.append((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
            except Exception:
                continue
    except Exception:
        return []
    return R

def agg(R, secs):
    out = {}
    for t, o, h, l, c, v in R:
        k = t - t % secs
        if k not in out:
            out[k] = [t, o, h, l, c, v]
        else:
            b = out[k]; b[2] = max(b[2], h); b[3] = min(b[3], l); b[4] = c; b[5] += v
    return [tuple(v) for k, v in sorted(out.items())]

def sma_at(closes, times, t, n=20):
    idx = -1
    for k in range(len(times)):
        if times[k] <= t: idx = k
        else: break
    if idx < n: return None
    mn = sum(closes[idx - n + 1:idx + 1]) / n
    mp = sum(closes[idx - n:idx]) / n
    return mn, (mn > mp), closes[idx], (closes[idx - 1] if idx > 0 else closes[idx])

def next_friday(t):
    lt = time.localtime(t)
    days = (4 - lt.tm_wday) % 7
    return time.strftime("%Y-%m-%d", time.localtime(t + days * 86400))

def resolve_contract(sym, exp, cp, spot):
    """contrato REAL mas cercano a ATM para ese underlying/exp/tipo."""
    typ = "call" if cp == "C" else "put"
    lo = spot * 0.95; hi = spot * 1.05
    d = poly(f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={sym.upper()}"
             f"&expiration_date={exp}&contract_type={typ}&strike_price.gte={lo:.0f}"
             f"&strike_price.lte={hi:.0f}&expired=true&limit=50")
    rs = d.get("results", [])
    if not rs:
        return None, None
    best = min(rs, key=lambda r: abs(r["strike_price"] - spot))
    return best["ticker"], best["strike_price"]

def option_path(otk, day_from, day_to):
    """agregados 5m de la opcion entre dos fechas YYYY-MM-DD; lista (epoch, o,h,l,c)."""
    d = poly(f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/5/minute/{day_from}/{day_to}?adjusted=true&limit=5000&sort=asc")
    out = []
    for r in d.get("results", []):
        out.append((r["t"] // 1000, r.get("o"), r.get("h"), r.get("l"), r.get("c")))
    return out

def detect_rebote(sym):
    """señales de rebote fiel v5: (entry_epoch, cp). DIA tendencia, HORA correccion, toque SMA20 diaria."""
    R = load(sym)
    if len(R) < 300:
        return []
    H = agg(R, 3600); D = agg(R, 86400); M15 = agg(R, 900)
    Hc = [b[4] for b in H]; Ht = [b[0] for b in H]
    Dc = [b[4] for b in D]; Dt = [b[0] for b in D]
    M15t = [b[0] for b in M15]; M15v = [b[5] for b in M15]
    sigs = []; last = -10**9
    for gi in range(21, len(M15) - 1):
        t = M15t[gi]
        if t - last < 3600:
            continue
        dr = sma_at(Dc, Dt, t); hr = sma_at(Hc, Ht, t)
        if not dr or not hr:
            continue
        dsma, dup, dpx, _ = dr
        hsma, hup, hpx, hprev = hr
        vma = sum(M15v[gi - 50:gi]) / 50 if gi >= 50 else None
        vol_ok = bool(vma and M15v[gi] > vma)
        near = abs(dpx - dsma) / dsma <= 0.005
        cp = None
        if dup and near and hpx > hsma and hprev <= hsma:
            cp = "C"
        elif (not dup) and near and hpx < hsma and hprev >= hsma:
            cp = "P"
        if cp:
            last = t
            sigs.append((t, cp, vol_ok, dpx))
    return sigs

def main():
    import sys
    syms = sys.argv[1:] or [os.path.basename(f).split("bars3mo5m_")[1][:-4]
                            for f in sorted(glob.glob("data/backtest/bars3mo5m_*.csv"))]
    TP = 1.00
    res = {"con": {"w": 0, "n": 0, "ret": 0.0}, "sin": {"w": 0, "n": 0, "ret": 0.0}}
    resC = {"con": {"w": 0, "n": 0, "ret": 0.0}, "sin": {"w": 0, "n": 0, "ret": 0.0}}  # conservador: TP por CIERRE
    detail = []
    for sym in syms:
        for (t, cp, vol_ok, spot) in detect_rebote(sym):
            exp = next_friday(t)
            otk, strike = resolve_contract(sym, exp, cp, spot)
            if not otk:
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(t))
            path = option_path(otk, day, exp)
            # entrar en la primera barra de opcion cuyo epoch >= t (open siguiente)
            entry = None
            for (et, o, h, l, c) in path:
                if et >= t and o and o > 0.02:
                    entry = (et, o); break
            if not entry:
                continue
            e_t, e_px = entry
            ret = None
            for (et, o, h, l, c) in path:
                if et < e_t:
                    continue
                if h and h >= e_px * (1 + TP):   # +100% con el high real de la opcion (orden limite)
                    ret = TP; break
            if ret is None:
                # liquidar al ultimo close real disponible
                closes = [c for (et, o, h, l, c) in path if et >= e_t and c is not None]
                ret = (closes[-1] / e_px - 1) if closes else -1.0
                ret = max(ret, -1.0)
            b = res["con" if vol_ok else "sin"]
            b["n"] += 1; b["ret"] += ret; b["w"] += int(ret > 0)
            # conservador: +100% solo si un CIERRE 5m real lo alcanza (evita spikes de high ilíquidos)
            retC = None
            for (et, o, h, l, c) in path:
                if et < e_t: continue
                if c and c >= e_px * (1 + TP): retC = TP; break
            if retC is None:
                cl = [c for (et, o, h, l, c) in path if et >= e_t and c is not None]
                retC = max((cl[-1] / e_px - 1) if cl else -1.0, -1.0)
            bc = resC["con" if vol_ok else "sin"]
            bc["n"] += 1; bc["ret"] += retC; bc["w"] += int(retC > 0)
            detail.append({"sym": sym, "date": day, "cp": cp, "strike": strike,
                           "vol_ok": vol_ok, "entry": round(e_px, 2), "ret": round(ret, 2)})

    def wilson(w, n):
        if n == 0: return 0.0
        p = w / n; z = 1.96; d = 1 + z * z / n
        return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)

    print("=" * 74)
    print("YOEL REBOTE — PRIMAS REALES de Polygon (opcion ATM semanal, TP +100%)")
    print("=" * 74)
    for lbl in ("con", "sin"):
        b = res[lbl]
        if b["n"] == 0:
            print(f"  vol {lbl}: sin señales"); continue
        print(f"  vol {lbl.upper():3s}: n={b['n']:3d}  P(gana)={b['w']/b['n']*100:.0f}%  "
              f"ret/trade={b['ret']/b['n']*100:+.0f}% prima  wilson={wilson(b['w'],b['n'])*100:.0f}%")
    print("\n--- CONSERVADOR (TP por cierre 5m real, no spike de high):")
    for lbl in ("con", "sin"):
        b = resC[lbl]
        if b["n"] == 0: continue
        print(f"  vol {lbl.upper():3s}: n={b['n']:3d}  P(gana)={b['w']/b['n']*100:.0f}%  "
              f"ret/trade={b['ret']/b['n']*100:+.0f}% prima  wilson={wilson(b['w'],b['n'])*100:.0f}%")
    json.dump({"result": res, "conservative": resC, "detail": detail},
              open("data/backtest/scores_yoel_real_options.json", "w"), indent=1)
    print(f"\n{len(detail)} trades con prima real -> data/backtest/scores_yoel_real_options.json")
    for x in detail[:20]:
        print(f"  {x['date']} {x['sym']:5s} {x['cp']} K{x['strike']} "
              f"{'VOL' if x['vol_ok'] else '   '} entrada ${x['entry']} -> {x['ret']*100:+.0f}%")

if __name__ == "__main__":
    main()
