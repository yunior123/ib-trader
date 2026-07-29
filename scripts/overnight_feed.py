#!/usr/bin/env python3
"""overnight_feed.py — puente TONTO: NQ/ES (yfinance) + Corea (bars locales) + sentimiento X
-> data/overnight_ctx.json atomico cada 120s, solo fuera de RTH US. Cero computo de senal.
Regla #3: dato que falla = null, jamas 0.0. Uso: [--once] para una sola escritura."""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gex_core

TZ = ZoneInfo("America/Toronto")
OUT = os.path.join(REPO, "data", "overnight_ctx.json")
SENT_DIR = os.path.join(REPO, "data", "x_sentiment")
KOREA = {"hynix_pct": "bars_skhynix.txt", "samsung_pct": "bars_samsung.txt",
         "kospi_pct": "bars_kospi.txt"}
LOOP_S, RTH_NAP_S, SENT_MAX_AGE_S = 120, 300, 7200


def fut_pct(sym):
    try:
        import yfinance as yf
        fi = yf.Ticker(sym).fast_info
        last, prev = fi["last_price"], fi["previous_close"]
        if last and prev:
            return round((last - prev) / prev * 100.0, 4)
        return None
    except Exception:
        return None


def krx_boundary(now=None):
    # apertura KRX de esta noche = las 20:00 Toronto mas recientes (hoy, o ayer si aun no son)
    now = now or datetime.now(TZ)
    b = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if b > now:
        b -= timedelta(days=1)
    return b.timestamp()


def korea_pct(fname, boundary):
    try:
        ref = last = None
        last_t = 0.0
        with open(os.path.join(REPO, "data", fname)) as f:
            for ln in f:
                p = ln.split()
                if len(p) < 5:
                    continue
                t, c = float(p[0]), float(p[4])
                if t < boundary:
                    ref = c
                last, last_t = c, t
        if ref and last is not None and last_t >= boundary:
            return round((last - ref) / ref * 100.0, 4)
        return None
    except Exception:
        return None


def sentiment():
    # tally con el clasificador YA existente del repo (x_sentiment.classify); solo para why[]
    try:
        files = [os.path.join(SENT_DIR, f) for f in os.listdir(SENT_DIR) if f.endswith(".json")]
        if not files:
            return None
        newest = max(files, key=os.path.getmtime)
        if time.time() - os.path.getmtime(newest) > SENT_MAX_AGE_S:
            return None
        with open(newest) as f:
            j = json.load(f)
        import x_sentiment as xs
        ko = any("가" <= ch <= "힣" for ch in j.get("query", ""))
        pos_kw, neg_kw = (xs.POS_KO, xs.NEG_KO) if ko else (xs.POS_EN, xs.NEG_EN)
        p, n, _ = xs.classify([t.get("text", "") for t in (j.get("data") or [])], pos_kw, neg_kw)
        return {"tag": os.path.basename(newest).rsplit("_", 2)[0],
                "n": j.get("n"), "pos": p, "neg": n}
    except Exception:
        return None


def build():
    ctx = {"ts": time.time(), "nq_pct": fut_pct("NQ=F"), "es_pct": fut_pct("ES=F")}
    b = krx_boundary()
    for key, fname in KOREA.items():
        ctx[key] = korea_pct(fname, b)
    ctx["sent"] = sentiment()
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ctx, f)
    os.replace(tmp, OUT)
    return ctx


def main():
    once = "--once" in sys.argv
    while True:
        if gex_core.in_rth():
            if once:
                print("RTH: no toca", flush=True)
                return
            time.sleep(RTH_NAP_S)
            continue
        print(json.dumps(build()), flush=True)
        if once:
            return
        time.sleep(LOOP_S)


if __name__ == "__main__":
    main()
