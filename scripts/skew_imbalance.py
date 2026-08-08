#!/usr/bin/env python3
"""skew_imbalance.py — el "delta imbalance" de @astocks92 (The Architect), reproducido.

CORRECCION IMPORTANTE (2026-08-07): su "delta imbalance" NO es flujo de delta por minuto
(eso es lo que midio delta_imbalance_study.py). Es el desequilibrio del SKEW por strike,
que el mismo describe como el inventario del dealer:

  "Remember: SKEW is pricing in inventory."                                (2026-07-07)
  "$SPY >$750 is 28%+ Call side Skew + higher | Put side to $740 is 7%"    (2026-06-30)
  "Call skew runs from 19% to 25%+ for $1-$6+ | Put skew 4% a 6%"          (2026-07-14)
  "$QCOM: 85th Percentile CALL SKEW 25 Delta"                              (2026-07-12)
  "Dealer inventory Monday $QQQ y $SPY: Call side 3-6%. Put side 12-15%"   (2026-06-26)

O sea, dos medidas distintas y las dos se calculan aqui:
  1. SKEW POR DISTANCIA: cuanto mas cara esta la IV a $1..$N del spot frente a la ATM,
     por lado. Es lo que publica a diario.
  2. RISK REVERSAL 25 DELTA: IV(call 25d) - IV(put 25d), la version estandar, para poder
     percentilarla contra su propia historia como hace el con "85th percentile".

Fuente: data/history/<dia>/chain_full_<sym>.json (Polygon, IV y griegas MEDIDAS).
El percentil exige historia: con menos de MIN_DIAS sesiones se dice "sin percentil", jamas
se inventa uno. LOTE FUERA DE SESION.
"""
import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

MIN_DIAS = 30            # por debajo no hay percentil honesto (measured-probability)
PASOS = 6                # "$1 to $6" — su rejilla
OUT = "data/skew_imbalance.json"


def cargar(sym, dia):
    p = f"data/history/{dia}/chain_full_{sym.lower()}.json"
    if not os.path.exists(p):
        return None, None
    with open(p) as f:
        d = json.load(f)
    return d.get("results") or [], (d.get("meta") or {}).get("spot")


def contratos(rows, spot, expiry=None):
    """(expiry -> {(tipo,strike): (iv, delta, oi)}) solo con IV y delta MEDIDOS."""
    out = {}
    for r in rows:
        det = r.get("details") or {}
        iv = r.get("implied_volatility")
        gk = r.get("greeks") or {}
        dl = gk.get("delta")
        if iv is None or dl is None:
            continue                      # sin medida no entra; jamas se rellena
        e = det.get("expiration_date")
        k = det.get("strike_price")
        t = det.get("contract_type")
        if e is None or k is None or t not in ("call", "put"):
            continue
        out.setdefault(e, {})[(t, float(k))] = (float(iv), float(dl), r.get("open_interest") or 0)
    return out


def iv_atm(ch, spot):
    """IV ATM = media de la call y la put del strike mas cercano al spot."""
    ks = sorted({k for (_, k) in ch}, key=lambda k: abs(k - spot))
    if not ks:
        return None
    k = ks[0]
    vals = [ch[(t, k)][0] for t in ("call", "put") if (t, k) in ch]
    return (sum(vals) / len(vals)) if vals else None


def skew_por_distancia(ch, spot, pasos=PASOS):
    """Su medida diaria: % que la IV supera a la ATM, a $1..$pasos por encima (calls)
    y por debajo (puts). Devuelve (lista_calls, lista_puts, iv_atm)."""
    atm = iv_atm(ch, spot)
    if not atm:
        return None, None, None
    ks = sorted({k for (_, k) in ch})

    def cerca(objetivo, tipo):
        cand = [k for k in ks if (tipo, k) in ch]
        if not cand:
            return None
        k = min(cand, key=lambda k: abs(k - objetivo))
        return None if abs(k - objetivo) > 2.5 else ch[(tipo, k)][0]

    calls, puts = [], []
    for d in range(1, pasos + 1):
        c = cerca(spot + d, "call")
        p = cerca(spot - d, "put")
        calls.append(None if c is None else round(100 * (c / atm - 1), 1))
        puts.append(None if p is None else round(100 * (p / atm - 1), 1))
    return calls, puts, atm


def risk_reversal_25(ch):
    """IV(call 25 delta) - IV(put 25 delta), en puntos de vol. El estandar que permite
    percentilar ("85th Percentile CALL SKEW 25 Delta")."""
    c = [(abs(d - 0.25), iv) for (t, _), (iv, d, _) in ch.items() if t == "call" and d > 0]
    p = [(abs(abs(d) - 0.25), iv) for (t, _), (iv, d, _) in ch.items() if t == "put" and d < 0]
    if not c or not p:
        return None
    return round(100 * (min(c)[1] - min(p)[1]), 2)


def analiza(sym, dia, n_exp=2):
    rows, spot = cargar(sym, dia)
    if not rows or not spot:
        return None
    porexp = contratos(rows, spot)
    if not porexp:
        return None
    out = {"sym": sym.upper(), "dia": dia, "spot": round(spot, 2), "expiries": []}
    for e in sorted(porexp)[:n_exp]:
        ch = porexp[e]
        calls, puts, atm = skew_por_distancia(ch, spot)
        if calls is None:
            continue
        cv = [x for x in calls if x is not None]
        pv = [x for x in puts if x is not None]
        out["expiries"].append({
            "expiry": e, "n": len(ch),
            "iv_atm": round(atm, 4),
            "call_skew_pct": calls, "put_skew_pct": puts,
            "call_media": round(sum(cv) / len(cv), 1) if cv else None,
            "put_media": round(sum(pv) / len(pv), 1) if pv else None,
            "imbalance": (round(sum(cv) / len(cv) - sum(pv) / len(pv), 1)
                          if cv and pv else None),
            "rr25": risk_reversal_25(ch)})
    return out


def percentil(sym, valor, campo="rr25", exp_idx=0):
    """Percentil del valor contra la propia historia archivada. None si no hay MIN_DIAS."""
    dias = sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(f"data/history/*/chain_full_{sym.lower()}.json"))
    serie = []
    for d in dias:
        a = analiza(sym, d, n_exp=exp_idx + 1)
        if a and len(a["expiries"]) > exp_idx:
            v = a["expiries"][exp_idx].get(campo)
            if v is not None:
                serie.append(v)
    if len(serie) < MIN_DIAS or valor is None:
        return None, len(serie)
    serie.sort()
    return round(100 * sum(1 for x in serie if x <= valor) / len(serie)), len(serie)


def main():
    ap = argparse.ArgumentParser(description="skew / delta imbalance al estilo The Architect")
    ap.add_argument("syms", nargs="*", default=["SPY", "QQQ"])
    ap.add_argument("--dia", default=None, help="YYYY-MM-DD (por defecto el ultimo archivado)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = []
    for sym in a.syms:
        dia = a.dia
        if dia is None:
            dias = sorted(os.path.basename(os.path.dirname(p))
                          for p in glob.glob(f"data/history/*/chain_full_{sym.lower()}.json"))
            if not dias:
                print(f"{sym}: sin cadena archivada", file=sys.stderr)
                continue
            dia = dias[-1]
        r = analiza(sym, dia)
        if r is None:
            print(f"{sym} {dia}: cadena sin IV/delta legibles", file=sys.stderr)
            continue
        for e in r["expiries"]:
            p, n = percentil(sym, e.get("rr25"))
            e["rr25_percentil"] = p
            e["rr25_n_sesiones"] = n
            e["rr25_nota"] = None if p is not None else \
                f"sin percentil: {n} sesiones archivadas, hacen falta {MIN_DIAS}"
        res.append(r)

    if a.json:
        print(json.dumps(res, indent=1))
    else:
        for r in res:
            print(f"\n{r['sym']}  {r['dia']}  spot {r['spot']}")
            for e in r["expiries"]:
                cs = " ".join("—" if x is None else f"{x:+.0f}" for x in e["call_skew_pct"])
                ps = " ".join("—" if x is None else f"{x:+.0f}" for x in e["put_skew_pct"])
                print(f"  {e['expiry']}  IV ATM {e['iv_atm']:.3f}  ({e['n']} contratos)")
                print(f"     call skew $1..$6:  {cs}   media {e['call_media']}%")
                print(f"     put  skew $1..$6:  {ps}   media {e['put_media']}%")
                lado = "CALL" if (e["imbalance"] or 0) > 0 else "PUT"
                print(f"     IMBALANCE {e['imbalance']:+}%  -> lado {lado} mas caro"
                      f"   |  RR25 {e['rr25']} vol pts   |  {e['rr25_nota'] or 'percentil ' + str(e['rr25_percentil'])}")
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"asof": __import__("time").time(), "syms": res}, f, indent=1)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
