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
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
HIST = os.path.join(REPO, "data", "history")
OUT = os.path.join(REPO, "data", "skew.json")

TARGET_DELTA = 0.25
MIN_HIST_FOR_Z = 60          # la ficha: z es NULL hasta 60 sesiones, y ese NULL se muestra


def latest_dates():
    """Fechas con cadenas archivadas, de mas nueva a mas vieja."""
    if not os.path.isdir(HIST):
        return []
    ds = [d for d in sorted(os.listdir(HIST), reverse=True)
          if os.path.isdir(os.path.join(HIST, d))
          and glob.glob(os.path.join(HIST, d, "chain_full_*.json"))]
    return ds


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

    out, n_ok, n_supr = {}, 0, 0
    for sym in syms:
        row = rr_for(load_chain(date, sym))
        if row is None:
            continue
        row["n_hist"] = n_hist
        if row["rr"] is None:
            n_supr += 1
        else:
            n_ok += 1
        out[sym] = row

    rep = {
        "generated_at": time.time(),
        "date": date,
        "n_hist_sessions": n_hist,
        "min_hist_for_z": MIN_HIST_FOR_Z,
        "veredicto": "DATA-INSUFFICIENT",
        "por_que": (
            "z exige %d sesiones de superficie y hay %d; la tabla iv_hist no existe. "
            "El z se publica como None y NO se rellena." % (MIN_HIST_FOR_Z, n_hist)),
        "syms_con_rr": n_ok,
        "syms_suprimidos": n_supr,
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
