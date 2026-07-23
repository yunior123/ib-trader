#!/usr/bin/env python3
"""gex_gate.py — gate GEX EN VIVO para engines/copiloto (2026-07-23).

Dado (sym, side, precio) devuelve un veredicto de CONTEXTO gamma:
  - régimen local (POS amortigua / NEG amplifica) visto desde el precio,
  - proximidad a call_wall/put_wall/flip,
  - y una recomendación: APTO / DEGRADAR / VETO, con la razón.

Es OVERLAY, no gatillo: sube o baja la probabilidad de una señal ya impresa; jamás
la crea. NO medido en histórico (falta OI/gamma por día) — se ofrece con esa honestidad
(ver skill gamma-exposure §7). Señal-solamente.

Uso:
  python3 scripts/gex_gate.py NVDA LONG 214.10
  python3 scripts/gex_gate.py QQQ SHORT           # usa el spot del cache
Salida legible + (--json) el dict para consumo de un bot.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gex_core

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)


def spot_from_cache(path):
    try:
        parts = open(path).readline().split()
        if "spot" in parts:
            return float(parts[parts.index("spot") + 1])
    except Exception:
        pass
    return None


def gate(sym, side, price=None):
    side = side.upper()
    path = f"data/opt_chain_{sym.lower()}.txt"
    if not os.path.exists(path):
        return {"sym": sym.upper(), "verdict": "SIN-DATOS", "reason": f"no hay {path}"}
    spot = spot_from_cache(path)
    if price is None:
        price = spot
    g = gex_core.from_ibkr_cache(path, spot)
    if not g:
        return {"sym": sym.upper(), "verdict": "SIN-DATOS", "reason": "cache sin griegas/OI útiles"}
    wc = gex_core.wall_context(g, price)
    regime = wc["regime"]
    verdict = "APTO"
    reasons = []

    # 1) comprar a la resistencia / vender al soporte = rebote esperado
    if side == "LONG" and wc["near_call_wall"]:
        verdict = "VETO"; reasons.append(f"LONG pegado al call wall {g['call_wall']} (rebote ~70%)")
    if side == "SHORT" and wc["near_put_wall"]:
        verdict = "VETO"; reasons.append(f"SHORT pegado al put wall {g['put_wall']} (rebote ~70%)")

    # 2) régimen: POS favorece reversión/pin, NEG favorece continuación
    if regime == "POS":
        reasons.append("régimen POSITIVO: amortigua → favorece fades/pin, castiga rupturas")
    else:
        reasons.append("régimen NEGATIVO: amplifica → favorece continuación/band-walk, castiga fades")

    # 3) cerca del flip = zona inestable
    if wc["near_flip"]:
        if verdict != "VETO":
            verdict = "DEGRADAR"
        reasons.append(f"a ≤0.4% del gamma-flip {g['flip']} (zona whippy, sign-flip de hedging)")

    # 4) contra un muro intermedio hacia el objetivo (aviso)
    dcw, dpw = wc["d_call_wall"], wc["d_put_wall"]
    if side == "LONG" and dcw is not None and 0 < dcw <= 1.0 and not wc["near_call_wall"]:
        reasons.append(f"call wall {g['call_wall']} a +{dcw:.2f}% = techo/imán cercano (objetivo, no cruzar comprando a través)")
    if side == "SHORT" and dpw is not None and -1.0 <= dpw < 0 and not wc["near_put_wall"]:
        reasons.append(f"put wall {g['put_wall']} a {dpw:.2f}% = piso/imán cercano (objetivo)")

    return {
        "sym": sym.upper(), "side": side, "price": round(price, 2), "spot": round(spot, 2),
        "regime": regime, "net_gex": round(g["net_gex"], 0),
        "flip": round(g["flip"], 2) if g["flip"] else None,
        "call_wall": g["call_wall"], "put_wall": g["put_wall"], "abs_wall": g["abs_wall"],
        "d_call_wall": None if dcw is None else round(dcw, 2),
        "d_put_wall": None if dpw is None else round(dpw, 2),
        "d_flip": None if wc["d_flip"] is None else round(wc["d_flip"], 2),
        "verdict": verdict, "reason": " | ".join(reasons),
    }


def main():
    a = [x for x in sys.argv[1:] if x != "--json"]
    as_json = "--json" in sys.argv
    if not a:
        print(__doc__); return
    sym = a[0]
    side = a[1] if len(a) > 1 else "LONG"
    price = float(a[2]) if len(a) > 2 else None
    r = gate(sym, side, price)
    if as_json:
        print(json.dumps(r)); return
    ico = {"APTO": "✅", "DEGRADAR": "⚠️", "VETO": "⛔", "SIN-DATOS": "❔"}.get(r["verdict"], "")
    print(f"{ico} {r['sym']} {r.get('side','')} @ {r.get('price','?')}  →  {r['verdict']}")
    if "regime" in r:
        print(f"   régimen {r['regime']} | net_gex {r['net_gex']:.0f} | flip {r['flip']} "
              f"| CW {r['call_wall']} (Δ{r['d_call_wall']}%) | PW {r['put_wall']} (Δ{r['d_put_wall']}%)")
    print(f"   {r['reason']}")


if __name__ == "__main__":
    main()
