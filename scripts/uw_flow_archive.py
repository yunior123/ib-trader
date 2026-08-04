#!/usr/bin/env python3
"""uw_flow_archive.py — archivador de las series INTRADIA de UW. Puente TONTO: mueve bytes.

POR QUE EXISTE Y POR QUE HOY: `net-prem-ticks`, `greek-flow` y `flow-per-strike` son series
del DIA. UW no las sirve hacia atras (`?date=` de dias pasados no devuelve la serie intradia
completa), asi que **lo que no se archive hoy no se puede medir nunca**. El reloj de la muestra
de las 3 alertas propuestas en docs/UW-FLOW-RECON-2026-08-04.md empieza el dia que esto corre.

Cero computo de senal aqui dentro (regla PYTHON ES PELIGROSO): ni percentiles, ni signos, ni
umbrales. Eso es del motor. Aqui solo: pedir, verificar la forma, escribir atomico.

AHORRO MEDIDO: los tres endpoints devuelven la sesion ENTERA en una llamada (406 minutos en la
sonda del recon), no el ultimo minuto. Por eso una peticion cada 60 s captura los 390 minutos
del dia sin perder ninguno, en vez de 390 peticiones.
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
import em_envelope  # noqa: E402

BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (uw_flow_archive senal-solamente)"
TIMEOUT_S = 30
BACKOFF_S = (5, 15, 40)

# Los 5 del recon: capitanes (regla 12) + los dos nombres con mas flujo propio de la casa.
DEFAULT_SYMS = ("SPY", "QQQ", "SMH", "NVDA", "MU")

# endpoint -> (ruta, cada cuantos segundos, clave del fichero)
SERIES = {
    "net_prem_ticks": ("/api/stock/{sym}/net-prem-ticks", 60),
    "greek_flow": ("/api/stock/{sym}/greek-flow", 60),
    "flow_per_strike": ("/api/stock/{sym}/flow-per-strike", 300),
}

# Campos sin los cuales la fila no sirve: si faltan, se LEVANTA. Jamas se rellena con 0.
REQUIRED = {
    "net_prem_ticks": ("tape_time", "net_call_premium", "net_put_premium"),
    "greek_flow": ("timestamp", "dir_vega_flow"),
    "flow_per_strike": ("strike",),
}

DAILY_CAP = int(os.environ.get("UW_DAILY_CAP", "30000"))
SAFETY_FRACTION = 0.5          # este archivador jamas se come mas de la mitad del cupo


class ShapeError(RuntimeError):
    """La respuesta no tiene la forma esperada. Se propaga: un archivo mudo miente peor que un fallo."""


def in_session(now=None):
    """RTH de un dia de mercado real. Fuera de ahi no hay serie intradia que archivar."""
    lt = now or time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1601):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def fetch(path, tok):
    """(rows, headers) o levanta. Nunca [] fingido: sin datos se propaga el motivo."""
    req = urllib.request.Request(BASE + path,
                                 headers={"Authorization": "Bearer " + tok,
                                          "Accept": "application/json", "User-Agent": UA})
    n_throttle = 0
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
                headers = dict(r.headers)
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                raise ShapeError("%s: forma inesperada %s" % (path, type(payload).__name__))
            return rows, headers
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ShapeError("401: UW_TOKEN caducado")
            if e.code in (403, 429):
                if n_throttle < len(BACKOFF_S):
                    time.sleep(BACKOFF_S[n_throttle])
                    n_throttle += 1
                    continue
                raise ShapeError("%s: %d tras %d esperas" % (path, e.code, n_throttle))
            last = "error %d" % e.code
        except ShapeError:
            raise
        except Exception as e:
            last = "%s: %s" % (e.__class__.__name__, str(e)[:60])
        if attempt < 3:
            time.sleep(1.5)
    raise ShapeError("%s: agotados los intentos (%s)" % (path, last))


def validate(kind, rows):
    """Levanta si a una fila le falta un campo obligatorio. Devuelve el nº de filas validadas."""
    req = REQUIRED[kind]
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ShapeError("%s fila %d no es un objeto: %s" % (kind, i, type(r).__name__))
        faltan = [k for k in req if k not in r]
        if faltan:
            raise ShapeError("%s fila %d sin %s" % (kind, i, ",".join(faltan)))
    return len(rows)


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def session_day(kind, rows):
    """Dia de la SESION segun el propio dato, no segun el reloj.

    A las 02:37 del dia 4, UW sirve la sesion del dia 3: etiquetar por reloj archivaria la
    sesion del lunes dentro de la carpeta del martes y ningun backtest posterior lo notaria.
    La sesion ET 09:30-16:00 cae siempre en 13:30-20:00 UTC, misma fecha de calendario, asi
    que la parte de fecha del timestamp UTC es la del dia de mercado.
    """
    dias = set()
    for r in rows:
        if "date" in r and r["date"]:
            dias.add(str(r["date"])[:10])
        elif "timestamp" in r and r["timestamp"]:
            dias.add(str(r["timestamp"])[:10])
    if not dias:
        raise ShapeError("%s: ninguna fila trae date ni timestamp; sin dia no se archiva" % kind)
    if len(dias) > 1:
        raise ShapeError("%s: la respuesta mezcla %d dias (%s)"
                         % (kind, len(dias), ",".join(sorted(dias))))
    return dias.pop()


def dest(kind, sym, day):
    return os.path.join(REPO, "data", "history", day, "uw_%s_%s.json" % (kind, sym.lower()))


def snapshot(kind, sym, tok, day=None):
    """Una captura. Devuelve (filas, ruta). El fichero se REEMPLAZA: la serie es acumulativa."""
    path, _ = SERIES[kind]
    rows, headers = fetch(path.format(sym=sym), tok)
    n = validate(kind, rows)
    out = dest(kind, sym, day or session_day(kind, rows))
    write_atomic(out, {"sym": sym, "kind": kind, "asof": round(time.time(), 1),
                       "n": n, "rows": rows})
    return n, out, headers


def used_quota(headers):
    """Peticiones consumidas hoy segun UW. None si la cabecera no viene: no se inventa."""
    for k in ("x-uw-daily-req-count", "X-Uw-Daily-Req-Count"):
        if k in headers:
            try:
                return int(headers[k])
            except (TypeError, ValueError):
                return None
    return None


def main():
    ap = argparse.ArgumentParser(description="archiva las series intradia de UW (puente tonto)")
    ap.add_argument("--syms", default=",".join(DEFAULT_SYMS))
    ap.add_argument("--once", action="store_true", help="una captura de cada serie y sale")
    ap.add_argument("--force", action="store_true", help="ignora el portero de sesion (pruebas)")
    a = ap.parse_args()

    tok = token()
    if not tok:
        sys.exit("uw_flow_archive ROTO: sin UW_TOKEN (entorno ni config/feeds.env)")
    syms = [s.strip().upper() for s in a.syms.split(",") if s.strip()]
    if not syms:
        sys.exit("uw_flow_archive ROTO: lista de simbolos vacia")

    presupuesto = int(DAILY_CAP * SAFETY_FRACTION)
    por_dia = sum(int(390 * 60 / cada) for _, cada in SERIES.values()) * len(syms)
    print("uw_flow_archive: %d syms x %d series -> ~%d peticiones/sesion (tope propio %d de %d)"
          % (len(syms), len(SERIES), por_dia, presupuesto, DAILY_CAP))
    if por_dia > presupuesto:
        sys.exit("uw_flow_archive ROTO: %d peticiones/sesion supera el tope propio %d. "
                 "Baja --syms o sube la cadencia en SERIES." % (por_dia, presupuesto))

    proxima = {(k, s): 0.0 for k in SERIES for s in syms}
    fallos = {}
    gastadas = None
    while True:
        if not a.force and not a.once and not in_session():
            time.sleep(60)
            continue
        ahora = time.time()
        for (kind, sym), cuando in sorted(proxima.items(), key=lambda kv: kv[1]):
            if not a.once and cuando > ahora:
                continue
            try:
                n, out, headers = snapshot(kind, sym, tok)
                fallos.pop((kind, sym), None)
                q = used_quota(headers)
                if q is not None:
                    gastadas = q
                print("%s %-16s %-5s %4d filas -> %s%s"
                      % (time.strftime("%H:%M:%S"), kind, sym, n,
                         os.path.relpath(out, REPO),
                         ("  [cupo %d/%d]" % (q, DAILY_CAP)) if q is not None else ""))
            except ShapeError as e:
                fallos[(kind, sym)] = fallos.get((kind, sym), 0) + 1
                print("%s FALLO %s %s: %s (racha %d)"
                      % (time.strftime("%H:%M:%S"), kind, sym, e, fallos[(kind, sym)]),
                      file=sys.stderr)
                # 3 fallos seguidos de la MISMA serie: se grita, no se archiva en silencio.
                if fallos[(kind, sym)] == 3:
                    try:
                        import notify_short
                        notify_short.push("⚠ ARCHIVO UW",
                                          "%s %s falla 3 veces: %s" % (kind, sym, str(e)[:80]))
                    except Exception:
                        pass
                if "401" in str(e):
                    time.sleep(600)
            proxima[(kind, sym)] = time.time() + SERIES[kind][1]
            time.sleep(0.4)                       # escalonado: no rafagas contra la API
        if a.once:
            if gastadas is not None:
                print("cupo UW consumido hoy: %d de %d" % (gastadas, DAILY_CAP))
            return 1 if fallos else 0
        time.sleep(1.0)


if __name__ == "__main__":
    sys.exit(main())
