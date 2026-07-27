#!/usr/bin/env python3
"""uw_gex_compare.py — referee: nuestro mapa GEX/DEX contra el de Unusual Whales,
POR PATA y con el SCOPE DECLARADO. Lote de archivo: solo lee y escribe, cero senal.

El neto NO se compara y el script se niega a publicarlo: `chain_full` es una ventana
(dte_max + banda de strikes) y `/greek-exposure/strike` de UW es el libro entero SIN
columna de expiry, o sea NO filtrable a nuestra ventana. Comparar netos de dos scopes
distintos ya dio un cambio de signo en MU. Se comparan call contra call y put contra
put sobre los strikes que los dos cubren, y el desajuste se publica como numero
(`cobertura_strikes`, `share_oi_fuera_banda`), no como nota al pie.

  ./venv/bin/python scripts/uw_gex_compare.py [--fecha 2026-07-26] [--syms QQQ SPY]
"""
import argparse
import datetime as dt
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_F = os.path.join(REPO, "data", "uw_vs_gex_compare.json")
MIN_STRIKES = 8   # por debajo de esto una correlacion es un adorno, no una medida


def fleet():
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        syms = f.read().split()
    if not syms:
        raise RuntimeError("data/fleet.txt VACIA")
    return [s.upper() for s in syms]


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    return _pearson(_ranks(xs), _ranks(ys))


def our_legs(chain_path):
    """Por strike: (call_gex, put_gex, call_dex, put_dex) en las convenciones ya
    publicadas en gex_snapshot (GEX $/1$ = gamma*OI*100*spot; DEX OI-larga = delta*OI*100*spot,
    calls +, puts -). Levanta si el fichero no sirve: media comparacion es peor que ninguna."""
    with open(chain_path) as f:
        blob = json.load(f)
    meta, rows = blob["meta"], blob["results"]
    spot = meta.get("spot")
    if not spot:
        raise RuntimeError(f"{chain_path}: sin spot en meta")
    per = {}
    n_sin_griegas = 0
    for r in rows:
        d, g = r.get("details") or {}, r.get("greeks") or {}
        oi = r.get("open_interest")
        k, typ = d.get("strike_price"), d.get("contract_type")
        gam, dlt = g.get("gamma"), g.get("delta")
        if k is None or typ not in ("call", "put") or oi is None:
            continue
        if gam is None or dlt is None:
            n_sin_griegas += 1
            continue
        e = per.setdefault(float(k), {"call_gex": 0.0, "put_gex": 0.0, "call_dex": 0.0, "put_dex": 0.0})
        sign = 1.0 if typ == "call" else -1.0
        e[f"{typ}_gex"] += sign * gam * oi * 100.0 * spot
        e[f"{typ}_dex"] += sign * dlt * oi * 100.0 * spot
    return per, {"spot": spot, "dte_max": meta.get("dte_max"), "exp_hasta": meta.get("exp_hasta"),
                 "banda": meta.get("band"), "n_contratos": len(rows), "n_sin_griegas": n_sin_griegas,
                 "greeks": meta.get("greeks"), "snapshot_local": meta.get("snapshot_local")}


def uw_legs(uw_path):
    with open(uw_path) as f:
        blob = json.load(f)
    rows = blob["payload"]["data"] if isinstance(blob.get("payload"), dict) else blob["payload"]
    per = {}
    for r in rows:
        try:
            k = float(r["strike"])
        except (KeyError, TypeError, ValueError):
            continue
        per[k] = {"call_gex": float(r["call_gex"]), "put_gex": float(r["put_gex"]),
                  "call_dex": float(r["call_delta"]), "put_dex": float(r["put_delta"])}
    return per, {"fecha_dato": (rows[0].get("date") if rows else None),
                 "n_strikes": len(per), "scope": "libro entero, sin columna de expiry -> NO filtrable"}


def compare_sym(sym, fecha):
    hd = os.path.join(REPO, "data", "history", fecha)
    chain = os.path.join(hd, f"chain_full_{sym.lower()}.json")
    uwf = os.path.join(hd, f"uw_greek_exposure_strike_{sym.lower()}.json")
    if not os.path.exists(chain) or not os.path.exists(uwf):
        return {"sym": sym, "estado": "SIN DATO",
                "falta": [p for p in (chain, uwf) if not os.path.exists(p)]}
    ours, ometa = our_legs(chain)
    theirs, umeta = uw_legs(uwf)
    common = sorted(set(ours) & set(theirs))
    res = {"sym": sym, "estado": "ok", "n_strikes_comunes": len(common),
           "cobertura_strikes_nuestros": round(len(common) / max(len(ours), 1), 4),
           "cobertura_strikes_uw": round(len(common) / max(len(theirs), 1), 4),
           "scope_nuestro": ometa, "scope_uw": umeta,
           "neto": "NO COMPARABLE: scopes distintos (ventana vs libro entero, UW sin expiry)"}
    if len(common) < MIN_STRIKES:
        res["estado"] = "MUESTRA CORTA"
        return res
    for pata in ("call_gex", "put_gex", "call_dex", "put_dex"):
        xs = [ours[k][pata] for k in common]
        ys = [theirs[k][pata] for k in common]
        res[pata] = {"spearman": spearman(xs, ys), "pearson": _pearson(xs, ys), "n": len(common)}
    return res


def main():
    ap = argparse.ArgumentParser(description="referee UW vs nuestro GEX/DEX, por pata y con scope declarado")
    ap.add_argument("--fecha", default=dt.date.today().isoformat())
    ap.add_argument("--syms", nargs="*")
    a = ap.parse_args()
    syms = [s.upper() for s in a.syms] if a.syms else fleet()

    out = {"_meta": {"fecha": a.fecha, "generado": dt.datetime.now().isoformat(timespec="seconds"),
                     "fuente_a": "gex propio (chain_full, griegas medidas polygon_directo)",
                     "fuente_b": "unusual_whales_trial /api/stock/{sym}/greek-exposure/strike",
                     "aviso": "SOLO por pata. El neto de los dos NO es comparable: distinto scope."},
           "syms": {}}
    print(f"{'sym':6s} {'n_k':>4s} {'cobNos':>7s} {'rho cG':>7s} {'rho pG':>7s} {'rho cD':>7s} {'rho pD':>7s}  scope_nuestro")
    fallos = 0
    for sym in syms:
        try:
            r = compare_sym(sym, a.fecha)
        except Exception as e:
            r = {"sym": sym, "estado": "ERROR", "motivo": f"{e.__class__.__name__}: {e}"}
        out["syms"][sym] = r
        if r["estado"] != "ok":
            fallos += 1
            print(f"{sym:6s} {r['estado']} {r.get('motivo','')}")
            continue
        def f(p):
            v = r[p]["spearman"]
            return "  n/d " if v is None else f"{v:+.3f}"
        print(f"{sym:6s} {r['n_strikes_comunes']:4d} {r['cobertura_strikes_nuestros']:7.2f} "
              f"{f('call_gex')} {f('put_gex')} {f('call_dex')} {f('put_dex')}  "
              f"dte<={r['scope_nuestro']['dte_max']} banda{r['scope_nuestro']['banda']}")

    tmp = OUT_F + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, indent=1)
    os.replace(tmp, OUT_F)
    okn = sum(1 for r in out["syms"].values() if r["estado"] == "ok")
    print(f"-> {okn}/{len(syms)} comparados -> {os.path.relpath(OUT_F, REPO)}"
          + (f"  ({fallos} sin dato/error)" if fallos else ""))
    return 0 if okn else 1


if __name__ == "__main__":
    sys.exit(main())
