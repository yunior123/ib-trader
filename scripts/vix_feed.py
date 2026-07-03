#!/usr/bin/env python3
"""vix_feed.py — el VIX y la estructura VX, con proveedor ENRUTADO y edad declarada.

POR QUE EXISTE (medido 2026-08-03 07:0x): el cockpit mostraba "VIX —" en las 6 ventanas.
El unico camino del VIX era `chart_bridge.py:3936` -> `Index("VIX","CBOE")` por TWS, y esa
suscripcion devuelve **Error 354 "Requested market data is not subscribed"**
(`charts/chart_live.log:15`). Con `state._vix = None` el puente no mete `lv["vix"]` en el
frame, `live.html:1433` no pinta nada y `data/vix.json` se quedo en 15.99 del 2026-07-31
16:45 -> `compass.cpp:1484` (VIX_MAX_AGE 90 s) lo tira -> los 31 `compass_*.json` con
`vix_context: null`. Un solo proveedor caido = el dato desaparece del sistema entero.

ENRUTADO POR PROVEEDOR, NADA SE BORRA (orden Yunior 2026-08-03: "code for ibkr stays, do not
delete it... put conditionals per data provider, remember to have all generic"). El camino
IBKR sigue INTACTO en chart_bridge.py; aqui solo se declara como proveedor de prioridad 0 y
se le CEDE el fichero cuando esta escribiendo. Mismo patron que
`provider_bridge.PROVEEDORES` (scripts/provider_bridge.py:227): la tabla es el unico punto
de decision; añadir proveedor = tocar la tabla, jamas un consumidor.

CONTRATO `data/vix.json` (superset compatible con lo que ya leen compass.cpp y live.html):
    vix, vix_live, ts          <- lo que ya existia (ts = epoch de ESTA escritura)
    vix_state                  <- "live" | "delayed" | "close"  (la tri-estado honesta)
    provider, src, latencia    <- procedencia
    quote_ts, quote_local, data_age_s   <- EDAD REAL del numero, no del fichero
    band                       <- CALM/ELEVADO/ALTO (misma particion que compass.cpp:101)
    vx1, vx2, vx_b1, vx_b2, vx_regime, vx (lista), vx_mixed_clock

REGLA DE LA CASA: si no se puede medir, `None` y motivo. Jamas un VIX plausible.
"""
import json
import os
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "vix.json")
MARKET_SOURCE = os.path.join(REPO, "data", "market_source.txt")

UA = {"User-Agent": "Mozilla/5.0"}
HTTP_TIMEOUT = float(os.environ.get("IBT_VIX_HTTP_TIMEOUT", "10"))
# un tick de menos de esto es "vivo"; por encima, delayed. El VIX de CBOE llega con ~15 min,
# asi que con este proveedor `vix_live` sale 0 SIEMPRE — y eso es la verdad, no un fallo.
LIVE_MAX_AGE_S = float(os.environ.get("IBT_VIX_LIVE_MAX_AGE_S", "120"))
# el fichero que escribe chart_bridge por TWS manda mientras siga fresco
IBKR_OWN_MAX_AGE_S = float(os.environ.get("IBT_VIX_IBKR_OWN_MAX_AGE_S", "180"))
VX_MIN_OI = int(os.environ.get("IBT_VX_MIN_OI", "1000"))   # ver vx_term(): settlement clonado

# ------------------- ENRUTADO: EL UNICO PUNTO DE DECISION -------------------
# prio: menor manda a igualdad de frescura. 'latencia' MEDIDA, no de la documentacion.
PROVEEDORES = {
    "ibkr": {"caps": ["vix"], "latencia": "tiempo_real", "prio": 0,
             "activo_si": "market_source==ibkr y chart_bridge escribiendo data/vix.json",
             "escribe": "scripts/chart_bridge.py:3772 persist_vix()",
             "nota": "OFF esta semana (orden Yunior 2026-08-02) y sin entitlement CBOE "
                     "Global Indexes en TWS: error 354. Codigo intacto."},
    "cboe": {"caps": ["vix", "vx_term"], "latencia": "delayed_15m", "prio": 9,
             "activo_si": "siempre (CDN publico, sin key)",
             "escribe": "este fichero",
             "nota": "cdn.cboe.com/api/global/delayed_quotes; la edad REAL la declara "
                     "last_trade_time, no el reloj de la peticion"},
}

CBOE_VIX = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"
CBOE_VX = "https://www-api.cboe.com/us/futures/api/data/?symbol=VX"


def band(v):
    """CALM <16 / ELEVADO 16-24 / ALTO >24 — la MISMA particion que compass.cpp:101."""
    if v is None:
        return None
    return "CALM" if v < 16.0 else ("ELEVADO" if v <= 24.0 else "ALTO")


def _get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read())


def _epoch_of(iso_et):
    """'2026-07-31T16:15:01' (hora de Nueva York, que es la del Mac) -> epoch, o None."""
    if not iso_et:
        return None
    try:
        return time.mktime(time.strptime(iso_et[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def market_source():
    try:
        with open(MARKET_SOURCE) as f:
            return f.read().strip().lower()
    except OSError:
        return None


# ------------------------------- proveedores -------------------------------

def from_cboe():
    """(vix, quote_epoch, prev_close) del CDN publico, o None. Nunca un numero inventado."""
    d = _get_json(CBOE_VIX)
    data = (d or {}).get("data") or {}
    px = data.get("current_price")
    if not isinstance(px, (int, float)) or px <= 0:
        return None
    return float(px), _epoch_of(data.get("last_trade_time")), data.get("prev_day_close")


def vx_term():
    """Estructura temporal VX: solo contratos CON VIDA. Devuelve (lista, None) o (None, motivo).

    El filtro de liquidez NO es cosmetico: CBOE sirve los semanales muertos con
    `settlement` CLONADO del monthly (medido 2026-08-03 07:1x: VX31/Q6 OI 0 y VX32/Q6 OI 10,
    los dos con settlement 18,1046 = el del VX/Q6 y last_price 0). Ordenar por vencimiento y
    coger los tres primeros — que es lo que hace `daily_fleet_plans.vx_term():311` — mete esos
    dos delante del front real y da b1 +13,4% cuando el front que cotiza da +12,3%.
    Regla: entra el que ha COTIZADO (last>0); el settlement solo vale si el contrato tiene un
    libro de verdad detras (OI >= VX_MIN_OI).
    """
    d = _get_json(CBOE_VX)
    rows = (d or {}).get("data") or []
    out = []
    for r in rows:
        oi = r.get("prev_open_int") or 0
        vol = r.get("volume") or 0
        last = r.get("last_price") or 0
        sett = r.get("settlement") or 0
        if last > 0:
            px = last
        elif oi >= VX_MIN_OI and sett > 0:
            px = sett
        else:
            continue                       # contrato fantasma: no describe ningun libro
        if not px or px <= 0:
            continue
        out.append({"sym": r.get("symbol"), "exp": r.get("expiration"), "px": round(px, 4),
                    "px_src": "last" if last > 0 else "settlement",
                    "oi": oi, "vol": vol})
    if len(out) < 2:
        return None, f"solo {len(out)} contratos VX con OI/volumen: sin estructura"
    out.sort(key=lambda x: time.strptime(x["exp"], "%m/%d/%Y"))
    return out, None


def _ibkr_owns():
    """True si el camino IBKR esta VIVO y escribiendo data/vix.json — entonces se le cede.

    Se reconoce por AUSENCIA de `provider` (chart_bridge.persist_vix escribe solo
    {vix, vix_live, ts}) y por frescura. Sin esto, el refresco por CBOE pisaria un tick
    de TWS en tiempo real con un numero de hace 15 min: exactamente al reves de la regla 4.
    """
    if market_source() != "ibkr":
        return False
    try:
        with open(OUT) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(d, dict) or d.get("provider"):
        return False
    ts = d.get("ts")
    return isinstance(ts, (int, float)) and (time.time() - ts) <= IBKR_OWN_MAX_AGE_S


# --------------------------------- resolve ---------------------------------

def resolve():
    """El payload de `data/vix.json`, o (None, motivo). UNICO punto de decision de proveedor."""
    if _ibkr_owns():
        return None, "cede a ibkr: chart_bridge esta escribiendo data/vix.json en tiempo real"

    prov, err = "cboe", None
    try:
        got = from_cboe()
    except Exception as e:                      # fail-loud: se dice cual y por que
        return None, f"cboe VIX: {type(e).__name__}: {e}"
    if got is None:
        return None, "cboe VIX: current_price ausente o <=0"
    vix, q_ts, prev = got

    now = time.time()
    age = round(now - q_ts, 1) if q_ts else None
    if age is None:
        state, live = "desconocido", 0
    elif age <= LIVE_MAX_AGE_S:
        state, live = "live", 1
    elif time.strftime("%Y%m%d", time.localtime(q_ts)) == time.strftime("%Y%m%d",
                                                                       time.localtime(now)):
        state, live = "delayed", 0             # tick de HOY pero con retraso declarado
    else:
        state, live = "close", 0               # sesion anterior: es el CIERRE, y se dice

    vx, vx_why = None, None
    try:
        vx, vx_why = vx_term()
    except Exception as e:
        vx, vx_why = None, f"{type(e).__name__}: {e}"

    d = {
        "vix": round(vix, 2),
        "vix_live": live,                      # 0/1: lo que ya leia compass.cpp:1486
        "ts": int(now),                        # edad del FICHERO (gate de 90 s de compass)
        "vix_state": state,                    # live | delayed | close | desconocido
        "provider": prov,
        "src": f"{prov}_cdn_delayed_quotes",
        "latencia": PROVEEDORES[prov]["latencia"],
        "quote_ts": int(q_ts) if q_ts else None,
        "quote_local": (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(q_ts))
                        if q_ts else None),
        "data_age_s": age,                     # edad del NUMERO, que no es la del fichero
        "band": band(vix),
        "prev_close": prev,
        "why": err,
    }
    if vx:
        v1, v2 = vx[0]["px"], vx[1]["px"]
        d.update({
            "vx": vx[:4], "vx1": v1, "vx2": v2,
            "vx1_sym": vx[0]["sym"], "vx2_sym": vx[1]["sym"],
            "vx_b1": round((v1 - vix) / vix * 100, 2),
            "vx_b2": round((v2 - v1) / v1 * 100, 2),
            "vx_regime": ("BACKWARDATION" if (v1 - vix) / vix * 100 < -1 else
                          "FLAT" if (v1 - vix) / vix * 100 < 1.5 else "CONTANGO"),
            # los futuros VX cotizan casi 24 h y el INDICE no: comparar un VX de ahora con un
            # VIX del cierre del viernes infla el contango. Se marca, no se esconde.
            "vx_mixed_clock": bool(state == "close"),
        })
    else:
        d["vx_why"] = vx_why
    return d, None


def write(d, path=OUT):
    """Escritura ATOMICA: compass.cpp lee este fichero en su bucle de 0,25 s."""
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, path)
    return path


def refresh():
    """(payload, motivo). Resuelve y escribe. `payload=None` => NO se escribio nada."""
    d, why = resolve()
    if d is None:
        return None, why
    write(d)
    return d, None


def _cli():
    d, why = resolve()
    if d is None:
        print(f"SIN VIX: {why}")
        raise SystemExit(1)
    if "--dry-run" not in sys.argv:
        print(f"escrito {write(d)}")
    print(f"VIX {d['vix']:.2f} {d['band']}  estado={d['vix_state']} "
          f"(dato de {d['quote_local']}, edad {d['data_age_s']:.0f}s, {d['latencia']})")
    if d.get("vx1"):
        print(f"  VX1 {d['vx1']:.2f} ({d['vx1_sym']})  VX2 {d['vx2']:.2f} ({d['vx2_sym']})  "
              f"b1 {d['vx_b1']:+.1f}%  b2 {d['vx_b2']:+.1f}%  {d['vx_regime']}"
              + ("  [RELOJES MEZCLADOS: indice cerrado]" if d.get("vx_mixed_clock") else ""))
    else:
        print(f"  sin estructura VX: {d.get('vx_why')}")


if __name__ == "__main__":
    _cli()
