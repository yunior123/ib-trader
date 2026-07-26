#!/usr/bin/env python3
"""uw_premium.py — premium NETO por lado en vivo (Unusual Whales net-prem-ticks),
para opt_whale_watch v2 (2026-07-26). El agresor manda: `net_call_premium`/
`net_put_premium` ya vienen firmados ask-side menos bid-side por UW, no hace
falta reconstruirlo con NBBO de IBKR. SEÑAL-SOLAMENTE, solo lectura, cero cache
de fallback disfrazado — un fallo se propaga, jamas se convierte en 0."""
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (opt_whale_watch v2 senal-solamente)"
TIMEOUT_S = 12
RETRIES = 2


def token():
    t = (os.environ.get("UW_TOKEN") or "").strip()
    if t:
        return t
    try:
        with open(os.path.join(REPO, "feeds.env")) as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith("UW_TOKEN="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def fetch_net_prem_ticks(sym, tok):
    """Filas del dia, mas recientes al final. Levanta si no se puede — nunca [] fingido."""
    req = urllib.request.Request(
        f"{BASE}/api/stock/{sym}/net-prem-ticks",
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json", "User-Agent": UA})
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ValueError(f"forma inesperada de {sym}: {type(payload)}")
            return rows
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError(f"UW_TOKEN caducado (401) en {sym}") from e
            last = e   # 403/429: puede ser rate-limit, no necesariamente token muerto
        except Exception as e:
            last = e
        if attempt < RETRIES - 1:
            time.sleep(1.0)
    raise RuntimeError(f"UW net-prem-ticks {sym} fallo tras {RETRIES} intentos: {last}")


def _epoch(tape_time):
    return dt.datetime.fromisoformat(tape_time.replace("Z", "+00:00"))


def latest_feed_age_s(rows, now=None):
    """(edad_en_segundos, tape_time_mas_reciente). (None, None) si no hay filas."""
    if not rows:
        return None, None
    last = max(rows, key=lambda r: r["tape_time"])
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now - _epoch(last["tape_time"])).total_seconds(), last["tape_time"]


def signed_premium(rows, window_min=15, now=None):
    """Suma net_call_premium - net_put_premium en los ultimos window_min minutos
    de tape. Positivo = agresor compra calls / vende puts = BULLISH en dolares.
    None si no hay filas (nunca 0 fingido)."""
    if not rows:
        return None
    last_ts = max(_epoch(r["tape_time"]) for r in rows)
    cutoff = last_ts - dt.timedelta(minutes=window_min)
    ncp = npp = 0.0
    n = 0
    for r in rows:
        if _epoch(r["tape_time"]) > cutoff:
            ncp += float(r["net_call_premium"])
            npp += float(r["net_put_premium"])
            n += 1
    if n == 0:
        return None
    return {"net_call_premium": ncp, "net_put_premium": npp,
            "signed_premium": ncp - npp, "n_buckets": n}
