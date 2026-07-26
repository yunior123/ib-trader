#!/usr/bin/env python3
"""options_enrich.py — overlay de opciones (M4, V6_SPEC §5). SOLO LECTURA.

Ley suprema (Yunior 2026-07-16): flota SEÑAL-SOLAMENTE. Este proceso se
conecta a TWS con readonly=True y JAMAS coloca/modifica/cancela ordenes.
Cero colocacion de ordenes. Solo lee: chain, greeks, OI, volumen, spread.

Que hace:
  - tail -F del mirror del dia ~/ib-trader/data/trading-signals/YYYY-MM-DD.txt
    (rota a medianoche). Trigger: linea cuyo titulo (campo 2, split ' | ')
    sea EXACTAMENTE "<SYM>: BUY" o "<SYM>: SELL".
  - por señal: chain SMART -> expiry mas cercano (DTE 0-2, si no el minimo
    disponible anotado), strikes ±5% del spot, right C si BUY / P si SELL,
    reqMktData genericTickList '100,101,106', elige strike con |delta| mas
    cercano a 0.55 dentro de [0.40, 0.70].
  - gates: 0.40<=|delta|<=0.70, spread<=OPT_SPREAD_MAX (3%), vol>=500,
    OI>=1000 (OI<100 = NO-APTO duro), warning IV>0.90. Ventana horaria
    9:35-15:00 ET; fuera => NO-APTO-HORA.
  - output (append O_APPEND): MISMO mirror del dia + data/options_enrich.log
    + <sym>_signals.log del ticker. Formato EXACTO (contrato §5):
    HH:MM:SS | NVDA: OPT | C 2026-07-17 124 | delta 0.56 gamma 0.041 theta -0.32 IV 43% | OI 5210 vol 2140 spread 1.8% | APTO same-day

Modos:
  options_enrich.py                  daemon (tail del mirror)
  options_enrich.py --test SYM [BUY|SELL]   enriquece una señal sintetica YA
                                     (stdout + log; mirror solo si OPT_TEST_MIRROR=1)

Python permitido SOLO porque ib_insync lo exige (greeks); todo lo demas de
la flota es C++.

Env: OPT_PORT (7496), OPT_CLIENT_ID (88 — 83/84 bridges, 86 korea, 87 tool
one-shot), OPT_SPREAD_MAX (3.0), OPT_VOL_MIN (500), OPT_OI_MIN (1000),
OPT_DEDUP_S (1800), OPT_SLEEP_MKT (4.0).
"""
import os
import re
import sys
import time
import math
from datetime import datetime, date

ROOT = "/Users/yuniorrodriguezosorio/ib-trader"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

try:
    from ib_insync import IB, Stock, Option  # noqa: F401
except ImportError:  # API identica
    from ib_async import IB, Stock, Option  # noqa: F401

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # Toronto == ET; fallback a hora local
    ET = None

HOST = "127.0.0.1"
import sys as _s2; _s2.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ib_mode                                    # fuente única paper/live (sin hardcode)
PORT = int(os.environ.get("OPT_PORT") or ib_mode.get_port())   # env OPT_PORT gana; si no, data/ib_mode.txt
CLIENT_ID = int(os.environ.get("OPT_CLIENT_ID", "88"))
SPREAD_MAX = float(os.environ.get("OPT_SPREAD_MAX", "3.0"))   # % sobre mid
VOL_MIN = int(os.environ.get("OPT_VOL_MIN", "500"))
OI_MIN = int(os.environ.get("OPT_OI_MIN", "1000"))
DEDUP_S = int(os.environ.get("OPT_DEDUP_S", "1800"))          # 30 min
SLEEP_MKT = float(os.environ.get("OPT_SLEEP_MKT", "4.0"))
MAX_STRIKES = int(os.environ.get("OPT_MAX_STRIKES", "16"))    # lineas mktdata

LOG_PATH = os.path.join(ROOT, "data", "options_enrich.log")
MIRROR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")

SYM_MAP = {"DRAM": "MU"}                                       # señal -> subyacente US
SKIP = {"KOSPI", "SAMSUNG", "SKHYNIX", "SKHY"}                 # sin opciones US
# titulos que JAMAS disparan enriquecimiento (ademas del regex estricto)
IGNORE_TOKENS = ("(STOP)", "WARMUP", "OPT", "ALARMA", "TERREMOTO", "SIN DATOS")
TITLE_RE = re.compile(r"^([A-Z]+): (BUY|SELL)$")


def now_et():
    return datetime.now(ET) if ET else datetime.now()


def log(msg):
    line = "%s | %s" % (now_et().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        fd = os.open(LOG_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        os.write(fd, (line + "\n").encode())
        os.close(fd)
    except OSError:
        pass


def append_atomic(path, line):
    """append O_APPEND de UNA linea (<PIPE_BUF, atomico) — como fleet_notify.h."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        os.write(fd, (line + "\n").encode())
        os.close(fd)
        return True
    except OSError:
        return False


def mirror_path(d=None):
    d = d or now_et().date()
    return os.path.join(MIRROR_DIR, "%04d-%02d-%02d.txt" % (d.year, d.month, d.day))


def in_hours(dt):
    """ventana de veredicto same-day 9:35-15:00 ET (ultimos 30-60 min = peor
    periodo risk-adjusted en 0DTE)."""
    m = dt.hour * 60 + dt.minute
    return 9 * 60 + 35 <= m <= 15 * 60


def fnum(x, default=float("nan")):
    try:
        v = float(x)
        return v if not math.isnan(v) else default
    except (TypeError, ValueError):
        return default


def fmt_strike(k):
    return ("%d" % round(k)) if abs(k - round(k)) < 1e-9 else ("%g" % k)


# ---------------------------------------------------------------- enriquecer
def enrich(ib, sym, side):
    """Devuelve la linea OPT (sin timestamp) o None si el simbolo se salta.
    Nunca lanza ordenes: solo reqTickers/reqSecDefOptParams/reqMktData."""
    sym = sym.upper()
    if sym in SKIP:
        log("%s: skip opciones (sin opciones US)" % sym)
        return None
    usym = SYM_MAP.get(sym, sym)
    right = "C" if side == "BUY" else "P"
    notes = []                       # anotaciones no fatales (DTE>2, IV alta)

    stock = Stock(usym, "SMART", "USD")
    ib.qualifyContracts(stock)
    (st,) = ib.reqTickers(stock)
    spot = fnum(st.marketPrice())
    if math.isnan(spot) or spot <= 0:
        spot = fnum(st.close)
    if math.isnan(spot) or spot <= 0:
        return "%s: OPT | %s - - | sin spot | - | NO-APTO (sin-precio-subyacente)" % (sym, right)

    chains = ib.reqSecDefOptParams(usym, "", stock.secType, stock.conId)
    chain = next((c for c in chains if c.tradingClass == usym and c.exchange == "SMART"), None)
    if chain is None:
        chain = next((c for c in chains if c.exchange == "SMART"), None)
    if chain is None or not chain.expirations:
        return "%s: OPT | %s - - | sin chain | - | NO-APTO (sin-chain)" % (sym, right)

    today = now_et().date()
    exps = sorted(chain.expirations)

    def dte(e):
        return (date(int(e[:4]), int(e[4:6]), int(e[6:8])) - today).days

    exps = [e for e in exps if dte(e) >= 0]
    if not exps:
        return "%s: OPT | %s - - | sin expiry | - | NO-APTO (sin-expiry)" % (sym, right)
    expiry = exps[0]                 # el mas cercano; ideal DTE 0-2
    if dte(expiry) > 2:
        notes.append("DTE-%d" % dte(expiry))

    strikes = sorted((k for k in chain.strikes if 0.95 * spot <= k <= 1.05 * spot),
                     key=lambda k: abs(k - spot))[:MAX_STRIKES]
    if not strikes:
        return "%s: OPT | %s %s - | sin strikes ±5%% | - | NO-APTO (sin-strikes)" % (
            sym, right, "%s-%s-%s" % (expiry[:4], expiry[4:6], expiry[6:8]))

    opts = [Option(usym, expiry, k, right, "SMART", tradingClass=chain.tradingClass)
            for k in strikes]
    opts = [o for o in ib.qualifyContracts(*opts) if o.conId]
    tickers = [ib.reqMktData(o, "100,101,106", False, False) for o in opts]
    ib.sleep(SLEEP_MKT)              # greeks/OI/vol tardan unos ticks

    def delta_of(t):
        g = t.modelGreeks
        return fnum(g.delta) if g else float("nan")

    # strike con |delta| mas cercano a 0.55 dentro de [0.40, 0.70]
    band = [t for t in tickers if not math.isnan(delta_of(t))
            and 0.40 <= abs(delta_of(t)) <= 0.70]
    pool = band or [t for t in tickers if not math.isnan(delta_of(t))]
    for t in tickers:                # limpiar TODAS las suscripciones
        try:
            ib.cancelMktData(t.contract)
        except Exception:
            pass
    if not pool:
        # sin greeks live: mercado de opciones cerrado O falta sub OPRA
        # (error 354 'not subscribed' — delayed PROHIBIDO por ley, no se usa)
        return "%s: OPT | %s %s ~%s | sin greeks live (opciones cerradas o falta sub OPRA) | - | NO-APTO (sin-greeks)" % (
            sym, right, "%s-%s-%s" % (expiry[:4], expiry[4:6], expiry[6:8]), fmt_strike(strikes[0]))
    best = min(pool, key=lambda t: abs(abs(delta_of(t)) - 0.55))

    g = best.modelGreeks
    delta = fnum(g.delta)
    gamma = fnum(g.gamma)
    theta = fnum(g.theta)
    iv = fnum(g.impliedVol)
    bid, ask = fnum(best.bid), fnum(best.ask)
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else float("nan")
    spread_pct = (ask - bid) / mid * 100.0 if not math.isnan(mid) and mid > 0 else float("nan")
    vol = fnum(best.volume, 0)
    vol = 0 if math.isnan(vol) else int(vol)
    oi_raw = best.callOpenInterest if right == "C" else best.putOpenInterest
    oi = fnum(oi_raw, 0)
    oi = 0 if math.isnan(oi) else int(oi)

    # ---- gates (§5 paso 5) — la PRIMERA razon fallida es la principal
    fails = []
    if oi < 100:
        fails.append("OI %d < 100" % oi)             # NO-APTO duro
    if not (0.40 <= abs(delta) <= 0.70):
        fails.append("delta %.2f fuera 0.40-0.70" % delta)
    if math.isnan(spread_pct):
        fails.append("sin bid/ask")
    elif spread_pct > SPREAD_MAX:
        fails.append("spread %.1f%% > %g%%" % (spread_pct, SPREAD_MAX))
    if vol < VOL_MIN:
        fails.append("vol %d < %d" % (vol, VOL_MIN))
    if oi < OI_MIN and oi >= 100:
        fails.append("OI %d < %d" % (oi, OI_MIN))
    if not math.isnan(iv) and iv > 0.90:
        notes.append("IV-alta")                       # warning, no fatal
    hour_ok = in_hours(now_et())

    if not hour_ok:
        verdict = "NO-APTO-HORA"
    elif fails:
        verdict = "NO-APTO (%s)" % fails[0]
    else:
        verdict = "APTO same-day"
    if notes:
        verdict += " [" + "+".join(notes) + "]"

    exp_h = "%s-%s-%s" % (expiry[:4], expiry[4:6], expiry[6:8])
    return ("%s: OPT | %s %s %s | delta %.2f gamma %.3f theta %.2f IV %.0f%% | "
            "OI %d vol %d spread %s | %s") % (
        sym, right, exp_h, fmt_strike(best.contract.strike),
        delta, gamma, theta, iv * 100.0 if not math.isnan(iv) else float("nan"),
        oi, vol,
        ("%.1f%%" % spread_pct) if not math.isnan(spread_pct) else "n/a",
        verdict)


def emit(body, to_mirror=True, sym=None):
    """timestamp + append al mirror del dia, data/options_enrich.log y
    <sym>_signals.log. body ya viene como 'SYM: OPT | ...'."""
    line = "%s | %s" % (now_et().strftime("%H:%M:%S"), body)
    print(line, flush=True)
    append_atomic(LOG_PATH, line)
    if to_mirror:
        os.makedirs(MIRROR_DIR, exist_ok=True)
        append_atomic(mirror_path(), line)
    if sym:
        slog = os.path.join(ROOT, "%s_signals.log" % sym.lower())
        if os.path.exists(slog):
            append_atomic(slog, line)


# ---------------------------------------------------------------- conexion
def connect_retry(ib):
    while not ib.isConnected():
        try:
            ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=10)
            ib.reqMarketDataType(1)   # LIVE — jamas delayed (ley)
            log("conectado TWS %s:%d clientId=%d readonly=True" % (HOST, PORT, CLIENT_ID))
        except Exception as e:
            log("TWS no disponible (%s) — reintento en 60 s" % e)
            ib.disconnect()
            time.sleep(60)
    return ib


def parse_title(raw_line):
    """-> (sym, side) o None. Campo 2 de 'HH:MM:SS | TITULO | MSG'."""
    parts = raw_line.rstrip("\n").split(" | ")
    if len(parts) < 2:
        return None
    title = parts[1].strip()
    if any(tok in title for tok in IGNORE_TOKENS):
        return None
    m = TITLE_RE.match(title)
    return (m.group(1), m.group(2)) if m else None


def daemon():
    ib = IB()
    connect_retry(ib)
    last_fire = {}                    # (sym, side) -> epoch
    cur_day = now_et().date()
    path = mirror_path(cur_day)
    f = None
    pos = None
    log("daemon: tail de %s" % path)
    while True:
        d = now_et().date()
        if d != cur_day:              # rotacion a medianoche
            cur_day = d
            path = mirror_path(cur_day)
            if f:
                f.close()
            f, pos = None, 0          # archivo nuevo: leer desde 0
            log("rotacion: tail de %s" % path)
        if f is None:
            if os.path.exists(path):
                f = open(path, "r", errors="replace")
                if pos is None:
                    f.seek(0, os.SEEK_END)   # arranque: solo señales nuevas
                else:
                    f.seek(pos)
            else:
                ib.sleep(2)
                continue
        line = f.readline()
        if not line:
            ib.sleep(1)               # sleep de ib_insync: mantiene el socket vivo
            continue
        if not line.endswith("\n"):   # linea a medio escribir: re-leer
            f.seek(f.tell() - len(line))
            ib.sleep(0.2)
            continue
        sig = parse_title(line)
        if not sig:
            continue
        sym, side = sig
        now = time.time()
        if now - last_fire.get((sym, side), 0) < DEDUP_S:
            continue                  # dedupe 30 min por (SYM, lado)
        last_fire[(sym, side)] = now
        if not ib.isConnected():
            connect_retry(ib)
        try:
            body = enrich(ib, sym, side)
        except Exception as e:
            log("%s %s: error enriqueciendo (%s)" % (sym, side, e))
            if not ib.isConnected():
                connect_retry(ib)
            continue
        if body:
            emit(body, to_mirror=True, sym=sym)


def test_mode(sym, side):
    ib = IB()
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=True, timeout=10)
    except Exception as e:
        log("TEST: TWS no disponible en %s:%d (%s)" % (HOST, PORT, e))
        sys.exit(1)
    ib.reqMarketDataType(1)
    log("TEST %s %s (señal sintetica, readonly)" % (sym, side))
    try:
        body = enrich(ib, sym, side)
    finally:
        ib.disconnect()
    if body:
        emit(body, to_mirror=os.environ.get("OPT_TEST_MIRROR", "0") == "1", sym=sym)
    else:
        log("TEST %s: sin salida (simbolo sin opciones US)" % sym)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--test":
        test_mode(sys.argv[2].upper(),
                  sys.argv[3].upper() if len(sys.argv) > 3 else "BUY")
    else:
        daemon()
