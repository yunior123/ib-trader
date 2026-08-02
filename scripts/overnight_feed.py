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
KST = ZoneInfo("Asia/Seoul")
OUT = os.path.join(REPO, "data", "overnight_ctx.json")
SENT_DIR = os.path.join(REPO, "data", "x_sentiment")
PREVCLOSE_NAME = "korea_prevclose.json"           # lo escribe korea_bar_bridge.update_prev_close
PREVCLOSE = os.path.join(REPO, "data", PREVCLOSE_NAME)
CTX_JSONL = os.path.join(REPO, "data", "history", "overnight_ctx.jsonl")
KOREA = {"hynix_pct": "skhynix", "samsung_pct": "samsung", "kospi_pct": "kospi"}
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


def krx_session_date(epoch):
    """Fecha KST de la sesion KRX a la que pertenece `epoch` (KRX 09:00-15:30 KST)."""
    return datetime.fromtimestamp(epoch, KST).date().isoformat()


def prev_krx_session_date(boundary):
    """Fecha KST de la sesion inmediatamente ANTERIOR a la que abre en `boundary`."""
    cur = datetime.fromtimestamp(boundary + 3600, KST).date()
    d = cur - timedelta(days=1)
    while d.weekday() >= 5:                       # KRX cierra sabado y domingo
        d -= timedelta(days=1)
    return d.isoformat()


def load_prevclose(name, path=None):
    """Entrada de data/korea_prevclose.json para `name`. None si falta o esta corrupta."""
    try:
        with open(path or PREVCLOSE) as f:
            j = json.load(f)
        e = j.get(name)
        if not isinstance(e, dict):
            return None
        c, ep, s = e.get("close"), e.get("epoch"), e.get("session")
        if not c or float(c) <= 0 or ep is None or not s:
            return None
        return {"close": float(c), "epoch": float(ep), "session": str(s)}
    except Exception:
        return None


def korea_pct(name, boundary):
    """(pct de la sesion KRX en curso, fuente de la referencia). Referencia: la ultima
    barra pre-boundary del propio fichero; si ya no queda (warmup lo trunca), el
    prev_close persistido SOLO si es de la sesion inmediatamente anterior.
    Sin referencia honesta -> (None, None). Jamas 0.0 (regla #2)."""
    try:
        ref = last = None
        last_t = 0.0
        try:
            with open(os.path.join(REPO, "data", f"bars_{name}.txt")) as f:
                for ln in f:
                    p = ln.split()
                    if len(p) < 5:
                        continue
                    t, c = float(p[0]), float(p[4])
                    if t < boundary:
                        ref = c
                    last, last_t = c, t
        except FileNotFoundError:
            return None, None
        src = "bars" if ref else None
        if not ref:
            pc = load_prevclose(name)
            if pc and pc["epoch"] < boundary and \
                    pc["session"] == prev_krx_session_date(boundary):
                ref, src = pc["close"], "prevclose"
        if ref and last is not None and last_t >= boundary:
            return round((last - ref) / ref * 100.0, 4), src
        return None, None
    except Exception:
        return None, None


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


def archive_ctx(ctx):
    """Append 1 linea/ciclo: unica forma de MEDIR luego el patron de la madrugada."""
    try:
        os.makedirs(os.path.dirname(CTX_JSONL), exist_ok=True)
        with open(CTX_JSONL, "a") as f:
            f.write(json.dumps(ctx) + "\n")
        return True
    except Exception as e:
        print(f"overnight_feed: archivo jsonl fallo — {e}", file=sys.stderr)
        return False


def build():
    ctx = {"ts": time.time(), "nq_pct": fut_pct("NQ=F"), "es_pct": fut_pct("ES=F")}
    b = krx_boundary()
    for key, name in KOREA.items():
        pct, src = korea_pct(name, b)
        ctx[key] = pct
        ctx[key.replace("_pct", "_ref_src")] = src   # "bars"|"prevclose"|null: "no se" != "se, y es 0"
    ctx["sent"] = sentiment()
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ctx, f)
    os.replace(tmp, OUT)
    archive_ctx(ctx)
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
