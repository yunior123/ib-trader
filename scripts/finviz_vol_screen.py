#!/usr/bin/env python
"""finviz_vol_screen.py — 3 lanes vol (2026-08-05, orden Yunior "filter finviz for squeeze, vrp
or volatility, overpriced options"). SQUEEZE: short float>15% + low float + sobre SMA20 + rvol
(candidato calls). VRP: IV ATM (UW si el plan lo cubre, si no Polygon snapshot) vs RV20 Polygon
— IV>>RV opciones CARAS (vender premium), IV<<RV BARATAS (comprar direccional). OVERPRICED:
VRP alto o IV pctile alto vs archivo propio (n etiquetado) + earnings<=5d = IV crush candidato
→ "comprados VETADOS, spreads o nada". Señal-solamente. Lote fuera de sesión.
Uso: ./venv/bin/python scripts/finviz_vol_screen.py [squeeze|vrp|overpriced ...]"""
import csv, datetime, glob, io, json, math, os, statistics, subprocess, sys, time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
OUT_DIR = os.path.join(ROOT, "data", "screener")
STAMP = os.path.join(ROOT, "data", ".finviz_last_call")  # ley: >=60s entre llamadas finviz

def env_key(*names):
    for line in open(os.path.join(ROOT, "config", "feeds.env")):
        line = line.strip()
        for k in names:
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def num(s):
    # jamás 0.0 en fallo de parseo: None o nada (regla de la casa)
    if s is None:
        return None
    s = str(s).strip().replace("%", "").replace(",", "")
    mult = 1.0
    if s[-1:] in "KMB":
        mult = {"K": 1e3, "M": 1e6, "B": 1e9}[s[-1]]
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None

# ---------- finviz ----------
FV_COLS = "1,6,25,30,50,52,59,63,64,65,66,67,68"
FV_BASE = "https://elite.finviz.com/export/screener?v=152&f={f}&auth={a}&c=" + FV_COLS

def finviz_fetch(filt):
    if os.path.exists(STAMP):
        wait = 61 - (time.time() - os.path.getmtime(STAMP))
        if wait > 0:
            time.sleep(wait)
    a = env_key("FINVIZ_AUTH3", "FINVIZ_AUTH")
    if not a:
        sys.exit("SIN TOKEN finviz (feeds.env)")
    r = subprocess.run(["curl", "-s", "--max-time", "25", FV_BASE.format(f=filt, a=a)],
                       capture_output=True, text=True)
    open(STAMP, "w").close()
    if not r.stdout.startswith('"'):
        sys.exit(f"FINVIZ ROTO: {r.stdout[:120]!r}")
    return r.stdout

def finviz_rows(body):
    return list(csv.DictReader(io.StringIO(body)))

# ---------- polygon ----------
POLY = env_key("POLYGON_KEY")

def poly_json(url):
    full = url + ("&" if "?" in url else "?") + "apiKey=" + POLY
    for wait in (0, 15):
        if wait:
            time.sleep(wait)
        try:
            return json.load(urllib.request.urlopen(full, timeout=25))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return None
        except Exception:
            return None
    return None

def daily_closes(sym):
    # cierre diario: poly_bars (BD local, hasta el fin del backfill) + bars 1m archivados
    closes = {}
    try:
        import sqlite3
        db = sqlite3.connect(f"file:{os.path.join(ROOT,'data','trades.db')}?mode=ro", uri=True)
        for d, c in db.execute(
                "SELECT date(ts/1000,'unixepoch') d, c FROM poly_bars WHERE sym=? "
                "AND ts IN (SELECT MAX(ts) FROM poly_bars WHERE sym=? "
                "GROUP BY date(ts/1000,'unixepoch'))", (sym, sym)):
            closes[d] = c
        db.close()
    except Exception:
        pass
    for fn in glob.glob(os.path.join(ROOT, "data", "history", "*", "bars",
                                     f"{sym.lower()}.txt")):
        try:
            last = open(fn).readlines()[-1].split()
            closes[os.path.basename(os.path.dirname(os.path.dirname(fn)))] = float(last[4])
        except (OSError, IndexError, ValueError):
            continue
    return [closes[d] for d in sorted(closes)]

def rv20(sym):
    closes = daily_closes(sym)[-21:]
    if len(closes) < 21:
        return None
    rets = [math.log(b / a) for a, b in zip(closes[:-1], closes[1:])]
    return statistics.stdev(rets) * math.sqrt(252)

def local_spot(sym):
    closes = daily_closes(sym)
    return closes[-1] if closes else None

def poly_atm_iv(sym, spot):
    lo, hi = spot * 0.98, spot * 1.02
    d0 = datetime.date.today()
    e0, e1 = d0 + datetime.timedelta(days=15), d0 + datetime.timedelta(days=60)
    j = poly_json(f"https://api.polygon.io/v3/snapshot/options/{sym}"
                  f"?strike_price.gte={lo:.2f}&strike_price.lte={hi:.2f}"
                  f"&expiration_date.gte={e0}&expiration_date.lte={e1}&limit=100")
    ivs = [r["implied_volatility"] for r in (j or {}).get("results", [])
           if r.get("implied_volatility")]
    if len(ivs) < 4:
        return None
    return statistics.median(ivs)

# ---------- unusual whales (primera opción si el plan lo cubre; hoy 403 → fallback) ----------
UW = env_key("UW_TOKEN")
_uw_dead = 0

def uw_atm_iv(sym):
    global _uw_dead
    if not UW or _uw_dead >= 2:
        return None
    req = urllib.request.Request(
        f"https://api.unusualwhales.com/api/stock/{sym}/volatility/stats",
        headers={"Authorization": "Bearer " + UW, "Accept": "application/json"})
    try:
        j = json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _uw_dead += 1
        return None
    except Exception:
        return None
    d = j.get("data") if isinstance(j, dict) else None
    if isinstance(d, list) and d:
        d = d[-1]
    for k in ("iv", "implied_volatility", "iv30"):
        v = num((d or {}).get(k))
        if v:
            return v
    return None

# ---------- IV percentil vs archivo propio de cadenas (IV medida Polygon) ----------
def archived_atm_iv(sym):
    out = []
    for fn in sorted(glob.glob(os.path.join(ROOT, "data", "history", "*",
                                            f"chain_full_{sym.lower()}.json"))):
        try:
            d = json.load(open(fn))
        except (OSError, ValueError):
            continue
        spot = (d.get("meta") or {}).get("spot")
        if not spot:
            continue
        day = os.path.basename(os.path.dirname(fn))
        ivs = []
        for r in d.get("results", []):
            iv, det = r.get("implied_volatility"), r.get("details", {})
            if not iv:
                continue
            k, exp = det.get("strike_price"), det.get("expiration_date", "")
            if not k or abs(k - spot) / spot > 0.02:
                continue
            try:
                dte = (datetime.date.fromisoformat(exp) - datetime.date.fromisoformat(day)).days
            except ValueError:
                continue
            if 15 <= dte <= 60:
                ivs.append(iv)
        if len(ivs) >= 4:
            out.append(statistics.median(ivs))
    return out

def iv_pctile(sym, iv_now):
    hist = archived_atm_iv(sym)
    if len(hist) < 6:
        return None, len(hist)
    return 100.0 * sum(1 for h in hist if h <= iv_now) / len(hist), len(hist)

# ---------- lanes ----------
def lane_squeeze():
    # rvol NO es gate (premarket es ~0 para todo, medido 2026-08-05): es impulso en el score
    body = finviz_fetch("sh_short_o15,sh_opt_option,sh_avgvol_o500,sh_price_o5,ta_sma20_pa")
    cands = []
    for r in finviz_rows(body):
        px, shortf = num(r.get("Price")), num(r.get("Short Float"))
        avgv, fl = num(r.get("Average Volume")), num(r.get("Shares Float"))
        if None in (px, shortf, avgv):
            continue
        avg_dollar = px * avgv * 1e3  # finviz exporta AvgVol en MILES (medido: AAOI 11947.76)
        if avg_dollar < 20e6:
            continue
        chg, rvol = num(r.get("Change")), num(r.get("Relative Volume"))
        float_m = fl if fl else None  # finviz exporta Shares Float en MILLONES (BTDR 131.39)
        boost = min(max(math.sqrt(100 / float_m), 0.5), 3.0) if float_m else 1.0
        momentum = 1.0 + max((rvol or 0) - 1, 0) + max(chg or 0, 0) / 2
        score = shortf * boost * momentum * math.log10(avg_dollar)
        f_txt = f" float {float_m:.0f}M" if float_m else ""
        rv_txt = f" rvol {rvol:.1f}" if rvol else " (rvol premarket sin dato)"
        cands.append({"sym": r["Ticker"], "price": px, "chg_pct": chg, "rvol": rvol,
                      "short_float_pct": shortf, "float_m": float_m,
                      "sma20_pct": num(r.get("20-Day Simple Moving Average")),
                      "rsi": num(r.get("Relative Strength Index (14)")),
                      "avg_dollar_m": avg_dollar / 1e6, "earn": r.get("Earnings Date", ""),
                      "score": score,
                      "note": f"squeeze: SF {shortf:.0f}%{f_txt}{rv_txt} "
                              f"sobre SMA20 → CALLS"})
    cands.sort(key=lambda c: -c["score"])
    return cands[:12]

def vrp_table():
    fleet = open(os.path.join(ROOT, "data", "fleet.txt")).read().split()
    rows, sin_dato = [], []
    for sym in fleet:
        iv, src = uw_atm_iv(sym), "uw"
        spot = local_spot(sym)
        if iv is None and spot:
            iv, src = poly_atm_iv(sym, spot), "poly_snapshot"
        rv = rv20(sym)
        if iv is None or rv is None or rv == 0:
            sin_dato.append(sym)
            continue
        rows.append({"sym": sym, "iv": round(iv, 4), "rv20": round(rv, 4),
                     "vrp": round(iv / rv, 3), "iv_source": src, "spot": spot})
        time.sleep(0.15)
    return rows, sin_dato

def lane_vrp(rows):
    cands = []
    for r in rows:
        v = r["vrp"]
        if v >= 1.35:
            note = f"IV {r['iv']:.0%} vs RV20 {r['rv20']:.0%} = CARAS → vender premium, no comprar"
        elif v <= 0.85:
            note = f"IV {r['iv']:.0%} vs RV20 {r['rv20']:.0%} = BARATAS → comprar direccional OK"
        else:
            continue
        cands.append({**r, "score": abs(math.log(v)), "note": note})
    cands.sort(key=lambda c: -c["score"])
    return cands

def lane_overpriced(rows):
    body = finviz_fetch("earningsdate_nextdays5,sh_opt_option")
    earn = {r["Ticker"]: r.get("Earnings Date", "") for r in finviz_rows(body)}
    cands = []
    for r in rows:
        pct, n = iv_pctile(r["sym"], r["iv"])
        caro = r["vrp"] >= 1.5 or (pct is not None and pct >= 80 and r["vrp"] >= 1.15)
        if not caro:
            continue
        e = earn.get(r["sym"], "")
        why = f"earnings {e[:10]} → IV crush candidato" if e else "IV alto sin catalizador"
        cands.append({**r, "iv_pctile": round(pct, 1) if pct is not None else None,
                      "iv_pctile_n": n, "earnings": e[:10],
                      "score": r["vrp"] * (1.5 if e else 1.0),
                      "note": f"premium CARO ({why}): puts/calls comprados VETADOS, "
                              f"spreads o nada"})
    cands.sort(key=lambda c: -c["score"])
    return cands

def emit(lane, cands):
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    line = json.dumps({"ts": ts, "kind": "vol_screen", "lane": lane, "candidates": cands})
    day = datetime.date.today().strftime("%Y%m%d")
    path = os.path.join(OUT_DIR, f"vol_screen_{day}.jsonl")
    prev = open(path).read() if os.path.exists(path) else ""
    tmp = path + ".tmp"
    open(tmp, "w").write(prev + line + "\n")
    os.replace(tmp, path)
    print(f"\n=== {lane.upper()} ({len(cands)} candidatos) ===")
    for c in cands[:8]:
        print(f"  {c['sym']:6} {c.get('price') or c.get('spot') or 0:>9.2f} "
              f"score {c['score']:.2f}  {c['note']}")

def main():
    want = sys.argv[1:] or ["squeeze", "vrp", "overpriced"]
    rows = None
    if "squeeze" in want:
        emit("squeeze", lane_squeeze())
    if "vrp" in want or "overpriced" in want:
        rows, sin_dato = vrp_table()
        if sin_dato:
            print(f"[vrp] sin dato IV/RV (excluidos, no fabricados): {' '.join(sin_dato)}")
    if "vrp" in want:
        emit("vrp", lane_vrp(rows))
    if "overpriced" in want:
        emit("overpriced", lane_overpriced(rows))

if __name__ == "__main__":
    main()
