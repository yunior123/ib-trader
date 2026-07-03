#!/usr/bin/env python3
"""opt_recon.py — reconstruccion de IV y griegas para el PASADO que no tiene otra via.

CONTEXTO (verificado 2026-07-25):
  Los aggregates de opciones de Polygon (/v2/aggs/ticker/O:...) devuelven SOLO
  {v,vw,o,c,h,l,t,n}: ni IV, ni griegas, ni open_interest. No es que el descargador
  las tirara — el endpoint no las da. Por eso poly_opt_bars no tiene esas columnas.
  El snapshot (/v3/snapshot/options) SI las da, pero solo del AHORA (`as_of` responde
  OK y sirve la cadena de hoy: comprobado). => para el pasado ya descargado
  (2026-06-24 .. 2026-07-24) o se reconstruye, o no hay nada.

RUTA: precio del contrato (poly_opt_bars.c) + spot al mismo ts (poly_bars.c)
      + strike + T(ts) -> invertir IV por biseccion -> griegas Black-Scholes.

LO QUE ESTA RECONSTRUIDO Y LO QUE NO:
  iv, delta, gamma   RECONSTRUIDOS (BS sobre precio de ULTIMO TRADE, no mid)
  oi                 NO EXISTE para el pasado. Proxy = volumen acumulado del dia,
                     SIEMPRE marcado `oi proxy_volumen` en la cabecera. Jamas se
                     presenta como medida.
  bid, ask           NO EXISTEN en aggregates -> -1

Reglas de la casa aplicadas: ante un fallo se devuelve None o se levanta; PROHIBIDO
0/0.5/50 (un numero plausible convierte "no se" en "se, y es cero").
gex_core.py NO se modifica: de ahi se REUSA bs_gamma/bs_vanna/bs_charm.
"""
import datetime as dt
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gex_core import bs_gamma, bs_vanna, bs_charm, T_FLOOR  # noqa: E402,F401  (reuso, no reimplemento)
from poly_client import DB_PATH  # noqa: E402

R_FREE = 0.045       # misma tasa que gex_core por coherencia
NA = -1.0


# ------------------------------------------------------------ Black-Scholes
def _ncdf(x):
    """N(x) con erfc (sin scipy), igual que la skill option-pricing-pro."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs_price(S, K, T, iv, cp="C", r=R_FREE):
    """Precio BS europeo. None si los argumentos no permiten un precio (no 0)."""
    if S is None or K is None or T is None or iv is None:
        return None
    if S <= 0 or K <= 0 or T <= 0 or iv <= 0:
        return None
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2.0) * T) / sq
    d2 = d1 - sq
    disc = math.exp(-r * T)
    if cp.upper().startswith("C"):
        return S * _ncdf(d1) - K * disc * _ncdf(d2)
    return K * disc * _ncdf(-d2) - S * _ncdf(-d1)


def bs_delta(S, K, T, iv, cp="C", r=R_FREE):
    """Delta BS. None si no es calculable (gex_core no lo tiene y no lo toco)."""
    if S is None or S <= 0 or K <= 0 or iv is None or iv <= 0 or T is None or T <= 0:
        return None
    T = max(T, T_FLOOR)
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2.0) * T) / sq
    return _ncdf(d1) if cp.upper().startswith("C") else _ncdf(d1) - 1.0


def implied_vol(price, S, K, T, cp="C", r=R_FREE, lo=1e-4, hi=5.0, tol=1e-7, iters=100):
    """IV por BISECCION. Devuelve la sigma o **None** — nunca un 0.3 "por defecto",
    que es exactamente el cero plausible que prohibe ~/CLAUDE.md.

    None cuando: precio <=0, T<=0, precio POR DEBAJO del valor intrinseco descontado
    (arbitraje / precio rancio de un contrato ilíquido), o precio por ENCIMA del
    maximo alcanzable con sigma=hi (IV fuera del bracket)."""
    if price is None or price <= 0 or S is None or S <= 0 or K <= 0 or T is None or T <= 0:
        return None
    disc = math.exp(-r * T)
    intrinsic = max(S - K * disc, 0.0) if cp.upper().startswith("C") else max(K * disc - S, 0.0)
    if price < intrinsic - 1e-9:
        return None                      # no invertible: el precio viola el suelo BS
    p_hi = bs_price(S, K, T, hi, cp, r)
    if p_hi is None or price > p_hi:
        return None                      # IV > 500%: fuera del bracket, no se extrapola
    p_lo = bs_price(S, K, T, lo, cp, r)
    if p_lo is None or price < p_lo:
        return None                      # por debajo del suelo con sigma minima
    a, b = lo, hi
    for _ in range(iters):
        mid = 0.5 * (a + b)
        pm = bs_price(S, K, T, mid, cp, r)
        if pm is None:
            return None
        if pm > price:
            b = mid
        else:
            a = mid
        if b - a < tol:
            break
    return 0.5 * (a + b)


def T_at(exp, ts_epoch):
    """Años desde ts_epoch hasta las 16:00 ET del vencimiento (YYYYMMDD o YYYY-MM-DD).
    IMPRESCINDIBLE para el pasado: gex_core._T_of usa time.time() (correcto en vivo,
    incorrecto en un replay). None si la fecha no parsea o el contrato ya expiro."""
    s = str(exp).replace("-", "")
    try:
        d = dt.datetime.strptime(s, "%Y%m%d").replace(hour=16, minute=0)
    except ValueError:
        return None
    T = (d.timestamp() - ts_epoch) / (365.0 * 86400.0)
    return T if T > 0 else None


# --------------------------------------------- reconstruccion desde la BD local
def _ro_db():
    if not os.path.exists(DB_PATH):
        raise RuntimeError(f"falta {DB_PATH}")
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    return c


def spot_at(c, sym, ts_ms, tol_ms=15 * 60 * 1000):
    """Cierre 1m de poly_bars en o antes de ts_ms (dentro de tol_ms). None si no hay
    barra cercana: sin spot no se reconstruye nada (no se toma "el ultimo que haya")."""
    r = c.execute("SELECT ts, c FROM poly_bars WHERE sym=? AND ts<=? AND ts>=? "
                  "ORDER BY ts DESC LIMIT 1", (sym, ts_ms, ts_ms - tol_ms)).fetchone()
    return float(r[1]) if r and r[1] else None


def cum_volume(c, day_start_ms, ts_ms):
    """Volumen acumulado del dia por contrato hasta ts_ms. PROXY de OI, nada mas."""
    rows = c.execute("SELECT otk, SUM(v) FROM poly_opt_bars WHERE ts>=? AND ts<=? "
                     "GROUP BY otk", (day_start_ms, ts_ms)).fetchall()
    return {k: (v or 0.0) for k, v in rows}


def rebuild_chain(sym, when, band=0.045, tol_ms=15 * 60 * 1000, c=None):
    """Reconstruye la cadena de `sym` en el instante `when` (datetime) desde
    poly_opt_bars + poly_bars.

    Devuelve dict con: rows (lista de dicts), spot, stats (contadores de por que
    fallo cada contrato — se REPORTAN, no se silencian) o levanta si no hay spot.
    """
    own = c is None
    c = c or _ro_db()
    try:
        ts_ms = int(when.timestamp() * 1000)
        day0 = int(dt.datetime.combine(when.date(), dt.time(0, 0)).timestamp() * 1000)
        spot = spot_at(c, sym, ts_ms, tol_ms)
        if spot is None:
            raise RuntimeError(f"{sym} {when:%Y-%m-%d %H:%M}: sin spot en poly_bars "
                               f"(+-{tol_ms // 60000}min) -> no se reconstruye")
        vol_cum = cum_volume(c, day0, ts_ms)
        lo, hi = spot * (1 - band), spot * (1 + band)
        # ultima barra <= ts para cada contrato en la banda
        rows = c.execute(
            "SELECT otk, exp, strike, right, MAX(ts), c, v FROM poly_opt_bars "
            "WHERE sym=? AND ts<=? AND ts>=? AND strike>=? AND strike<=? GROUP BY otk",
            (sym, ts_ms, ts_ms - tol_ms, lo, hi)).fetchall()
        out = []
        st = {"contratos": 0, "iv_ok": 0, "sin_spot": 0, "iv_no_invertible": 0,
              "sin_T": 0, "precio_no_valido": 0}
        for otk, exp, strike, right, bts, close, v in rows:
            st["contratos"] += 1
            cp = "C" if str(right).lower().startswith("c") else "P"
            if close is None or close <= 0:
                st["precio_no_valido"] += 1
                iv = None
            else:
                T = T_at(exp, bts / 1000.0)
                if T is None:
                    st["sin_T"] += 1
                    iv = None
                else:
                    iv = implied_vol(float(close), spot, float(strike), T, cp)
                    if iv is None:
                        st["iv_no_invertible"] += 1
                    else:
                        st["iv_ok"] += 1
            T = T_at(exp, bts / 1000.0)
            g = bs_gamma(spot, float(strike), T, iv) if (iv and T) else None
            d = bs_delta(spot, float(strike), T, iv, cp) if (iv and T) else None
            out.append({
                "otk": otk, "strike": float(strike), "right": cp,
                "exp": str(exp).replace("-", ""), "ts": bts, "price": close,
                "iv": iv, "delta": d, "gamma": g, "T": T,
                "oi_proxy_vol": vol_cum.get(otk),   # PROXY, no OI
                "vol_bar": v,
            })
        return {"sym": sym, "when": when, "spot": spot, "rows": out, "stats": st,
                "band": band}
    finally:
        if own:
            c.close()


def chain_to_text(rec):
    """Mismo formato de produccion (gex_core.from_ibkr_cache), con PROCEDENCIA explicita.
    -1 en todo lo que genuinamente no tenemos. El OI va marcado como PROXY."""
    rows, spot, when = rec["rows"], rec["spot"], rec["when"]
    exps = sorted({r["exp"] for r in rows})
    hdr = [
        f"# opt_chain {rec['sym']} | epoch {int(when.timestamp())} | "
        f"{when:%Y-%m-%d %H:%M:%S} | spot {spot:.2f} | exps {' '.join(exps)}",
        "# fuente poly_opt_bars(aggregates) | greeks BS_reconstruidas | "
        "iv BS_invertida_biseccion_sobre_ULTIMO_TRADE | oi proxy_volumen_acumulado | "
        "bid/ask NO_DISPONIBLE(-1) | RECONSTRUIDO_NO_MEDIDO",
        "# strike right exp bid ask vol oi iv delta gamma",
    ]
    body = []
    for r in rows:
        oi = r["oi_proxy_vol"]
        body.append(
            f"{r['strike']:.2f} {r['right']} {r['exp']} {NA:.2f} {NA:.2f} "
            f"{(r['vol_bar'] if r['vol_bar'] is not None else NA):.0f} "
            f"{(oi if oi is not None else NA):.0f} "
            f"{(r['iv'] if r['iv'] is not None else NA):.4f} "
            f"{(r['delta'] if r['delta'] is not None else NA):.4f} "
            f"{(r['gamma'] if r['gamma'] is not None else NA):.6f}")
    return "\n".join(hdr + body) + "\n"


# ------------------------------------------------------------------------ CLI
def _cli():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "selftest":
        # inversion contra caso de referencia: precio BS -> invertir -> recuperar sigma
        print("INVERSION DE IV (precio BS -> biseccion -> sigma original)")
        worst = 0.0
        for S, K, T, sig, cp in [(100, 100, 0.25, 0.20, "C"), (100, 110, 0.5, 0.35, "C"),
                                 (100, 90, 0.08, 0.55, "P"), (685, 690, 0.011, 0.19, "C"),
                                 (50, 45, 1.0, 0.80, "P"), (200, 200, 0.004, 0.45, "C")]:
            p = bs_price(S, K, T, sig, cp)
            got = implied_vol(p, S, K, T, cp)
            err = abs(got - sig) if got is not None else float("inf")
            worst = max(worst, err)
            print(f"  S={S:6} K={K:6} T={T:6} sigma={sig:.3f} -> precio {p:8.4f} "
                  f"-> iv {got if got is None else round(got, 8)}  err {err:.2e}")
        print(f"  peor error absoluto: {worst:.2e}  "
              f"{'OK (<1e-4)' if worst < 1e-4 else 'FALLA'}")
        return
    if a[0] == "chain":
        sym = a[a.index("--sym") + 1].upper() if "--sym" in a else "QQQ"
        when = dt.datetime.strptime(a[a.index("--at") + 1], "%Y-%m-%d %H:%M") \
            if "--at" in a else dt.datetime(2026, 7, 24, 15, 55)
        rec = rebuild_chain(sym, when)
        print(chain_to_text(rec), end="")
        print(f"# stats {rec['stats']}")
        return
    print(__doc__)


if __name__ == "__main__":
    _cli()
