#!/usr/bin/env python3
"""book_quality.py — VETO POR CALIDAD DE LIBRO (feature minada #3, 2026-07-25).

No es un 12o factor aditivo: es un **coeficiente MULTIPLICATIVO** sobre los pesos gamma que
ya existen (`flip` 1.5 / `walls` 1.0 / `magnet` 1.1 en direction_view). Con `coef = 0.0` la
lectura es literal: **"los niveles gamma son decoracion hoy para este nombre"**.

POR QUE (medido, no supuesto): la cadena de NOK son 2 strikes por vencimiento (4 filas de
las 8 del fichero) y DRAM/SPCX/SKHY son libros de un puñado de contratos — y la casa canta
veredictos de muro, flip y regimen sobre ellos con la misma cara que sobre QQQ (48 strikes
poblados). Borrar confirmaciones falsas vale mas que añadir una señal.

Salida: `data/book_quality.json`  (lo lee ./compass: `book_label` + `coef` por simbolo)
        `data/book_quality_hist.jsonl`  (ledger para los percentiles; ver LIMITES abajo)

LIMITES DECLARADOS (no se disimulan)
  `book_pctile` e `impact_pctile` piden 20 sesiones del snapshot COMPLETO de Polygon
  (feature #7). Con la banda de IBKR, `gross` mide la VENTANA DEL FETCHER, no el tamaño del
  libro, asi que un percentil sobre eso seria un numero inventado con pinta de medida. Hasta
  que haya historia: percentiles = `null` declarado y el `coef` cae al SUELO conservador
  (0.35), con `coef_basis` diciendolo. Cada corrida sobre snapshot completo de Polygon
  añade una linea al ledger, asi que la historia se acumula sola.

Uso:  ./venv/bin/python scripts/book_quality.py            # flota con mapa disponible
      ./venv/bin/python scripts/book_quality.py QQQ NOK
      ./venv/bin/python scripts/book_quality.py --json
"""
import glob
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
ROOT = os.environ.get("IBT_ROOT") or REPO
os.chdir(ROOT)

import chart_levels                        # noqa: E402  (gen() -> el mapa GEX del simbolo)
import gex_core                            # noqa: E402  (build_gex sobre la cadena archivada)
import gex_snapshot                        # noqa: E402  (latest_chain/contracts_from: chain_full)
import universe                            # noqa: E402  (universo del mapa vs flota de señales)

OUT_JSON = "data/book_quality.json"
HIST = "data/book_quality_hist.jsonl"
DB = "trades.db"

# ---- umbrales de la spec (feature #3, paso 6/7)
THIN_PCTILE = 0.20
THIN_STRIKES = 8            # menos de 8 strikes poblados no puede DEFINIR un muro
THIN_GREEKS = 0.5
BIFURCATION_MIN = 4.0
NEAR_FLIP_FRAC = 0.0015     # 0.15% del spot
COEF_FLOOR = 0.35           # suelo del coeficiente cuando no hay percentiles medibles
HIST_MIN = 5                # menos de 5 sesiones -> percentil = None (no se publica)
HIST_MAX = 20               # ventana de la spec

# ---- SEGUNDA PIERNA DE FUENTE (2026-07-25).
#
# EL ARTEFACTO: el cache `data/opt_chain_<sym>.txt` trae iv=-1 delta=-1 gamma=-1 en el 100%
# de las filas cuando TWS esta apagado -> greeks_ok_pct 0.00, 0 strikes poblados, THIN y
# coef 0.0. Eso no mide el libro, mide que TWS esta cerrado: apagaria el mapa gamma de la
# flota entera por un ARTEFACTO DE LA FUENTE.
#
# ESTADO REAL MEDIDO (2026-07-25 16:5x, flota parada, TWS apagado, los 30 de fleet.txt):
# el artefacto NO se reproduce. `chart_levels.gen` YA cae por su cuenta a los ficheros
# `poly_chain_<sym>_*.txt` archivados hoy, asi que los 30 resuelven por `polygon_snapshot_v3`
# con **83-100% de griegas** y salen **9/30 THIN** — y esos 9 lo son por POCOS STRIKES
# (NOK 1, NFLX/QCOM/SKHY 5, NVDA 6, AMZN/DRAM/INTC/TSLA 7), que es THIN legitimo, no por
# griegas ausentes. La medicion anterior de esta cabecera ("26/26 THIN") se tomo a las 11:22,
# ANTES de que el archivador llenase data/history/2026-07-25/; quedo obsoleta el mismo dia.
#
# CONSECUENCIA HONESTA: esta segunda pierna es hoy un NO-OP (verificado: 0/30 simbolos
# cambian de fuente, etiqueta o coef al activarla). Se deja porque el artefacto es real y
# reaparece en cuanto el archivador no haya corrido — pero como no se recorre sola, va
# cubierta por tests que la fuerzan (tests/test_book_quality.py), o seria codigo muerto.
#
# LO QUE ESTA PIERNA NO ARREGLA: los 9 THIN por pocos strikes. El mapa de `chart_levels` es
# 0DTE puro y la cadena `chain_full` trae todos los vencimientos de la banda, asi que cambiar
# de fuente por CONTEO DE STRIKES rescataria varios de esos 9 — pero es otra regla, mueve
# muchos simbolos y afecta al dinero. NO se hace aqui por decision propia: lo decide Yunior.
#
# `chart_levels.gen` ya cae a `data/history/<fecha>/poly_chain_<sym>_*.txt`, pero esa pierna
# es 0DTE-pura y no publica la FECHA de la cadena, asi que aqui no se puede fechar el libro ni
# distinguir "cadena de hoy" de "cadena del martes". Cuando la fuente activa no llega al
# minimo de griegas se reconstruye desde `chain_full_<sym>.json` — el artefacto canonico, con
# griegas+OI medidos y `meta` auditable (banda, dte_max, spot, snapshot local).
MIN_GREEKS_SRC = 0.5        # < 50% de griegas usables = la fuente no sirve (== gex_core.MIN_GREEKS_OK)
# CADUCIDAD, coherente con `daily_fleet_plans.gex_snapshot_for` y `gex_snapshot.latest_chain`
# (mismo margen, no un criterio nuevo): el OI no se mueve con el mercado cerrado, asi que la
# cadena del viernes ES el libro del sabado; una de hace 6 dias no lo es.
CHAIN_MAX_DAYS = 5


def atomic_write(path, text):
    """tmp + os.replace: `./compass` y los bots leen estos ficheros en bucle."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# ------------------------------------------------------------------ liquidez
def adv20(sym):
    """Volumen medio diario (acciones) de las ultimas <=20 sesiones desde poly_bars.
    Devuelve (adv, n_sesiones) o None — nunca un volumen por defecto."""
    if not os.path.exists(DB):
        return None
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=20)
        rows = c.execute(
            "SELECT d, SUM(v) FROM (SELECT date(ts/1000,'unixepoch') d, v FROM poly_bars "
            "WHERE sym=?) GROUP BY d ORDER BY d DESC LIMIT 20", (sym.upper(),)).fetchall()
        c.close()
    except sqlite3.Error:
        return None
    vols = [float(v) for _, v in rows if v]
    if not vols:
        return None
    return sum(vols) / len(vols), len(vols)


# ---------------------------------------------------------------- percentiles
def percentile(value, hist):
    """Percentil de `value` dentro de `hist` (fraccion de la historia <= value).
    None si la muestra es demasiado corta: publicar un percentil con n=1 seria
    exactamente el numero plausible que la casa prohibe."""
    if value is None or not hist or len(hist) < HIST_MIN:
        return None
    hist = sorted(hist)[-HIST_MAX:]
    return sum(1 for h in hist if h <= value) / len(hist)


def load_hist(path=HIST, src=None):
    """{sym: {"gross": [...], "impact": [...]}} desde el ledger (una linea por sym-sesion).

    `src` filtra por FUENTE. Es obligatorio para un percentil honesto: el mapa 0DTE de
    `poly_chain` y el de `chain_full` (todos los vencimientos de la banda) tienen `gross`
    de MAGNITUD DISTINTA por construccion — medido hoy, QQQ 6.4e8 con 48 strikes 0DTE frente
    a 61 strikes multi-vencimiento. Un percentil sobre las dos poblaciones juntas seria un
    numero inventado con pinta de medida. `src=None` no filtra (compatibilidad y tests)."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue                      # linea corrupta: se salta, no se adivina
            if src is not None and r.get("src") != src:
                continue                      # otra poblacion: no entra en este percentil
            s = out.setdefault(str(r.get("sym", "")).upper(), {"gross": [], "impact": []})
            if isinstance(r.get("gross"), (int, float)):
                s["gross"].append(float(r["gross"]))
            if isinstance(r.get("impact"), (int, float)):
                s["impact"].append(float(r["impact"]))
    return out


# ------------------------------------------------------- eleccion de la fuente
def usable_greeks(pct):
    """True solo si `pct` es un numero >= MIN_GREEKS_SRC. `None` NO es usable (y no se
    convierte en 0.0: un cero plausible es justo lo que la casa prohibe)."""
    return isinstance(pct, (int, float)) and float(pct) >= MIN_GREEKS_SRC


def prefer_fallback(primary_pct, fallback_pct):
    """(usar_fallback, motivo). PURA: es la regla de la segunda pierna y tiene que poder
    testearse sin ficheros.

    Solo se cambia de fuente cuando la primaria NO sirve y la de respaldo SI. Nunca se cambia
    una fuente buena por otra (aunque la de respaldo tenga mas griegas): dentro de RTH el
    cache TWS es el dato fresco y la cadena archivada es del cierre anterior.
    Si NINGUNA llega al minimo no hay respaldo que valga -> THIN de verdad, coef 0."""
    if usable_greeks(primary_pct):
        return False, None
    if not usable_greeks(fallback_pct):
        return False, ("ninguna fuente llega al "
                       f"{MIN_GREEKS_SRC:.0%} de griegas usables (primaria "
                       f"{'n/d' if primary_pct is None else f'{primary_pct:.0%}'}, "
                       f"chain_full {'n/d' if fallback_pct is None else f'{fallback_pct:.0%}'})")
    return True, (f"fuente primaria con griegas "
                  f"{'n/d' if primary_pct is None else f'{primary_pct:.0%}'} "
                  f"< {MIN_GREEKS_SRC:.0%} -> chain_full de Polygon (griegas MEDIDAS)")


def chain_full_map(sym, max_days=CHAIN_MAX_DAYS):
    """Mapa gamma de `sym` reconstruido desde `data/history/<fecha>/chain_full_<sym>.json`.

    Devuelve un dict con las MISMAS claves que consume `measure()` mas la procedencia, o
    **None** si no hay cadena dentro de `max_days`, si no trae spot, o si esta vacia. Jamas un
    dict a medias y jamas un cero: sin cadena no hay libro que medir.

    Ojo con el ALCANCE: este mapa se construye sobre TODOS los vencimientos del fichero (banda
    ADAPTATIVA por gamma marginal y vencimientos hasta el mensual siguiente desde 2026-07-26;
    la banda real va en `chain_band`), mientras que el de `chart_levels` es 0DTE puro. Son
    poblaciones distintas y por eso `chain_scope` va publicado en la salida — y por eso el
    ledger de percentiles no las mezcla."""
    path, fecha = gex_snapshot.latest_chain(sym, max_days=max_days)
    if not path:
        return None
    # n_cand = contratos con OI>0 (los unicos que pueden entrar en el perfil): es el
    # denominador que no se hunde al ensanchar la banda del archivo.
    cs, spot, meta, n_cand = gex_snapshot.contracts_from(path)
    if not spot or not n_cand or not cs:
        return None
    pct = len(cs) / n_cand
    gi = gex_core.build_gex(cs, spot)
    if not gi:
        return None
    try:
        edad_d = (time.time() - time.mktime(time.strptime(fecha, "%Y-%m-%d"))) / 86400.0
    except (TypeError, ValueError):
        return None                    # sin fecha utilizable no se puede fechar el libro
    out = dict(gi)
    out.update({
        "spot": spot,
        "greeks_ok_pct": pct,
        # `build_gex` publica `flip`; los consumidores de este modulo leen `flip_live`
        # (el `flip_open` congelado lo arrastra `measure()` desde el mapa primario).
        "flip_live": gi.get("flip"),
        "gamma_ok": usable_greeks(pct) and bool(gi.get("net_gex") is not None),
        "chain_src": "polygon_chain_full",
        "chain_path": path,
        "chain_date": fecha,
        "chain_age_days": round(edad_d, 2),
        "chain_n_contracts": len(cs),
        "chain_n_oi": n_cand,
        "chain_band": meta.get("band"),
        "chain_dte_max": meta.get("dte_max"),
        "chain_snapshot_local": meta.get("snapshot_local"),
        "chain_scope": "todos_los_vencimientos_del_fichero",
        "degraded_reason": (None if usable_greeks(pct) else
                            f"griegas usables {pct:.0%} < {MIN_GREEKS_SRC:.0%} en chain_full"),
    })
    return out


def provenance(lv, fallback=False, reason=None):
    """Los campos de procedencia que SIEMPRE viajan dentro del registro de un simbolo.
    Ley de la casa: jamas mezclar reconstruido con medido sin decirlo en el propio dato."""
    return {
        "chain_src": lv.get("chain_src"),
        "chain_path": lv.get("chain_path"),
        "chain_date": lv.get("chain_date"),
        "chain_age_days": lv.get("chain_age_days"),
        "chain_age_s": lv.get("chain_age_s"),
        "chain_n_contracts": lv.get("chain_n_contracts") or lv.get("n_candidates"),
        "chain_band": lv.get("chain_band") if lv.get("chain_band") is not None
        else lv.get("band_fetch"),
        "chain_dte_max": lv.get("chain_dte_max"),
        "chain_scope": lv.get("chain_scope") or lv.get("scope"),
        "greeks_medidas": bool(str(lv.get("chain_src") or "").startswith("polygon")),
        "src_fallback": bool(fallback),
        "src_switch_reason": reason,
        "chain_max_days": CHAIN_MAX_DAYS,
    }


# --------------------------------------------------------------- la evaluacion
def evaluate(gross, net, hhi, n_strikes, greeks_ok_pct, spot, flip,
             book_pctile=None, impact_pctile=None, abs_wall_regime=None):
    """PURA: mide -> etiqueta -> coeficiente. Sin ficheros ni reloj, para poder testearla.

    Etiquetas (excluyentes, en este orden):
      THIN         book_pctile<0.20  O  n_strikes<8  O  greeks_ok_pct<0.5   -> coef 0.0
      BIFURCATED   net<0 Y bifurcation>4 Y book_pctile>0.5   (scalps nivel-a-nivel si,
                   direccion-por-regimen NO)
      NEAR_FLIP    |spot-flip|/spot < 0.0015                 (regimen inestable)
      STABLE_PIN   el resto
    Coeficiente: THIN -> 0.0 ; si hay percentiles -> clamp(0.35+0.65*min(bp,ip),0,1) ;
    si no -> el suelo 0.35 (conservador y DECLARADO en coef_basis)."""
    reasons = []
    bif = (gross / abs(net)) if (gross and net not in (None, 0)) else None

    thin = []
    if greeks_ok_pct is None or greeks_ok_pct < THIN_GREEKS:
        thin.append(f"griegas {('n/d' if greeks_ok_pct is None else f'{greeks_ok_pct:.0%}')}"
                    f" < {THIN_GREEKS:.0%}")
    if n_strikes is None or n_strikes < THIN_STRIKES:
        thin.append(f"{n_strikes if n_strikes is not None else 'n/d'} strikes poblados "
                    f"< {THIN_STRIKES}")
    if book_pctile is not None and book_pctile < THIN_PCTILE:
        thin.append(f"libro en el percentil {book_pctile:.0%} de su propia historia")

    if thin:
        label, coef, basis = "THIN", 0.0, "thin"
        reasons = thin + ["los niveles gamma son decoracion hoy para este nombre: "
                          "operar solo precio / momentum / capitan"]
    else:
        if (net is not None and net < 0 and bif is not None and bif > BIFURCATION_MIN
                and book_pctile is not None and book_pctile > 0.5):
            label = "BIFURCATED"
            reasons.append(f"gross/|net| = {bif:.1f} con net<0: mucha gamma total y poca neta "
                           "-> scalps nivel-a-nivel SI, direccion-por-regimen NO")
        elif (spot and flip and abs(spot - flip) / spot < NEAR_FLIP_FRAC):
            label = "NEAR_FLIP"
            reasons.append(f"spot a {abs(spot - flip) / spot * 100:.3f}% del flip: regimen "
                           "inestable, sign-flip de hedging")
        else:
            label = "STABLE_PIN"
            reasons.append("libro denso y con regimen definido")
        if book_pctile is not None and impact_pctile is not None:
            coef = max(0.0, min(1.0, COEF_FLOOR + 0.65 * min(book_pctile, impact_pctile)))
            basis = "percentiles"
        else:
            coef = COEF_FLOOR
            basis = "suelo_sin_percentiles"
            reasons.append("sin 20 sesiones de snapshot COMPLETO de Polygon no hay percentil "
                           f"medible -> coef al suelo {COEF_FLOOR}")

    # PIN vs TRAMPILLA del muro dominante. El discriminador NO es el signo crudo del perfil
    # (con la convencion calls+/puts- un put wall es negativo POR CONSTRUCCION y se etiquetaria
    # TODO como trampilla): es el REGIMEN acumulado en el nivel, de que lado del flip cae.
    sign = None
    if abs_wall_regime == "POS":
        sign = "+"
    elif abs_wall_regime == "NEG":
        sign = "-"
        reasons.append("muro absoluto en regimen NEG = TRAMPILLA (los dealers amplifican "
                       "debajo): VETO DURO sobre 0DTE comprado a +-1 strike")
    return {"book_label": label, "coef": round(coef, 4), "coef_basis": basis,
            "bifurcation": None if bif is None else round(bif, 4),
            "hhi": None if hhi is None else round(hhi, 6),
            "abs_wall_sign": sign, "why": reasons}


# --------------------------------------------------------------------- corrida
def measure(sym, lv=None, alt=None):
    """Mide un simbolo desde su mapa GEX. Devuelve el registro o None si no hay NINGUN mapa.

    Dos piernas de fuente (ver MIN_GREEKS_SRC arriba): el mapa de `chart_levels` y, si sus
    griegas no llegan al minimo, el reconstruido desde la cadena archivada `chain_full`. La
    eleccion, la fuente elegida y el motivo van PUBLICADOS en el registro."""
    lv = lv if lv is not None else chart_levels.gen(sym, write=False)
    alt_lazy = alt is None
    if lv is None:
        # sin mapa primario la unica opcion es la cadena archivada (o nada)
        alt = chain_full_map(sym) if alt_lazy else alt
        if not alt:
            return None
        lv, usar, motivo = alt, True, "sin mapa primario (sin cache TWS utilizable)"
    else:
        if not usable_greeks(lv.get("greeks_ok_pct")) and alt_lazy:
            alt = chain_full_map(sym)
        usar, motivo = prefer_fallback(lv.get("greeks_ok_pct"),
                                      None if not alt else alt.get("greeks_ok_pct"))
        if usar:
            # el flip CONGELADO del dia (feature #6) es del simbolo, no de la fuente: si la
            # primaria ya lo habia congelado se ARRASTRA, para no resucitar un flip oscilante.
            alt = dict(alt)
            alt["flip_open"] = lv.get("flip_open")
            lv = alt
    prov = provenance(lv, fallback=usar, reason=motivo)
    gross = lv.get("gross_gex")
    net = lv.get("net_gex")
    spot = lv.get("spot")
    a = adv20(sym)
    impact = None
    if gross and a and spot:
        impact = gross / (a[0] * spot)          # gamma nocional por dolar de liquidez (SG #4)
    rec = {
        "sym": sym.upper(),
        "gross": None if gross is None else round(gross, 2),
        "net": None if net is None else round(net, 2),
        "n_strikes_populated": lv.get("n_strikes_populated"),
        "greeks_ok_pct": lv.get("greeks_ok_pct"),
        "gamma_ok": bool(lv.get("gamma_ok")),
        "spot": spot,
        "flip_open": lv.get("flip_open"),
        "flip_live": lv.get("flip_live"),
        "abs_wall": lv.get("abs_wall"),
        "abs_wall_regime": lv.get("abs_wall_regime"),
        "abs_wall_kind": lv.get("abs_wall_kind"),
        "impact": None if impact is None else round(impact, 10),
        "adv20": None if a is None else round(a[0], 0),
        "adv20_sesiones": None if a is None else a[1],
        "exp": lv.get("exp"), "exp_rolled": lv.get("exp_rolled"),
        "degraded_reason": lv.get("degraded_reason"),
    }
    rec.update(prov)              # la procedencia va DENTRO del dato, siempre
    return rec


def run(syms, hist=None):
    """`hist` explicito = una sola poblacion, sin filtrar (compatibilidad y tests).

    Con `hist=None` el percentil se busca en la historia DE LA FUENTE QUE USO CADA SIMBOLO,
    no en una sola tabla comun. Es obligatorio ahora que hay dos piernas: el `gross` de un
    mapa 0DTE y el de una cadena de todos los vencimientos son magnitudes distintas por
    construccion, asi que comparar el de hoy (chain_full) contra un historial de poly_chain
    daria un percentil sobre dos poblaciones = un numero inventado con pinta de medida.
    Se cachea por fuente: `load_hist` relee el ledger entero en cada llamada."""
    por_fuente = {}

    def hist_de(src):
        if hist is not None:
            return hist
        if src not in por_fuente:
            por_fuente[src] = load_hist(src=src)
        return por_fuente[src]

    out, nuevos = {}, []
    for sym in syms:
        m = measure(sym)
        if m is None:
            continue
        h = hist_de(m.get("chain_src")).get(sym.upper(), {"gross": [], "impact": []})
        bp = percentile(m["gross"], h["gross"])
        ip = percentile(m["impact"], h["impact"])
        # el regimen se lee del flip CONGELADO (feature #6); el vivo es diagnostico
        flip = m["flip_open"] if m["flip_open"] is not None else m["flip_live"]
        ev = evaluate(m["gross"], m["net"], None, m["n_strikes_populated"],
                      m["greeks_ok_pct"], m["spot"], flip,
                      book_pctile=bp, impact_pctile=ip,
                      abs_wall_regime=m["abs_wall_regime"])
        rec = dict(m)
        rec.update(ev)
        rec["book_pctile"] = bp
        rec["impact_pctile"] = ip
        # el percentil se nombra CON SU POBLACION: "historia_polygon" a secas ocultaba de
        # cual de las dos fuentes salia, y son magnitudes distintas.
        rec["pctile_source"] = (f"historia de {m.get('chain_src')} (n={len(h['gross'])})"
                                if bp is not None else
                                f"ausente (n={len(h['gross'])} de {m.get('chain_src')}, "
                                f"hacen falta {HIST_MIN})")
        rec["hhi"] = None if not isinstance(rec.get("hhi"), float) else rec["hhi"]
        out[sym.upper()] = rec
        # el ledger SOLO acumula lo que puede compararse: snapshot completo de Polygon con
        # gamma valida. Mezclar la banda de IBKR con el snapshot completo haria un percentil
        # sobre dos poblaciones distintas.
        if m["gamma_ok"] and str(m["chain_src"] or "").startswith("polygon") and m["gross"]:
            nuevos.append({"sym": sym.upper(), "date": time.strftime("%Y-%m-%d"),
                           "src": m["chain_src"], "gross": m["gross"],
                           "impact": m["impact"], "n_strikes": m["n_strikes_populated"]})
    doc = {"asof": int(time.time()), "asof_local": time.strftime("%Y-%m-%d %H:%M:%S"),
           "generado_por": "scripts/book_quality.py (feature minada #3)"}
    doc.update(out)
    atomic_write(OUT_JSON, json.dumps(doc, indent=1))
    if nuevos:
        hoy = time.strftime("%Y-%m-%d")
        ya = set()
        if os.path.exists(HIST):
            with open(HIST) as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                        ya.add((r.get("sym"), r.get("date"), r.get("src")))
                    except ValueError:
                        pass
        with open(HIST, "a") as f:              # una linea por sym-sesion-fuente, idempotente
            for r in nuevos:
                if (r["sym"], hoy, r["src"]) not in ya:
                    f.write(json.dumps(r) + "\n")
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # sin argumentos: primero los charts ya abiertos (sesion activa); si no hay ninguno,
    # el universo del MAPA (35, `data/universe_gamma.txt`) — nunca una lista vacia silenciosa
    # que dejaria book_quality.json sin escribir sin que nadie se entere.
    syms = (args or sorted({os.path.basename(p)[7:-5]
                            for p in glob.glob("charts/data/levels_*.json")})
            or universe.gamma_universe())
    res = run(syms)
    if "--json" in sys.argv:
        print(json.dumps(res, indent=1))
        return
    orden = {"THIN": 0, "BIFURCATED": 1, "NEAR_FLIP": 2, "STABLE_PIN": 3}
    print(f"{'SYM':7s} {'ETIQUETA':11s} {'coef':>5s} {'strikes':>7s} {'griegas':>7s} "
          f"{'gross':>15s} {'bifur':>6s} {'muro':>8s} fuente")
    for s in sorted(res, key=lambda x: (orden.get(res[x]["book_label"], 9), x)):
        r = res[s]
        gp = "n/d" if r["greeks_ok_pct"] is None else "{:.0%}".format(r["greeks_ok_pct"])
        gr = "n/d" if r["gross"] is None else "{:.4g}".format(r["gross"])
        bf = "n/d" if r["bifurcation"] is None else "{:.2f}".format(r["bifurcation"])
        print(f"{s:7s} {r['book_label']:11s} {r['coef']:5.2f} "
              f"{str(r['n_strikes_populated']):>7s} {gp:>7s} {gr:>15s} {bf:>6s} "
              f"{str(r['abs_wall_kind'] or '-'):>8s} {r['chain_src']}")
    thin = [s for s in res if res[s]["book_label"] == "THIN"]
    print(f"\n-> {OUT_JSON}  ({len(res)} simbolos, {len(thin)} en THIN con coef 0.0)")
    if thin:
        print(f"-> GAMMA MUTEADA (coef 0.0): {' '.join(sorted(thin))}")


if __name__ == "__main__":
    main()
