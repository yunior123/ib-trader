#!/usr/bin/env python3
"""truth_lock.py — OLA 1 feature #9: detector de REPINTADO. Si el PASADO cambia, avisa.

POR QUE EXISTE: warmup_sym() en scripts/ibkr_bar_bridge.py TRUNCA Y REESCRIBE dos dias de
barras 1m cada vez que el bridge arranca, y la calibracion lee esas barras despues. Hoy
nadie sabe que fraccion de nuestro win rate medido se computo sobre datos que luego
cambiaron. Sin esto, CUALQUIER backtest es ficcion: un proveedor que reescribe historia
(ajustes, splits, correcciones del SIP) invalida en silencio todo lo calibrado.

COMO: huella SHA-1 de las ultimas 120 barras CERRADAS por (sym, dia) + la copia de esas
barras. En cada chequeo se recomputa sobre LOS MISMOS epochs:
  - barras añadidas al FINAL          -> normal, NO es alarma (asi crece el fichero)
  - epoch que desaparece              -> reescritura (el warmup trunco) -> MATERIAL
  - o/h/l/c que cambia > 1 tick, o volumen > 1%  -> MATERIAL
  - cambios por debajo del umbral     -> se cuentan como `cosmetic`, sin alarma
El FILTRO DE MATERIALIDAD es obligatorio o esto se vuelve fatiga de alertas y se ignora.

QUE HACE AL DETECTAR: registro (data/truth_lock_events.jsonl + tabla truth_lock_events en
trades.db) + BANNER + una linea INFO en el log de señales. NO HAY VOZ: un backfill benigno
del SIP entrenaria a Yunior a ignorar la sirena, y la sirena es lo unico que preempta.
El sym queda `adjusted=1` (doctrina: NO-TRADE en ese sym hasta re-lock explicito).

LO QUE NO HACE (y por que): no escribe `signals.data_adjusted` ni toca
scripts/calibration_ledger.py — son de otro dueño. La exclusion queda POSIBLE via la tabla
truth_lock_events (sym, first_ep, last_ep) que dice exactamente que ventana esta sucia.
`--audit` ya cuenta cuantas señales de trades.db caen dentro de ventanas marcadas.

Uso:
  ./venv/bin/python scripts/truth_lock.py --check          # una pasada por toda la flota
  ./venv/bin/python scripts/truth_lock.py --loop 30
  ./venv/bin/python scripts/truth_lock.py --status
  ./venv/bin/python scripts/truth_lock.py --audit          # % de señales sobre datos sucios
  ./venv/bin/python scripts/truth_lock.py --relock NVDA    # re-armar tras inspeccionar
  ./venv/bin/python scripts/truth_lock.py --context NVDA   # blob de contexto congelado

SEÑAL-SOLAMENTE: lee barras, escribe registro. Cero red, cero ordenes.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

_OSA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osa_gate")  # portero: respeta data/notify_off

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

BARS_GLOB = os.path.join("data", "bars_*_ibkr.txt")
STATE_PATH = os.path.join("data", "truth_lock.json")
SNAP_DIR = os.path.join("data", "truth_lock_snap")
EVENTS_PATH = os.path.join("data", "truth_lock_events.jsonl")
SIGDIR = os.path.join("data", "trading-signals")
DB = os.path.join(REPO, "data", "trades.db")

WINDOW = 120            # barras cerradas que se congelan
TICK = 0.01             # 1 tick: por debajo de esto un cambio de precio no es material
VOL_TOL = 0.01          # 1% de volumen
EVENT_RETENTION_DAYS = 90


def atomic_write_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_text(path, text):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_line(path, line):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)


# ------------------------------------------------------------------ barras

def parse_bar(ln):
    """'epoch o h l c v' -> tupla o None. None = no es una barra; jamas una barra de ceros."""
    t = ln.split()
    if len(t) < 6:
        return None
    try:
        ep = int(float(t[0]))
        o, h, l, c = (float(t[1]), float(t[2]), float(t[3]), float(t[4]))
        v = float(t[5])
    except ValueError:
        return None
    if ep <= 0 or min(o, h, l, c) <= 0:
        return None
    return (ep, o, h, l, c, v)


def read_bars(path):
    out = []
    try:
        with open(path, errors="replace") as f:
            for ln in f:
                b = parse_bar(ln)
                if b:
                    out.append(b)
    except OSError:
        return None
    out.sort(key=lambda b: b[0])
    return out


def closed_window(bars, now=None):
    """Las ultimas WINDOW barras CERRADAS (se excluye el minuto en curso: aun puede cambiar
    legitimamente y marcarlo seria crying wolf)."""
    now = now or time.time()
    cur_min = int(now // 60) * 60
    closed = [b for b in bars if b[0] < cur_min]
    return closed[-WINDOW:]


def ser(b):
    return "%d|%.4f|%.4f|%.4f|%.4f|%.0f" % b


def sha_of(window):
    h = hashlib.sha1()
    for b in window:
        h.update((ser(b) + "\n").encode())
    return h.hexdigest()


def material_diff(old, new, file_min=None):
    """Compara sobre LOS MISMOS epochs contra TODO el fichero (no contra la ventana nueva:
    la ventana DESLIZA y eso haria pasar por 'desaparecidas' unas barras que siguen en disco
    — falso positivo cazado por el test 2026-07-25).

    Devuelve (materiales, cosmeticos, faltantes, rodadas).
      faltantes = epoch que ESTA dentro del rango del fichero pero ya no existe -> reescritura
      rodadas   = epoch mas viejo que la primera barra del fichero -> retencion normal del
                  bridge (2 dias rodantes), NO es repintado
    """
    old_by = dict((b[0], b) for b in old)
    new_by = dict((b[0], b) for b in new)
    if file_min is None:
        file_min = min(new_by) if new_by else None
    materiales, cosmeticos, faltantes, rodadas = [], [], [], []
    for ep, ob in sorted(old_by.items()):
        nb = new_by.get(ep)
        if nb is None:
            if file_min is not None and ep < file_min:
                rodadas.append(ep)
            else:
                faltantes.append(ep)
            continue
        dp = max(abs(ob[i] - nb[i]) for i in (1, 2, 3, 4))
        dv = abs(ob[5] - nb[5]) / max(ob[5], 1.0)
        if dp > TICK or dv > VOL_TOL:
            materiales.append({"ep": ep, "max_dprice": round(dp, 4), "dvol_pct": round(100 * dv, 2),
                               "old": ser(ob), "new": ser(nb)})
        elif dp > 0 or ob[5] != nb[5]:
            cosmeticos.append(ep)
    return materiales, cosmeticos, faltantes, rodadas


# ------------------------------------------------------------------ estado

def _load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _snap_path(sym):
    return os.path.join(SNAP_DIR, "%s.txt" % sym.lower())


def _read_snap(sym):
    p = _snap_path(sym)
    if not os.path.exists(p):
        return None
    out = []
    with open(p, errors="replace") as f:
        for ln in f:
            t = ln.strip().split("|")
            if len(t) != 6:
                continue
            try:
                out.append((int(t[0]), float(t[1]), float(t[2]), float(t[3]), float(t[4]), float(t[5])))
            except ValueError:
                continue
    return out or None


def _write_snap(sym, window):
    os.makedirs(SNAP_DIR, exist_ok=True)
    atomic_write_text(_snap_path(sym), "".join(ser(b) + "\n" for b in window))


def banner(title, msg):
    """Banner del Mac. Sin sonido y sin voz: esto es visible, no urgente."""
    try:
        subprocess.run([_OSA, "-e",
                        'display notification "%s" with title "%s"' %
                        (msg.replace('"', "'"), title.replace('"', "'"))],
                       timeout=5, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        print("truth_lock: banner fallo (%s)" % e, file=sys.stderr)


def log_signal_line(kind, msg):
    """Linea en el log de señales del dia. `kind` lleva INFO a proposito: signals_db.classify
    lo marca INFO -> voice_queue hace notify_only (banner, cero voz) y notify_relay no manda
    push. Si algun dia esto debe gritar, sera decision de Yunior, no un efecto colateral."""
    try:
        os.makedirs(SIGDIR, exist_ok=True)
        p = os.path.join(SIGDIR, time.strftime("%Y-%m-%d") + ".txt")
        append_line(p, "%s | %s | %s\n" % (time.strftime("%H:%M:%S"), kind, msg))
    except OSError as e:
        print("truth_lock: no pude escribir el log de señales (%s)" % e, file=sys.stderr)


def db_connect():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA busy_timeout=5000")
    return c


def db_init(conn=None):
    """Tabla PROPIA (aditiva). No se toca signals ni voice_log de nadie."""
    c = conn or db_connect()
    c.execute("""CREATE TABLE IF NOT EXISTS truth_lock_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detected_ts INTEGER, sym TEXT, date TEXT,
        first_ep INTEGER, last_ep INTEGER,
        n_material INTEGER, n_missing INTEGER, n_cosmetic INTEGER,
        old_sha TEXT, new_sha TEXT, detail TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_tl_sym ON truth_lock_events(sym, date)")
    c.commit()
    if conn is None:
        c.close()
    return True


def db_record(ev):
    try:
        c = db_connect()
        db_init(c)
        c.execute("""INSERT INTO truth_lock_events(detected_ts, sym, date, first_ep, last_ep,
                     n_material, n_missing, n_cosmetic, old_sha, new_sha, detail)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  (ev["detected_ts"], ev["sym"], ev["date"], ev["first_ep"], ev["last_ep"],
                   ev["n_material"], ev["n_missing"], ev["n_cosmetic"],
                   ev["old_sha"], ev["new_sha"], json.dumps(ev["detail"])[:8000]))
        c.commit()
        c.close()
        return True
    except sqlite3.Error as e:
        # la BD tiene 8 daemons encima: si no se puede escribir, el jsonl ya tiene el evento
        print("truth_lock: sqlite fallo (%s) — el evento esta en %s" % (e, EVENTS_PATH),
              file=sys.stderr)
        return False


# ------------------------------------------------------------------ chequeo

def check(now=None, syms=None, notify=True, bars_glob=None):
    now = now or time.time()
    state = _load_state()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    out = {"ts": int(now), "date": today, "checked": 0, "events": [], "syms": {}}
    for p in sorted(glob.glob(bars_glob or BARS_GLOB)):
        m = re.match(r"^bars_([a-z0-9.]+)_ibkr\.txt$", os.path.basename(p))
        if not m:
            continue
        sym = m.group(1).upper()
        if syms and sym not in syms:
            continue
        bars = read_bars(p)
        if bars is None:
            out["syms"][sym] = {"err": "ilegible"}
            continue
        win = closed_window(bars, now)
        if len(win) < 2:
            out["syms"][sym] = {"skip": "sin barras cerradas suficientes", "n": len(win)}
            continue
        out["checked"] += 1
        st = state.setdefault(sym, {})
        prev = _read_snap(sym)
        new_sha = sha_of(win)
        if prev is None:
            _write_snap(sym, win)
            state[sym] = {"lock_ts": int(now), "bars_sha": new_sha, "n": len(win),
                          "first_ep": win[0][0], "last_ep": win[-1][0],
                          "adjusted": 0, "last_check": int(now),
                          "material_changes_today": 0, "changes_total": 0, "date": today}
            out["syms"][sym] = {"locked": True, "n": len(win), "sha": new_sha[:12]}
            continue
        mat, cos, miss, rolled = material_diff(prev, bars, file_min=bars[0][0])
        if st.get("date") != today:
            st["material_changes_today"] = 0
            st["date"] = today
        st["last_check"] = int(now)
        st["n"] = len(win)
        if not mat and not miss:
            # solo crecio por el final (o cambios sub-umbral): normal
            _write_snap(sym, win)
            st["bars_sha"] = new_sha
            st["lock_ts"] = int(now)
            st["first_ep"], st["last_ep"] = win[0][0], win[-1][0]
            out["syms"][sym] = {"ok": True, "sha": new_sha[:12], "cosmetic": len(cos),
                                "rolled_off": len(rolled),
                                "adjusted": st.get("adjusted", 0)}
            continue
        ev = {"detected_ts": int(now), "sym": sym, "date": today,
              "first_ep": prev[0][0], "last_ep": prev[-1][0],
              "n_material": len(mat), "n_missing": len(miss), "n_cosmetic": len(cos),
              "old_sha": sha_of(prev), "new_sha": new_sha,
              "detail": {"material": mat[:20], "missing": miss[:50], "rolled_off": len(rolled)}}
        append_line(EVENTS_PATH, json.dumps(ev, sort_keys=True) + "\n")
        db_record(ev)
        st["adjusted"] = 1
        st["material_changes_today"] = st.get("material_changes_today", 0) + 1
        st["changes_total"] = st.get("changes_total", 0) + 1
        st["bars_sha"] = new_sha
        st["last_event_ts"] = int(now)
        _write_snap(sym, win)          # la nueva verdad queda congelada, pero adjusted=1
        if notify:
            txt = "%s: PASADO reescrito (%d barras materiales, %d desaparecidas). NO-TRADE hasta re-lock." % (
                sym, len(mat), len(miss))
            banner("🔒 truth-lock", txt)
            log_signal_line("🔒 TRUTH-LOCK INFO", txt)
        out["events"].append(ev)
        out["syms"][sym] = {"adjusted": 1, "material": len(mat), "missing": len(miss)}
    atomic_write_json(STATE_PATH, state)
    return out


def relock(sym):
    """Re-arma un sym tras inspeccion humana. La doctrina exige gesto explicito."""
    state = _load_state()
    hits = [s for s in state if sym.upper() in ("ALL", s)]
    for s in hits:
        state[s]["adjusted"] = 0
        state[s]["relock_ts"] = int(time.time())
    atomic_write_json(STATE_PATH, state)
    return hits


def status():
    state = _load_state()
    dirty = [s for s, v in state.items() if v.get("adjusted")]
    return {"syms": len(state), "adjusted": dirty,
            "events_total": sum(v.get("changes_total", 0) for v in state.values()),
            "state": state}


def audit():
    """El SUBPRODUCTO que justifica la feature aunque la incidencia sea cero: cuantas señales
    medidas cayeron dentro de una ventana que despues cambio."""
    res = {"events": 0, "signals": None, "signals_dirty": None, "pct_dirty": None,
           "nota": "pct_dirty=None significa 'no hay eventos todavia', NO 'cero riesgo'"}
    try:
        c = db_connect()
        db_init(c)
        res["events"] = c.execute("SELECT COUNT(*) FROM truth_lock_events").fetchone()[0]
        res["signals"] = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        if res["events"]:
            n = c.execute("""SELECT COUNT(*) FROM signals s WHERE EXISTS(
                             SELECT 1 FROM truth_lock_events e
                             WHERE e.sym = s.symbol AND s.ts_epoch BETWEEN e.first_ep AND e.last_ep)"""
                          ).fetchone()[0]
            res["signals_dirty"] = n
            res["pct_dirty"] = round(100.0 * n / max(res["signals"], 1), 2)
        c.close()
    except sqlite3.Error as e:
        res["err"] = str(e)
    return res


def prune_events(now=None):
    """Retencion 90 dias: el jsonl se reescribe y la tabla se limpia."""
    now = now or time.time()
    cut = now - EVENT_RETENTION_DAYS * 86400
    n_kept = n_dropped = 0
    if os.path.exists(EVENTS_PATH):
        keep = []
        with open(EVENTS_PATH, errors="replace") as f:
            for ln in f:
                try:
                    if json.loads(ln).get("detected_ts", 0) >= cut:
                        keep.append(ln)
                        n_kept += 1
                    else:
                        n_dropped += 1
                except ValueError:
                    n_dropped += 1
        atomic_write_text(EVENTS_PATH, "".join(keep))
    try:
        c = db_connect()
        db_init(c)
        c.execute("DELETE FROM truth_lock_events WHERE detected_ts < ?", (int(cut),))
        c.commit()
        c.close()
    except sqlite3.Error as e:
        print("truth_lock: prune sqlite fallo (%s)" % e, file=sys.stderr)
    return {"kept": n_kept, "dropped": n_dropped}


def context_blob(sym, now=None):
    """Blob de contexto CONGELADO para que un emisor de señal pueda adjuntarlo (lock_ts +
    bars_sha + spot/NBBO + niveles + regimen + fuerza). Devuelve None en los campos que no
    existen: nunca un 0 plausible."""
    now = now or time.time()
    sl = sym.lower()
    bars = read_bars(os.path.join("data", "bars_%s_ibkr.txt" % sl))
    win = closed_window(bars, now) if bars else []
    nb = na = spot = None
    p = os.path.join("data", "nbbo_%s.txt" % sl)
    if os.path.exists(p):
        try:
            with open(p, errors="replace") as f:
                last = None
                for ln in f:
                    if ln.strip():
                        last = ln
            if last:
                t = last.split()
                if len(t) >= 3:
                    nb, na = float(t[1]), float(t[2])
        except (OSError, ValueError):
            nb = na = None
    lv = None
    lp = os.path.join("charts", "data", "levels_%s.json" % sl)
    if os.path.exists(lp):
        try:
            with open(lp) as f:
                lv = json.load(f)
        except (OSError, ValueError):
            lv = None
    if lv:
        spot = lv.get("spot")
    force = None
    try:
        with open(os.path.join("data", "force.json")) as f:
            force = json.load(f).get(sym.upper())
    except (OSError, ValueError):
        force = None
    return {
        "sym": sym.upper(), "lock_ts": int(now),
        "bars_sha": sha_of(win) if win else None,
        "bars_window": [win[0][0], win[-1][0]] if win else None,
        "spot": spot, "nbbo_bid": nb, "nbbo_ask": na,
        "regime": (lv or {}).get("regime"),
        "levels": {k: (lv or {}).get(k) for k in
                   ("flip", "call_wall", "put_wall", "abs_wall", "abs_wall_kind", "em", "iv_atm")} if lv else None,
        "force": (force or {}).get("force") if force else None,
        "adjusted": _load_state().get(sym.upper(), {}).get("adjusted", 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--loop", type=int, metavar="SEC", nargs="?", const=30)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--relock", metavar="SYM")
    ap.add_argument("--context", metavar="SYM")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--sym", action="append")
    a = ap.parse_args()
    if a.relock:
        print("re-locked: %s" % ", ".join(relock(a.relock)))
        return
    if a.status:
        s = status()
        print("%d syms bajo candado, sucios: %s, eventos totales: %d" %
              (s["syms"], ", ".join(s["adjusted"]) or "ninguno", s["events_total"]))
        return
    if a.audit:
        print(json.dumps(audit(), indent=1))
        return
    if a.context:
        print(json.dumps(context_blob(a.context), indent=1))
        return
    if a.prune:
        print(json.dumps(prune_events(), indent=1))
        return
    if a.loop:
        while True:
            try:
                r = check(syms=a.sym)
                if r["events"]:
                    print("%s: %d REESCRITURAS -> %s" %
                          (time.strftime("%H:%M:%S"), len(r["events"]),
                           ", ".join(e["sym"] for e in r["events"])), flush=True)
            except Exception as e:
                print("truth_lock: FALLO %s" % e, file=sys.stderr, flush=True)
            time.sleep(a.loop)
    r = check(syms=a.sym)
    if a.check and not r["events"]:
        return
    print("chequeados %d syms, %d reescrituras materiales" % (r["checked"], len(r["events"])))
    for s, v in sorted(r["syms"].items()):
        if v.get("adjusted"):
            print("  %s SUCIO: %d materiales, %d desaparecidas" %
                  (s, v.get("material", 0), v.get("missing", 0)))


if __name__ == "__main__":
    main()
