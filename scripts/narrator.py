#!/usr/bin/env python3
"""narrator.py — narrador de mercado tipo gexa para el chart cockpit (2026-07-23).

DOS capas (thrift de tokens):
  1) deterministic(lv, bars)  -> lectura BREVE en español desde los niveles GEX/flip/muros
     (régimen, distancia al flip, muro imán/acelerador más cercano, dealer-pressure,
     expected-move). CERO tokens, siempre disponible, se refresca cada 15s gratis.
  2) deepseek(lv, bars, prev) -> pule esa lectura con DeepSeek (OpenAI-compat) en ≤2 frases.
     Solo se llama BAJO DEMANDA (botón ↻) o ante cambio MATERIAL de estado, con throttle.

DeepSeek: key en llm.env (DEEPSEEK_API_KEY), base api.deepseek.com/v1, model deepseek-chat.
Barato pero se cuida: max_tokens corto, temperatura baja, prompt minúsculo. NUNCA imprime la key.
SEÑAL-SOLAMENTE: describe estructura/flujo, jamás ordena comprar/vender ni da tamaño.
"""
import os, json, urllib.request, urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    """Lee llm.env sin exponer nada. Devuelve (key, base_url, model) o (None,...)."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    base = os.environ.get("TA_BACKEND_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("TA_QUICK_MODEL", "deepseek-chat")
    path = os.path.join(REPO, "config", "llm.env")
    if os.path.exists(path):
        try:
            with open(path) as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln or ln.startswith("#") or "=" not in ln:
                        continue
                    k, v = ln.split("=", 1)
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    if k == "DEEPSEEK_API_KEY" and not key:
                        key = v
                    elif k == "TA_BACKEND_URL":
                        base = v
                    elif k == "TA_QUICK_MODEL":
                        model = v
        except Exception:
            pass
    return key, base, model


def _fmt_m(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e9: return f"{v/1e9:+.2f}B"
    if a >= 1e6: return f"{v/1e6:+.0f}M"
    if a >= 1e3: return f"{v/1e3:+.0f}K"
    return f"{v:+.0f}"


def trigger_key(lv):
    """Firma del estado MATERIAL — cambia solo cuando algo relevante se mueve (régimen,
    cruce de muro, signo de pressure, banda de precio). Sirve para decidir si vale un
    token de DeepSeek (mismo key = nada nuevo que contar)."""
    if not lv:
        return None
    spot = lv.get("spot") or 0
    flip = lv.get("flip")
    side = "?" if not flip else ("up" if spot >= flip else "dn")
    p = lv.get("pressure") or 0
    psign = "+" if p >= 20 else ("-" if p <= -20 else "0")
    # banda de precio ~0.4% para no disparar por ruido
    band = round(spot / (spot * 0.004)) if spot else 0
    cw = lv.get("call_wall"); pw = lv.get("put_wall")
    return f"{lv.get('regime')}|{side}|{psign}|{band}|CW{cw}|PW{pw}|{lv.get('scope')}"


def deterministic(lv, bars=None):
    """Lectura BREVE (1-2 frases) desde los niveles. Cero tokens. Doctrina gexa."""
    if not lv:
        return "Sin mapa GEX aún."
    sym = lv.get("sym", "?"); spot = lv.get("spot")
    flip = lv.get("flip"); reg = lv.get("regime")
    scope = lv.get("scope", "0DTE")
    cw = lv.get("call_wall"); pw = lv.get("put_wall")
    cwg = lv.get("call_wall_gex"); pwg = lv.get("put_wall_gex")
    press = lv.get("pressure"); plab = lv.get("pressure_lab", "")
    em = lv.get("em")
    parts = []
    # régimen + flip
    if flip and spot:
        d = (spot - flip) / flip * 100
        if abs(d) < 0.12:
            parts.append(f"{sym} PEGADO al flip {flip} (±{abs(d):.2f}%) — TRANSICIÓN, un empujón lo voltea.")
        elif spot >= flip:
            parts.append(f"{sym} {spot} ARRIBA del flip {flip} (+{d:.2f}%) — gamma+ amortigua: vol baja, se fadean rallies y se compran dips.")
        else:
            parts.append(f"{sym} {spot} DEBAJO del flip {flip} ({d:.2f}%) — gamma− amplifica: hedging acelera, operar rupturas no fades.")
    else:
        parts.append(f"{sym} {spot} — régimen {reg}.")
    # muro más cercano (imán oro gamma+ / acelerador morado gamma-)
    near = None
    if cw and pw and spot:
        dc = abs(cw - spot); dp = abs(pw - spot)
        if dc <= dp:
            typ = "imán (techo)" if (cwg or 0) >= 0 else "acelerador"
            near = f"Muro cercano: call {cw} {typ} {_fmt_m(cwg)}; piso put {pw} {_fmt_m(pwg)}."
        else:
            typ = "imán (piso)" if (pwg or 0) >= 0 else "acelerador (trampilla)"
            near = f"Muro cercano: put {pw} {typ} {_fmt_m(pwg)}; techo call {cw} {_fmt_m(cwg)}."
    if near:
        parts.append(near)
    # pressure + EM
    tail = []
    if press is not None:
        tail.append(f"Dealer-pressure {press:+d} ({plab})")
    if em and spot:
        tail.append(f"rango esperado ±{em:.2f} ({spot-em:.2f}/{spot+em:.2f})")
    if tail:
        parts.append(" · ".join(tail) + f" · {scope}.")
    return " ".join(parts)


def _momentum(bars, n=6):
    """dirección del momentum reciente: +1 sube, -1 baja, 0 plano (últimas n barras)."""
    if not bars or len(bars) < n + 1:
        return 0
    closes = [b[4] for b in bars[-n:]]
    d = closes[-1] - closes[0]
    ref = abs(closes[0]) * 0.0008 or 0.01
    return 1 if d > ref else (-1 if d < -ref else 0)


def structural_signal(lv, bars=None):
    """Señal ESTRUCTURAL desde el mapa GEX (lo que Yunior quiere ver en el chart:
    'NVDA se dirige a su imán 210, prob 70%'). Devuelve {text, prob, dir, kind, price} o None.
    La 'prob' es una CONVICCIÓN estructural transparente (pressure + distancia + momentum),
    NO un win-rate medido — así se etiqueta en el tip/BD. Doctrina [[gexa-framework]]."""
    if not lv:
        return None
    sym = lv.get("sym", "?"); spot = lv.get("spot"); flip = lv.get("flip")
    reg = lv.get("regime"); press = lv.get("pressure") or 0
    em = lv.get("em") or (spot * 0.02 if spot else 1)
    cw = lv.get("call_wall"); cwg = lv.get("call_wall_gex") or 0
    pw = lv.get("put_wall"); pwg = lv.get("put_wall_gex") or 0
    aw = lv.get("abs_wall"); awg = lv.get("abs_wall_gex") or 0
    if not spot or not flip:
        return None
    mom = _momentum(bars)

    def _cond(base, dirstr):
        """Condiciona la convicción estructural por hora×flota×inflación (medido).
        Devuelve (prob_condicionada, nota_corta o None). Degrada limpio si falta el módulo."""
        try:
            import signal_conditioning as SC
            r = SC.conditioned_prob("structural", sym, 1 if dirstr == "up" else -1, base)
            note = None
            if r["veto"]:
                note = "flota en contra — rebajada"
            elif r["prob"] < base - 4:
                note = "rebajada (hora/flota/valuación)"
            elif r["prob"] > base + 4:
                note = "reforzada (flota a favor)"
            return r["prob"], note
        except Exception:
            return base, None
    # 1) pérdida de flip inminente -> aviso de cambio de régimen (lo más accionable)
    dflip = (spot - flip) / flip * 100
    if abs(dflip) < 0.12:
        return {"sym": sym, "text": f"{sym} pegado al flip {flip} — TRANSICIÓN, no direccional",
                "prob": None, "dir": "flat", "kind": "flip", "price": flip}
    # 2) IMÁN: nodo ORO (gamma+) dominante hacia el que va el precio
    magnet = aw if awg > 0 else (cw if cwg > 0 and cw and cw >= spot else (pw if pwg > 0 and pw and pw <= spot else None))
    if magnet is None or reg != "POS":
        return None
    dist = abs(magnet - spot)
    dist_pct = dist / spot * 100
    prob = int(max(52, min(85, round(50 + 0.30 * abs(press) - (dist / em) * 10))))
    # 3a) EN el imán (≤0.30%): pin — el precio ya llegó, dealers lo fijan
    if dist_pct <= 0.30:
        d = "up" if spot <= magnet else "down"
        cp, note = _cond(prob, d)
        return {"sym": sym, "text": f"{sym} en su imán {magnet} — pin",
                "prob": cp, "base_prob": prob, "note": note, "dir": d,
                "kind": "pin", "price": magnet}
    # 3b) SE DIRIGE al imán: momentum (o pin fuerte) hacia él, dentro del rango
    toward = (magnet >= spot and mom >= 0) or (magnet <= spot and mom <= 0) or abs(press) >= 75
    if toward and dist <= 1.6 * em:
        arrow = "↑" if magnet >= spot else "↓"
        d = "up" if magnet >= spot else "down"
        cp, note = _cond(prob, d)
        return {"sym": sym, "text": f"{sym} se dirige a su imán {magnet} {arrow}",
                "prob": cp, "base_prob": prob, "note": note, "dir": d,
                "kind": "magnet", "price": magnet}
    return None


SYS = ("Eres el narrador de un mapa GEX (estilo gexa.ai) para un trader experto. "
       "Reescribe la lectura en 1-2 frases MÁXIMO, español, tono directo de trading floor, "
       "sin relleno. Describe estructura/flujo (régimen, flip, muros imán/acelerador, presión). "
       "NUNCA ordenes comprar/vender ni des tamaño/stop — es señal educativa. No inventes cifras: "
       "usa solo las dadas. Termina sin disclaimers.")


def deepseek(lv, bars=None, prev=None, timeout=8):
    """Pule la lectura determinista con DeepSeek. Devuelve texto o None si falla/no hay key.
    Token-thrift: prompt minúsculo, max_tokens 120, temp 0.4."""
    key, base, model = _load_env()
    if not key:
        return None
    base_read = deterministic(lv, bars)
    user = f"Datos: {base_read}"
    if prev:
        user += f"\nNarración previa (evita repetir literal): {prev}"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": user}],
        "max_tokens": 120, "temperature": 0.4, "stream": False,
    }
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode())
        txt = j["choices"][0]["message"]["content"].strip()
        return txt or None
    except Exception:
        return None


if __name__ == "__main__":
    # smoke test con niveles del cache
    import sys, glob
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import chart_levels
    sym = (sys.argv[1] if len(sys.argv) > 1 else "nvda").lower()
    lv = chart_levels.gen(sym, write=False)
    if not lv:
        print("sin cache para", sym); sys.exit(1)
    print("KEY:", "sí" if _load_env()[0] else "NO")
    print("DET :", deterministic(lv))
    print("TRIG:", trigger_key(lv))
    ai = deepseek(lv)
    print("AI  :", ai or "(no disponible)")
