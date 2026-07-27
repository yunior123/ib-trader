#!/usr/bin/env python3
"""chart_levels.py — genera charts/data/levels_<sym>.json (GEX / gamma-flip / muros)
desde el cache IBKR opt_chain_<sym>.txt via gex_core (2026-07-23).

El puente del chart (chart_bridge.py) lee este JSON y dibuja las lineas horizontales
(createPriceLine) de call-wall / put-wall / gamma-flip + el perfil GEX por strike.
ADITIVO, senal-solamente. Sin red: usa el cache TWS que ya mantiene opt_chain_cache.py.

Uso: python3 scripts/chart_levels.py [SYM ...]   (default: flota con cache disponible)
"""
import json, os, sys, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gex_core

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# SANDBOX DE REPLAY (2026-07-25, aditivo): scripts/replay.cpp publica las cadenas historicas
# en un directorio APARTE (nunca sobre data/ real, que la flota viva esta leyendo). Sin poder
# redirigir este chdir no habria forma de generar los levels_<sym>.json del sandbox.
# Sin la variable de entorno el comportamiento es IDENTICO al de siempre.
ROOT = os.environ.get("IBT_ROOT") or REPO
os.chdir(ROOT)
OUT = "charts/data"

# RELOJ VIRTUAL para gex_core (IBT_ASOF="auto" | epoch). gex_core decide el 0DTE con la fecha
# de PARED (`time.strftime("%Y%m%d")`) y el DTE con `time.time()`. Con una cadena de hace dos
# dias eso descarta TODOS los contratos por expirados y devuelve None: el replay se quedaria
# sin niveles y la brujula en "SIN LECTURA". Aqui se congela el reloj del PROCESO (no se toca
# gex_core, que esta vetado). El arreglo de verdad es un parametro `as_of` en gex_core: lo
# decide Yunior. Sin IBT_ASOF nada de esto se activa.
_ASOF = os.environ.get("IBT_ASOF") or ""
_real_time, _real_strftime, _real_localtime = time.time, time.strftime, time.localtime


def _freeze_clock(epoch):
    """Congela time.time()/time.strftime() del proceso en `epoch` (segundos)."""
    ep = float(epoch)
    time.time = lambda: ep
    time.strftime = lambda fmt, t=None: _real_strftime(fmt, t if t is not None
                                                       else _real_localtime(ep))


def _asof_of(path):
    """Epoch as-of: 'auto' -> el `epoch` de la cabecera del snapshot; si no, el valor dado."""
    if _ASOF != "auto":
        try:
            return float(_ASOF)
        except ValueError:
            return None
    try:
        with open(path) as f:
            parts = f.readline().split()
        return float(parts[parts.index("epoch") + 1])
    except Exception:
        return None       # fail-loud por ausencia: sin as-of no se congela nada


def spot_from_cache(path):
    """El header del cache trae 'spot NNN'."""
    try:
        with open(path) as f:
            head = f.readline()
        for tok in head.replace("|", " ").split():
            pass
        parts = head.split()
        if "spot" in parts:
            return float(parts[parts.index("spot") + 1])
    except Exception:
        return None
    return None


FREEZE_MIN = 9 * 60 + 35     # 09:35 ET: el flip/VT del dia se congela aqui (features #6/#20)


POLY_LOOKBACK_DIAS = 4       # viernes 15:58 tiene que servir para el plan del lunes 04:00


def poly_chain_path(sym, day=None, lookback=POLY_LOOKBACK_DIAS):
    """La cadena de Polygon MAS RECIENTE (griegas/IV/OI MEDIDOS) de los ultimos `lookback`
    dias de calendario, o None.

    Verificado 2026-07-25: el snapshot /v3/snapshot/options trae greeks+IV+OI reales
    (QQQ 816/854 contratos con griegas = 95.5%), mientras que el cache TWS a las 16:16
    trae iv=-1 delta=-1 gamma=-1 en el 100% de las filas. Fuera de RTH esta es la unica
    fuente con griegas MEDIDAS; se prefiere solo cuando la de IBKR no sirve, para no perder
    frescura durante la sesion.

    Por que se mira ATRAS y no solo hoy: el OI NO cambia mientras el mercado esta cerrado, asi
    que el libro del ultimo cierre ES el libro correcto para el mapa nocturno, del premarket y
    de los planes de las 04:00 (que corren con el fin de semana por medio). La edad va publicada
    en `chain_age_s` y el vencimiento muerto lo elimina `gex_core.exp_status`, asi que nada de
    esto se puede colar como "de ahora". Y dentro de RTH este respaldo NO se acepta: alli una
    cadena de mas de 45 min se marca rancia y la gamma se mutea."""
    base = time.time() if day is None else time.mktime(time.strptime(day, "%Y-%m-%d"))
    for i in range(max(1, lookback)):
        d = time.strftime("%Y-%m-%d", time.localtime(base - i * 86400))
        cands = sorted(glob.glob(f"data/history/{d}/poly_chain_{sym.lower()}_*.txt"))
        if cands:
            return cands[-1]
    return None


def _et_min(ts=None):
    """Minutos del dia del reloj del Mac (= ET, ley de la casa)."""
    lt = time.localtime(ts if ts is not None else time.time())
    return lt.tm_hour * 60 + lt.tm_min


def freeze_decision(flip_live, prev_open, prev_day, today, now_min, is_market_day):
    """Decide (flip_open, congelar_ahora). PURA a proposito: es la regla que evita el
    crying-wolf y tiene que poder testearse sin reloj ni ficheros.

    - ya congelado HOY -> se mantiene, pase lo que pase con el spot.
    - dia de mercado y >= 09:35 -> congela el flip vivo.
    - fin de semana / antes de 09:35 -> None (no hay apertura que congelar; inventar un
      nivel "de apertura" fuera de sesion seria exactamente la clase de numero plausible
      que la casa prohibe)."""
    if prev_day == today and prev_open is not None:
        return prev_open, False
    if flip_live is not None and is_market_day and now_min >= FREEZE_MIN:
        return flip_live, True
    return None, False


def _frozen_flip(sym):
    """(flip_open, frozen_day, frozen_at) del levels_<sym>.json anterior, o (None,None,None).

    Por que congelar (feature #6): el OI intradia es el del cierre ANTERIOR, congelado. Un
    flip que se mueve con ese libro estatico no mide un cambio de regimen, mide el spot
    moviendose bajo un libro quieto — y cada oscilacion cruzando el nivel era un crying-wolf.
    Un nivel que no puede oscilar no puede dar falsas alarmas."""
    try:
        with open(f"{OUT}/levels_{sym.lower()}.json") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        return None, None, None
    return prev.get("flip_open"), prev.get("frozen_day"), prev.get("frozen_at")


def _from_cache_capturing(path, spot, all_exp):
    """gex_core.from_ibkr_cache + los contratos `usable` que uso, para poder calcular el
    CHARM sin duplicar su filtrado (banda, vencimiento vivo, IV invertida del mid).
    gex_core esta vetado (ver cabecera): se envuelve build_gex en el proceso, como el
    reloj de _freeze_clock. Devuelve (g, contratos) — contratos [] si no se pudo casar."""
    orig = gex_core.build_gex
    box = []

    def cap(contracts, spot_, scale="house"):
        cs = list(contracts)
        box.append(cs)
        return orig(cs, spot_, scale=scale)

    gex_core.build_gex = cap
    try:
        g = gex_core.from_ibkr_cache(path, spot, scale="dollar1pct", all_exp=all_exp)
    finally:
        gex_core.build_gex = orig
    if not g or not box:
        return g, []
    # el ultimo build_gex de una llamada buena es el de `usable`; se exige que cuadre con
    # n_gamma_ok antes de fiarse. Si no cuadra -> [] y el charm sale None con motivo.
    cs = box[-1]
    return g, (cs if len(cs) == g.get("n_gamma_ok") else [])


def gen(sym, spot=None, write=True, all_exp=False):
    """spot=None -> usa el spot del header del cache (EOD/última actualización TWS).
    spot=<precio vivo> -> recalcula GEX/flip/walls al spot EN VIVO (real time; el OI
    del cache es lento pero el flip y los muros se desplazan con el precio).
    write=False -> no escribe el JSON (para el loop en vivo, evita churn de disco)."""
    path = f"data/opt_chain_{sym.lower()}.txt"
    if not os.path.exists(path):
        path = poly_chain_path(sym) or path
    if not os.path.exists(path):
        return None
    if _ASOF:
        ep = _asof_of(path)
        if ep is None:
            print(f"[chart_levels] IBT_ASOF sin epoch utilizable para {sym}: no congelo reloj",
                  file=sys.stderr)
        else:
            _freeze_clock(ep)
    if spot is None:
        spot = spot_from_cache(path)
    if not spot:
        return None
    g, cs_used = _from_cache_capturing(path, spot, all_exp)  # $/1% como gexa
    # RESPALDO CON GRIEGAS MEDIDAS: si el cache TWS no tiene griegas usables (tipico fuera de
    # RTH: iv=-1 en todas las filas) se reintenta con el snapshot de Polygon del dia, que SI
    # las trae. Solo se acepta si resulta mejor: nunca se cambia una fuente buena por otra.
    if (g is None or not g.get("gamma_ok")) and not path.startswith("data/history/"):
        alt = poly_chain_path(sym)
        if alt:
            g2, cs2 = _from_cache_capturing(alt, spot, all_exp)
            if g2 and g2.get("gamma_ok"):
                g, path, cs_used = g2, alt, cs2
    if not g:
        return None
    wc = gex_core.wall_context(g, spot)
    # perfil ordenado por strike (para el histograma horizontal)
    prof = [{"strike": k, "gex": round(v, 1)} for k, v in sorted(g["profile"].items())]
    vprof = [{"strike": k, "vex": round(v, 1)} for k, v in sorted(g.get("vex_profile", {}).items())]
    # CHARM (dolar-delta por dia de decaimiento) = motor del drift/pin de la TARDE
    # (13:30-15:45, skill pin-and-expiry-mechanics). gex_core lo sabe calcular pero no lo
    # publica; se calcula aqui sobre los MISMOS contratos que el GEX. Sin contratos casados
    # -> None + motivo, jamas un perfil vacio que el chart pintaria como "charm plano".
    cprof, net_charm, charm_peak, charm_why = [], None, None, None
    if not g.get("gamma_ok"):
        charm_why = g.get("degraded_reason") or "sin griegas usables"
    elif not cs_used:
        charm_why = "no se pudieron casar los contratos de gex_core (n_gamma_ok != capturados)"
    else:
        # bs_charm es por AÑO: a 0DTE (T~1/365) eso da cifras de 1e11 que no dicen nada.
        # Se publica por DIA, que es como se lee el drift de la tarde.
        cx = gex_core.build_exposure(cs_used, spot, greek="charm", scale="dollar1pct")
        cprof = [{"strike": k, "charm": round(v / 365.0, 1)} for k, v in sorted(cx["profile"].items())]
        net_charm, charm_peak = cx["net"] / 365.0, cx["peak"]
    pmap = g["profile"]
    # DEALER PRESSURE score -100..+100 (composite gamma 80% + vanna 20%, normalizado
    # por el peso total del libro). Cerca del flip (±0.15%) se degrada (régimen inestable).
    # SIN GRIEGAS NO HAY PRESION. Antes esto siempre daba un numero porque el perfil venia de
    # una IV inventada; ahora, si gex_core degrado, la presion es None y la etiqueta lo dice.
    gamma_ok = bool(g.get("gamma_ok"))
    near_flip = bool(g.get("flip")) and abs((g["flip"] - spot) / spot * 100) < 0.15
    if not gamma_ok or g.get("net_gex") is None:
        press, press_lab = None, "sin griegas"
    else:
        tot_g = sum(abs(v) for v in pmap.values()) or 1.0
        tot_v = sum(abs(v) for v in g.get("vex_profile", {}).values()) or 1.0
        gl = g["net_gex"] / tot_g
        vl = (g.get("net_vex") or 0.0) / tot_v
        press = 100.0 * (0.8 * gl + 0.2 * vl)
        if near_flip:
            press *= 0.4
        press = round(max(-100.0, min(100.0, press)))
        if near_flip:
            press_lab = "near flip"
        elif press >= 60: press_lab = "PIN fuerte"
        elif press >= 20: press_lab = "amortigua"
        elif press <= -60: press_lab = "AMPLIFICA fuerte"
        elif press <= -20: press_lab = "amplifica"
        else: press_lab = "FLAT"
    # dominancia call/put del POC (abs_wall), estilo gexa "72%P"
    poc_dom = None
    aw = g.get("abs_wall")
    if aw is not None:
        cc = abs(g["call_gex"].get(aw, 0.0)); pp = abs(g["put_gex"].get(aw, 0.0)); tot = cc + pp
        if tot > 0:
            poc_dom = f"{round(100 * max(cc, pp) / tot)}%{'C' if cc >= pp else 'P'}"
    out = {
        "sym": sym.upper(), "spot": spot, "asof": int(time.time()),
        "exp": g.get("exp"), "dte": g.get("dte"), "scope": g.get("scope"),   # 0DTE / ALL
        "net_vex": round(g["net_vex"], 1) if g.get("net_vex") is not None else None,
        "vex_peak": g.get("vex_peak"),
        "vex_profile": vprof,
        "net_charm": round(net_charm, 1) if net_charm is not None else None,
        "charm_peak": charm_peak,
        "charm_profile": cprof,
        "charm_why": charm_why,
        "pressure": press, "pressure_lab": press_lab,
        "iv_atm": g.get("iv_atm"), "em": g.get("em"),
        "net_gex": round(g["net_gex"], 1) if g.get("net_gex") is not None else None,
        "regime": g.get("regime"),
        "flip": round(g["flip"], 2) if g["flip"] else None,
        "flip_static": round(g["flip_static"], 2) if g["flip_static"] else None,
        "call_wall": g["call_wall"], "put_wall": g["put_wall"], "abs_wall": g["abs_wall"],
        "poc_dom": poc_dom,
        "call_wall_gex": round(pmap.get(g["call_wall"], 0), 1) if g["call_wall"] else None,
        "put_wall_gex": round(pmap.get(g["put_wall"], 0), 1) if g["put_wall"] else None,
        "abs_wall_gex": round(pmap.get(g["abs_wall"], 0), 1) if g["abs_wall"] else None,
        "oi_call_wall": g["oi_call_wall"], "oi_put_wall": g["oi_put_wall"],
        "near_call_wall": wc["near_call_wall"], "near_put_wall": wc["near_put_wall"],
        "near_flip": wc["near_flip"],
        "profile": prof,
    }
    # PIN vs TRAMPILLA por muro (2026-07-25). gex_core.build_gex ya los calcula y
    # wall_context los reexporta, pero este `out` era explicito y los TIRABA, asi que el
    # chart no podia distinguir un nivel que AGUANTA de uno que el precio ATRAVIESA
    # acelerando — justo el fade que la doctrina prohibe. Aditivo: si gex_core no los trae
    # (version vieja) el valor queda None y el chart pinta "?" en gris, nunca un pin falso.
    for _key in ("call_wall", "put_wall", "abs_wall"):
        out[_key + "_kind"] = wc.get(_key + "_kind")
        out[_key + "_regime"] = wc.get(_key + "_regime")
        _n = wc.get(_key + "_net")
        out[_key + "_net"] = round(_n, 1) if _n is not None else None

    # ---- CABECERA DE HONESTIDAD (feature #5). Todo consumidor puede ver, sin adivinar, sobre
    # que se calculo el mapa: cuantas filas tenian griegas, que banda uso el fetcher, cuantos
    # vencimientos, la edad del snapshot y si el vencimiento rodo. `gamma_ok=false` significa
    # "los numeros gamma de este fichero son null a proposito", no "falta el dato".
    out["gamma_ok"] = gamma_ok
    for k in ("greeks_ok_pct", "chain_src", "chain_ts", "chain_age_s", "stale", "stale_reason",
              "regime_raw", "regime_why", "parity_ok_pct",
              "net_gex_parity_lo", "net_gex_parity_hi",
              "quotes_ok", "session", "band_used", "band_fetch", "n_expiries",
              "exps_en_fichero", "rows_total", "n_candidates", "n_gamma_ok", "n_no_greeks",
              "n_iv_provider", "n_iv_inverted", "iv_source", "exp_rolled", "roll_reason",
              "degraded_reason", "gross_gex", "bifurcation", "hhi", "n_strikes_populated"):
        v = g.get(k)
        out[k] = round(v, 4) if isinstance(v, float) and k not in ("chain_ts",) else v
    out["chain_path"] = g.get("chain_path")

    # ---- FLIP HONESTO + CONGELADO A LAS 09:35 (feature #6)
    out["flip_live"] = out["flip"]
    out["flip_src"] = g.get("flip_src")
    out["flip_why"] = g.get("flip_why")
    out["roots"] = [round(r, 2) for r in (g.get("roots") or [])]
    out["trapdoor_root"] = (round(g["trapdoor_root"], 2)
                           if g.get("trapdoor_root") is not None else None)
    today = time.strftime("%Y-%m-%d")
    prev_open, prev_day, fat = _frozen_flip(sym)
    fo, nuevo = freeze_decision(out["flip_live"], prev_open, prev_day, today, _et_min(),
                                time.localtime().tm_wday < 5)
    if nuevo:
        fat = int(time.time())
    out["flip_open"] = fo
    out["frozen_at"] = fat
    out["frozen_day"] = today if fo is not None else None
    # `flip` = el CONGELADO cuando existe: es la clave que leen ./compass, fleet_consensus,
    # direction_view y narrator, y la regla de la feature dice que el regimen se lee del
    # congelado. `flip_live` queda como diagnostico.
    if fo is not None:
        out["flip"] = fo

    if write:
        os.makedirs(OUT, exist_ok=True)
        # ESCRITURA ATOMICA (obligatoria): ./compass lee este fichero cada 0.25 s. Con el
        # json.dump directo sobre el destino, un lector que caiga en medio del write ve un
        # JSON TRUNCADO -> "SIN LECTURA" o, peor, niveles a medias.
        dst = f"{OUT}/levels_{sym.lower()}.json"
        tmp = dst + f".tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(out, f, indent=1)
        os.replace(tmp, dst)
    return out


def main():
    syms = sys.argv[1:]
    if not syms:
        syms = [os.path.basename(p)[10:-4] for p in glob.glob("data/opt_chain_*.txt")]
    ok = 0
    for s in syms:
        # forma "sym@precio": recalcula GEX/flip/muros al spot dado (lo que hace el loop en
        # vivo pasando spot=). El replay lo usa para que el mapa NO herede el spot rancio de
        # la cabecera del snapshot (hasta 5 min de retraso = flecha con retraso fabricado).
        spot = None
        if "@" in s:
            s, _, px = s.partition("@")
            try:
                spot = float(px)
            except ValueError:
                print(f"{s.upper():6s} spot invalido '{px}' -> skip", file=sys.stderr)
                continue
        r = gen(s, spot=spot)
        if r and r.get("gamma_ok"):
            ok += 1
            gp = r.get("greeks_ok_pct")
            print(f"{r['sym']:6s} spot {r['spot']:8.2f} | net_gex {r['net_gex']:>14.0f} {r['regime']} "
                  f"| flip {r['flip']} (live {r['flip_live']} est {r['flip_static']} "
                  f"src {r['flip_src']}) | CW {r['call_wall']} PW {r['put_wall']} "
                  f"| abs {r['abs_wall']} | griegas {100 * gp:.0f}% {r.get('chain_src')}"
                  f"{' ROLL' if r.get('exp_rolled') else ''}")
        elif r:
            # MUTEADO A PROPOSITO: se imprime el motivo, no un mapa con numeros inventados.
            print(f"{r['sym']:6s} spot {r['spot']:8.2f} | GAMMA MUTEADA — {r.get('degraded_reason')}"
                  f" | muros OI: C {r.get('oi_call_wall')} P {r.get('oi_put_wall')}"
                  f" | exp {r.get('exp')}{' ROLL' if r.get('exp_rolled') else ''}")
        else:
            print(f"{s.upper():6s} sin cache/spot -> skip")
    print(f"\n-> {OUT}/levels_*.json  ({ok} generados)")


if __name__ == "__main__":
    main()
