#!/usr/bin/env python
"""daily_fleet_plans.py — plan picaro diario por ticker (PDF + email Resend + drafts X).

Por ticker: precio overnight/premarket, expansion vs ATR (dip de liquidez en apertura),
muros OI + max pain + GEX propio (flip estimado, regimen), griegas BS de strikes clave,
Bollinger diario/15m, ballenas (tape propia), Korea (memoria) y futuros US.
Salida: ~/Desktop/planes-YYYY-MM-DD/<SYM>_plan.pdf + email + out x_drafts/.

Uso: ./venv/bin/python scripts/daily_fleet_plans.py [--tickers QQQ,NVDA] [--no-email]
Programado por launchd com.ibtrader.dailyplans a las 04:00 ET.
SEÑAL-SOLAMENTE: jamas ordena. 2026-07-21."""
import argparse, base64, datetime as dt, json, math, os, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import requests
import yfinance as yf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

# Mapa gamma MEDIDO en casa (griegas REALES de Polygon sobre la cadena archivada). Sustituye
# a gexa.ai, muerto el 2026-07-25. Si el modulo no se puede importar NO se inventa un regimen:
# se grita en stderr y el plan lo DICE en su propio texto (ver gex_snapshot_for / plan_engine).
GEX_SNAP_WHY = None
try:
    import gex_snapshot
except Exception as _e:                      # repo a medias: se degrada, pero a la vista
    gex_snapshot = None
    GEX_SNAP_WHY = f"modulo gex_snapshot no importable: {_e}"
    print(f"AVISO: {GEX_SNAP_WHY} -> los planes iran SIN regimen gamma medido", file=sys.stderr)

# ---------- flota: metadata por ticker ----------
FLEET = {
    "QQQ":  dict(style="0dte", fut="NQ=F", korea=False),
    "SPY":  dict(style="0dte", fut="ES=F", korea=False),
    "NVDA": dict(style="weekly", fut="NQ=F", korea=True),
    "TSLA": dict(style="weekly", fut="NQ=F", korea=False),
    "MU":   dict(style="weekly", fut="NQ=F", korea=True),
    "SMH":  dict(style="weekly", fut="NQ=F", korea=True),
    "AMD":  dict(style="weekly", fut="NQ=F", korea=True),
    "AAPL": dict(style="weekly", fut="NQ=F", korea=False),
    "MSFT": dict(style="weekly", fut="NQ=F", korea=False),
    "META": dict(style="weekly", fut="NQ=F", korea=False),
    "AMZN": dict(style="weekly", fut="NQ=F", korea=False),
    "GOOGL":dict(style="weekly", fut="NQ=F", korea=False),
    "INTC": dict(style="weekly", fut="NQ=F", korea=True),
    "TSM":  dict(style="weekly", fut="NQ=F", korea=True),
    "ASML": dict(style="weekly", fut="NQ=F", korea=True, europe="ASML.AS"),
    "TXN":  dict(style="weekly", fut="NQ=F", korea=True),
    "QCOM": dict(style="weekly", fut="NQ=F", korea=True),
    "AVGO": dict(style="weekly", fut="NQ=F", korea=True),
    "NFLX": dict(style="weekly", fut="NQ=F", korea=False),
    # `no_gex_map`: sin mapa gamma de terceros ni propio fiable (gexa nunca cubrio NOK; y su
    # cadena Polygon suele quedarse sin griegas usables) -> muros OI de TWS y nada mas.
    "NOK":  dict(style="weekly", fut="ES=F", korea=False, no_gex_map=True),
    "GLD":  dict(style="weekly", fut="ES=F", korea=False),
    "XLK":  dict(style="weekly", fut="NQ=F", korea=False),
    "EWY":  dict(style="weekly", fut="ES=F", korea=True),
    "DRAM": dict(style="weekly", fut="NQ=F", korea=True),
    "SPCX": dict(style="weekly", fut="NQ=F", korea=False),
    "SKHY": dict(style="weekly", fut="NQ=F", korea=True),
    # ampliacion 2026-07-22 (orden Yunior): storage/memoria + equipos, todos
    # miembros QQQ verificados (LRCX 1.79%, SNDK 0.93%, WDC/STX <0.9%).
    "LRCX": dict(style="weekly", fut="NQ=F", korea=True),
    "SNDK": dict(style="weekly", fut="NQ=F", korea=True),
    "WDC":  dict(style="weekly", fut="NQ=F", korea=True),
    "STX":  dict(style="weekly", fut="NQ=F", korea=True),
}

def env_load():
    d = {}
    for f in ("feeds.env", "x.env"):
        try:
            for ln in open(os.path.join(REPO, f)):
                ln = ln.strip()
                if "=" in ln and not ln.startswith("#"):
                    k, v = ln.split("=", 1)
                    d[k.strip()] = v.strip().strip('"').strip("'")
        except FileNotFoundError:
            pass
    return d
ENV = env_load()

def load_calibration():
    try: return json.load(open("data/calibration.json"))
    except Exception: return {}
CALIB = load_calibration()

def load_breadth():
    try: return json.load(open("data/breadth.json"))
    except Exception: return {}
BREADTH = load_breadth()

def load_patterns():
    try: return json.load(open("data/patterns.json"))
    except Exception: return {}
PATTERNS = load_patterns()

def measured_prob(setup_type, regime, heuristic):
    """Reemplaza la prob adivinada por la MEDIDA si el bucket tiene muestra suficiente.
    Nada hardcoded: viene de calib_log real. Si no hay datos, devuelve la heuristica."""
    b = CALIB.get(f"{setup_type}|{regime}")
    if b and b.get("trust"):
        return int(round(b["ci_low"] * 100)), f"MEDIDA n={b['n']} (CI-low, honesta)"
    if b:
        return heuristic, f"heuristica (medida provisional n={b['n']}, aun no fiable)"
    return heuristic, "heuristica (sin muestra aun)"

# ---------- matematicas ----------
def bs_greeks(S, K, T, iv, cp, r=0.045):
    if T <= 0 or iv <= 0 or S <= 0: return {}
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    delta = N(d1) if cp == "C" else N(d1) - 1
    gamma = pdf / (S * sq)
    theta = (-(S * pdf * iv) / (2 * math.sqrt(T)) - (r * K * math.exp(-r * T) * (N(d2) if cp == "C" else N(-d2)) * (1 if cp == "C" else -1))) / 365
    vega = S * pdf * math.sqrt(T) / 100
    return dict(delta=delta, gamma=gamma, theta=theta, vega=vega)

def pick_expiry(t, style):
    opts = t.options
    if not opts: return None
    today = time.strftime("%Y-%m-%d")
    if style == "0dte":
        for e in opts:
            if e >= today: return e
    for e in opts:  # primer viernes >= hoy
        if e >= today and time.strptime(e, "%Y-%m-%d").tm_wday == 4: return e
    return opts[0]

def chain_stats(t, exp, spot):
    ch = t.option_chain(exp)
    c, p = ch.calls.fillna(0), ch.puts.fillna(0)
    lo, hi = spot * 0.965, spot * 1.035
    c = c[(c.strike >= lo) & (c.strike <= hi)]
    p = p[(p.strike >= lo) & (p.strike <= hi)]
    ks = sorted(set(c.strike) | set(p.strike))
    coi = dict(zip(c.strike, c.openInterest)); poi = dict(zip(p.strike, p.openInterest))
    pain = min(ks, key=lambda s: sum(max(0, s - k) * coi.get(k, 0) for k in ks)
                               + sum(max(0, k - s) * poi.get(k, 0) for k in ks)) if ks else spot
    # GEX propio: gamma_BS * OI * 100 * S ; calls + / puts - (convencion dealer-long-calls)
    T = max((time.mktime(time.strptime(exp, "%Y-%m-%d")) + 16 * 3600 - time.time()) / (365 * 86400), 1e-4)
    gex = {}
    for df, sign, right in ((c, +1, "C"), (p, -1, "P")):
        for _, r_ in df.iterrows():
            g = bs_greeks(spot, float(r_.strike), T, float(r_.impliedVolatility) or 0.3, right)
            if g: gex[r_.strike] = gex.get(r_.strike, 0) + sign * g["gamma"] * float(r_.openInterest) * 100 * spot
    net_gex = sum(gex.values())
    # flip: strike donde el GEX acumulado (desde abajo) cruza 0
    flip = None
    if gex:
        cum, last_k = 0, None
        for k in sorted(gex):
            prev = cum; cum += gex[k]
            if prev < 0 <= cum or prev > 0 >= cum: flip = k
            last_k = k
        if flip is None: flip = last_k if net_gex < 0 else min(gex)
    cw = c.nlargest(4, "openInterest")[["strike", "openInterest", "volume", "bid", "ask", "impliedVolatility"]].values.tolist()
    pw = p.nlargest(4, "openInterest")[["strike", "openInterest", "volume", "bid", "ask", "impliedVolatility"]].values.tolist()
    atm = min(ks, key=lambda k: abs(k - spot)) if ks else spot
    ca = c[c.strike == atm]; pa = p[p.strike == atm]
    straddle = (float(ca.ask.iloc[0]) if len(ca) else 0) + (float(pa.ask.iloc[0]) if len(pa) else 0)
    iv_atm = float(ca.impliedVolatility.iloc[0]) if len(ca) else 0
    pcv = p.volume.sum() / max(c.volume.sum(), 1)
    pco = p.openInterest.sum() / max(c.openInterest.sum(), 1)
    greeks_atm = bs_greeks(spot, atm, T, iv_atm or 0.3, "C")
    return dict(pain=pain, gex=gex, net_gex=net_gex, flip=flip, cw=cw, pw=pw, atm=atm,
                straddle=straddle, imove=straddle / spot * 100 if spot else 0, iv=iv_atm,
                pcv=pcv, pco=pco, T=T, greeks=greeks_atm, exp=exp)

def ibkr_chain_stats(sym, spot):
    """Cadena real IBKR del cache opt_chain_<sym>.txt (opt_chain_cache.py, TWS vivo).
    Devuelve mismo shape que chain_stats o None si el cache falta/esta viejo (>45min)."""
    pth = f"data/opt_chain_{sym.lower()}.txt"
    try:
        if time.time() - os.path.getmtime(pth) > 45 * 60: return None
        rows = []
        exps = set()
        for ln in open(pth):
            if ln.startswith("#"): continue
            f = ln.split()
            if len(f) < 10: continue
            k, right, exp, bid, ask, vol, oi, iv, delta, gamma = f[:10]
            rows.append((float(k), right, exp, float(bid), float(ask), int(float(vol)),
                         int(float(oi)), float(iv), float(delta), float(gamma)))
            exps.add(exp)
        if not rows: return None
        exp = sorted(exps)[0]
        rows = [r for r in rows if r[2] == exp and spot * 0.965 <= r[0] <= spot * 1.035]
        if not rows: return None
        c = [r for r in rows if r[1] == "C"]; pz = [r for r in rows if r[1] == "P"]
        ks = sorted({r[0] for r in rows})
        coi = {r[0]: r[6] for r in c}; poi = {r[0]: r[6] for r in pz}
        pain = min(ks, key=lambda st: sum(max(0, st - k) * coi.get(k, 0) for k in ks)
                                    + sum(max(0, k - st) * poi.get(k, 0) for k in ks))
        gex = {}
        for r in rows:
            g = r[9] if r[9] > 0 else 0
            gex[r[0]] = gex.get(r[0], 0) + (1 if r[1] == "C" else -1) * g * r[6] * 100 * spot
        net = sum(gex.values())
        flip = None; cum = 0
        for k in sorted(gex):
            prev = cum; cum += gex[k]
            if prev < 0 <= cum or prev > 0 >= cum: flip = k
        cw = sorted(c, key=lambda r: -r[6])[:4]; pw = sorted(pz, key=lambda r: -r[6])[:4]
        fmt = lambda r: [r[0], r[6], r[5], r[3], r[4], r[7]]
        atm = min(ks, key=lambda k: abs(k - spot))
        ca = [r for r in c if r[0] == atm]; pa = [r for r in pz if r[0] == atm]
        str_ = (ca[0][4] if ca and ca[0][4] > 0 else 0) + (pa[0][4] if pa and pa[0][4] > 0 else 0)
        iv_atm = ca[0][7] if ca and ca[0][7] > 0 else 0
        pcv = sum(r[5] for r in pz) / max(sum(r[5] for r in c), 1)
        pco = sum(r[6] for r in pz) / max(sum(r[6] for r in c), 1)
        T = max((time.mktime(time.strptime(exp, "%Y%m%d")) + 16 * 3600 - time.time()) / (365 * 86400), 1e-4)
        gk = dict(delta=ca[0][8], gamma=ca[0][9], theta=0, vega=0) if ca and ca[0][8] > -1 else bs_greeks(spot, atm, T, iv_atm or .3, "C")
        return dict(pain=pain, gex=gex, net_gex=net, flip=flip, cw=[fmt(r) for r in cw],
                    pw=[fmt(r) for r in pw], atm=atm, straddle=str_, imove=str_/spot*100,
                    iv=iv_atm, pcv=pcv, pco=pco, T=T, greeks=gk, exp=f"{exp} IBKR✓")
    except Exception:
        return None

def overnight_stats(t, spot_now):
    d = t.history(period="3mo", interval="1d")
    if len(d) < 25: return {}
    closes, opens_, highs, lows = d.Close.values, d.Open.values, d.High.values, d.Low.values
    atr = float(np.mean(np.maximum(highs[-15:] - lows[-15:],
                 np.maximum(abs(highs[-15:] - closes[-16:-1]), abs(lows[-15:] - closes[-16:-1])))))
    prev_close = float(closes[-1])
    gap_pct = (spot_now - prev_close) / prev_close * 100
    ext_atr = (spot_now - prev_close) / atr if atr else 0
    # historico: gaps >0.3% en la misma direccion — ¿cuantos hicieron dip que toco el cierre previo (fill)?
    fills = tot = 0
    for i in range(1, len(d)):
        g = (opens_[i] - closes[i - 1]) / closes[i - 1] * 100
        if (gap_pct >= 0 and g > 0.3) or (gap_pct < 0 and g < -0.3):
            tot += 1
            if (gap_pct >= 0 and lows[i] <= closes[i - 1]) or (gap_pct < 0 and highs[i] >= closes[i - 1]):
                fills += 1
    fill_rate = fills / tot * 100 if tot else 50
    # BB diario
    ma, sd = float(np.mean(closes[-20:])), float(np.std(closes[-20:], ddof=1))
    pb = (spot_now - (ma - 2 * sd)) / (4 * sd) if sd else 0.5
    return dict(prev_close=prev_close, atr=atr, gap_pct=gap_pct, ext_atr=ext_atr,
                fill_rate=fill_rate, n_gaps=tot, bb_lo=ma - 2 * sd, bb_hi=ma + 2 * sd, pb=pb)

def prepost_series(t):
    try:
        h = t.history(period="2d", interval="5m", prepost=True)
        return h.Close
    except Exception:
        return None

def whale_read(sym):
    buys = sells = 0.0
    try:
        for ln in open(f"data/whale_{sym.lower()}.txt"):
            f = ln.split()
            if len(f) < 4: continue
            lt = time.localtime(float(f[0]))
            if lt.tm_hour * 100 + lt.tm_min >= 1558: continue
            if int(f[3]) > 0: buys += float(f[2])
            else: sells += float(f[2])
    except Exception:
        pass
    return buys, sells

def korea_read():
    out = {}
    for sym, tk in (("KOSPI", "^KS11"), ("Samsung", "005930.KS"), ("SK-Hynix", "000660.KS")):
        try:
            h = yf.Ticker(tk).history(period="2d")
            out[sym] = (float(h.Close.iloc[-1]) / float(h.Close.iloc[-2]) - 1) * 100
        except Exception:
            pass
    return out

def europe_read(syms):
    """Momentum del listado europeo (lidera ~6h) para euro-tickers. ej ASML.AS Amsterdam.
    + STOXX50 como termometro. Delayed pero adelanta la apertura US."""
    out = {}
    try:
        import yfinance as yf
        for eu in set(s for s in syms if s):
            try:
                h = yf.Ticker(eu).history(period="2d")
                out[eu] = (float(h.Close.iloc[-1]) / float(h.Close.iloc[-2]) - 1) * 100
            except Exception: pass
        try:
            h = yf.Ticker("^STOXX50E").history(period="2d")
            out["STOXX50"] = (float(h.Close.iloc[-1]) / float(h.Close.iloc[-2]) - 1) * 100
        except Exception: pass
    except Exception: pass
    return out

def vx_term():
    """VIX spot + futuros VX (CBOE publico, delayed ~15m): contango/backwardation = regimen de vol."""
    try:
        H = {"User-Agent": "Mozilla/5.0"}
        vix = requests.get("https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json",
                           headers=H, timeout=10).json()["data"]["current_price"]
        fut = requests.get("https://www-api.cboe.com/us/futures/api/data/?symbol=VX",
                           headers=H, timeout=10).json()
        rows = sorted([(f.get("expiration", ""), float(f.get("last_price") or f.get("settlement") or 0))
                       for f in fut.get("data", []) if (f.get("last_price") or f.get("settlement"))],)[:3]
        if not rows or not vix: return {}
        vx1 = rows[0][1]; vx2 = rows[1][1] if len(rows) > 1 else vx1
        b1 = (vx1 - vix) / vix * 100; b2 = (vx2 - vx1) / vx1 * 100 if vx1 else 0
        if b1 < -1: reg = "BACKWARDATION — MIEDO AHORA: dia de vol, tamaño mitad, respetar aceleradores"
        elif b1 < 1.5: reg = "FLAT — tension: la calma cuesta poco, vigilar"
        else: reg = "CONTANGO — calma pagada: prima de miedo normal, pin plays viables"
        return dict(vix=vix, vx1=vx1, vx2=vx2, b1=b1, b2=b2, reg=reg)
    except Exception:
        return {}

def futures_read():
    out = {}
    for lab, tk in (("NQ", "NQ=F"), ("ES", "ES=F")):
        try:
            t = yf.Ticker(tk)
            h = t.history(period="2d", interval="1d")
            prev = float(h.Close.iloc[-2]) if len(h) >= 2 else float(h.Close.iloc[-1])
            # last REALTIME del overnight (fast_info sigue el globex vivo), no
            # el cierre diario — cazado 2026-07-22: % de futuros viejo en premarket
            last = float(t.fast_info.last_price or h.Close.iloc[-1])
            out[lab] = (last / prev - 1) * 100
        except Exception:
            pass
    return out

# ---------- motor del plan picaro ----------
STALE_EARN_H = 6.0   # mismo ciclo que x_earnings_post.MAX_AGE_S: pasarlo = Finviz no re-verifico

def earnings_calendar_dated():
    """({SYM:(fecha,'BMO'|'AMC',datetime)}, edad_horas_del_CSV) via x_earnings_post (v=152).
    fetch_csv RE-VERIFICA contra Finviz si el cache pasa de 6h porque Finviz MUEVE fechas.
    Si la re-verificacion falla se sirve el CSV rancio **con su edad** y el plan lo dice:
    callar un print que viene es peor que un dato viejo etiquetado.
    (None, edad|None) si no hay ni cache legible — jamas {} fabricado."""
    try:
        import x_earnings_post as xep
    except Exception as e:
        print(f"AVISO earnings: x_earnings_post no importable ({e})", file=sys.stderr)
        return None, None
    body = xep.fetch_csv("152", xep.CACHE_152, xep.token(), cols=xep.COLS_152)
    if body is None:
        try:
            body = open(xep.CACHE_152).read()
            print("AVISO earnings: Finviz no re-verifico; se usa el CSV RANCIO, etiquetado",
                  file=sys.stderr)
        except OSError as e:
            print(f"AVISO earnings: sin CSV de earnings ({e})", file=sys.stderr)
            return None, None
    try:
        age_h = (time.time() - os.path.getmtime(xep.CACHE_152)) / 3600.0
    except OSError:
        age_h = None
    rows = xep.parse_csv(body)
    if not rows:
        return None, age_h
    out = {}
    for row in rows:
        sym = (row.get("Ticker") or "").strip().upper()
        parsed = xep.parse_earn(row.get("Earnings Date"))
        if sym and parsed:
            out[sym] = parsed
    return (out or None), age_h

def load_earnings_calendar():
    """Solo el dict (o None). La edad del CSV la sirve earnings_calendar_dated()."""
    return earnings_calendar_dated()[0]

def earnings_veto_lines(sym, earn, today=None, age_h=None, cal_ok=True):
    """Texto de calendario+veto duro (regla 4: jamas aguantar prima comprada a traves
    del print). AMC bite al cierre del propio dia del print; BMO bite al cierre del dia
    ANTERIOR (el print ya salio antes de esa apertura). `earn` = (fecha,sesion,datetime)
    o None. Sin earnings y con calendario sano -> []; calendario CAIDO -> aviso, nunca
    silencio; CSV rancio -> se dice la edad y el veto se marca como no re-verificado."""
    hoy = today or time.strftime("%Y-%m-%d")
    if not earn:
        if cal_ok:
            return []
        return ["📅 EARNINGS: calendario NO verificado hoy (feed Finviz caido) —",
                f"  confirmar a mano la fecha de {sym} antes de aguantar prima comprada."]
    edate, esess, edt = earn
    veto_date = edate if esess == "AMC" else (edt - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    sesion_txt = "tras el cierre (AMC)" if esess == "AMC" else "antes de abrir (BMO)"
    rancio = age_h is not None and age_h > STALE_EARN_H
    out = [f"📅 EARNINGS {edate} {sesion_txt}."
           + (f" ⚠ dato RANCIO ({age_h:.0f}h sin re-verificar; Finviz mueve fechas)" if rancio else "")]
    if hoy == veto_date:
        out.append(f"  🚫 VETO HOY: prima comprada de {sym} FUERA antes del cierre —")
        out.append("  regla 4: jamas aguantar prima comprada a traves del print.")
        if rancio:
            out.append("  fecha sin re-verificar hoy: confirmarla antes de fiarse del veto.")
    elif hoy < veto_date:
        out.append(f"  Veto de prima comprada entra en vigor al cierre de {veto_date}.")
    else:
        out.append(f"  Print ya paso ({edate}); veto ya no aplica.")
        if rancio:
            out.append("  dato rancio: si Finviz movio la fecha el print puede seguir pendiente.")
    return out

def finviz_read(sym):
    try:
        d = dict(ln.strip().split("=", 1) for ln in open(f"data/finviz_{sym.lower()}.txt") if "=" in ln)
        if time.time() - float(d.get("ts", 0)) > 36 * 3600: return {}
        return d
    except Exception:
        return {}

def live_spot(sym, max_age_s=180):
    """Spot REALTIME del bridge IBKR (data/nbbo_<sym>.txt, SIP 4/s, incluye
    premarket) — yfinance fast_info da el cierre de ayer en premarket (cazado
    2026-07-22: PDFs con precios viejos). Fallback limpio: None -> yfinance."""
    try:
        ln = open(f"data/nbbo_{sym.lower()}.txt").read().split()
        ep, bid, ask = float(ln[0]), float(ln[1]), float(ln[2])
        if time.time() - ep <= max_age_s and 0 < bid < ask:
            return (bid + ask) / 2.0
    except Exception:
        pass
    return None

def gex_snapshot_for(sym):
    """Mapa gamma MEDIDO de `sym`: data/gex_snapshot.json, calculado por scripts/gex_snapshot.py
    con las griegas REALES de Polygon sobre data/history/<fecha>/chain_full_<sym>.json.
    (Sustituye al difunto gexa.ai, 2026-07-25. La ruta la resuelve el propio modulo desde
    __file__ — aqui no se hardcodea nada.)

    CADUCIDAD: el mapa se construye sobre la cadena ARCHIVADA del dia, asi que la mtime del
    fichero envejece sin que el mapa deje de ser vigente (el del viernes manda todo el fin de
    semana). Por eso: 36h de fichero Y ADEMAS `chain_date` dentro de los ultimos 5 dias de
    calendario — el mismo margen que gex_snapshot.latest_chain acepta al construirlo.

    Devuelve el dict del simbolo o **None**. Nunca {} y nunca un cero: sin `score` no hay signo
    y sin signo no hay regimen; afirmar "0" seria convertir "no se" en "se, y es cero"."""
    if gex_snapshot is None:
        return None
    snap = gex_snapshot.load(max_age_h=36)       # load() ya devuelve None (jamas {}) si falla
    if not snap:
        return None
    g = snap.get(sym.upper())
    if not isinstance(g, dict):
        return None                              # simbolo omitido por el builder (sin cadena/griegas)
    if not isinstance(g.get("score"), (int, float)) or g.get("flip") is None:
        return None                              # sin score/flip no se afirma regimen
    cd = g.get("chain_date")
    try:
        edad_d = (dt.date.today() - dt.date.fromisoformat(str(cd))).days
    except (TypeError, ValueError):
        return None                              # sin fecha de cadena no se puede fechar el mapa
    if not 0 <= edad_d <= 5:
        return None                              # cadena rancia (o del futuro): no se usa
    return g

MACRO_AHEAD_D = 7        # el print de toda la semana entra en el plan (FOMC del miercoles se ve el domingo)
MACRO_BACK_D = 1         # hacia atras solo la resaca del dia anterior

def load_macro_events():
    """CPI/FOMC/NFP confirmados de los proximos MACRO_AHEAD_D dias (macro_calendar.py).
    None si el modulo no importa o el calendario no cubre el año — jamas [] disfrazado
    de 'sin eventos'; [] solo cuando el año SI esta cubierto y no hay nada cerca."""
    try:
        import macro_calendar as mc
    except Exception as e:
        print(f"AVISO macro_calendar no importable ({e})", file=sys.stderr)
        return None
    evs = mc.macro_events_near(dt.date.today(), window_days=MACRO_AHEAD_D)
    if evs is None:
        return None
    return [e for e in evs if e["days_away"] >= -MACRO_BACK_D]

def plan_engine(sym, spot, cs, on, wb, ws, kor, fut, meta, vx=None, eur=None, earn=None, macro=None,
                earn_age_h=None, earn_cal_ok=True):
    reg = "NEGATIVO" if cs["net_gex"] < 0 else "POSITIVO"
    below_flip = cs["flip"] is not None and spot < cs["flip"]
    lines, score = [], 0
    # apertura: dip de liquidez
    dip_p = 50
    if abs(on.get("ext_atr", 0)) > 0.35: dip_p += 15
    if on.get("fill_rate", 50) > 60: dip_p += 10
    if reg == "NEGATIVO": dip_p += 10
    if abs(on.get("gap_pct", 0)) < 0.15: dip_p = 35
    dip_p = min(dip_p, 90)
    gd = "arriba" if on.get("gap_pct", 0) >= 0 else "abajo"
    lines.append(f"APERTURA: gap {on.get('gap_pct',0):+.2f}% ({gd}), expansion {on.get('ext_atr',0):+.2f} ATRs.")
    lines.append(f"  Historico {sym}: {on.get('fill_rate',50):.0f}% de gaps similares hicieron dip-de-liquidez")
    lines.append(f"  hasta el cierre previo ({on.get('prev_close',0):.2f}) [n={on.get('n_gaps',0)}].")
    lines.append(f"  PROB DIP APERTURA ~{dip_p:.0f}% -> PICARO: no perseguir el gap; esperar el flush")
    lines.append(f"  9:30-9:45 y comprar/vender el RECLAIM del cierre previo con print (2 lecturas).")
    if dip_p >= 65: score += 2
    # regimen
    fl = f"{cs['flip']:.0f}" if cs["flip"] else "n/d"
    lines.append("")
    gx = gex_snapshot_for(sym)
    # 2a foto (la de SIEMPRE en este generador): GEX del vencimiento mas cercano, ventana
    # +/-3.5% del spot. Es propia tambien -> ya no hay "contraste con un tercero".
    viva = ("griegas TWS reales" if "IBKR" in str(cs.get("exp", ""))
            else "gamma Black-Scholes RECONSTRUIDA (IV yfinance)")
    if gx:
        reg = "NEGATIVO" if float(gx["score"]) < 0 else "POSITIVO"
        gok = gx.get("greeks_ok_pct")
        goks = f"{gok*100:.0f}%" if isinstance(gok, (int, float)) else "n/d"
        nc = gx.get("n_contracts")
        ncs = f"{nc}" if isinstance(nc, int) else "n/d"
        lines.append(f"REGIMEN GAMMA (MEDIDO, griegas Polygon): flip {gx['flip']} | net {gx['score']:+.1f}M/pt"
                     f" | bias {gx.get('bias','?')} | POC {gx.get('poc','?')} -> {reg}")
        lines.append(f"  Fuente: cadena archivada {gx.get('chain_date','?')} COMPLETA (todos los vencimientos),")
        lines.append(f"          {ncs} contratos, griegas+OI usables {goks} — en casa, auditable strike a strike.")
        lines.append(f"  2a foto (misma casa, NO un tercero): venc. {cs['exp']} +/-3.5% spot"
                     f" {cs['net_gex']/1e6:+.1f}M/pt flip est {fl},")
        lines.append(f"          {viva}; PARCIAL (1 venc.) -> manda el MEDIDO.")
    else:
        porque = (GEX_SNAP_WHY or "data/gex_snapshot.json ausente/caducado o cadena rancia")[:80]
        lines.append(f"REGIMEN GAMMA NO MEDIDO HOY: {porque}.")
        lines.append(f"  Solo heuristica propia: venc. {cs['exp']} +/-3.5% spot,"
                     f" net GEX {cs['net_gex']/1e6:+.1f}M/pt, flip est {fl}")
        lines.append(f"          -> sesgo ESTIMADO {reg}"
                     + (" (precio DEBAJO del flip)" if below_flip else ""))
        lines.append(f"          origen: {viva} — no es un regimen medido.")
        lines.append("  Lo que sigue asume ese sesgo ESTIMADO: pesarlo menos.")
    if reg == "NEGATIVO":
        lines.append("  Dealers AMPLIFICAN: rebote 1er toque ~50-55%, breaks corren, POC = pelea no muro.")
        lines.append("  Jugadas: breakout con print A FAVOR; strangle si coil; NO vender spreads pegados.")
    else:
        lines.append("  Dealers FIJAN: fade de bordes hacia iman/max-pain; vender muros en spreads.")
    mp, msrc = measured_prob("reclaim_wall", reg, 55 if reg == "POSITIVO" else 50)
    lines.append(f"  PROB reclaim_wall: {mp}% [{msrc}]")
    pt = PATTERNS.get(sym, {}).get("active")
    if pt:
        emp = PATTERNS.get(sym, {}).get("empirical", {}).get(pt.get("pattern"), {})
        emps = f" — cumple {emp['rate']*100:.0f}% histórico (n={emp['n']})" if emp.get("n", 0) >= 8 else " — SIN muestra suficiente, solo contexto"
        lines.append(f"  PATRON detectado: {pt.get('pattern')} {pt.get('direction','')} trigger {pt.get('trigger_level','?')}{emps}")
    # niveles
    lines.append("")
    lines.append(f"NIVELES ({cs['exp']}): max pain {cs['pain']:g} | ATM {cs['atm']:g} IV {cs['iv']*100:.0f}%"
                 f" | implied move +/-{cs['imove']:.1f}% | P/C vol {cs['pcv']:.2f} OI {cs['pco']:.2f}")
    for k, oi, v, b, a, iv in sorted(cs["cw"]): lines.append(f"  techo {k:g}C  OI {int(oi):>7,} vol {int(v):>7,}")
    for k, oi, v, b, a, iv in sorted(cs["pw"], reverse=True): lines.append(f"  piso  {k:g}P  OI {int(oi):>7,} vol {int(v):>7,}")
    # bollinger veto
    lines.append("")
    lines.append(f"BOLLINGER diario: %B {on.get('pb',0.5):.2f} [{on.get('bb_lo',0):.2f}-{on.get('bb_hi',0):.2f}]")
    if on.get("pb", 0.5) < 0.12: lines.append("  ⚠ EN banda inferior: VETO a cortos frescos en apertura (rebote elastico).")
    if on.get("pb", 0.5) > 0.88: lines.append("  ⚠ EN banda superior: VETO a largos frescos en apertura.")
    # spreads sugeridos (picaro: vender el muro)
    try:
        cw0 = sorted(cs["cw"], key=lambda r: -r[1])[0]; pw0 = sorted(cs["pw"], key=lambda r: -r[1])[0]
        lines.append("")
        lines.append("BOLETOS (defined-risk, verificar spread<=5% OI>500 con opt_quick):")
        lines.append(f"  BULL: call spread {cs['atm']:g}/{cw0[0]:g} — vendes el muro rey de calls.")
        lines.append(f"  BEAR: put spread {cs['atm']:g}/{pw0[0]:g} — solo si el piso {pw0[0]:g} ROMPE con print.")
    except Exception:
        pass
    # ballenas + korea + futuros
    if wb or ws:
        lean = "COMPRADOR" if wb > ws else "VENDEDOR"
        lines.append(f"BALLENAS (tape propia, ayer): {lean} — compras ${wb/1e6:.1f}M vs ventas ${ws/1e6:.1f}M")
        score += 1 if (lean == "COMPRADOR") == (on.get("gap_pct", 0) >= 0) else 0
    if meta.get("europe") and eur:
        e_sym = meta["europe"]; e_mv = eur.get(e_sym); e_sx = eur.get("STOXX50")
        bits = []
        if e_mv is not None: bits.append(f"{e_sym} {e_mv:+.1f}% (lider ~6h)")
        if e_sx is not None: bits.append(f"STOXX50 {e_sx:+.1f}%")
        if bits:
            lines.append("EUROPA: " + " | ".join(bits) + " — el listado europeo adelanta la apertura US.")
            if e_mv is not None and abs(e_mv) > 1: score += 1
    if meta.get("korea") and kor:
        ks = " | ".join(f"{k} {v:+.1f}%" for k, v in kor.items())
        lines.append(f"KOREA (memoria, sesion en vivo): {ks} — lider ~13h de MU/DRAM/semis.")
        if any(abs(v) > 1.5 for v in kor.values()): score += 1
    if fut:
        lines.append(f"FUTUROS: NQ {fut.get('NQ',0):+.2f}% | ES {fut.get('ES',0):+.2f}%")
    if sym in ("QQQ", "SPY"):
        b = BREADTH.get(sym)
        if b:
            lines.append(f"ENGRANAJE FLOTA (amplitud de componentes): {b['verdict']}")
            if b.get("breakdowns"):
                lines.append(f"  ⚠ RUPTURAS BAJISTAS en pesos: {', '.join(b['breakdowns'])} -> {sym} hereda presion abajo")
            if b.get("breakouts"):
                lines.append(f"  rupturas alcistas en pesos: {', '.join(b['breakouts'])} -> {sym} apoyo arriba")
            lines.append(f"  regla: el engranaje CONFIRMA, no gatilla — alinear con muros/print, no operar solo por amplitud")
    if vx:
        lines.append(f"VOL (CBOE): VIX {vx['vix']:.1f} | VX1 {vx['vx1']:.1f} ({vx['b1']:+.1f}%) | VX2 {vx['vx2']:.1f}")
        lines.append(f"  -> {vx['reg']}")
    earn_lines = earnings_veto_lines(sym, earn, age_h=earn_age_h, cal_ok=earn_cal_ok)
    if earn_lines:
        lines.append("")
        lines.extend(earn_lines)
    if macro is None:
        lines.append("")
        lines.append(f"🗞 MACRO: SIN calendario CPI/FOMC/NFP para {dt.date.today().year} —"
                     " refrescar data/macro_calendar_2026.json (caducado, no vacio).")
    elif macro:
        lines.append("")
        for ev in macro:
            cuando = ("HOY" if ev["days_away"] == 0 else
                      f"en {ev['days_away']}d" if ev["days_away"] > 0 else
                      f"hace {-ev['days_away']}d")
            veto = "  🚫 NO OPERAR EL PRINT (ventana +/-15min)" if ev["days_away"] == 0 else ""
            lines.append(f"🗞 MACRO {ev['kind']} {ev['date']} {ev['hora']} [{cuando}]{veto}")
    fv = finviz_read(sym)
    if fv:
        bits = []
        if fv.get("earnings_date"): bits.append(f"EARNINGS {fv['earnings_date']} ⚠")
        if fv.get("short_float"): bits.append(f"short float {fv['short_float']} (squeeze fuel si >10%)")
        if fv.get("target_price"): bits.append(f"target analistas {fv['target_price']}")
        if fv.get("relative_strength_index_14"): bits.append(f"RSI {fv['relative_strength_index_14']}")
        if fv.get("relative_volume"): bits.append(f"rvol {fv['relative_volume']}")
        if bits: lines.append("FINVIZ scout: " + " | ".join(bits))
    if cs["iv"] == 0 or cs["straddle"] == 0:
        lines.append("")
        lines.append("⚠ DATOS PREMARKET INCOMPLETOS (OI/IV de yfinance aun no refresca):")
        lines.append("  este mapa es provisional — re-correr tras 8:00 y muros REALES 9:40 via")
        lines.append("  fetch_option_walls.py con TWS. No operar niveles de este PDF sin refresco.")
    lines.append("")
    lines.append("REGLAS: 9:30-9:45 JAMAS | print o nada | hacia el iman jamas a traves del muro |")
    lines.append("3 perdidas = fin | presupuesto opciones SOLO 0DTE (semanales requieren excepcion).")
    score += 2 if abs(on.get("gap_pct", 0)) > 0.4 else 0
    return lines, dip_p, reg, score

QUIPS = [
    "Si persigues el gap, TU eres la liquidez.",
    "El theta no duerme; tu cuenta tampoco deberia comprar 0DTE aburrida.",
    "Los dealers no son tus amigos, pero hoy son predecibles.",
    "El FOMO no paga la renta; el print si.",
    "Stop mental: si, mental — tu cuenta no tiene psicologo.",
    "El mercado abre a las 9:30; los errores tambien.",
    "Paciencia de cocodrilo: un buen bocado > diez mordiscos.",
    "Primer toque rebota. El heroe del segundo toque paga la cena de los dealers.",
]

def x_draft(sym, spot, cs, on, dip_p, reg, kor=None, meta=None, eur=None):
    e = "🧲" if reg == "POSITIVO" else "⚡"
    above=[r for r in cs['cw'] if r[0]>spot] or cs['cw']
    below=[r for r in cs['pw'] if r[0]<spot] or cs['pw']
    techo=sorted(above,key=lambda r:-r[1])[0][0]; piso=sorted(below,key=lambda r:-r[1])[0][0]
    atr=on.get("atr", spot*0.01)
    stop_b=techo-0.35*atr; tgt_b=min([w[0] for w in above if w[0]>techo]+[cs['pain'] if cs['pain']>techo else techo+atr])
    prob=55 if reg=="POSITIVO" else 50
    gap=on.get("gap_pct",0)
    f=lambda x: f"{x:.0f}" if x>=50 else f"{x:.1f}"
    tend="⬆️ALCISTA" if gap>0.25 else ("⬇️BAJISTA" if gap<-0.25 else "➡️plano")
    kline=""
    if meta and meta.get("europe") and eur:
        e_mv=eur.get(meta["europe"])
        if e_mv is not None:
            ses="🟢alza" if e_mv>0.5 else ("🔴baja" if e_mv<-0.5 else "🟡plano")
            if e_mv>0.5 and reg=="POSITIVO": prob=min(prob+5,68)
            elif e_mv<-0.5: prob=max(prob-4,40)
            kline+=f"🇪🇺{meta['europe'].split('.')[0]} {e_mv:+.1f}% (lider 6h) {ses}\n"
            if e_mv>0.8: e="🚀"
    if meta and meta.get("korea") and kor:
        sam=kor.get("Samsung"); skh=kor.get("SK-Hynix"); ksp=kor.get("KOSPI")
        avg=[x for x in (sam,skh,ksp) if x is not None]
        if avg:
            m=sum(avg)/len(avg)
            sesgo="🟢ALZA semis" if m>0.4 else ("🔴BAJA semis" if m<-0.4 else "🟡mixto")
            if m>0.4 and reg=="POSITIVO": prob=min(prob+7,68)
            elif m<-0.4: prob=max(prob-5,40)
            det=" ".join(x for x in [f"Sam{sam:+.0f}%" if sam is not None else "",
                                     f"SKH{skh:+.0f}%" if skh is not None else ""] if x)
            if m>0.4: e="🚀"
            kline+=f"🇰🇷Corea 13h {det} {sesgo}\n"
    q=QUIPS[(int(time.strftime("%j"))+sum(map(ord,sym)))%len(QUIPS)]
    if len(q)>42: q="Print o nada."
    # escalera visual: techo/iman/precio/piso/stop en una linea
    return (f"{e} ${sym} 0DTE prob ~{prob}%\n"
            f"{kline}"
            f"🔴{f(techo)} 🎯{f(tgt_b)} 📍{f(spot)} 🟢{f(piso)}\n"
            f"▶️reclaim {f(techo)} (2 lecturas, no 9:30-9:45)\n"
            f"🛑{f(stop_b)} si falla · Gap {gap:+.1f}% {tend}\n"
            f"{q} No consejo fin.")

def ta_view_line(sym):
    """Veredicto TradingAgents (data/ta_view_<sym>.json de scripts/ta_view.py) si es fresco (<20h)."""
    p = os.path.join(REPO, "data", f"ta_view_{sym.lower()}.json")
    try:
        d = json.load(open(p))
    except Exception:
        return None
    if "veredicto" not in d or time.time() - d.get("ts", 0) > 20 * 3600:
        return None
    return f"TradingAgents: {d['veredicto'].upper()} ({d.get('rating', '?')}) — {d.get('tesis', '')[:170]}"

# ---------- PDF ----------
def make_pdf(outdir, sym, spot, cs, on, plan_lines, series):
    path = os.path.join(outdir, f"{sym}_plan.pdf")
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle(f"{sym} ${spot:.2f} — PLAN {time.strftime('%Y-%m-%d')} (exp {cs['exp']} | max pain {cs['pain']:g} | "
                     f"GEX {cs['net_gex']/1e6:+.0f}M flip~{cs['flip'] if cs['flip'] else 0:g})", fontsize=11, fontweight="bold")
        ax = fig.add_axes([0.06, 0.08, 0.68, 0.82])
        if series is not None and len(series) > 5:
            ax.plot(range(len(series)), series.values, color="black", lw=1.0)
        allw = [(k, oi, "C") for k, oi, *_ in cs["cw"]] + [(k, oi, "P") for k, oi, *_ in cs["pw"]]
        mx = (max(w[1] for w in allw) if allw else 1) or 1
        for k, oi, right in allw:
            col = "#c62828" if right == "C" else "#2e7d32"
            ax.axhline(k, color=col, lw=0.8 + 3 * oi / mx, alpha=0.6)
            ax.annotate(f"{k:g}{right} {oi/1000:.1f}k", (len(series) * 1.004 if series is not None else 1, k),
                        fontsize=7, color=col, va="center", annotation_clip=False)
        ax.axhline(cs["pain"], color="#1565c0", ls="--", lw=1.2)
        if cs["flip"]: ax.axhline(cs["flip"], color="#7b1fa2", ls="--", lw=1.4)
        ax.axhline(on.get("prev_close", spot), color="#f9a825", ls=":", lw=1.4)
        ax.annotate(f"cierre previo {on.get('prev_close',0):.2f} (iman del dip {'-liquidez' if True else ''})",
                    (2, on.get("prev_close", spot)), fontsize=7, color="#f9a825", va="bottom")
        ax.set_title("48h con overnight/premarket (5m) + muros | azul=max pain, purpura=flip GEX, amarillo=cierre previo",
                     fontsize=8.5, loc="left")
        ax.tick_params(labelsize=7); ax.grid(alpha=0.2); ax.set_xticks([])
        g = cs.get("greeks", {})
        side = (f"GRIEGAS ATM {cs['atm']:g} (BS):\n delta {g.get('delta',0):+.2f}\n gamma {g.get('gamma',0):.4f}\n"
                f" theta {g.get('theta',0):+.2f}/dia\n vega {g.get('vega',0):+.2f}\n IV {cs['iv']*100:.0f}%\n"
                f" straddle {cs['straddle']:.2f}\n move +/-{cs['imove']:.1f}%\n\nP/C vol {cs['pcv']:.2f}\nP/C OI  {cs['pco']:.2f}")
        fig.text(0.76, 0.86, side, fontsize=9, family="monospace", va="top")
        pdf.savefig(fig); plt.close(fig)
        # ---- pagina 2: ARBOL DE ESCENARIOS (estilo p9, generado por reglas) ----
        try:
            reg = "NEGATIVO" if cs["net_gex"] < 0 else "POSITIVO"
            pA, pB, pP = 33, 33, 34
            if reg == "NEGATIVO": pB += 6
            if cs["pcv"] > 1.5: pB += 5
            if cs["pcv"] < 0.6: pA += 5
            if on.get("pb", .5) < 0.12: pA += 6
            if on.get("pb", .5) > 0.88: pB += 6
            tot = pA + pB + pP; pA, pB, pP = round(pA*100/tot), round(pB*100/tot), 0
            pP = 100 - pA - pB
            above = sorted([w[0] for w in cs["cw"] if w[0] > spot]) or [spot * 1.01]
            below = sorted([w[0] for w in cs["pw"] if w[0] < spot], reverse=True) or [spot * 0.99]
            up1 = above[0]; up2 = above[1] if len(above) > 1 else up1 * 1.008
            dn1 = below[0]; dn2 = below[1] if len(below) > 1 else dn1 * 0.992
            fig, ax = plt.subplots(figsize=(11, 8.5))
            fig.suptitle(f"{sym} ${spot:.2f} — ARBOL DE ESCENARIOS {time.strftime('%Y-%m-%d')} "
                         f"(regimen {reg} | max pain {cs['pain']:g} | flip~{cs['flip'] if cs['flip'] else 0:g})",
                         fontsize=11, fontweight="bold")
            lo_y = min(dn2, on.get("bb_lo", spot*0.97)) * 0.998; hi_y = max(up2, cs["pain"]) * 1.004
            ax.set_xlim(0, 10); ax.set_ylim(lo_y, hi_y); ax.set_ylabel("precio $"); ax.set_xticks([])
            ax.grid(axis="y", alpha=0.15)
            for k, oi, *_ in cs["cw"]:
                ax.axhline(k, color="#c62828", lw=1.6, alpha=0.6)
                ax.annotate(f"{k:g}C {oi/1000:.1f}k", (10.02, k), fontsize=7.5, color="#c62828", va="center", annotation_clip=False)
            for k, oi, *_ in cs["pw"]:
                ax.axhline(k, color="#2e7d32", lw=1.6, alpha=0.6)
                ax.annotate(f"{k:g}P {oi/1000:.1f}k", (10.02, k), fontsize=7.5, color="#2e7d32", va="center", annotation_clip=False)
            ax.axhline(cs["pain"], color="#1565c0", ls="--", lw=1.2)
            ax.annotate(f"max pain {cs['pain']:g}", (0.2, cs["pain"]), fontsize=7.5, color="#1565c0", va="bottom")
            if cs["flip"]:
                ax.axhline(cs["flip"], color="#7b1fa2", ls="--", lw=1.4)
                ax.annotate(f"flip GEX {cs['flip']:g}", (5.0, cs["flip"]), fontsize=7.5, color="#7b1fa2", va="bottom")
            ax.axhline(on.get("prev_close", spot), color="#f9a825", ls=":", lw=1.3)
            ax.plot(1.0, spot, "o", color="black", ms=9, zorder=5)
            ax.annotate("APERTURA\n(esperar 9:45)", (0.42, spot), fontsize=8, fontweight="bold", ha="center", va="center")
            def arw(x0, y0, x1, y1, c, lw=2.4, ls="-"):
                ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="-|>", color=c, lw=lw, ls=ls, shrinkA=2, shrinkB=2))
            G, R, GY = "#1b7d2e", "#b71c1c", "#616161"
            arw(1.0, spot, 2.5, up1, G); arw(2.5, up1, 3.1, spot + (up1-spot)*0.55, G, 1.7)
            arw(3.1, spot + (up1-spot)*0.55, 4.1, up1*1.001, G); arw(4.1, up1*1.001, 5.6, up2, G, 2.0, "--")
            ax.annotate(f"ALCISTA ~{pA}%: sube al muro {up1:g} -> 1er toque rechaza ->\n"
                        f"retroceso 30-70% que aguanta = entrada -> reclaim -> {up2:g}",
                        (2.2, hi_y - (hi_y-lo_y)*0.06), fontsize=8, color=G)
            arw(1.0, spot, 3.4, spot + (cs['pain']-spot)*0.35, GY, 1.9)
            arw(3.4, spot + (cs['pain']-spot)*0.35, 5.8, spot + (cs['pain']-spot)*0.55, GY, 1.9, "--")
            ax.annotate(f"PIN ~{pP}%: imanta max pain {cs['pain']:g} — chop, theta gana;\nno comprar 0DTE dentro del pin",
                        (6.0, spot + (cs['pain']-spot)*0.55), fontsize=8, color=GY, va="bottom")
            arw(1.0, spot, 2.0, dn1*1.001, R); arw(2.0, dn1*1.001, 2.6, dn1*0.9985, R, 1.7)
            arw(2.6, dn1*0.9985, 3.2, dn1*1.0015, G, 1.5); arw(3.2, dn1*1.0015, 4.2, dn1*0.997, R, 1.7)
            arw(4.2, dn1*0.997, 5.6, dn2, R, 2.2, "--")
            ax.annotate(f"BAJISTA ~{pB}%: print <{dn1:g} (piso) -> rebote 1er toque ->\n"
                        f"RE-TEST decide -> {dn2:g}" + (" (regimen negativo: el break CORRE)" if reg == "NEGATIVO" else ""),
                        (4.0, lo_y + (hi_y-lo_y)*0.10), fontsize=8, color=R)
            ax.annotate(f"Reglas: 1er toque rebota (~{'50-55' if reg=='NEGATIVO' else '70'}%), 3+ toques = muro muerto, ruptura confirmada "
                        f"(retest-rechazo) INVIERTE el nivel.\nDip-liquidez apertura: cierre previo {on.get('prev_close',0):.2f} (amarillo) es el iman del flush 9:30-9:45. "
                        f"Print o nada | 3 perdidas = fin.",
                        (0.2, lo_y + (hi_y-lo_y)*0.015), fontsize=8, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.4", fc="#fffde7", ec="#9e9e9e"))
            tav = ta_view_line(sym)
            if tav:
                fig.text(0.06, 0.012, tav, fontsize=7.5, color="#37474f")
            # ADITIVO: guardar la MISMA figura como PNG tweet-ready para el poster de X.
            # Falla silenciosa: un error de PNG jamas rompe la generacion del PDF.
            try:
                media_dir = os.path.join(outdir, "x_media")
                os.makedirs(media_dir, exist_ok=True)
                fig.savefig(os.path.join(media_dir, f"{sym}_tree.png"),
                            dpi=150, bbox_inches="tight")
            except Exception:
                pass
            pdf.savefig(fig); plt.close(fig)
        except Exception:
            plt.close("all")
        fig = plt.figure(figsize=(8.5, 11))
        fig.text(0.05, 0.97, f"{sym} — PLAN PICARO {time.strftime('%Y-%m-%d')}\n" + "=" * 60 + "\n" + "\n".join(plan_lines),
                 fontsize=9, family="monospace", va="top")
        pdf.savefig(fig); plt.close(fig)
    return path

# ---------- email ----------
def send_email(paths, summary, tag=""):
    key, to = ENV.get("RESEND_KEY"), ENV.get("RESEND_TO")
    if not key or not to: return "sin RESEND_KEY/TO"
    atts = []
    if len(paths) > 10:
        # >10 adjuntos: algunos clientes/Resend recortan la lista (cazado
        # 2026-07-22: "only see 3 pdfs") -> UN zip con todo, infalible.
        import zipfile
        zp = os.path.join(os.path.dirname(paths[0]), f"planes_{time.strftime('%Y-%m-%d')}.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                z.write(p, os.path.basename(p))
        paths = [zp]
    for p in paths:
        with open(p, "rb") as f:
            atts.append({"filename": os.path.basename(p),
                         "content": base64.b64encode(f.read()).decode()})
    r = requests.post("https://api.resend.com/emails", timeout=30,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"from": "onboarding@resend.dev", "to": [to],
              "subject": f"📋 {tag+' ' if tag else ''}Planes flota {time.strftime('%Y-%m-%d')} ({len(paths)} tickers)",
              "text": summary, "attachments": atts})
    return f"{r.status_code} {r.text[:120]}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=",".join(FLEET))
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--tag", default="")
    # IBT_DESKTOP_HOY: misma convencion que print_mon_plans/daily_archive/price_alarm (Yunior: jamas Desktop raiz)
    _hoy = os.environ.get("IBT_DESKTOP_HOY", os.path.expanduser("~/Desktop/ib-trader/hoy"))
    ap.add_argument("--outdir", default=os.path.join(_hoy, f"planes-{time.strftime('%Y-%m-%d')}"))
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    os.makedirs(os.path.join(a.outdir, "x_drafts"), exist_ok=True)
    kor, fut = korea_read(), futures_read()
    vx = vx_term()
    eur = europe_read([m.get("europe") for m in FLEET.values() if m.get("europe")])
    earn_cal, earn_age_h = earnings_calendar_dated()
    earn_cal_ok = earn_cal is not None
    earn_cal = earn_cal or {}
    macro_ev = load_macro_events()          # None = calendario caducado; [] = medido y sin eventos
    made, scored, zerodte = [], [], {}
    for sym in [s.strip().upper() for s in a.tickers.split(",") if s.strip()]:
        meta = FLEET.get(sym, dict(style="weekly", fut="ES=F", korea=False))
        try:
            t = yf.Ticker(sym)
            spot = live_spot(sym) or float(t.fast_info.last_price)
            exp = pick_expiry(t, meta["style"])
            if not exp: raise RuntimeError("sin opciones")
            cs = ibkr_chain_stats(sym, spot) or chain_stats(t, exp, spot)
            on = overnight_stats(t, spot)
            wb, ws = whale_read(sym)
            series = prepost_series(t)
            plan, dip_p, reg, score = plan_engine(sym, spot, cs, on, wb, ws, kor, fut, meta, vx, eur,
                                                    earn_cal.get(sym), macro_ev,
                                                    earn_age_h=earn_age_h, earn_cal_ok=earn_cal_ok)
            pdf = make_pdf(a.outdir, sym, spot, cs, on, plan, series)
            with open(os.path.join(a.outdir, "x_drafts", f"{sym}.txt"), "w") as f:
                f.write(x_draft(sym, spot, cs, on, dip_p, reg, kor, meta, eur))
            if meta.get("style") == "0dte":
                zerodte[sym] = dict(spot=spot, cs=cs, reg=reg, dip=dip_p)
            made.append(pdf); scored.append((score, sym, dip_p, reg))
            print(f"{sym}: OK dip~{dip_p:.0f}% {reg} score {score}")
        except Exception as e:
            print(f"{sym}: FALLO {e}", file=sys.stderr)
    scored.sort(reverse=True)
    picks = []
    try:
        for ln in open("data/options_picks.txt"):
            if ln.startswith("#"): continue
            f = ln.split()
            if len(f) >= 5: picks.append(f"{f[0]} {f[2]} @ {f[3]} (rvol {f[5] if len(f)>5 else '?'})")
            if len(picks) >= 2: break
    except Exception: pass
    # 🎯 CANDIDATOS 0DTE del dia (orden Yunior 2026-07-22: en el email SIEMPRE)
    zd = ""
    for sym, z in zerodte.items():
        try:
            cs, spot = z["cs"], z["spot"]
            gx = gex_snapshot_for(sym)
            cw = cs.get("cw"); pw = cs.get("pw")
            cwl = f"{cw[0][0]:g}({int(cw[0][1]/1000)}k)" if cw else "s/d"
            pwl = f"{pw[0][0]:g}({int(pw[0][1]/1000)}k)" if pw else "s/d"
            # el flip MEDIDO (cadena archivada, griegas Polygon) manda; si no hay, el estimado
            # del vencimiento cercano, y se dice cual es cual — nunca un numero sin origen.
            if gx and gx.get("flip") is not None:
                flip, fsrc = gx["flip"], "MEDIDO"
            elif cs.get("flip"):
                flip, fsrc = cs["flip"], "est"
            else:
                flip, fsrc = None, ""
            lado = ("BAJO flip = dealers amplifican (movimiento)" if flip and spot < flip
                    else "SOBRE flip = dealers amortiguan (pin)" if flip else "")
            zd += (f"  {sym} {spot:.2f}: piso {pwl} techo {cwl} | max pain {cs.get('pain', 0):g}"
                   f" | flip {f'{flip:g} ({fsrc})' if flip else 's/d'} {lado} | dip {z['dip']:.0f}% {z['reg']}\n")
        except Exception as e:
            # nunca `pass`: un simbolo que desaparece del bloque 0DTE en silencio es el
            # mismo olor del denominador fabricado. Se dice cual y por que.
            print(f"AVISO 0DTE {sym}: fuera del bloque ({type(e).__name__}: {e})", file=sys.stderr)
    # engranaje MAG7/componentes -> a donde apunta QQQ (index_breadth vivo)
    try:
        br = json.load(open("data/breadth.json"))
        if time.time() - os.path.getmtime("data/breadth.json") < 3 * 3600:
            for idx in ("QQQ", "SPY"):
                v = br.get(idx, {}).get("verdict")
                if v: zd += f"  ⚙️ {v}\n"
    except Exception:
        pass
    # LEY ENMENDADA 2026-07-22: cualquier contrato de la flota <= $200 premium.
    # Escaneo de asequibles: primer OTM del vencimiento mas cercano con quote
    # viva, ask<=2.00, spread<=5% y OI>500, desde el cache IBKR.
    afford = []
    import glob as _glob
    today8 = time.strftime("%Y%m%d")
    for cp_ in _glob.glob("data/opt_chain_*.txt"):
        try:
            symc = os.path.basename(cp_)[10:-4].upper()
            spot_c = None; best = None
            for ln in open(cp_):
                if ln.startswith("#"):
                    if "spot " in ln:
                        spot_c = float(ln.split("spot ")[1].split(" |")[0].split()[0])
                    continue
                f = ln.split()
                if len(f) < 7 or not spot_c: continue
                k, r, exp, bid, ask, vol, oi = float(f[0]), f[1], f[2], float(f[3]), float(f[4]), float(f[5]), float(f[6])
                if bid <= 0 or ask <= 0 or ask > 2.00 or oi < 500: continue
                if (ask - bid) > max(0.05 * ask, 0.03): continue
                otm = k < spot_c if r == "P" else k > spot_c
                if not otm: continue
                dist = abs(k - spot_c) / spot_c
                cand = (exp != today8, dist, symc, k, r, exp, ask, int(oi))
                if best is None or cand < best: best = cand
            if best:
                afford.append((best[0], best[1], f"{best[2]} {best[3]:g}{best[4]} exp{best[5][-4:]} ask {best[6]:.2f} OI {best[7]:,}"))
        except Exception:
            pass
    if afford:
        afford.sort()
        zd += "  💰 Asequibles <=$200 (primer OTM, spread/OI ok): " + " | ".join(x[2] for x in afford[:8]) + "\n"
    zd = ("🎯 CANDIDATOS OPCIONES HOY (ley 2026-07-22: cualquier contrato <=$200):\n" + zd +
          "  Regla: 9:30-9:45 jamas; 9:45-10:30 oro; print 2-lecturas o nada; earnings del ticker = no aguantar el print.\n\n") if zd else ""
    vxs = zd + (f"VOL: VIX {vx['vix']:.1f} VX1 {vx['vx1']:.1f} ({vx['b1']:+.1f}%) — {vx['reg']}\n\n" if vx else "")
    # MACRO arriba del email SIEMPRE (orden Yunior 2026-07-22: futuros + KOSPI visibles)
    macro = ""
    for etiqueta, d in (("FUTUROS", fut), ("🇰🇷 KOREA", kor), ("🇪🇺 EUROPA", eur)):
        try:
            if d: macro += etiqueta + ": " + "  ".join(f"{k} {float(v):+.2f}%" for k, v in d.items()) + "\n"
        except Exception:
            pass
    if macro_ev is None:
        macro += f"🗞 MACRO: SIN calendario CPI/FOMC/NFP para {dt.date.today().year} — refrescar\n"
    for ev in (macro_ev or []):
        cuando = ("HOY 🚫 no operar el print" if ev["days_away"] == 0 else
                  f"en {ev['days_away']}d" if ev["days_away"] > 0 else f"hace {-ev['days_away']}d")
        macro += f"🗞 MACRO {ev['kind']} {ev['date']} {ev['hora']} [{cuando}]\n"
    if not earn_cal_ok:
        macro += "📅 EARNINGS: calendario Finviz NO verificado hoy — fechas sin confirmar\n"
    elif earn_age_h is not None and earn_age_h > STALE_EARN_H:
        macro += f"📅 EARNINGS: CSV rancio ({earn_age_h:.0f}h) — Finviz mueve fechas, confirmar\n"
    else:
        fl_earn = sorted(s for s in earn_cal if s in FLEET)
        if fl_earn:
            macro += ("📅 EARNINGS flota: "
                      + " | ".join(f"{s} {earn_cal[s][0]} {earn_cal[s][1]}" for s in fl_earn)
                      + "\n")
    vxs = (macro + "\n" if macro else "") + vxs
    summary = vxs + (("PICKS PICAROS FINVIZ: " + " | ".join(picks) + "\n\n") if picks else "") + ("Planes picaros del dia. TOP accionables: "
               + ", ".join(f"{s} (dip {d:.0f}%, {r})" for _, s, d, r in scored[:5])
               + f"\nGenerado {time.strftime('%H:%M ET')}. Señal-solamente; 3 perdidas = fin del dia.")
    if made and not a.no_email:
        print("email:", send_email(made, summary, a.tag))
    with open(os.path.join(a.outdir, "ranking.json"), "w") as f:
        json.dump([{"sym": s, "score": sc, "dip": d, "reg": r} for sc, s, d, r in scored], f)
    print(f"{len(made)} PDFs en {a.outdir}")

if __name__ == "__main__":
    main()
