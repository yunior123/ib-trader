#!/usr/bin/env python3
"""compass.py — LA BRUJULA: la flecha apunta al PROXIMO movimiento, no al que ya paso.

Orden Yunior 2026-07-25: "la flecha deberia ser como una brujula; si a las 10am SPY esta
tocando el Muro put de 740 y hay flujo masivo de puts con posibilidad de rebote fuerte,
entonces la flecha debe moverse hacia ARRIBA, y asi para todos los casos, ultraprecisa".

POR QUE NO SIRVE LA MEDIA PONDERADA (el bug de forma que esto arregla)
---------------------------------------------------------------------
direction_view combinaba TODOS los factores en una media ponderada. En el escenario de
arriba, con los pesos reales del archivo:

    walls        +0.96 x1.0   = +0.96   <- piso, rebote
    captain_flow +1.00 x1.2   = +1.20   <- piso, rebote (reglas 11 y 12)
    bollinger    +0.67 x1.15  = +0.77   <- sobreventa, rebote
    flip         -0.80 x1.5   = -1.20   <- ya cayo
    fleet        -1.00 x1.4   = -1.40   <- ya cayo
    components   -0.70 x1.3   = -0.91   <- ya cayo
    momentum     -1.00 x1.0   = -1.00   <- ya cayo
    magnet       -1.00 x1.1   = -1.10   <- ya cayo
    score = -2.68/9.65 = -0.278  ->  FLECHA ABAJO 61%

...justo cuando la doctrina de la casa canta REBOTE. La causa raiz no es un peso mal
puesto: es que una media mezcla dos familias incompatibles — factores de DONDE HA ESTADO
(momentum, lado del flip, amplitud, flota, iman) y factores de DONDE VA A GIRAR (Muro,
%B extremo, flujo del capitan, agotamiento). En TODO extremo real los de tendencia estan
maximamente en contra, asi que promediar SIEMPRE diluye la llamada de reversion.

LA BRUJULA: maquina de estados. EL ESTADO FIJA EL SIGNO; los factores solo modulan la
confianza DENTRO del estado. Y en reversion el momentum cambia de papel: su magnitud es
COMBUSTIBLE (cuanto mas fuerte cayo hacia un piso IMPRESO con puts inundando, mas elastico
el latigazo), no un voto en contra.

ESTADOS (excluyentes, por precedencia)
  SIN LECTURA          sin mapa fresco / libro THIN / sin barras contiguas -> plana, y dice por que
  REVERSION EN EXTREMO nivel IMPRESO + >=2 familias de giro + ningun veto -> la brujula GIRA
  CONTINUACION         un veto de doctrina activo -> la brujula NO gira ("no fadear")
  APROXIMANDO          va hacia el nivel pero AUN NO HA IMPRESO -> flecha hueca, "esperando print"
  CAJA / PIN           gamma+ densa entre Muros sin extremo -> plana, bordes como objetivo

LOS 4+ VETOS (doctrina existente, no inventada)
  V1 band-walk en >=2 TF a favor del movimiento           (regla 1: banda reventada a favor = continuacion)
  V2 regimen NEG sin pin impreso                          (memoria negative-gamma-whipsaw: NEG es caja, no direccion)
  V3 spot bajo el VT congelado                            (fadear prohibido; feature minada vol-trigger)
  V4 el Muro es TRAMPILLA, no pin                         (gex_core *_kind; antes indistinguible)
  V5 3+ toques del Muro                                   (protocolo imanes: 3+ = exhausto -> lado de la ruptura)
  V6 dia de catalizador del lider                         (excepcion explicita de la regla 11)

PRINT O NADA: sin 2 lecturas en el nivel el estado es APROXIMANDO, jamas la flecha
confiada. Esa es la linea entre ANTICIPAR y FANTASEAR.

HISTERESIS (regla 3): un estado nuevo necesita 2 computos consecutivos para entrar. Si no,
la brujula tiembla en la frontera y es crying-wolf.

HONESTIDAD DE PROBABILIDAD: prob_source='medido' solo si hay celda de calibracion con n
suficiente; si no 'doctrina', y ahi la prob se topa a DOCTRINE_CAP. Nunca se presenta un
prior como una medida.

SENAL-SOLAMENTE. Puro stdlib, sin red, compatible py3.9 (venv) y py3.12 (venv-chart).
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- umbrales (los que son doctrina citada van marcados; el resto son de forma) ---
NEAR_PCT = 0.0015        # 0.15% del spot = "en el nivel" (zona de toque)
PRINT_MIN = 2            # PRINT O NADA: 2 lecturas cruzando (doctrina regla 2)
PRINT_LOOKBACK = 8       # barras 1m donde buscar esas lecturas
APPROACH_EM = 0.35       # <0.35 EM al nivel = "aproximando"
FLOW_MIN = 0.25          # |flujo capitan| minimo para contar como familia
PCTB_HI = 0.85           # extremo alto (mismo umbral que direction_view)
PCTB_LO = 0.15           # extremo bajo
BANDWALK_TF_MIN = 2      # >=2 TF band-walking a favor = continuacion (doctrina regla 1)
TOUCH_EXHAUST = 3        # 3+ toques = muro exhausto (protocolo imanes)
FUEL_SAT = 2.5           # |z| de saturacion del combustible de momentum
FUEL_MAX = 8             # puntos de prob que puede aportar el combustible
DOCTRINE_CAP = 78        # tope de prob cuando la fuente es doctrina, no medida
HYST_N = 2               # computos consecutivos para cambiar de estado

S_REV = "REVERSION EN EXTREMO"
S_CONT = "CONTINUACION"
S_APPR = "APROXIMANDO"
S_BOX = "CAJA / PIN"
S_NONE = "SIN LECTURA"

# priors DOCTRINALES por numero de familias de giro (no son win-rates medidos)
_PRIOR_REV = {2: 62, 3: 68, 4: 72}
_PRIOR_CONT = 60
_PRIOR_CONT_BANDWALK = 65
_PRIOR_BOX = 50

_HIST = {}   # {sym: {"state": str, "cand": str, "n": int}} — histeresis por simbolo


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _sgn(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def blank_evidence(sym="?", spot=None):
    """Evidencia vacia — todo lo desconocido es None, nunca 0 (0 es una afirmacion)."""
    return {
        "sym": sym, "spot": spot, "em": None, "regime": None, "flip": None,
        "levels": [],            # [{price, kind, wall_kind, touch_idx}]
        "bars": None,            # [(ts,o,h,l,c,v)] 1m, para contar prints
        "r6": None, "r15": None, "z6": None,
        "pctb_1m": None, "pctb_15m": None,
        "bandwalk_tf": 0, "bandwalk_dir": 0,
        "flow": None,            # + = puts inundando (piso) / - = calls (techo)
        "force_phase": None, "exhaustion": None,
        "candle_bias": 0,        # +1 alcista / -1 bajista / 0
        "vt": None,              # Volatility Trigger congelado (None = no lo tenemos)
        "book_label": None, "book_coef": None,
        "leader_catalyst": False,
        "bars_contig": True,
        "calib": None,           # {"p":float,"n":int,"lo":float} si hay celda medida
    }


def _prints_at(bars, level, spot):
    """Cuantas de las ultimas barras TOCARON el nivel (PRINT O NADA)."""
    if not bars or not level or not spot:
        return 0
    band = spot * NEAR_PCT
    n = 0
    for b in bars[-PRINT_LOOKBACK:]:
        try:
            hi, lo = float(b[2]), float(b[3])
        except (IndexError, TypeError, ValueError):
            continue
        if lo - band <= level <= hi + band:
            n += 1
    return n


def _nearest_level(ev):
    """El nivel que el precio esta PROBANDO, con su distancia y prints.

    No es el geometricamente mas cercano: es el del lado del que VIENE el precio. Si cae
    (r6<0) el nivel que se pone a prueba esta ABAJO, aunque haya otro 0.4% por encima —
    "SPY esta tocando el Muro put de 740" habla del suelo, no del techo que queda arriba.
    Sin momentum se cae al mas cercano en valor absoluto."""
    spot = ev.get("spot")
    if not spot or not ev.get("levels"):
        return None
    move = _sgn(ev.get("r6") or 0)
    side = move           # cae (move=-1) -> se prueba lo de ABAJO ; sube -> lo de arriba

    def pick(cands):
        best = None
        for L in cands:
            p = L.get("price")
            if not p:
                continue
            d = abs(p - spot) / spot
            if best is None or d < best["dist"]:
                best = dict(L)
                best["dist"] = d
                best["above"] = p > spot
        return best

    best = None
    if side:
        best = pick([L for L in ev["levels"]
                     if L.get("price") and _sgn(L["price"] - spot) in (side, 0)])
    if best is None:
        best = pick(ev["levels"])
    if best is None:
        return None
    if best["above"] is None:
        best["above"] = best["price"] > spot
    best["prints"] = _prints_at(ev.get("bars"), best["price"], spot)
    best["printed"] = best["prints"] >= PRINT_MIN
    return best


def _rebound_dir(level, ev):
    """Direccion del REBOTE en ese nivel: alejandose de el.
    Bajo el spot (piso) -> arriba. Sobre el spot (techo) -> abajo.
    Si el precio esta justo encima, manda de que lado vino (r6)."""
    if level.get("above") is True:
        return -1
    if level.get("above") is False:
        return 1
    r6 = ev.get("r6")
    return 1 if (r6 or 0) < 0 else -1


def _families(ev, rdir):
    """Familias INDEPENDIENTES que confirman un giro hacia rdir. Devuelve (n, [nombres])."""
    fam = []
    # 1) FLUJO del capitan/ballena a favor del rebote (reglas 11 y 12)
    flow = ev.get("flow")
    if flow is not None and abs(flow) >= FLOW_MIN and _sgn(flow) == rdir:
        fam.append("flujo capitan {} ({:+.2f})".format(
            "puts=piso" if rdir > 0 else "calls=techo", flow))
    # 2) ESTIRAMIENTO: %B extremo en 1m Y 15m (BOLLINGER-SIEMPRE, 2 TF)
    b1, b15 = ev.get("pctb_1m"), ev.get("pctb_15m")
    if b1 is not None and b15 is not None:
        if rdir > 0 and b1 <= PCTB_LO and b15 <= PCTB_LO:
            fam.append("%B 1m {:.2f} y 15m {:.2f} extremo bajo".format(b1, b15))
        elif rdir < 0 and b1 >= PCTB_HI and b15 >= PCTB_HI:
            fam.append("%B 1m {:.2f} y 15m {:.2f} extremo alto".format(b1, b15))
    # 3) AGOTAMIENTO de la pata que llega al nivel
    if ev.get("force_phase") in ("AGOTAMIENTO", "GIRO"):
        fam.append("fuerza en {}".format(ev["force_phase"]))
    # 4) VELA de reversion en el nivel
    if ev.get("candle_bias") and _sgn(ev["candle_bias"]) == rdir:
        fam.append("vela de reversion")
    return len(fam), fam


def _vetoes(ev, level, rdir):
    """Vetos de doctrina que PROHIBEN fadear. Devuelve lista de motivos (vacia = via libre)."""
    v = []
    move = _sgn(ev.get("r6") or 0)          # sentido del movimiento reciente
    # V1 band-walk a favor del movimiento en >=2 TF (regla 1)
    if (ev.get("bandwalk_tf") or 0) >= BANDWALK_TF_MIN and ev.get("bandwalk_dir") and \
            _sgn(ev["bandwalk_dir"]) == move and move == -rdir:
        v.append("band-walk en {} TF a favor: continuacion, NO fadear".format(ev["bandwalk_tf"]))
    # V2 regimen NEG sin pin impreso (NEG es caja/acelerador, no direccion)
    if ev.get("regime") == "NEG" and level.get("wall_kind") != "pin":
        v.append("regimen NEG (acelerador): el nivel no es piso, NO fadear en el aire")
    # V3 bajo el Volatility Trigger congelado -> licencia de momentum, fade prohibido
    vt, spot = ev.get("vt"), ev.get("spot")
    if vt and spot and spot < vt:
        v.append("bajo el VT {} congelado: fadear prohibido".format(round(vt, 2)))
    # V4 el Muro es TRAMPILLA (gamma acumulada NEG en ese nivel), no pin
    if level.get("wall_kind") == "trampilla":
        v.append("{} es TRAMPILLA (gamma NEG), no piso".format(level.get("kind") or "el nivel"))
    # V5 muro exhausto por toques
    ti = level.get("touch_idx")
    if ti is not None and ti >= TOUCH_EXHAUST:
        v.append("{}º toque: muro exhausto -> lado de la ruptura".format(ti))
    # V6 dia de catalizador del lider (excepcion explicita de la regla 11)
    if ev.get("leader_catalyst"):
        v.append("catalizador del lider: la ballena puede ser continuacion")
    return v


def load_decay(path=None):
    """Retrocesos MEDIDOS de data/momentum_decay.json (momentum_decay.py).
    -> {"por_ticker":{...}, "agregado":{...}} o None. Degradacion limpia si falta."""
    import json
    p = path or os.path.join(REPO, "data", "momentum_decay.json")
    try:
        with open(p) as f:
            d = json.load(f)
        if "agregado" not in d:
            return None
        return d
    except Exception:
        return None


def _decay_cell(decay, sym, move_dir, now_min=None):
    """Celda medida para (ticker, sentido de la PATA, sesion). Cae al agregado si el ticker
    no esta cubierto (momentum_decay solo mide 6). Devuelve (celda, fuente)."""
    if not decay:
        return None, None
    # la pata que llega al nivel: bajista si el precio cayo hacia un piso
    leg = "bear" if move_dir < 0 else "bull"
    if now_min is None:
        import time as _t
        lt = _t.localtime()
        now_min = lt.tm_hour * 60 + lt.tm_min
    ses = "manana" if now_min < 12 * 60 else "tarde"
    # celda del propio ticker solo si tiene n suficiente; si es fina, mejor el agregado
    pt = (decay.get("por_ticker") or {}).get((sym or "").upper())
    if pt and (pt.get(leg, {}).get(ses, {}).get("n") or 0) >= 30:
        return pt[leg][ses], "medido"
    ag = (decay.get("agregado") or {}).get(leg, {})
    for key in (ses, "todo"):
        if ag.get(key, {}).get("n"):
            return ag[key], "medido-agregado"
    return None, None


def amplitude(ev, rdir, decay=None):
    """CUANTO se espera que rebote (Yunior 2026-07-25: "puede revertir fuerte o solo un
    poco; calculalo y mueve la flecha en consecuencia").

    Se toma el MINIMO de las restricciones — nunca prometer mas de lo que cabe:
      room     distancia al SIGUIENTE nivel estructural en el sentido del rebote.
               Doctrina imanes: JAMAS contar con atravesar un Muro intermedio.
      pull     distancia a la media de Bollinger (el "efecto iman a la SMA20").
      retrace  50% de la pata, con su probabilidad MEDIDA (prob_retroceso_50).
      em_left  lo que queda del expected move del dia.

      amp = min(room, max(pull, retrace), em_left)

    El grado se mide contra el EM del PROPIO ticker (no un % absoluto), y la regla 11
    (espada-ballena) topa el grado a REBOTE cuando el giro lo sostiene solo el flujo:
    "profit pequeno y seguro, no pedir mas"."""
    spot = ev.get("spot")
    if not spot or not rdir:
        return None
    em_pct = ((ev.get("em") or spot * 0.02) / spot) * 100
    cons = {}

    # room: siguiente nivel estructural en el sentido del rebote (excluye el que se toca)
    lv = _nearest_level(ev) or {}
    touched = lv.get("price")
    nxt = None
    for L in ev.get("levels") or []:
        p = L.get("price")
        if not p or p == touched:
            continue
        if (rdir > 0 and p > spot) or (rdir < 0 and p < spot):
            if nxt is None or abs(p - spot) < abs(nxt - spot):
                nxt = p
    if nxt:
        cons["room"] = abs(nxt - spot) / spot * 100

    # pull: la media de Bollinger como iman de reversion
    mid = ev.get("bb_mid")
    if mid and _sgn(mid - spot) == rdir:
        cons["pull"] = abs(mid - spot) / spot * 100

    # retrace: 50% de la pata, con probabilidad MEDIDA
    cell, csrc = _decay_cell(decay if decay is not None else load_decay(),
                             ev.get("sym"), -rdir, ev.get("now_min"))
    leg = ev.get("leg_pct")
    if leg:
        cons["retrace"] = abs(leg) * 0.5
    if cell and cell.get("ext_mediana_pct"):
        cons["ext_medido"] = float(cell["ext_mediana_pct"])

    # em_left: techo por presupuesto de movimiento del dia
    used = ev.get("em_used_pct")
    if used is not None and em_pct:
        cons["em_left"] = max(0.0, em_pct - abs(used))

    if not cons:
        return None
    upside = max([v for k, v in cons.items() if k in ("pull", "retrace", "ext_medido")] or [0.0])
    if upside <= 0:
        upside = min(cons.values())
    caps = [v for k, v in cons.items() if k in ("room", "em_left")]
    amp = min([upside] + caps) if caps else upside
    amp = max(0.0, amp)

    ratio = (amp / em_pct) if em_pct else 0.0
    if ratio >= 0.50:
        grade = "LATIGAZO"
    elif ratio >= 0.20:
        grade = "REBOTE"
    else:
        grade = "SCALP"

    # regla 11: si el giro lo sostiene SOLO el flujo, no pedir el latigazo entero
    flow_only = bool(ev.get("flow")) and not ev.get("bb_mid") and not ev.get("leg_pct")
    capped = False
    if flow_only and grade == "LATIGAZO":
        grade, capped = "REBOTE", True

    return {
        "amp_pct": round(amp, 3),
        "amp_price": round(spot * (1 + rdir * amp / 100), 2),
        "grade": grade,
        "mag": round(_clamp(ratio / 0.6, 0.0, 1.0), 3),   # 0..1 para escalar la flecha
        "ratio_em": round(ratio, 3),
        "binding": (min(cons, key=lambda k: cons[k]) if caps else None),
        "constraints": {k: round(v, 3) for k, v in cons.items()},
        "retrace_prob": (None if not cell else cell.get("prob_retroceso_50")),
        "retrace_n": (None if not cell else cell.get("n")),
        "retrace_src": csrc,
        "leg_minutes_median": (None if not cell else cell.get("mediana_min")),
        "capped_by_rule11": capped,
    }


def _prob(state, nfam, ev, calib, amp=None):
    """Probabilidad HONESTA. Orden de preferencia:
      1. celda de calibracion propia (calibration_ledger) con n>=30  -> 'medido'
      2. prob_retroceso_50 MEDIDA de momentum_decay para el estado de reversion
      3. prior doctrinal, topado a DOCTRINE_CAP y etiquetado 'doctrina'
    Nunca se presenta un prior como una medida."""
    if calib and calib.get("n") and calib["n"] >= 30 and calib.get("lo") is not None:
        return int(round(_clamp(calib["lo"] * 100, 50, 90))), "medido"
    # NOTA (honestidad, 2026-07-25): NO se usa prob_retroceso_50 de momentum_decay como
    # probabilidad de la flecha. Esa medida condiciona en "hubo un impulso", no en "hubo
    # NUESTRO setup (nivel impreso + >=2 familias + sin vetos)": son poblaciones distintas y
    # usarla aqui inflaria la flecha al 90% con una n que no es de este setup. Se publica en
    # `amplitude.retrace_prob` como lo que es — cuanto retrocede un impulso — y la
    # probabilidad de la flecha sigue siendo DOCTRINA hasta que barrier-labels + null-control
    # llenen celdas propias en calibration_ledger.
    if state == S_REV:
        base = _PRIOR_REV.get(min(nfam, 4), 62)
        # MOMENTUM COMO COMBUSTIBLE: cuanto mas fuerte llego al nivel, mas elastico el latigazo
        z = ev.get("z6")
        if z is None and ev.get("r6") is not None:
            z = (ev["r6"] or 0) / 0.5
        fuel = _clamp(abs(z or 0) / FUEL_SAT, 0.0, 1.0) * FUEL_MAX
        base += fuel
    elif state == S_CONT:
        base = _PRIOR_CONT_BANDWALK if (ev.get("bandwalk_tf") or 0) >= BANDWALK_TF_MIN else _PRIOR_CONT
    elif state == S_APPR:
        base = _PRIOR_REV.get(min(nfam, 4), 62) - 8      # aun no ha impreso: se rebaja
    else:
        base = _PRIOR_BOX
    return int(round(_clamp(base, 50, DOCTRINE_CAP))), "doctrina"


def classify(ev, hist=None, decay=None):
    """FUNCION PURA: evidencia -> estado/direccion/prob/AMPLITUD. `hist` = estado previo para
    la histeresis ({"state","cand","n"}); si es None no se aplica (util en tests)."""
    sym = ev.get("sym", "?")
    spot = ev.get("spot")
    why = []
    fading = []
    level = _nearest_level(ev)
    nfam, fams = 0, []
    vetoes = []
    rdir = 0

    # ---- 0) SIN LECTURA: fail-loud, jamas fingir un mapa ----
    if not spot:
        state, d = S_NONE, 0
        why.append("sin spot")
    elif not ev.get("bars_contig", True):
        state, d = S_NONE, 0
        why.append("barras no contiguas (hueco de feed): no se afirma nada")
    elif ev.get("book_label") == "THIN" or ev.get("book_coef") == 0:
        state, d = S_NONE, 0
        why.append("libro THIN: los niveles gamma son decoracion en este nombre")
    elif not ev.get("regime") or not level:
        state, d = S_NONE, 0
        why.append("sin mapa GEX fresco" if not ev.get("regime") else "sin niveles estructurales")
    else:
        rdir = _rebound_dir(level, ev)
        nfam, fams = _families(ev, rdir)
        vetoes = _vetoes(ev, level, rdir)
        near = level["dist"] <= NEAR_PCT * 2
        em_pct = ((ev.get("em") or spot * 0.02) / spot)
        approaching = level["dist"] <= max(APPROACH_EM * em_pct, NEAR_PCT * 2)
        lbl = "{} {}".format(level.get("kind") or "nivel", round(level["price"], 2))

        if vetoes and (near or approaching):
            # ---- CONTINUACION: la brujula NO gira; el estado lo fija el veto ----
            state = S_CONT
            move = _sgn(ev.get("r6") or 0)
            if move == 0 and ev.get("flip") and spot:
                move = 1 if spot >= ev["flip"] else -1
            d = move
            why.append("{}: NO fadear".format(vetoes[0]))
            why.extend(vetoes[1:2])
            if fams:
                fading.append("se ignoran {} familia(s) de giro: {}".format(nfam, "; ".join(fams)))
        elif level["printed"] and nfam >= 2:
            # ---- REVERSION EN EXTREMO: la brujula GIRA ----
            state, d = S_REV, rdir
            why.append("{} IMPRESO ({} lecturas)".format(lbl, level["prints"]))
            why.extend(fams[:3])
            if ev.get("r6") is not None and _sgn(ev["r6"]) == -rdir:
                fading.append("momentum {:+.2f}% (es el COMBUSTIBLE del latigazo, no un voto en contra)"
                              .format(ev["r6"]))
            if ev.get("flip") and spot and _sgn(spot - ev["flip"]) == -rdir:
                fading.append("spot del lado {} del flip {}".format(
                    "bajo" if rdir > 0 else "sobre", round(ev["flip"], 2)))
        elif approaching and nfam >= 2:
            # ---- APROXIMANDO: PRINT O NADA. Se ve venir, no se afirma ----
            state, d = S_APPR, rdir
            why.append("aproximando {} — esperando print ({}/{})".format(
                lbl, level["prints"], PRINT_MIN))
            why.extend(fams[:2])
        elif ev.get("regime") == "POS" and not near:
            state, d = S_BOX, 0
            why.append("gamma+ entre Muros, sin extremo: caja")
        else:
            state = S_CONT
            d = _sgn(ev.get("r6") or 0)
            why.append("sin extremo confirmado: manda la tendencia")

    # ---- histeresis (regla 3: senal marginal != decisiva) ----
    pend = None
    if hist is not None:
        prev = hist.get("state")
        if prev is None or prev == state:
            hist["cand"], hist["n"] = state, 0
            hist["state"] = state
        elif hist.get("cand") == state:
            hist["n"] = hist.get("n", 0) + 1
            if hist["n"] + 1 >= HYST_N:
                hist["state"], hist["cand"], hist["n"] = state, state, 0
            else:
                pend = state
                state = prev
                why.insert(0, "estado {} pendiente de confirmar ({}/{})".format(
                    pend, hist["n"] + 1, HYST_N))
        else:
            hist["cand"], hist["n"] = state, 0
            pend = state
            state = prev
            why.insert(0, "estado {} pendiente de confirmar (1/{})".format(pend, HYST_N))
        if state != pend and pend is not None:
            d = 0 if state in (S_BOX, S_NONE) else d

    # ---- AMPLITUD: cuanto se espera que se mueva (y con ella se escala la flecha) ----
    amp = None
    if state in (S_REV, S_APPR) and rdir:
        amp = amplitude(ev, rdir, decay=decay)
        if amp:
            why.append("{} esperado {:+.2f}% -> {}{}".format(
                amp["grade"], rdir * amp["amp_pct"], amp["amp_price"],
                "" if not amp.get("retrace_prob") else " (retroceso 50% medido {:.0f}%, n={})".format(
                    amp["retrace_prob"] * 100, amp["retrace_n"])))
            if amp.get("capped_by_rule11"):
                why.append("solo flujo lo sostiene: scalp seguro, no pedir el latigazo (regla 11)")

    prob, psrc = _prob(state, nfam, ev, ev.get("calib"), amp)
    if state in (S_BOX, S_NONE):
        prob, d = 50, 0
        amp = None

    return {
        "sym": sym,
        "state": state,
        "amplitude": amp,
        "mag": (amp or {}).get("mag", 0.0),
        "target": (amp or {}).get("amp_price"),
        "grade": (amp or {}).get("grade"),
        "state_pending": pend,
        "dir": "up" if d > 0 else "down" if d < 0 else "flat",
        "prob": prob,
        "prob_source": psrc,
        "pending_print": state == S_APPR,
        "families": nfam,
        "families_why": fams,
        "vetoes": vetoes,
        "fading": fading,
        "state_why": why[:5],
        "level": (None if not level else {
            "price": level["price"], "kind": level.get("kind"),
            "wall_kind": level.get("wall_kind"), "touch_idx": level.get("touch_idx"),
            "prints": level.get("prints"), "printed": level.get("printed"),
            "dist_pct": round(level["dist"] * 100, 3),
        }),
    }


def classify_sym(ev):
    """Como classify() pero usando el histerico persistente del modulo (lo que usa el chart)."""
    sym = (ev.get("sym") or "?").upper()
    h = _HIST.setdefault(sym, {"state": None, "cand": None, "n": 0})
    return classify(ev, hist=h)


def reset_hist(sym=None):
    if sym is None:
        _HIST.clear()
    else:
        _HIST.pop(sym.upper(), None)


def _cli():
    """Demo del escenario de Yunior: SPY en el Muro put 740 con puts inundando."""
    import json
    ev = blank_evidence("SPY", 740.6)
    ev.update({
        "em": 8.0, "regime": "POS", "flip": 748.0,
        "levels": [{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1}],
        "bars": [(0, 742, 742.2, 741.0, 741.2, 1e6), (0, 741.2, 741.4, 739.9, 740.3, 2e6),
                 (0, 740.3, 740.8, 739.8, 740.6, 3e6)],
        "r6": -0.62, "r15": -0.9, "z6": -2.6,
        "pctb_1m": 0.04, "pctb_15m": 0.08,
        "flow": 1.0, "force_phase": "AGOTAMIENTO",
    })
    r = classify(ev)
    arrow = "^" if r["dir"] == "up" else "v" if r["dir"] == "down" else "-"
    print("{} {} {} {}%  [{}]  ({})".format(
        arrow, r["sym"], r["dir"].upper(), r["prob"], r["state"], r["prob_source"]))
    for w in r["state_why"]:
        print("    - " + w)
    for f in r["fading"]:
        print("    fadeando: " + f)
    print("    nivel:", json.dumps(r["level"]))


if __name__ == "__main__":
    _cli()
