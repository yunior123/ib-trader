#!/usr/bin/env python3
"""uw_net_prem.py — premium NETO firmado por UW (net-prem-ticks) -> data/uw_net_prem.json.

Llena el widget `wgt-prem` del cockpit, que estaba VACIO y rotulado "requiere tick-by-tick de
opciones IBKR (err 10189)". No hace falta: UW ya firma el lado agresor por bucket de minuto.

GOTCHA de la casa, no reinventarlo: `signed_premium = net_call_premium - net_put_premium`.
NO es "net call premium" (SPY dio +104M firmado con net_call -20M el mismo dia).
Vender un put es alcista, por eso el put entra RESTANDO.

Latencia: UW, declarada en cada payload con `feed_age_s` MEDIDO. No dispara ordenes
(la doctrina reserva el disparo a IBKR). SEÑAL-SOLAMENTE, cero voz.
Campos verificados contra la API real 2026-08-03.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import em_envelope  # noqa: E402
import uw_premium  # noqa: E402

SYMS = ("QQQ", "SPY", "SMH", "NVDA", "TSLA", "MU", "SKHY", "DRAM")
OUT = os.path.join(REPO, "data", "uw_net_prem.json")
POLL_S = 90.0            # por simbolo; 8 syms -> ~11 s entre requests
WINDOWS_MIN = (15, 60)
SERIES_MAX = 120         # ultimos N buckets de minuto para la curva del widget


def in_session():
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def cumulative(rows):
    """Curva acumulada de premium firmado a lo largo del dia, un punto por bucket.
    None si no hay filas (nunca una curva plana en cero fingida)."""
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: r["tape_time"])
    acc = 0.0
    out = []
    for r in ordered:
        acc += float(r["net_call_premium"]) - float(r["net_put_premium"])
        out.append({"ts": round(uw_premium._epoch(r["tape_time"]).timestamp(), 1),
                    "cum": round(acc, 2)})
    return out[-SERIES_MAX:]


def day_totals(rows):
    """Totales del dia entero. None si no hay filas."""
    if not rows:
        return None
    ncp = sum(float(r["net_call_premium"]) for r in rows)
    npp = sum(float(r["net_put_premium"]) for r in rows)
    return {"net_call_premium": round(ncp, 2), "net_put_premium": round(npp, 2),
            "signed_premium": round(ncp - npp, 2),
            "net_delta": round(sum(float(r["net_delta"]) for r in rows), 2),
            "call_volume": sum(int(r["call_volume"]) for r in rows),
            "put_volume": sum(int(r["put_volume"]) for r in rows),
            "n_buckets": len(rows)}


def summarize(sym, rows, now=None):
    """Resumen del simbolo. `error` si las filas no dan para nada: cero fabricado, jamas."""
    if not rows:
        return {"sym": sym, "error": "sin filas de net-prem-ticks"}
    age_s, feed_ts = uw_premium.latest_feed_age_s(rows, now=now)
    out = {"sym": sym, "day": day_totals(rows), "series": cumulative(rows),
           "feed_age_s": None if age_s is None else round(age_s, 1), "feed_ts": feed_ts,
           "windows": {}}
    for w in WINDOWS_MIN:
        sp = uw_premium.signed_premium(rows, window_min=w, now=now)
        if sp is not None:
            sp = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in sp.items()}
        out["windows"][str(w)] = sp   # None explicito = no habia buckets en la ventana
    return out


def payload(by_sym, now=None):
    return {"asof": round(now if now is not None else time.time(), 1),
            "source": "Unusual Whales /api/stock/{sym}/net-prem-ticks",
            "note": "signed_premium = net_call_premium - net_put_premium",
            "syms": by_sym}


def error_payload(err, now=None):
    return {"asof": round(now if now is not None else time.time(), 1), "error": err}


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="premium neto firmado UW (senal-solamente)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--syms", default="", help="lista separada por comas (default: capitanes)")
    a = ap.parse_args()

    tok = uw_premium.token()
    if not tok:
        sys.exit("uw_net_prem ROTO: sin UW_TOKEN (entorno ni feeds.env)")
    syms = tuple(s.strip().upper() for s in a.syms.split(",") if s.strip()) or SYMS

    stagger = POLL_S / len(syms)
    by_sym = {}
    fail_streak = 0
    print(f"uw_net_prem: {len(syms)} syms, {POLL_S:.0f}s/sym -> {OUT}")
    while True:
        if not a.once and not in_session():
            time.sleep(60)
            continue
        for sym in syms:
            try:
                rows = uw_premium.fetch_net_prem_ticks(sym, tok)
            except Exception as e:
                fail_streak += 1
                err = f"{e.__class__.__name__}: {str(e)[:80]}"
                print(f"uw_net_prem {sym}: {err}", file=sys.stderr)
                if fail_streak >= len(syms):
                    write_atomic(OUT, error_payload(err))
                if "401" in err:
                    time.sleep(600)
            else:
                fail_streak = 0
                by_sym[sym] = summarize(sym, rows)
                write_atomic(OUT, payload(by_sym))
            time.sleep(0.3 if a.once else stagger)
        if a.once:
            print(f"uw_net_prem --once: {len(by_sym)} syms en {OUT}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
