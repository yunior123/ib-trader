#!/usr/bin/env python3
"""cage_lotto_scan.py — lotos de $10-30 en tickers baratos + score de JAULA.

DESCRIPTIVO. Mide, no vota. Por simbolo barato (spot <= MAX_SPOT):
  option-contracts?expiry=X  -> NBBO real, OI, dOI, volumen, lado agresor, IV
  greek-exposure/expiry      -> cuanta gamma MUERE el viernes vs la que queda
  max-pain por expiry        -> a donde rueda la gravedad tras el vencimiento
  stock-state                -> spot

Un contrato entra si el ASK (lo que se paga de verdad) cae en [MIN_ASK, MAX_ASK].
P(ITM) y P(profit) por Black-Scholes con la IV que publica UW; sin IV no hay fila.
Fallo de un simbolo = error del simbolo, jamas relleno con 0.

Uso: python3 scripts/cage_lotto_scan.py [--syms NOK OPEN] [--max-spot 45]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from fleet_cp_scan import f, get  # noqa: E402
from uw_premium import token  # noqa: E402

MIN_ASK, MAX_ASK = 0.10, 0.30
MIN_OI, MIN_VOL = 300, 50
MAX_SPREAD = 0.35
OUT = os.path.join(REPO, "data", "scan")


def ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs_probs(S, K, iv, T, right, be):
    """(P(ITM), P(profit), delta, gamma) o None si el input no permite calcularlo."""
    if not (S > 0 and K > 0 and iv and iv > 0 and T > 0):
        return None
    sig = iv * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / sig
    d2 = d1 - sig
    d2be = (math.log(S / be) - 0.5 * iv * iv * T) / sig if be > 0 else None
    npdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    gam = npdf / (S * sig)
    if right == "C":
        return ncdf(d2), (ncdf(d2be) if d2be is not None else None), ncdf(d1), gam
    return ncdf(-d2), (ncdf(-d2be) if d2be is not None else None), ncdf(d1) - 1.0, gam


def parse_osym(s):
    """NOK260807C00010000 -> ('2026-08-07', 'C', 10.0)"""
    i = 0
    while i < len(s) and not s[i].isdigit():
        i += 1
    body = s[i:]
    exp = "20%s-%s-%s" % (body[0:2], body[2:4], body[4:6])
    return exp, body[6], int(body[7:]) / 1000.0


def scan_sym(sym, tok, w1, w2):
    st = get("/api/stock/%s/stock-state" % sym, tok)
    st = st[0] if isinstance(st, list) else st
    spot = f(st.get("close")) or f(st.get("last")) or f(st.get("price"))
    if spot is None:
        raise RuntimeError("%s sin spot" % sym)

    gex = get("/api/stock/%s/greek-exposure/expiry" % sym, tok)
    by_exp, tot_abs = {}, 0.0
    for r in gex:
        cg, pg = f(r.get("call_gex")), f(r.get("put_gex"))
        if cg is None or pg is None:
            continue
        a = abs(cg) + abs(pg)
        by_exp[r["expiry"]] = {"abs": a, "net": cg + pg, "dte": r.get("dte"),
                               "charm": (f(r.get("call_charm")) or 0) + (f(r.get("put_charm")) or 0)}
        tot_abs += a
    if tot_abs <= 0:
        raise RuntimeError("%s sin gamma" % sym)

    out = {"sym": sym, "spot": spot, "gamma_total_abs": tot_abs,
           "gamma_share": {e: v["abs"] / tot_abs for e, v in by_exp.items()},
           "gamma_net": {e: v["net"] for e, v in by_exp.items()},
           "charm": {e: v["charm"] for e, v in by_exp.items()},
           "expiries": {}, "lottos": []}

    for exp in (w1, w2):
        if exp is None:
            continue
        rows = get("/api/stock/%s/option-contracts?expiry=%s&limit=500" % (sym, exp), tok)
        # MEDIDO 2026-08-05: /max-pain IGNORA ?expiry y devuelve una fila POR vencimiento;
        # coger mp[0] daba siempre el 08-07. Se filtra por el campo expiry de la fila.
        mp = get("/api/stock/%s/max-pain" % sym, tok)
        mpv, mp_why = None, None
        if isinstance(mp, list):
            row = next((r for r in mp if (r.get("expiry") or r.get("date")) == exp), None)
            if row is None:
                mp_why = "expiry %s ausente en /max-pain (%d filas)" % (exp, len(mp))
            else:
                mpv = f(row.get("max_pain")) or f(row.get("price"))
                if mpv is None:
                    mp_why = "fila de %s sin max_pain/price" % exp
        else:
            mp_why = "/max-pain no devolvio lista"

        T = max((dt.date.fromisoformat(exp) - dt.date.today()).days, 0) / 365.0
        # el dia del vencimiento aun tiene horas: piso de medio dia
        T = max(T, 0.5 / 365.0)
        agg = {"call_oi": {}, "put_oi": {}, "vol_c": 0, "vol_p": 0,
               "ask_c": 0, "bid_c": 0, "ask_p": 0, "bid_p": 0}
        # MEDIDO 2026-08-05: OI enorme con ask<=0.05 = gamma ~0 (INTC P55, SPCX C330); fuera del muro
        wall_c, wall_p, oi_nominal = {}, {}, {"C": 0, "P": 0}
        for r in rows:
            osym = r.get("option_symbol")
            if not osym:
                continue
            e, right, K = parse_osym(osym)
            if e != exp:
                continue
            oi = int(r.get("open_interest") or 0)
            vol = int(r.get("volume") or 0)
            av, bv = int(r.get("ask_volume") or 0), int(r.get("bid_volume") or 0)
            (agg["call_oi"] if right == "C" else agg["put_oi"])[K] = oi
            ask_raw = f(r.get("nbbo_ask"))
            if ask_raw is not None and ask_raw <= 0.05:
                oi_nominal[right] += oi
            else:
                (wall_c if right == "C" else wall_p)[K] = oi
            if right == "C":
                agg["vol_c"] += vol
                agg["ask_c"] += av
                agg["bid_c"] += bv
            else:
                agg["vol_p"] += vol
                agg["ask_p"] += av
                agg["bid_p"] += bv

            bid, ask = f(r.get("nbbo_bid")), f(r.get("nbbo_ask"))
            iv = f(r.get("implied_volatility"))
            if bid is None or ask is None or ask <= 0:
                continue
            if not (MIN_ASK <= ask <= MAX_ASK):
                continue
            mid = (bid + ask) / 2.0
            spr = (ask - bid) / mid if mid > 0 else None
            if oi < MIN_OI or vol < MIN_VOL or spr is None or spr > MAX_SPREAD:
                continue
            be = K + ask if right == "C" else K - ask
            pr = bs_probs(spot, K, iv, T, right, be)
            if pr is None:
                continue
            pitm, pprof, dlt, gam = pr
            # peaje = % que debe moverse el SUBYACENTE para pagar la horquilla (medido: bueno <=0.60)
            peaje = round((ask - bid) / (abs(dlt) * spot) * 100, 2) if abs(dlt) >= 0.02 else None
            # suelo del tick medido: 0.20 (mismo numero que optgate.MIN_MID), no 0.25
            ganga = bool(mid >= 0.20 and vol >= 200 and spr <= 0.05
                         and peaje is not None and peaje <= 0.60)
            out["lottos"].append({
                "osym": osym, "exp": exp, "right": right, "strike": K,
                "bid": bid, "ask": ask, "cost": round(ask * 100, 2),
                "spread_pct": round(spr * 100, 1), "oi": oi, "prev_oi": int(r.get("prev_oi") or 0),
                "doi": oi - int(r.get("prev_oi") or 0), "vol": vol,
                "ask_vol": av, "bid_vol": bv, "aggr": av - bv,
                "sweep": int(r.get("sweep_volume") or 0),
                "prem_usd": f(r.get("total_premium")),
                "iv": iv, "delta": round(dlt, 3), "gamma": gam,
                "dist_pct": round((K - spot) / spot * 100, 2),
                "be": round(be, 2), "be_pct": round((be - spot) / spot * 100, 2),
                "p_itm": round(pitm, 3), "p_profit": round(pprof, 3) if pprof else None,
                "sig_move_pct": round(iv * math.sqrt(T) * 100, 2) if iv else None,
                "peaje_pct": peaje, "ganga_limpia": ganga,
            })

        cw = max(wall_c.items(), key=lambda kv: kv[1], default=(None, 0))
        pw = max(wall_p.items(), key=lambda kv: kv[1], default=(None, 0))
        # max pain propio DESDE el OI de ESTE vencimiento (control del endpoint que ignora expiry)
        ks = sorted(set(agg["call_oi"]) | set(agg["put_oi"]))
        mp_own = None
        if ks:
            def pain(S):
                return sum(agg["call_oi"].get(k, 0) * max(S - k, 0) +
                           agg["put_oi"].get(k, 0) * max(k - S, 0) for k in ks)
            mp_own = min(ks, key=pain)
        tot_by_k = {k: agg["call_oi"].get(k, 0) + agg["put_oi"].get(k, 0) for k in ks}
        pin_k = max(tot_by_k, key=tot_by_k.get) if tot_by_k else None
        out["expiries"][exp] = {
            "max_pain": mpv, "max_pain_why": mp_why, "max_pain_own": mp_own,
            "oi_nominal_sin_gamma": oi_nominal,
            "pin_strike": pin_k, "pin_oi": tot_by_k.get(pin_k) if pin_k else None,
            "pin_dist_pct": round((pin_k - spot) / spot * 100, 2) if pin_k else None,
            "call_wall": cw[0], "call_wall_oi": cw[1],
            "put_wall": pw[0], "put_wall_oi": pw[1],
            "call_oi_tot": sum(agg["call_oi"].values()), "put_oi_tot": sum(agg["put_oi"].values()),
            "vol_c": agg["vol_c"], "vol_p": agg["vol_p"],
            "aggr_c": agg["ask_c"] - agg["bid_c"], "aggr_p": agg["ask_p"] - agg["bid_p"],
            "gamma_share": out["gamma_share"].get(exp),
            "oi_by_strike": {str(k): [agg["call_oi"].get(k, 0), agg["put_oi"].get(k, 0)]
                             for k in ks},
        }
    out["lottos"].sort(key=lambda d: -(d["p_profit"] or 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--syms", nargs="*")
    ap.add_argument("--max-spot", type=float, default=45.0)
    a = ap.parse_args()

    tok = token()
    if a.syms:
        syms = [s.upper() for s in a.syms]
    else:
        bar = open(os.path.join(REPO, "data", "bargain_fleet.txt")).read().split()
        fle = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
        syms = sorted(set(bar) | set(fle))

    today = dt.date.today()
    fri = today + dt.timedelta(days=(4 - today.weekday()) % 7)
    w1, w2 = fri.isoformat(), (fri + dt.timedelta(days=7)).isoformat()

    res, errs = [], {}
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(scan_sym, s, tok, w1, w2): s for s in syms}
        for fu in cf.as_completed(futs):
            s = futs[fu]
            try:
                r = fu.result()
                if r["spot"] <= a.max_spot:
                    res.append(r)
            except Exception as e:
                errs[s] = str(e)[:120]

    res.sort(key=lambda r: r["sym"])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "cage_lotto_%s.json" % today.isoformat())
    with open(path, "w") as fh:
        json.dump({"ts": dt.datetime.now().isoformat(timespec="seconds"), "w1": w1, "w2": w2,
                   "doi_sesion": "anterior (OI de UW = cierre de ayer)",
                   "max_spot": a.max_spot, "syms": res, "errors": errs}, fh, indent=1)
    print("escrito %s | %d simbolos | %d errores" % (path, len(res), len(errs)))
    if errs:
        print("errores:", json.dumps(errs, indent=1))


if __name__ == "__main__":
    main()
