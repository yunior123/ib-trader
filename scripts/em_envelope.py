#!/usr/bin/env python3
"""em_envelope.py — OLA 1 feature #10: LA VALLA DEL DIA, solo la mitad determinista.

QUE ARREGLA: el `em` que publica gex_core es `spot·iv_atm·sqrt(T)` con un conteo de dias
que convierte en silencio un nivel de VIERNES en una banda de 1 dia en vez de abarcar hasta
el LUNES, y direction_view apunta felizmente a niveles fuera de cualquier rango plausible
del dia.

MATEMATICA (pasos del doc, con una desviacion declarada abajo):
  1. em_straddle = 0.8 · (call_mid + put_mid) en el strike mas cercano al spot del expiry
     frontal, capturado A LAS 15:55 ET O ANTES. A las 16:16 el bid/ask ya es -1.00
     (verificado en las cadenas reales), asi que si la foto viva no tiene cotizaciones se
     busca la ULTIMA foto archivada del dia con cotizaciones y HHMM <= 1555.
  2. SPAN CONSCIENTE DEL CALENDARIO: span_trading_days = dias de MERCADO del snapshot al
     cierre de la sesion objetivo, con calendar_days publicado al lado (viernes->lunes = 1
     dia de mercado, 3 de calendario). Festivos hasta 2027 en tabla; si se pide una fecha
     fuera de la tabla LEVANTA en vez de asumir que no hay festivos.
  3. hi = S·exp(+em_pct) ; lo = S·exp(-em_pct)
  4. invalidacion por earnings dentro del span.
  5. confluencia con muro cuando |hi - call_wall| <= 0.0015·S (o lo vs put_wall).

DESVIACION DECLARADA del doc: el doc hace em_pct = (em_straddle/S)·sqrt(span_trading_days),
que es correcto solo si el expiry frontal ES la sesion objetivo. Con el frontal a 2 dias y
un span de 1, ese straddle abarca MAS tiempo del que se quiere vallar y la valla sale ancha
— exactamente el error de conteo de dias que la feature venia a matar. Aqui se escala en
tiempo: em_pct = (em_straddle/S)·sqrt(span_trading_days / exp_span_trading_days), y se
publican los dos spans + `scaled_from_exp` para que sea auditable. Si span == exp_span el
resultado es identico al del doc.

LO QUE NO SE HACE Y POR QUE (mitad NO determinista, ELIMINADA):
  - k_u/k_d empiricos y percentiles condicionados de cobertura: exigen >=120 sym-sesiones
    (el doc pide ~250 para los percentiles) y hoy poly_bars tiene 21 dias. `coverage_hist`
    sale como null y NO se publica ninguna probabilidad de contencion. Cuando haya sesiones
    se mide con Wilson y se publica la cobertura LOGRADA, no la deseada.
  - vrp_ratio para cambiar de vehiculo: un ratio no medido no cambia una regla de trading.

TAMPOCO recorta nada por su cuenta: escribe data/em_<sym>.json y punto. El clamp de
direction_view.target y el borrado de lineas del chart son de otros dueños (chart_levels.py
y direction_view.py) — aqui solo se publica la valla con su procedencia.

DECISION RULE (doctrina, para quien lea el json): jamas apuntar mas alla de em_hi/em_lo. Un
toque de em_hi POR ENCIMA del call wall es AGOTAMIENTO, no ruptura -> fade o cobrar, jamas
perseguir; eso mas un %B extremo es la confluencia de fade mas fuerte que podemos afirmar.
Con invalid_reason puesto, no se opera la valla.

Uso:
  ./venv/bin/python scripts/em_envelope.py --all
  ./venv/bin/python scripts/em_envelope.py --sym QQQ --print
  ./venv/bin/python scripts/em_envelope.py --sym QQQ --date 2026-07-24

SEÑAL-SOLAMENTE: lee cadenas y niveles, escribe json. Cero red, cero ordenes.
"""
import argparse
import datetime as dt
import glob
import importlib.util
import json
import math
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)


def _sibling(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CUBE = _sibling("chain_cube_archive")          # lector unico de cadenas (feature #16)

STRADDLE_K = 0.8                # el 0.8 del straddle-mid de MenthorQ
CONFLUENCE_TOL = 0.0015         # 15 bps del spot
SNAP_CUTOFF_HHMM = 1555         # a partir de aqui el bid/ask ya viene -1.00
TRADING_DAYS_YEAR = 252.0

# Festivos de mercado US. La tabla TERMINA en 2027 a proposito: pedir una fecha mas alla
# LEVANTA en vez de asumir "no hay festivos" (asumirlo es fabricar un dia de mercado).
HOLIDAYS = set("""
2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03
2026-09-07 2026-11-26 2026-12-25
2027-01-01 2027-01-18 2027-02-15 2027-03-26 2027-05-31 2027-06-18 2027-07-05
2027-09-06 2027-11-25 2027-12-24
""".split())
HOLIDAY_TABLE_LAST = dt.date(2027, 12, 31)


def is_market_day(d):
    if d > HOLIDAY_TABLE_LAST:
        raise ValueError("tabla de festivos agotada en %s: añade el año antes de usar %s"
                         % (HOLIDAY_TABLE_LAST, d))
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def next_market_day(d):
    d = d + dt.timedelta(days=1)
    while not is_market_day(d):
        d = d + dt.timedelta(days=1)
    return d


def market_days_between(d0, d1):
    """Sesiones de mercado desde d0 (excluida) hasta d1 (incluida). d1<=d0 -> 0."""
    if d1 <= d0:
        return 0
    n = 0
    d = d0
    while d < d1:
        d = d + dt.timedelta(days=1)
        if is_market_day(d):
            n += 1
    return n


def target_session(snap_epoch):
    """La sesion que la valla debe abarcar: la de HOY si el snapshot es de un dia de mercado
    antes del cierre; si no, la siguiente sesion."""
    lt = time.localtime(snap_epoch)
    d = dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)
    before_close = (lt.tm_hour * 60 + lt.tm_min) < 16 * 60
    if is_market_day(d) and before_close:
        return d
    return next_market_day(d)


def spans(snap_epoch, target, exp_date):
    """(span_trading_days, calendar_days, exp_span_trading_days)."""
    lt = time.localtime(snap_epoch)
    d0 = dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday)
    span = max(market_days_between(d0, target), 1) if target != d0 else 1
    cal = max((target - d0).days, 0) or 1
    exp_span = max(market_days_between(d0, exp_date), 1) if exp_date != d0 else 1
    return span, cal, exp_span


# ------------------------------------------------------------------ cadenas

def _hhmm_of(path):
    base = os.path.basename(path)
    for part in base.replace(".txt", "").split("_")[::-1]:
        if part.isdigit() and len(part) in (2, 4):
            return int(part) * 100 if len(part) == 2 else int(part)
    return None


LOOKBACK_DAYS = 5               # cuantos dias de calendario se retrocede buscando cotizaciones


def quote_snapshot(sym, date=None):
    """La mejor foto CON COTIZACIONES: la viva si las tiene, si no la ultima archivada con
    HHMM <= 15:55. Si el dia pedido no tiene ninguna (fin de semana, festivo, foto de las
    16:16 con todo a -1.00) se retrocede hasta LOOKBACK_DAYS dias: la foto del VIERNES a las
    15:55 es precisamente la valla legitima del LUNES, que es el caso que el doc persigue.
    La antiguedad se publica (snap_date / snap_age_market_days) y la regla de rancidez la
    aplica envelope(). Devuelve (ChainSnap, origen) o (None, motivo)."""
    if date is None:
        live = CUBE.latest_chain(sym)
        if live:
            try:
                snap = CUBE.read_chain(live)
                if snap.meta["n_with_quotes"] > 0:
                    return snap, "live"
            except (ValueError, OSError):
                pass
        d0 = dt.date.today()
        for back in range(0, LOOKBACK_DAYS + 1):
            d = (d0 - dt.timedelta(days=back)).isoformat()
            snap, origin = _archived_quote_snapshot(sym, d)
            if snap is not None:
                return snap, origin
        return None, "sin_cotizaciones"
    return _archived_quote_snapshot(sym, date)


def _archived_quote_snapshot(sym, date):
    loose, bundles = CUBE.day_snapshot_paths(date, sym)
    best = None
    for p in loose:
        hh = _hhmm_of(p)
        if hh is None or hh > SNAP_CUTOFF_HHMM:
            continue
        try:
            snap = CUBE.read_chain(p)
        except (ValueError, OSError):
            continue
        if snap.meta["n_with_quotes"] > 0 and (best is None or snap.meta["ts"] > best.meta["ts"]):
            best = snap
    for p in bundles:
        try:
            snaps = CUBE.read_bundle(p)
        except (ValueError, OSError):
            continue
        for snap in snaps:
            lt = time.localtime(snap.meta["ts"] or 0)
            if lt.tm_hour * 100 + lt.tm_min > SNAP_CUTOFF_HHMM:
                continue
            if snap.meta["n_with_quotes"] > 0 and (best is None or snap.meta["ts"] > best.meta["ts"]):
                best = snap
    if best is not None:
        return best, "archivo<=1555 %s" % date
    return None, "sin_cotizaciones"


def front_expiry(rows, target):
    """El primer expiry que CUBRE la sesion objetivo (exp >= target).

    Ojo con el error que esto evita (cazado en la corrida real del 2026-07-25): vallar el
    LUNES con el straddle 0DTE del VIERNES a las 15:55 da un em de 0,11% — es una opcion a
    5 minutos de expirar, no el movimiento de una sesion. El expiry tiene que llegar al menos
    hasta el dia que se quiere vallar.
    """
    tgt = int("%04d%02d%02d" % (target.year, target.month, target.day))
    exps = sorted(set(r.exp for r in rows))
    for e in exps:
        if e >= tgt:
            return e
    return None


def atm_straddle(rows, exp, spot):
    """(strike, call_mid, put_mid) del strike mas cercano al spot con las DOS patas
    cotizadas. None si no hay ninguna: jamas se completa una pata que falta."""
    by_strike = {}
    for r in rows:
        if r.exp != exp or r.bid is None or r.ask is None or r.ask <= 0:
            continue
        mid = (r.bid + r.ask) / 2.0
        if mid <= 0:
            continue
        by_strike.setdefault(r.strike, {})[r.right] = mid
    cands = [(abs(k - spot), k) for k, v in by_strike.items() if "C" in v and "P" in v]
    if not cands:
        return None
    _, k = min(cands)
    return (k, by_strike[k]["C"], by_strike[k]["P"])


def iv_atm_from(rows, exp, spot):
    """IV del contrato mas cercano al spot con IV real. None si no hay."""
    cands = [(abs(r.strike - spot), r.iv) for r in rows
             if r.exp == exp and r.iv is not None and r.iv > 0]
    if not cands:
        return None
    return min(cands)[1]


def levels_of(sym):
    p = os.path.join("charts", "data", "levels_%s.json" % sym.lower())
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def earnings_within(sym, d0, d1):
    """(invalid, src). Hoy NO hay fuente de earnings en el repo (finviz_scan no deja json de
    fechas): se declara src=None y `earnings_checked=False`. Jamas se afirma "no hay
    earnings" sin haberlo mirado."""
    for cand in ("data/earnings.json", "data/finviz_earnings.json", "data/catalysts.json"):
        if os.path.exists(cand):
            try:
                with open(cand) as f:
                    obj = json.load(f)
            except (OSError, ValueError):
                continue
            e = (obj.get(sym.upper()) or {}) if isinstance(obj, dict) else {}
            ed = e.get("earnings_date") or e.get("date")
            if ed:
                try:
                    d = dt.date.fromisoformat(str(ed)[:10])
                except ValueError:
                    continue
                return (d0 <= d <= d1), cand
    return None, None


def envelope(sym, date=None, now=None):
    """Calcula la valla. Devuelve el dict que se publica; None NUNCA se sustituye por 0."""
    now = now or time.time()
    out = {"sym": sym.upper(), "asof": int(now), "em_src": None, "em_straddle": None,
           "em_straddle_pct": None, "em_pct": None, "em_hi": None, "em_lo": None,
           "spot": None, "exp": None, "atm_strike": None,
           "span_days": None, "calendar_days": None, "exp_span_days": None,
           "scaled_from_exp": False, "snap_ts": None, "snap_origin": None,
           "invalid_reason": None, "earnings_checked": False, "earnings_src": None,
           "confluence": None, "coverage_hist": None,
           "nota": "coverage_hist=null: los percentiles condicionados piden ~250 sesiones y "
                   "poly_bars tiene 21. No se publica probabilidad de contencion."}
    snap, origin = quote_snapshot(sym, date)
    lv = levels_of(sym)
    rows = []
    if snap is not None:
        rows = snap.rows
        out["snap_ts"] = snap.meta.get("ts")
        out["snap_origin"] = origin
        spot = snap.meta.get("spot")
    else:
        # sin cotizaciones en ningun sitio (tipico fuera de RTH: bid/ask = -1.00): la cadena
        # viva sigue sirviendo para el spot, el expiry y la ruta IV
        spot = None
        live = CUBE.latest_chain(sym)
        if live:
            try:
                s2 = CUBE.read_chain(live)
                rows = s2.rows
                spot = s2.meta.get("spot")
                out["snap_ts"] = s2.meta.get("ts")
                out["snap_origin"] = "live_sin_cotizaciones"
            except (ValueError, OSError):
                rows = []
    if (spot is None or spot <= 0) and lv:
        spot = lv.get("spot")
    if spot is None or spot <= 0:
        out["invalid_reason"] = "sin_spot"
        return out
    out["spot"] = spot
    if not rows:
        out["invalid_reason"] = "sin_cadena"
        return out
    # la sesion a vallar la fija AHORA (no el snapshot): la foto del viernes 15:55 valla el LUNES
    target = target_session(now)
    exp = front_expiry(rows, target)
    if exp is None:
        out["invalid_reason"] = "sin_expiry_que_cubra_la_sesion"
        return out
    out["exp"] = exp
    exp_date = dt.date(exp // 10000, (exp // 100) % 100, exp % 100)
    span, cal, exp_span = spans(out["snap_ts"] or now, target, exp_date)
    out["span_days"], out["calendar_days"], out["exp_span_days"] = span, cal, exp_span
    out["target_session"] = target.isoformat()
    snap_day = dt.date.fromtimestamp(out["snap_ts"] or now)
    out["snap_date"] = snap_day.isoformat()
    out["snap_age_market_days"] = market_days_between(snap_day, target)
    if out["snap_age_market_days"] > 1:
        # viernes 15:55 -> lunes es 1 sesion: legitimo. Mas de una sesion de distancia y la
        # valla ya no es de hoy: se publica pero marcada, y la doctrina prohibe operarla.
        out["invalid_reason"] = "snapshot_viejo"

    st = atm_straddle(rows, exp, spot)
    if st:
        k, cmid, pmid = st
        em_str = STRADDLE_K * (cmid + pmid)
        out["atm_strike"] = k
        out["em_straddle"] = round(em_str, 4)
        out["em_straddle_pct"] = round(em_str / spot, 6)
        em_pct = (em_str / spot) * math.sqrt(float(span) / float(exp_span))
        out["scaled_from_exp"] = (span != exp_span)
        out["em_src"] = "straddle"
    else:
        iv = iv_atm_from(rows, exp, spot)
        src = "iv_atm_chain"
        if iv is None and lv and lv.get("iv_atm"):
            iv, src = lv["iv_atm"], "iv_atm_levels"
        if iv is None:
            fc = CUBE.full_chain_path(sym, date)
            if fc:
                try:
                    fs = CUBE.read_chain(fc)
                    iv = iv_atm_from(fs.rows, front_expiry(fs.rows, target), spot)
                    src = "iv_atm_polygon"
                except (ValueError, OSError):
                    iv = None
        if iv is None:
            out["invalid_reason"] = "sin_iv_ni_straddle"
            return out                      # None, NO un em de 0
        em_pct = iv * math.sqrt(float(span) / TRADING_DAYS_YEAR)
        out["em_src"] = src
        out["iv_atm"] = round(iv, 6)
    out["em_pct"] = round(em_pct, 6)
    out["em_hi"] = round(spot * math.exp(em_pct), 4)
    out["em_lo"] = round(spot * math.exp(-em_pct), 4)

    inv, esrc = earnings_within(sym, dt.date.fromtimestamp(out["snap_ts"] or now), target)
    out["earnings_checked"] = inv is not None
    out["earnings_src"] = esrc
    if inv:
        out["invalid_reason"] = "earnings"

    if lv:
        for side, key, level in (("up", "call_wall", lv.get("call_wall")),
                                 ("down", "put_wall", lv.get("put_wall"))):
            if not level:
                continue
            edge = out["em_hi"] if side == "up" else out["em_lo"]
            gap = abs(edge - level)
            if gap <= CONFLUENCE_TOL * spot:
                out["confluence"] = {"side": side, "wall": key, "level": level,
                                     "gap_pct": round(100.0 * gap / spot, 4)}
                break
    return out


def write_envelope(sym, date=None, now=None):
    e = envelope(sym, date=date, now=now)
    CUBE.atomic_write_json(os.path.join("data", "em_%s.json" % sym.lower()), e)
    return e


def fleet():
    p = os.path.join("data", "fleet.txt")
    if os.path.exists(p):
        with open(p) as f:
            return f.read().split()
    return [os.path.basename(x)[10:-4].upper()
            for x in sorted(glob.glob(os.path.join("data", "opt_chain_*.txt")))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args()
    syms = [a.sym.upper()] if a.sym else (fleet() if a.all else [])
    if not syms:
        ap.print_help()
        return
    ok = bad = 0
    for s in syms:
        try:
            e = write_envelope(s, date=a.date)
        except Exception as ex:
            print("%-6s FALLO %s" % (s, ex), file=sys.stderr)
            bad += 1
            continue
        if a.print:
            print(json.dumps(e, indent=1))
        else:
            if e["em_hi"] is None:
                print("%-6s valla NO disponible (%s)" % (s, e["invalid_reason"]))
            else:
                print("%-6s %s spot %.2f -> [%.2f, %.2f] em %.2f%% span %dd (cal %dd) exp %s%s%s" % (
                    s, e["em_src"], e["spot"], e["em_lo"], e["em_hi"], 100 * e["em_pct"],
                    e["span_days"], e["calendar_days"], e["exp"],
                    " ESCALADO" if e["scaled_from_exp"] else "",
                    (" CONFLUENCIA %s" % e["confluence"]["wall"]) if e["confluence"] else ""))
        ok += 1 if e["em_hi"] is not None else 0
    print("vallas publicadas: %d/%d (%d fallos)" % (ok, len(syms), bad))


if __name__ == "__main__":
    main()
