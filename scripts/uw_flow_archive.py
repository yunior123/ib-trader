#!/usr/bin/env python3
"""uw_flow_archive.py — archivador de las series INTRADIA de UW. Puente TONTO: mueve bytes.

DOS MODOS:
  (1) daemon (por defecto): captura la sesion VIVA cada 60/300 s. Es lo que corre bajo
      com.ibtrader.uwflowarchive.
  (2) --backfill --days N: descarga sesiones PASADAS con `?date=`. Reanudable.

CORRECCION MEDIDA 2026-08-04: la cabecera original decia que UW «no sirve hacia atras». **FALSO.**
Medido contra la API con este mismo token: `?date=` devuelve la sesion intradia COMPLETA de las
tres series (405/405/434 filas para 2026-06-05), y el propio servidor declara la pared con un 403
`historic_data_access_missing`: «The earliest date currently available to you is 2026-03-24 (90
trading days)». 2026-03-24 -> 200; 2026-03-23 -> 403. Por eso existe el modo --backfill.

Cero computo de senal aqui dentro (regla PYTHON ES PELIGROSO): ni percentiles, ni signos, ni
umbrales. Eso es del motor. Aqui solo: pedir, verificar la forma, escribir atomico.

AHORRO MEDIDO: los tres endpoints devuelven la sesion ENTERA en una llamada (406 minutos en la
sonda del recon), no el ultimo minuto. Por eso una peticion cada 60 s captura los 390 minutos
del dia sin perder ninguno, en vez de 390 peticiones.

PROCEDENCIA: los ficheros del backfill llevan `source:"backfill"` + `pull_date` + `session_date`.
Los del daemon no llevan `source`. Un backtest jamas debe mezclarlos sin declararlo.
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
BACKFILL_STOP_FRACTION = 0.6   # freno absoluto del backfill sobre el cupo YA consumido hoy

# Medido 2026-08-04 contra la API: 2026-03-24 -> 200, 2026-03-23 -> 403. La pared la declara el
# servidor en cada 403; esto es solo el valor por defecto para PLANIFICAR sin gastar peticiones.
WALL_HINT = "2026-03-24"
WALL_CODE = "historic_data_access_missing"


class ShapeError(RuntimeError):
    """La respuesta no tiene la forma esperada. Se propaga: un archivo mudo miente peor que un fallo."""


class WallError(RuntimeError):
    """403 historic_data_access_missing: la fecha cae fuera del plan. Reintentar no la acerca."""


class QuotaStop(RuntimeError):
    """El cupo consumido hoy paso del freno. Se para y se reporta lo descargado."""


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
                # 403 de PARED != 403 de estrangulamiento: esperar 60 s no acerca marzo.
                if e.code == 403:
                    try:
                        cuerpo = e.read().decode("utf-8", "replace")
                    except Exception:
                        cuerpo = ""
                    if WALL_CODE in cuerpo:
                        raise WallError("%s: %s" % (path, cuerpo[:200].replace("\n", " ")))
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


# ---------------------------------------------------------------------------------------
# BACKFILL: sesiones pasadas via ?date=. Reanudable, escalonado, con freno de cupo.
# ---------------------------------------------------------------------------------------

def hole_path(kind, sym, day):
    """Marca de HUECO. Extension distinta de .json a proposito: ningun consumidor de
    `uw_*.json` puede confundir un dia sin dato con un dia con dato."""
    return dest(kind, sym, day)[:-len(".json")] + ".HUECO"


def archived_state(kind, sym, day):
    """('ok', n) si ya hay fichero bueno · ('hueco', 0) si hay marca · (None, 0) si falta.

    Un fichero corrupto, vacio o etiquetado con OTRO dia cuenta como ausente: se rebaja a
    None para que el backfill lo rehaga, jamas se da por bueno.
    """
    p = dest(kind, sym, day)
    if os.path.exists(p):
        try:
            with open(p) as f:
                d = json.load(f)
            rows = d["rows"]
            if d["n"] == len(rows) and rows and session_day(kind, rows) == day:
                return "ok", d["n"]
        except (OSError, ValueError, KeyError, ShapeError, TypeError):
            pass
        return None, 0
    if os.path.exists(hole_path(kind, sym, day)):
        return "hueco", 0
    return None, 0


def backfill_one(kind, sym, day, tok):
    """Una sesion-simbolo-serie. Devuelve (estado, n, cupo).

    Estados: 'nuevo' (bajado) · 'hueco' (200 con 0 filas, marcado) · 'ya' (ya en disco, 0 peticiones).
    Levanta WallError / ShapeError.
    GUARDA DURA: el dia lo pone el DATO y tiene que coincidir con el que se pidio. Si UW
    ignorase `?date=` y sirviese la sesion de hoy, aqui se levanta en vez de archivar la
    sesion de hoy con fecha de marzo.
    """
    estado, n = archived_state(kind, sym, day)
    if estado:                                 # ok o hueco ya en disco: no se vuelve a pedir
        return "ya", n, None

    path, _ = SERIES[kind]
    rows, headers = fetch(path.format(sym=sym) + "?date=" + day, tok)
    q = used_quota(headers)
    n = validate(kind, rows)
    if not rows:
        # 0 filas es un hecho (festivo a medias, hueco del vendor). Se MARCA, no se rellena.
        write_atomic(hole_path(kind, sym, day),
                     {"sym": sym, "kind": kind, "session_date": day, "n": 0, "hueco": True,
                      "source": "backfill", "pull_date": dt.date.today().isoformat(),
                      "motivo": "el vendor devolvio 200 con 0 filas"})
        return "hueco", 0, q

    dia_dato = session_day(kind, rows)
    if dia_dato != day:
        raise ShapeError("%s %s: se pidio ?date=%s y el dato dice %s; no se archiva"
                         % (kind, sym, day, dia_dato))
    write_atomic(dest(kind, sym, day),
                 {"sym": sym, "kind": kind, "session_date": day, "source": "backfill",
                  "pull_date": dt.date.today().isoformat(), "asof": round(time.time(), 1),
                  "n": n, "rows": rows})
    return "nuevo", n, q


def sessions_back(n_days, end=None):
    """Las n_days sesiones de mercado mas recientes que TERMINARON, mas nueva primero.

    Por defecto termina el ultimo dia de mercado ESTRICTAMENTE anterior a hoy: la sesion de
    hoy es del daemon y ademas esta incompleta.
    """
    d = (end or dt.date.today() - dt.timedelta(days=1))
    out = []
    tope = dt.date.fromisoformat(WALL_HINT) - dt.timedelta(days=14)
    while len(out) < n_days and d >= tope:
        if em_envelope.is_market_day(d):
            out.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return out


def coverage(kinds, syms, days):
    """Lo que hay en DISCO, sin gastar ni una peticion. {(kind,sym,day): (estado, n)}."""
    return {(k, s, d): archived_state(k, s, d) for d in days for s in syms for k in kinds}


def print_coverage(cov, kinds, syms, days):
    print("\ncobertura (sesiones=%d, syms=%d, series=%d, celdas=%d)"
          % (len(days), len(syms), len(kinds), len(cov)))
    print("%-16s %-6s %8s %8s %8s %10s" % ("serie", "sym", "ok", "hueco", "falta", "filas/ses"))
    for k in kinds:
        for s in syms:
            est = [cov[(k, s, d)] for d in days]
            ok = [n for e, n in est if e == "ok"]
            hue = sum(1 for e, _ in est if e == "hueco")
            falta = sum(1 for e, _ in est if e is None)
            med = (sorted(ok)[len(ok) // 2] if ok else 0)
            print("%-16s %-6s %8d %8d %8d %10d" % (k, s, len(ok), hue, falta, med))


def run_backfill(a, tok):
    kinds = [k.strip() for k in a.series.split(",") if k.strip()] if a.series else list(SERIES)
    for k in kinds:
        if k not in SERIES:
            sys.exit("uw_flow_archive ROTO: serie desconocida %r (validas: %s)"
                     % (k, ",".join(SERIES)))
    syms = [s.strip().upper() for s in a.syms.split(",") if s.strip()]
    try:
        end = dt.date.fromisoformat(a.end) if a.end else None
    except ValueError:
        sys.exit("--end debe ser YYYY-MM-DD (recibido: %r)" % a.end)
    days = sessions_back(a.days, end)
    cov = coverage(kinds, syms, days)
    pendientes = [c for c, (e, _) in cov.items() if e is None]
    print("backfill: %d sesiones (%s -> %s) x %d syms x %d series = %d celdas, %d pendientes"
          % (len(days), days[-1] if days else "-", days[0] if days else "-",
             len(syms), len(kinds), len(cov), len(pendientes)))
    tope_plan = int(DAILY_CAP * SAFETY_FRACTION)
    if len(pendientes) > tope_plan:
        sys.exit("uw_flow_archive ROTO: %d peticiones supera el tope propio %d (SAFETY_FRACTION). "
                 "Baja --days o --syms." % (len(pendientes), tope_plan))
    if a.dry_run:
        print_coverage(cov, kinds, syms, days)
        return 0

    freno = int(DAILY_CAP * a.max_quota_frac)
    q0 = q = None
    hecho = {"nuevo": 0, "ya": 0, "hueco": 0}
    fallos = []
    peticiones = 0
    pared = None
    t0 = time.time()
    try:
        for day in days:                       # mas nuevo primero: si se corta, queda lo util
            for sym in syms:
                for kind in kinds:
                    if q is not None and q >= freno:
                        raise QuotaStop("cupo %d >= freno %d" % (q, freno))
                    try:
                        est, n, qq = backfill_one(kind, sym, day, tok)
                    except WallError as e:
                        pared = "%s (primera fecha rechazada: %s)" % (str(e)[:160], day)
                        raise
                    except ShapeError as e:
                        fallos.append((kind, sym, day, str(e)[:120]))
                        print("FALLO %s %s %s: %s" % (kind, sym, day, str(e)[:120]),
                              file=sys.stderr)
                        time.sleep(a.sleep)
                        continue
                    hecho[est] += 1
                    if qq is not None:
                        q = qq
                        if q0 is None:
                            q0 = qq
                    if est != "ya":
                        peticiones += 1
                        print("%s %-16s %-5s %s %5d filas%s"
                              % (time.strftime("%H:%M:%S"), kind, sym, day, n,
                                 ("  [cupo %d/%d]" % (q, DAILY_CAP)) if q is not None else ""))
                        time.sleep(a.sleep)
    except (QuotaStop, WallError) as e:
        print("\nPARADA: %s" % e, file=sys.stderr)
    except KeyboardInterrupt:
        print("\nPARADA: interrumpido a mano", file=sys.stderr)

    cov = coverage(kinds, syms, days)
    print_coverage(cov, kinds, syms, days)
    rep = {
        "generado": dt.datetime.now().isoformat(timespec="seconds"),
        "modo": "backfill", "series": kinds, "syms": syms,
        "sesiones": days, "pared_declarada": pared, "wall_hint": WALL_HINT,
        "cupo_inicio": q0, "cupo_fin": q, "peticiones_backfill": peticiones,
        "segundos": round(time.time() - t0, 1),
        "celdas": {"ok": sum(1 for e, _ in cov.values() if e == "ok"),
                   "hueco": sum(1 for e, _ in cov.values() if e == "hueco"),
                   "falta": sum(1 for e, _ in cov.values() if e is None)},
        "nuevos": hecho["nuevo"], "ya_estaban": hecho["ya"],
        "huecos": [{"kind": k, "sym": s, "day": d}
                   for (k, s, d), (e, _) in sorted(cov.items()) if e == "hueco"],
        "faltan": [{"kind": k, "sym": s, "day": d}
                   for (k, s, d), (e, _) in sorted(cov.items()) if e is None],
        "fallos": [{"kind": k, "sym": s, "day": d, "error": m} for k, s, d, m in fallos],
    }
    write_atomic(os.path.join(REPO, "data", "uw_backfill_report.json"), rep)
    print("\npeticiones gastadas por el backfill: %d | cupo UW %s -> %s de %d"
          % (peticiones, q0, q, DAILY_CAP))
    print("informe: data/uw_backfill_report.json")
    return 1 if (fallos or rep["celdas"]["falta"]) else 0


def main():
    ap = argparse.ArgumentParser(description="archiva las series intradia de UW (puente tonto)")
    ap.add_argument("--syms", default=",".join(DEFAULT_SYMS))
    ap.add_argument("--once", action="store_true", help="una captura de cada serie y sale")
    ap.add_argument("--force", action="store_true", help="ignora el portero de sesion (pruebas)")
    ap.add_argument("--backfill", action="store_true", help="descarga sesiones PASADAS con ?date=")
    ap.add_argument("--days", type=int, default=90, help="sesiones de mercado hacia atras")
    ap.add_argument("--end", help="ultima sesion a bajar (YYYY-MM-DD); por defecto ayer")
    ap.add_argument("--series", help="subconjunto de series, coma-separado")
    ap.add_argument("--sleep", type=float, default=0.6, help="segundos entre peticiones")
    ap.add_argument("--max-quota-frac", type=float, default=BACKFILL_STOP_FRACTION,
                    help="para si el cupo consumido hoy pasa de esta fraccion de %d" % DAILY_CAP)
    ap.add_argument("--dry-run", action="store_true", help="solo cobertura en disco, cero peticiones")
    a = ap.parse_args()

    tok = token()
    if not tok:
        sys.exit("uw_flow_archive ROTO: sin UW_TOKEN (entorno ni config/feeds.env)")
    syms = [s.strip().upper() for s in a.syms.split(",") if s.strip()]
    if not syms:
        sys.exit("uw_flow_archive ROTO: lista de simbolos vacia")

    if a.backfill:
        return run_backfill(a, tok)

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
