#!/usr/bin/env python3
"""uw_latency_probe.py — MEDIR (no suponer) la latencia real de Unusual Whales
en sesion viva, condicion dura de ~/CLAUDE.md antes de fiarse de una fuente
("ningun nivel que dispare una orden viene de fuente delayed"). Correr manual
en horas de mercado: ./venv/bin/python scripts/uw_latency_probe.py
Fuera de horas dice por que no midio, jamas finge un numero (2026-07-26,
domingo con mercado cerrado: NO se pudo medir hoy, queda listo para el lunes).
Escribe data/uw_latency_probe.jsonl (historial acumulado). SEÑAL-SOLAMENTE."""
import datetime as dt
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import em_envelope
import uw_premium

PROBE_F = os.path.join(REPO, "data", "uw_latency_probe.jsonl")
SYMS = ["SPY", "QQQ"]
REALTIME_BAR_S = 60   # 1 bucket de tape: mas viejo que esto ya no es "tiempo real"


def in_session():
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def probe_darkpool(sym, tok, now):
    """Edad del print de bloque mas reciente. El dato NO se toca: solo se mide."""
    import uw_darkpool
    rows, err = uw_darkpool.fetch_darkpool(sym, tok)
    if rows is None:
        return {"sym": sym, "endpoint": "darkpool", "error": err}
    lat = uw_darkpool.latency(uw_darkpool.clean(rows), now=now.timestamp())
    if lat is None:
        return {"sym": sym, "endpoint": "darkpool", "error": "sin prints utilizables"}
    return {"sym": sym, "endpoint": "darkpool", "feed_ts": lat["newest_iso"],
            "feed_age_s": lat["feed_age_s"], "trf_lag_med_s": lat["trf_lag_med_s"],
            "n_rows": len(rows)}


def probe_gex_expiry(sym, tok, now):
    """Sello EOD de greek-exposure/expiry. Se espera DIARIO, no segundos: se mide en dias."""
    import uw_gex_expiry
    rows, err = uw_gex_expiry.fetch_expiry(sym, tok)
    if rows is None:
        return {"sym": sym, "endpoint": "greek-exposure/expiry", "error": err}
    s = uw_gex_expiry.summarize(sym, rows)
    if "error" in s:
        return {"sym": sym, "endpoint": "greek-exposure/expiry", "error": s["error"]}
    stamp = s["asof_date"]
    age = (now.date() - dt.date.fromisoformat(stamp)).days
    return {"sym": sym, "endpoint": "greek-exposure/expiry", "feed_ts": stamp,
            "feed_age_days": age, "n_rows": len(rows)}


def main():
    todo = "--all" in sys.argv    # + darkpool y greek-exposure/expiry (widgets 2026-08-03)
    if not in_session():
        print("FUERA DE SESION (fin de semana, festivo o fuera de 09:30-16:00): "
              "no se puede medir latencia real hoy — probe NO ejecutado", file=sys.stderr)
        return 1
    tok = uw_premium.token()
    if not tok:
        print("SIN UW_TOKEN: no se puede medir", file=sys.stderr)
        return 1

    now = dt.datetime.now(dt.timezone.utc)
    results = []
    for sym in SYMS:
        try:
            rows = uw_premium.fetch_net_prem_ticks(sym, tok)
            age_s, feed_ts = uw_premium.latest_feed_age_s(rows, now=now)
            rec = {"ts": now.isoformat(), "sym": sym, "endpoint": "net-prem-ticks",
                   "feed_ts": feed_ts, "feed_age_s": age_s, "n_rows": len(rows)}
        except Exception as e:
            rec = {"ts": now.isoformat(), "sym": sym, "endpoint": "net-prem-ticks",
                   "error": str(e)}
        results.append(rec)
        print(json.dumps(rec))
        with open(PROBE_F, "a") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        time.sleep(0.6)

    # Endpoints de los widgets nuevos: se miden APARTE porque su unidad no es la misma
    # (darkpool en segundos, greek-exposure/expiry en DIAS) y mezclarlos daria un veredicto falso.
    if todo:
        for sym in SYMS:
            for fn in (probe_darkpool, probe_gex_expiry):
                r = dict(fn(sym, tok, now), ts=now.isoformat())
                print(json.dumps(r))
                with open(PROBE_F, "a") as f:
                    f.write(json.dumps(r, separators=(",", ":")) + "\n")
                time.sleep(0.6)

    fails = [r for r in results if "error" in r]
    if fails:
        print(f"-> {len(fails)}/{len(results)} FALLARON, no se puede fijar veredicto", file=sys.stderr)
        return 1
    ages = [r["feed_age_s"] for r in results if r.get("feed_age_s") is not None]
    if not ages:
        print("-> sin feed_age_s en ninguna fila: no se puede fijar veredicto", file=sys.stderr)
        return 1
    veredicto = "CANDIDATO A TIEMPO-REAL" if max(ages) < REALTIME_BAR_S else "DELAYED — no dispara"
    print(f"-> UW feed_age_s min={min(ages):.1f}s max={max(ages):.1f}s -> {veredicto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
