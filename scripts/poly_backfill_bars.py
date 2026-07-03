#!/usr/bin/env python3
"""poly_backfill_bars.py — backfill de 2 AÑOS de barras 1m para la flota, a poly_bars.

El desbloqueo: con 21 dias de historia casi ninguna feature del roadmap es medible y
todos los buckets salen DATA-INSUFFICIENT. Con 2 años (~500 sesiones) si.

PROPIEDADES (las tres que pidio Yunior, y por que):
  IDEMPOTENTE  poly_bars tiene PRIMARY KEY(sym, ts) -> INSERT OR IGNORE. Correrlo dos
               veces sobre el mismo rango no duplica nada. Verificado por test.
  REANUDABLE   tabla poly_bf_progress guarda el cursor en MILISEGUNDOS por (sym, tf).
               Polygon acepta epoch-ms en /range/{tf}/minute/{from}/{to} (verificado),
               asi que se retoma en el ms exacto: ni hueco ni relectura.
               Matarlo a mitad y relanzarlo continua donde iba.
  HUECOS       al final se NOMBRAN las sesiones NYSE sin datos y las anomalamente
               cortas. Un dia que falta y nadie lo dice es un backtest que parece
               completo y no lo es — ese es el peligro real.

RITMO: 5 peticiones / 60 s medidas (ver poly_client.py). Con limit=50000 una peticion
trae ~3 meses de 1m, asi que 2 años son ~8-9 peticiones por simbolo: ~250 peticiones
para la flota => ~50 min de reloj. Se puede cortar y reanudar cuando sea.

BD: WAL + timeout y UN commit por pagina (nunca una transaccion de minutos): hay 6
procesos vivos leyendo trades.db y signals_db escribiendo.

Uso:
  python3 scripts/poly_backfill_bars.py run [--years 2] [--tf 1] [--syms QQQ SPY]
  python3 scripts/poly_backfill_bars.py status        # por donde va cada simbolo
  python3 scripts/poly_backfill_bars.py gaps [--syms ...]   # informe de huecos
"""
import datetime as dt
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_client import DB_PATH, Polygon, PolygonError, fleet, market_days  # noqa: E402

os.environ.setdefault("TZ", "America/New_York")
time.tzset()

PAGE = 50000
MIN_BARS_DAY = 300     # una sesion RTH completa a 1m son 390 barras (+pre/post). Por
                       # debajo de esto es media sesion o dia parcial: se REPORTA.


def db():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=60000")
    c.execute("""CREATE TABLE IF NOT EXISTS poly_bars(
        sym TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
        PRIMARY KEY(sym, ts))""")
    # la PK ya da el indice unico (sqlite_autoindex_poly_bars_1); este es explicito y
    # barato por si alguna vez se recrea la tabla sin PK.
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_poly_bars_sym_ts ON poly_bars(sym, ts)")
    c.execute("""CREATE TABLE IF NOT EXISTS poly_bf_progress(
        sym TEXT, tf INTEGER, target_from INTEGER, target_to INTEGER,
        cursor_ms INTEGER, rows_new INTEGER, requests INTEGER,
        done INTEGER, updated REAL, PRIMARY KEY(sym, tf))""")
    c.execute("""CREATE TABLE IF NOT EXISTS poly_dl_log(
        sym TEXT, kind TEXT, d0 TEXT, d1 TEXT, rows INTEGER, ts REAL)""")
    return c


def progress(c, sym, tf):
    return c.execute("SELECT target_from,target_to,cursor_ms,rows_new,requests,done "
                     "FROM poly_bf_progress WHERE sym=? AND tf=?", (sym, tf)).fetchone()


def save_progress(c, sym, tf, tf_from, tf_to, cursor, rows, reqs, done):
    c.execute("INSERT INTO poly_bf_progress VALUES(?,?,?,?,?,?,?,?,?) "
              "ON CONFLICT(sym,tf) DO UPDATE SET target_from=excluded.target_from, "
              "target_to=excluded.target_to, cursor_ms=excluded.cursor_ms, "
              "rows_new=poly_bf_progress.rows_new+excluded.rows_new, "
              "requests=poly_bf_progress.requests+excluded.requests, "
              "done=excluded.done, updated=excluded.updated",
              (sym, tf, tf_from, tf_to, cursor, rows, reqs, 1 if done else 0, time.time()))
    c.commit()


def backfill_sym(poly, c, sym, tf, t_from, t_to):
    """Descarga [t_from, t_to] en ms para un simbolo, reanudando desde el cursor.
    Devuelve (filas_nuevas, peticiones, terminado, error_o_None).
    Un fallo NO se traga: se devuelve el motivo y el cursor queda donde llego."""
    pr = progress(c, sym, tf)
    cursor = t_from
    if pr and pr[2] and pr[0] == t_from and pr[1] == t_to:
        if pr[5]:
            return 0, 0, True, None            # ya terminado para este objetivo
        cursor = max(t_from, pr[2] + 1)
    new = reqs = 0
    while cursor <= t_to:
        url = (f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/{tf}/minute/"
               f"{cursor}/{t_to}?adjusted=true&sort=asc&limit={PAGE}")
        d = poly.get(url)
        reqs += 1
        if d is None:
            save_progress(c, sym, tf, t_from, t_to, cursor - 1, new, reqs, False)
            return new, reqs, False, "peticion abandonada tras reintentos"
        res = d.get("results") or []
        if not res:
            # sin resultados en lo que queda del rango: objetivo cubierto
            save_progress(c, sym, tf, t_from, t_to, t_to, new, reqs, True)
            return new, reqs, True, None
        rows = []
        for b in res:
            try:
                rows.append((sym, int(b["t"]), b["o"], b["h"], b["l"], b["c"], b.get("v", 0)))
            except (KeyError, TypeError, ValueError) as e:
                # barra malformada: se cuenta como fallo visible, no se rellena con 0
                return new, reqs, False, f"barra malformada de Polygon: {e!r}"
        before = c.total_changes
        c.executemany("INSERT OR IGNORE INTO poly_bars VALUES(?,?,?,?,?,?,?)", rows)
        c.commit()                              # commit por pagina: la BD no se bloquea
        inserted = c.total_changes - before
        new += inserted
        last = rows[-1][1]
        if last <= cursor - 1:
            return new, reqs, False, "el cursor no avanza (respuesta incoherente)"
        cursor = last + 1
        save_progress(c, sym, tf, t_from, t_to, last, inserted, 1, False)
        print(f"    {sym:6s} +{inserted:6d} (de {len(res)}) hasta "
              f"{dt.datetime.fromtimestamp(last / 1000):%Y-%m-%d %H:%M}", flush=True)
        if len(res) < PAGE and not d.get("next_url"):
            save_progress(c, sym, tf, t_from, t_to, t_to, 0, 0, True)
            return new, reqs, True, None
    save_progress(c, sym, tf, t_from, t_to, t_to, 0, 0, True)
    return new, reqs, True, None


def run(syms, years, tf):
    c = db()
    poly = Polygon()
    d1 = dt.date.today()
    d0 = d1 - dt.timedelta(days=int(365.25 * years))
    t_from = int(dt.datetime.combine(d0, dt.time(0, 0)).timestamp() * 1000)
    t_to = int(dt.datetime.combine(d1, dt.time(23, 59)).timestamp() * 1000)
    print(f"BACKFILL poly_bars {tf}m | {len(syms)} simbolos | {d0} -> {d1} ({years} años)")
    print(f"  ritmo medido 5 pet./60s -> estimado ~{len(syms) * 9 * 12.4 / 60:.0f} min\n")
    tot_new = 0
    fallos = []
    t0 = time.time()
    for i, sym in enumerate(syms, 1):
        try:
            new, reqs, done, err = backfill_sym(poly, c, sym, tf, t_from, t_to)
        except PolygonError as e:
            fallos.append((sym, str(e)))
            print(f"  ! {sym}: {e}", flush=True)
            continue
        tot_new += new
        c.execute("INSERT INTO poly_dl_log VALUES(?,?,?,?,?,?)",
                  (sym, f"backfill{tf}m", f"{d0}", f"{d1}", new, time.time()))
        c.commit()
        state = "COMPLETO" if done else "INCOMPLETO"
        print(f"  [{i:2d}/{len(syms)}] {sym:6s} {state} +{new} filas en {reqs} peticiones"
              f"  ({(time.time() - t0) / 60:.0f} min)", flush=True)
        if err:
            fallos.append((sym, err))
            print(f"       ! {sym}: {err}", flush=True)
    print(f"\n-> {tot_new} filas nuevas en {(time.time() - t0) / 60:.1f} min")
    print(f"-> {poly.report()}")
    if fallos:
        print(f"-> FALLOS ({len(fallos)}) — reanudable, relanza y continua desde el cursor:")
        for s, w in fallos:
            print(f"     {s}: {w}")
    else:
        print("-> sin fallos")
    return tot_new, fallos


def status(syms, tf):
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    print(f"{'sym':7s} {'dias':>5s} {'filas':>8s} {'desde':>10s} {'hasta':>10s} "
          f"{'cursor':>10s} estado")
    tot_rows = 0
    for sym in syms:
        r = c.execute("SELECT COUNT(*), MIN(ts), MAX(ts), COUNT(DISTINCT date(ts/1000,"
                      "'unixepoch','localtime')) FROM poly_bars WHERE sym=?", (sym,)).fetchone()
        n, mn, mx, nd = r if r else (0, None, None, 0)
        tot_rows += n or 0
        pr = c.execute("SELECT cursor_ms, done FROM poly_bf_progress WHERE sym=? AND tf=?",
                       (sym, tf)).fetchone()
        cur = f"{dt.date.fromtimestamp(pr[0] / 1000)}" if pr and pr[0] else "-"
        st = ("COMPLETO" if pr and pr[1] else ("en curso" if pr else "sin arrancar"))
        f0 = f"{dt.date.fromtimestamp(mn / 1000)}" if mn else "-"
        f1 = f"{dt.date.fromtimestamp(mx / 1000)}" if mx else "-"
        print(f"{sym:7s} {nd or 0:5d} {n or 0:8d} {f0:>10s} {f1:>10s} {cur:>10s} {st}")
    print(f"TOTAL {tot_rows} filas")


def gaps(syms, min_bars=MIN_BARS_DAY):
    """Informe de HUECOS: sesiones NYSE sin ninguna barra, y sesiones con menos de
    `min_bars` (media sesion o dia parcial). Se NOMBRAN, no se cuentan y punto."""
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    print(f"INFORME DE HUECOS (sesiones NYSE sin datos / parciales, umbral {min_bars} barras)\n")
    total_missing = total_thin = 0
    for sym in syms:
        rows = dict(c.execute(
            "SELECT date(ts/1000,'unixepoch','localtime') d, COUNT(*) FROM poly_bars "
            "WHERE sym=? GROUP BY d ORDER BY d", (sym,)).fetchall())
        if not rows:
            print(f"{sym:7s} SIN NINGUN DATO")
            continue
        days = sorted(rows)
        d0 = dt.date.fromisoformat(days[0])
        d1 = dt.date.fromisoformat(days[-1])
        expected = market_days(d0, d1)
        missing = [f"{d:%Y-%m-%d}" for d in expected if f"{d:%Y-%m-%d}" not in rows]
        thin = [(d, rows[d]) for d in days if rows[d] < min_bars]
        total_missing += len(missing)
        total_thin += len(thin)
        print(f"{sym:7s} {len(days):4d} dias con datos / {len(expected):4d} sesiones "
              f"[{days[0]} .. {days[-1]}]  faltan {len(missing)}  parciales {len(thin)}")
        if missing:
            print(f"        FALTAN: {' '.join(missing[:40])}"
                  + (f" ... (+{len(missing) - 40})" if len(missing) > 40 else ""))
        if thin:
            print(f"        PARCIALES: "
                  + " ".join(f"{d}({n})" for d, n in thin[:20])
                  + (f" ... (+{len(thin) - 20})" if len(thin) > 20 else ""))
    print(f"\n-> TOTAL: {total_missing} sesiones ausentes, {total_thin} sesiones parciales")
    return total_missing, total_thin


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else "status"

    def opt(flag, default, cast=str):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    syms = fleet()
    if "--syms" in a:
        i = a.index("--syms") + 1
        syms = [s.upper() for s in a[i:] if not s.startswith("--")]
    tf = opt("--tf", 1, int)
    if cmd == "run":
        run(syms, opt("--years", 2.0, float), tf)
    elif cmd == "status":
        status(syms, tf)
    elif cmd == "gaps":
        gaps(syms, opt("--min-bars", MIN_BARS_DAY, int))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
