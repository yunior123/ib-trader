#!/usr/bin/env python3
"""
momentum_decay.py — Estudio EMPIRICO del decaimiento de momentum intradia.

Orden: "analiza el historico para saber despues de cuanto tiempo promedio se
pierde momentum en mercados bullish y tambien en bearish". NADA asumido: todo
medido sobre barras reales de yfinance.

Definicion de IMPULSO:
  - Arranca en un cruce de %B(20,2): sobre 0.8 (bull) o bajo 0.2 (bear),
  - con volumen del cruce > mediana de volumen de 20 barras,
  - y EMA(3) de retornos con el signo del impulso en el cruce.
Muerte del impulso (primero que ocurra, dentro del mismo dia):
  - primer cierre que retrocede >38.2% del tramo (anchor -> extremo), o
  - %B vuelve a <0.5 (bull) / >0.5 (bear).
Metricas por impulso:
  - duracion en minutos (cruce -> muerte),
  - extension % del tramo (anchor -> extremo en la muerte),
  - retroceso >50% del tramo en los 30 min posteriores a la muerte.

Datos: 1m period=5d + 5m period=1mo (pooled; duracion normalizada a minutos).
Sesiones: manana 9:30-11:30, tarde 13:00-16:00 (medio dia excluido).
Salida: tabla texto plano + data/momentum_decay.json (idempotente, corrible
semanalmente; degradacion limpia si un ticker falla).

Uso: ./venv/bin/python scripts/momentum_decay.py
"""

import json
import os
import random
import sys
import time
import warnings
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

TICKERS = ["QQQ", "SPY", "NVDA", "MU", "SMH", "INTC"]
FETCH_SPECS = [("1m", "5d"), ("5m", "1mo")]
RETRACE_DEATH = 0.382
RETRACE_POST = 0.50
POST_WINDOW_MIN = 30
BB_LEN, BB_STD = 20, 2.0
VOL_MED_LEN = 20
SESSIONS = {
    "manana": (dtime(9, 30), dtime(11, 30)),
    "tarde": (dtime(13, 0), dtime(16, 0)),
}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(REPO, "data", "momentum_decay.json")


def fetch(symbol, interval, period, max_retries=4):
    """yfinance con reintentos + backoff (Yahoo rate-limitea rafagas)."""
    import yfinance as yf
    delay = 5
    for attempt in range(1, max_retries + 1):
        try:
            df = yf.Ticker(symbol).history(
                period=period, interval=interval, prepost=False,
                auto_adjust=False, actions=False)
            if df is None or df.empty:
                raise RuntimeError("empty frame")
            return df
        except Exception as e:
            msg = str(e)
            print(f"  [{symbol} {interval}] intento {attempt} fallo: {msg[:90]}",
                  file=sys.stderr)
            if attempt == max_retries:
                return None
            time.sleep(delay + random.uniform(0, 2))
            delay *= 2
    return None


def compute_indicators(df):
    c = df["Close"]
    mid = c.rolling(BB_LEN).mean()
    sd = c.rolling(BB_LEN).std(ddof=0)
    upper, lower = mid + BB_STD * sd, mid - BB_STD * sd
    width = (upper - lower).replace(0, np.nan)
    df = df.copy()
    df["pctb"] = (c - lower) / width
    df["ret"] = c.pct_change()
    df["ema3"] = df["ret"].ewm(span=3, adjust=False).mean()
    df["volmed"] = df["Volume"].rolling(VOL_MED_LEN).median()
    return df


def session_of(ts):
    t = ts.time()
    for name, (a, b) in SESSIONS.items():
        if a <= t < b:
            return name
    return None


def detect_impulses(df, interval_min):
    """Devuelve lista de dicts con metricas por impulso. Intradia solamente."""
    out = []
    for _, day in df.groupby(df.index.date):
        n = len(day)
        if n < BB_LEN + 5:
            continue
        pctb = day["pctb"].values
        close = day["Close"].values
        ema3 = day["ema3"].values
        vol = day["Volume"].values
        volmed = day["volmed"].values
        idx = day.index
        i = BB_LEN
        while i < n - 1:
            side = None
            if pctb[i] > 0.8 and pctb[i - 1] <= 0.8 and ema3[i] > 0:
                side = "bull"
            elif pctb[i] < 0.2 and pctb[i - 1] >= 0.2 and ema3[i] < 0:
                side = "bear"
            if side is None or np.isnan(volmed[i]) or vol[i] <= volmed[i]:
                i += 1
                continue
            sess = session_of(idx[i])
            sgn = 1.0 if side == "bull" else -1.0
            anchor = close[i - 1]
            extreme = close[i]
            death = None
            for j in range(i + 1, n):
                extreme = max(extreme, close[j - 1]) if sgn > 0 else min(extreme, close[j - 1])
                leg = sgn * (extreme - anchor)
                retr = sgn * (extreme - close[j]) / leg if leg > 0 else 0.0
                pb_dead = pctb[j] < 0.5 if sgn > 0 else pctb[j] > 0.5
                if (leg > 0 and retr > RETRACE_DEATH) or pb_dead:
                    death = j
                    break
            if death is None:
                death = n - 1  # muere con el cierre del dia
            extreme = (max(extreme, close[death]) if sgn > 0
                       else min(extreme, close[death])) if death > i else extreme
            leg = sgn * (extreme - anchor)
            dur_min = (idx[death] - idx[i]).total_seconds() / 60.0
            ext_pct = 100.0 * leg / anchor if anchor else 0.0
            # retroceso >50% del tramo en los 30 min tras la muerte
            retr50 = False
            if leg > 0:
                thresh = extreme - sgn * RETRACE_POST * leg
                t_end = idx[death] + pd.Timedelta(minutes=POST_WINDOW_MIN)
                for k in range(death + 1, n):
                    if idx[k] > t_end:
                        break
                    if sgn * (close[k] - thresh) < 0:
                        retr50 = True
                        break
            if sess is not None and dur_min >= interval_min and leg > 0:
                out.append({"side": side, "session": sess, "dur_min": dur_min,
                            "ext_pct": ext_pct, "retr50": retr50})
            i = max(death, i + 1)
    return out


def summarize(impulses):
    if not impulses:
        return {"n": 0, "mediana_min": None, "p75_min": None,
                "ext_mediana_pct": None, "prob_retroceso_50": None}
    d = np.array([x["dur_min"] for x in impulses])
    e = np.array([abs(x["ext_pct"]) for x in impulses])
    r = np.array([x["retr50"] for x in impulses])
    return {"n": int(len(d)),
            "mediana_min": round(float(np.median(d)), 1),
            "p75_min": round(float(np.percentile(d, 75)), 1),
            "ext_mediana_pct": round(float(np.median(e)), 3),
            "prob_retroceso_50": round(float(r.mean()), 3)}


def main():
    all_imp = {}   # ticker -> list of impulses
    failed = []
    for si, sym in enumerate(TICKERS):
        imps = []
        for interval, period in FETCH_SPECS:
            df = fetch(sym, interval, period)
            time.sleep(random.uniform(3, 5))  # espaciar llamadas
            if df is None:
                print(f"  [WARN] {sym} {interval}: sin datos, sigo", file=sys.stderr)
                continue
            df = compute_indicators(df)
            imps.extend(detect_impulses(df, 1 if interval == "1m" else 5))
        if imps:
            all_imp[sym] = imps
        else:
            failed.append(sym)

    results = {}
    for sym, imps in all_imp.items():
        results[sym] = {}
        for side in ("bull", "bear"):
            results[sym][side] = {}
            for sess in ("manana", "tarde"):
                sub = [x for x in imps if x["side"] == side and x["session"] == sess]
                results[sym][side][sess] = summarize(sub)
    # agregado
    pooled = [x for imps in all_imp.values() for x in imps]
    agg = {}
    for side in ("bull", "bear"):
        agg[side] = {}
        for sess in ("manana", "tarde"):
            sub = [x for x in pooled if x["side"] == side and x["session"] == sess]
            agg[side][sess] = summarize(sub)
        agg[side]["todo"] = summarize([x for x in pooled if x["side"] == side])

    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "params": {"tickers": TICKERS, "specs": FETCH_SPECS,
                   "bb": [BB_LEN, BB_STD], "death_retrace": RETRACE_DEATH,
                   "post_retrace": RETRACE_POST, "post_window_min": POST_WINDOW_MIN},
        "failed_tickers": failed,
        "por_ticker": results,
        "agregado": agg,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=1)

    # ---- tabla texto plano ----
    hdr = f"{'TICKER':<8}{'LADO':<6}{'SESION':<8}{'N':>4}{'MED_MIN':>9}{'P75_MIN':>9}{'EXT_MED%':>10}{'RETR50_30m':>12}"
    lines = ["MOMENTUM DECAY — empirico yfinance 1m(5d)+5m(1mo) — " + payload["generated"],
             hdr, "-" * len(hdr)]

    def row(name, side, sess, s):
        if s["n"] == 0:
            return f"{name:<8}{side:<6}{sess:<8}{0:>4}{'-':>9}{'-':>9}{'-':>10}{'-':>12}"
        return (f"{name:<8}{side:<6}{sess:<8}{s['n']:>4}{s['mediana_min']:>9.1f}"
                f"{s['p75_min']:>9.1f}{s['ext_mediana_pct']:>10.3f}"
                f"{100*s['prob_retroceso_50']:>11.0f}%")

    for sym in TICKERS:
        if sym not in results:
            lines.append(f"{sym:<8}{'—— FALLO DE DATOS, EXCLUIDO ——'}")
            continue
        for side in ("bull", "bear"):
            for sess in ("manana", "tarde"):
                lines.append(row(sym, side, sess, results[sym][side][sess]))
    lines.append("-" * len(hdr))
    for side in ("bull", "bear"):
        for sess in ("manana", "tarde", "todo"):
            lines.append(row("TODOS", side, sess, agg[side][sess]))
    print("\n".join(lines))
    print(f"\nJSON -> {OUT_JSON}" + (f" | fallos: {failed}" if failed else ""))


if __name__ == "__main__":
    main()
