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
        iv = float(c.get("iv", 0.3)) or 0.3
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
    for c in contracts:
        K = float(c["strike"])
        oi = float(c.get("oi", 0) or 0)
        if oi <= 0:
            continue
        right = c["right"].upper()[:1]
        g = c.get("gamma")
        if g is None or g <= 0:
            g = bs_gamma(spot, K, float(c.get("T", 0.02)), float(c.get("iv", 0.3)) or 0.3)
        if g <= 0:
            continue
        gx = g * oi * 100 * mult
        if right == "C":
            call_gex[K] = call_gex.get(K, 0.0) + gx
            call_oi[K] = call_oi.get(K, 0.0) + oi
            profile[K] = profile.get(K, 0.0) + gx
        else:
            put_gex[K] = put_gex.get(K, 0.0) - gx
            put_oi[K] = put_oi.get(K, 0.0) + oi
            profile[K] = profile.get(K, 0.0) - gx

    net = sum(profile.values())
    # recompute del flip solo si hay DISPERSION real de IV (skew): con IV plana de
    # respaldo (greeks no disponibles) el barrido es poco fiable -> usar estatico.
    ivs = {round(float(c["iv"]), 4) for c in contracts if c.get("iv", 0) and float(c["iv"]) > 0}
    flip_rc = flip_recompute(contracts, spot) if len(ivs) >= 3 else None
    flip_static = _flip(profile)
    out = {
        "profile": profile, "call_gex": call_gex, "put_gex": put_gex,
        "net_gex": net, "regime": "POS" if net >= 0 else "NEG",
        "flip": flip_rc if flip_rc is not None else flip_static,
        "flip_static": flip_static, "flip_recompute": flip_rc,
        "spot": spot, "scale": scale,
    }
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


def flip_recompute(contracts, spot, lo=0.85, hi=1.15, steps=120):
    """Gamma-flip CORRECTO (SqueezeMetrics/Perfiliev): recomputa la gamma BS a cada
    spot hipotetico S del grid (la gamma DEPENDE de S), arma GEX(S) = sum ±gamma(S)·
    OI·100·S^2·0.01, y halla la raiz por interpolacion lineal en el cambio de signo.
    Mas fiel que interpolar el perfil estatico (_flip), a costa de recomputar griegas.
    Requiere iv+T por contrato (usa BS gamma, ignora la gamma del snapshot que es a
    spot actual). Devuelve el precio de gamma-cero o None."""
    grid = [spot * (lo + (hi - lo) * i / (steps - 1)) for i in range(steps)]
    prev_S = prev_g = None
    for S in grid:
        tot = 0.0
        for c in contracts:
            oi = float(c.get("oi", 0) or 0)
            if oi <= 0:
                continue
            iv = float(c.get("iv", 0.3)) or 0.3
            T = float(c.get("T", 0.02))
            g = bs_gamma(S, float(c["strike"]), T, iv)
            sign = 1.0 if c["right"].upper()[:1] == "C" else -1.0
            tot += sign * g * oi * 100 * S * S * 0.01
        if prev_g is not None and ((prev_g < 0 <= tot) or (prev_g > 0 >= tot)):
            span = tot - prev_g
            if abs(span) < 1e-9:
                return S
            return prev_S - (S - prev_S) * prev_g / span
        prev_S, prev_g = S, tot
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
def _T_of(exp):
    """Años al 16:00 ET del vencimiento YYYYMMDD (piso 1e-5)."""
    import time as _t
    try:
        return max((_t.mktime(_t.strptime(exp, "%Y%m%d")) + 16 * 3600 - _t.time()) / (365 * 86400), 1e-5)
    except Exception:
        return 0.02


def from_ibkr_cache(path, spot, band=0.035, scale="house", all_exp=False):
    """Lee data/opt_chain_<sym>.txt. scale='dollar1pct' -> $/1% (estándar gexa).
    all_exp=False (default) -> 0DTE puro (vencimiento más cercano >= hoy).
    all_exp=True -> TODA la cadena mezclada, cada contrato con su propio T (mapa multi-día).
    Añade el perfil VEX (vanna) y la etiqueta de escala/scope."""
    import os
    contracts = []
    exps = set()
    rows = []
    if not os.path.exists(path):
        return None
    for ln in open(path):
        if ln.startswith("#"):
            continue
        f = ln.split()
        if len(f) < 10:
            continue
        try:
            k, right, exp = float(f[0]), f[1], f[2]
            oi, iv, gamma = float(f[6]), float(f[7]), float(f[9])
        except Exception:
            continue
        rows.append((k, right, exp, oi, iv, gamma))
        exps.add(exp)
    if not rows:
        return None
    import time as _t
    today = _t.strftime("%Y%m%d")
    future = sorted(e for e in exps if e >= today)
    exp0 = future[0] if future else sorted(exps)[0]   # 0DTE
    for (k, right, exp2, oi, iv, gamma) in rows:
        if not all_exp and exp2 != exp0:
            continue
        if exp2 < today:            # nunca contratos expirados
            continue
        if not (spot * (1 - band) <= k <= spot * (1 + band)):
            continue
        contracts.append({"strike": k, "right": right, "oi": oi,
                          "gamma": gamma if gamma > 0 else None,
                          "iv": iv if iv > 0 else 0.3, "T": _T_of(exp2)})
    if not contracts:
        return None
    g = build_gex(contracts, spot, scale=scale)
    # cache near-ATM: el flip ESTÁTICO (gamma real del snapshot) queda más cerca de gexa.
    if g.get("flip_static") is not None:
        g["flip"] = g["flip_static"]
    g["exp"] = "ALL" if all_exp else exp0
    g["dte"] = None if all_exp else round(_T_of(exp0) * 365, 2)
    g["scope"] = "ALL" if all_exp else "0DTE"
    # ATM IV + expected move (±1σ hasta el vencimiento) = spot·IV·√T
    atmc = min(contracts, key=lambda c: abs(c["strike"] - spot))
    iv_atm = float(atmc.get("iv", 0.3)) or 0.3
    T_atm = float(atmc.get("T", 0.02))
    g["iv_atm"] = round(iv_atm, 4)
    g["em"] = round(spot * iv_atm * math.sqrt(T_atm), 2)
    # VEX (vanna exposure) en la misma escala
    vx = build_exposure(contracts, spot, greek="vanna", scale=scale if scale != "house" else "dollar1pct")
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
