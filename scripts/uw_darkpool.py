#!/usr/bin/env python3
"""uw_darkpool.py — prints de bloque fuera de bolsa (UW /api/darkpool/{sym}) -> data/uw_darkpool.json.

DESCRIPTIVO Y NADA MAS. La killlist de la casa (anti-overfit-killlist #3 `dpi-lite`) mato el
dark pool como SEÑAL: la replica bayesiana independiente pone el edge de DIX en ~0 y su
horizonte es de 60 dias contra un stack intradia. Aqui no hay probabilidad, ni score, ni
gatillo, ni voz: solo se agrega lo que UW MIDE (tamaño, precio, NBBO del momento del print)
y se publica con su latencia medida al lado. SEÑAL-SOLAMENTE.

Campos verificados contra la API real 2026-08-03: size, price, executed_at, premium,
nbbo_bid, nbbo_ask, volume (consolidado acumulado), market_center, trf_executed_at, canceled.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uw_premium import token  # noqa: E402
import em_envelope  # noqa: E402

SYMS = ("QQQ", "SPY", "SMH", "NVDA", "TSLA", "MU", "SKHY", "DRAM")
BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (uw_darkpool descriptivo senal-solamente)"
OUT = os.path.join(REPO, "data", "uw_darkpool.json")
LIMIT = 500              # maximo que sirve UW por llamada (medido 2026-08-03)
POLL_S = 120.0           # por simbolo; 8 syms -> 15 s entre requests, ~3100 req/sesion (cupo 30000)
TIMEOUT_S = 20
BACKOFF_403_S = (5, 15, 40)
N_BUCKETS = 40           # objetivo de barras del histograma precio-volumen
TOP_LEVELS = 8
TOP_PRINTS = 12
MID_TOL = 0.0001         # 1 pb del precio: "al punto medio" es una igualdad con tolerancia


def in_session():
    """04:00-20:00 ET en dia de mercado: los prints fuera de bolsa siguen llegando en
    extendido (medido: ultimo print del 31-jul a las 19:59 ET)."""
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (400 <= lt.tm_hour * 100 + lt.tm_min < 2000):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def fetch_darkpool(sym, tok):
    """(rows, None) o (None, error). Nunca [] fingido."""
    req = urllib.request.Request(
        f"{BASE}/api/darkpool/{sym}?limit={LIMIT}",
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json",
                 "User-Agent": UA})
    n_403 = 0
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return None, f"forma inesperada {sym}: {type(payload).__name__}"
            return rows, None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return None, "error 401 (token caducado)"
            if e.code in (403, 429):
                if n_403 < len(BACKOFF_403_S):
                    time.sleep(BACKOFF_403_S[n_403])
                    n_403 += 1
                    continue
                return None, f"error {e.code} tras {n_403} esperas"
            last = f"error {e.code}"
        except Exception as e:
            last = f"{e.__class__.__name__}: {str(e)[:60]}"
        if attempt < 3:
            time.sleep(1.5)
    return None, last


def _epoch(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def clean(rows):
    """Filas utilizables: no canceladas y con los campos numericos que usamos.
    Una fila malformada se salta; jamas se rellena con un numero plausible."""
    out = []
    for r in rows:
        try:
            if r.get("canceled"):
                continue
            c = {"ts": _epoch(r["executed_at"]), "size": int(r["size"]),
                 "price": float(r["price"]), "premium": float(r["premium"]),
                 "bid": float(r["nbbo_bid"]), "ask": float(r["nbbo_ask"]),
                 "vol": int(r["volume"]), "mc": r.get("market_center"),
                 "ext": bool(r.get("ext_hour_sold_codes"))}
            c["trf_lag_s"] = _epoch(r["trf_executed_at"]) - c["ts"] if r.get("trf_executed_at") else None
        except (KeyError, TypeError, ValueError):
            continue
        out.append(c)
    return out


def _nice_step(span):
    """Ancho de bucket 'redondo' (1/2/2.5/5 x 10^k) para ~N_BUCKETS barras."""
    raw = span / N_BUCKETS
    if not (raw > 0 and math.isfinite(raw)):
        return None
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= m * mag:
            return m * mag
    return 10.0 * mag


def levels(rs):
    """Histograma precio-volumen de los prints ocultos. Devuelve None si no se puede
    construir (un solo precio, sin filas): el widget dice 'sin dato', no dibuja una barra."""
    if not rs:
        return None
    lo = min(r["price"] for r in rs)
    hi = max(r["price"] for r in rs)
    step = _nice_step(hi - lo) if hi > lo else None
    if step is None:
        return None
    buckets = {}
    for r in rs:
        k = round(math.floor(r["price"] / step) * step, 6)
        buckets[k] = buckets.get(k, 0) + r["size"]
    tot = sum(buckets.values())
    if tot <= 0:
        return None
    top = sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)[:TOP_LEVELS]
    return {"step": step, "lo": lo, "hi": hi, "total_size": tot,
            "rows": [{"price": k, "size": v, "pct": round(100.0 * v / tot, 2)}
                     for k, v in top]}


def vs_mid(rs):
    """Reparto de los prints respecto al punto medio del NBBO **en el instante del print**.
    Es una DESCRIPCION de donde se imprimio, no una clasificacion de agresor: en dark pool
    el cruce al punto medio es el diseño, no una señal. None si no hay NBBO utilizable."""
    up = dn = mid = 0
    for r in rs:
        if not (r["ask"] > r["bid"] > 0):
            continue
        m = 0.5 * (r["bid"] + r["ask"])
        d = r["price"] - m
        if abs(d) <= MID_TOL * m:
            mid += r["size"]
        elif d > 0:
            up += r["size"]
        else:
            dn += r["size"]
    tot = up + dn + mid
    if tot <= 0:
        return None
    return {"above_mid_pct": round(100.0 * up / tot, 2),
            "at_mid_pct": round(100.0 * mid / tot, 2),
            "below_mid_pct": round(100.0 * dn / tot, 2), "total_size": tot}


def vs_ref(rs, ref):
    """Reparto del volumen oculto por encima/por debajo de `ref` (precio del print mas
    reciente). Descriptivo. None si no hay filas o `ref` no es utilizable."""
    if not rs or not (isinstance(ref, (int, float)) and ref > 0):
        return None
    up = sum(r["size"] for r in rs if r["price"] > ref)
    dn = sum(r["size"] for r in rs if r["price"] < ref)
    tot = up + dn
    if tot <= 0:
        return None
    return {"ref_price": ref, "above_pct": round(100.0 * up / tot, 2),
            "below_pct": round(100.0 * dn / tot, 2), "total_size": tot}


def dark_share(rs):
    """Volumen impreso fuera de bolsa / volumen consolidado de LA MISMA VENTANA.
    `volume` de UW es el consolidado acumulado del dia en el instante del print, asi que
    el denominador es la diferencia entre el print mas nuevo y el mas viejo de la pagina.
    None si la ventana no tiene avance de volumen (una sola fila, o pagina degenerada)."""
    if len(rs) < 2:
        return None
    newest = max(rs, key=lambda r: r["ts"])
    oldest = min(rs, key=lambda r: r["ts"])
    cons = newest["vol"] - oldest["vol"]
    if cons <= 0:
        return None
    dark = sum(r["size"] for r in rs)
    return {"dark_size": dark, "consolidated": cons,
            "pct": round(100.0 * dark / cons, 2),
            "window_s": round(newest["ts"] - oldest["ts"], 1)}


def latency(rs, now=None):
    """Latencia MEDIDA, dos numeros distintos y ambos honestos:
      feed_age_s  = ahora - print mas reciente (lo que el widget nota)
      trf_lag_med = mediana de trf_executed_at - executed_at (retraso de reporte del TRF)"""
    if not rs:
        return None
    now = now if now is not None else time.time()
    newest = max(r["ts"] for r in rs)
    lags = sorted(r["trf_lag_s"] for r in rs if r["trf_lag_s"] is not None)
    med = lags[len(lags) // 2] if lags else None
    return {"feed_age_s": round(now - newest, 1),
            "newest_iso": dt.datetime.fromtimestamp(newest, dt.timezone.utc).isoformat(),
            "trf_lag_med_s": med, "n_lags": len(lags)}


def big_prints(rs):
    rows = sorted(rs, key=lambda r: r["premium"], reverse=True)[:TOP_PRINTS]
    out = []
    for r in rows:
        m = 0.5 * (r["bid"] + r["ask"]) if r["ask"] > r["bid"] > 0 else None
        out.append({"ts": round(r["ts"], 1), "size": r["size"], "price": r["price"],
                    "premium": round(r["premium"], 2), "mc": r["mc"], "ext": r["ext"],
                    "vs_mid": (None if m is None else round(r["price"] - m, 4))})
    return out


def summarize(sym, rows, now=None):
    """Resumen descriptivo del simbolo. `error` si las filas no dan para nada:
    un resumen vacio jamas se disfraza de resumen con ceros."""
    rs = clean(rows)
    if not rs:
        return {"sym": sym, "error": "sin prints utilizables en la respuesta"}
    newest = max(rs, key=lambda r: r["ts"])
    return {"sym": sym, "n_prints": len(rs),
            "total_size": sum(r["size"] for r in rs),
            "total_premium": round(sum(r["premium"] for r in rs), 2),
            "last_price": newest["price"],
            "levels": levels(rs), "vs_mid": vs_mid(rs),
            "vs_last": vs_ref(rs, newest["price"]), "prints": big_prints(rs),
            "dark_share": dark_share(rs), "latency": latency(rs, now=now)}


def payload(by_sym, now=None):
    return {"asof": round(now if now is not None else time.time(), 1),
            "kind": "descriptivo",            # killlist #3: NO es señal, NO dispara
            "source": "Unusual Whales /api/darkpool/{sym}",
            "syms": by_sym}


def error_payload(err, now=None):
    """Sin `syms` a proposito: un error jamas fabrica simbolos."""
    return {"asof": round(now if now is not None else time.time(), 1), "error": err}


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="prints dark pool UW (descriptivo, senal-solamente)")
    ap.add_argument("--once", action="store_true", help="una pasada por los syms y sale")
    ap.add_argument("--syms", default="", help="lista separada por comas (default: capitanes)")
    a = ap.parse_args()

    tok = token()
    if not tok:
        sys.exit("uw_darkpool ROTO: sin UW_TOKEN (entorno ni feeds.env)")
    syms = tuple(s.strip().upper() for s in a.syms.split(",") if s.strip()) or SYMS

    stagger = POLL_S / len(syms)
    by_sym = {}
    fail_streak = 0
    print(f"uw_darkpool: {len(syms)} syms, {POLL_S:.0f}s/sym (~{stagger:.0f}s entre requests) -> {OUT}")
    while True:
        if not a.once and not in_session():
            time.sleep(60)
            continue
        for sym in syms:
            raw, err = fetch_darkpool(sym, tok)
            if raw is None:
                fail_streak += 1
                print(f"uw_darkpool {sym}: {err}", file=sys.stderr)
                if fail_streak >= len(syms):
                    write_atomic(OUT, error_payload(err))
                if "401" in (err or ""):
                    time.sleep(600)
            else:
                fail_streak = 0
                by_sym[sym] = summarize(sym, raw)
                write_atomic(OUT, payload(by_sym))
            time.sleep(0.3 if a.once else stagger)
        if a.once:
            print(f"uw_darkpool --once: {len(by_sym)} syms en {OUT}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
