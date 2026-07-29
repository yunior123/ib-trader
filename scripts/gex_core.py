#!/usr/bin/env python3
"""gex_core.py — fuente UNICA de GEX / gamma-flip / muros put-call (2026-07-23).

Extraido de la logica ya probada en daily_fleet_plans.py (chain_stats /
ibkr_chain_stats) para que los ENGINES y el CHART consuman el MISMO calculo, sin
duplicar. ADITIVO: no toca el generador del cron (daily_fleet_plans.py sigue igual;
opcionalmente puede importar esto luego, con backup).

Entradas (lo que ya tenemos):
  - Polygon: por contrato strike, OI, IV/griegas snapshot, expiry, spot.
  - IBKR TWS cache (data/opt_chain_<sym>.txt): strike,right,exp,bid,ask,vol,OI,iv,delta,gamma.

Convencion de signo (dealer-long-calls, la de la casa y la de SqueezeMetrics para
el indice): dealers estan LARGOS gamma en calls (+) y CORTOS gamma en puts (-).
  GEX_strike = sign * gamma * OI * 100 * spot            (convencion CASA, lineal)
  GEX_strike = sign * gamma * OI * 100 * spot^2 * 0.01   (ESTANDAR $/1% de SqueezeMetrics)
La CASA usa la lineal (ranking de strikes identico; el flip y los muros no cambian
de strike). `scale="dollar1pct"` da la version estandar en $ por 1% de movimiento.

Regimen:
  net_gex > 0  -> POSITIVA: dealers amortiguan (mean-reversion, rango, pin al POC).
  net_gex < 0  -> NEGATIVA: dealers amplifican (momentum, band-walk, colas).
Precio por ENCIMA del flip = zona positiva; por DEBAJO = negativa.
"""
import bisect
import math


T_FLOOR = 5.0 / (365.0 * 24.0 * 60.0)   # ~5 min: evita el blow-up de gamma ATM en 0DTE (gamma ~ 1/sqrt(T))

# ---------------------------------------------------------------- HONESTIDAD DE CADENA
# feature #5 chain-honesty (2026-07-25). MEDIDO ese dia sobre data/history/:
#   en RTH  las cadenas IBKR traen iv/delta/gamma en el 100% de las filas (QQQ 80/80,
#           NVDA 40/40 a las 10:00/12:00/14:00/15:30);
#   a 16:16 (ultimo ciclo tras el cierre) TODAS las filas vienen iv=-1 delta=-1 gamma=-1
#           y bid/ask=-1.
# Antes de este cambio ese caso caia en `float(c.get("iv", 0.3)) or 0.3` -> se publicaban
# muros, flip y regimen calculados sobre una IV FABRICADA del 30%, sin decirlo. Y los planes
# de las 04:00 (26 PDFs) leen justamente esa foto de las 16:16. Ahora: se invierte la IV del
# mid cuando el mid EXISTE, y si no se puede, el contrato se EXCLUYE y se cuenta; por debajo
# de MIN_GREEKS_OK el consumidor recibe None, nunca un numero plausible.
R_FREE = 0.045            # misma tasa que opt_recon.py (coherencia entre vivo y reconstruido)
MIN_GREEKS_OK = 0.5       # < 50% de filas con griegas usables -> sin voz gamma (spec #5)
STALE_S = 45 * 60         # cadena mas vieja que esto = rancia (los muros ya no son de hoy)
ROLL_HOUR_ET = 16         # 16:00 ET: al cierre el contrato que vence HOY deja de existir
RTH_LO, RTH_HI = 9 * 60 + 30, 16 * 60      # ventana en la que bid/ask son reales


def _ncdf(x):
    """N(x) con erfc (sin scipy), igual que opt_recon.py / skill option-pricing-pro."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs_price(S, K, T, iv, cp="C", r=R_FREE):
    """Precio BS europeo. None si los argumentos no permiten un precio (JAMAS 0.0:
    un cero plausible convierte "no se" en "se, y vale cero")."""
    if S is None or K is None or T is None or iv is None:
        return None
    if S <= 0 or K <= 0 or T <= 0 or iv <= 0:
        return None
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2.0) * T) / sq
    d2 = d1 - sq
    disc = math.exp(-r * T)
    if str(cp).upper().startswith("C"):
        return S * _ncdf(d1) - K * disc * _ncdf(d2)
    return K * disc * _ncdf(-d2) - S * _ncdf(-d1)


def implied_vol(price, S, K, T, cp="C", r=R_FREE, lo=1e-4, hi=5.0, tol=1e-6, iters=60):
    """IV por BISECCION sobre el precio (60 iteraciones, tol 1e-6 — spec feature #5).

    Devuelve la sigma o **None**; nunca un 0.3 por defecto. None cuando: precio <= 0,
    T <= 0, precio por DEBAJO del valor intrinseco descontado (precio rancio/arbitraje),
    o por ENCIMA del maximo alcanzable con sigma=hi (IV fuera del bracket, no se extrapola).
    Misma matematica que opt_recon.implied_vol; aqui vive sin dependencias (gex_core solo
    importa math/bisect y lo consume el camino vivo)."""
    if price is None or price <= 0 or S is None or S <= 0 or K is None or K <= 0:
        return None
    if T is None or T <= 0:
        return None
    disc = math.exp(-r * T)
    intrinsic = (max(S - K * disc, 0.0) if str(cp).upper().startswith("C")
                 else max(K * disc - S, 0.0))
    if price < intrinsic - 1e-9:
        return None
    p_hi = bs_price(S, K, T, hi, cp, r)
    if p_hi is None or price > p_hi:
        return None
    p_lo = bs_price(S, K, T, lo, cp, r)
    if p_lo is None or price < p_lo:
        return None
    a, b = lo, hi
    for _ in range(iters):
        mid = 0.5 * (a + b)
        pm = bs_price(S, K, T, mid, cp, r)
        if pm is None:
            return None
        if pm > price:
            b = mid
        else:
            a = mid
        if b - a < tol:
            break
    return 0.5 * (a + b)


def forward_from_parity(call_mid, put_mid, K, T, r=R_FREE):
    """Forward implicito por paridad put-call: C - P = e^{-rT}(F - K)  ->  F = K + (C-P)e^{rT}.

    Con el forward medido del propio par no hace falta suponer que el spot del fichero es
    el spot de referencia de la cadena (dividendos, coste de acarreo, spot rancio de la
    cabecera). None si falta cualquiera de los dos mids o T no es valido."""
    if call_mid is None or put_mid is None or K is None or T is None or T <= 0:
        return None
    return K + (call_mid - put_mid) * math.exp(r * T)


def bs_delta(S, K, T, iv, cp="C", r=R_FREE):
    """Delta BS (fallback cuando el proveedor no lo trae). **None**, jamas 0.0, si los
    argumentos no dan un delta: un 0.0 aqui significa "OTM lejano", no "no se". (bs_gamma si
    devuelve 0.0 porque una gamma nula es inocua en la suma; un delta nulo borra el strike
    del DEX y mueve el neto — y del signo del neto sale la voz.)"""
    if S is None or K is None or T is None or iv is None:
        return None
    if S <= 0 or K <= 0 or iv <= 0:
        return None
    T = max(T, T_FLOOR)
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2.0) * T) / sq
    nd1 = _ncdf(d1)
    return nd1 if str(cp).upper().startswith("C") else nd1 - 1.0


def bs_gamma(S, K, T, iv, r=0.045):
    """Gamma Black-Scholes (fallback cuando no hay gamma del proveedor).
    Piso de T a ~5min: cerca de expiry la gamma ATM tiende a infinito (1/sqrt(T)) y
    distorsiona todo el perfil (pitfall 0DTE, investigacion 2026-07-23)."""
    if iv <= 0 or S <= 0 or K <= 0:
        return 0.0
    T = max(T, T_FLOOR)
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    return pdf / (S * sq)


def bs_vanna(S, K, T, iv, r=0.045):
    """Vanna BS por acción (∂vega/∂S = ∂delta/∂vol). Igual magnitud call/put.
    VEX+ (dorado) = dealers COMPRAN spot al subir la IV; VEX- (morado) = venden."""
    if iv <= 0 or S <= 0 or K <= 0:
        return 0.0
    T = max(T, T_FLOOR)
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    return -pdf * d2 / iv


def bs_charm(S, K, T, iv, cp="C", r=0.045):
    """Charm BS por acción (∂delta/∂t, decaimiento del delta). Motor del drift/pin tardío."""
    if iv <= 0 or S <= 0 or K <= 0:
        return 0.0
    T = max(T, T_FLOOR)
    sq = iv * math.sqrt(T)
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / sq
    d2 = d1 - sq
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    ch = -pdf * (2 * r * T - d2 * sq) / (2 * T * sq)
    return ch if cp == "C" else ch   # con q=0 el término de dividendo se anula


def _iv_of(c):
    """IV usable de un contrato, o None. NUNCA 0.3 por defecto (feature #5).
    Acepta la IV del proveedor (`iv`) o la invertida por biseccion (`iv_inv`), marcando
    con `iv_src` de donde salio para que el consumidor pueda auditarlo."""
    for key in ("iv", "iv_inv"):
        v = c.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return None


def _T_from(c, now=None):
    """Años a vencimiento del contrato. `T` explicita si viene; si no, se DERIVA de
    `exp`. **None** si no hay ninguna de las dos — el contrato queda fuera.

    Por que existe (bug medido el 2026-07-25): `gex_snapshot.contracts_from` construye
    los contratos SIN la clave `T`, y todos los usos hacian `c.get("T", 0.02)`. Como
    `gex_snapshot` llama a `build_gex` directamente (sin pasar por `from_ibkr_cache`,
    que si calcula `T` en :688), el flip de data/gex_snapshot.json se repreciaba
    asumiendo **7,3 dias para TODOS los vencimientos, 0DTE incluido**. Los muros no
    se veian afectados (usan la gamma medida de Polygon), pero el flip si — y del
    flip sale `abs_wall_kind` (pin/trampilla), que es VETO DURO en compass.cpp:630
    y en book_quality. Un numero plausible convertia "no se" en "sé, y es una semana".
    """
    t = c.get("T")
    if t is not None:
        try:
            t = float(t)
            if t > 0:
                return t
        except (TypeError, ValueError):
            pass
    exp = c.get("exp")
    return _T_of(exp, now) if exp else None


def _dte_of(exp, now=None):
    """Dias al vencimiento, o None si `exp` es ilegible. Envoltorio de `_T_of` para que
    un vencimiento roto no reviente el mapa entero (antes: None * 365 -> TypeError)."""
    t = _T_of(exp, now)
    return None if t is None else round(t * 365, 2)


def _gamma_of(c, spot, now=None):
    """Gamma usable: la del proveedor si es >0, si no la BS desde una IV MEDIDA.
    None cuando no hay ninguna de las dos -> el contrato no entra en el perfil."""
    g = c.get("gamma")
    try:
        g = None if g is None else float(g)
    except (TypeError, ValueError):
        g = None
    if g is not None and g > 0:
        return g
    iv = _iv_of(c)
    if iv is None:
        return None
    T = _T_from(c, now)
    if T is None:                     # sin plazo no hay gamma BS: se excluye, no se inventa
        return None
    g = bs_gamma(spot, float(c["strike"]), T, iv)
    return g if g > 0 else None


def _delta_of(c, spot, now=None):
    """Delta usable de un contrato, o None. El del proveedor si es un delta LEGAL
    (0 < |d| <= 1), si no el BS desde una IV medida y `_T_from`.

    El signo lo fija el TIPO de contrato, no el fichero: Polygon manda el delta de put en
    negativo, IBKR lo escribe en positivo en algunas builds, y `-1.00` es su centinela de
    "sin dato" (que es tambien un delta de put perfectamente legal). Por eso el centinela se
    filtra en el parser, donde se ve la fila entera, y aqui solo se normaliza el signo."""
    d = c.get("delta")
    try:
        d = None if d is None else float(d)
    except (TypeError, ValueError):
        d = None
    right = str(c.get("right", "C")).upper()[:1]
    if d is not None and 0 < abs(d) <= 1:
        return abs(d) if right == "C" else -abs(d)
    iv = _iv_of(c)
    if iv is None:
        return None
    T = _T_from(c, now)
    if T is None:
        return None
    return bs_delta(spot, float(c["strike"]), T, iv, right)


def build_exposure(contracts, spot, greek="vanna", scale="dollar1pct"):
    """Perfil de exposición de una griega de 2o orden (vanna/charm) con la misma
    convención dealer-long-calls que el GEX. Devuelve {profile, net, regime, peak}."""
    contracts = list(contracts)
    mult = spot if scale == "house" else spot * spot * 0.01
    fn = bs_vanna if greek == "vanna" else (lambda S, K, T, iv, cp: bs_charm(S, K, T, iv, cp))
    profile = {}
    for c in contracts:
        K = float(c["strike"]); oi = float(c.get("oi", 0) or 0)
        if oi <= 0:
            continue
        right = c["right"].upper()[:1]
        iv = _iv_of(c)                    # None si no hay IV medida/invertida: se EXCLUYE
        if iv is None:
            continue                      # antes: `or 0.3` -> perfil VEX inventado en silencio
        T = _T_from(c)
        if T is None:
            continue                      # antes: 0.02 -> vanna/charm con plazo inventado
        g = fn(spot, K, T, iv) if greek == "vanna" else fn(spot, K, T, iv, right)
        sign = 1.0 if right == "C" else -1.0
        profile[K] = profile.get(K, 0.0) + sign * g * oi * 100 * mult
    net = sum(profile.values())
    peak = max(profile.items(), key=lambda x: abs(x[1]))[0] if profile else None
    return {"profile": profile, "net": net, "regime": "POS" if net >= 0 else "NEG", "peak": peak}


def build_gex(contracts, spot, scale="house"):
    """contracts: iterable de dicts con keys: strike, right ('C'|'P'), oi,
    y (gamma) o (iv, T) para calcular gamma BS. spot: subyacente.

    Devuelve dict:
      profile   : {strike: gex_neto_del_strike}   (calls+ puts-)
      call_gex  : {strike: gex_calls}  (>=0)
      put_gex   : {strike: gex_puts}   (<=0)
      net_gex   : suma total
      regime    : 'POS' | 'NEG'
      flip      : precio de gamma-cero (interpolado entre strikes; None si no hay)
      call_wall : strike de mayor gamma POSITIVA por encima del spot (resistencia/iman)
      put_wall  : strike de mayor |gamma NEGATIVA| por debajo del spot (soporte)
      abs_wall  : strike de mayor |gex| absoluto (muro dominante / POC gamma)
      oi_call_wall, oi_put_wall : muros por OI puro (lo clasico), por si se prefiere.
    """
    contracts = list(contracts)   # materializar (puede venir como generador)
    mult = spot if scale == "house" else spot * spot * 0.01
    profile, call_gex, put_gex, call_oi, put_oi = {}, {}, {}, {}, {}
    n_oi, n_gamma_ok, n_no_greeks = 0, 0, 0
    for c in contracts:
        K = float(c["strike"])
        oi = float(c.get("oi", 0) or 0)
        if oi <= 0:
            continue
        n_oi += 1
        right = c["right"].upper()[:1]
        # muros por OI PURO primero: no necesitan griegas, asi que siguen siendo validos en
        # un libro sin IV (NOK, o cualquier cadena despues del cierre). Antes se contaban
        # DESPUES del `continue` de gamma, asi que un libro sin griegas se quedaba tambien
        # sin muros de OI — una perdida de dato gratuita.
        if right == "C":
            call_oi[K] = call_oi.get(K, 0.0) + oi
        else:
            put_oi[K] = put_oi.get(K, 0.0) + oi
        g = _gamma_of(c, spot)
        if g is None:
            n_no_greeks += 1      # feature #5: se CUENTA, no se rellena con iv=0.3
            continue
        n_gamma_ok += 1
        gx = g * oi * 100 * mult
        if right == "C":
            call_gex[K] = call_gex.get(K, 0.0) + gx
            profile[K] = profile.get(K, 0.0) + gx
        else:
            put_gex[K] = put_gex.get(K, 0.0) - gx
            profile[K] = profile.get(K, 0.0) - gx

    # net None (no 0.0) cuando NO hay ni un strike con griegas: "no se" != "vale cero".
    net = sum(profile.values()) if profile else None
    # recompute del flip solo si hay DISPERSION real de IV (skew): con IV plana de
    # respaldo (greeks no disponibles) el barrido es poco fiable -> usar estatico.
    ivs = {round(_iv_of(c), 4) for c in contracts if _iv_of(c) is not None}
    # de TODAS las raices del barrido se toma la MAS CERCANA al spot, no la primera del grid.
    # `flip_recompute` barre desde 0.85·spot hacia arriba, asi que la "primera" era la raiz mas
    # BAJA del rango (-12% del spot en la cadena completa de QQQ): un nivel real pero
    # irrelevante, y publicarlo como "el flip" invertia el regimen del dia entero.
    roots_rc = flip_recompute(contracts, spot, all_roots=True) if len(ivs) >= 3 else []
    flip_rc = roots_rc[0] if roots_rc else None
    flip_static = _flip(profile)
    out = {
        "profile": profile, "call_gex": call_gex, "put_gex": put_gex,
        "net_gex": net, "regime": None if net is None else ("POS" if net >= 0 else "NEG"),
        "flip": flip_rc if flip_rc is not None else flip_static,
        "flip_static": flip_static, "flip_recompute": flip_rc,
        "spot": spot, "scale": scale,
    }
    # ---- agregados de CALIDAD DE LIBRO (feature #3 book-quality). Se calculan aqui porque
    # aqui esta el perfil; scripts/book_quality.py los consume y les pone percentil/etiqueta.
    gross = sum(abs(v) for v in profile.values()) if profile else None
    out["gross_gex"] = gross
    out["n_strikes_populated"] = len(profile)
    # ANCHO REAL de strikes con gamma (no la banda PEDIDA): el cache TWS pide ±15% pero su cap de
    # 20 strikes lo recorta a ±1,4% en QQQ, y sobre esa ventana estrecha el flip es el borde y el
    # regimen sale al reves (NVDA/TSLA/AMD/INTC NEG cuando el libro ancho dice POS, medido en RTH
    # 2026-07-27). Este es el numero que decide si una fuente SIRVE PARA EL MAPA (>= BAND_FLOOR).
    out["strike_span_pct"] = (((max(profile) - min(profile)) / 2 / spot)
                              if (profile and spot) else None)
    out["bifurcation"] = (gross / abs(net)) if (gross and net not in (None, 0)) else None
    out["hhi"] = (sum((abs(v) / gross) ** 2 for v in profile.values())
                  if gross else None)
    # contadores del PERFIL (solo contratos con OI>0, que son los que pueden entrar en el GEX).
    # from_ibkr_cache publica ademas `greeks_ok_pct` sobre TODOS los candidatos de la banda:
    # son dos denominadores distintos y llevan nombres distintos a proposito.
    out["n_contracts_oi"] = n_oi
    out["n_oi_gamma_ok"] = n_gamma_ok
    out["n_oi_no_greeks"] = n_no_greeks
    out["greeks_ok_pct_oi"] = (n_gamma_ok / n_oi) if n_oi else None
    # TODAS las raices del flip (feature #6), no solo la primera: la 2a raiz DEBAJO del spot
    # es la trampilla, y hasta hoy se tiraba.
    out["roots"] = roots_rc if roots_rc else _flip_roots(profile, spot)
    # muros por GAMMA (no solo OI): call wall = mayor gamma+ sobre spot,
    # put wall = mayor |gamma-| bajo spot. abs = mayor |gex| absoluto global.
    cw = [(k, v) for k, v in call_gex.items() if k >= spot]
    pw = [(k, v) for k, v in put_gex.items() if k <= spot]
    out["call_wall"] = max(cw, key=lambda x: x[1])[0] if cw else None
    out["put_wall"] = min(pw, key=lambda x: x[1])[0] if pw else None
    out["abs_wall"] = max(profile.items(), key=lambda x: abs(x[1]))[0] if profile else None
    # PIN vs TRAMPILLA por muro (fix 2026-07-25). Antes se tomaba solo el strike con
    # max(...)[0] y todo lo demas del muro se tiraba, asi que un nivel que AGUANTA y uno que
    # el precio ATRAVIESA acelerando eran el mismo dato para todos los consumidores. La
    # brujula necesita distinguirlos: fadear contra una trampilla es el error que la doctrina
    # prohibe explicitamente (memoria negative-gamma-whipsaw).
    #
    # El discriminador NO es el signo crudo del perfil en el strike: con la convencion naive
    # (calls +, puts -) un put wall tiene gamma neta negativa POR CONSTRUCCION, asi que
    # "signo<0 = trampilla" etiquetaria TODO put wall como trampilla y el veto se disparia
    # siempre. El discriminador correcto es el REGIMEN acumulado en ese nivel — de que lado
    # del gamma-flip cae: POS = dealers amortiguan (el nivel aguanta, pin) / NEG = dealers
    # amplifican (el precio lo atraviesa, trampilla).
    _flip_lvl = out.get("flip")
    for _key in ("call_wall", "put_wall", "abs_wall"):
        _k = out.get(_key)
        _v = profile.get(_k) if _k is not None else None
        out[_key + "_net"] = _v                      # gamma NETA en el strike (fuerza del muro)
        if _k is None or _flip_lvl is None:
            out[_key + "_regime"] = None
            out[_key + "_kind"] = None
        else:
            _reg = "POS" if _k >= _flip_lvl else "NEG"
            out[_key + "_regime"] = _reg
            out[_key + "_kind"] = "pin" if _reg == "POS" else "trampilla"
    # muros clasicos por OI (resistencia calls arriba, soporte puts abajo)
    co = [(k, v) for k, v in call_oi.items() if k >= spot]
    po = [(k, v) for k, v in put_oi.items() if k <= spot]
    out["oi_call_wall"] = max(co, key=lambda x: x[1])[0] if co else None
    out["oi_put_wall"] = max(po, key=lambda x: x[1])[0] if po else None
    return out


# -------------------------------------------------- COHERENCIA DE PARIDAD (gamma C == gamma P)
PARITY_TOL = 0.05          # 5% = la resolucion practica de una gamma servida a 4 decimales


def parity_pairs(contracts):
    """{(exp, strike): {'C': (gamma, oi), 'P': (gamma, oi)}} con solo gamma MEDIDA > 0."""
    m = {}
    for c in contracts:
        g = c.get("gamma")
        oi = c.get("oi")
        try:
            g, oi = (None if g is None else float(g)), float(oi or 0)
        except (TypeError, ValueError):
            continue
        if not g or g <= 0 or oi <= 0:
            continue
        m.setdefault((str(c.get("exp")), float(c["strike"])), {})[
            str(c.get("right", "C")).upper()[:1]] = (g, oi)
    return m


def parity_audit(contracts, spot, tol=PARITY_TOL):
    """La gamma de una call y la de una put del MISMO (strike, vencimiento) son IGUALES por
    paridad put-call: es una identidad, no una convencion. Este audit la mide y devuelve las
    DOS lecturas legales del neto ($/1%), o None si el libro no tiene ni un par.

    Por que existe (medido 2026-07-27 08:30, premercado): la cadena Polygon de SPY cumplia la
    paridad en el **2%** de sus 927 pares (mediana gamma_C/gamma_P = 0,243: una call con 4x
    MENOS gamma que su put al mismo strike es imposible), y con eso `gex_snapshot` publicaba
    SPY **net +2,29 B / regimen POSITIVE**. Las dos lecturas reparadas dan -6,84 y -4,36 B y
    CBOE -10,0 B: el signo crudo era el UNICO positivo. CBOE cumple la paridad en el 72-78%
    de sus pares, y en los libros coherentes (Polygon al cierre, CBOE) reparar no mueve el
    neto ni un 3% -> el arreglo es inocuo donde el dato esta bien y salva el signo donde no.
    POS vs NEG es el interruptor de doctrina: POS licencia el fade, NEG lo PROHIBE.
    """
    m = parity_pairs(contracts)
    both = [v for v in m.values() if "C" in v and "P" in v]
    if not both:
        return None
    ok = sum(1 for v in both if abs(v["C"][0] / v["P"][0] - 1.0) <= tol)
    mult = spot * spot * 0.01

    def read(src):
        """(neto, calls, puts) forzando la gamma del par al valor de la pata `src`."""
        cc = pp = 0.0
        for v in m.values():
            g_src = v[src][0] if src in v else None
            for right in ("C", "P"):
                if right not in v:
                    continue
                g = g_src if g_src is not None else v[right][0]
                x = g * v[right][1] * 100 * mult
                if right == "C":
                    cc += x
                else:
                    pp += x
        return cc - pp, cc, pp

    (lo_c, cc_c, pp_c), (lo_p, cc_p, pp_p) = read("C"), read("P")
    lo, hi = min(lo_c, lo_p), max(lo_c, lo_p)
    # CERO NO ES UN SIGNO: `(lo>0)==(hi>0)` daba firme=True y regimen NEG con lo==hi==0 (pasa
    # con OI simetrico, donde reparar la paridad anula el neto exactamente). El signo es firme
    # solo si las dos lecturas caen del MISMO lado y ninguna es cero.
    firm = (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
    return {
        "n_pares": len(both), "n_pares_ok": ok, "parity_ok_pct": round(ok / len(both), 4),
        "net_from_calls": lo_c, "net_from_puts": lo_p,
        "net_parity_lo": lo, "net_parity_hi": hi,
        "call_gex_parity": 0.5 * (cc_c + cc_p), "put_gex_parity": 0.5 * (pp_c + pp_p),
        "signo_firme": firm,
        # el menor en valor absoluto de las dos lecturas legales: no se sobreestima la
        # exposicion, y va etiquetado para que nadie lo confunda con una medicion unica.
        "net_parity_conservador": (min((lo, hi), key=abs) if firm else None),
        "regime_parity": (None if not firm else ("POS" if lo > 0 else "NEG")),
        "tol": tol,
        "convention": ("gamma_call == gamma_put al mismo (strike,exp) es identidad de paridad; "
                       "las dos lecturas fuerzan el par al valor de una pata u otra"),
    }


def regime_by_parity(contracts, spot, regime_raw, tol=PARITY_TOL):
    """(regime, why, audit). UNA sola definicion de "quien fija el signo" para los DOS caminos
    (gex_snapshot en lote y from_ibkr_cache en vivo) — duplicarla es el bug (CLAUDE.md #7).

    El 2026-07-27 09:00 estaban peleadas: `gex_snapshot` publicaba QQQ NEGATIVE (ya con el
    guardian de paridad) y `chart_levels.gen('qqq')` POS (signo crudo de la MISMA cadena
    Polygon), y el regimen es VETO DURO. Dos fuentes, dos regimenes, una de las dos miente."""
    par = parity_audit(contracts, spot, tol)
    if par is None:
        return regime_raw, None, None
    if par["regime_parity"] is None:
        return None, (f"signo NO determinado: las dos lecturas de paridad discrepan "
                      f"({par['net_parity_lo']/1e9:+.2f} vs {par['net_parity_hi']/1e9:+.2f} "
                      f"B $/1%)"), par
    why = None
    if par["regime_parity"] != regime_raw:
        why = (f"signo crudo {regime_raw} CONTRADICHO por la paridad put-call "
               f"(pares coherentes {par['parity_ok_pct']*100:.0f}%; lecturas legales "
               f"{par['net_parity_lo']/1e9:+.2f}..{par['net_parity_hi']/1e9:+.2f} B $/1%)")
    return par["regime_parity"], why, par


# ------------------------------------------------------------------ DEX (delta exposure)
DEX_SIGN_FIELDS = ("dex_sentiment", "dex_flow_impact")
DEX_CONVENTION = ("OI-larga (delta CRUDO del contrato: calls +, puts -), la misma que "
                  "publica Unusual Whales. NO es la dealer-long-calls del GEX.")


def check_dex_signs(d):
    """Devuelve `d` o levanta: PROHIBIDO publicar DEX con UN SOLO campo de signo
    (designs-menthorq.md:224). DEX positivo = cliente alcista Y creador comprando subyacente
    para quedar neutral: son dos hechos opuestos en el mismo numero, asi que quien lea un
    unico campo lee el contrario la mitad de las veces. Los dos, o ninguno."""
    falta = [k for k in DEX_SIGN_FIELDS if d.get(k) is None]
    if falta and len(falta) < len(DEX_SIGN_FIELDS):
        raise ValueError("DEX con un solo campo de signo: falta " + ", ".join(falta))
    return d


def build_dex(contracts, spot, scale="house"):
    """Perfil DEX por strike: DEX_k = Δ_k · OI_k · 100 · S  (`scale='shares'` quita el ·S y
    deja acciones equivalentes, que es lo comparable con el ADV).

    Contratos sin delta medido ni IV para reconstruirlo se EXCLUYEN y se CUENTAN; con cero
    strikes usables `net_dex` es None, no 0.0.
    """
    mult = 1.0 if scale == "shares" else spot
    profile, call_dex, put_dex, by_exp = {}, {}, {}, {}
    n_oi = n_ok = n_no = 0
    for c in contracts:
        K = float(c["strike"])
        oi = float(c.get("oi", 0) or 0)
        if oi <= 0:
            continue
        n_oi += 1
        dl = _delta_of(c, spot)
        if dl is None:
            n_no += 1
            continue
        n_ok += 1
        side = "call" if str(c["right"]).upper()[:1] == "C" else "put"
        dx = dl * oi * 100 * mult
        profile[K] = profile.get(K, 0.0) + dx
        tgt = call_dex if side == "call" else put_dex
        tgt[K] = tgt.get(K, 0.0) + dx
        e = by_exp.setdefault(str(c.get("exp")), {"net": 0.0, "gross": 0.0, "call": 0.0, "put": 0.0})
        e["net"] += dx
        e["gross"] += abs(dx)
        e[side] += dx
    net = sum(profile.values()) if profile else None
    gross = sum(abs(v) for v in profile.values()) if profile else None
    net_sh = None if net is None else net / (1.0 if scale == "shares" else spot)
    out = {
        "dex_profile": profile, "call_dex": call_dex, "put_dex": put_dex,
        "net_dex": net, "gross_dex": gross,
        # acciones equivalentes: el cliente esta largo net_sh delta, asi que el creador esta
        # CORTO ese delta y para quedar neutral tiene +net_sh acciones compradas.
        "net_dex_shares": net_sh,
        "dex_sentiment": None if not net else ("alcista" if net > 0 else "bajista"),
        "dex_flow_impact": None if not net else ("mm_compra" if net > 0 else "mm_vende"),
        "dex_convention": DEX_CONVENTION,
        "abs_dex_wall": max(profile.items(), key=lambda x: abs(x[1]))[0] if profile else None,
        "dex_by_exp": by_exp,
        "n_contracts_oi": n_oi, "n_oi_delta_ok": n_ok, "n_oi_no_delta": n_no,
        "delta_ok_pct_oi": (n_ok / n_oi) if n_oi else None,
        "spot": spot, "dex_scale": scale,
    }
    return check_dex_signs(out)


def _dex_fields(contracts, spot, scale="house"):
    """Campos DEX listos para fusionar en la salida gamma, sin las claves homonimas de
    `build_gex` (`n_contracts_oi`, `spot`), que llevan otro denominador."""
    dx = build_dex(contracts, spot, scale=scale)
    return {k: v for k, v in dx.items() if k not in ("n_contracts_oi", "spot")}


def _flip(profile):
    """Precio de gamma-cero: donde el GEX ACUMULADO (de abajo hacia arriba) cruza 0,
    interpolado linealmente entre los dos strikes que lo encierran. Mas fino que
    'el primer strike que cruza'. **None** si el perfil nunca cambia de signo: un libro de
    un solo signo no tiene flip, y el extremo del recorte no es un nivel de mercado."""
    if not profile:
        return None
    ks = sorted(profile)
    cum = 0.0
    prev_k = None
    prev_cum = 0.0
    for k in ks:
        prev_cum = cum
        cum += profile[k]
        if prev_k is not None and ((prev_cum < 0 <= cum) or (prev_cum > 0 >= cum)):
            # interpolar entre prev_k (prev_cum) y k (cum)
            span = cum - prev_cum
            if abs(span) < 1e-12:
                return k
            frac = -prev_cum / span
            return prev_k + frac * (k - prev_k)
        prev_k = k
    # SIN CRUCE = SIN FLIP -> None. Antes se devolvia el EXTREMO del rango de strikes, que lo
    # fija la banda del fichero, no el mercado: medido el 2026-07-27 en el camino vivo, EWY
    # publicaba flip 260,0 con spot 163,49 (a 0,97 pp del borde de la banda 0,6) y SNDK 2300,0
    # con spot 1440,88 (0,38 pp) -> los tres muros etiquetados "trampilla", que es VETO DURO.
    # gex_snapshot.honest_flip ya lo hacia bien por su cuenta; aqui estaba el original.
    return None


def _flip_roots(profile, spot=None):
    """TODAS las raices del GEX acumulado, no solo la primera (feature #6 flip-honesty).

    `_flip` devuelve UNA raiz y se queda tan ancho: cuando hay una segunda raiz DEBAJO del
    spot, esa es la TRAMPILLA (los dealers amplifican por debajo) y hasta hoy se tiraba,
    asi que el veto de 0DTE comprado no podia verla. Ordenadas por |K - spot| si se da spot
    (la mas relevante primero), si no por precio. Lista VACIA si el perfil nunca cruza."""
    if not profile:
        return []
    ks = sorted(profile)
    roots, cum, prev_k = [], 0.0, None
    for k in ks:
        prev_cum = cum
        cum += profile[k]
        if prev_k is not None and ((prev_cum < 0 <= cum) or (prev_cum > 0 >= cum)):
            span = cum - prev_cum
            roots.append(k if abs(span) < 1e-12 else prev_k + (-prev_cum / span) * (k - prev_k))
        prev_k = k
    if spot:
        roots.sort(key=lambda r: abs(r - spot))
    return roots


def trapdoor_root(roots, spot, em=None):
    """La raiz mas cercana DEBAJO del spot dentro de 1x `em` (feature #6, paso 4).
    None si no hay ninguna, o si no se conoce `em` (sin expected move no hay escala:
    "cerca" no significa nada y no se inventa un umbral)."""
    if not roots or not spot or not em or em <= 0:
        return None
    below = [r for r in roots if r < spot and (spot - r) <= em]
    return max(below) if below else None


def _gex_at(contracts, S, r=R_FREE):
    """GEX neto ($/1%) a un spot hipotetico S, re-gammando cada contrato a ESE spot.
    Contratos sin IV medida se EXCLUYEN (antes entraban con iv=0.3 fabricada)."""
    tot, used = 0.0, 0
    for c in contracts:
        oi = float(c.get("oi", 0) or 0)
        if oi <= 0:
            continue
        iv = _iv_of(c)
        if iv is None:
            continue
        T = _T_from(c)
        if T is None:
            continue          # sin plazo no se reprecia: es el flip lo que sale de aqui
        g = bs_gamma(S, float(c["strike"]), T, iv, r)
        if g <= 0:
            continue
        used += 1
        tot += (1.0 if c["right"].upper()[:1] == "C" else -1.0) * g * oi * 100 * S * S * 0.01
    return (tot, used)


def flip_recompute(contracts, spot, lo=0.85, hi=1.15, steps=120, all_roots=False,
                   tol_frac=1e-4):
    """Gamma-flip CORRECTO (SqueezeMetrics/Perfiliev): recomputa la gamma BS a cada
    spot hipotetico S del grid (la gamma DEPENDE de S), arma GEX(S) = sum ±gamma(S)·
    OI·100·S^2·0.01, y halla la raiz por interpolacion lineal en el cambio de signo.
    Mas fiel que interpolar el perfil estatico (_flip), a costa de recomputar griegas.
    Requiere iv+T por contrato (usa BS gamma, ignora la gamma del snapshot que es a
    spot actual). Devuelve el precio de gamma-cero o None.

    all_roots=True -> lista con TODAS las raices (feature #6), cada cruce REFINADO por
    biseccion a `tol_frac`·spot (1e-4 por defecto) en vez de interpolado a pelo. La firma
    de una sola raiz se conserva intacta: los consumidores viejos no notan nada."""
    contracts = [c for c in contracts if _iv_of(c) is not None]   # sin IV medida no se barre
    if not contracts:
        return [] if all_roots else None
    # el barrido no sale del libro: fuera de los strikes el cruce de signo es artefacto
    ks = [float(c["strike"]) for c in contracts if c.get("strike") is not None]
    k_lo, k_hi = (min(ks), max(ks)) if ks else (spot * lo, spot * hi)
    g_lo, g_hi = max(spot * lo, k_lo), min(spot * hi, k_hi)
    if g_hi <= g_lo:                       # libro degenerado: no se inventa un rango
        return [] if all_roots else None
    grid = [g_lo + (g_hi - g_lo) * i / (steps - 1) for i in range(steps)]
    tol = max(spot * tol_frac, 1e-9)
    roots = []
    prev_S = prev_g = None
    for S in grid:
        tot = _gex_at(contracts, S)[0]
        if prev_g is not None and ((prev_g < 0 <= tot) or (prev_g > 0 >= tot)):
            a, ga, b = prev_S, prev_g, S
            # biseccion: el GEX(S) no es lineal en S, asi que interpolar el intervalo del
            # grid (~0.25% del spot con steps=120) deja el flip desplazado varios centavos.
            for _ in range(40):
                if b - a <= tol:
                    break
                m = 0.5 * (a + b)
                gm = _gex_at(contracts, m)[0]
                if (ga < 0 <= gm) or (ga > 0 >= gm):
                    b = m
                else:
                    a, ga = m, gm
            roots.append(0.5 * (a + b))
            if not all_roots:
                return roots[0]
        prev_S, prev_g = S, tot
    if all_roots:
        roots.sort(key=lambda x: abs(x - spot))
        return roots
    return None


def regime_at(gexinfo, price):
    """Regimen local visto desde `price`: por encima del flip = POS (amortigua),
    por debajo = NEG (amplifica). Devuelve ('POS'|'NEG', distancia_%_al_flip)."""
    flip = gexinfo.get("flip")
    if flip is None or price <= 0:
        return gexinfo["regime"], None
    d = (price - flip) / price * 100
    return ("POS" if price >= flip else "NEG"), d


def wall_context(gexinfo, price):
    """Para gates de engine: distancia del precio a los muros (en %), y si un muro
    esta INMEDIATO (<=0.4%) — el toque de muro rebota ~70% la 1a vez (doctrina casa
    oi-magnets-protocol). Devuelve dict con call_wall/put_wall/flip + flags near_*."""
    def dpct(level):
        return None if not level or price <= 0 else (level - price) / price * 100
    cw, pw, flip = gexinfo.get("call_wall"), gexinfo.get("put_wall"), gexinfo.get("flip")
    dc, dp, df = dpct(cw), dpct(pw), dpct(flip)
    NEAR = 0.4
    out = {
        "call_wall": cw, "put_wall": pw, "flip": flip, "abs_wall": gexinfo.get("abs_wall"),
        "d_call_wall": dc, "d_put_wall": dp, "d_flip": df,
        "near_call_wall": dc is not None and abs(dc) <= NEAR,
        "near_put_wall": dp is not None and abs(dp) <= NEAR,
        "near_flip": df is not None and abs(df) <= NEAR,
        "regime": regime_at(gexinfo, price)[0],
    }
    # pin vs trampilla por muro — lo consume la brujula para VETAR el fade
    for _key in ("call_wall", "put_wall", "abs_wall"):
        for _suf in ("_net", "_regime", "_kind"):
            out[_key + _suf] = gexinfo.get(_key + _suf)
    return out


PIN_T_FLOOR = 1 / (252 * 24)   # 1 hora en años: piso para 1/T, sin esto T->0 al cierre da infinito


def pin_risk_score(gexinfo, contracts, spot):
    """concentracion(|gamma|) x proximidad(spot,POC) x 1/T (protocolo oi-magnets-protocol).
    DESCRIPTIVO, no probabilidad: convencion declarada, no calibrada con historico (como
    VPVR). None si falta HHI, POC o ningun contrato trae T -- nunca un score fabricado."""
    hhi = gexinfo.get("hhi")
    poc = gexinfo.get("abs_wall")
    if hhi is None or poc is None or not spot or spot <= 0:
        return None
    Ts = [float(c["T"]) for c in contracts if c.get("T") and float(c["T"]) > 0]
    if not Ts:
        return None
    t_min = max(min(Ts), PIN_T_FLOOR)
    proximity = max(0.0, 1 - abs(poc - spot) / spot)
    call_wall = gexinfo.get("call_wall")
    return {
        "score": hhi * proximity / t_min,
        "hhi": hhi, "proximity_to_poc": proximity, "t_min_years": t_min,
        "poc": poc, "call_wall": call_wall,
        "fortress_pin": call_wall is not None and poc == call_wall,
        "convention": "score = hhi * proximidad_al_POC / T_min(anos, piso 1h); "
                      "no es probabilidad, es un ranking descriptivo",
    }


def flip_migration_trail(points):
    """points: iterable de (ts, flip) del flip archivado cada 5min (levels_5m.jsonl).
    Polilinea + forma (horizontal/inclinada/dentada) para juzgar si el regimen del dia es
    fiable o es ruido de banda. Umbrales CONVENCION, no medidos con historico (como VPVR
    confluence): declarados en el propio dato. <3 puntos validos -> insuficiente, sin forma."""
    pts = sorted((float(t), float(f)) for t, f in points if f is not None)
    n = len(pts)
    if n < 3:
        return {"n": n, "trail": pts, "shape": None, "status": "insuficiente_datos"}
    flips = [f for _, f in pts]
    first, last, mean = flips[0], flips[-1], sum(flips) / n
    span = max(flips) - min(flips)
    drift_pct = (last - first) / first * 100 if first else None
    range_pct = (span / mean * 100) if mean else None
    deltas = [b - a for a, b in zip(flips, flips[1:])]
    signs = [1 if d > 0 else (-1 if d < 0 else 0) for d in deltas if d != 0]
    reversals = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    reversal_rate = reversals / max(1, len(signs) - 1) if len(signs) >= 2 else 0.0
    HORIZ_RANGE_PCT, DENTADA_REVERSAL_RATE = 0.15, 0.5     # convencion, no medida
    if range_pct is not None and range_pct <= HORIZ_RANGE_PCT:
        shape = "horizontal"
    elif reversal_rate > DENTADA_REVERSAL_RATE:
        shape = "dentada"
    else:
        shape = "inclinada"
    return {
        "n": n, "trail": pts, "first": first, "last": last, "range_pct": range_pct,
        "drift_pct": drift_pct, "reversals": reversals, "reversal_rate": round(reversal_rate, 3),
        "shape": shape, "status": "ok",
        "convention": f"horizontal<={HORIZ_RANGE_PCT}% rango, dentada>{DENTADA_REVERSAL_RATE} "
                      "tasa de reversion -- umbrales convencion, no medidos",
    }


# ------------------------------ adaptadores de datos -------------------------
def _T_of(exp, now=None):
    """Años al 16:00 ET del vencimiento YYYYMMDD (piso 1e-5). `now` (epoch) permite
    replay/tests deterministas sin parchear el reloj del proceso.

    Devuelve **None** si el vencimiento es ilegible. Antes devolvia 0.02 (7,3 dias):
    el patron "cero plausible" prohibido en ~/CLAUDE.md — convertia "no se cuando
    vence" en "vence en una semana", y como T entra en bs_gamma, eso desplazaba el
    flip; y del flip sale pin-vs-trampilla, que es VETO DURO sobre 0DTE comprado.
    """
    import time as _t
    try:
        ref = _t.time() if now is None else float(now)
        return max((_t.mktime(_t.strptime(exp, "%Y%m%d")) + 16 * 3600 - ref) / (365 * 86400), 1e-5)
    except Exception:
        return None


def _now_parts(now=None):
    """(epoch, 'YYYYMMDD' local, minutos_del_dia). Respeta el reloj congelado del proceso
    (chart_levels parchea time.time/time.strftime para el replay con IBT_ASOF)."""
    import time as _t
    ts = _t.time() if now is None else float(now)
    lt = _t.localtime(ts)
    return ts, _t.strftime("%Y%m%d", lt), lt.tm_hour * 60 + lt.tm_min


def exp_status(exp, now=None):
    """'vivo' | 'vencido_hoy' | 'expirado'  — feature #13 next-day-map roll-off.

    EL BUG QUE ARREGLA (determinado, 2026-07-25): el unico filtro era `exp >= hoy`, asi que
    un contrato que vencia HOY seguia contando desde las 16:00 hasta las 23:59 y a las
    00:00:00 desaparecia de golpe. Los muros y el flip de la flota SALTABAN a medianoche
    (el conteo de fleet_consensus paso de 10↑/16↓ a 5↑/21↓ exactamente a las 00:00 y disparo
    MANADA a las 00:00:45). El vencimiento tiene que rodar EN EL CIERRE, que es cuando el
    contrato deja de existir, no cuando cambia la fecha del reloj."""
    _, today, hm = _now_parts(now)
    e = str(exp)
    if e < today:
        return "expirado"
    if e == today:
        return "vivo" if hm < ROLL_HOUR_ET * 60 else "vencido_hoy"
    return "vivo"


def in_rth(now=None):
    """True dentro de 9:30-16:00 ET en dia de semana. Fuera de ahi IBKR escribe bid/ask=-1
    y un mid de -1 seria una mentira MAS convincente que el bug que reemplaza -> no se
    invierte IV (spec #5 paso 3)."""
    import time as _t
    ts, _, hm = _now_parts(now)
    return _t.localtime(ts).tm_wday < 5 and RTH_LO <= hm <= RTH_HI


def parse_chain_header(path):
    """Metadatos de la cabecera de data/opt_chain_<sym>.txt (append-only, ver
    docs/CHAIN-HEADER.md). Devuelve dict con lo que HAYA; los ausentes van a None —
    jamas a un valor plausible."""
    out = {"epoch": None, "spot": None, "exps": [], "fuente": None,
           "band": None, "max_strikes": None, "narrow": None, "greeks_ok_pct": None}
    try:
        with open(path) as f:
            for _ in range(4):
                ln = f.readline()
                if not ln or not ln.startswith("#"):
                    break
                p = ln.split()
                for key, cast in (("epoch", float), ("spot", float), ("band", float),
                                  ("max_strikes", int), ("narrow", int),
                                  ("greeks_ok_pct", float)):
                    if key in p:
                        try:
                            out[key] = cast(p[p.index(key) + 1])
                        except (ValueError, IndexError):
                            pass
                if "fuente" in p:
                    try:
                        out["fuente"] = p[p.index("fuente") + 1]
                    except IndexError:
                        pass
                if "exps" in p:
                    i = p.index("exps") + 1
                    out["exps"] = [x for x in p[i:] if x.isdigit() and len(x) == 8]
    except OSError:
        return out
    return out


def invert_chain_iv(rows, spot, now=None, r=R_FREE):
    """Inversion de IV por biseccion sobre el MID, con forward implicito por paridad
    put-call (feature #5 paso 2/3). `rows`: iterable de dicts con strike/right/exp/bid/ask/T.

    Devuelve (mapa {(exp,strike,right): iv}, stats). SOLO invierte si `bid>0 y ask>0 y RTH`:
    a las 16:16 IBKR escribe -1.00 en ambos lados y una biseccion sobre ESE mid publicaria
    una IV con toda la pinta de medida. Si no se puede invertir, el contrato NO recibe IV
    (queda fuera del perfil y se cuenta), nunca un 0.3 de relleno."""
    stats = {"intentos": 0, "ok": 0, "sin_mid": 0, "no_invertible": 0,
             "fuera_rth": 0, "forward_paridad": 0}
    if not in_rth(now):
        stats["fuera_rth"] = sum(1 for _ in rows) if isinstance(rows, list) else 0
        return {}, stats
    mids = {}
    for c in rows:
        try:
            bid, ask = float(c.get("bid", -1)), float(c.get("ask", -1))
        except (TypeError, ValueError):
            continue
        if bid <= 0 or ask <= 0 or ask < bid:
            continue
        mids[(str(c["exp"]), float(c["strike"]), str(c["right"]).upper()[:1])] = 0.5 * (bid + ask)
    out = {}
    for c in rows:
        key = (str(c["exp"]), float(c["strike"]), str(c["right"]).upper()[:1])
        mid = mids.get(key)
        if mid is None:
            stats["sin_mid"] += 1
            continue
        stats["intentos"] += 1
        K, T = key[1], float(c.get("T") or 0.0)
        # forward por paridad si existe el par C/P del mismo strike+expiry; si no, spot.
        cm = mids.get((key[0], K, "C"))
        pm = mids.get((key[0], K, "P"))
        S_eff = spot
        F = forward_from_parity(cm, pm, K, T, r)
        if F is not None and F > 0:
            S_eff = F * math.exp(-r * T)
            stats["forward_paridad"] += 1
        iv = implied_vol(mid, S_eff, K, T, key[2], r)
        if iv is None:
            stats["no_invertible"] += 1
            continue
        stats["ok"] += 1
        out[key] = iv
    return out, stats


def _health_shell(spot, scale, hdr, health):
    """Esqueleto con TODAS las claves de la salida normal a None/vacio + la cabecera de
    salud. La degradacion honesta CONSERVA el contrato: los consumidores comprueban
    `flip`/`gamma_ok`, no la ausencia de una clave (y todos ya hacen `if not lv.get('flip')`)."""
    out = {
        "profile": {}, "call_gex": {}, "put_gex": {},
        "net_gex": None, "regime": None, "flip": None,
        "flip_static": None, "flip_recompute": None, "flip_src": "none",
        "roots": [], "trapdoor_root": None,
        "spot": spot, "scale": scale,
        "gross_gex": None, "n_strikes_populated": 0, "strike_span_pct": None,
        "bifurcation": None, "hhi": None,
        "n_contracts_oi": 0, "n_oi_gamma_ok": 0, "n_oi_no_greeks": 0,
        "greeks_ok_pct_oi": None, "n_gamma_ok": 0, "n_no_greeks": 0, "greeks_ok_pct": None,
        "call_wall": None, "put_wall": None, "abs_wall": None,
        "oi_call_wall": None, "oi_put_wall": None,
        "iv_atm": None, "em": None,
        "vex_profile": {}, "net_vex": None, "vex_peak": None,
        "dex_profile": {}, "call_dex": {}, "put_dex": {},
        "net_dex": None, "gross_dex": None, "net_dex_shares": None,
        "dex_sentiment": None, "dex_flow_impact": None, "dex_convention": DEX_CONVENTION,
        "abs_dex_wall": None, "dex_by_exp": {}, "n_oi_delta_ok": 0, "n_oi_no_delta": 0,
        "delta_ok_pct_oi": None,
        "exp": None, "dte": None, "scope": None,
    }
    for k in ("call_wall", "put_wall", "abs_wall"):
        out[k + "_net"] = None
        out[k + "_regime"] = None
        out[k + "_kind"] = None
    out.update(health)
    out["chain_hdr"] = hdr
    return out


def from_ibkr_cache(path, spot, band=None, scale="house", all_exp=False, now=None):
    """Lee data/opt_chain_<sym>.txt. scale='dollar1pct' -> $/1% (estándar gexa).
    all_exp=False (default) -> 0DTE puro (vencimiento VIVO más cercano).
    all_exp=True -> TODA la cadena viva mezclada, cada contrato con su T (mapa multi-día).
    Añade el perfil VEX (vanna), la etiqueta de escala/scope y la CABECERA DE SALUD.

    HONESTIDAD (features #5/#6/#13, 2026-07-25):
      - iv<=0 y gamma<=0 -> se intenta invertir la IV del mid (solo con bid/ask>0 en RTH);
        si no se puede, el contrato se EXCLUYE y se CUENTA. Ya no existe el `iv=0.3`.
      - `greeks_ok_pct < MIN_GREEKS_OK` o cadena rancia -> gamma_ok=False y TODAS las claves
        gamma a None (los muros por OI puro SI sobreviven: no necesitan griegas).
      - un vencimiento que ya cerro (16:00 ET) NO cuenta: el roll es en el cierre, no a
        medianoche.
    `now` (epoch) hace la funcion determinista para tests/replay."""
    import os
    if not os.path.exists(path):
        return None
    hdr = parse_chain_header(path)
    # band=None -> la del fichero. El default fijo de 0.035 recortaba a +-3,5% cadenas
    # archivadas con banda adaptativa mucho mas ancha (QQQ: 48 strikes de 184).
    if band is None:
        band = hdr.get("band") or 0.035
    ts_now, today, _ = _now_parts(now)
    rows, exps = [], set()
    with open(path) as fh:
        for ln in fh:
            if ln.startswith("#"):
                continue
            f = ln.split()
            if len(f) < 10:
                continue
            try:
                k, right, exp = float(f[0]), f[1], f[2]
                bid, ask = float(f[3]), float(f[4])
                oi, iv, delta, gamma = float(f[6]), float(f[7]), float(f[8]), float(f[9])
            except ValueError:
                continue
            # el `-1.00` de delta es el centinela de "sin dato" de IBKR y es TAMBIEN un delta
            # de put legal: solo se distingue mirando la fila entera (a las 16:16 viene iv=-1
            # en todas). Por eso el filtro vive aqui y no en `_delta_of`.
            rows.append({"strike": k, "right": right, "exp": exp, "bid": bid, "ask": ask,
                         "oi": oi, "iv": iv if iv > 0 else None,
                         "delta": delta if (iv > 0 and 0 < abs(delta) <= 1) else None,
                         "gamma": gamma if gamma > 0 else None, "T": _T_of(exp, ts_now)})
            exps.add(exp)
    age = None if not hdr["epoch"] else max(ts_now - hdr["epoch"], 0.0)
    rth = in_rth(now)
    # RANCIA no es "vieja": es "mas vieja de lo que su fuente promete". El cache TWS se
    # reescribe cada 180 s dentro de su ventana, asi que >45 min EN RTH significa que el
    # daemon esta muerto -> mutear. FUERA de RTH no existe cadena mas fresca: el libro del
    # cierre anterior ES el libro correcto para el mapa nocturno/premarket (asi se computa la
    # gamma overnight en todas partes), y lo que se pierde ahi son las COTIZACIONES (bid/ask
    # a -1), no el OI. Eso se declara aparte en `quotes_ok`, y quien decide si hay voz gamma
    # es `greeks_ok_pct` — dato medible — no el reloj.
    stale = bool(age is None or (rth and age > STALE_S))
    health = {
        "chain_path": path, "chain_ts": hdr["epoch"], "chain_age_s": age,
        "chain_src": hdr["fuente"] or "ibkr_tws",
        "quotes_ok": rth, "session": "rth" if rth else "fuera_de_rth",
        "stale_reason": (None if not stale else
                         ("cabecera sin epoch" if age is None else
                          f"cache TWS de hace {age / 60:.0f} min en RTH (ciclo son 3 min)")),
        "stale": stale,
        "band_used": band, "band_fetch": hdr["band"],
        "exps_en_fichero": sorted(exps), "n_expiries": 0,
        "rows_total": len(rows), "n_candidates": 0,
        "n_iv_provider": 0, "n_iv_inverted": 0, "iv_source": "none",
        "exp_rolled": False, "roll_reason": None,
        "gamma_ok": False, "degraded_reason": None,
    }
    if not rows:
        health["degraded_reason"] = "cadena vacia"
        return _health_shell(spot, scale, hdr, health)

    # ---- vencimientos VIVOS (feature #13): el que vencio hoy muere en el cierre.
    status = {e: exp_status(e, now) for e in exps}
    live = sorted(e for e in exps if status[e] == "vivo")
    health["n_expiries"] = len(live)
    first_in_file = sorted(exps)[0]
    if not live:
        health["degraded_reason"] = (f"todos los vencimientos del fichero estan muertos "
                                    f"({', '.join(f'{e}:{status[e]}' for e in sorted(exps))})")
        health["exp_rolled"] = True
        health["roll_reason"] = "sin vencimiento vivo en la cadena"
        return _health_shell(spot, scale, hdr, health)
    exp0 = live[0]
    if exp0 != first_in_file:
        health["exp_rolled"] = True
        health["roll_reason"] = f"{first_in_file} {status[first_in_file]} -> mapa desde {exp0}"

    # ---- candidatos: en scope y en banda
    cands = [c for c in rows
             if (all_exp or c["exp"] == exp0) and status[c["exp"]] == "vivo"
             and spot * (1 - band) <= c["strike"] <= spot * (1 + band)]
    health["n_candidates"] = len(cands)
    if not cands:
        health["degraded_reason"] = f"0 contratos en ±{band * 100:.2f}% del vencimiento {exp0}"
        return _health_shell(spot, scale, hdr, health)

    # ---- IV: la medida manda; si falta, se INVIERTE del mid (solo RTH con bid/ask reales)
    health["n_iv_provider"] = sum(1 for c in cands if c["iv"] is not None)
    faltan = [c for c in cands if c["iv"] is None and c["gamma"] is None]
    if faltan:
        inv, inv_stats = invert_chain_iv(faltan, spot, now)
        for c in faltan:
            iv = inv.get((str(c["exp"]), float(c["strike"]), str(c["right"]).upper()[:1]))
            if iv is not None:
                c["iv_inv"] = iv
        health["n_iv_inverted"] = len(inv)
        health["iv_inv_stats"] = inv_stats
    health["iv_source"] = ("provider" if health["n_iv_provider"] and not health["n_iv_inverted"]
                           else "inverted" if health["n_iv_inverted"] and not health["n_iv_provider"]
                           else "mixed" if health["n_iv_provider"] and health["n_iv_inverted"]
                           else "none")
    usable = [c for c in cands if _gamma_of(c, spot) is not None]
    health["greeks_ok_pct"] = len(usable) / len(cands)

    if not usable or health["greeks_ok_pct"] < MIN_GREEKS_OK or health["stale"]:
        # DEGRADACION HONESTA. Antes esto no existia: se rellenaba iv=0.3 y se publicaban
        # muros/flip/regimen como si fueran medidos. Los muros por OI PURO si se publican
        # (el OI es dato real y no necesita griegas) — es lo unico que NOK/DRAM tienen.
        oi_only = build_gex([{**c, "gamma": None, "iv": None} for c in cands], spot, scale=scale)
        out = _health_shell(spot, scale, hdr, health)
        # el DEX SI se publica en degradado: solo necesita delta+OI, no gamma ni flip, y un
        # libro sin griegas de gamma puede tener delta perfectamente medido.
        out.update(_dex_fields(cands, spot))
        out["oi_call_wall"] = oi_only["oi_call_wall"]
        out["oi_put_wall"] = oi_only["oi_put_wall"]
        out["n_contracts_oi"] = oi_only["n_contracts_oi"]
        out["n_no_greeks"] = len(cands) - len(usable)
        out["n_gamma_ok"] = len(usable)
        out["exp"] = "ALL" if all_exp else exp0
        out["dte"] = None if all_exp else _dte_of(exp0, ts_now)
        out["scope"] = "ALL" if all_exp else "0DTE"
        out["degraded_reason"] = (
            f"cadena rancia: {health['stale_reason']}"
            if health["stale"] and health["greeks_ok_pct"] >= MIN_GREEKS_OK
            else f"griegas usables {health['greeks_ok_pct'] * 100:.0f}% "
                 f"(<{MIN_GREEKS_OK * 100:.0f}%) sobre {len(cands)} contratos")
        return out

    g = build_gex(usable, spot, scale=scale)
    # GUARDIAN DE PARIDAD tambien en el camino VIVO: sin esto `gex_snapshot` publicaba QQQ
    # NEGATIVE y `chart_levels.gen('qqq')` POS sobre la MISMA cadena Polygon, y el regimen es
    # VETO DURO. Una sola definicion del signo para los dos (regime_by_parity).
    _reg, _why, _par = regime_by_parity(usable, spot, g.get("regime"))
    g["regime_raw"] = g.get("regime")
    g["regime"] = _reg
    g["regime_why"] = _why
    g["parity_ok_pct"] = None if _par is None else _par["parity_ok_pct"]
    g["net_gex_parity_lo"] = None if _par is None else _par["net_parity_lo"]
    g["net_gex_parity_hi"] = None if _par is None else _par["net_parity_hi"]
    g.update(health)
    g["n_gamma_ok"] = len(usable)
    g["n_no_greeks"] = len(cands) - len(usable)
    g["gamma_ok"] = True
    g["chain_hdr"] = hdr
    # FLIP HONESTO (feature #6): el repreciado GANA cuando existe (recomputa la gamma a cada
    # spot hipotetico, que es la definicion correcta). Antes se sobreescribia SIEMPRE con el
    # estatico —pagabamos flip_recompute y lo tirabamos— sin decirlo en ninguna clave.
    if g.get("flip_recompute") is not None:
        g["flip"] = g["flip_recompute"]
        g["flip_src"] = "repriced"
        g["flip_why"] = "gamma recomputada a cada spot del barrido (definicion correcta)"
    elif g.get("flip_static") is not None:
        g["flip"] = g["flip_static"]
        g["flip_src"] = "static_no_iv"
        g["flip_why"] = ("menos de 3 IVs distintas en la banda: el barrido no es fiable, "
                         "se usa el perfil estatico -> peso del factor flip x0.5")
    else:
        g["flip"] = None
        g["flip_src"] = "none"
        g["flip_why"] = "sin cruce de signo en el perfil"
    g["exp"] = "ALL" if all_exp else exp0
    g["dte"] = None if all_exp else _dte_of(exp0, ts_now)
    g["scope"] = "ALL" if all_exp else "0DTE"
    # ATM IV + expected move (±1σ hasta el vencimiento) = spot·IV·√T. Sin IV medida en el ATM
    # no hay expected move: em=None (antes salia de un iv=0.3 inventado y se usaba de escala
    # para amplitudes y vetos).
    atmc = min(usable, key=lambda c: abs(c["strike"] - spot))
    iv_atm = _iv_of(atmc)
    T_atm = _T_from(atmc, ts_now)
    if T_atm is None:            # sin plazo no hay expected move: None, jamas un +-2% fingido
        em = None
    g["iv_atm"] = None if iv_atm is None else round(iv_atm, 4)
    g["em"] = None if iv_atm is None else round(spot * iv_atm * math.sqrt(T_atm), 2)
    # trampilla: la raiz mas cercana DEBAJO del spot dentro de 1x em (roots ya vienen de
    # build_gex, no se re-barre la rejilla: son 120 pasos x N contratos)
    g["trapdoor_root"] = trapdoor_root(g.get("roots") or [], spot, g["em"])
    # VEX (vanna exposure) en la misma escala
    vx = build_exposure(usable, spot, greek="vanna", scale=scale if scale != "house" else "dollar1pct")
    g["vex_profile"] = vx["profile"]
    g["net_vex"] = vx["net"]
    g["vex_peak"] = vx["peak"]
    g.update(_dex_fields(cands, spot))   # DEX sobre TODOS los candidatos: no depende de gamma
    return g


if __name__ == "__main__":
    # autotest sintetico ASIMETRICO: puts pesados abajo, calls arriba -> flip ~ mitad
    demo = []
    for k in range(90, 111):
        demo.append({"strike": k, "right": "C", "oi": max(0, k - 100) * 400, "gamma": 0.03, "iv": 0.3, "T": 0.02})
        demo.append({"strike": k, "right": "P", "oi": max(0, 100 - k) * 300, "gamma": 0.03, "iv": 0.3, "T": 0.02})
    g = build_gex(demo, 100.0)
    print(f"net_gex={g['net_gex']:.0f} regime={g['regime']} flip={g['flip']:.2f} "
          f"(static={g['flip_static']:.2f} recompute={g['flip_recompute']}) "
          f"call_wall={g['call_wall']} put_wall={g['put_wall']} abs_wall={g['abs_wall']}")
    wc = wall_context(g, 100.0)
    print(f"wall_context@100: regime={wc['regime']} d_flip={wc['d_flip']:.1f}% "
          f"d_call_wall={wc['d_call_wall']:.1f}% d_put_wall={wc['d_put_wall']:.1f}%")

def gamma_by_expiry(rows, spot, scale="house"):
    """Gamma total por días a expiry. rows=[{strike, right, oi, gamma, ...}].
    Devuelve {daysToExp: gamma_sum, ...} ordenado por proximidad a expiry."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).timestamp()
    by_exp = {}
    for r in rows:
        try:
            exp_str = str(r.get("exp", ""))
            if len(exp_str) != 8:  # YYYYMMDD
                continue
            from datetime import datetime as dt
            exp_ts = int(dt.strptime(exp_str, "%Y%m%d").replace(hour=16).timestamp())
            dte = max(0, int((exp_ts - now) / 86400))
            gamma = float(r.get("gamma", 0))
            oi = float(r.get("oi", 0))
            if dte not in by_exp:
                by_exp[dte] = 0.0
            by_exp[dte] += gamma * oi / 100.0
        except Exception:
            pass
    return by_exp
