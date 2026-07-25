#!/usr/bin/env python3
"""voice_budget.py — OLA 1 feature #12: PRESUPUESTO DE ALARMAS.

EL RIESGO REAL: la fatiga de alertas es el unico modo de fallo de la lista de 30 features sin
remedio tecnico posterior — deshabilita en silencio el sistema entero. Medido hoy en trades.db:
voice_log tiene 455 filas (219 notify_only INFO, 120 spoke SIGNAL, 89 spoke DANGER, 18
coalesced, 9 preempted) contra 3851 señales; y el roster nuevo añadiria ~14 emisores x 30 syms.

QUE HACE (y que NO):
  - DANGER NUNCA se recorta. Ni una linea de codigo del camino DANGER pasa por aqui: speak.sh
    comprueba la prioridad ANTES de llamar al gate. Es la unica voz que preempta y es lo que
    Yunior oye para operar sin pantalla.
  - INFO tampoco se toca: voice_queue.sh ya no lo vocaliza (notify_only), asi que gatearlo solo
    borraria su fila de registro.
  - SIGNAL SI se raciona: tope diario total (DANGER incluido en la CUENTA, jamas en el recorte),
    tope por hora y, opcional y APAGADO por defecto, cooldown por sym.
  - cada supresion queda registrada con un `action` PROPIO en voice_log: `budget_suppressed`.
    Los de voice_queue.sh (spoke|preempted|notify_only|coalesced|dropped_stale) no se tocan.

FAIL-OPEN POR DISEÑO: el gate solo suprime si sale con codigo 42. Cualquier otro final —
python roto, json corrupto, disco lleno, fichero ausente — deja hablar. Un bug en el
presupuesto JAMAS puede volver muda la flota.

INTERRUPTOR: el gate esta INERTE hasta que exista data/voice_budget_enable. Se enciende con
  touch data/voice_budget_enable      y se apaga borrandolo. Reversible en un gesto.

CONGELACION DE DANGER (punto (a) del doc): data/voice_registry.json congela el numero de
emisores DANGER en el conteo de hoy + 1. Los 7 emisores DANGER reales, verificados uno a uno
en el codigo (2026-07-25): opt_whale_watch.py:33, fleet_consensus.py:124, fleet_consensus.cpp:403,
price_alarm.cpp:231, compass_keepalive.sh:22/40, fleet_keepalive_start.sh:17, tws_watchdog.sh:109/130/146.
`--check-registry` avisa si aparece uno nuevo: un DANGER nuevo debe DESPLAZAR a uno existente.
La comprobacion es una AUDITORIA, no un gate en caliente: para bloquear en caliente cada emisor
tendria que pasar --emitter (soportado, opcional) y eso son ficheros de otros dueños.

Uso:
  ./venv/bin/python scripts/voice_budget.py --init            # crea registry + caps
  ./venv/bin/python scripts/voice_budget.py --publish         # data/voice_budget.json
  ./venv/bin/python scripts/voice_budget.py --status
  ./venv/bin/python scripts/voice_budget.py --check-registry
  ./venv/bin/python scripts/voice_budget.py --flush           # spool de supresiones -> voice_log
  ./venv/bin/python scripts/voice_budget.py --gate SIGNAL --msg "..." [--sym QQQ] [--emitter id]
  ./venv/bin/python scripts/voice_budget.py --record SIGNAL   # contabiliza una locucion encolada

SEÑAL-SOLAMENTE: cuenta voces y escribe registro. Cero red, cero ordenes.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

REGISTRY_PATH = os.path.join("data", "voice_registry.json")
CAPS_PATH = os.path.join("data", "voice_budget_caps.json")
BUDGET_PATH = os.path.join("data", "voice_budget.json")
SPEND_DIR = os.path.join("data", "voice_spend")
SPOOL_PATH = os.path.join("data", "voice_suppressed.jsonl")
ENABLE_PATH = os.path.join("data", "voice_budget_enable")
DB = os.path.join(REPO, "trades.db")

EXIT_SPEAK = 0
EXIT_SUPPRESS = 42          # el UNICO codigo que silencia; todo lo demas habla
SPEND_RETENTION_DAYS = 90

DEFAULT_CAPS = {
    "day_total_cap": 40,        # tope del doc; medido hoy ~21 locuciones/sesion
    "hour_signal_cap": 12,      # ~1 cada 5 min en la hora mas cargada
    "cooldown_sym_sec": 0,      # APAGADO: un cooldown por sym puede tapar una señal nueva de
                                # verdad; el knob existe y lo enciende Yunior, no yo.
    "gated_classes": ["SIGNAL"],   # DANGER jamas; INFO no se vocaliza
    "nota": "DANGER cuenta para el total pero NUNCA se suprime. Cambiar aqui, no en el codigo.",
}

# Emisores DANGER verificados en el codigo el 2026-07-25 (fichero:linea comprobados)
DANGER_EMITTERS = {
    "whale_espada": {"module": "scripts/opt_whale_watch.py:33", "class": "DANGER",
                     "calib_cell": "whale/flow", "enabled": True},
    "manada_py": {"module": "scripts/fleet_consensus.py:124", "class": "DANGER",
                  "calib_cell": "consenso", "enabled": True},
    "manada_cpp": {"module": "scripts/fleet_consensus.cpp:403", "class": "DANGER",
                   "calib_cell": "consenso", "enabled": True},
    "price_alarm": {"module": "scripts/price_alarm.cpp:231", "class": "DANGER",
                    "calib_cell": "nivel_impreso", "enabled": True},
    "compass_caida": {"module": "scripts/compass_keepalive.sh:22,40", "class": "DANGER",
                      "calib_cell": "salud", "enabled": True},
    "permisos_flota": {"module": "scripts/fleet_keepalive_start.sh:17", "class": "DANGER",
                       "calib_cell": "salud", "enabled": True},
    "tws_zombie": {"module": "scripts/tws_watchdog.sh:109,130,146", "class": "DANGER",
                   "calib_cell": "salud", "enabled": True},
}


def atomic_write_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_line(path, line):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def caps():
    c = dict(DEFAULT_CAPS)
    c.update(_load_json(CAPS_PATH, {}))
    return c


def registry():
    return _load_json(REGISTRY_PATH, {})


def init(now=None):
    now = now or time.time()
    reg = registry()
    if not reg:
        reg = {"frozen_at": int(now),
               "danger_frozen_limit": len(DANGER_EMITTERS) + 1,
               "nota": "el conteo de emisores DANGER esta CONGELADO en el de hoy + 1: un DANGER "
                       "nuevo debe DESPLAZAR a uno existente (regla del doc #12).",
               "emitters": dict(DANGER_EMITTERS)}
        atomic_write_json(REGISTRY_PATH, reg)
    if not os.path.exists(CAPS_PATH):
        atomic_write_json(CAPS_PATH, DEFAULT_CAPS)
    os.makedirs(SPEND_DIR, exist_ok=True)
    return {"registry": REGISTRY_PATH, "caps": CAPS_PATH,
            "danger_frozen_limit": reg["danger_frozen_limit"],
            "enabled": os.path.exists(ENABLE_PATH)}


# ------------------------------------------------------------------ gasto

def spend_path(now=None):
    now = now or time.time()
    return os.path.join(SPEND_DIR, time.strftime("%Y-%m-%d", time.localtime(now)) + ".txt")


def record(prio, sym=None, emitter=None, now=None):
    """Contabiliza UNA locucion encolada. Lo llama speak.sh DESPUES de encolar, para que la
    contabilidad no pueda retrasar ni bloquear una voz."""
    now = now or time.time()
    os.makedirs(SPEND_DIR, exist_ok=True)
    append_line(spend_path(now), "%d %s %s %s\n" %
                (int(now), prio, sym or "-", emitter or "-"))
    return True


def read_spend(now=None):
    now = now or time.time()
    p = spend_path(now)
    rows = []
    if not os.path.exists(p):
        return rows
    with open(p, errors="replace") as f:
        for ln in f:
            t = ln.split()
            if len(t) < 2:
                continue
            try:
                rows.append((int(float(t[0])), t[1], t[2] if len(t) > 2 else "-",
                             t[3] if len(t) > 3 else "-"))
            except ValueError:
                continue
    return rows


def counters(now=None):
    now = now or time.time()
    rows = read_spend(now)
    hour = time.strftime("%H", time.localtime(now))
    per_prio = {}
    per_hour = {}
    last_by_sym = {}
    for ts, prio, sym, _em in rows:
        per_prio[prio] = per_prio.get(prio, 0) + 1
        h = time.strftime("%H", time.localtime(ts))
        per_hour.setdefault(h, {})
        per_hour[h][prio] = per_hour[h].get(prio, 0) + 1
        if sym and sym != "-":
            last_by_sym[sym] = max(last_by_sym.get(sym, 0), ts)
    return {"total": len(rows), "per_prio": per_prio, "per_hour": per_hour,
            "hour": hour, "signal_this_hour": per_hour.get(hour, {}).get("SIGNAL", 0),
            "last_by_sym": last_by_sym}


# ------------------------------------------------------------------ gate

def decide(prio, sym=None, emitter=None, now=None, force_enabled=None):
    """(allow: bool, reason: str|None, counters). LA MISMA logica que usa el gate del shell:
    una sola implementacion, sin duplicar reglas en bash."""
    now = now or time.time()
    prio = (prio or "").upper()
    c = caps()
    enabled = os.path.exists(ENABLE_PATH) if force_enabled is None else force_enabled
    cnt = counters(now)
    if prio == "DANGER":
        return True, "danger_nunca_se_recorta", cnt
    if not enabled:
        return True, "presupuesto_apagado", cnt
    if prio not in c.get("gated_classes", ["SIGNAL"]):
        return True, "clase_no_gateada", cnt
    reg = registry().get("emitters", {})
    if emitter and emitter in reg and not reg[emitter].get("enabled", True):
        return False, "emitter_disabled", cnt
    if cnt["total"] >= c["day_total_cap"]:
        return False, "day_cap %d" % c["day_total_cap"], cnt
    if cnt["signal_this_hour"] >= c["hour_signal_cap"]:
        return False, "hour_cap %d" % c["hour_signal_cap"], cnt
    cd = c.get("cooldown_sym_sec", 0)
    if cd and sym and sym in cnt["last_by_sym"] and (now - cnt["last_by_sym"][sym]) < cd:
        return False, "cooldown_sym %ds" % cd, cnt
    return True, None, cnt


def log_suppression(prio, msg, reason, sym=None, emitter=None, now=None):
    """Spool inmediato (durable) + intento de insertar en voice_log con action PROPIO.
    Si sqlite esta ocupada, el spool guarda la fila y --flush la mete despues: CERO
    supresiones silenciosas."""
    now = now or time.time()
    ev = {"ts": int(now), "action": "budget_suppressed", "priority": prio,
          "reason": reason, "sym": sym, "emitter": emitter, "msg": (msg or "")[:400]}
    append_line(SPOOL_PATH, json.dumps(ev, sort_keys=True) + "\n")
    if _db_insert([ev], timeout=1.0):
        # el puntero avanza una linea: sin esto --flush reinsertaria la misma supresion
        # (duplicado cazado por el test 2026-07-25)
        _ptr_write(min(_ptr_read() + 1, _spool_len()))
    return ev


def _ptr_path():
    return SPOOL_PATH + ".ptr"


def _ptr_read():
    try:
        with open(_ptr_path()) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _ptr_write(n):
    tmp = _ptr_path() + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(int(n)))
    os.replace(tmp, _ptr_path())


def _spool_len():
    if not os.path.exists(SPOOL_PATH):
        return 0
    with open(SPOOL_PATH, errors="replace") as f:
        return sum(1 for _ in f)


def _db_insert(evs, timeout=5.0):
    """Inserta en voice_log. Devuelve cuantas filas entraron (0 si la BD esta ocupada)."""
    try:
        c = sqlite3.connect(DB, timeout=timeout)
        c.execute("PRAGMA busy_timeout=%d" % int(timeout * 1000))
        c.execute("""CREATE TABLE IF NOT EXISTS voice_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_epoch REAL, action TEXT, priority TEXT, msg TEXT)""")
        n = 0
        for ev in evs:
            c.execute("INSERT INTO voice_log(ts_epoch, action, priority, msg) VALUES(?,?,?,?)",
                      (ev["ts"], ev["action"], ev["priority"],
                       "[%s] %s" % (ev["reason"], ev["msg"])))
            n += 1
        c.commit()
        c.close()
        return n
    except sqlite3.Error:
        return 0


def flush(now=None):
    """Mete en voice_log lo que el spool tenga sin insertar (marca con un puntero)."""
    now = now or time.time()
    if not os.path.exists(SPOOL_PATH):
        return {"pending": 0, "inserted": 0}
    ptr = _ptr_read()
    evs = []
    with open(SPOOL_PATH, errors="replace") as f:
        for i, ln in enumerate(f):
            if i < ptr:
                continue
            try:
                evs.append(json.loads(ln))
            except ValueError:
                continue
    if not evs:
        return {"pending": 0, "inserted": 0}
    n = _db_insert(evs)
    if n:
        _ptr_write(ptr + len(evs))
    return {"pending": len(evs), "inserted": n}


# ------------------------------------------------------------------ publicacion

def db_counts(date=None):
    """Lo que voice_queue.sh registro de verdad (para reconciliar contra lo encolado)."""
    date = date or time.strftime("%Y-%m-%d")
    out = {}
    try:
        c = sqlite3.connect(DB, timeout=5)
        c.execute("PRAGMA busy_timeout=3000")
        for action, prio, n in c.execute(
                "SELECT action, priority, COUNT(*) FROM voice_log "
                "WHERE date(ts_epoch,'unixepoch','localtime')=? GROUP BY 1,2", (date,)):
            out["%s/%s" % (action, prio)] = n
        c.close()
    except sqlite3.Error as e:
        return {"err": str(e)}
    return out


def publish(now=None):
    now = now or time.time()
    c = caps()
    cnt = counters(now)
    reg = registry()
    date = time.strftime("%Y-%m-%d", time.localtime(now))
    sup = {"total": 0, "by_reason": {}}
    if os.path.exists(SPOOL_PATH):
        with open(SPOOL_PATH, errors="replace") as f:
            for ln in f:
                try:
                    ev = json.loads(ln)
                except ValueError:
                    continue
                if time.strftime("%Y-%m-%d", time.localtime(ev.get("ts", 0))) != date:
                    continue
                sup["total"] += 1
                r = str(ev.get("reason"))
                sup["by_reason"][r] = sup["by_reason"].get(r, 0) + 1
    out = {
        "date": date,
        "updated": int(now),
        "enabled": os.path.exists(ENABLE_PATH),
        "caps": c,
        "spent": cnt["per_prio"],
        "spent_total": cnt["total"],
        "per_hour": cnt["per_hour"],
        "signal_this_hour": cnt["signal_this_hour"],
        "suppressed": sup,
        "danger": {"frozen_limit": reg.get("danger_frozen_limit"),
                   "registered": sum(1 for e in reg.get("emitters", {}).values()
                                     if e.get("class") == "DANGER"),
                   "never_suppressed": True},
        "voice_log_today": db_counts(date),
        "nota": "spent = locuciones ENCOLADAS por speak.sh; voice_log_today = lo que el daemon "
                "hablo de verdad. La diferencia es informacion, no un error.",
    }
    atomic_write_json(BUDGET_PATH, out)
    prune_spend(now)
    return out


def prune_spend(now=None):
    now = now or time.time()
    cut = now - SPEND_RETENTION_DAYS * 86400
    n = 0
    if not os.path.isdir(SPEND_DIR):
        return 0
    for fn in sorted(os.listdir(SPEND_DIR)):
        p = os.path.join(SPEND_DIR, fn)
        try:
            if os.path.getmtime(p) < cut:
                os.unlink(p)
                n += 1
        except OSError:
            pass
    return n


def check_registry():
    """Auditoria de la congelacion: ¿hay emisores DANGER nuevos en el codigo?"""
    reg = registry()
    limit = reg.get("danger_frozen_limit") or (len(DANGER_EMITTERS) + 1)
    found = {}
    try:
        out = subprocess.run(
            ["grep", "-rn", "-e", "speak.sh.*DANGER", "-e", "DANGER.*speak.sh",
             "scripts"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return {"err": str(e)}
    for ln in out.splitlines():
        if ln.startswith("scripts/speak.sh") or ln.startswith("scripts/voice_budget.py"):
            continue
        f = ln.split(":")[0]
        found[f] = found.get(f, 0) + 1
    known = set()
    for e in reg.get("emitters", {}).values():
        known.add(e.get("module", "").split(":")[0])
    new = sorted(f for f in found if f not in known)
    return {"danger_frozen_limit": limit,
            "registered": len(known),
            "files_with_danger": found,
            "nuevos_sin_registrar": new,
            "veredicto": "OK" if not new else
                         "DANGER NUEVO SIN RETIRADA: %s" % ", ".join(new)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--check-registry", action="store_true")
    ap.add_argument("--flush", action="store_true")
    ap.add_argument("--gate", metavar="PRIO")
    ap.add_argument("--record", metavar="PRIO")
    ap.add_argument("--msg", default="")
    ap.add_argument("--sym")
    ap.add_argument("--emitter")
    a = ap.parse_args()

    if a.gate:
        # NUNCA levanta: cualquier fallo interno = HABLAR (fail-open)
        try:
            allow, reason, _cnt = decide(a.gate, sym=a.sym, emitter=a.emitter)
            if allow:
                # NO contabiliza aqui: la contabilidad la hace speak.sh DESPUES de encolar,
                # para que exista un unico punto de conteo (y para que DANGER, que no pasa
                # por el gate, tambien cuente).
                sys.exit(EXIT_SPEAK)
            log_suppression(a.gate.upper(), a.msg, reason, sym=a.sym, emitter=a.emitter)
            print("SUPPRESS %s" % reason)
            sys.exit(EXIT_SUPPRESS)
        except Exception as e:                      # noqa: BLE001 — fail-open a proposito
            print("voice_budget gate FALLO (%s): se deja hablar" % e, file=sys.stderr)
            sys.exit(EXIT_SPEAK)
    if a.record:
        record(a.record.upper(), sym=a.sym, emitter=a.emitter)
        return
    if a.init:
        print(json.dumps(init(), indent=1))
        return
    if a.flush:
        print(json.dumps(flush(), indent=1))
        return
    if getattr(a, "check_registry"):
        print(json.dumps(check_registry(), indent=1))
        return
    if a.publish or a.status:
        b = publish()
        if a.status:
            print("presupuesto %s | %s | encoladas %d/%d (SIGNAL esta hora %d/%d) | "
                  "suprimidas %d | DANGER registrados %d/%d, jamas suprimidos" % (
                      b["date"], "ACTIVO" if b["enabled"] else "APAGADO (inerte)",
                      b["spent_total"], b["caps"]["day_total_cap"],
                      b["signal_this_hour"], b["caps"]["hour_signal_cap"],
                      b["suppressed"]["total"], b["danger"]["registered"],
                      b["danger"]["frozen_limit"]))
        else:
            print(json.dumps(b, indent=1))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
