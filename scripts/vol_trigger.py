#!/usr/bin/env python3
"""vol_trigger.py — VOLATILITY TRIGGER congelado a las 09:35 (feature minada #20).

Es un INTERRUPTOR DE LICENCIA-PARA-FADEAR, no una señal:
  spot > vt_open -> licencia de REVERSION A LA MEDIA (fadear hacia el call wall permitido)
  spot < vt_open -> licencia de MOMENTUM: **fadear PROHIBIDO**, stops mas anchos, sin trades
                    de pin, sin venta de premium. Una banda de Bollinger estirada en contra
                    tuya POR DEBAJO del VT es CONTINUACION, no rebote elastico (refina la
                    regla 1 de la doctrina).

Y la congelacion es la mitad del valor: un nivel que no puede oscilar no puede crying-wolf.
Con el OI de cierre previo congelado, un VT que se mueve intradia mide el spot moviendose
bajo un libro quieto, no un cambio de posicionamiento.

QUE NO ES: no es el cruce por cero de la gamma. `VT = max{ K <= spot : net_gex(K) > 0 y
net_gex(K) >= 5% de Σ|net_gex| y los dos strikes vecinos poblados }` — la ULTIMA ESTANTERIA
DENSA de gamma positiva por debajo del spot. Respaldo: el strike LISTADO mas cercano a la
raiz continua de gamma-cero.

PUERTA DURA (kill-risk de la spec): solo simbolos con **>= 40 strikes poblados**. Si la
estanteria es un artefacto de una cadena escasa, el nivel congelado es arbitrario y la regla
de prohibir-fadear hace daño REAL. Por debajo de la puerta: `vt_open = null` con motivo.

Salida: `data/vt_<sym>.json` — es la ruta que lee `./compass` (`vt_open`).

Uso:  ./venv/bin/python scripts/vol_trigger.py            # los simbolos con mapa
      ./venv/bin/python scripts/vol_trigger.py QQQ SPY
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
ROOT = os.environ.get("IBT_ROOT") or REPO
os.chdir(ROOT)

import chart_levels                        # noqa: E402

MIN_STRIKES = 40          # puerta de la spec: menos que esto y la estanteria es ruido
SHELF_FRAC = 0.05         # el estante tiene que valer >=5% del peso total del libro
FREEZE_MIN = chart_levels.FREEZE_MIN       # 09:35 ET, la misma que el flip


def atomic_write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def strike_width(strikes):
    """Intervalo MODAL de strikes (el paso de la rejilla). None con menos de 2 strikes:
    sin rejilla no se puede hablar de "vecino poblado"."""
    ks = sorted(strikes)
    if len(ks) < 2:
        return None
    gaps = {}
    for a, b in zip(ks, ks[1:]):
        g = round(b - a, 6)
        if g > 0:
            gaps[g] = gaps.get(g, 0) + 1
    if not gaps:
        return None
    return max(gaps.items(), key=lambda x: (x[1], -x[0]))[0]


def vt_from_profile(profile, spot, zero_gamma=None):
    """(vt, shelf_gex_pct, fuente, motivo). `profile`: {strike: gex_neto}.

    Devuelve (None, None, None, motivo) si no hay estante ni respaldo — nunca un strike
    "razonable" elegido a dedo."""
    if not profile or not spot:
        return None, None, None, "sin perfil GEX"
    gross = sum(abs(v) for v in profile.values())
    if gross <= 0:
        return None, None, None, "perfil con peso 0"
    w = strike_width(profile)
    if w is None:
        return None, None, None, "menos de 2 strikes: no hay rejilla"
    cands = []
    for k, v in profile.items():
        if k > spot or v <= 0 or v < SHELF_FRAC * gross:
            continue
        vecinos = any(abs(k2 - (k - w)) < 1e-6 for k2 in profile) and \
                  any(abs(k2 - (k + w)) < 1e-6 for k2 in profile)
        if vecinos:
            cands.append((k, v))
    if cands:
        k, v = max(cands, key=lambda x: x[0])
        return k, round(v / gross, 4), "estante_denso", None
    if zero_gamma:
        k = min(profile, key=lambda x: abs(x - zero_gamma))
        return k, round(abs(profile[k]) / gross, 4), "respaldo_strike_junto_a_gamma_cero", None
    return None, None, None, (f"ningun estante de gamma+ >= {SHELF_FRAC:.0%} del libro por "
                              f"debajo del spot, y sin raiz de gamma-cero para el respaldo")


def freeze_decision(vt_live, prev_open, prev_day, today, now_min, is_market_day):
    """Misma regla que el flip: ya congelado hoy manda; si no, se congela en dia de mercado
    desde las 09:35; fuera de eso None (no hay apertura que congelar)."""
    if prev_day == today and prev_open is not None:
        return prev_open, False
    if vt_live is not None and is_market_day and now_min >= FREEZE_MIN:
        return vt_live, True
    return None, False


def _prev(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None, None, None
    return d.get("vt_open"), d.get("frozen_day"), d.get("frozen_at")


def gen(sym, lv=None, write=True):
    lv = lv if lv is not None else chart_levels.gen(sym, write=False)
    if not lv:
        return None
    spot = lv.get("spot")
    prof = {p["strike"]: p["gex"] for p in (lv.get("profile") or [])}
    n_strikes = lv.get("n_strikes_populated") or len(prof)
    zero_gamma = lv.get("flip_live") if lv.get("flip_live") is not None else lv.get("flip")

    vt_live = shelf = fuente = None
    if not lv.get("gamma_ok"):
        motivo = f"gamma muteada: {lv.get('degraded_reason')}"
    elif n_strikes < MIN_STRIKES:
        # fail loud: mejor sin VT que un VT arbitrario que PROHIBA fadear todo el dia
        motivo = (f"{n_strikes} strikes poblados < {MIN_STRIKES}: la estanteria seria un "
                  f"artefacto de una cadena escasa, no un nivel")
    else:
        vt_live, shelf, fuente, motivo = vt_from_profile(prof, spot, zero_gamma)

    path = f"data/vt_{sym.lower()}.json"
    prev_open, prev_day, frozen_at = _prev(path)
    today = time.strftime("%Y-%m-%d")
    lt = time.localtime()
    vt_open, nuevo = freeze_decision(vt_live, prev_open, prev_day, today,
                                     lt.tm_hour * 60 + lt.tm_min, lt.tm_wday < 5)
    if nuevo:
        frozen_at = int(time.time())
    ref = vt_open if vt_open is not None else vt_live
    em = lv.get("em")
    out = {
        "sym": sym.upper(), "asof": int(time.time()), "spot": spot, "em": em,
        "vt_open": vt_open, "vt_live": vt_live, "zero_gamma": zero_gamma,
        "shelf_gex_pct": shelf, "vt_source": fuente,
        "n_strikes": n_strikes, "source": lv.get("chain_src"),
        "frozen_at": frozen_at, "frozen_day": today if vt_open is not None else None,
        "dist_vt_em": (round((spot - ref) / em, 3)
                       if (ref is not None and spot and em) else None),
        "regime_vt": (None if ref is None or not spot else ("ABOVE" if spot > ref else "BELOW")),
        "licencia": (None if ref is None or not spot else
                     ("reversion a la media permitida (fadear hacia el call wall, venta de "
                      "premium OK)" if spot > ref else
                      "MOMENTUM: fadear PROHIBIDO, stops mas anchos, sin pin, sin venta de "
                      "premium; banda estirada en contra = CONTINUACION")),
        "why": motivo,
    }
    if write:
        atomic_write(path, json.dumps(out, indent=1))
    return out


def main():
    syms = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not syms:
        syms = sorted({os.path.basename(p)[7:-5]
                       for p in glob.glob("charts/data/levels_*.json")})
    con_vt = 0
    for s in syms:
        r = gen(s)
        if not r:
            print(f"{s.upper():6s} sin mapa GEX -> skip")
            continue
        if r["vt_live"] is None:
            print(f"{r['sym']:6s} SIN VT — {r['why']}")
            continue
        con_vt += 1
        print(f"{r['sym']:6s} spot {r['spot']:8.2f} | VT vivo {r['vt_live']} "
              f"(open {r['vt_open']}) | {r['regime_vt']} | estante "
              f"{r['shelf_gex_pct']:.1%} del libro | {r['vt_source']} | {r['source']}")
    print(f"\n-> data/vt_<sym>.json  ({con_vt}/{len(syms)} con VT; "
          f"puerta: >= {MIN_STRIKES} strikes poblados)")


if __name__ == "__main__":
    main()
