#!/usr/bin/env python3
"""levels_refresh_daemon.py — EL servicio de refresco continuo del mapa.

Orden Yunior 2026-08-03 07:00: "make sure walls, magnets, gamma flip, gex, vix, get updated
constantly, preferably realtime" + "put conditionals per data provider, remember to have all
generic to avoid deleting code, and modifying preferably just one service file".

QUE REFRESCA (los 5 datos, en UN solo servicio):
  1. muros / imanes / flip / regimen POR SIMBOLO -> charts/data/levels_<sym>.json
     (chart_levels.gen; lo leen compass.cpp:1453, fleet_consensus.cpp:291 con gate de 180 s,
      level_react.cpp:353, truth_lock, em_envelope, pin_clock, ta_view)
  2. el MAPA GAMMA de los 35 del universo -> data/gex_snapshot.json
     (gex_snapshot.build; lo leen daily_fleet_plans, x_*_post, whales_week_map, peer_structure,
      opt_whale_watch, volume_profile.cpp)
  3. VIX + estructura VX -> data/vix.json  (vix_feed, proveedor enrutado)
  4. su propio estado y EDAD -> data/refresh_status.json

EL AGUJERO QUE TAPA (medido 2026-08-03): `data/gex_snapshot.json` solo lo escribian el cron
`com.ibtrader.dailyplans` (04:00) y `print_plans.sh --archive` (16:25). Entre las 09:12 y el
cierre, muros/imanes/flip/GEX NO se refrescaban solos. Recomputado a mano a las 06:58 con la
cadena de ese momento, QQQ pasaba de spot 684,56 / flip 652,62 / net +65,9M a spot 690,78 /
flip 675,79 / net +196,3M: un mapa de 2,8 h ya esta materialmente equivocado.

CADENCIA — se elige por la LATENCIA DE LA FUENTE, no por deseo (docs/LATENCIA-FUENTES.md):
  · `data/opt_chain_<sym>.txt` lo reescribe `provider_bridge` cada ~60 s. Su CONTENIDO es
    Polygon con 15 min de retraso declarado y el OI es el CIERRE DE AYER (killlist #16:
    prohibido derivar nada temporal de un dato congelado).
  · dentro de esa cabecera el `spot` SI es tiempo real (`spot_src finnhub`, `spot_age ~37 s`,
    via data/rt_last_<SYM>.txt). Es lo unico que puede ir rapido, y es lo que mueve el flip
    y la distancia a los muros — por eso los niveles se recalculan CONTRA EL PRINT VIVO.
  · recomputar mas rapido que los ~60 s del escritor de la cadena procesa EXACTAMENTE las
    mismas entradas: no da frescura, quema CPU y finge una edad que el dato no tiene.
  · coste medido: mapa completo de 35 simbolos = 3,6 s; un levels = 0,029 s.

FASES (reloj de Toronto, que es el del Mac) y portero:
  el portero horario `./bin/fleet_hours` manda (dom 20:00 -> vie 20:00). Si NO se le encuentra
  la respuesta es None y este servicio NO trabaja — precedente de la casa: el consumidor que
  no encuentra al portero jamas revive nada a ciegas (fleet_window.py:18-26).
"""
import json
import os
import sys
import time

__file_abs = os.path.abspath(__file__)
REPO = os.path.dirname(os.path.dirname(__file_abs))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import chart_levels
import fleet_window
import gex_core
import gex_snapshot
import rt_last
import vix_feed

FLEET_FILE = os.path.join(REPO, "data", "fleet.txt")
LEVELS_DIR = os.path.join(REPO, "charts", "data")
LOG_FILE = os.path.join(REPO, "logs", "levels_refresh.log")
STATUS_FILE = os.path.join(REPO, "data", "refresh_status.json")

# --- CADENCIA POR FASE (segundos). None = esa tarea no corre en esa fase. -------------------
# Justificacion en la cabecera: el suelo lo pone el escritor de la cadena (~60 s) y el techo
# util lo pone que fuera de RTH nada de eso se mueve.
CADENCIA = {
    "premarket":  {"levels": 120, "gex": 120, "vix": 60},
    "rth":        {"levels": 60,  "gex": 60,  "vix": 60},
    "afterhours": {"levels": 300, "gex": 300, "vix": 300},
    "noche":      {"levels": 600, "gex": 600, "vix": 600},
    "cerrado":    {"levels": None, "gex": None, "vix": None},
}
PHASE_MIN = {"premarket": 4 * 60, "rth": 9 * 60 + 30, "afterhours": 16 * 60, "noche": 20 * 60}
SPOT_MAX_AGE_S = float(os.environ.get("IBT_REFRESH_SPOT_MAX_AGE_S", "120"))
SYM_SLEEP_S = float(os.environ.get("IBT_REFRESH_SYM_SLEEP_S", "0.1"))
TICK_S = 5.0            # granularidad del reloj del servicio


def _cad(fase, tarea):
    v = os.environ.get(f"IBT_REFRESH_{tarea.upper()}_{fase.upper()}_S")
    if v is not None:
        try:
            return None if v.lower() in ("none", "off", "0") else float(v)
        except ValueError:
            pass
    return CADENCIA[fase][tarea]


def log_msg(s):
    msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {s}"
    print(msg, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def fase_ahora(now=None):
    """(fase, motivo). 'cerrado' cuando el portero dice DEAD o NO SE SABE — jamas se asume
    vivo: un falso LIVE hace trabajar al sistema con datos muertos."""
    v = fleet_window.live()
    if v is None:
        return "cerrado", f"portero AUSENTE ({fleet_window.BINARIO})"
    if v is False:
        return "cerrado", (fleet_window.why() or "fuera de la ventana de la flota")
    ts = time.time() if now is None else float(now)
    lt = time.localtime(ts)
    hm = lt.tm_hour * 60 + lt.tm_min
    if lt.tm_wday >= 5:
        return "noche", "fin de semana dentro de la ventana"
    if hm < PHASE_MIN["premarket"]:
        return "noche", "antes de las 04:00"
    if hm < PHASE_MIN["rth"]:
        return "premarket", "04:00-09:30"
    if hm < PHASE_MIN["afterhours"]:
        return "rth", "09:30-16:00"
    if hm < PHASE_MIN["noche"]:
        return "afterhours", "16:00-20:00"
    return "noche", "despues de las 20:00"


def _spot_vivo(sym):
    """(precio, edad_s, fuente) del PRINT en tiempo real, o (None, None, None).

    Es lo UNICO del mapa que puede ir a tiempo real: la cadena y el OI no. Recalcular los
    muros/flip contra el print vivo es lo mismo que ya hace el cockpit
    (chart_bridge.levels_loop:3739 `chart_levels.gen(sym, spot=spot)`)."""
    p = rt_last.fresh(sym, SPOT_MAX_AGE_S)
    if p is None:
        return None, None, None
    return p[0], p[3], p[2]


def refresh_levels(fase):
    """Un barrido de la flota. Devuelve (ok, fallos, edad_max_s)."""
    try:
        fleet = open(FLEET_FILE).read().split()
    except OSError as e:
        log_msg(f"ERROR: {FLEET_FILE}: {e}")
        return 0, 0, None
    if not fleet:
        log_msg("ERROR: data/fleet.txt vacio")
        return 0, 0, None
    cad = _cad(fase, "levels") or 60
    frescura = cad * 0.5          # no se reescribe lo que aun no ha llegado a media cadencia
    ok = fail = 0
    for sym in fleet:
        dst = os.path.join(LEVELS_DIR, f"levels_{sym.lower()}.json")
        if os.path.exists(dst) and (time.time() - os.path.getmtime(dst)) < frescura:
            continue
        px, edad, src = _spot_vivo(sym)
        try:
            r = chart_levels.gen(sym, spot=px, write=True, all_exp=False)
            if r:
                ok += 1
                if px is None:
                    # sin print vivo se usa el spot de la cabecera de la cadena, que tiene su
                    # PROPIA procedencia y edad: se estampa esa, no se deja el hueco en blanco.
                    h = gex_core.parse_chain_header(os.path.join(REPO, "data",
                                                                 f"opt_chain_{sym.lower()}.txt"))
                    src, edad = h.get("spot_src"), h.get("spot_age")
                _stamp_spot(dst, src, edad)
            else:
                fail += 1
                log_msg(f"x {sym}: gen() None (sin cache de cadena?)")
        except Exception as e:
            fail += 1
            log_msg(f"x {sym}: {type(e).__name__}: {e}")
        time.sleep(SYM_SLEEP_S)
    edades = [time.time() - os.path.getmtime(os.path.join(LEVELS_DIR, f"levels_{s.lower()}.json"))
              for s in fleet
              if os.path.exists(os.path.join(LEVELS_DIR, f"levels_{s.lower()}.json"))]
    return ok, fail, (round(max(edades), 1) if edades else None)


def _stamp_spot(dst, src, edad):
    """Deja dicho DE DONDE salio el spot con el que se recalculo el nivel y que edad tenia.
    chart_levels no lo sabe: se lo pasamos nosotros. Si falla, el nivel ya esta escrito y
    correcto — solo se pierde la etiqueta, asi que no se levanta."""
    try:
        with open(dst) as f:
            d = json.load(f)
        d["spot_src"] = src
        d["spot_age_s"] = round(edad, 1) if edad is not None else None
        tmp = f"{dst}.tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, dst)
    except (OSError, ValueError):
        pass


def refresh_gex(fase):
    """El mapa gamma completo. Devuelve (cobertura, chain_age_max_s) o (None, None)."""
    extra = {"refrescado_por": "scripts/levels_refresh_daemon.py",
             "fase": fase, "cadencia_s": _cad(fase, "gex"),
             "cadencia_why": "suelo = ~60 s que tarda provider_bridge en reescribir "
                             "data/opt_chain_<sym>.txt; el contenido es Polygon delayed 15m "
                             "y el OI es el cierre de ayer"}
    d = gex_snapshot.build(meta_extra=extra)
    gex_snapshot.write(d)
    m = d["_meta"]
    return m["cobertura"], m.get("chain_age_max_s")


def refresh_vix():
    """(payload, motivo). None + motivo cuando no se escribio (p.ej. IBKR tiene el fichero)."""
    return vix_feed.refresh()


def write_status(st):
    tmp = f"{STATUS_FILE}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATUS_FILE)


def _edad(path):
    try:
        return round(time.time() - os.path.getmtime(path), 1)
    except OSError:
        return None


def main():
    once = "--once" in sys.argv
    force = "--force-rth" in sys.argv or os.environ.get("IBT_REFRESH_FORCE_PHASE")
    prox = {"levels": 0.0, "gex": 0.0, "vix": 0.0}
    ultimo = {"levels": None, "gex": None, "vix": None}
    detalle = {}
    fase_prev = None
    log_msg(f"arranca refresco continuo (levels + gex_snapshot + vix) | cadencias {CADENCIA}")

    while True:
        if force:
            fase = os.environ.get("IBT_REFRESH_FORCE_PHASE", "rth")
            motivo = "FORZADA por flag/env"
        else:
            fase, motivo = fase_ahora()
        if fase != fase_prev:
            log_msg(f"FASE {fase} ({motivo}) cadencias "
                    f"levels={_cad(fase,'levels')}s gex={_cad(fase,'gex')}s "
                    f"vix={_cad(fase,'vix')}s")
            fase_prev = fase

        ahora = time.time()
        for tarea in ("levels", "gex", "vix"):
            cad = _cad(fase, tarea)
            if cad is None or ahora < prox[tarea]:
                continue
            t0 = time.time()
            try:
                if tarea == "levels":
                    ok, fail, edad_max = refresh_levels(fase)
                    detalle["levels"] = {"ok": ok, "fallos": fail, "edad_max_s": edad_max}
                    if ok or fail:
                        log_msg(f"levels: {ok} ok, {fail} fallos, edad_max {edad_max}s "
                                f"({time.time()-t0:.1f}s)")
                elif tarea == "gex":
                    cob, chage = refresh_gex(fase)
                    detalle["gex"] = {"cobertura": cob, "chain_age_max_s": chage}
                    log_msg(f"gex_snapshot: cobertura {cob}, cadena mas vieja {chage}s "
                            f"({time.time()-t0:.1f}s)")
                else:
                    d, why = refresh_vix()
                    detalle["vix"] = ({"vix": d["vix"], "estado": d["vix_state"],
                                       "data_age_s": d["data_age_s"], "banda": d["band"],
                                       "vx_regime": d.get("vx_regime")} if d
                                      else {"vix": None, "why": why})
                    log_msg(f"vix: {detalle['vix']}")
                ultimo[tarea] = int(time.time())
            except Exception as e:              # fail-loud POR TAREA: una rota no tumba el resto
                log_msg(f"x {tarea}: {type(e).__name__}: {e}")
                detalle[tarea] = {"error": f"{type(e).__name__}: {e}"}
            prox[tarea] = time.time() + cad

        write_status({
            "epoch": int(time.time()),
            "local": time.strftime("%Y-%m-%d %H:%M:%S"),
            "servicio": "scripts/levels_refresh_daemon.py",
            "fase": fase, "fase_why": motivo,
            "cadencia_s": {t: _cad(fase, t) for t in ("levels", "gex", "vix")},
            "ultimo_epoch": ultimo,
            "proximo_en_s": {t: (None if _cad(fase, t) is None
                                 else round(max(0.0, prox[t] - time.time()), 1))
                             for t in ("levels", "gex", "vix")},
            "detalle": detalle,
            "edad_ficheros_s": {
                "data/gex_snapshot.json": _edad(os.path.join(REPO, "data", "gex_snapshot.json")),
                "data/vix.json": _edad(os.path.join(REPO, "data", "vix.json")),
                "charts/data/levels_qqq.json": _edad(os.path.join(LEVELS_DIR, "levels_qqq.json")),
            },
        })

        if once:
            break
        espera = min([p - time.time() for p in prox.values() if p > 0] or [TICK_S])
        time.sleep(max(1.0, min(espera, 60.0)))


if __name__ == "__main__":
    main()
