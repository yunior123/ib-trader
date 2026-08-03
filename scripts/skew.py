#!/usr/bin/env python3
"""skew.py — risk reversal 25 delta (ficha #28 `skew-lead`, ola 3). SIN VOZ, SIN FACTOR.

`RR = IV(25delta put) - IV(25delta call)`. Un RR subiendo significa que **estan pujando los
puts**: es la corroboracion de que un print de BALLENA-CALLS es un TECHO local (los dealers
comprando downside) en vez de continuacion. **Contexto, jamas gatillo.**

EL ENTREGABLE DE HOY ES UN "NO SE" HONESTO
------------------------------------------
La ficha #28 dice, literalmente, **"Veredicto HOY: DATA-INSUFFICIENT, y la feature lo dice en voz
alta"**. Este fichero existe para decirlo con numeros propios, no para fingir una serie:

  1. `z` se calcula frente a las **60 sesiones previas** de la superficie. La tabla `iv_hist`
     **NO EXISTE** en `trades.db` (verificado 2026-07-25) y el archivo de cadenas tiene **1 sola
     fecha**. Asi que `z = None`, `n_hist = 1`, y **ese None SE MUESTRA, no se rellena**.
  2. El contrato de `|delta| = 0.25` tiene que estar **DENTRO de la banda traida**. Medido sobre
     el archivo del 2026-07-25: **16 de 30 simbolos**. Para los otros 14 el valor se
     **SUPRIME** con `extrapolated=1` — no se extrapola una IV fuera de la banda para tener
     un numero bonito.
  3. `iv_src` se arrastra SIEMPRE, y la IV del snapshot de Polygon **jamas** se mezcla en una
     serie con `modelGreeks.impliedVol` de IBKR (una salida de modelo suavizada, ausente fuera
     de RTH). Mezclarlas produce una serie que parece continua y no lo es.

Su propio soporte publicado (skew de Xing-Zhang-Zhao, vol spread de Cremers-Weinbaum) es
**TRANSVERSAL a horizontes SEMANALES**, no un lead intradia — por eso aqui no hay ni voz ni
factor en `direction_view`, y la ficha lo revisita en 2027.

Python legitimo: lote fuera de sesion. SEÑAL-SOLAMENTE.
"""
import glob
import json
import os
import sqlite3
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
sys.path.insert(0, os.path.join(REPO, "scripts"))
import session_dirs  # noqa: E402

HIST = os.path.join(REPO, "data", "history")
DB = os.path.join(REPO, "data", "trades.db")
OUT = os.path.join(REPO, "data", "skew.json")

TARGET_DELTA = 0.25
MIN_HIST_FOR_Z = 60          # la ficha: z es NULL hasta 60 sesiones, y ese NULL se muestra


def latest_dates():
    """Sesiones con cadenas archivadas, de mas nueva a mas vieja.

    Solo dias de MERCADO: el archivador corre tambien sabado y domingo y esa foto es la del
    viernes con otro nombre — colada como dates[0] daria drr_1d = 0 fabricado.
    """
    return [d for d in session_dirs.session_dirs(HIST)
            if glob.glob(os.path.join(HIST, d, "chain_full_*.json"))]


def load_chain(date, sym):
    p = os.path.join(HIST, date, "chain_full_%s.json" % sym.lower())
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None      # None, jamas {}: "no hay cadena" no es "cadena vacia"


def nearest_expiry(rows):
    exps = sorted({r["details"]["expiration_date"] for r in rows
                   if r.get("details", {}).get("expiration_date")})
    return exps[0] if exps else None


def interp_iv_at_delta(pts, target):
    """Interpola linealmente la IV al |delta| objetivo.

    `pts` = [(abs_delta, iv), ...]. Devuelve `(iv, extrapolated)`.
    Si el objetivo cae FUERA del rango traido, devuelve `(None, True)` — el valor se SUPRIME.
    Extrapolar una sonrisa fuera de la banda es inventarse el ala que no compramos.
    """
    pts = sorted(p for p in pts if p[0] is not None and p[1] is not None and p[1] > 0)
    if len(pts) < 2:
        return (None, True)
    lo, hi = pts[0][0], pts[-1][0]
    if not (lo <= target <= hi):
        return (None, True)
    for i in range(1, len(pts)):
        d0, v0 = pts[i - 1]
        d1, v1 = pts[i]
        if d0 <= target <= d1:
            if d1 == d0:
                return (v0, False)
            w = (target - d0) / (d1 - d0)
            return (v0 + w * (v1 - v0), False)
    return (None, True)


def rr_for(chain):
    """Devuelve el dict de skew de un simbolo, o None si la cadena no sirve."""
    if not chain or "results" not in chain:
        return None
    rows = chain["results"]
    exp = nearest_expiry(rows)
    if exp is None:
        return None

    calls, puts = [], []
    for r in rows:
        det = r.get("details") or {}
        if det.get("expiration_date") != exp:
            continue
        g = r.get("greeks") or {}
        d, iv = g.get("delta"), r.get("implied_volatility")
        if d is None or iv is None:
            continue
        if det.get("contract_type") == "call":
            calls.append((abs(d), iv))
        elif det.get("contract_type") == "put":
            puts.append((abs(d), iv))

    iv_c, ext_c = interp_iv_at_delta(calls, TARGET_DELTA)
    iv_p, ext_p = interp_iv_at_delta(puts, TARGET_DELTA)
    extrapolated = bool(ext_c or ext_p)
    rr = None if (iv_c is None or iv_p is None) else (iv_p - iv_c)

    # Pendiente de la sonrisa: d(IV)/d(delta) entre las dos alas traidas. Descriptiva.
    smile_slope = None
    allp = sorted(calls + puts)
    if len(allp) >= 2 and (allp[-1][0] - allp[0][0]) > 1e-9:
        smile_slope = (allp[-1][1] - allp[0][1]) / (allp[-1][0] - allp[0][0])

    return {
        "rr": rr,
        "drr_1d": None,            # requiere 2 fechas archivadas; hoy hay 1
        "z": None,                 # requiere 60 sesiones; se MUESTRA como None
        "smile_slope": smile_slope,
        "term": None,              # requiere >1 expiry comparable con banda suficiente
        "iv_src": (chain.get("meta") or {}).get("iv", "desconocido"),
        "extrapolated": 1 if extrapolated else 0,
        "n_hist": None,            # lo rellena main() con las fechas realmente archivadas
        "exp": exp,
        "suprimido_por": ("0.25 delta fuera de la banda traida" if extrapolated else None),
    }


def rr_history(sym):
    """Serie historica de RR 25 delta desde `trades.db iv_hist` (IV INVERTIDA POR BISECCION).

    Esta es la mitad que convierte el DATA-INSUFFICIENT en un numero: la IV del pasado no es
    irrecuperable, se reconstruye del precio del contrato (`scripts/iv_hist_build.py`).

    Devuelve `[(date, rr), ...]` ordenada. Lista VACIA si no hay tabla — nunca una serie
    inventada. **La IV invertida no se mezcla jamas con la del proveedor**: esta funcion lee
    solo filas con `iv_src='invertida_biseccion'`, y el RR de hoy (que viene del snapshot) se
    compara contra ella declarando ambas fuentes.
    """
    if not os.path.exists(DB):
        return []
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "SELECT date, exp, right, delta, iv FROM iv_hist "
            "WHERE sym=? AND iv IS NOT NULL AND delta IS NOT NULL "
            "AND iv_src='invertida_biseccion' ORDER BY date, exp", (sym,)).fetchall()
    except sqlite3.Error:
        return []                      # tabla ausente: serie vacia, no un cero plausible
    finally:
        con.close()

    by_day = {}
    for date, exp, right, delta, iv in rows:
        by_day.setdefault(date, {}).setdefault(exp, {"call": [], "put": []})
        side = "call" if str(right).upper().startswith("C") else "put"
        by_day[date][exp][side].append((abs(delta), iv))

    series = []
    for date in sorted(by_day):
        exp = sorted(by_day[date])[0]            # el vencimiento frontal de esa sesion
        wings = by_day[date][exp]
        iv_c, ext_c = interp_iv_at_delta(wings["call"], TARGET_DELTA)
        iv_p, ext_p = interp_iv_at_delta(wings["put"], TARGET_DELTA)
        if iv_c is None or iv_p is None or ext_c or ext_p:
            continue                             # sesion sin el 25 delta en banda: se OMITE
        series.append((date, iv_p - iv_c))
    return series


def zscore(x, sample):
    """z frente a la muestra. None si no hay `n` suficiente o si la serie es plana.

    La guarda de la desviacion es RELATIVA a proposito. Una serie constante no da `var == 0`
    en coma flotante: 60 copias de 0.02 suman 1.2000000000000002 y dejan una varianza residual
    de ~1e-35, que con un `var <= 0` se cuela y produce un **z gigantesco a partir de ruido de
    redondeo**. Un `z(drr) > 2` fabricado asi entraria como "refuerzo" de una decision de fade.
    """
    n = len(sample)
    if x is None or n < MIN_HIST_FOR_Z:
        return None
    mu = sum(sample) / n
    var = sum((s - mu) ** 2 for s in sample) / (n - 1)
    if var <= 0:
        return None
    sd = var ** 0.5
    if sd <= max(1e-12, 1e-9 * abs(mu)):     # serie plana: no hay escala contra la que medir
        return None
    return (x - mu) / sd


def main():
    dates = latest_dates()
    if not dates:
        print("skew: no hay cadenas archivadas en data/history — no hay veredicto",
              file=sys.stderr)
        return 2
    date = dates[0]
    n_hist = len(dates)

    syms = []
    for p in sorted(glob.glob(os.path.join(HIST, date, "chain_full_*.json"))):
        syms.append(os.path.basename(p)[len("chain_full_"):-len(".json")].upper())

    out, n_ok, n_supr, n_con_z, max_hist = {}, 0, 0, 0, 0
    for sym in syms:
        row = rr_for(load_chain(date, sym))
        if row is None:
            continue

        # --- historia reconstruida (IV invertida por biseccion) --------------------------
        hist = rr_history(sym)
        vals = [v for _, v in hist]
        row["n_hist"] = len(hist)
        row["hist_src"] = "iv_hist/invertida_biseccion" if hist else "ninguna"
        max_hist = max(max_hist, len(hist))
        if len(hist) >= 2 and row["rr"] is not None:
            row["drr_1d"] = row["rr"] - vals[-1]
        row["z"] = zscore(row["rr"], vals)
        if row["z"] is not None:
            n_con_z += 1

        if row["rr"] is None:
            n_supr += 1
        else:
            n_ok += 1
        out[sym] = row

    rep = {
        "generated_at": time.time(),
        "date": date,
        "n_hist_chain_dates": n_hist,
        "n_hist_sessions": max_hist,
        "min_hist_for_z": MIN_HIST_FOR_Z,
        "hist_src": "trades.db iv_hist (IV invertida por biseccion desde poly_opt_bars)",
        "veredicto": ("DATA-INSUFFICIENT" if n_con_z == 0 else "PARCIAL"),
        "por_que": (
            "z exige %d sesiones de superficie; la mejor serie reconstruida tiene %d. "
            "La IV del pasado SI se recupera (biseccion sobre el precio del contrato), lo que "
            "falta es MATERIA PRIMA: mas barras en poly_opt_bars. El z se publica como None "
            "mientras tanto y NO se rellena." % (MIN_HIST_FOR_Z, max_hist)),
        "syms_con_rr": n_ok,
        "syms_con_z": n_con_z,
        "syms_suprimidos": n_supr,
        "oi_historico": None,
        "oi_por_que": ("IMPOSIBLE en este plan a cualquier precio: el as_of del snapshot "
                       "devuelve OK e IGNORA la fecha. Muros/max-pain/GEX historico siguen "
                       "bloqueados y no se aproximan"),
        "voz": "OFF",
        "factor_en_direction_view": "NINGUNO",
        "skew": out,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    os.replace(tmp, OUT)                  # escritura atomica

    print(json.dumps({k: v for k, v in rep.items() if k != "skew"}, indent=1))
    print("DATA-INSUFFICIENT: %d/%d simbolos con RR medible, %d suprimidos por 0.25 delta "
          "fuera de banda. z=None en los %d (hacen falta %d sesiones)."
          % (n_ok, n_ok + n_supr, n_supr, n_ok + n_supr, MIN_HIST_FOR_Z), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
