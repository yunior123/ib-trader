#!/usr/bin/env python3
"""uw_gex_expiry.py — GEX/DEX/charm/vanna POR VENCIMIENTO (UW /greek-exposure/expiry)
-> data/uw_gex_expiry.json.

POR QUE EXISTE (medido 2026-08-03): el archivo propio se para en el mensual siguiente
(`poly_chain_archive.py:445`, `--dte` None en los 3 invocadores) y la cadena VIVA se recorta
a 2 vencimientos (`provider_bridge.py:160 NEAR_EXPS = 2`), asi que `data/gex_snapshot.json`
publicaba QQQ y SPY con UN SOLO vencimiento. 2026-08-24..08-31 no existia en ninguna parte.
UW devuelve TODOS los vencimientos en UNA llamada, 08-28 y 08-31 incluidos.

LATENCIA: **EOD DIARIO**. El campo `date` es el cierre de la ultima sesion, no el ahora.
Por doctrina de la casa esto es MAPA/CONTEXTO y JAMAS dispara una orden: el disparo se
reserva a IBKR en tiempo real. La edad se publica en cada payload para que se vea.
SEÑAL-SOLAMENTE, cero voz. Campos verificados contra la API real 2026-08-03.
"""
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

BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (uw_gex_expiry mapa senal-solamente)"   # urllib pelado -> Cloudflare 1010
OUT = os.path.join(REPO, "data", "uw_gex_expiry.json")
UNIVERSE_F = os.path.join(REPO, "data", "universe_gamma.txt")
DTE_MAX = 45             # cubre "las proximas 2-3 semanas y todo agosto" con margen
POLL_S = 1800.0          # dato EOD: repreguntar rapido no lo hace mas nuevo
TIMEOUT_S = 20
BACKOFF_403_S = (5, 15, 40)
PAUSE_S = 0.4


def universe():
    """El universo del MAPA (35). LEVANTA si no se puede leer: media flota en silencio
    es peor que ninguna (nadie se enteraria del hueco)."""
    with open(UNIVERSE_F) as f:
        syms = f.read().split()
    if not syms:
        raise RuntimeError("data/universe_gamma.txt VACIA")
    return [s.upper() for s in syms]


def fetch_expiry(sym, tok):
    """(rows, None) o (None, error). Nunca [] fingido."""
    req = urllib.request.Request(
        f"{BASE}/api/stock/{sym}/greek-exposure/expiry",
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


def map_row(r, today=None):
    """Fila por vencimiento. None si esta malformada (se salta, no se rellena).
    `dte` se RECALCULA contra hoy: el que sirve UW es relativo a su sello EOD, asi que el
    lunes pintaba el vencimiento del viernes como '0d' cuando ya habia expirado."""
    try:
        cg, pg = float(r["call_gex"]), float(r["put_gex"])
        cd, pd_ = float(r["call_delta"]), float(r["put_delta"])
        exp = dt.date.fromisoformat(r["expiry"])
        return {"expiry": r["expiry"], "dte": (exp - (today or dt.date.today())).days,
                "dte_uw": int(r["dte"]),
                "call_gex": cg, "put_gex": pg, "net_gex": cg + pg,
                "call_delta": cd, "put_delta": pd_, "net_delta": cd + pd_,
                "net_charm": float(r["call_charm"]) + float(r["put_charm"]),
                "net_vanna": float(r["call_vanna"]) + float(r["put_vanna"])}
    except (KeyError, TypeError, ValueError):
        return None


def summarize(sym, rows, dte_max=DTE_MAX, today=None):
    """Vencimientos vivos dentro de dte_max, ordenados. `error` si no queda ninguno:
    una lista vacia jamas se disfraza de cobertura."""
    if not rows:
        return {"sym": sym, "error": "sin filas de greek-exposure/expiry"}
    # el sello es el MAXIMO, no rows[0]: en el endpoint hermano /greek-exposure la serie
    # empieza hace un año y tomar la primera fila daria un cierre de 2025 por "hoy".
    stamps = [r["date"] for r in rows if isinstance(r, dict) and r.get("date")]
    stamp = max(stamps) if stamps else None
    out = []
    for r in rows:
        m = map_row(r, today=today)
        if m is not None and 0 <= m["dte"] <= dte_max:
            out.append(m)
    if not out:
        return {"sym": sym, "error": f"sin vencimientos vivos dentro de {dte_max} DTE"}
    out.sort(key=lambda m: m["dte"])
    return {"sym": sym, "asof_date": stamp, "n_expiries": len(out),
            "exp_hasta": out[-1]["expiry"], "net_gex_total": sum(m["net_gex"] for m in out),
            "rows": out}


def stamp_age_days(by_sym, today=None):
    """Edad en dias del cierre que sirve UW. None si ningun simbolo trajo `date`."""
    today = today or dt.date.today()
    ds = [v["asof_date"] for v in by_sym.values() if v.get("asof_date")]
    if not ds:
        return None
    return (today - dt.date.fromisoformat(max(ds))).days


def payload(by_sym, now=None, today=None):
    return {"asof": round(now if now is not None else time.time(), 1),
            "latency": "EOD_DIARIO",          # NO dispara: mapa/contexto (doctrina de la casa)
            "source": "Unusual Whales /api/stock/{sym}/greek-exposure/expiry",
            "stamp_age_days": stamp_age_days(by_sym, today=today),
            "dte_max": DTE_MAX, "syms": by_sym}


def error_payload(err, now=None):
    return {"asof": round(now if now is not None else time.time(), 1), "error": err}


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="GEX por vencimiento UW (mapa, senal-solamente)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--syms", default="", help="lista separada por comas (default: universe_gamma)")
    a = ap.parse_args()

    tok = token()
    if not tok:
        sys.exit("uw_gex_expiry ROTO: sin UW_TOKEN (entorno ni feeds.env)")
    syms = [s.strip().upper() for s in a.syms.split(",") if s.strip()] or universe()

    print(f"uw_gex_expiry: {len(syms)} syms, <= {DTE_MAX} DTE -> {OUT}")
    while True:
        by_sym = {}
        n_err = 0
        for sym in syms:
            rows, err = fetch_expiry(sym, tok)
            if rows is None:
                n_err += 1
                print(f"uw_gex_expiry {sym}: {err}", file=sys.stderr)
                if "401" in (err or ""):
                    write_atomic(OUT, error_payload(err))
                    time.sleep(600)
                    break
            else:
                by_sym[sym] = summarize(sym, rows)
            time.sleep(PAUSE_S)
        if by_sym:
            write_atomic(OUT, payload(by_sym))
        elif n_err:
            write_atomic(OUT, error_payload(f"los {n_err} simbolos fallaron"))
        print(f"uw_gex_expiry: {len(by_sym)} syms ok, {n_err} fallos")
        if a.once:
            return 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
