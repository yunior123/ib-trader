#!/usr/bin/env python3
"""direction_view.py — lectura DIRECCIONAL compuesta del ticker seleccionado, para pintar una
FLECHA semitransparente en el chart con su % (orden Yunior 2026-07-24: "overlayed arrow con la
dirección predicha basada en fleet state, walls, gex, gamma flip y cuantos factores relevantes
sea posible, con porcentaje, limpia y un poco transparente").

Combina, en tiempo real y TODO MEDIDO/derivado (nada inventado):
  · gamma flip + régimen  (spot sobre/bajo flip; en POS el flip sostiene, en NEG amplifica)
  · muros call/put + POC  (espacio a la resistencia vs al piso -> sesgo de recorrido)
  · GEX net + dealer pressure (pin vs aceleración)
  · dirección de la FLOTA / capitanes (signal_conditioning.fleet_bias)
  · momentum reciente (bars 1m)
  · valuación/inflación (inflation_score) como viento de cola/frente
  · imán estructural (narrator.structural_signal) si hay nodo oro dominante

Devuelve {dir: 'up'|'down'|'flat', prob: int%, score: float[-1..1], factors:{...}, why:[...]}
Es un SESGO compuesto (estilo 'bias' de gexa), honesto: NO es un win-rate medido, es la
resultante de las fuerzas del mapa. SEÑAL-SOLAMENTE.
"""
import os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def _bars_mom(sym, n=6):
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(p):
        return None
    try:
        c = [float(l.split()[4]) for l in open(p) if l.strip()]
    except Exception:
        return None
    if len(c) < n + 1:
        return None
    return 100 * (c[-1] - c[-1 - n]) / c[-1 - n]


def _closes(sym):
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    try:
        return [float(l.split()[4]) for l in open(p) if l.strip()]
    except Exception:
        return []


def _pctb(closes, n=20, k=2.0):
    """%B de Bollinger(n,k) sobre el último cierre. 0=banda baja, 1=banda alta, extremos=riesgo
    de reversión (doctrina BOLLINGER-SIEMPRE). None si no hay data."""
    if len(closes) < n:
        return None
    import statistics as _st
    w = closes[-n:]; m = _st.mean(w); sd = _st.pstdev(w)
    if sd == 0:
        return 0.5
    up, lo = m + k * sd, m - k * sd
    return (closes[-1] - lo) / (up - lo)


def compute(sym, lv=None):
    sym = sym.upper()
    try:
        import chart_levels
        if lv is None:
            lv = chart_levels.gen(sym, write=False)
    except Exception:
        lv = lv or {}
    if not lv or not lv.get("spot") or not lv.get("flip"):
        return {"dir": "flat", "prob": 50, "score": 0.0, "factors": {},
                "why": ["sin mapa GEX fresco"]}
    spot = lv["spot"]; flip = lv["flip"]; reg = lv.get("regime", "POS")
    em = lv.get("em") or spot * 0.02
    cw = lv.get("call_wall"); pw = lv.get("put_wall")
    press = lv.get("pressure") or 0
    factors = {}; why = []; weights = {}

    # 1) posición vs flip (régimen manda el signo del efecto)
    dflip = _clamp((spot - flip) / em)
    reg_pos = (reg == "POS")
    f_flip = dflip * (1.0 if reg_pos else 0.5)   # en NEG el flip es whippy -> menos peso
    factors["flip"] = round(f_flip, 2); weights["flip"] = 1.5
    if abs(dflip) > 0.15:
        why.append(f"{'sobre' if dflip>0 else 'bajo'} el flip {flip} ({reg})")

    # 2) espacio muros: cerca del put wall con recorrido al call wall = sesgo arriba (y viceversa)
    f_wall = 0.0
    if cw and pw and cw > pw:
        pos = (spot - pw) / (cw - pw)            # 0=en put wall, 1=en call wall
        f_wall = _clamp((0.5 - pos) * 2)          # cerca del piso -> +; pegado al techo -> -
        factors["walls"] = round(f_wall, 2); weights["walls"] = 1.0
        if pos > 0.82:
            why.append(f"pegado al call wall {cw} (techo)")
        elif pos < 0.18:
            why.append(f"pegado al put wall {pw} (piso)")

    # 3) GEX net + pressure: pin (POS, pressure+) frena; NEG con pressure- acelera el movimiento
    f_gex = 0.0
    if not reg_pos and press:
        # en NEG, la aceleración va EN el sentido del momentum/flip actual
        f_gex = _clamp(dflip) * 0.4
        factors["gex_accel"] = round(f_gex, 2); weights["gex_accel"] = 0.8
        why.append("régimen NEG: acelera el movimiento (whipsaw)")

    # 4) FLOTA / capitanes
    f_fleet = 0.0
    try:
        import signal_conditioning as SC
        fb = SC.fleet_bias()
        gov_key, gov_name = SC.governing_captain(sym)
        cd = fb.get(gov_key, 0)
        if cd and sym not in ("SPY", "QQQ", "SMH"):
            f_fleet = float(cd)
            why.append(f"capitán {gov_name or gov_key} {'↑' if cd>0 else '↓'}")
        elif sym in ("SPY", "QQQ", "SMH"):
            f_fleet = float(fb.get("market" if sym != "SMH" else "semis", 0))
        factors["fleet"] = f_fleet; weights["fleet"] = 1.4
    except Exception:
        pass

    # 4b) COMPONENTES del índice (QQQ/SPY): LOCAL rápido (sin red) — si MSFT/AMZN/TSLA caen, hereda
    if sym in ("QQQ", "SPY"):
        try:
            import signal_conditioning as SC
            comp = SC.component_bias(sym)
            f_comp = _clamp(comp * 1.5)
            factors["components"] = round(f_comp, 2); weights["components"] = 1.3
            if abs(f_comp) > 0.1:
                why.append(f"componentes {'↓' if f_comp < 0 else '↑'} ({comp:+.2f})")
        except Exception:
            pass

    # 4c) SPIKES de opciones de CAPITANES en tiempo real (SPY/QQQ/SMH) — Yunior 2026-07-24
    try:
        import signal_conditioning as SC
        cf = SC.captain_flow_bias()
        gk, _ = SC.governing_captain(sym)
        cfv = cf.get("semis" if gk == "semis" else "market", 0.0)
        if abs(cfv) > 0.2:
            factors["captain_flow"] = round(cfv, 2); weights["captain_flow"] = 1.2
            why.append(f"spike-flow capitanes {'↑ (puts=piso)' if cfv > 0 else '↓ (calls=techo)'}")
    except Exception:
        pass

    # 5) momentum reciente
    mom = _bars_mom(sym)
    if mom is not None:
        f_mom = _clamp(mom / 0.5)                 # 0.5% ~ saturación
        factors["momentum"] = round(f_mom, 2); weights["momentum"] = 1.0
        if abs(mom) > 0.15:
            why.append(f"momentum {mom:+.2f}%")

    # 5b) %B de Bollinger (BOLLINGER-SIEMPRE): en EXTREMO manda la reversión de corto plazo
    closes = _closes(sym)
    pctb = _pctb(closes)
    if pctb is not None:
        f_bb = 0.0
        if pctb >= 0.85:
            f_bb = -min(1.0, (pctb - 0.85) / 0.15)     # sobrecompra -> sesgo fade abajo
        elif pctb <= 0.15:
            f_bb = min(1.0, (0.15 - pctb) / 0.15)       # sobreventa -> sesgo fade arriba
        if f_bb != 0.0:
            factors["bollinger"] = round(f_bb, 2); weights["bollinger"] = 1.15
            why.append(f"%B 1m {pctb:.2f} {'extremo alto→fade' if f_bb<0 else 'extremo bajo→rebote'}")

    # 5c) patrón de velas (contexto de reversión/continuación, no gatillo)
    try:
        import candles
        pats = candles.read(sym, 1).get("patterns", [])
        net = sum(1 if p["bias"] == "bull" else -1 if p["bias"] == "bear" else 0 for p in pats)
        if net != 0:
            factors["candle"] = 1.0 if net > 0 else -1.0; weights["candle"] = 0.6
            why.append(f"velas {'alcista' if net > 0 else 'bajista'} ({pats[-1]['name']})")
    except Exception:
        pass

    # 6) inflación (viento de cola/frente lento)
    try:
        import json
        infl = json.load(open(os.path.join(REPO, "data/inflation_score.json")))
        row = infl.get(sym)
        if row and row.get("score") is not None:
            f_infl = -row["score"] * 0.4          # inflada -> sesgo abajo
            factors["inflation"] = round(f_infl, 2); weights["inflation"] = 0.5
    except Exception:
        pass

    # 7) imán estructural
    mag_price = None; mag_kind = None
    try:
        import narrator
        sig = narrator.structural_signal(lv)
        if sig and sig.get("dir") in ("up", "down"):
            f_str = 1.0 if sig["dir"] == "up" else -1.0
            factors["magnet"] = f_str; weights["magnet"] = 1.1
            why.append(sig["text"])
            mag_price = sig.get("price"); mag_kind = sig.get("kind")   # imán/pin
    except Exception:
        pass

    # combinar (media ponderada de los factores presentes)
    num = sum(factors[k] * weights.get(k, 1.0) for k in factors)
    den = sum(weights.get(k, 1.0) for k in factors) or 1.0
    score = _clamp(num / den)
    if score > 0.15:
        d = "up"
    elif score < -0.15:
        d = "down"
    else:
        d = "flat"
    prob = int(round(50 + abs(score) * 40)) if d != "flat" else 50
    prob = max(50, min(90, prob))

    # PRÓXIMO OBJETIVO en el sentido de la flecha: imán estructural si va hacia él, si no
    # el muro/nodo más cercano en esa dirección (call wall arriba / put wall abajo / POC).
    target = None; target_lab = None
    cands_up = [x for x in (cw, lv.get("abs_wall"), lv.get("poc")) if x and x > spot * 1.0005]
    cands_dn = [x for x in (pw, lv.get("abs_wall"), lv.get("poc")) if x and x < spot * 0.9995]
    if d == "up":
        if mag_price and mag_price >= spot:
            target, target_lab = mag_price, ("pin" if mag_kind == "pin" else "imán")
        elif cands_up:
            target, target_lab = min(cands_up), "muro call"
    elif d == "down":
        if mag_price and mag_price <= spot:
            target, target_lab = mag_price, ("pin" if mag_kind == "pin" else "imán")
        elif cands_dn:
            target, target_lab = max(cands_dn), "muro put"
    else:  # flat: el borde de caja más cercano
        near = [x for x in (cw, pw) if x]
        if near:
            target = min(near, key=lambda x: abs(x - spot)); target_lab = "borde"
    tgt_pct = round((target - spot) / spot * 100, 2) if target else None

    return {"dir": d, "prob": prob, "score": round(score, 3),
            "target": round(target, 2) if target else None, "target_label": target_lab,
            "target_pct": tgt_pct, "spot": round(spot, 2),
            "factors": factors, "why": why[:5], "sym": sym}


def _cli():
    import json
    sym = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    r = compute(sym)
    arrow = "▲" if r["dir"] == "up" else "▼" if r["dir"] == "down" else "▬"
    tgt = (f"  → {r['target_label']} {r['target']} ({r['target_pct']:+.2f}%)"
           if r.get("target") else "")
    print(f"{arrow} {sym}: {r['dir'].upper()} {r['prob']}%  (score {r['score']:+.2f}){tgt}")
    for w in r["why"]:
        print(f"    · {w}")
    print("    factores:", json.dumps(r["factors"]))


if __name__ == "__main__":
    _cli()
