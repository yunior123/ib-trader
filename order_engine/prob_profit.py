#!/usr/bin/env python3
"""prob_profit.py — OVERLAY de PROBABILIDAD DE PROFIT para el order_engine (F3, doc §5).

El chip que va a la DERECHA del icono buy en el gráfico: dado un contrato de opción que
Yunior pinta como zona (símbolo, nivel-gatillo del subyacente, buy/sell, call/put, expiry),
¿qué probabilidad HONESTA tiene de dar profit? Compone —todo ya medido/vivo, nada inventado,
degradación limpia si falta un insumo (jamás crash)— cuatro capas:

  1. ESTRUCTURA GAMMA (gex_core vía chart_levels + narrator.structural_signal, doctrina
     [[gamma-regime-walls]]/[[gexa-framework]]): recomputa GEX/flip/muros AL nivel-gatillo.
     ¿El nivel se dirige HACIA un imán oro (gamma+) en el sentido del trade, o CHOCA un muro
     (1er toque rebota ~70%)? régimen POS (pin, amortigua) vs NEG (whipsaw, amplifica);
     distancia al flip (pegado = transición sin lado). **HONESTO: mapa todo-acelerador NEG
     SIN imán oro = no hay lado limpio -> "whipsaw sin lado limpio" (post-mortem QQQ 2026-07-24),
     salvo band-walk confirmado por el flujo.**
  2. FLUJO (direction_view.compute): flecha compuesta flip+muros+GEX+flota+momentum+inflación+
     componentes+spike-flow de capitanes. ¿apunta a favor del trade?
  3. TÉCNICOS (signal_conditioning.conditioned_prob): prob condicionada hora×flota×inflación×
     componentes-QQQ×spike-flow. Capitán EN CONTRA = veto (regla #12).
  4. AGENTES/CRÍTICO (opcional): veredicto bull/bear + crítica, leído de un CACHE fresco
     (order_engine/state/agents_<sym>.json). NUNCA se invoca TradingAgents en el hot-path
     (sería lento); si no hay cache fresco -> se omite con nota y baja la confianza.

API:
  prob_profit(sym, level, side, kind, exp=None) -> dict {
     prob:0..100, verdict:'GO'|'CAUTION'|'NO-GO', why:[...],
     regime, magnet:{price,kind,dir}|None, walls:{call,put},
     components:{gamma,flow,technical,agents,critic}  # score [-1..1] o None si ausente
  }

Rápido (<1s): sin red en el hot-path (usa el cache TWS opt_chain_<sym>.txt y los bars de la
flota); TradingAgents jamás en línea. SEÑAL-SOLAMENTE — este módulo solo PUNTÚA; no coloca
ni modifica órdenes.
CLI: python3 order_engine/prob_profit.py NVDA 205 buy call 20260815   -> imprime JSON.
"""
import os, sys, json, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

# pesos de composición (estructura manda; agentes/crítico son contexto)
W = {"gamma": 1.6, "flow": 1.2, "technical": 1.1, "agents": 0.7, "critic": 0.4}
CORE = ("gamma", "flow", "technical")            # insumos cuya ausencia baja la confianza
AGENTS_TTL = int(os.environ.get("PROB_AGENTS_TTL", "21600"))   # 6h: cache de agentes válido
GO_MIN = float(os.environ.get("PROB_GO_MIN", "62"))
CAUTION_MIN = float(os.environ.get("PROB_CAUTION_MIN", "52"))


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def _dfav(side, kind):
    """Dirección FAVORABLE al trade en el subyacente: comprar call / vender put = alcista (+1);
    comprar put / vender call = bajista (-1). (Idéntico a order_ticket.build.)"""
    return 1 if (kind.lower().startswith("c")) == (side.lower() == "buy") else -1


def _days_to_exp(exp):
    """Días de calendario hasta YYYYMMDD (None -> 0 = 0DTE/hoy). Degrada a 0."""
    if not exp:
        return 0
    try:
        t = time.mktime(time.strptime(str(exp), "%Y%m%d"))
        return max(0, int((t - time.time()) // 86400) + 1)
    except Exception:
        return 0


# ------------------------------ 1) ESTRUCTURA GAMMA ------------------------------
def _gamma_component(sym, level, dfav, all_exp):
    """Recomputa el mapa GEX AL nivel-gatillo (spot=level) y puntúa la estructura para el
    trade. -> (dict, lv). score en [-1..1] a favor del trade; flags transition/whipsaw."""
    out = {"score": None, "regime": None, "magnet": None,
           "walls": {"call": None, "put": None}, "why": [],
           "transition": False, "whipsaw": False, "missing": True}
    try:
        import chart_levels
        lv = chart_levels.gen(sym, spot=float(level), write=False, all_exp=all_exp)
    except Exception:
        lv = None
    if not lv or not lv.get("flip") or not lv.get("spot"):
        out["why"].append("sin mapa GEX fresco (gamma neutral, confianza ↓)")
        return out, None
    out["missing"] = False
    spot = lv["spot"]; flip = lv["flip"]
    cw = lv.get("call_wall"); pw = lv.get("put_wall")
    em = lv.get("em") or spot * 0.02
    press = lv.get("pressure") or 0
    out["walls"] = {"call": cw, "put": pw}
    reg_local = "POS" if spot >= flip else "NEG"          # régimen VISTO desde el nivel
    out["regime"] = reg_local
    fav = "up" if dfav > 0 else "down"
    em_pct = (em / spot * 100) or 2.0

    # a) TRANSICIÓN: pegado al flip -> no hay lado limpio
    dflip = (spot - flip) / spot * 100
    if abs(dflip) < 0.13:
        out["transition"] = True
        out["score"] = 0.0
        out["why"].append(f"pegado al flip {flip} (±{abs(dflip):.2f}%) — transición, sin lado limpio")
        return out, lv

    score = 0.0
    # b) IMÁN estructural (nodo oro gamma+) — reusa la doctrina de narrator.structural_signal
    sig = None
    try:
        import narrator
        sig = narrator.structural_signal(lv)
    except Exception:
        pass
    magnet_toward = False
    if sig and sig.get("kind") in ("magnet", "pin") and sig.get("dir") in ("up", "down"):
        mp, md, mk = sig.get("price"), sig.get("dir"), sig.get("kind")
        out["magnet"] = {"price": mp, "kind": mk, "dir": md}
        if md == fav:
            magnet_toward = True
            score += 0.70 if mk == "magnet" else 0.48   # se DIRIGE al imán vs ya PINEADO en él
            out["why"].append(f"{sym} {'↑' if fav=='up' else '↓'} hacia imán oro {mp} "
                              f"({'se dirige' if mk=='magnet' else 'pin'}, {reg_local})")
        else:
            score -= 0.60
            out["why"].append(f"imán oro {mp} EN CONTRA ({md}) — jala al lado opuesto del trade")
    else:
        # sin imán oro dominante
        if reg_local == "NEG":
            out["whipsaw"] = True
            score -= 0.35
            out["why"].append("whipsaw sin lado limpio (NEG, sin imán oro) — post-mortem QQQ 2026-07-24")
        else:
            out["why"].append(f"POS sin imán dominante (rango/pin difuso, {reg_local})")

    # c) MURO en el camino (sentido favorable): 1er toque rebota ~70% (oi-magnets-protocol);
    #    con recorrido libre en unidades de EM -> pequeño bono.
    fav_wall = cw if dfav > 0 else pw
    if fav_wall:
        d_wall = (fav_wall - spot) / spot * 100 * dfav   # % de recorrido hasta el muro a favor
        if 0 < d_wall <= 0.4:
            score -= 0.30
            out["why"].append(f"muro {'call' if dfav>0 else 'put'} {fav_wall} inmediato "
                              f"(rebota ~70% 1er toque)")
        elif d_wall > 0.4:
            score += 0.12 * min(1.0, d_wall / em_pct)     # recorrido libre hasta el muro

    # d) presión de dealers: POS+ refuerza el pin/imán; NEG- confirma la amplificación a favor
    if press:
        if reg_local == "POS" and press >= 40 and magnet_toward:
            score += 0.10
        elif reg_local == "NEG" and press <= -40:
            score += 0.06 * dfav * (1 if dfav > 0 else 1)  # amplifica: peso leve, el signo lo da el flujo

    out["score"] = round(_clamp(score), 3)
    return out, lv


# ------------------------------ 2) FLUJO ------------------------------
def _flow_component(sym, dfav):
    out = {"score": None, "why": [], "missing": True}
    try:
        import direction_view as DV
        r = DV.compute(sym)
        s = float(r.get("score", 0.0))                    # +up / -down
        fav = _clamp(s * dfav)                            # >0 = flecha a favor del trade
        out.update(score=round(fav, 3), dir=r.get("dir"), prob=r.get("prob"),
                   raw_score=round(s, 3), missing=False)
        out["why"].append(f"flecha {str(r.get('dir','?')).upper()} {r.get('prob','?')}% "
                          f"(score {s:+.2f}) {'a favor' if fav >= 0 else 'EN CONTRA'} del trade")
    except Exception:
        out["why"].append("direction_view no disponible (flujo neutral, confianza ↓)")
    return out


# ------------------------------ 3) TÉCNICOS ------------------------------
def _tech_component(sym, direction):
    out = {"score": None, "veto": False, "speak": False, "why": [], "missing": True}
    try:
        import signal_conditioning as SC
        r = SC.conditioned_prob("order_engine", sym, direction, 60)   # base 60 neutral -> condiciona
        prob = r["prob"]
        out.update(score=round(_clamp((prob - 60) / 30.0), 3), prob=prob,
                   veto=bool(r["veto"]), speak=bool(r["speak"]), missing=False)
        for w in r.get("why", []):
            if any(k in w for k in ("capitán", "componentes", "hora", "valuación", "spike", "apagada")):
                out["why"].append(w)
        out["why"] = out["why"][:3]
    except Exception:
        out["why"].append("signal_conditioning no disponible (técnicos neutrales, confianza ↓)")
    return out


# ------------------------------ 4) AGENTES / CRÍTICO (opcional, cache) ------------------------------
def _agents_component(sym, dfav):
    """Lee un veredicto CACHEADO de TradingAgents+crítico (order_engine/state/agents_<sym>.json).
    NUNCA invoca el pipeline (lento) en el hot-path. Formato tolerante:
      {verdict:'bull'|'bear'|'neutral', conviction:0..1, asof:epoch, ttl:sec,
       critic:{agree:bool, note:str} | critic_verdict:'agree'|'disagree'}
    -> (agents_dict, critic_dict). Ambos degradan a missing si no hay cache fresco."""
    ag = {"score": None, "why": [], "missing": True}
    cr = {"score": None, "why": [], "missing": True}
    path = os.path.join(REPO, "order_engine", "state", f"agents_{sym.lower()}.json")
    if not os.path.exists(path):
        return ag, cr
    try:
        j = json.load(open(path))
    except Exception:
        return ag, cr
    asof = j.get("asof") or j.get("ts") or 0
    ttl = j.get("ttl") or AGENTS_TTL
    if asof and (time.time() - asof) > ttl:
        ag["why"].append(f"agentes: cache viejo ({int((time.time()-asof)/3600)}h) — omitido")
        return ag, cr
    verdict = str(j.get("verdict", "")).lower()
    conv = float(j.get("conviction", j.get("confidence", 0.5)) or 0.5)
    vsign = 1.0 if verdict in ("bull", "bullish", "buy", "long") else \
            -1.0 if verdict in ("bear", "bearish", "sell", "short") else 0.0
    if vsign != 0.0:
        ag.update(score=round(_clamp(vsign * conv * dfav), 3), verdict=verdict,
                  conviction=round(conv, 2), missing=False)
        ag["why"].append(f"agentes {verdict} (conv {conv:.0%}) "
                         f"{'a favor' if vsign*dfav > 0 else 'en contra'}")
    else:
        ag.update(score=0.0, verdict=verdict or "neutral", missing=False)
        ag["why"].append("agentes neutrales")
    # crítico
    critic = j.get("critic")
    agree = None
    if isinstance(critic, dict):
        agree = critic.get("agree")
        note = critic.get("note")
    else:
        cv = str(j.get("critic_verdict", "")).lower()
        agree = True if cv in ("agree", "confirm") else False if cv in ("disagree", "reject") else None
        note = j.get("critic_note")
    if agree is not None:
        cr.update(score=round(0.5 * (1.0 if agree else -1.0) * (vsign * dfav if vsign else 1.0), 3),
                  agree=bool(agree), missing=False)
        cr["why"].append(f"crítico {'confirma' if agree else 'DISCREPA'}"
                         + (f": {note}" if note else ""))
    return ag, cr


# ------------------------------ COMPOSICIÓN ------------------------------
def prob_profit(sym, level, side, kind, exp=None):
    sym = sym.upper(); side = str(side).lower(); kind = str(kind).lower()
    try:
        level = float(level)
    except Exception:
        level = None
    dfav = _dfav(side, kind)
    direction = dfav                                  # técnicos/agentes usan el signo del trade
    all_exp = _days_to_exp(exp) > 2                    # >2 días -> estructura multi-día, no 0DTE puro

    why = []
    g, lv = _gamma_component(sym, level if level else 0, dfav, all_exp) if level else \
        ({"score": None, "regime": None, "magnet": None, "walls": {"call": None, "put": None},
          "why": ["nivel-gatillo inválido"], "transition": False, "whipsaw": False, "missing": True}, None)
    fl = _flow_component(sym, dfav)
    te = _tech_component(sym, direction)
    ag, cr = _agents_component(sym, dfav)

    comps = {"gamma": g, "flow": fl, "technical": te, "agents": ag, "critic": cr}
    for c in comps.values():
        why.extend(c.get("why", []))

    # flags de doctrina
    veto = bool(te.get("veto"))
    transition = bool(g.get("transition"))
    whipsaw = bool(g.get("whipsaw"))
    magnet = g.get("magnet")
    magnet_against = bool(magnet and magnet.get("dir") and dfav and
                          (magnet["dir"] == "up") != (dfav > 0))
    magnet_toward = bool(magnet and not magnet_against)
    flow_fav = fl.get("score")
    # band-walk: en NEG sin imán oro PERO con flujo fuerte a favor = continuación, NO whipsaw ciego
    band_walk = bool(whipsaw and flow_fav is not None and flow_fav >= 0.40)
    if band_walk:
        why.append("band-walk NEG a favor del flujo — continuación, no whipsaw ciego")

    # --- media ponderada de los componentes presentes ---
    num = den = 0.0
    for name, c in comps.items():
        s = c.get("score")
        if s is None:
            continue
        num += s * W[name]; den += W[name]
    composite = _clamp(num / den) if den else 0.0
    prob = 50 + composite * 40

    # --- degradación de confianza por insumos CORE ausentes ---
    missing_core = sum(1 for k in CORE if comps[k].get("missing"))
    if missing_core:
        prob = 50 + (prob - 50) * (1 - 0.15 * missing_core)      # acerca a 50 (menos convicción)
        why.append(f"confianza ↓: {missing_core} insumo(s) núcleo ausente(s)")
    prob = max(5, min(92 - 8 * missing_core, prob))
    prob = int(round(max(5, prob)))

    # --- veredicto (doctrina + prob) ---
    clean_side = magnet_toward or band_walk or (flow_fav is not None and flow_fav >= 0.35 and not whipsaw)
    hard_nogo = (veto or transition or magnet_against
                 or (whipsaw and not band_walk)         # NEG sin lado ni band-walk = honesto NO-GO
                 or prob < 45)
    if veto:
        why.insert(0, "⛔ capitán EN CONTRA — veto de voz (regla #12)")
    if transition and "transición" not in " ".join(why[:1]):
        pass

    if hard_nogo:
        verdict = "NO-GO"
    elif prob >= GO_MIN and clean_side and missing_core == 0:
        verdict = "GO"
    elif prob >= CAUTION_MIN:
        verdict = "CAUTION"
    else:
        verdict = "NO-GO"

    # razón-cabecera compacta para el chip
    head = {"GO": "estructura y flujo a favor", "CAUTION": "lado no confirmado / confianza parcial",
            "NO-GO": "whipsaw/veto/estructura en contra"}[verdict]

    return {
        "sym": sym, "level": level, "side": side, "kind": kind, "exp": exp,
        "prob": prob, "verdict": verdict, "headline": head,
        "regime": g.get("regime"), "magnet": magnet, "walls": g.get("walls", {"call": None, "put": None}),
        "components": {k: comps[k].get("score") for k in ("gamma", "flow", "technical", "agents", "critic")},
        "flags": {"veto": veto, "transition": transition, "whipsaw": whipsaw,
                  "band_walk": band_walk, "magnet_toward": magnet_toward,
                  "magnet_against": magnet_against, "missing_core": missing_core},
        "why": why[:8],
    }


def _cli():
    a = sys.argv[1:]
    if len(a) < 4:
        print("uso: prob_profit.py SYM LEVEL buy|sell call|put [EXP_YYYYMMDD]")
        print("ej : prob_profit.py NVDA 205 buy call 20260815")
        return
    exp = a[4] if len(a) > 4 else None
    r = prob_profit(a[0], a[1], a[2], a[3], exp)
    icon = {"GO": "🟢", "CAUTION": "🟡", "NO-GO": "🔴"}[r["verdict"]]
    mg = r["magnet"]
    mgs = f"  imán {mg['price']} {mg['kind']} {mg['dir']}" if mg else ""
    print(f"{icon} {r['sym']} {r['kind']}@{r['level']} ({r['side']}) exp {r['exp'] or '0DTE'}: "
          f"P(profit) {r['prob']}%  {r['verdict']} — {r['headline']}  "
          f"[{r['regime']}{mgs}  muros C{r['walls'].get('call')}/P{r['walls'].get('put')}]")
    print(f"    componentes: {json.dumps(r['components'])}")
    for w in r["why"]:
        print(f"    · {w}")
    print("\n" + json.dumps(r, default=str, indent=1))


if __name__ == "__main__":
    _cli()
