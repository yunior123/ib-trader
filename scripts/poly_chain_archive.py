#!/usr/bin/env python3
"""poly_chain_archive.py — ARCHIVADOR de cadenas de opciones con griegas/IV/OI REALES
de Polygon. Camino PRINCIPAL para el histórico de muros/GEX (orden Yunior 2026-07-25:
"trae las griegas de Polygon directo").

QUE ESTA VERIFICADO (medido 2026-07-25 con la key de feeds.env)
  GET /v3/snapshot/options/{SUBYACENTE}  devuelve por contrato:
    details{strike_price, expiration_date, contract_type}
    greeks{delta, gamma, theta, vega}      <- REALES
    implied_volatility                     <- REAL
    open_interest                          <- REAL (comprobado QQQ 680P 2026-08-21: 71165)
    day{open,high,low,close,volume,vwap}   <- OHLCV del dia; VACIO {} si no cotizo
  NO devuelve last_quote/last_trade con esta key -> bid/ask NO DISPONIBLES -> se
  escribe -1, jamas un precio inventado.

LA TRAMPA (verificada, no teorica): `?as_of=<fecha_pasada>` responde status OK pero
LO IGNORA y sirve la cadena de HOY. Construir histórico con as_of da N copias del dia
de hoy con etiquetas de fecha distintas: un backtest que "funciona" y es ficcion pura.
Por eso este script NO usa as_of: archiva el AHORA, fechado con el AHORA, y valida que
las expiraciones devueltas sean >= la fecha del snapshot (si no, aborta el simbolo).
=> El OI/griegas ANTERIORES a hoy NO LOS TENEMOS y no se pueden pedir. Desde hoy si.

Salida por corrida, en data/history/<fecha>/ :
  chain_full_<sym>.json          snapshot crudo + procedencia (auditoria completa)
  poly_chain_<sym>_<HHMM>.txt    formato de PRODUCCION (lo lee gex_core.from_ibkr_cache)

Uso:
  python3 scripts/poly_chain_archive.py                 # flota completa, banda por defecto
  python3 scripts/poly_chain_archive.py --syms QQQ SPY
  python3 scripts/poly_chain_archive.py --band 0.06 --dte 21
  python3 scripts/poly_chain_archive.py --cost          # solo estima el coste en peticiones
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_client import REPO, DB_PATH, Polygon, PolygonError, atomic_write, fleet  # noqa: E402

os.environ.setdefault("TZ", "America/New_York")
time.tzset()

BAND = 0.045      # +-4.5% de strikes: donde viven los muros que operamos
DTE_MAX = 10      # 0DTE + las 2 semanas siguientes (lo que mueve el GEX intradia)
NA = -1.0         # "no lo se". NUNCA 0 (regla ~/CLAUDE.md)


# --------------------------------------------------------------------- el spot
def spot_ibkr(sym, max_age_s):
    """Spot del puente IBKR (data/bars_<sym>_ibkr.txt): GRATIS y en vivo, cero coste
    de cuota Polygon. Devuelve (precio, edad_s) o None — nunca un precio por defecto."""
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
    """Spot del ultimo cierre 1m en poly_bars. Solo lectura, no bloquea la BD."""
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


def spot_of(poly, sym, max_age_s):
    """(precio, fuente, edad_s) o None. Orden: IBKR vivo (gratis) -> poly_bars ->
    /v2/aggs/prev (1 peticion de cuota). Si las tres fallan: None y se REPORTA."""
    for fn, name in ((spot_ibkr, "ibkr_bridge"), (spot_poly_bars, "poly_bars")):
        got = fn(sym, max_age_s)
        if got:
            return got[0], name, got[1]
    d = poly.get(f"https://api.polygon.io/v2/aggs/ticker/{sym}/prev?adjusted=true")
    res = (d or {}).get("results") or []
    if res and res[0].get("c"):
        ts = res[0].get("t")
        age = (time.time() - ts / 1000.0) if ts else float("nan")
        return float(res[0]["c"]), "polygon_prev_close", age
    return None


# ------------------------------------------------------- descarga de la cadena
def fetch_chain(poly, sym, spot, band, dte_max, snap_day):
    """Snapshot completo (paginado) del subyacente, filtrado a la banda de strikes y
    a los vencimientos proximos. Levanta PolygonError si una pagina falla (un
    resultado PARCIAL jamas se entrega como completo) o si las expiraciones vuelven
    incoherentes con la fecha pedida (la trampa del as_of)."""
    lo, hi = spot * (1 - band), spot * (1 + band)
    exp_hi = snap_day + dt.timedelta(days=dte_max)
    url = (f"https://api.polygon.io/v3/snapshot/options/{sym}?limit=250"
           f"&strike_price.gte={lo:.2f}&strike_price.lte={hi:.2f}"
           f"&expiration_date.gte={snap_day:%Y-%m-%d}&expiration_date.lte={exp_hi:%Y-%m-%d}")
    rows, pages = [], 0
    for d in poly.paginate(url, max_pages=40):
        rows.extend(d.get("results") or [])
        pages += 1
    # guardia anti-as_of / anti-cadena-equivocada
    for r in rows:
        e = (r.get("details") or {}).get("expiration_date")
        if e and e < f"{snap_day:%Y-%m-%d}":
            raise PolygonError(
                f"{sym}: la cadena trae expiracion {e} ANTERIOR al snapshot "
                f"{snap_day:%Y-%m-%d} -> respuesta incoherente, no se archiva")
    return rows, pages


def to_production_text(sym, rows, spot, snap_ts, spot_src, spot_age):
    """Formato que ya consume produccion (gex_core.from_ibkr_cache):
        # strike right exp bid ask vol oi iv delta gamma
    Cabecera con PROCEDENCIA de cada campo: ningun consumidor debe poder confundir
    'medido por Polygon' con 'reconstruido por nosotros'."""
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
            continue          # contrato sin identidad: se descarta y se cuenta abajo
        exps.add(exp)

        def num(v):
            """v real -> v ; ausente/no-numerico -> NA(-1). Nunca 0 por defecto."""
            if v is None:
                return NA
            try:
                return float(v)
            except (TypeError, ValueError):
                return NA

        # day{} vacio = el contrato NO cotizo hoy -> volumen DESCONOCIDO, no 0.
        vol = num(day.get("volume")) if day else NA
        oi = num(r.get("open_interest"))
        iv = num(r.get("implied_volatility"))
        out.append(f"{k:.2f} {right} {exp} {NA:.2f} {NA:.2f} "
                   f"{vol:.0f} {oi:.0f} {iv:.4f} {num(g.get('delta')):.4f} "
                   f"{num(g.get('gamma')):.6f}")
    hdr = [
        f"# opt_chain {sym} | epoch {int(snap_ts)} | "
        f"{dt.datetime.fromtimestamp(snap_ts):%Y-%m-%d %H:%M:%S} | spot {spot:.2f} | "
        f"exps {' '.join(sorted(exps))}",
        f"# fuente polygon_snapshot_v3 | greeks polygon_directo | iv polygon_directo | "
        f"oi polygon_directo | vol day.volume_polygon(-1 si no cotizo) | "
        f"bid/ask NO_ENTITLED(-1) | spot {spot_src} edad {spot_age:.0f}s",
        "# strike right exp bid ask vol oi iv delta gamma",
    ]
    return "\n".join(hdr + out) + "\n", sorted(exps)


# ------------------------------------------------------------------- corrida
def run(syms, band, dte_max, spot_max_age):
    poly = Polygon()
    t0 = time.time()
    now = dt.datetime.now()
    day_dir = os.path.join(REPO, "data", "history", f"{now:%Y-%m-%d}")
    stamp = f"{now:%H%M}"
    ok, fallos, tot_contracts, tot_pages, oi_real = [], [], 0, 0, 0

    print(f"ARCHIVADOR de cadenas Polygon | {now:%Y-%m-%d %H:%M:%S} | "
          f"{len(syms)} simbolos | banda +-{band * 100:.1f}% | <= {dte_max} DTE")
    for sym in syms:
        try:
            sp = spot_of(poly, sym, spot_max_age)
            if sp is None:
                fallos.append((sym, "sin spot (ni IBKR, ni poly_bars, ni prev-close)"))
                print(f"  ! {sym:6s} SIN SPOT — no se archiva (no se inventa un precio)")
                continue
            spot, src, age = sp
            rows, pages = fetch_chain(poly, sym, spot, band, dte_max, now.date())
            tot_pages += pages
            if not rows:
                fallos.append((sym, f"0 contratos en banda +-{band * 100:.1f}% / {dte_max}DTE"))
                print(f"  ! {sym:6s} 0 contratos (spot {spot:.2f}) — cadena ilíquida o sin opciones")
                continue
            txt, exps = to_production_text(sym, rows, spot, time.time(), src, age)
            n_oi = sum(1 for r in rows if (r.get("open_interest") or 0) > 0)
            n_iv = sum(1 for r in rows if (r.get("implied_volatility") or 0) > 0)
            oi_real += n_oi
            atomic_write(os.path.join(day_dir, f"poly_chain_{sym.lower()}_{stamp}.txt"), txt)
            atomic_write(os.path.join(day_dir, f"chain_full_{sym.lower()}.json"), json.dumps({
                "meta": {
                    "sym": sym, "snapshot_epoch": time.time(),
                    "snapshot_local": f"{now:%Y-%m-%d %H:%M:%S}",
                    "spot": spot, "spot_source": src, "spot_age_s": round(age, 1),
                    "band": band, "dte_max": dte_max, "pages": pages,
                    "endpoint": "/v3/snapshot/options",
                    "greeks": "polygon_directo", "iv": "polygon_directo",
                    "oi": "polygon_directo", "bid_ask": "NO_ENTITLED",
                    "as_of_usado": False,
                    "aviso": "as_of se ignora en este plan (sirve la cadena de hoy) -> "
                             "NO hay OI/griegas anteriores a la fecha de este fichero",
                },
                "results": rows,
            }, separators=(",", ":")))
            ok.append(sym)
            print(f"  {sym:6s} spot {spot:8.2f} ({src[:12]:12s} {age / 60:5.1f}min) "
                  f"{len(rows):5d} contratos {pages}p | oi>0 {n_oi:4d} iv>0 {n_iv:4d} "
                  f"| exps {len(exps)}", flush=True)
            tot_contracts += len(rows)
        except PolygonError as e:
            fallos.append((sym, str(e)))
            print(f"  ! {sym:6s} {e}", flush=True)

    el = time.time() - t0
    print(f"\n-> {len(ok)}/{len(syms)} archivados en {day_dir}")
    print(f"-> {tot_contracts} contratos, {tot_pages} paginas, {oi_real} con OI>0")
    print(f"-> {poly.report()}")
    print(f"-> reloj {el / 60:.1f} min  ({tot_pages} peticiones de cadena + "
          f"{poly.stats['requests'] - tot_pages} de spot)")
    if fallos:
        print(f"-> FALLOS ({len(fallos)}) — NOMBRADOS, no silenciados:")
        for s, why in fallos:
            print(f"     {s}: {why}")
    else:
        print("-> sin fallos")
    return {"ok": ok, "fallos": fallos, "contracts": tot_contracts,
            "pages": tot_pages, "requests": poly.stats["requests"], "elapsed_s": el}


def main():
    a = sys.argv[1:]

    def opt(flag, default, cast=str):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    syms = fleet()
    if "--syms" in a:
        i = a.index("--syms") + 1
        syms = [s.upper() for s in a[i:] if not s.startswith("--")]
    band = opt("--band", BAND, float)
    dte = opt("--dte", DTE_MAX, int)
    age = opt("--spot-max-age", 86400 * 4, float)
    if "--cost" in a:
        print(f"coste estimado: ~{len(syms)} spots (0 si el puente IBKR esta fresco) + "
              f"~5 paginas/simbolo = ~{len(syms) * 5} peticiones\n"
              f"a 5 peticiones/60s medidas => ~{len(syms) * 5 * 12.4 / 60:.0f} min por corrida")
        return
    run(syms, band, dte, age)


if __name__ == "__main__":
    main()
