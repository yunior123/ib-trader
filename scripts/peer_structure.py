#!/usr/bin/env python3
"""peer_structure.py — estructura de CADENAS de pares para la flecha (Yunior 2026-07-28:
"weight all major companies that might influence the direction, including big etfs, options
chain in those etfs, spy, spx"). Deriva de data/gex_snapshot.json (griegas MEDIDAS Polygon,
sin fetch nuevo): lado estructural de cada componente ponderado por su peso en el indice +
confluencia de indices hermanos. Entra en direction_view como COEFICIENTE multiplicativo
sobre fleet/components (doctrina direction-view-architecture: jamas factor aditivo).
SEÑAL-SOLAMENTE."""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SNAP_F = os.path.join(REPO, "data", "gex_snapshot.json")
SNAP_MAX_AGE_S = 36 * 3600   # mismo umbral que dailyplans_run.sh: estructura, no gatillo
SIBLINGS = {"QQQ": ["SPY", "SPX", "NDX", "XSP", "SMH", "XLK"],
            "SPY": ["QQQ", "SPX", "XSP", "DIA", "IWM"]}
STRONG = 0.5   # |score| minimo para que el coeficiente actue (mismo espiritu que captain_flow 0.2)


BARS_MAX_AGE_S = 600


def _spot_live(sym):
    """Cierre 1m local fresco (<10min); None si no hay barras (SPX/NDX/XSP no estan en flota)."""
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    try:
        if time.time() - os.path.getmtime(p) > BARS_MAX_AGE_S:
            return None
        last = open(p).readlines()[-1].split()
        return float(last[4])
    except Exception:
        return None


def _side(sym, e):
    """Lado estructural: spot VIVO (barras) vs flip congelado; sin barras, spot del snapshot;
    sin flip, el bias del libro. El flip rancio vale (se congela 09:35); el spot rancio NO."""
    if not e:
        return None
    spot = _spot_live(sym)
    if spot is None:
        spot = e.get("spot")
    flip = e.get("flip")
    if spot is not None and flip is not None:
        return 1.0 if spot > flip else -1.0
    b = e.get("bias")
    if b == "CALL":
        return 1.0
    if b == "PUT":
        return -1.0
    return None


def compute(index):
    """-> dict {score, comp, sib, n_comp, n_sib, asof, why} o None (sin dato fresco, jamas 0)."""
    index = index.upper()
    try:
        snap = json.load(open(SNAP_F))
    except Exception:
        return None
    meta = snap.get("_meta") or {}
    asof = meta.get("asof") or 0
    if time.time() - asof > SNAP_MAX_AGE_S:
        return None
    try:
        import index_breadth
        W = index_breadth.WEIGHTS.get(index, {})
    except Exception:
        W = {}
    num = den = 0.0
    n_comp = 0
    for s, w in W.items():
        sd = _side(s.upper(), snap.get(s.upper()))
        if sd is None:
            continue
        num += w * sd
        den += w
        n_comp += 1
    comp = num / den if den else None
    sides = [sd for s in SIBLINGS.get(index, []) if (sd := _side(s, snap.get(s))) is not None]
    sib = sum(sides) / len(sides) if sides else None
    if comp is None and sib is None:
        return None
    score = 0.6 * (comp if comp is not None else sib) + 0.4 * (sib if sib is not None else comp)
    return {"score": round(score, 3), "comp": None if comp is None else round(comp, 3),
            "sib": None if sib is None else round(sib, 3), "n_comp": n_comp,
            "n_sib": len(sides), "asof": asof,
            "why": f"cadenas: componentes {comp:+.2f} ({n_comp})" if comp is not None else "cadenas: solo hermanos"}


def peer_coef(index, local_dir):
    """Coeficiente sobre fleet/components (cuantizado como captain_coef 1.25/1.0/0.75).
    local_dir: signo del factor components/fleet ya calculado. -> (coef, why|None)"""
    d = compute(index)
    if d is None or not local_dir or abs(d["score"]) < STRONG:
        return 1.0, None
    agree = (d["score"] > 0) == (local_dir > 0)
    coef = 1.25 if agree else 0.75
    return coef, (f"estructura pares ×{coef:.2f} (comp {d['comp']:+.2f} n={d['n_comp']}, "
                  f"hermanos {d['sib']:+.2f} n={d['n_sib']})")


def apply_peer(weights, coef):
    """Escala fleet/components (mismo contrato que cor_fleet.apply_damper). Copia, no muta."""
    w = dict(weights)
    for k in ("fleet", "components"):
        if k in w:
            w[k] = round(w[k] * coef, 3)
    return w


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["QQQ", "SPY"]):
        print(s.upper(), json.dumps(compute(s)))
