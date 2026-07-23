#!/usr/bin/env python3
"""chart_levels.py — genera charts/data/levels_<sym>.json (GEX / gamma-flip / muros)
desde el cache IBKR opt_chain_<sym>.txt via gex_core (2026-07-23).

El puente del chart (chart_bridge.py) lee este JSON y dibuja las lineas horizontales
(createPriceLine) de call-wall / put-wall / gamma-flip + el perfil GEX por strike.
ADITIVO, senal-solamente. Sin red: usa el cache TWS que ya mantiene opt_chain_cache.py.

Uso: python3 scripts/chart_levels.py [SYM ...]   (default: flota con cache disponible)
"""
import json, os, sys, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gex_core

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
OUT = "charts/data"


def spot_from_cache(path):
    """El header del cache trae 'spot NNN'."""
    try:
        with open(path) as f:
            head = f.readline()
        for tok in head.replace("|", " ").split():
            pass
        parts = head.split()
        if "spot" in parts:
            return float(parts[parts.index("spot") + 1])
    except Exception:
        return None
    return None


def gen(sym, spot=None, write=True, all_exp=False):
    """spot=None -> usa el spot del header del cache (EOD/última actualización TWS).
    spot=<precio vivo> -> recalcula GEX/flip/walls al spot EN VIVO (real time; el OI
    del cache es lento pero el flip y los muros se desplazan con el precio).
    write=False -> no escribe el JSON (para el loop en vivo, evita churn de disco)."""
    path = f"data/opt_chain_{sym.lower()}.txt"
    if not os.path.exists(path):
        return None
    if spot is None:
        spot = spot_from_cache(path)
    if not spot:
        return None
    g = gex_core.from_ibkr_cache(path, spot, scale="dollar1pct", all_exp=all_exp)  # $/1% como gexa
    if not g:
        return None
    wc = gex_core.wall_context(g, spot)
    # perfil ordenado por strike (para el histograma horizontal)
    prof = [{"strike": k, "gex": round(v, 1)} for k, v in sorted(g["profile"].items())]
    vprof = [{"strike": k, "vex": round(v, 1)} for k, v in sorted(g.get("vex_profile", {}).items())]
    pmap = g["profile"]
    # DEALER PRESSURE score -100..+100 (composite gamma 80% + vanna 20%, normalizado
    # por el peso total del libro). Cerca del flip (±0.15%) se degrada (régimen inestable).
    tot_g = sum(abs(v) for v in pmap.values()) or 1.0
    tot_v = sum(abs(v) for v in g.get("vex_profile", {}).values()) or 1.0
    gl = g["net_gex"] / tot_g
    vl = g.get("net_vex", 0.0) / tot_v
    press = 100.0 * (0.8 * gl + 0.2 * vl)
    near_flip = g.get("flip") and abs((g["flip"] - spot) / spot * 100) < 0.15
    if near_flip:
        press *= 0.4
    press = round(max(-100.0, min(100.0, press)))
    if near_flip:
        press_lab = "near flip"
    elif press >= 60: press_lab = "PIN fuerte"
    elif press >= 20: press_lab = "amortigua"
    elif press <= -60: press_lab = "AMPLIFICA fuerte"
    elif press <= -20: press_lab = "amplifica"
    else: press_lab = "FLAT"
    # dominancia call/put del POC (abs_wall), estilo gexa "72%P"
    poc_dom = None
    aw = g.get("abs_wall")
    if aw is not None:
        cc = abs(g["call_gex"].get(aw, 0.0)); pp = abs(g["put_gex"].get(aw, 0.0)); tot = cc + pp
        if tot > 0:
            poc_dom = f"{round(100 * max(cc, pp) / tot)}%{'C' if cc >= pp else 'P'}"
    out = {
        "sym": sym.upper(), "spot": spot, "asof": int(time.time()),
        "exp": g.get("exp"), "dte": g.get("dte"), "scope": g.get("scope"),   # 0DTE / ALL
        "net_vex": round(g.get("net_vex", 0), 1), "vex_peak": g.get("vex_peak"),
        "vex_profile": vprof,
        "pressure": press, "pressure_lab": press_lab,
        "iv_atm": g.get("iv_atm"), "em": g.get("em"),
        "net_gex": round(g["net_gex"], 1), "regime": g["regime"],
        "flip": round(g["flip"], 2) if g["flip"] else None,
        "flip_static": round(g["flip_static"], 2) if g["flip_static"] else None,
        "call_wall": g["call_wall"], "put_wall": g["put_wall"], "abs_wall": g["abs_wall"],
        "poc_dom": poc_dom,
        "call_wall_gex": round(pmap.get(g["call_wall"], 0), 1) if g["call_wall"] else None,
        "put_wall_gex": round(pmap.get(g["put_wall"], 0), 1) if g["put_wall"] else None,
        "abs_wall_gex": round(pmap.get(g["abs_wall"], 0), 1) if g["abs_wall"] else None,
        "oi_call_wall": g["oi_call_wall"], "oi_put_wall": g["oi_put_wall"],
        "near_call_wall": wc["near_call_wall"], "near_put_wall": wc["near_put_wall"],
        "near_flip": wc["near_flip"],
        "profile": prof,
    }
    if write:
        os.makedirs(OUT, exist_ok=True)
        json.dump(out, open(f"{OUT}/levels_{sym.lower()}.json", "w"), indent=1)
    return out


def main():
    syms = sys.argv[1:]
    if not syms:
        syms = [os.path.basename(p)[10:-4] for p in glob.glob("data/opt_chain_*.txt")]
    ok = 0
    for s in syms:
        r = gen(s)
        if r:
            ok += 1
            print(f"{r['sym']:6s} spot {r['spot']:8.2f} | net_gex {r['net_gex']:>14.0f} {r['regime']} "
                  f"| flip {r['flip']} (est {r['flip_static']}) | CW {r['call_wall']} PW {r['put_wall']} "
                  f"| abs {r['abs_wall']}")
        else:
            print(f"{s.upper():6s} sin cache/spot -> skip")
    print(f"\n-> {OUT}/levels_*.json  ({ok} generados)")


if __name__ == "__main__":
    main()
