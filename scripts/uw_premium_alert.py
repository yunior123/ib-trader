#!/usr/bin/env python3
import json
import os

import narrator

LEVELS_MAX_AGE_S = 600
STRIKE_UNAVAILABLE = "strike no disponible (flujo agregado)"


def structural_context(levels, live_spot, now_epoch, max_age_s=LEVELS_MAX_AGE_S):
    if not isinstance(levels, dict) or not live_spot or live_spot <= 0:
        return None
    asof = levels.get("asof")
    if not isinstance(asof, (int, float)):
        return None
    age = now_epoch - asof
    if age < 0 or age > max_age_s:
        return None
    current = dict(levels)
    current["spot"] = float(live_spot)
    return narrator.structural_signal(current)


def load_structural_context(repo, sym, live_spot, now_epoch):
    path = os.path.join(repo, "charts", "data", f"levels_{sym.lower()}.json")
    try:
        with open(path) as f:
            levels = json.load(f)
        return structural_context(levels, live_spot, now_epoch)
    except (OSError, TypeError, ValueError, KeyError):
        return None


def _price(value):
    return f"{value:g}"


def build_alert(sym, premium, structure=None):
    sp = premium["signed_premium"]
    bullish = sp > 0
    side = "ALCISTA" if bullish else "BAJISTA"
    side_l = side.lower()
    title = f"{'🟢📈' if bullish else '🔴📉'} FLUJO AGRESOR {side} {sym}"
    flow = (f"Flujo agresor {side_l} en {sym}: neto ${sp:,.0f} "
            f"(call ${premium['net_call_premium']:,.0f} "
            f"put ${premium['net_put_premium']:,.0f})")
    voice = f"Flujo agresor {side_l} en {sym}"

    if structure and structure.get("kind") == "pin":
        pin = _price(structure["price"])
        context = (f"flujo {side_l}, pero {sym} fijado al pin {pin}; "
                   "continuación NO confirmada")
        voice = context
    elif structure and structure.get("kind") == "magnet":
        aligned = (bullish and structure.get("dir") == "up") or (
            not bullish and structure.get("dir") == "down")
        target = _price(structure["price"])
        level_side = "superior" if structure.get("dir") == "up" else "inferior"
        if aligned:
            context = (f"objetivo {target} (imán/muro {level_side}); no asumir ruptura, "
                       "esperar aceptación/retest")
            voice = f"{voice}; {context}"
        else:
            context = (f"el mapa apunta al imán/muro {level_side} {target}; "
                       "continuación del flujo NO confirmada")
            voice = f"{voice}; {context}"
    else:
        context = None

    message = flow
    if context:
        message += f"; {context}"
    message += f"; {STRIKE_UNAVAILABLE}."
    voice += f"; {STRIKE_UNAVAILABLE}."
    return {"title": title, "message": message, "voice": voice}
