#!/usr/bin/env python3
"""cboe_nbbo_sidecar.py — bid/ask de RESPALDO desde CBOE para las fichas de opciones.

POR QUE EXISTE (2026-08-04): sin IBKR (prohibido esta semana) la cadena viva sale del
snapshot de Polygon, que trae strikes/OI/griegas pero CERO bid/ask (`bidask_ok_pct 0.0000`
medido en cabecera; /v3/quotes de opciones = 403 con esta key). Resultado: order_ticket
daba NO-GO "sin bid/ask valido" en TODA la flota y ninguna ficha podia armarse.

CBOE delayed_quotes SI trae bid/ask (medido hoy: 11.977 de 12.632 contratos de QQQ).
Doctrina LATENCIA-FUENTES: CBOE = estructura y "bid/ask de respaldo" — DELAYED y desigual.
Por eso este dato JAMAS aprueba un GO: la ficha con spread CBOE se capa a CAUTION con la
etiqueta "(spread CBOE delayed)" y el humano ve el NBBO real en IBKR al ejecutar.

Puente TONTO: mueve bytes, cero computo de senal. data/cboe_nbbo_<sym>.json atomico.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import em_envelope  # noqa: E402

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
UA = "ib-trader/1.0 (cboe_nbbo_sidecar respaldo bid/ask)"
OCC = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
POLL_S = 300.0            # CBOE es delayed: mas rapido no compra nada
STAGGER_S = 4.0
TIMEOUT_S = 60


def fleet():
    syms = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    if not syms:
        raise RuntimeError("data/fleet.txt vacio")
    return [s.upper() for s in syms]


def in_session():
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (925 <= lt.tm_hour * 100 + lt.tm_min < 1601):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def fetch(sym):
    """{clave: [bid, ask]} con clave "C|YYYYMMDD|strike". Levanta si no hay dato util."""
    req = urllib.request.Request(URL.format(sym), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        d = json.load(r)
    ops = ((d or {}).get("data") or {}).get("options") or []
    out = {}
    for o in ops:
        m = OCC.match(str(o.get("option") or ""))
        if not m:
            continue
        _, ymd, cp, kk = m.groups()
        bid, ask = o.get("bid"), o.get("ask")
        if not bid or not ask or float(ask) <= 0 or float(bid) < 0:
            continue                       # sin lado no hay spread: se omite, no se inventa
        out["%s|20%s|%g" % (cp, ymd, int(kk) / 1000.0)] = [float(bid), float(ask)]
    if not out:
        raise RuntimeError("%s: CBOE sirvio 0 contratos con bid/ask" % sym)
    return out


def dest(sym):
    return os.path.join(REPO, "data", "cboe_nbbo_%s.json" % sym.lower())


def write_atomic(sym, quotes):
    path = dest(sym)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"sym": sym, "asof": round(time.time(), 1), "src": "cboe_delayed",
                   "n": len(quotes), "quotes": quotes}, f, separators=(",", ":"))
    os.replace(tmp, path)
    return path


def main():
    ap = argparse.ArgumentParser(description="bid/ask de respaldo CBOE (delayed, etiquetado)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--syms")
    a = ap.parse_args()
    syms = [s.strip().upper() for s in a.syms.split(",")] if a.syms else fleet()
    print("cboe_nbbo_sidecar: %d syms, %.0fs de ciclo" % (len(syms), POLL_S))
    fallos = {}
    while True:
        if not a.force and not a.once and not in_session():
            time.sleep(60)
            continue
        for sym in syms:
            try:
                q = fetch(sym)
                fallos.pop(sym, None)
                print("%s %s: %d contratos con bid/ask" % (time.strftime("%H:%M:%S"), sym, len(q)))
                write_atomic(sym, q)
            except Exception as e:
                fallos[sym] = fallos.get(sym, 0) + 1
                print("%s FALLO %s: %s (racha %d)" % (time.strftime("%H:%M:%S"), sym,
                                                      str(e)[:80], fallos[sym]), file=sys.stderr)
                # 3 rachas del MISMO simbolo: se avisa una vez; sin dato el ticket cae a
                # "sin bid/ask" que ya es fail-loud aguas abajo.
                if fallos[sym] == 3:
                    try:
                        import notify_short
                        notify_short.push("⚠ CBOE NBBO", "%s sin respaldo bid/ask (3 rachas)" % sym)
                    except Exception:
                        pass
            time.sleep(0.3 if a.once else STAGGER_S)
        if a.once:
            return 1 if fallos else 0
        time.sleep(max(POLL_S - STAGGER_S * len(syms), 30.0))


if __name__ == "__main__":
    sys.exit(main())
