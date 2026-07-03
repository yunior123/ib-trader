#!/usr/bin/env python3
"""uw_netprem_archive.py — TODOS 8d: archivador FORWARD-ONLY de net-prem-ticks de los 30 de
data/fleet.txt, una pasada al CIERRE (16:10 ET). Puente TONTO: pedir, validar forma, escribir.

Por que al cierre y no intradia: el endpoint devuelve la SESION ENTERA en una llamada (medido en
el recon del 2026-08-04), asi que una pasada tras el cierre captura los 390 minutos del dia con
30 peticiones = 0,1% del cupo, en vez de las ~7.560/dia que costaria el muestreo intradia.

Cero computo de senal aqui dentro (regla PYTHON ES PELIGROSO): ni signos, ni umbrales, ni sumas.
Un fallo se propaga; jamas se archiva un fichero mudo ni se rellena con 0.

Salida: data/history/<fecha-de-sesion>/uw_net_prem_ticks_<sym>.json — mismo formato y misma
funcion `session_day` que uw_flow_archive.py, para que los dos archivos sean intercambiables.
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
from uw_flow_archive import (ShapeError, dest, fetch, session_day,  # noqa: E402
                             used_quota, validate, write_atomic)
from uw_premium import token  # noqa: E402

KIND = "net_prem_ticks"
PATH = "/api/stock/{sym}/net-prem-ticks"
PAUSE_S = 0.4          # escalonado: nada de rafagas contra la API
DAILY_CAP = int(os.environ.get("UW_DAILY_CAP", "30000"))


def fleet():
    """Los 30 de data/fleet.txt. Fuente unica; si falta el fichero se levanta."""
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        syms = [s.strip().upper() for s in f.read().split() if s.strip()]
    if not syms:
        raise RuntimeError("data/fleet.txt vacio: sin universo no se archiva nada")
    return syms


def es_dia_de_mercado(d=None):
    return em_envelope.is_market_day(d or dt.date.today())


def archivar(sym, tok, forzar_dia=None):
    """(n_filas, ruta, cupo). Levanta ShapeError con el motivo."""
    rows, headers = fetch(PATH.format(sym=sym), tok)
    n = validate(KIND, rows)
    if not rows:
        raise ShapeError("%s: 200 con 0 filas al cierre; no se archiva fichero mudo" % sym)
    dia = forzar_dia or session_day(KIND, rows)
    out = dest(KIND, sym, dia)
    write_atomic(out, {"sym": sym, "kind": KIND, "session_date": dia,
                       "source": "netprem_archive_eod", "asof": round(time.time(), 1),
                       "n": n, "rows": rows})
    return n, out, used_quota(headers)


def main():
    ap = argparse.ArgumentParser(description="archiva net-prem-ticks de la flota al cierre")
    ap.add_argument("--syms", default=None, help="lista coma-separada; por defecto data/fleet.txt")
    ap.add_argument("--force", action="store_true",
                    help="ignora el portero de dia de mercado (pruebas)")
    ap.add_argument("--dry-run", action="store_true", help="cero peticiones: solo dice que haria")
    a = ap.parse_args()

    if not a.force and not es_dia_de_mercado():
        print("HOY NO ES DIA DE MERCADO: no hay sesion que archivar", file=sys.stderr)
        return 0

    syms = ([s.strip().upper() for s in a.syms.split(",") if s.strip()] if a.syms else fleet())
    if a.dry_run:
        print("archivaria %d syms (%d peticiones = %.2f%% del cupo %d): %s"
              % (len(syms), len(syms), 100.0 * len(syms) / DAILY_CAP, DAILY_CAP, ",".join(syms)))
        return 0

    tok = token()
    if not tok:
        sys.exit("uw_netprem_archive ROTO: sin UW_TOKEN (entorno ni config/feeds.env)")

    ok, fallos, cupo = 0, [], None
    for sym in syms:
        try:
            n, out, q = archivar(sym, tok)
            ok += 1
            if q is not None:
                cupo = q
            print("%s %-5s %4d filas -> %s" % (time.strftime("%H:%M:%S"), sym, n,
                                               os.path.relpath(out, REPO)))
        except (ShapeError, Exception) as e:  # noqa: B014
            fallos.append((sym, "%s: %s" % (type(e).__name__, str(e)[:120])))
            print("%s FALLO %-5s %s" % (time.strftime("%H:%M:%S"), sym, str(e)[:120]),
                  file=sys.stderr)
        time.sleep(PAUSE_S)

    print("\nnet-prem-ticks archivados: %d/%d%s"
          % (ok, len(syms), ("  [cupo %d/%d]" % (cupo, DAILY_CAP)) if cupo is not None else ""))
    if fallos:
        print("FALLARON %d: %s" % (len(fallos), ", ".join(s for s, _ in fallos)), file=sys.stderr)
        # 3+ fallos = problema de fuente, no de un simbolo: se GRITA, no se archiva en silencio.
        if len(fallos) >= 3:
            try:
                import notify_short
                notify_short.push("⚠ ARCHIVO UW EOD",
                                  "net-prem-ticks fallo en %d/%d syms" % (len(fallos), len(syms)))
            except Exception:
                pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
