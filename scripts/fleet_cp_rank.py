#!/usr/bin/env python3
"""fleet_cp_rank.py — ordena el barrido de fleet_cp_scan.py de alcista a bajista. DESCRIPTIVO.

COMO SE ORDENA (y por que asi):
La killlist de la casa prohibe el score compuesto de z-scores con pesos a mano y el ranking
transversal con autoridad sobre una flota correlacionada. Aqui NO hay pesos ajustados: son
5 votos de VALOR IGUAL (+1/0/−1), umbrales fijos A PRIORI, cada uno de una FAMILIA DE DATO
DISTINTA, y los 5 se publican por separado. El orden es la suma de votos; los empates los
rompe la magnitud continua del voto de flujo. No es una probabilidad y no se presenta como tal.

  V1 FLUJO      premium firmado del dia / premium bruto (ambos vencimientos objetivo)
  V2 ΔOI        posicion nueva calls vs puts — OI de la SESION ANTERIOR (la OCC publica t+1)
  V3 MAX PAIN   spot vs max pain del vencimiento de la semana
  V4 MUROS      distancia relativa al muro de calls vs al de puts
  V5 BALLENAS   premium firmado por lado agresor de las alertas del vencimiento objetivo

C/P ratio: SE MUESTRA SIEMPRE (es lo que se pidio) pero NO VOTA. Medido hoy en NOK: C/P 8.9
con las calls pegadas al BID (vendidas) — el ratio dice "hay calls", el lado agresor dice
quien las quiere. Vota el lado agresor, no el ratio.
Dark pool: DESCRIPTIVO, sin voto (killlist #3: la replica bayesiana pone su edge en ~0).
Earnings: VETO marcado, nunca un voto.
"""
import argparse
import datetime as dt
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = os.path.join(REPO, "data", "scan", "cp_scan_latest.json")

# Umbrales de MATERIALIDAD, no de acierto: ninguno se ajusto contra un resultado. --sens
# barre x0.66/x1/x1.66 y publica la concordancia del orden (killlist test #4).
T_FLOW = 0.05      # |firmado|/bruto — 5% del premium bruto del dia. La mediana transversal
                   # de |ratio| medida el 2026-08-05 fue 0.048: separa destacar de ruido de fondo.
T_DOI = 0.20       # (doi_call − doi_put)/(|doi_call| + |doi_put|)
T_MAXPAIN = 0.005  # |spot − max_pain|/spot: medio punto porcentual
T_WALL = 0.15      # asimetria de distancias a los muros EFECTIVOS
T_WHALE = 100_000  # $ firmados de ballenas
BAND = 0.15        # los muros que votan son los LOCALES: el mayor OI dentro de ±15% del spot.
                   # Sin banda, el "techo" de POET salia a $40 con el spot en $8.21 (OI de
                   # lotto en cola larga) y todo nombre meme votaba alcista por construccion.


def local_walls(e, spot, band=BAND):
    """(suelo, techo) LOCALES desde el perfil de OI: mayor put_oi por debajo y mayor call_oi
    por encima, ambos dentro de ±band. None si de ese lado no hay nada en la banda."""
    prof = ((e or {}).get("walls") or {}).get("profile")
    if not prof or not spot:
        return None, None
    lo, hi = spot * (1 - band), spot * (1 + band)
    dn = [p for p in prof if lo <= p["k"] < spot and p["poi"] > 0]
    up = [p for p in prof if spot < p["k"] <= hi and p["coi"] > 0]
    suelo = max(dn, key=lambda p: p["poi"]) if dn else None
    techo = max(up, key=lambda p: p["coi"]) if up else None
    return (suelo["k"] if suelo else None), (techo["k"] if techo else None)


def gross_and_signed(sym):
    """(firmado, bruto) del flujo de opciones del DIA, toda la cadena. None si no hay dato.

    Antes se sumaba w1 + w2 de flow-per-strike; MEDIDO 2026-08-05 ese endpoint ignora
    `expiry`, asi que la suma contaba el mismo total del dia DOS VECES."""
    fl = sym.get("flow_day")
    if not fl:
        return None, None
    g = fl["call_prem_ask"] + fl["call_prem_bid"] + fl["put_prem_ask"] + fl["put_prem_bid"]
    return fl["signed_prem"], g


def doi_pair(sym):
    c = p = 0
    seen = False
    for tag in ("w1", "w2"):
        ch = ((sym.get("exp") or {}).get(tag) or {}).get("chain")
        if not ch:
            continue
        seen = True
        c += ch["doi_call"]
        p += ch["doi_put"]
    return (c, p) if seen else (None, None)


def votes(sym, k=1.0):
    """5 votos independientes. Cada uno None si su dato falta (jamas 0 fabricado)."""
    v = {}
    spot = sym.get("spot")

    s, g = gross_and_signed(sym)
    if g and g > 0:
        ratio = s / g
        v["V1_flujo"] = (1 if ratio > T_FLOW * k else (-1 if ratio < -T_FLOW * k else 0), round(ratio, 3))
    else:
        v["V1_flujo"] = (None, None)

    dc, dp = doi_pair(sym)
    if dc is not None and (abs(dc) + abs(dp)) > 0:
        r = (dc - dp) / (abs(dc) + abs(dp))
        v["V2_doi"] = (1 if r > T_DOI * k else (-1 if r < -T_DOI * k else 0), round(r, 3))
    else:
        v["V2_doi"] = (None, None)

    w1 = sym.get("exp_w1")
    mp = (sym.get("max_pain") or {}).get(w1)
    if mp and spot:
        d = (mp - spot) / spot                      # iman por encima = +
        v["V3_maxpain"] = (1 if d > T_MAXPAIN * k else (-1 if d < -T_MAXPAIN * k else 0), round(d, 4))
    else:
        v["V3_maxpain"] = (None, None)

    # Muros LOCALES: techo = calls por ENCIMA, suelo = puts por DEBAJO, ambos dentro de la banda.
    # Un muro de puts por encima del spot no es un suelo — es un iman. Sin uno de los dos lados
    # el voto es None (no se fabrica una asimetria con un solo muro).
    suelo, techo = local_walls((sym.get("exp") or {}).get("w1"), spot)
    if spot and suelo and techo:
        d_techo = (techo - spot) / spot
        d_suelo = (spot - suelo) / spot
        tot = d_techo + d_suelo
        # mas cerca del SUELO = rebote (+1) ; mas cerca del TECHO = tope (−1)
        asym = (d_techo - d_suelo) / tot if tot else 0.0
        v["V4_muros"] = (1 if asym > T_WALL * k else (-1 if asym < -T_WALL * k else 0), round(asym, 3))
    else:
        v["V4_muros"] = (None, None)

    wh = sym.get("whales")
    if wh and wh.get("target_n"):
        ts = wh["target_signed"]
        v["V5_ballenas"] = (1 if ts > T_WHALE * k else (-1 if ts < -T_WHALE * k else 0), round(ts))
    elif wh is not None:
        v["V5_ballenas"] = (0, 0)
    else:
        v["V5_ballenas"] = (None, None)
    return v


def score(v):
    return sum(x[0] for x in v.values() if x[0] is not None)


def row(sym, k=1.0):
    v = votes(sym, k)
    s, g = gross_and_signed(sym)
    day = sym.get("day") or {}
    ca, cb = day.get("call_ask"), day.get("call_bid")
    pa, pb = day.get("put_ask"), day.get("put_bid")
    return {
        "sym": sym["sym"], "spot": sym.get("spot"), "chg": sym.get("chg_pct"),
        "score": score(v), "votes": v,
        "cp_vol": day.get("cp_vol"),
        "signed_day": day.get("signed_prem"),
        "signed_tgt": s, "gross_tgt": g,
        "call_agg": round((ca - cb) / (ca + cb), 3) if ca is not None and (ca + cb) else None,
        "put_agg": round((pa - pb) / (pa + pb), 3) if pa is not None and (pa + pb) else None,
        "net_delta": day.get("net_delta"),
        "earnings": sym.get("earnings"),
        "dp": sym.get("dp"), "whales": sym.get("whales"),
        "exp_w1": sym.get("exp_w1"), "exp_w2": sym.get("exp_w2"),
        "max_pain": sym.get("max_pain"), "exp": sym.get("exp"),
    }


def order(rows):
    return sorted(rows, key=lambda r: (-r["score"],
                                       -(r["votes"]["V1_flujo"][1] or 0.0),
                                       -(r["signed_tgt"] or 0.0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=SCAN)
    ap.add_argument("--group", choices=("fleet", "bargain", "all"), default="all")
    ap.add_argument("--sens", action="store_true", help="curva de sensibilidad de umbrales")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    d = json.load(open(a.scan))
    fleet, bargain = set(d["fleet"]), set(d["bargain"])
    pool = {"fleet": fleet, "bargain": bargain, "all": fleet | bargain}[a.group]
    rows = [row(s) for k, s in d["syms"].items() if k in pool and not s.get("errors")]
    bad = [k for k, s in d["syms"].items() if k in pool and s.get("errors")]
    rows = order(rows)

    if a.sens:
        base = [r["sym"] for r in rows]
        print("curva de sensibilidad (killlist test #4) — orden con umbrales x0.66 / x1 / x1.66")
        for k in (0.66, 1.0, 1.66):
            rr = order([row(s) for kk, s in d["syms"].items() if kk in pool and not s.get("errors")]
                       if k == 1.0 else
                       [row(s, k) for kk, s in d["syms"].items() if kk in pool and not s.get("errors")])
            names = [r["sym"] for r in rr]
            tau = sum(1 for i in range(len(names)) for j in range(i + 1, len(names))
                      if base.index(names[i]) < base.index(names[j]))
            n = len(names)
            pairs = n * (n - 1) / 2
            print("  x%.2f  concordancia con base: %.1f%%   top5: %s" %
                  (k, 100.0 * tau / pairs if pairs else 100.0, " ".join(names[:5])))
        return

    if a.json:
        print(json.dumps({"generated_at": d["generated_at"], "rows": rows}, default=str))
        return

    print("# %s — %s (%s)  scan %s" % (a.group.upper(), d["today"], d["generated_at"], a.scan))
    print("%-6s %5s %6s %7s %8s %10s %6s %6s  %s" %
          ("SYM", "px", "chg%", "score", "C/P", "firm.$obj", "cAgg", "pAgg", "votos V1..V5 / earn"))
    for r in rows:
        vv = "".join({1: "+", 0: "·", -1: "−", None: "?"}[r["votes"][k][0]]
                     for k in ("V1_flujo", "V2_doi", "V3_maxpain", "V4_muros", "V5_ballenas"))
        e = r["earnings"]
        etag = ""
        if e and e["date"] <= (dt.date.fromisoformat(d["today"]) + dt.timedelta(days=12)).isoformat():
            etag = " ER %s%s" % (e["date"][5:], "/" + (e["time"] or "?")[:4])
        print("%-6s %5s %6s %+7d %8s %10s %6s %6s  %s%s" %
              (r["sym"], r["spot"], r["chg"], r["score"],
               r["cp_vol"], ("%.0fk" % (r["signed_tgt"] / 1000)) if r["signed_tgt"] is not None else "s/d",
               r["call_agg"], r["put_agg"], vv, etag))
    if bad:
        print("\nSIN DATO (errores en el scan): %s" % " ".join(bad))


if __name__ == "__main__":
    main()
