#!/usr/bin/env python3
"""poly_chain_archive.py — ARCHIVADOR de cadenas de opciones con griegas/IV/OI REALES
de Polygon. Camino PRINCIPAL para el histórico de muros/GEX.

GET /v3/snapshot/options/{SUBYACENTE} devuelve por contrato:
  details{strike_price, expiration_date, contract_type}
  greeks{delta, gamma, theta, vega} + implied_volatility + open_interest   <- REALES
  day{open,high,low,close,volume,vwap}   <- VACIO {} si el contrato no cotizo
bid/ask NO vienen con esta key -> se escribe -1, jamas un precio inventado.

LA TRAMPA (verificada): `?as_of=<fecha_pasada>` responde OK pero LO IGNORA y sirve la
cadena de HOY. Este script NO usa as_of: archiva el AHORA y valida que las expiraciones
devueltas sean >= la fecha del snapshot. El OI/griegas del PASADO no se pueden pedir.

BANDA ADAPTATIVA + DTE AL MENSUAL (2026-07-26). Lo que habia (BAND=0.045, DTE_MAX=10)
capturaba el 28% de la gamma (mediana de la flota; MU 7,7%) y dejaba 14 de 25 flips
clavados entre 3,7% y 4,6% del spot = el borde del recorte, no un nivel de mercado.
Medido contra la cadena COMPLETA de CBOE el 2026-07-26, QQQ net GEX ($/1%):
    banda 4,5% x 10 DTE  -> -3,29 B      (lo que archivabamos)
    banda 4,5% x mensual -> -5,00 B
    cadena entera        -> -6,03 B      (referees CBOE/TradingFlow: -5,3 a -6,0 B)
Ahora la banda se ENSANCHA POR CORONAS hasta que la gamma marginal de la corona nueva
cae bajo RING_EPS, con suelo y techo duros, y la banda que convergio se guarda en
data/gamma_band.json para arrancar ahi la corrida siguiente. El DTE llega al MENSUAL
siguiente (3er viernes), que es donde vive el OI que fija los muros del mes.

Salida por corrida en data/history/<fecha>/ :
  chain_full_<sym>.json          snapshot crudo + procedencia + traza de la banda
  poly_chain_<sym>_<HHMM>.txt    formato de PRODUCCION (gex_core.from_ibkr_cache)

Uso:
  python3 scripts/poly_chain_archive.py                 # universo del mapa, banda adaptativa
  python3 scripts/poly_chain_archive.py --syms QQQ SPY
  python3 scripts/poly_chain_archive.py --band 0.06     # banda FIJA (desactiva la adaptativa)
  python3 scripts/poly_chain_archive.py --dte 10 --cost
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import universe  # noqa: E402  (universo del MAPA, no la flota de señales)
from poly_client import (REPO, DB_PATH, Polygon, PolygonError, RateLimiter,  # noqa: E402
                         atomic_write)

os.environ.setdefault("TZ", "America/New_York")
time.tzset()

# --- banda adaptativa (parametros MEDIDOS el 2026-07-26 sobre las 35 cadenas CBOE
#     completas: con esto los 35 simbolos dan flip interior, el mas justo a 13,1 pp del
#     borde, y el net GEX de QQQ/SPY queda en el orden de los referees) ---
BAND_START = 0.12     # arranque cuando no hay calibracion previa del simbolo
BAND_FLOOR = 0.10     # por debajo de esto el flip lo fija el recorte (medido)
BAND_CAP = 0.60       # techo duro: mas alla la gamma es ruido y el fichero engorda
BAND_GROWTH = 1.5
RING_EPS = 0.02       # corona nueva con <2% de la gamma bruta = converge
MAX_STEPS = 6
MAX_PAGES = 200       # SPX +-18% son 35 paginas; el techo protege de un next_url infinito
NA = -1.0             # "no lo se". NUNCA 0 (regla ~/CLAUDE.md)
CALIB = os.path.join(REPO, "data", "gamma_band.json")

# Ritmo: la ventana de 5 peticiones/60s del limitador compartido se midio con la key
# ANTERIOR. Remedido el 2026-07-26: 219 peticiones seguidas (hasta 7/s) sin un solo 429.
# Se usa fichero de estado PROPIO para no vaciar la cuota de los demas procesos.
RATE_N = int(os.environ.get("POLY_CHAINS_RATE_N", "120"))
RATE_STATE = os.path.join(REPO, "data", "poly_rate_state_chains.json")

CBOE_QUOTE = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{}.json"
CBOE_SYM = {"SPX": "_SPX", "XSP": "_XSP", "NDX": "_NDX", "VIX": "_VIX",
            "DJI": "_DJI", "RUT": "_RUT"}


# ------------------------------------------------------------------ vencimientos
def next_monthly(day):
    """3er viernes >= `day` (el del mes siguiente si el de este mes ya paso)."""
    y, m = day.year, day.month
    for _ in range(3):
        first = dt.date(y, m, 1)
        third_fri = first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)
        if third_fri >= day:
            return third_fri
        m, y = (m + 1, y) if m < 12 else (1, y + 1)
    raise ValueError(f"no se pudo situar el mensual siguiente a {day}")


# --------------------------------------------------------------------- el spot
def spot_ibkr(sym, max_age_s):
    """Spot del puente IBKR (data/bars_<sym>_ibkr.txt): vivo y sin coste de cuota.
    (precio, edad_s) o None — nunca un precio por defecto."""
    p = os.path.join(REPO, "data", f"bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(p):
        return None
    last = None
    with open(p) as fh:
        for ln in fh:
            f = ln.split()
            if len(f) >= 5:
                last = f
    if not last:
        return None
    try:
        ts, close = int(float(last[0])), float(last[4])
    except (ValueError, IndexError):
        return None
    age = time.time() - ts
    if close <= 0 or age > max_age_s:
        return None
    return close, age


def spot_poly_bars(sym, max_age_s):
    """Ultimo cierre 1m en poly_bars. Solo lectura, no bloquea la BD."""
    if not os.path.exists(DB_PATH):
        return None
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=20)
    try:
        r = c.execute("SELECT ts, c FROM poly_bars WHERE sym=? ORDER BY ts DESC LIMIT 1",
                      (sym,)).fetchone()
    finally:
        c.close()
    if not r or not r[1]:
        return None
    age = time.time() - r[0] / 1000.0
    if age > max_age_s:
        return None
    return float(r[1]), age


def spot_cboe(sym, max_age_s):
    """Cotizacion delayed de CBOE. Es la UNICA fuente de spot para SPX y XSP: Polygon
    devuelve 403 en /v3/snapshot/indices y en aggs de I:SPX con esta key. La edad sale
    de `last_trade_time` del propio dato, no del reloj del fichero."""
    url = CBOE_QUOTE.format(CBOE_SYM.get(sym.upper(), sym.upper()))
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    q = (d or {}).get("data") or {}
    px = q.get("current_price") or q.get("close")
    lt = q.get("last_trade_time")
    if not px or float(px) <= 0 or not lt:
        return None
    try:
        age = time.time() - time.mktime(time.strptime(str(lt)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None
    if age > max_age_s:
        return None
    return float(px), age


def spot_of(poly, sym, max_age_s):
    """(precio, fuente, edad_s) o None. IBKR vivo -> poly_bars -> prev-close Polygon ->
    CBOE delayed. Si las cuatro fallan: None, y el simbolo se REPORTA sin archivar."""
    for fn, name in ((spot_ibkr, "ibkr_bridge"), (spot_poly_bars, "poly_bars")):
        got = fn(sym, max_age_s)
        if got:
            return got[0], name, got[1]
    try:
        d = poly.get(f"https://api.polygon.io/v2/aggs/ticker/{sym}/prev?adjusted=true")
    except PolygonError:
        d = None                      # 401/403: los indices no estan autorizados -> CBOE
    res = (d or {}).get("results") or []
    if res and res[0].get("c"):
        ts = res[0].get("t")
        age = (time.time() - ts / 1000.0) if ts else float("nan")
        return float(res[0]["c"]), "polygon_prev_close", age
    got = spot_cboe(sym, max_age_s)
    if got:
        return got[0], "cboe_delayed_quote", got[1]
    return None


# ------------------------------------------------------- descarga de la cadena
def gamma_mass(rows):
    """Gamma bruta MEDIDA de un lote: suma |gamma x OI|. Los contratos sin gamma o sin
    OI no suman (no se les inventa peso) — es la magnitud contra la que se decide si
    ensanchar merece la pena."""
    tot = 0.0
    for r in rows:
        g = (r.get("greeks") or {}).get("gamma")
        oi = r.get("open_interest")
        if g is None or not oi:
            continue
        try:
            tot += abs(float(g) * float(oi))
        except (TypeError, ValueError):
            continue
    return tot


def window_of(poly, sym, snap_day, exp_hi):
    """Cierra la ventana de red en una funcion `fetch(lo=..., hi=...)` para que el
    criterio de banda no sepa de donde vienen los contratos."""
    def fetch(**kw):
        return fetch_window(poly, sym, snap_day, exp_hi, **kw)
    return fetch


def fetch_window(poly, sym, snap_day, exp_hi, lo=None, hi=None, lo_strict=None,
                 hi_strict=None):
    """Una ventana de strikes del snapshot, paginada. `lo/hi` inclusive, `*_strict`
    exclusivo (las coronas usan los estrictos para no solapar con lo ya traido).
    Levanta si una pagina falla — un resultado PARCIAL no se entrega como completo — o
    si vuelve una expiracion anterior al snapshot (la trampa del as_of)."""
    q = [f"https://api.polygon.io/v3/snapshot/options/{sym}?limit=250",
         f"expiration_date.gte={snap_day:%Y-%m-%d}",
         f"expiration_date.lte={exp_hi:%Y-%m-%d}"]
    if lo is not None:
        q.append(f"strike_price.gte={lo:.2f}")
    if hi is not None:
        q.append(f"strike_price.lte={hi:.2f}")
    if lo_strict is not None:
        q.append(f"strike_price.lt={lo_strict:.2f}")
    if hi_strict is not None:
        q.append(f"strike_price.gt={hi_strict:.2f}")
    rows, pages = [], 0
    for d in poly.paginate("&".join(q), max_pages=MAX_PAGES):
        rows.extend(d.get("results") or [])
        pages += 1
    for r in rows:
        e = (r.get("details") or {}).get("expiration_date")
        if e and e < f"{snap_day:%Y-%m-%d}":
            raise PolygonError(
                f"{sym}: la cadena trae expiracion {e} ANTERIOR al snapshot "
                f"{snap_day:%Y-%m-%d} -> respuesta incoherente, no se archiva")
    return rows, pages


def fetch_chain_adaptive(fetch, spot, band0=None, fixed_band=None):
    """Cadena con la banda que la propia gamma dicta.

    Ensancha x BAND_GROWTH y mide la gamma de la corona nueva: cuando aporta menos de
    RING_EPS del total, el perfil ya no cambia y se para. Suelo BAND_FLOOR (por debajo
    el flip sale del recorte) y techo BAND_CAP. Devuelve (rows, pages, banda, traza).
    `convergido` False en la traza final = se toco el techo con corona aun material:
    eso se DICE en el informe, no se calla."""
    dedup = {}

    def add(rows):
        """Un contrato repetido doblaria su gamma en el perfil: se indexa por ticker."""
        for r in rows:
            t = (r.get("details") or {}).get("ticker")
            dedup[t or f"anon{len(dedup)}"] = r

    if fixed_band:
        rows, pages = fetch(lo=spot * (1 - fixed_band), hi=spot * (1 + fixed_band))
        add(rows)
        return (list(dedup.values()), pages, fixed_band,
                [{"band": fixed_band, "n": len(dedup), "ring_share": None,
                  "convergido": None, "modo": "banda_fija"}])

    band = max(BAND_FLOOR, min(band0 or BAND_START, BAND_CAP))
    lo, hi = spot * (1 - band), spot * (1 + band)
    rows, pages = fetch(lo=lo, hi=hi)
    add(rows)
    trace = [{"band": round(band, 4), "n": len(dedup), "ring_share": None,
              "convergido": False}]
    for _ in range(MAX_STEPS):
        if band >= BAND_CAP:
            break
        nb = min(band * BAND_GROWTH, BAND_CAP)
        r_lo, p_lo = fetch(lo=spot * (1 - nb), lo_strict=lo)
        r_hi, p_hi = fetch(hi=spot * (1 + nb), hi_strict=hi)
        pages += p_lo + p_hi
        ring = r_lo + r_hi
        base = gamma_mass(list(dedup.values()))
        m_ring = gamma_mass(ring)
        share = (m_ring / (base + m_ring)) if (base + m_ring) > 0 else 0.0
        add(ring)
        band, lo, hi = nb, spot * (1 - nb), spot * (1 + nb)
        conv = share < RING_EPS
        trace.append({"band": round(band, 4), "n": len(dedup),
                      "ring_share": round(share, 5), "convergido": conv})
        if conv:
            break
    return list(dedup.values()), pages, band, trace


# ------------------------------------------- griegas de indice: CBOE (Polygon no las da)
CBOE_CHAIN = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"
_OCC = None


def cboe_rows(sym, snap_day, exp_hi):
    """Cadena COMPLETA de CBOE traducida a la FORMA de Polygon (1 peticion, sin key).

    Es la unica fuente de griegas para opciones de INDICE: medido el 2026-07-26, la
    cadena Polygon de SPX trae 8.512 contratos y **0 con gamma**, XSP 5.446 y 0 — solo
    OI. Lo que llega de aqui queda marcado contrato a contrato (`_src`) y en la
    cabecera del fichero: medido de CBOE nunca se confunde con medido de Polygon."""
    global _OCC
    if _OCC is None:
        import re
        _OCC = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
    url = CBOE_CHAIN.format(CBOE_SYM.get(sym.upper(), sym.upper()))
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            d = json.load(r)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PolygonError(f"{sym}: CBOE no sirvio la cadena ({e!r})")
    dd = (d or {}).get("data") or {}
    out = []
    for o in dd.get("options") or []:
        m = _OCC.match(str(o.get("option") or ""))
        if not m:
            continue
        root, ymd, cp, kk = m.groups()
        try:
            exp = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
        except ValueError:
            continue
        if exp < snap_day or exp > exp_hi:
            continue
        iv = o.get("iv")
        out.append({
            "details": {"ticker": f"O:{root}{ymd}{cp}{kk}", "strike_price": int(kk) / 1000.0,
                        "expiration_date": f"{exp:%Y-%m-%d}",
                        "contract_type": "call" if cp == "C" else "put"},
            # iv=0 no es una volatilidad: es "no calculada" -> None (se escribe -1)
            "greeks": {k: o.get(k) for k in ("delta", "gamma", "theta", "vega")},
            "implied_volatility": (float(iv) if iv else None),
            "open_interest": o.get("open_interest"),
            "day": {"volume": o.get("volume"), "close": o.get("last_trade_price"),
                    "open": o.get("open"), "high": o.get("high"), "low": o.get("low")},
            "_src": "cboe_delayed",
        })
    if not out:
        raise PolygonError(f"{sym}: CBOE sirvio 0 contratos en el rango de vencimientos")
    return out, (dd.get("current_price") or dd.get("close"))


def slicer_of(rows):
    """La misma `fetch(lo=,hi=,lo_strict=,hi_strict=)` que la red, pero recortando una
    cadena que ya esta en memoria: asi el criterio de banda es UNO para los dos
    transportes. 0 paginas porque no cuesta peticiones."""
    def fetch(lo=None, hi=None, lo_strict=None, hi_strict=None):
        out = []
        for r in rows:
            k = r["details"]["strike_price"]
            if lo is not None and k < lo:
                continue
            if hi is not None and k > hi:
                continue
            if lo_strict is not None and k >= lo_strict:
                continue
            if hi_strict is not None and k <= hi_strict:
                continue
            out.append(r)
        return out, 0
    return fetch


def to_production_text(sym, rows, spot, snap_ts, spot_src, spot_age, band, exp_hi,
                       greeks_src="polygon_directo"):
    """Formato que ya consume produccion (gex_core.from_ibkr_cache):
        # strike right exp bid ask vol oi iv delta gamma
    La cabecera lleva la PROCEDENCIA de cada campo y la banda/vencimiento del recorte:
    ningun consumidor debe poder confundir 'medido' con 'reconstruido', ni leer un
    perfil sin saber donde se corto."""
    out, exps = [], set()
    for r in rows:
        de = r.get("details") or {}
        g = r.get("greeks") or {}
        day = r.get("day") or {}
        try:
            k = float(de["strike_price"])
            exp = str(de["expiration_date"]).replace("-", "")
            right = "C" if str(de["contract_type"]).lower().startswith("c") else "P"
        except (KeyError, TypeError, ValueError):
            continue
        exps.add(exp)

        def num(v):
            if v is None:
                return NA
            try:
                return float(v)
            except (TypeError, ValueError):
                return NA

        # day{} vacio = el contrato NO cotizo hoy -> volumen DESCONOCIDO, no 0.
        vol = num(day.get("volume")) if day else NA
        out.append(f"{k:.2f} {right} {exp} {NA:.2f} {NA:.2f} "
                   f"{vol:.0f} {num(r.get('open_interest')):.0f} "
                   f"{num(r.get('implied_volatility')):.4f} {num(g.get('delta')):.4f} "
                   f"{num(g.get('gamma')):.6f}")
    hdr = [
        f"# opt_chain {sym} | epoch {int(snap_ts)} | "
        f"{dt.datetime.fromtimestamp(snap_ts):%Y-%m-%d %H:%M:%S} | spot {spot:.2f} | "
        f"exps {' '.join(sorted(exps))}",
        f"# fuente {'polygon_snapshot_v3' if greeks_src == 'polygon_directo' else greeks_src} | "
        f"greeks {greeks_src} | iv {greeks_src} | oi {greeks_src} | "
        f"vol day.volume(-1 si no cotizo) | bid/ask NO_ENTITLED(-1) | "
        # `spot_src`, no `spot`: opt_quick.cpp:92 hace strstr("spot ")+atof en CUALQUIER
        # linea de cabecera, asi que un `spot ibkr_bridge` le daria spot=0
        # (docs/CHAIN-HEADER.md, regla 2).
        f"spot_src {spot_src} spot_edad_s {spot_age:.0f} | "
        f"band {band:.4f} vencimientos {len(exps)} exp_hasta {exp_hi:%Y-%m-%d}",
        "# strike right exp bid ask vol oi iv delta gamma",
    ]
    return "\n".join(hdr + out) + "\n", sorted(exps)


# --------------------------------------------------------------- calibracion
def load_calib(path=CALIB):
    """Bandas que convergieron en la ultima corrida. {} si no hay o esta roto: el
    arranque sin calibracion es BAND_START, no un numero heredado a medias."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    return d.get("syms", {}) if isinstance(d, dict) else {}


def start_band(calib, sym):
    """Arranque para `sym`: la banda guardada DIVIDIDA por el crecimiento, para que el
    primer ensanche caiga exactamente en la banda que ya convergio. Arrancar EN la
    banda guardada la haria crecer x1.5 en cada corrida (trinquete)."""
    got = (calib.get(sym) or {}).get("band")
    try:
        got = float(got)
    except (TypeError, ValueError):
        return None
    if got <= 0:
        return None
    return max(BAND_FLOOR, min(got / BAND_GROWTH, BAND_CAP))


# ------------------------------------------------------------------- corrida
def run(syms, band, dte_max, spot_max_age):
    poly = Polygon(limiter=RateLimiter(n=RATE_N, path=RATE_STATE))
    t0 = time.time()
    now = dt.datetime.now()
    snap_day = now.date()
    exp_hi = (snap_day + dt.timedelta(days=dte_max)) if dte_max else next_monthly(snap_day)
    day_dir = os.path.join(REPO, "data", "history", f"{now:%Y-%m-%d}")
    stamp = f"{now:%H%M}"
    calib = load_calib()
    nuevo_calib = {}
    ok, fallos, sin_converger = [], [], []
    tot_contracts = tot_pages = oi_real = 0

    print(f"ARCHIVADOR de cadenas Polygon | {now:%Y-%m-%d %H:%M:%S} | {len(syms)} simbolos | "
          f"banda {'FIJA +-%.1f%%' % (band * 100) if band else 'ADAPTATIVA'} | "
          f"vencimientos hasta {exp_hi:%Y-%m-%d}")
    for sym in syms:
        try:
            sp = spot_of(poly, sym, spot_max_age)
            if sp is None:
                fallos.append((sym, "sin spot (ni IBKR, ni poly_bars, ni prev-close, ni CBOE)"))
                print(f"  ! {sym:6s} SIN SPOT — no se archiva (no se inventa un precio)")
                continue
            spot, src, age = sp
            greeks_src = "polygon_directo"
            rows, pages, band_used, trace = fetch_chain_adaptive(
                window_of(poly, sym, snap_day, exp_hi), spot,
                band0=start_band(calib, sym), fixed_band=band)
            tot_pages += pages
            if rows and gamma_mass(rows) <= 0:
                # cadena sin UNA sola gamma: con esto no hay mapa. Es el caso medido de
                # los indices (Polygon sirve el OI y las griegas vacias) -> CBOE, dicho.
                full, spot_c = cboe_rows(sym, snap_day, exp_hi)
                rows, _, band_used, trace = fetch_chain_adaptive(
                    slicer_of(full), spot, band0=start_band(calib, sym), fixed_band=band)
                greeks_src = "cboe_delayed"
                if spot_c:
                    spot, src = float(spot_c), "cboe_delayed_quote"
                print(f"    {sym}: Polygon sin griegas ({len(full)} contratos CBOE en su lugar)",
                      flush=True)
            if not rows:
                fallos.append((sym, f"0 contratos en +-{band_used * 100:.1f}% hasta {exp_hi}"))
                print(f"  ! {sym:6s} 0 contratos (spot {spot:.2f}) — cadena ilíquida o sin opciones")
                continue
            txt, exps = to_production_text(sym, rows, spot, time.time(), src, age,
                                           band_used, exp_hi, greeks_src)
            n_oi = sum(1 for r in rows if (r.get("open_interest") or 0) > 0)
            n_iv = sum(1 for r in rows if (r.get("implied_volatility") or 0) > 0)
            oi_real += n_oi
            conv = bool(trace[-1].get("convergido"))
            atomic_write(os.path.join(day_dir, f"poly_chain_{sym.lower()}_{stamp}.txt"), txt)
            atomic_write(os.path.join(day_dir, f"chain_full_{sym.lower()}.json"), json.dumps({
                "meta": {
                    "sym": sym, "snapshot_epoch": time.time(),
                    "snapshot_local": f"{now:%Y-%m-%d %H:%M:%S}",
                    "spot": spot, "spot_source": src, "spot_age_s": round(age, 1),
                    "band": band_used, "band_mode": "fija" if band else "adaptativa",
                    "band_convergida": conv, "band_trace": trace,
                    "band_floor": BAND_FLOOR, "band_cap": BAND_CAP, "ring_eps": RING_EPS,
                    "exp_hasta": f"{exp_hi:%Y-%m-%d}",
                    "exp_criterio": "dte_explicito" if dte_max else "mensual_siguiente",
                    "dte_max": (exp_hi - snap_day).days, "pages": pages,
                    "endpoint": ("/v3/snapshot/options" if greeks_src == "polygon_directo"
                                 else "cboe/delayed_quotes/options"),
                    "greeks": greeks_src, "iv": greeks_src,
                    "oi": greeks_src, "bid_ask": "NO_ENTITLED",
                    "as_of_usado": False,
                    "aviso": "as_of se ignora en este plan (sirve la cadena de hoy) -> "
                             "NO hay OI/griegas anteriores a la fecha de este fichero",
                },
                "results": rows,
            }, separators=(",", ":")))
            nuevo_calib[sym] = {"band": round(band_used, 4), "convergido": conv,
                                "ring_share": trace[-1].get("ring_share"),
                                "n": len(rows), "pages": pages, "spot": round(spot, 4),
                                "asof": f"{now:%Y-%m-%d %H:%M:%S}"}
            ok.append(sym)
            if not conv and not band:
                sin_converger.append((sym, band_used, trace[-1].get("ring_share")))
            print(f"  {sym:6s} spot {spot:9.2f} ({src[:12]:12s} {age / 60:6.1f}min) "
                  f"+-{band_used * 100:4.1f}% {len(rows):5d} contratos {pages:3d}p | "
                  f"oi>0 {n_oi:5d} iv>0 {n_iv:5d} | exps {len(exps)}"
                  f"{'' if conv or band else '  ** SIN CONVERGER (techo)'}", flush=True)
            tot_contracts += len(rows)
        except PolygonError as e:
            fallos.append((sym, str(e)))
            print(f"  ! {sym:6s} {e}", flush=True)

    if nuevo_calib and not band:
        atomic_write(CALIB, json.dumps({
            "generado_por": "scripts/poly_chain_archive.py",
            "asof": f"{now:%Y-%m-%d %H:%M:%S}",
            "criterio": (f"ensanchar x{BAND_GROWTH} hasta que la corona nueva aporte "
                         f"<{RING_EPS * 100:.0f}% de la gamma bruta; suelo "
                         f"{BAND_FLOOR * 100:.0f}%, techo {BAND_CAP * 100:.0f}%"),
            "syms": nuevo_calib,
        }, indent=1))

    el = time.time() - t0
    print(f"\n-> {len(ok)}/{len(syms)} archivados en {day_dir}")
    print(f"-> {tot_contracts} contratos, {tot_pages} paginas, {oi_real} con OI>0")
    print(f"-> {poly.report()}")
    print(f"-> reloj {el / 60:.1f} min")
    if sin_converger:
        print(f"-> BANDA EN EL TECHO ({len(sin_converger)}) — queda gamma FUERA del archivo:")
        for s, b, sh in sin_converger:
            print(f"     {s}: +-{b * 100:.0f}% con corona al {(sh or 0) * 100:.1f}%")
    if fallos:
        print(f"-> FALLOS ({len(fallos)}) — NOMBRADOS, no silenciados:")
        for s, why in fallos:
            print(f"     {s}: {why}")
    else:
        print("-> sin fallos")
    return {"ok": ok, "fallos": fallos, "contracts": tot_contracts, "pages": tot_pages,
            "requests": poly.stats["requests"], "elapsed_s": el,
            "sin_converger": sin_converger}


def main():
    a = sys.argv[1:]

    def opt(flag, default, cast=str):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    syms = universe.gamma_universe()
    if "--syms" in a:
        i = a.index("--syms") + 1
        syms = [s.upper() for s in a[i:] if not s.startswith("--")]
    band = opt("--band", None, float)          # None = banda adaptativa
    dte = opt("--dte", None, int)              # None = hasta el mensual siguiente
    age = opt("--spot-max-age", 86400 * 4, float)
    if "--cost" in a:
        hoy = dt.date.today()
        cal = load_calib()
        pag = sum((cal.get(s) or {}).get("pages", 10) for s in syms)
        print(f"universo {len(syms)} simbolos | vencimientos hasta "
              f"{next_monthly(hoy) if dte is None else hoy + dt.timedelta(days=dte)}\n"
              f"paginas de la ultima corrida (10 estimadas si el simbolo es nuevo): {pag}\n"
              f"a {RATE_N} peticiones/60s => ~{pag / RATE_N:.1f} min")
        return
    run(syms, band, dte, age)


if __name__ == "__main__":
    main()
