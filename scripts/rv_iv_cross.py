#!/usr/bin/env python3
"""rv_iv_cross.py — cruce Realized vs Implied Vol (la metrica de ARCHI: IV/RV).

Salida: data/rv_iv_spread.json {sym: {rv, iv, spread_pct, ratio, exp, dte, bars, signal}}
        + clave "_meta" (asof, omitidos y por que). La consume charts/live.html:4678.

FIX 2026-08-14 (dos bugs que daban SHORT_VOL en 20/20, RV de SPY = 0,21% anual):
  1. anualizacion: retornos de 1m se anualizan con sqrt(252*390), no sqrt(252) -> 19,7x
  2. IV: era la del PRIMER contrato del fichero (una cola, MU 138%), ahora ATM real
Fuera de sesion, con barras rancias, el simbolo se OMITE: mejor hueco que numero plausible.

Uso: python3 scripts/rv_iv_cross.py
"""
import json, os, sys, time, statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

BARS_RTH = 390                  # barras 1m de una sesion regular
ANN_1M = (252 * BARS_RTH) ** 0.5
MIN_BARS = 60                   # menos de 1h de camino no es una RV, es ruido
MAX_GAP_S = 120                 # salto mayor = hueco de sesion: ese retorno no entra
MAX_AGE_S = 6 * 3600            # barras mas viejas que esto = dato muerto, no se publica
MIN_DTE = 5                     # evita la IV del 0DTE para el cruce; si no hay, se usa la frontal

def load_fleet():
    with open("data/fleet.txt") as f:
        return f.read().split()

def rv_intraday(sym, n=BARS_RTH):
    """RV anualizada de las ultimas n barras 1m. (rv_pct, n_usadas, edad_s) o None."""
    try:
        rows = []
        with open(f"data/bars_{sym.lower()}_ibkr.txt") as f:
            for ln in f:
                if not ln.strip() or ln.startswith("#"):
                    continue
                p = ln.split()
                if len(p) >= 5:
                    rows.append((int(float(p[0])), float(p[4])))
    except Exception:
        return None
    if len(rows) < MIN_BARS + 1:
        return None
    rows = rows[-(n + 1):]
    age = time.time() - rows[-1][0]
    if age > MAX_AGE_S:
        return None
    rets = [st.log(rows[i][1] / rows[i - 1][1])
            for i in range(1, len(rows))
            if rows[i][0] - rows[i - 1][0] <= MAX_GAP_S and rows[i - 1][1] > 0]
    if len(rets) < MIN_BARS:
        return None
    return round(st.stdev(rets) * 100 * ANN_1M, 2), len(rets), int(age)

def iv_atm(sym):
    """IV ATM (media call/put del strike mas cercano al spot). (iv_pct, exp, dte) o None."""
    path = f"data/opt_chain_{sym.lower()}.txt"
    try:
        spot, rows = None, []
        with open(path) as f:
            for ln in f:
                if ln.startswith("#"):
                    if spot is None and " spot " in ln:
                        p = ln.split()
                        spot = float(p[p.index("spot") + 1])
                    continue
                p = ln.split()
                if len(p) < 8:
                    continue
                try:
                    k, right, exp, iv = float(p[0]), p[1], p[2], float(p[7])
                except ValueError:
                    continue
                if 0.01 < iv <= 5.0 and right in ("C", "P"):
                    rows.append((exp, k, right, iv))
    except Exception:
        return None
    if not spot or spot <= 0 or not rows:
        return None
    hoy = time.strftime("%Y%m%d")
    exps = sorted({e for e, _, _, _ in rows})
    def dte(e):
        try:
            return (time.mktime(time.strptime(e, "%Y%m%d")) - time.mktime(time.strptime(hoy, "%Y%m%d"))) / 86400
        except ValueError:
            return -1
    limpios = [e for e in exps if dte(e) >= MIN_DTE]
    exp = limpios[0] if limpios else exps[0]
    cand = [(k, r, iv) for e, k, r, iv in rows if e == exp]
    if not cand:
        return None
    k_atm = min({k for k, _, _ in cand}, key=lambda k: abs(k - spot))
    ivs = [iv for k, _, iv in cand if k == k_atm]
    if not ivs:
        return None
    return round(100 * sum(ivs) / len(ivs), 2), exp, round(dte(exp))

def compute_cross(sym):
    rv = rv_intraday(sym)
    iv = iv_atm(sym)
    if rv is None:
        return None, "sin barras frescas"
    if iv is None:
        return None, "sin IV ATM"
    rv_pct, n_bars, _ = rv
    iv_pct, exp, d = iv
    if rv_pct <= 0:
        return None, "rv nula"
    ratio = iv_pct / rv_pct
    signal = "SHORT_VOL" if ratio > 1.20 else "LONG_VOL" if ratio < 0.90 else "FAIR"
    return {"rv": rv_pct, "iv": iv_pct, "spread_pct": round(iv_pct - rv_pct, 1),
            "ratio": round(ratio, 2), "exp": exp, "dte": d, "bars": n_bars,
            "signal": signal}, None

def main():
    out, omitidos = {}, {}
    fleet = load_fleet()
    for sym in fleet:
        r, why = compute_cross(sym)
        if r:
            out[sym] = r
        else:
            omitidos[sym] = why
    out["_meta"] = {"asof": int(time.time()), "n": len(out), "omitidos": omitidos,
                    "ann": "sqrt(252*390) sobre retornos 1m"}
    tmp = "data/rv_iv_spread.json.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, "data/rv_iv_spread.json")
    print(f"[rv_iv_cross] {len(out) - 1}/{len(fleet)} símbolos medidos, {len(omitidos)} omitidos")

if __name__ == "__main__":
    main()
