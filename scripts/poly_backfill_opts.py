#!/usr/bin/env python3
"""poly_backfill_opts.py — backfill de BARRAS DIARIAS DE OPCIONES a poly_opt_bars.

POR QUE EXISTE
  `poly_opt_bars` tenia 114.337 filas pero solo **10-22 sesiones** (NVDA 22, el resto
  10). Varias features piden **60 sesiones** de superficie de IV. La IV del pasado NO
  se descarga (Polygon no sirve griegas historicas en este plan) pero SI se reconstruye
  invirtiendola por biseccion desde el precio del contrato (`gex_core.implied_vol`).
  Para eso hace falta la MATERIA PRIMA: barras de opciones con historia. Eso trae esto.

LO QUE SE MIDIO CON LA KEY REAL (2026-07-25) — no de memoria:
  OK   /v2/aggs/ticker/O:<c>/range/1/day/{from}/{to}  -> 200. Una sola peticion devuelve
       la VIDA ENTERA del contrato en barras diarias (medido: 73 barras para
       O:QQQ260515C00500000). Da v vw o c h l t n. NO da OI ni griegas.
  OK   /v3/reference/options/contracts?underlying_ticker=X&expired=true
       &expiration_date.gte=..&expiration_date.lte=..  -> 200, 1000 por pagina, con
       contratos VENCIDOS reales (QQQ llega a expiries de 2011).
  TRAMPA  `as_of=` en /v3/reference/options/contracts se **IGNORA**: as_of=2026-03-16 y
       as_of=2025-09-15 devolvieron la MISMA primera pagina. Misma trampa que el
       `as_of` del snapshot. -> aqui NO se usa `as_of`; se acota por expiration_date.
  NO EXISTE  /v2/aggs/grouped/locale/us/market/options/{fecha} -> HTTP 400.
  NO AUTORIZADO  /v3/trades/O: y /v3/quotes/O: -> 403 (no se reintenta).
  NO HAY OI HISTORICO a ningun precio en este plan. No se aproxima. No se afirma.

ESTRATEGIA (el presupuesto es el recurso escaso: 5 peticiones/60 s = 12 s cada una)
  Como una peticion trae la vida entera de un contrato, la palanca no es el volumen de
  peticiones sino el ORDEN. Se trabaja por RONDAS de moneyness:
     ronda 0: ATM de cada (simbolo x expiry)  -> con ~112 peticiones los 8 simbolos
              pasan de 10 sesiones a la ventana completa. Es el mejor cuarto de hora.
     ronda 1..n: se densifica la sonrisa hacia +/-15%.
  Cortarlo en cualquier ronda deja un resultado UTIL, no un resultado a medias.

  Expiries: los MENSUALES (3er viernes). Son los que viven meses, asi que un contrato
  cubre cientos de sesiones. Strikes: rejilla de moneyness sobre el spot MEDIANO de la
  ventana que ese expiry cubre, leido de `poly_bars` (local, 0 peticiones). Se toma el
  OTM de cada lado (put debajo del spot, call encima): es la superficie que se usa.

PROPIEDADES
  IDEMPOTENTE  poly_opt_bars tiene PRIMARY KEY(otk, ts) -> INSERT OR IGNORE.
  REANUDABLE   `poly_opt_bf_progress` guarda el estado por contrato; el catalogo de
               contratos se cachea en data/opt_contracts/. Relanzar retoma donde iba
               sin repetir ni peticiones ni filas.
  FAIL-LOUD    un contrato que falla queda 'failed' con el motivo. JAMAS se cuenta como
               "0 filas, todo bien". 'empty' (existio pero nunca cotizo) es un estado
               DISTINTO de 'failed', y ambos se publican en el informe.

BD  trades.db pesa 1,5 GB y hay otros procesos leyendo. busy_timeout=60000, un commit
    por contrato (transaccion de milisegundos). NUNCA VACUUM ni ALTER sobre
    poly_opt_bars: hay features leyendola y el esquema no se toca.

SEÑAL-SOLAMENTE: esto no pone ordenes. Lote fuera de sesion -> Python legitimo.

Uso:
  python3 scripts/poly_backfill_opts.py plan            # que se va a pedir y cuanto cuesta
  python3 scripts/poly_backfill_opts.py run [--rounds 4] [--syms QQQ SPY] [--max-req 400]
  python3 scripts/poly_backfill_opts.py status
  python3 scripts/poly_backfill_opts.py report          # escribe data/opt_backfill_report.json
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_client import (DB_PATH, REPO, Polygon, PolygonError,  # noqa: E402
                         atomic_write, market_days)

os.environ.setdefault("TZ", "America/New_York")
time.tzset()

CONTRACT_CACHE = os.path.join(REPO, "data", "opt_contracts")
REPORT_PATH = os.path.join(REPO, "data", "opt_backfill_report.json")

# Los 8 que ya viven en poly_opt_bars. Fuera de aqui no se toca nada.
SYMS = ["QQQ", "SPY", "NVDA", "MU", "SMH", "AMD", "META", "TSLA"]

# Ventana objetivo. >=60 sesiones es el minimo util; se pide holgura porque un
# contrato puede no haber cotizado los primeros dias de su vida.
WINDOW_START = dt.date(2026, 2, 2)
WINDOW_END = dt.date.today()

# Expiries mensuales (3er viernes) que se van a pedir. El primero cubre el arranque de
# la ventana, el ultimo la cola.
EXPIRY_MONTHS = [(2026, 3), (2026, 4), (2026, 5), (2026, 6),
                 (2026, 7), (2026, 8), (2026, 9)]

# Rondas de moneyness. Cada entrada: (moneyness, right). right None = OTM automatico
# (put por debajo del spot, call por encima). La ronda 0 es la que mas rinde.
ROUNDS = [
    [(0.00, "call")],
    [(-0.05, None), (0.05, None)],
    [(-0.10, None), (0.10, None)],
    [(-0.15, None), (0.15, None)],
    [(0.00, "put"), (-0.025, None), (0.025, None),
     (-0.075, None), (0.075, None), (-0.125, None), (0.125, None)],
]

PAGE = 50000


# --------------------------------------------------------------------- BD
def db(readonly=False):
    if readonly:
        c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
        c.execute("PRAGMA busy_timeout=60000")
        return c
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=60000")
    # poly_opt_bars YA EXISTE con features leyendola: se crea solo si faltara, con el
    # esquema EXACTO. Nunca ALTER, nunca DROP, nunca VACUUM.
    c.execute("""CREATE TABLE IF NOT EXISTS poly_opt_bars(
        otk TEXT, sym TEXT, exp TEXT, strike REAL, right TEXT, ts INTEGER,
        o REAL, h REAL, l REAL, c REAL, v REAL, PRIMARY KEY(otk, ts))""")
    # tabla de progreso PROPIA de este backfill (no toca las ajenas)
    c.execute("""CREATE TABLE IF NOT EXISTS poly_opt_bf_progress(
        otk TEXT PRIMARY KEY, sym TEXT, exp TEXT, strike REAL, right TEXT,
        rnd INTEGER, state TEXT, rows INTEGER, err TEXT, updated REAL)""")
    return c


def mark(c, otk, sym, exp, strike, right, rnd, state, rows, err):
    c.execute("INSERT INTO poly_opt_bf_progress VALUES(?,?,?,?,?,?,?,?,?,?) "
              "ON CONFLICT(otk) DO UPDATE SET state=excluded.state, "
              "rows=excluded.rows, err=excluded.err, updated=excluded.updated",
              (otk, sym, exp, strike, right, rnd, state, rows, err, time.time()))
    c.commit()


def done_set(c):
    """Contratos ya resueltos con exito (done/empty). Los 'failed' se REINTENTAN."""
    return {r[0] for r in c.execute(
        "SELECT otk FROM poly_opt_bf_progress WHERE state IN ('done','empty')")}


# ------------------------------------------------------- spot local (0 peticiones)
def daily_closes(c, sym, d0, d1):
    """Cierres diarios desde poly_bars (1m, ts en MILISEGUNDOS -> /1000 obligatorio;
    olvidarlo devuelve NULL para todo y parece 'no hay datos' sobre 8,9 M de filas).
    Devuelve {fecha_iso: cierre}. Si no hay datos LEVANTA: sin spot no hay rejilla, y
    un spot inventado es exactamente el cero plausible que la casa prohibe."""
    rows = c.execute(
        "SELECT date(ts/1000,'unixepoch','localtime') d, c, ts FROM poly_bars "
        "WHERE sym=? AND ts BETWEEN ? AND ? ORDER BY ts",
        (sym,
         int(dt.datetime.combine(d0, dt.time(0, 0)).timestamp() * 1000),
         int(dt.datetime.combine(d1, dt.time(23, 59)).timestamp() * 1000))).fetchall()
    if not rows:
        raise PolygonError(f"sin barras locales de {sym} en {d0}..{d1}: "
                           f"no hay spot con el que construir la rejilla de strikes")
    out = {}
    for d, close, _ts in rows:
        out[d] = close          # ordenado por ts -> se queda el ultimo del dia
    return out


def ref_spot(c, sym, exp):
    """Spot de referencia de un expiry: MEDIANA de los cierres de la ventana que ese
    contrato puede cubrir. La mediana aguanta un gap sin desplazar la rejilla entera."""
    d0 = max(WINDOW_START, exp - dt.timedelta(days=120))
    d1 = min(exp, WINDOW_END)
    if d1 < d0:
        d0, d1 = WINDOW_START, WINDOW_END
    vals = sorted(daily_closes(c, sym, d0, d1).values())
    return vals[len(vals) // 2]


def third_friday(year, month):
    """Vencimiento mensual: 3er viernes, ADELANTADO al jueves si es festivo de mercado.

    MEDIDO 2026-07-25: el 3er viernes de junio-2026 es el 19, que es Juneteenth. Polygon
    no lista NINGUN contrato con esa fecha porque el vencimiento real es el jueves 18.
    Pedir el 19 devolvia catalogo vacio y se perdia un expiry entero."""
    d = dt.date(year, month, 1)
    fridays = [d + dt.timedelta(days=i) for i in range(31)
               if (d + dt.timedelta(days=i)).month == month
               and (d + dt.timedelta(days=i)).weekday() == 4]
    e = fridays[2]
    while not market_days(e, e):                  # festivo -> dia habil anterior
        e -= dt.timedelta(days=1)
    return e


def expiries():
    return [third_friday(y, m) for y, m in EXPIRY_MONTHS]


# ---------------------------------------------------- catalogo de contratos (cache)
CATALOG_BAND = 0.30      # se pide +/-30% de strikes: el doble de la banda que se usa
MAX_PAGES = 12


def contracts_for(poly, sym, exp, spot):
    """Contratos que EXISTEN para (sym, expiry) dentro de +/-30% del spot, cacheados.

    Se acota por `expiration_date` exacto y por `strike_price.gte/lte`. NO se usa
    `as_of`: esta MEDIDO que Polygon lo ignora (dos as_of distintos -> la misma
    respuesta), y un parametro que parece funcionar y no funciona es peor que un 403.
    La banda de strikes es el DOBLE de la que se llega a pedir (+/-15%), asi que no
    puede recortar nada que se vaya a usar, y evita paginar la cadena entera de SPY.

    Devuelve lista de dicts {ticker, strike, right}. Levanta si la peticion falla:
    devolver [] convertiria "no pude preguntar" en "no existen contratos"."""
    os.makedirs(CONTRACT_CACHE, exist_ok=True)
    path = os.path.join(CONTRACT_CACHE,
                        f"{sym}_{exp:%Y-%m-%d}_b{int(CATALOG_BAND * 100)}.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    # MEDIDO 2026-07-25: `expired` NO es "incluye vencidos", es un FILTRO EXCLUYENTE.
    # expired=true devuelve SOLO vencidos -> con un expiry futuro devolvia lista vacia,
    # que es indistinguible de "no existe". Se elige el filtro segun la fecha.
    expired = "true" if exp < dt.date.today() else "false"
    lo, hi = spot * (1 - CATALOG_BAND), spot * (1 + CATALOG_BAND)
    url = ("https://api.polygon.io/v3/reference/options/contracts"
           f"?underlying_ticker={sym}&expired={expired}&expiration_date={exp:%Y-%m-%d}"
           f"&strike_price.gte={lo:.2f}&strike_price.lte={hi:.2f}&limit=1000")
    out = []
    truncado = False
    for page in poly.paginate(url, max_pages=MAX_PAGES):   # paginate LEVANTA si falla
        for r in page.get("results") or []:
            t, k, ct = r.get("ticker"), r.get("strike_price"), r.get("contract_type")
            if not t or k is None or ct not in ("call", "put"):
                raise PolygonError(f"contrato malformado de Polygon en {sym} {exp}: {r!r}")
            out.append({"ticker": t, "strike": float(k), "right": ct})
        truncado = bool(page.get("next_url"))
    if truncado:
        # se acabaron las paginas y AUN habia next_url. Un catalogo truncado en
        # silencio se ordena por ticker (calls antes que puts): guardarlo perderia
        # todos los puts sin que nadie lo note. Se levanta.
        raise PolygonError(f"catalogo de {sym} {exp} TRUNCADO en {MAX_PAGES} paginas "
                           f"({len(out)} contratos y seguia habiendo next_url)")
    if not out:
        raise PolygonError(f"Polygon no lista NINGUN contrato para {sym} {exp} "
                           f"(no se asume que no existan: se reporta)")
    atomic_write(path, json.dumps(out))
    return out


def pick(cats, spot, moneyness, right):
    """Contrato mas cercano a spot*(1+moneyness) con el `right` pedido.
    right None -> OTM del lado que toque (put debajo, call encima). None si no hay."""
    want = right or ("put" if moneyness < 0 else "call")
    target = spot * (1.0 + moneyness)
    cand = [x for x in cats if x["right"] == want]
    if not cand:
        return None
    return min(cand, key=lambda x: abs(x["strike"] - target))


# ------------------------------------------------------------------ descarga
def parse_agg_rows(otk, sym, exp, strike, right, payload):
    """Payload de /v2/aggs -> filas de poly_opt_bars.

    Una barra malformada LEVANTA. No se rellena con 0: un 0 en o/h/l/c es un precio
    plausible, y un precio plausible falso rompe la inversion de IV rio abajo."""
    res = payload.get("results")
    if res is None:
        return []
    rows = []
    for b in res:
        try:
            rows.append((otk, sym, exp, float(strike), right, int(b["t"]),
                         float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"]),
                         float(b.get("v", 0.0))))
        except (KeyError, TypeError, ValueError) as e:
            raise PolygonError(f"barra malformada de Polygon en {otk}: {e!r}")
    return rows


def download_contract(poly, c, sym, exp, meta, rnd, d0, d1):
    """Baja la vida diaria de un contrato. Devuelve (filas_insertadas, state, err).
    state: 'done' | 'empty' | 'failed'. NUNCA 'done' con 0 filas por un fallo."""
    otk = meta["ticker"]
    url = (f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/1/day/"
           f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}?adjusted=true&sort=asc&limit={PAGE}")
    try:
        d = poly.get(url)
    except PolygonError as e:                       # 401/403 -> no se disfraza de vacio
        mark(c, otk, sym, f"{exp:%Y-%m-%d}", meta["strike"], meta["right"], rnd,
             "failed", 0, str(e))
        return 0, "failed", str(e)
    if d is None:
        err = "peticion abandonada tras reintentos"
        mark(c, otk, sym, f"{exp:%Y-%m-%d}", meta["strike"], meta["right"], rnd,
             "failed", 0, err)
        return 0, "failed", err
    try:
        rows = parse_agg_rows(otk, sym, f"{exp:%Y-%m-%d}", meta["strike"],
                              meta["right"], d)
    except PolygonError as e:
        mark(c, otk, sym, f"{exp:%Y-%m-%d}", meta["strike"], meta["right"], rnd,
             "failed", 0, str(e))
        return 0, "failed", str(e)
    if not rows:
        # el contrato existe en el catalogo pero no cotizo en la ventana. Es un hecho,
        # no un fallo, y se distingue del fallo en el informe.
        mark(c, otk, sym, f"{exp:%Y-%m-%d}", meta["strike"], meta["right"], rnd,
             "empty", 0, None)
        return 0, "empty", None
    before = c.total_changes
    c.executemany("INSERT OR IGNORE INTO poly_opt_bars VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  rows)
    c.commit()                                       # transaccion corta: BD compartida
    ins = c.total_changes - before
    mark(c, otk, sym, f"{exp:%Y-%m-%d}", meta["strike"], meta["right"], rnd,
         "done", len(rows), None)
    return ins, "done", None


# ------------------------------------------------------------------ orquestacion
def run(syms, rounds, max_req):
    c = db()
    poly = Polygon()
    exps = expiries()
    already = done_set(c)
    t0 = time.time()
    tot_new = tot_req = 0
    fails = []
    print(f"BACKFILL poly_opt_bars 1d | {len(syms)} syms x {len(exps)} expiries | "
          f"ventana {WINDOW_START} -> {WINDOW_END}")
    print(f"  expiries: {' '.join(f'{e}' for e in exps)}")
    print(f"  ronda 0 = ATM de todo (lo que mas rinde). Techo {max_req} peticiones.\n",
          flush=True)
    for rnd in range(min(rounds, len(ROUNDS))):
        print(f"--- RONDA {rnd}: {ROUNDS[rnd]}", flush=True)
        for sym in syms:
            for exp in exps:
                if tot_req >= max_req:
                    print(f"\n! techo de {max_req} peticiones alcanzado — REANUDABLE",
                          flush=True)
                    return finish(c, poly, tot_new, tot_req, fails, t0)
                try:
                    spot = ref_spot(c, sym, exp)
                except PolygonError as e:
                    fails.append((f"{sym} {exp}", str(e)))
                    print(f"  ! {sym} {exp}: {e}", flush=True)
                    continue
                cached = os.path.exists(os.path.join(
                    CONTRACT_CACHE,
                    f"{sym}_{exp:%Y-%m-%d}_b{int(CATALOG_BAND * 100)}.json"))
                try:
                    cats = contracts_for(poly, sym, exp, spot)
                except PolygonError as e:
                    fails.append((f"{sym} {exp} catalogo", str(e)))
                    print(f"  ! catalogo {sym} {exp}: {e}", flush=True)
                    continue
                if not cached:
                    # el catalogo puede haber costado VARIAS paginas: el techo se lleva
                    # con el contador del cliente, no con una estimacion optimista
                    tot_req = poly.stats["requests"]
                d0 = WINDOW_START
                d1 = min(exp, WINDOW_END)
                for mny, right in ROUNDS[rnd]:
                    m = pick(cats, spot, mny, right)
                    if m is None or m["ticker"] in already:
                        continue
                    already.add(m["ticker"])
                    ins, state, err = download_contract(poly, c, sym, exp, m, rnd,
                                                        d0, d1)
                    tot_req = poly.stats["requests"]
                    tot_new += ins
                    if state == "failed":
                        fails.append((m["ticker"], err))
                        print(f"  ! {m['ticker']}: {err}", flush=True)
                    else:
                        print(f"  {m['ticker']:26s} spot~{spot:8.2f} k={m['strike']:8.2f} "
                              f"{state:5s} +{ins:4d}  ({tot_req} pet., "
                              f"{(time.time() - t0) / 60:.0f} min)", flush=True)
                    if tot_req >= max_req:
                        break
    return finish(c, poly, tot_new, tot_req, fails, t0)


def finish(c, poly, tot_new, tot_req, fails, t0):
    print(f"\n-> {tot_new} filas nuevas, {tot_req} peticiones, "
          f"{(time.time() - t0) / 60:.1f} min")
    print(f"-> {poly.report()}")
    if fails:
        print(f"-> FALLOS ({len(fails)}) — quedan 'failed' y se REINTENTAN al relanzar:")
        for k, w in fails[:20]:
            print(f"     {k}: {w}")
    else:
        print("-> sin fallos")
    write_report(c)
    return tot_new, fails


# ------------------------------------------------------------------ informe
def collect(c, syms=None):
    syms = syms or SYMS
    out = {}
    for sym in syms:
        r = c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT otk), "
            "COUNT(DISTINCT date(ts/1000,'unixepoch')), "
            "MIN(date(ts/1000,'unixepoch')), MAX(date(ts/1000,'unixepoch')) "
            "FROM poly_opt_bars WHERE sym=?", (sym,)).fetchone()
        rows, contracts, sess, d0, d1 = r if r else (0, 0, 0, None, None)
        out[sym] = {"contracts": contracts or 0, "rows": rows or 0,
                    "sessions": sess or 0, "first_date": d0, "last_date": d1}
    return out


def write_report(c):
    syms = collect(c)
    st = dict(c.execute("SELECT state, COUNT(*) FROM poly_opt_bf_progress "
                        "GROUP BY state").fetchall())
    failed = [{"otk": k, "err": e} for k, e in c.execute(
        "SELECT otk, err FROM poly_opt_bf_progress WHERE state='failed' "
        "ORDER BY otk LIMIT 200")]
    dates = [v["first_date"] for v in syms.values() if v["first_date"]]
    dates2 = [v["last_date"] for v in syms.values() if v["last_date"]]
    sess = [v["sessions"] for v in syms.values()]
    rep = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "syms": syms,
        "span_real": {
            "first_date": min(dates) if dates else None,
            "last_date": max(dates2) if dates2 else None,
            "sessions_min": min(sess) if sess else 0,
            "sessions_max": max(sess) if sess else 0,
            "target_sessions": 60,
            "target_met": bool(sess) and min(sess) >= 60,
        },
        "contract_states": st,
        "failed": failed,
        "notas": [
            "MEDIDO: /v2/aggs/ticker/O:<c>/range/1/day devuelve la vida entera del "
            "contrato en una peticion. Da v vw o c h l t n.",
            "MEDIDO: NO hay OI ni griegas historicas en este plan. La IV se reconstruye "
            "por biseccion desde el precio (gex_core.implied_vol); el OI historico NO "
            "existe y no se aproxima.",
            "MEDIDO: as_of en /v3/reference/options/contracts se IGNORA (dos fechas "
            "distintas -> misma respuesta). Aqui se acota por expiration_date.",
            "MEDIDO: /v2/aggs/grouped/.../market/options/{fecha} -> HTTP 400 (no existe).",
            "MEDIDO: /v3/trades/O: y /v3/quotes/O: -> 403 NOT_AUTHORIZED.",
            "Barras DIARIAS: ts a medianoche ET. Las barras de 5m preexistentes no "
            "colisionan (PK otk,ts) y siguen ahi: no se borro ni una fila.",
            "Solo strikes OTM en rejilla de moneyness +/-15% sobre el spot mediano de "
            "la ventana de cada expiry, leido de poly_bars (0 peticiones).",
            "'empty' = el contrato existe pero no cotizo en la ventana. NO es un fallo "
            "y no se cuenta como exito con 0 filas: es su propio estado.",
        ],
    }
    atomic_write(REPORT_PATH, json.dumps(rep, indent=2))
    print(f"-> informe: {REPORT_PATH}")
    return rep


def status(syms):
    c = db(readonly=True)
    print(f"{'sym':6s} {'sesiones':>9s} {'contratos':>10s} {'filas':>9s} "
          f"{'desde':>11s} {'hasta':>11s}")
    for sym, v in collect(c, syms).items():
        print(f"{sym:6s} {v['sessions']:9d} {v['contracts']:10d} {v['rows']:9d} "
              f"{str(v['first_date']):>11s} {str(v['last_date']):>11s}")
    try:
        st = dict(c.execute("SELECT state, COUNT(*) FROM poly_opt_bf_progress "
                            "GROUP BY state").fetchall())
        print(f"contratos por estado: {st}")
    except sqlite3.OperationalError:
        print("contratos por estado: (sin arrancar)")


def plan(syms):
    """Que se va a pedir y cuanto cuesta, SIN gastar una sola peticion de datos."""
    c = db(readonly=True)
    exps = expiries()
    n_ref = sum(1 for s in syms for e in exps
                if not os.path.exists(os.path.join(CONTRACT_CACHE, f"{s}_{e:%Y-%m-%d}.json")))
    print(f"ventana {WINDOW_START} -> {WINDOW_END} "
          f"({len(market_days(WINDOW_START, WINDOW_END))} sesiones NYSE)")
    print(f"expiries mensuales: {' '.join(str(e) for e in exps)}")
    for sym in syms:
        try:
            sp = [f"{ref_spot(c, sym, e):.0f}" for e in exps]
            print(f"  {sym:6s} spot mediano por expiry: {' '.join(sp)}")
        except PolygonError as e:
            print(f"  {sym:6s} ! {e}")
    acc = n_ref
    for i, r in enumerate(ROUNDS):
        acc += len(syms) * len(exps) * len(r)
        print(f"  ronda {i}: +{len(syms) * len(exps) * len(r):4d} peticiones "
              f"-> acumulado {acc:4d}  (~{acc * 12.4 / 60:.0f} min a 5 pet./min)")


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else "status"
    syms = SYMS
    if "--syms" in a:
        i = a.index("--syms") + 1
        syms = [s.upper() for s in a[i:] if not s.startswith("--")]

    def opt(flag, default, cast=str):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    if cmd == "run":
        run(syms, opt("--rounds", len(ROUNDS), int), opt("--max-req", 10000, int))
    elif cmd == "status":
        status(syms)
    elif cmd == "plan":
        plan(syms)
    elif cmd == "report":
        write_report(db(readonly=True))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
