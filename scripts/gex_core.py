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


def _gamma_of(c, spot):
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
    g = bs_gamma(spot, float(c["strike"]), float(c.get("T", 0.02)), iv)
    return g if g > 0 else None


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
        T = float(c.get("T", 0.02))
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


def _flip(profile):
    """Precio de gamma-cero: donde el GEX ACUMULADO (de abajo hacia arriba) cruza 0,
    interpolado linealmente entre los dos strikes que lo encierran. Mas fino que
    'el primer strike que cruza'. None si el perfil nunca cambia de signo."""
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
    # sin cruce: todo un signo. flip fuera del rango -> el extremo mas cercano a cero.
    return ks[-1] if cum < 0 else ks[0]


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
        g = bs_gamma(S, float(c["strike"]), float(c.get("T", 0.02)), iv, r)
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
    grid = [spot * (lo + (hi - lo) * i / (steps - 1)) for i in range(steps)]
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


# ------------------------------ adaptadores de datos -------------------------
def _T_of(exp, now=None):
    """Años al 16:00 ET del vencimiento YYYYMMDD (piso 1e-5). `now` (epoch) permite
    replay/tests deterministas sin parchear el reloj del proceso."""
    import time as _t
    try:
        ref = _t.time() if now is None else float(now)
        return max((_t.mktime(_t.strptime(exp, "%Y%m%d")) + 16 * 3600 - ref) / (365 * 86400), 1e-5)
    except Exception:
        return 0.02


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
        "gross_gex": None, "n_strikes_populated": 0, "bifurcation": None, "hhi": None,
        "n_contracts_oi": 0, "n_oi_gamma_ok": 0, "n_oi_no_greeks": 0,
        "greeks_ok_pct_oi": None, "n_gamma_ok": 0, "n_no_greeks": 0, "greeks_ok_pct": None,
        "call_wall": None, "put_wall": None, "abs_wall": None,
        "oi_call_wall": None, "oi_put_wall": None,
        "iv_atm": None, "em": None,
        "vex_profile": {}, "net_vex": None, "vex_peak": None,
        "exp": None, "dte": None, "scope": None,
    }
    for k in ("call_wall", "put_wall", "abs_wall"):
        out[k + "_net"] = None
        out[k + "_regime"] = None
        out[k + "_kind"] = None
    out.update(health)
    out["chain_hdr"] = hdr
    return out


def from_ibkr_cache(path, spot, band=0.035, scale="house", all_exp=False, now=None):
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
                oi, iv, gamma = float(f[6]), float(f[7]), float(f[9])
            except ValueError:
                continue
            rows.append({"strike": k, "right": right, "exp": exp, "bid": bid, "ask": ask,
                         "oi": oi, "iv": iv if iv > 0 else None,
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
        out["oi_call_wall"] = oi_only["oi_call_wall"]
        out["oi_put_wall"] = oi_only["oi_put_wall"]
        out["n_contracts_oi"] = oi_only["n_contracts_oi"]
        out["n_no_greeks"] = len(cands) - len(usable)
        out["n_gamma_ok"] = len(usable)
        out["exp"] = "ALL" if all_exp else exp0
        out["dte"] = None if all_exp else round(_T_of(exp0, ts_now) * 365, 2)
        out["scope"] = "ALL" if all_exp else "0DTE"
        out["degraded_reason"] = (
            f"cadena rancia: {health['stale_reason']}"
            if health["stale"] and health["greeks_ok_pct"] >= MIN_GREEKS_OK
            else f"griegas usables {health['greeks_ok_pct'] * 100:.0f}% "
                 f"(<{MIN_GREEKS_OK * 100:.0f}%) sobre {len(cands)} contratos")
        return out

    g = build_gex(usable, spot, scale=scale)
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
    g["dte"] = None if all_exp else round(_T_of(exp0, ts_now) * 365, 2)
    g["scope"] = "ALL" if all_exp else "0DTE"
    # ATM IV + expected move (±1σ hasta el vencimiento) = spot·IV·√T. Sin IV medida en el ATM
    # no hay expected move: em=None (antes salia de un iv=0.3 inventado y se usaba de escala
    # para amplitudes y vetos).
    atmc = min(usable, key=lambda c: abs(c["strike"] - spot))
    iv_atm = _iv_of(atmc)
    T_atm = float(atmc.get("T", 0.02))
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
