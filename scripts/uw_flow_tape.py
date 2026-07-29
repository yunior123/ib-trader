#!/usr/bin/env python3
"""uw_flow_tape.py — cinta de ballenas en vivo: UW /flow-alerts -> data/uw_flow_tape.json.
Campos medidos con probe real 2026-07-28 (UW NO trae `sentiment` ni `side` directo: el lado
se deriva de total_bid/ask_side_prem MEDIDOS; sentiment solo se pasa si UW lo trae).
SEÑAL-SOLAMENTE, cero voz. Daemon: 90 s por simbolo escalonado, solo RTH."""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uw_premium import token  # noqa: E402
import em_envelope  # noqa: E402

# capitanes de flujo (regla 12: SPY/QQQ mercado, SMH semis) + foco memoria/lideres del dia
SYMS = ("QQQ", "SPY", "SMH", "NVDA", "TSLA", "MU", "SKHY", "DRAM")
BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (uw_flow_tape senal-solamente)"
OUT = os.path.join(REPO, "data", "uw_flow_tape.json")
POLL_S = 90.0            # por simbolo; 8 syms -> ~11 s entre requests, ~770 req/sesion (cupo 30000)
LIMIT = 40
MAX_ROWS = 60
TIMEOUT_S = 20
BACKOFF_403_S = (5, 15, 40)   # mismo patron medido en uw_archive: 403 tambien es rate-limit


def in_session():
    """RTH + dia de mercado real (mismo patron que opt_whale_watch.in_session)."""
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def fetch_alerts(sym, tok):
    """(rows, None) o (None, error). Nunca [] fingido."""
    req = urllib.request.Request(
        f"{BASE}/api/stock/{sym}/flow-alerts?limit={LIMIT}",
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


def _side(r):
    """Lado dominante derivado de los premiums POR LADO que UW mide (no hay campo `side`)."""
    total = float(r["total_premium"])
    bid = float(r["total_bid_side_prem"])
    ask = float(r["total_ask_side_prem"])
    mid = max(total - bid - ask, 0.0)
    return max((bid, "bid"), (ask, "ask"), (mid, "mid"))[1]


def map_row(r):
    """Fila de la cinta desde el alert crudo de UW. None si esta malformada (se salta)."""
    try:
        ts = dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).timestamp()
        out = {"ts": round(ts, 1), "sym": r["ticker"].upper(),
               "type": "C" if r["type"] == "call" else "P",
               "side": _side(r), "strike": float(r["strike"]), "expiry": r["expiry"],
               "premium": float(r["total_premium"]), "size": int(r["total_size"]),
               "oi": int(r["open_interest"]), "vol": int(r["volume"]),
               "vol_oi": round(float(r["volume_oi_ratio"]), 1),
               "rule": r.get("alert_rule"), "sweep": bool(r.get("has_sweep"))}
        if "sentiment" in r:   # UW no lo trae hoy; si algun dia lo trae, se pasa TAL CUAL
            out["sentiment"] = r["sentiment"]
        return out
    except (KeyError, TypeError, ValueError):
        return None


def _key(r):
    return (r.get("ticker"), r.get("option_chain"), r.get("created_at"))


def merge(rows_by_key, raw_rows):
    """Acumula alerts nuevos y recorta a los MAX_ROWS mas recientes por ts."""
    for r in raw_rows:
        m = map_row(r)
        if m is not None:
            rows_by_key[_key(r)] = m
    if len(rows_by_key) > MAX_ROWS:
        keep = sorted(rows_by_key.items(), key=lambda kv: kv[1]["ts"], reverse=True)[:MAX_ROWS]
        rows_by_key.clear()
        rows_by_key.update(keep)
    return rows_by_key


def tape_payload(rows_by_key, now=None):
    rows = sorted(rows_by_key.values(), key=lambda r: r["ts"], reverse=True)
    return {"asof": round(now if now is not None else time.time(), 1), "rows": rows}


def error_payload(err, now=None):
    """Sin `rows` a proposito: un error jamas fabrica filas."""
    return {"asof": round(now if now is not None else time.time(), 1), "error": err}


def stale_s(payload, now=None):
    """Edad del tape en segundos. None si el payload no trae asof."""
    asof = payload.get("asof") if isinstance(payload, dict) else None
    if not isinstance(asof, (int, float)):
        return None
    return (now if now is not None else time.time()) - asof


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="cinta de ballenas UW (senal-solamente)")
    ap.add_argument("--once", action="store_true", help="una pasada por los 8 syms y sale")
    a = ap.parse_args()

    tok = token()
    if not tok:
        sys.exit("uw_flow_tape ROTO: sin UW_TOKEN (entorno ni feeds.env)")

    stagger = POLL_S / len(SYMS)
    rows_by_key = {}
    fail_streak = 0
    print(f"uw_flow_tape: {len(SYMS)} syms, {POLL_S:.0f}s/sym (~{stagger:.0f}s entre requests) -> {OUT}")
    while True:
        if not a.once and not in_session():
            time.sleep(60)
            continue
        for sym in SYMS:
            raw, err = fetch_alerts(sym, tok)
            if raw is None:
                fail_streak += 1
                print(f"uw_flow_tape {sym}: {err}", file=sys.stderr)
                if fail_streak >= len(SYMS):   # ciclo entero fallando = persistente -> el widget ve el motivo
                    write_atomic(OUT, error_payload(err))
                if "401" in (err or ""):
                    time.sleep(600)   # token muerto: no martillear; el widget ya lo dice
            else:
                fail_streak = 0
                merge(rows_by_key, raw)
                write_atomic(OUT, tape_payload(rows_by_key))
            time.sleep(0.3 if a.once else stagger)
        if a.once:
            p = tape_payload(rows_by_key)
            print(f"uw_flow_tape --once: {len(p['rows'])} filas en {OUT}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
