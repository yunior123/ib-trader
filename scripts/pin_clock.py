#!/usr/bin/env python3
"""pin_clock.py — OLA 1 feature #14: max pain estructural, DESCRIPTIVO y sin probabilidad.

POR QUE VALE LA PENA: no necesita griegas en absoluto, asi que es el unico nivel estructural
que funciona en NOK (4 strikes), DRAM, SPCX y SKHY, donde toda computacion gamma es ruido. Y
su salida es una PROHIBICION que ya creemos: OI monstruo a +-1 strike del spot = pin -> 0DTE
comprado prohibido ahi.

MATEMATICA (pasos del doc):
  1. pain(K*) = SUM_{K<K*} callOI(K)*(K*-K)*100 + SUM_{K>K*} putOI(K)*(K-K*)*100 sobre TODOS
     los expiries hasta el proximo viernes, DESDE EL SNAPSHOT COMPLETO (Polygon).
     max_pain = argmin pain.
  2. width = intervalo MODAL de strikes.
  3. pin = max_pain solo si |max_pain - abs_wall| <= 1 strike Y SUM(OI en +-2 strikes) >= min_oi
     (5000 en ETF de indice liquido / 1000 en nombre individual). Si no, pin = null.
  4. zone = [pin - width/4, pin + width/4].
  5. verdict = PIN_DAY solo si pin != null Y el abs_wall es del tipo PIN. Un abs_wall
     TRAMPILLA no es un pin: es una trampilla -> RELEASE.

POR QUE SOLO EL SNAPSHOT COMPLETO: la cadena de IBKR trae una banda de +-1,45% alrededor del
spot (medido), y calcular max pain dentro de una ventana centrada en el spot lo empuja
MECANICAMENTE hacia el spot. Por eso, si no hay chain_full_<sym>.json de Polygon, max_pain
sale null con reason='sin_cadena_completa'. Se publica ademas max_pain_ibkr_band con su
band_pct SOLO como diagnostico, y JAMAS entra en el veredicto (queda marcado biased=true).

LO QUE NO SE PUBLICA Y POR QUE:
  - p_pin: null SIEMPRE. Tenemos 4 viernes de expiry en el histórico; publicar una
    probabilidad de pin con 4 observaciones seria inventarla.
  - corr_abs_wall_60d: null hasta que haya 60 dias de max_pain archivado. El PRIMER test de
    esta feature no es de edge, es de COLINEALIDAD: si |rho(max_pain, abs_wall)| > 0.9 la
    feature es un re-etiquetado del abs_wall y MUERE. `--colinearity` lo calcula sobre la
    flota y dice cuantos syms entraron; con n<10 no concluye nada.

Uso:
  ./venv/bin/python scripts/pin_clock.py --all
  ./venv/bin/python scripts/pin_clock.py --sym QQQ --print
  ./venv/bin/python scripts/pin_clock.py --colinearity

SEÑAL-SOLAMENTE: lee cadenas y niveles, escribe json. Cero red, cero ordenes.
"""
import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)


def _sibling(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CUBE = _sibling("chain_cube_archive")

CONTRACT_MULT = 100
# ETFs de indice liquidos: el suelo de OI alto tiene sentido. El resto (nombres individuales y
# tematicos finos como DRAM/SPCX/SKHY) usa 1000 o el max pain salta de strike cada dia.
INDEX_LIKE = {"QQQ", "SPY", "SMH", "XLK"}
MIN_OI_INDEX = 5000
MIN_OI_NAME = 1000
COLINEARITY_KILL = 0.9


def next_friday(d=None):
    d = d or dt.date.today()
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def strike_width(strikes):
    """Intervalo MODAL entre strikes consecutivos. None con menos de 2 strikes."""
    ks = sorted(set(strikes))
    if len(ks) < 2:
        return None
    diffs = [round(ks[i + 1] - ks[i], 6) for i in range(len(ks) - 1)]
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return None
    return collections.Counter(diffs).most_common(1)[0][0]


def pain_profile(rows, exp_max=None):
    """{K*: pain} sobre las filas con OI. exp_max = YYYYMMDD inclusive."""
    call_oi = collections.defaultdict(float)
    put_oi = collections.defaultdict(float)
    for r in rows:
        if r.oi is None or r.oi <= 0:
            continue
        if exp_max is not None and r.exp > exp_max:
            continue
        (call_oi if r.right == "C" else put_oi)[r.strike] += r.oi
    strikes = sorted(set(list(call_oi) + list(put_oi)))
    if not strikes:
        return {}, call_oi, put_oi
    prof = {}
    for kt in strikes:
        pain = 0.0
        for k, oi in call_oi.items():
            if k < kt:
                pain += oi * (kt - k) * CONTRACT_MULT
        for k, oi in put_oi.items():
            if k > kt:
                pain += oi * (k - kt) * CONTRACT_MULT
        prof[kt] = pain
    return prof, call_oi, put_oi


def max_pain_of(rows, exp_max=None):
    prof, call_oi, put_oi = pain_profile(rows, exp_max)
    if not prof:
        return None, None, call_oi, put_oi
    mp = min(prof.items(), key=lambda kv: kv[1])[0]
    return mp, prof, call_oi, put_oi


def oi_within(call_oi, put_oi, center, width, n_strikes=2):
    if center is None or not width:
        return None
    lo, hi = center - n_strikes * width, center + n_strikes * width
    tot = 0.0
    for d in (call_oi, put_oi):
        for k, oi in d.items():
            if lo - 1e-9 <= k <= hi + 1e-9:
                tot += oi
    return tot


def levels_of(sym):
    p = os.path.join("charts", "data", "levels_%s.json" % sym.lower())
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def abs_wall_sign(lv):
    """'+' (pin) / '-' (trampilla) / None. abs_wall_kind es lo que ya publica chart_levels;
    si no esta, el signo del gex del muro. Nunca se adivina un '+'."""
    if not lv:
        return None
    kind = (lv.get("abs_wall_kind") or "").lower()
    if kind == "pin":
        return "+"
    if kind in ("trampilla", "trapdoor"):
        return "-"
    g = lv.get("abs_wall_gex")
    if g is None:
        g = lv.get("abs_wall_net")
    if g is None:
        return None
    return "+" if g >= 0 else "-"


def pin_clock(sym, date=None, now=None):
    now = now or time.time()
    sym = sym.upper()
    out = {"sym": sym, "asof": int(now), "oi_src": None, "exp_max": None,
           "max_pain": None, "max_pain_ibkr_band": None, "band_pct": None,
           "abs_wall": None, "abs_wall_sign": None, "spot": None,
           "pin": None, "width": None, "zone": None, "oi_in_zone": None,
           "min_oi_required": MIN_OI_INDEX if sym in INDEX_LIKE else MIN_OI_NAME,
           "verdict": "NEUTRAL", "reason": None,
           "zero_dte_buy_forbidden": False,
           "corr_abs_wall_60d": None, "p_pin": None,
           "nota": "descriptivo: p_pin=null (4 viernes de historico) y corr_abs_wall_60d=null "
                   "(sin archivo de max_pain). El primer test de esta feature es COLINEALIDAD "
                   "con abs_wall, no edge."}
    lv = levels_of(sym)
    out["abs_wall"] = (lv or {}).get("abs_wall")
    out["abs_wall_sign"] = abs_wall_sign(lv)
    out["spot"] = (lv or {}).get("spot")
    exp_max = int(next_friday().strftime("%Y%m%d"))
    out["exp_max"] = exp_max

    # diagnostico con la banda de IBKR: NUNCA entra en el veredicto
    live = CUBE.latest_chain(sym)
    if live:
        try:
            snap = CUBE.read_chain(live)
            if out["spot"] is None:
                out["spot"] = snap.meta.get("spot")
            mp_b, _prof, _c, _p = max_pain_of(snap.rows, exp_max)
            out["max_pain_ibkr_band"] = mp_b
            ks = [r.strike for r in snap.rows]
            sp = snap.meta.get("spot") or out["spot"]
            if ks and sp:
                out["band_pct"] = round(100.0 * (max(ks) - min(ks)) / 2.0 / sp, 3)
            out["band_biased"] = True
        except (ValueError, OSError):
            pass

    fc = CUBE.full_chain_path(sym, date)
    if not fc:
        out["reason"] = "sin_cadena_completa"
        return out
    try:
        full = CUBE.read_chain(fc)
    except (ValueError, OSError) as e:
        out["reason"] = "cadena_completa_ilegible: %s" % e
        return out
    out["oi_src"] = full.meta["src"]
    out["full_chain"] = fc
    if out["spot"] is None:
        out["spot"] = full.meta.get("spot")
    mp, prof, call_oi, put_oi = max_pain_of(full.rows, exp_max)
    if mp is None:
        out["reason"] = "sin_oi_hasta_%d" % exp_max
        return out
    out["max_pain"] = mp
    w = strike_width([r.strike for r in full.rows if r.exp <= exp_max])
    out["width"] = w
    out["contracts_used"] = sum(1 for r in full.rows if r.exp <= exp_max and r.oi)

    oi_zone = oi_within(call_oi, put_oi, mp, w, 2)
    out["oi_in_zone"] = None if oi_zone is None else round(oi_zone)
    if out["abs_wall"] is None:
        out["reason"] = "sin_abs_wall"
        return out
    if not w:
        out["reason"] = "sin_width"
        return out
    near_wall = abs(mp - out["abs_wall"]) <= w + 1e-9
    enough_oi = oi_zone is not None and oi_zone >= out["min_oi_required"]
    if not near_wall:
        out["reason"] = "max_pain lejos del abs_wall (%.2f vs %.2f, width %.2f)" % (
            mp, out["abs_wall"], w)
        return out
    if not enough_oi:
        out["reason"] = "OI insuficiente en +-2 strikes (%s < %d)" % (
            out["oi_in_zone"], out["min_oi_required"])
        return out
    out["pin"] = mp
    out["zone"] = [round(mp - w / 4.0, 4), round(mp + w / 4.0, 4)]
    if out["abs_wall_sign"] == "+":
        out["verdict"] = "PIN_DAY"
    elif out["abs_wall_sign"] == "-":
        out["verdict"] = "RELEASE"
        out["reason"] = "abs_wall TRAMPILLA: no es pin, es trampilla"
    else:
        out["verdict"] = "NEUTRAL"
        out["reason"] = "sin signo de abs_wall: no se afirma pin"
    if out["verdict"] == "PIN_DAY" and out["spot"] is not None:
        lo, hi = out["zone"]
        out["zero_dte_buy_forbidden"] = bool(lo <= out["spot"] <= hi)
    return out


def write_pin(sym, date=None, now=None):
    p = pin_clock(sym, date=date, now=now)
    CUBE.atomic_write_json(os.path.join("data", "pin_%s.json" % sym.lower()), p)
    return p


def colinearity(date=None):
    """El test que puede MATAR la feature: si max_pain es abs_wall con otro nombre, fuera."""
    xs, ys, used = [], [], []
    for sym in fleet():
        p = pin_clock(sym, date=date)
        if p["max_pain"] is None or p["abs_wall"] is None or not p["spot"]:
            continue
        xs.append(p["max_pain"] / p["spot"])
        ys.append(p["abs_wall"] / p["spot"])
        used.append(sym)
    n = len(xs)
    res = {"n": n, "syms": used, "rho": None, "verdict": None,
           "nota": "con n<10 no se concluye nada; el kill es |rho|>%.1f" % COLINEARITY_KILL}
    if n < 3:
        res["verdict"] = "DATOS_INSUFICIENTES"
        res["nota"] = ("n=%d < 10: no se concluye nada (ni siquiera hay 3 puntos para una "
                       "correlacion). El kill es |rho|>%.1f" % (n, COLINEARITY_KILL))
        return res
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        res["verdict"] = "VARIANZA_CERO"
        return res
    rho = sxy / (sxx * syy) ** 0.5
    res["rho"] = round(rho, 4)
    # La nota se REESCRIBE segun la muestra que hay de verdad. Antes se quedaba clavada en
    # "con n<10 no se concluye nada" incluso con n=30, contradiciendo al propio veredicto de
    # la linea siguiente: un lector (o la sesion siguiente) veia APORTA_ALGO junto a "no se
    # concluye nada" y no sabia a cual creer.
    if n < 10:
        res["verdict"] = "DATOS_INSUFICIENTES"
        res["nota"] = ("n=%d < 10: no se concluye nada. El kill es |rho|>%.1f"
                       % (n, COLINEARITY_KILL))
    else:
        res["verdict"] = "MUERE_ES_ABS_WALL" if abs(rho) > COLINEARITY_KILL else "APORTA_ALGO"
        res["nota"] = ("n=%d simbolos, |rho|=%.4f vs kill %.1f -> %s. Mide COLINEALIDAD (si el "
                       "max pain fuera un duplicado del abs_wall no aporta), NO edge: esta "
                       "feature sigue sin probabilidad medida."
                       % (n, abs(rho), COLINEARITY_KILL,
                          "muere" if abs(rho) > COLINEARITY_KILL else "sobrevive"))
    return res


def fleet():
    p = os.path.join("data", "fleet.txt")
    if os.path.exists(p):
        with open(p) as f:
            return f.read().split()
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--colinearity", action="store_true")
    a = ap.parse_args()
    if a.colinearity:
        print(json.dumps(colinearity(a.date), indent=1))
        return
    syms = [a.sym.upper()] if a.sym else (fleet() if a.all else [])
    if not syms:
        ap.print_help()
        return
    n_pin = 0
    for s in syms:
        try:
            p = write_pin(s, date=a.date)
        except Exception as e:
            print("%-6s FALLO %s" % (s, e), file=sys.stderr)
            continue
        if a.print:
            print(json.dumps(p, indent=1))
            continue
        if p["max_pain"] is None:
            print("%-6s -- (%s)" % (s, p["reason"]))
            continue
        n_pin += 1 if p["pin"] else 0
        print("%-6s max_pain %.2f abs_wall %s (%s) pin %s zona %s OI+-2 %s -> %s%s" % (
            s, p["max_pain"], p["abs_wall"], p["abs_wall_sign"] or "?", p["pin"],
            p["zone"], p["oi_in_zone"], p["verdict"],
            "  0DTE COMPRADO PROHIBIDO" if p["zero_dte_buy_forbidden"] else ""))
    print("pins declarados: %d de %d syms" % (n_pin, len(syms)))


if __name__ == "__main__":
    main()
