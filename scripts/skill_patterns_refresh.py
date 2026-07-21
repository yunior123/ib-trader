#!/usr/bin/env python
"""skill_patterns_refresh.py — inyecta patrones de 3-6 meses + muros + backtest WR
en las skills ticker-<sym> de Claude. Re-correr mensualmente o tras regime change.
Uso: ./venv/bin/python scripts/skill_patterns_refresh.py [--tickers QQQ,...]"""
import argparse, glob, json, os, re, time, warnings
warnings.filterwarnings("ignore")
import numpy as np
import yfinance as yf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
SKILLS = os.path.expanduser("~/.claude/skills")
MARK_A, MARK_B = "<!-- AUTO-PATRONES -->", "<!-- /AUTO-PATRONES -->"
DOW = ["lunes", "martes", "miercoles", "jueves", "viernes"]

def backtest_line(sym):
    try:
        for ln in open(f"scripts/{sym.lower()}_keepalive.sh"):
            if "WR" in ln and ("backtest" in ln.lower() or "FULL26" in ln or "T " in ln):
                return ln.strip("# \n")
    except Exception:
        pass
    return None

def stats(sym):
    d = yf.Ticker(sym).history(period="6mo", interval="1d")
    if len(d) < 40: return None
    o, h, l, c = d.Open.values, d.High.values, d.Low.values, d.Close.values
    n = len(c)
    atr = float(np.mean(np.maximum(h[-15:]-l[-15:], np.maximum(abs(h[-15:]-c[-16:-1]), abs(l[-15:]-c[-16:-1])))))
    rng_pct = float(np.mean((h[-60:]-l[-60:])/c[-60:]*100))
    # gaps y fills
    gu = gd = fu = fd = 0
    for i in range(1, n):
        g = (o[i]-c[i-1])/c[i-1]*100
        if g > 0.3:
            gu += 1
            if l[i] <= c[i-1]: fu += 1
        elif g < -0.3:
            gd += 1
            if h[i] >= c[i-1]: fd += 1
    # dia de la semana
    dows = d.index.dayofweek.values[1:]
    rets = (c[1:]-c[:-1])/c[:-1]*100
    dowm = {DOW[k]: float(np.mean(rets[dows == k])) for k in range(5) if (dows == k).sum() > 3}
    best = max(dowm, key=dowm.get); worst = min(dowm, key=dowm.get)
    # intradia vs overnight
    intra = float(np.mean((c[-60:]-o[-60:])/o[-60:]*100))
    overn = float(np.mean((o[1:][-60:]-c[:-1][-60:])/c[:-1][-60:]*100))
    green_open = float(np.mean(c[-60:] > o[-60:]) * 100)
    # bollinger toques
    ma = np.convolve(c, np.ones(20)/20, "valid"); sd = np.array([np.std(c[i-19:i+1], ddof=1) for i in range(19, n)])
    cc = c[19:]
    lo_t = float(np.mean(cc < ma - 1.9*sd) * 100); hi_t = float(np.mean(cc > ma + 1.9*sd) * 100)
    return dict(atr=atr, rng=rng_pct, gu=gu, fu=fu, gd=gd, fd=fd, dowm=dowm, best=best,
                worst=worst, intra=intra, overn=overn, green=green_open, lo_t=lo_t, hi_t=hi_t,
                px=float(c[-1]))

def intraday_shape(sym):
    """Forma intradia tipica (60d de 15m): pop apertura, timing de HOD/LOD, whip final."""
    try:
        h = yf.Ticker(sym).history(period="60d", interval="15m")
        if len(h) < 200: return None, None
        days = {}
        for ts, row in h.iterrows():
            if ts.hour * 100 + ts.minute < 930 or ts.hour * 100 + ts.minute >= 1600: continue
            days.setdefault(ts.date(), []).append((ts.hour * 60 + ts.minute, row.Open, row.High, row.Low, row.Close))
        pop = fade_after_pop = whip = 0; lod_b = {"apertura": 0, "mediodia": 0, "tarde": 0, "cierre": 0}
        hod_b = {"apertura": 0, "mediodia": 0, "tarde": 0, "cierre": 0}
        arch = {"POP-DESANGRE-LATIGAZO": 0, "FADE-RECUPERA": 0, "TREND-UP": 0, "TREND-DOWN": 0, "CHOP": 0}
        n = 0
        for d, bars in days.items():
            if len(bars) < 20: continue
            n += 1
            bars.sort()
            o = bars[0][1]; c = bars[-1][4]
            first30 = (bars[1][4] - o) / o * 100 if len(bars) > 1 else 0
            last30 = (bars[-1][4] - bars[-3][4]) / bars[-3][4] * 100 if len(bars) > 2 else 0
            lows = [(b[3], b[0]) for b in bars]; highs = [(b[2], b[0]) for b in bars]
            lo_t = min(lows)[1]; hi_t = max(highs)[1]
            def bucket(m):
                if m < 630: return "apertura"
                if m < 780: return "mediodia"
                if m < 900: return "tarde"
                return "cierre"
            lod_b[bucket(lo_t)] += 1; hod_b[bucket(hi_t)] += 1
            day_ret = (c - o) / o * 100
            if first30 > 0.05: pop += 1
            if last30 > 0.05: whip += 1
            if first30 > 0.05 and min(lows)[1] > 660 and last30 > 0.03 and day_ret < first30:
                arch["POP-DESANGRE-LATIGAZO"] += 1; fade_after_pop += 1
            elif first30 < -0.05 and day_ret > 0: arch["FADE-RECUPERA"] += 1
            elif day_ret > 0.5: arch["TREND-UP"] += 1
            elif day_ret < -0.5: arch["TREND-DOWN"] += 1
            else: arch["CHOP"] += 1
        if not n: return None, None
        dom = max(arch, key=arch.get)
        lod_dom = max(lod_b, key=lod_b.get); hod_dom = max(hod_b, key=hod_b.get)
        line = (f"pop apertura {pop/n*100:.0f}% dias | HOD suele ser {hod_dom} / LOD {lod_dom} | "
                f"whip final verde {whip/n*100:.0f}% | arquetipo dominante: {dom} ({arch[dom]/n*100:.0f}% de {n}d)")
        detail = " ".join(f"{k}:{v/n*100:.0f}%" for k, v in arch.items())
        return line, detail
    except Exception:
        return None, None

def walls_today(sym):
    # del ultimo plan generado hoy si existe (ranking no tiene niveles; usar PDF no; recalcular ligero)
    try:
        t = yf.Ticker(sym); spot = float(t.fast_info.last_price)
        opts = t.options
        exp = next((e for e in opts if e >= time.strftime("%Y-%m-%d")), None)
        if not exp: return ""
        ch = t.option_chain(exp)
        c = ch.calls.fillna(0); p = ch.puts.fillna(0)
        c = c[(c.strike >= spot*.96) & (c.strike <= spot*1.04)]
        p = p[(p.strike >= spot*.96) & (p.strike <= spot*1.04)]
        cw = c.nlargest(2, "openInterest").strike.tolist()
        pw = p.nlargest(2, "openInterest").strike.tolist()
        return f"techos {'/'.join(f'{k:g}' for k in cw)} | pisos {'/'.join(f'{k:g}' for k in pw)} (exp {exp}, snapshot al refresh)"
    except Exception:
        return ""

def gexa_line(sym):
    try:
        g = json.load(open("data/gexa_snapshot.json")).get(sym)
        if g: return f"flip {g.get('flip','?')} | dealer {g.get('score','?')} | bias {g.get('bias','?')}"
    except Exception:
        pass
    return None

def section(sym, st, bt, wl, gx):
    dw = " ".join(f"{k} {v:+.2f}%" for k, v in st["dowm"].items())
    L = [MARK_A, f"## Patrones auto (6 meses, refresh {time.strftime('%Y-%m-%d')})",
         f"- Precio {st['px']:.2f} | ATR14 {st['atr']:.2f} | rango medio dia {st['rng']:.2f}%",
         f"- GAPS: {st['gu']} up>0.3% ({st['fu']}/{st['gu']} = {st['fu']/max(st['gu'],1)*100:.0f}% hicieron dip-fill al cierre previo) | "
         f"{st['gd']} down ({st['fd']}/{st['gd']} = {st['fd']/max(st['gd'],1)*100:.0f}% rebote-fill) -> base del play dip-liquidez",
         f"- Dia de semana: mejor {st['best']} / peor {st['worst']} ({dw})",
         f"- Drift: intradia {st['intra']:+.2f}%/dia vs overnight {st['overn']:+.2f}%/dia | cierra verde-sobre-open {st['green']:.0f}% de los dias",
         f"- Bollinger diario: toca banda inferior {st['lo_t']:.0f}% de dias / superior {st['hi_t']:.0f}% (elastico si es raro, band-walker si frecuente)"]
    shp, shp_d = intraday_shape(sym)
    if shp:
        L.append(f"- FORMA INTRADIA (60d/15m): {shp}")
        L.append(f"  reparto: {shp_d} — jugar el arquetipo: si es POP-DESANGRE-LATIGAZO, el pop de")
        L.append(f"  apertura se VENDE (no se compra), el dip de media tarde es la entrada, el latigazo final paga")
    if bt: L.append(f"- Backtest bot ({sym.lower()}_keepalive): {bt[:150]}")
    if wl: L.append(f"- Muros snapshot: {wl}")
    if gx: L.append(f"- Gexa snapshot: {gx}")
    L.append(f"- Refresh: `./venv/bin/python scripts/skill_patterns_refresh.py --tickers {sym}`")
    L.append(MARK_B)
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tickers", default="")
    a = ap.parse_args()
    dirs = sorted(glob.glob(os.path.join(SKILLS, "ticker-*")))
    want = [s.strip().upper() for s in a.tickers.split(",") if s.strip()]
    done = 0
    for d in dirs:
        sym = os.path.basename(d).replace("ticker-", "").upper()
        if want and sym not in want: continue
        f = os.path.join(d, "SKILL.md")
        if not os.path.exists(f): continue
        try:
            st = stats(sym)
            if not st: print(sym, "sin datos"); continue
            sec = section(sym, st, backtest_line(sym), walls_today(sym), gexa_line(sym))
            body = open(f).read()
            if MARK_A in body:
                body = re.sub(re.escape(MARK_A) + ".*?" + re.escape(MARK_B), sec, body, flags=re.S)
            else:
                body = body.rstrip() + "\n\n" + sec + "\n"
            open(f, "w").write(body); done += 1; print(sym, "ok")
            if shp := section.__defaults__ if False else None: pass
        except Exception as e:
            print(sym, "FALLO", e)
    print(f"{done} skills actualizadas")

main()
