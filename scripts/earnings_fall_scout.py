#!/usr/bin/env python3
"""earnings_fall_scout.py — caza CAIDAS POST-EARNINGS liquidas para opciones
(Yunior 2026-07-28: "finviz bots that detects falls after earnings, based on
news or technicals, with help of trading agents, liquid for options").

SEÑAL-SOLAMENTE. Scan Finviz Elite (earnings ayer AMC / hoy BMO, optionable,
avg vol>=1M, precio>=$15, mcap>=$2B, caida<=-5%) -> score medible (caida en
ATRs = capitulacion vs rasguño, rvol, cascada vs dead-cat, titular bear) ->
TOP3 gate de opciones IBKR 1-shot (spread/mid<=5% + OI>500, regla #4) ->
TOP2 veredicto TradingAgents (ta_view.py, degradacion limpia "TA pendiente").
Salida: data/earnings_falls.json + feed + voz (score>=70 y OPCIONES OK).
Pasadas 8:20 / 9:50 / 12:30 ET, muere 13:00. EF_TEST=1 = 1 pasada sin voz.
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SCRIPTS)
os.chdir(REPO)
sys.path.insert(0, SCRIPTS)

TEST = os.environ.get("EF_TEST") == "1"
DROP_MIN = -5.0
SCORE_FEED = 45
SCORE_VOICE = 70
TOP_NEWS, TOP_OPT, TOP_TA = 6, 3, 2
PASSES = [("0820", 820), ("0950", 950), ("1230", 1230)]
DIE_HM = 1300
COLS = "1,2,3,4,6,49,59,60,61,63,64,65,66,67,68"
BASE_F = ["sh_opt_option", "sh_avgvol_o1000", "sh_price_o15", "cap_midover"]
WINDOWS = [("AMC-ayer", "earningsdate_yesterdayafter"),
           ("BMO-hoy", "earningsdate_todaybefore")]
BEAR_WORDS = ("miss", "misses", "cut", "cuts", "weak", "guidance", "disappoint",
              "falls", "slide", "slides", "plunge", "sinks", "downgrade", "warns",
              "lowers", "below", "short of")
SEMI_RE = re.compile(r"semiconductor", re.I)


def token():
    for k in ("FINVIZ_AUTH3", "FINVIZ_AUTH"):
        if os.environ.get(k, "").strip():
            return os.environ[k].strip()
    for name in ("config/feeds.env", "config/llm.env"):
        try:
            for ln in open(os.path.join(REPO, name)):
                for k in ("FINVIZ_AUTH3=", "FINVIZ_AUTH="):
                    if ln.startswith(k):
                        return ln.split("=", 1)[1].strip()
        except OSError:
            continue
    return None


def num(v):
    try:
        f = float(str(v).replace("%", "").replace(",", "").strip())
        return f
    except (TypeError, ValueError):
        return None


def say(title, msg, voice, prio="SIGNAL", sound="ProAlert", voice_msg=None):
    """voice_msg: version corta (Yunior 2026-07-28 "voces muy largas, resume")."""
    if TEST:
        print(f"[EF_TEST {'VOZ' if voice else 'banner'}] {title} | {msg}")
        return
    corto = voice_msg or msg
    if voice:
        subprocess.Popen(["/bin/bash", os.path.join(SCRIPTS, "speak.sh"), prio, corto],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import notify_short; notify_short.push(title, corto)
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      f'display notification "{corto}" with title "{title}" sound name "{sound}"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt = time.localtime()
    d = os.path.join(REPO, "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")


def _fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def screen(auth):
    """Filas crudas Finviz de las 2 ventanas de earnings, o None si el export fallo."""
    rows, fails = [], []
    for tag, efilt in WINDOWS:
        url = (f"https://elite.finviz.com/export/screener?v=152"
               f"&f={efilt},{','.join(BASE_F)}&o=change&auth={auth}&c={COLS}")
        try:
            body = _fetch(url)
        except Exception as e:
            fails.append(f"{tag}: {repr(e)[:80]}")
            continue
        lines = [l for l in body.splitlines() if l.strip()]
        if not lines or "Ticker" not in lines[0] or "Change" not in lines[0]:
            fails.append(f"{tag}: respuesta invalida ({len(lines)} lineas, header sin Ticker/Change)")
            continue
        for r in csv.DictReader(io.StringIO("\n".join(lines))):
            r["_window"] = tag
            rows.append(r)
    if fails:
        print(f"earnings_fall_scout: export Finviz fallo -> {' | '.join(fails)}", file=sys.stderr)
    if not rows and fails:
        return None
    return rows


def build_cand(r, rth):
    chg, gap = num(r.get("Change")), num(r.get("Gap"))
    drop = chg if chg is not None else gap
    if drop is None or drop > DROP_MIN:
        return None
    c = {"sym": (r.get("Ticker") or "").strip().upper(),
         "company": (r.get("Company") or "").strip(),
         "sector": (r.get("Sector") or "").strip(),
         "industry": (r.get("Industry") or "").strip(),
         "window": r["_window"],
         "earnings": (r.get("Earnings Date") or "").strip(),
         "chg_pct": chg, "gap_pct": gap, "from_open_pct": num(r.get("Change from Open")),
         "price": num(r.get("Price")), "atr": num(r.get("Average True Range")),
         "rvol": num(r.get("Relative Volume")), "avg_vol_k": num(r.get("Average Volume")),
         "volume": num(r.get("Volume")), "mcap_m": num(r.get("Market Cap")),
         "rsi": num(r.get("Relative Strength Index (14)")), "drop_pct": drop,
         "headline": None, "news_bear": None, "rth": rth}
    if not c["sym"]:
        return None
    if SEMI_RE.search(c["industry"]):
        c["capitan"] = "SMH"
    elif c["sector"] == "Technology":
        c["capitan"] = "QQQ/XLK"
    else:
        c["capitan"] = None
    if c["price"] is not None and c["atr"] and c["atr"] > 0:
        c["drop_atr"] = round(abs(c["drop_pct"]) / 100 * c["price"] / c["atr"], 2)
    else:
        c["drop_atr"] = None
    return c


def score_cand(c):
    """Score 0-100 normalizado sobre componentes DISPONIBLES; lo ausente se lista, no se inventa."""
    parts, missing = {}, []
    parts["caida"] = (30, min(abs(c["drop_pct"]) / 12.0, 1.0))
    if c["drop_atr"] is not None:
        parts["capitulacion_atr"] = (25, min(c["drop_atr"] / 4.0, 1.0))
    else:
        missing.append("capitulacion_atr")
    if c["rvol"] is not None:
        parts["rvol"] = (20, min(c["rvol"] / 3.0, 1.0))
    else:
        missing.append("rvol")
    # cascada solo en RTH: en premarket Gap/from-open aun describen la sesion de ayer
    if c["rth"] and c["from_open_pct"] is not None:
        fo = c["from_open_pct"]
        parts["cascada"] = (15, 1.0 if fo <= -1.0 else (0.5 if fo < 1.0 else 0.0))
        c["forma"] = "CASCADA (perdio el open)" if fo <= -1.0 else \
            ("plana post-open" if fo < 1.0 else "DEAD-CAT (rebote sobre el open)")
    else:
        missing.append("cascada")
        c["forma"] = "premarket (forma pendiente de la apertura)"
    if c["news_bear"] is not None:
        parts["news"] = (10, 1.0 if c["news_bear"] else 0.3)
    else:
        missing.append("news")
    wsum = sum(w for w, _ in parts.values())
    c["score"] = round(100 * sum(w * v for w, v in parts.values()) / wsum) if wsum else None
    c["score_parts"] = {k: round(v, 2) for k, (_, v) in parts.items()}
    c["score_missing"] = missing
    return c


def add_news(c, auth):
    try:
        body = _fetch(f"https://elite.finviz.com/news_export.ashx?v=3&t={c['sym']}&auth={auth}", 15)
        now = time.time()
        for r in csv.DictReader(io.StringIO(body)):
            try:
                ts = time.mktime(time.strptime(r.get("Date", ""), "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
            if now - ts > 36 * 3600:
                break
            t = (r.get("Title") or "").strip()
            if t:
                c["headline"] = t[:160]
                c["news_bear"] = any(w in t.lower() for w in BEAR_WORDS)
                return
    except Exception as e:
        print(f"earnings_fall_scout: news {c['sym']} fallo ({repr(e)[:60]})", file=sys.stderr)


def opt_check(syms):
    """{sym: (estado, texto)} — 1-shot IBKR readonly clientId 47; sin gateway -> s/d."""
    out = {s: ("s/d", "OPCIONES s/d (IBKR no disponible) — default ACCIONES") for s in syms}
    if not syms:
        return out
    try:
        try:
            from ib_insync import IB, Option, Stock
        except ImportError:
            from ib_async import IB, Option, Stock
        from ib_mode import get_port
        ib = IB()
        ib.connect("127.0.0.1", get_port(), clientId=47, timeout=12, readonly=True)
        ib.RequestTimeout = 15   # causa raiz 2026-07-28 (opt_whale_watch.py): sin esto, qualifyContracts cuelga para siempre si TWS no responde
        ib.reqMarketDataType(1)
    except Exception as e:
        print(f"earnings_fall_scout: IBKR no disponible ({str(e)[:70]})", file=sys.stderr)
        return out
    today = time.strftime("%Y%m%d")
    for sym in syms:
        try:
            stk = Stock(sym, "SMART", "USD")
            ib.qualifyContracts(stk)
            tk = ib.reqTickers(stk)[0]
            spot = next((float(v) for v in (tk.marketPrice(), tk.last, tk.close)
                         if v == v and v and v > 0), None)
            if not spot:
                out[sym] = ("s/d", "OPCIONES s/d (sin spot IBKR) — default ACCIONES")
                continue
            params = ib.reqSecDefOptParams(sym, "", "STK", stk.conId)
            ch = next((p for p in params if p.exchange == "SMART" and p.tradingClass == sym),
                      next((p for p in params if p.exchange == "SMART"), None))
            exps = sorted(e for e in ch.expirations if e >= today) if ch else []
            if not exps:
                out[sym] = ("s/d", "OPCIONES s/d (sin cadena SMART) — default ACCIONES")
                continue
            strike = min(ch.strikes, key=lambda k: abs(k - spot))
            cons = [c for c in ib.qualifyContracts(
                *[Option(sym, exps[0], strike, r, "SMART", currency="USD",
                         tradingClass=ch.tradingClass) for r in ("P", "C")]) if c and c.conId]
            tks = [ib.reqMktData(c, "100,101", False, False) for c in cons]
            ib.sleep(5)
            verdict = None
            for t in tks:                       # tesis bear: manda el PUT ATM
                bid, ask = num(t.bid), num(t.ask)
                oi = num(t.putOpenInterest if t.contract.right == "P" else t.callOpenInterest)
                ib.cancelMktData(t.contract)
                if not bid or not ask or bid <= 0 or ask <= 0:
                    continue
                mid = (bid + ask) / 2
                sp = (ask - bid) / mid * 100
                lab = f"{t.contract.right} {strike:g} {exps[0]}"
                if sp <= 5.0 + 1e-9 and oi is not None and oi > 500:
                    verdict = ("OK", f"OPCIONES OK ({lab}: spread {sp:.1f}%, OI {oi/1000:.1f}k)")
                    break
                oitxt = f"{oi:.0f}" if oi is not None else "s/d"
                verdict = ("VETADAS", f"OPCIONES VETADAS ({lab}: spread {sp:.1f}%, "
                           f"OI {oitxt}) — usar ACCIONES o ETF")
            if verdict is None:
                verdict = ("s/d", "OPCIONES s/d (ATM sin cotizar) — default ACCIONES")
            out[sym] = verdict
        except Exception as e:
            out[sym] = ("s/d", f"OPCIONES s/d ({str(e)[:50]}) — default ACCIONES")
    ib.disconnect()
    return out


def ta_verdict(sym):
    p = os.path.join("data", f"ta_view_{sym.lower()}.json")
    try:
        d = json.load(open(p))
        if d.get("sym") == sym and d.get("veredicto") and time.time() - d.get("ts", 0) < 6 * 3600:
            return d["veredicto"]
    except Exception:
        pass
    if os.environ.get("EF_TA", "1") == "0":
        return "pendiente"
    try:
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "ta_view.py"), sym],
                           capture_output=True, text=True, timeout=340, cwd=REPO)
        if r.returncode == 0:
            d = json.load(open(p))
            return d.get("veredicto") or "pendiente"
        print(f"earnings_fall_scout: TA {sym} rc={r.returncode} — pendiente", file=sys.stderr)
    except Exception as e:
        print(f"earnings_fall_scout: TA {sym} fallo ({repr(e)[:60]}) — pendiente", file=sys.stderr)
    return "pendiente"


def atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def alerted_path():
    return time.strftime("data/earnings_fall_alerted_%Y-%m-%d.txt")


def run_pass(label, auth):
    lt = time.localtime()
    rth = lt.tm_hour * 100 + lt.tm_min >= 935
    rows = screen(auth)
    if rows is None:
        say("🩸 EARNINGS-FALL ROTO", "Scout de earnings sin datos: export Finviz caido. Revisar token.", voice=False, sound="Sosumi")
        return
    cands = [c for c in (build_cand(r, rth) for r in rows) if c]
    seen = {}
    for c in cands:                             # dedupe AMC/BMO: gana la caida mayor
        if c["sym"] not in seen or c["drop_pct"] < seen[c["sym"]]["drop_pct"]:
            seen[c["sym"]] = c
    cands = sorted((score_cand(c) for c in seen.values()), key=lambda c: -(c["score"] or 0))
    for c in cands[:TOP_NEWS]:
        add_news(c, auth)
        score_cand(c)
    cands.sort(key=lambda c: -(c["score"] or 0))
    opts = opt_check([c["sym"] for c in cands[:TOP_OPT]])
    for c in cands:
        st, txt = opts.get(c["sym"], (None, None))
        c["opciones"], c["opciones_txt"] = st, txt
    for c in cands[:TOP_TA]:
        c["ta"] = ta_verdict(c["sym"]) if (c["score"] or 0) >= SCORE_FEED else "pendiente"
    for c in cands:
        c.setdefault("ta", "pendiente")
    atomic_json("data/earnings_falls.json",
                {"ts": int(time.time()), "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "pasada": label, "n_screen": len(rows), "candidatos": cands})
    print(f"[{label}] {len(rows)} en screen, {len(cands)} caidas <= {DROP_MIN}%:")
    for c in cands:
        print(f"  {c['sym']:6s} {c['drop_pct']:+6.1f}% score {str(c['score']):>4s} "
              f"atr_x {c['drop_atr']} rvol {c['rvol']} {c['window']} {c['forma']} | "
              f"{c.get('opciones') or '-'} | TA {c['ta']} | {c['headline'] or ''}"[:200])
    try:
        alerted = set(open(alerted_path()).read().split())
    except OSError:
        alerted = set()
    for c in cands:
        if c["sym"] in alerted or (c["score"] or 0) < SCORE_FEED:
            continue
        cap = f", capitan {c['capitan']}" if c["capitan"] else ""
        line = (f"🩸 EARNINGS-FALL {c['sym']} {c['drop_pct']:+.1f}% (score {c['score']}, "
                f"{c.get('opciones_txt') or 'OPCIONES s/d'}, TA: {c['ta']}{cap})")
        voice = c["score"] >= SCORE_VOICE and c.get("opciones") == "OK"
        msg = (f"Caida post earnings en {c['sym']}: {abs(c['drop_pct']):.1f} por ciento, "
               f"{c['drop_atr'] or '?'} ATRs. Score {c['score']}. {c.get('opciones_txt') or 'opciones sin dato'}. "
               f"TradingAgents {c['ta']}.")
        say(line.split(" (")[0], msg if voice else line, voice=voice,
            voice_msg=f"{c['sym']} cayó fuerte tras resultados. {c['ta']}.")
        if not TEST:
            with open(alerted_path(), "a") as f:
                f.write(c["sym"] + "\n")
        alerted.add(c["sym"])


def passes_path():
    return time.strftime("data/earnings_fall_passes_%Y-%m-%d.txt")


def main():
    auth = token()
    if not auth:
        print("earnings_fall_scout ROTO: sin FINVIZ_AUTH3/FINVIZ_AUTH", file=sys.stderr)
        return 1
    if TEST:
        run_pass("TEST", auth)
        return 0
    if time.localtime().tm_wday >= 5:
        print("earnings_fall_scout: fin de semana — fuera")
        return 0
    print(f"earnings_fall_scout arriba: pasadas {[p for p, _ in PASSES]}, muere {DIE_HM}")
    while True:
        lt = time.localtime()
        hm = lt.tm_hour * 100 + lt.tm_min
        if hm >= DIE_HM:
            break
        try:
            done = set(open(passes_path()).read().split())
        except OSError:
            done = set()
        pend = [(l, t) for l, t in PASSES if l not in done and hm >= t]
        if pend:
            label = pend[-1][0]
            run_pass(label, auth)
            with open(passes_path(), "a") as f:
                f.write(" ".join(l for l, _ in pend) + "\n")   # las saltadas no se re-corren tarde
        elif all(l in done for l, _ in PASSES):
            break
        time.sleep(30)
    print("earnings_fall_scout: pasadas completas / 13:00 — fuera hasta mañana")
    return 0


if __name__ == "__main__":
    sys.exit(main())
