#!/usr/bin/env python3
"""levels_5min_archive.py — OLA 1 feature #18: densifica el archivo de niveles de
1 foto al dia a 1 foto cada 5 minutos. ES EL HABILITADOR de todo lo demas: sin los
niveles A LA HORA DEL EVENTO no se puede reconstruir que veia el sistema, y por eso
`stability-10` se MATO en vez de degradarse (sus features no existian en tiempo de etiqueta).

QUE HABIA: data/history/<fecha>/levels.json — UN snapshot al dia (lo escribe
daily_archive.py a las 16:10 desde las cadenas). Inutil para etiquetar eventos intradia.

QUE HACE ESTO: cada 5 min COPIA lo que ya se escribe, sin tocar el generador.
  data/history/<fecha>/levels_<sym>_HHMM.json   copia literal de charts/data/levels_<sym>.json
  data/history/<fecha>/levels_5m.jsonl          1 linea por (slot, sym) con asof + age_s + todo

  NO SE TOCA scripts/chart_levels.py NI scripts/chart_bridge.py (otro agente los tiene y
  chart_bridge es un daemon vivo en una caja de 8 GB que ya swapea). Proceso cron aparte:
  es exactamente la valvula de escape que el doc #18 exige si el test de coste falla —
  aqui no hace falta ni medirlo porque el daemon no se toca (coste 0 MB RSS, 0 ms/loop).

  age_s ES OBLIGATORIO: si el generador se queda atascado, esto seguiria copiando el mismo
  fichero 78 veces y eso PARECERIA densidad. Con asof/age_s en cada linea la rancidez es
  auditable y `stale_slots` sale en el health. Nunca se inventa un nivel: si el fichero no
  existe o esta vacio, ese sym no tiene linea (y se cuenta como hueco).

TAMAÑO MEDIDO (2026-07-25): los 26 charts/data/levels_*.json ocupan 51,2 KB en total
  => 78 slots de sesion x 51,2 KB = ~4,0 MB/dia de copias + ~0,7 MB/dia de jsonl.
  RETENCION: dia 0-1 copias sueltas intactas; dia >=2 se PLIEGAN al jsonl del dia
  (verificado por paridad de lineas) y se borran las sueltas -> queda 1 fichero
  levels_5m.jsonl.gz por dia, ~0,5 MB. Se guarda INDEFINIDO: el doc decia 90 dias
  "luego colapso en gex_snap" y gex_snap NO EXISTE, asi que borrarlo seria tirar la unica
  copia del habilitador que necesita >=40 sesiones para servir. 0,5 MB/dia = 180 MB/año.
  Guarda dura: si data/history pasa de 3 GB la retencion aborta y grita.
  (Las sueltas NO se gzipean una a una a proposito: 2028 ficheros de ~2 KB pagarian 8 MB
  de bloques de 4 KB — mas que el propio dato.)

Uso:
  ./venv/bin/python scripts/levels_5min_archive.py --once                 # una pasada
  ./venv/bin/python scripts/levels_5min_archive.py --once --session-only  # no-op fuera de RTH (cron)
  ./venv/bin/python scripts/levels_5min_archive.py --loop 300             # bucle propio
  ./venv/bin/python scripts/levels_5min_archive.py --verify --date 2026-07-25
  ./venv/bin/python scripts/levels_5min_archive.py --retention [--apply]

SEÑAL-SOLAMENTE: solo copia ficheros. Cero red, cero ordenes, cero escritura en lo vivo.
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

SRC_GLOB = os.path.join("charts", "data", "levels_*.json")
HIST = os.path.join("data", "history")
STATE_PATH = os.path.join("data", "levels5m_state.json")
HEALTH_PATH = os.path.join("data", "levels5m_health.json")
JSONL_NAME = "levels_5m.jsonl"

SLOT_SEC = 300
SESSION_START = (9, 25)        # un slot antes de la apertura (09:30)
SESSION_END = (16, 10)         # un slot despues del cierre (16:00)
STALE_WARN_S = 900             # asof mas viejo que esto = el generador esta atascado
HISTORY_BUDGET_GB = 3.0
LOOSE_DAYS = 2


def atomic_write_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_bytes(path, data):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_line(path, line):
    """Append O_APPEND de una sola escritura: un lector jamas ve media linea."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)


def slot_of(epoch):
    return int(epoch // SLOT_SEC) * SLOT_SEC


def in_session(epoch):
    lt = time.localtime(epoch)
    if lt.tm_wday >= 5:
        return False
    mins = lt.tm_hour * 60 + lt.tm_min
    return (SESSION_START[0] * 60 + SESSION_START[1]) <= mins <= (SESSION_END[0] * 60 + SESSION_END[1])


def _load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def snapshot(now=None, session_only=False, src_glob=None, hist=None):
    """Una pasada. Devuelve el dict de salud de la pasada. Idempotente por (slot, sym)."""
    now = now or time.time()
    if session_only and not in_session(now):
        return {"skipped": "fuera_de_sesion", "ts": int(now)}
    hist = hist or HIST
    slot = slot_of(now)
    date = time.strftime("%Y-%m-%d", time.localtime(slot))
    hhmm = time.strftime("%H%M", time.localtime(slot))
    day_dir = os.path.join(hist, date)
    os.makedirs(day_dir, exist_ok=True)
    jsonl = os.path.join(day_dir, JSONL_NAME)

    state = _load_state()
    if state.get("date") != date:
        state = {"date": date, "slots": {}}
    done = state["slots"].setdefault(str(slot), [])

    written, skipped, stale, unreadable = [], [], [], []
    for src in sorted(glob.glob(src_glob or SRC_GLOB)):
        base = os.path.basename(src)
        m = re.match(r"^levels_([a-z0-9.]+)\.json$", base)
        if not m:
            continue
        sym = m.group(1).upper()
        try:
            with open(src, "rb") as f:
                blob = f.read()
            if not blob.strip():
                raise ValueError("vacio")
            obj = json.loads(blob.decode())
        except (OSError, ValueError) as e:
            unreadable.append({"sym": sym, "err": str(e)})
            continue
        if sym in done:
            skipped.append(sym)                       # idempotencia: este slot ya se archivo
            continue
        asof = obj.get("asof")
        age = (slot - float(asof)) if isinstance(asof, (int, float)) else None
        if age is not None and age > STALE_WARN_S:
            stale.append({"sym": sym, "age_s": round(age)})
        # 1) copia literal del fichero vivo (no se altera ni un byte del original)
        atomic_write_bytes(os.path.join(day_dir, "levels_%s_%s.json" % (sym.lower(), hhmm)), blob)
        # 2) linea de serie temporal con la rancidez declarada
        append_line(jsonl, json.dumps({"ts": slot, "slot": hhmm, "sym": sym,
                                       "asof": asof, "age_s": None if age is None else round(age, 1),
                                       "stale": bool(age is not None and age > STALE_WARN_S),
                                       "levels": obj}, sort_keys=True) + "\n")
        written.append(sym)
        done.append(sym)

    state["slots"][str(slot)] = done
    # el estado solo guarda el dia en curso (no crece)
    atomic_write_json(STATE_PATH, state)

    health = {
        "date": date,
        "ts": int(now),
        "slot": hhmm,
        "written": written,
        "skipped_already_done": skipped,
        "stale": stale,
        "unreadable": unreadable,
        "syms_expected": len(glob.glob(src_glob or SRC_GLOB)),
        "slots_today": len(state["slots"]),
        "rows_today": _count_rows(jsonl),
        "bytes_today": _day_bytes(day_dir),
    }
    health["projected_mb_day"] = round(
        health["bytes_today"] / max(len(state["slots"]), 1) * 78 / 1e6, 2)
    atomic_write_json(HEALTH_PATH, health)
    return health


def _count_rows(jsonl):
    if not os.path.exists(jsonl):
        return 0
    with open(jsonl, errors="replace") as f:
        return sum(1 for _ in f)


def _day_bytes(day_dir):
    tot = 0
    for fn in os.listdir(day_dir):
        if fn.startswith("levels_"):
            try:
                tot += os.path.getsize(os.path.join(day_dir, fn))
            except OSError:
                pass
    return tot


def verify(date, hist=None):
    """Cobertura de un dia: slots por sym y % de huecos contra los 78 de sesion."""
    hist = hist or HIST
    jsonl = os.path.join(hist, date, JSONL_NAME)
    per_sym = {}
    if os.path.exists(jsonl):
        with open(jsonl, errors="replace") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                s = per_sym.setdefault(r["sym"], {"slots": set(), "stale": 0})
                s["slots"].add(r["slot"])
                if r.get("stale"):
                    s["stale"] += 1
    for p in sorted(glob.glob(os.path.join(hist, date, JSONL_NAME + ".gz"))):
        with gzip.open(p, "rt", errors="replace") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                s = per_sym.setdefault(r["sym"], {"slots": set(), "stale": 0})
                s["slots"].add(r["slot"])
    out = {"date": date, "syms": {}}
    for sym, s in sorted(per_sym.items()):
        n = len(s["slots"])
        out["syms"][sym] = {"slots": n, "gap_pct": round(100.0 * (78 - n) / 78.0, 1) if n < 78 else 0.0,
                            "stale_slots": s["stale"]}
    out["syms_covered"] = len(out["syms"])
    return out


def retention(apply_=False, today=None, hist=None):
    """Pliega las copias sueltas de dias >=2 al jsonl del dia y gzipea el jsonl.
    Verifica paridad de lineas ANTES de borrar. Sin --apply no toca nada."""
    hist = hist or HIST
    hb = _tree_bytes(hist)
    if hb > HISTORY_BUDGET_GB * 1e9:
        raise RuntimeError("data/history = %.2f GB > presupuesto %.1f GB: retencion ABORTADA"
                           % (hb / 1e9, HISTORY_BUDGET_GB))
    today = today or time.strftime("%Y-%m-%d")
    acts = []
    for date in sorted(os.listdir(hist)):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date) or date >= today:
            continue
        if _age_days(date, today) < LOOSE_DAYS:
            continue
        day_dir = os.path.join(hist, date)
        loose = sorted(glob.glob(os.path.join(day_dir, "levels_*_[0-9][0-9][0-9][0-9].json")))
        jsonl = os.path.join(day_dir, JSONL_NAME)
        gz = jsonl + ".gz"
        if loose:
            act = {"action": "fold", "date": date, "files": len(loose),
                   "bytes": sum(os.path.getsize(p) for p in loose), "applied": False}
            if apply_:
                have = set()
                for src in (jsonl,) if os.path.exists(jsonl) else ():
                    with open(src, errors="replace") as f:
                        for ln in f:
                            try:
                                r = json.loads(ln)
                            except ValueError:
                                continue
                            have.add((r["slot"], r["sym"]))
                added = 0
                for p in loose:
                    m = re.match(r"^levels_([a-z0-9.]+)_(\d{4})\.json$", os.path.basename(p))
                    if not m:
                        continue
                    sym, hhmm = m.group(1).upper(), m.group(2)
                    if (hhmm, sym) in have:
                        continue
                    try:
                        with open(p) as f:
                            obj = json.load(f)
                    except (OSError, ValueError) as e:
                        act["error"] = "copia ilegible %s (%s) -> NO se borra nada" % (p, e)
                        break
                    ts = int(time.mktime(time.strptime(date + " " + hhmm, "%Y-%m-%d %H%M")))
                    append_line(jsonl, json.dumps({"ts": ts, "slot": hhmm, "sym": sym,
                                                   "asof": obj.get("asof"), "age_s": None,
                                                   "stale": None, "levels": obj},
                                                  sort_keys=True) + "\n")
                    have.add((hhmm, sym))
                    added += 1
                if not act.get("error"):
                    for p in loose:
                        os.unlink(p)
                    act["applied"] = True
                    act["folded"] = added
            acts.append(act)
        if os.path.exists(jsonl) and not glob.glob(os.path.join(day_dir, "levels_*_[0-9][0-9][0-9][0-9].json")):
            act = {"action": "gzip_jsonl", "date": date, "bytes": os.path.getsize(jsonl),
                   "applied": False}
            if apply_:
                lines = _count_rows(jsonl)
                tmp = gz + ".tmp.%d" % os.getpid()
                with open(jsonl, "rb") as f, gzip.open(tmp, "wb") as g:
                    g.write(f.read())
                os.replace(tmp, gz)
                with gzip.open(gz, "rt", errors="replace") as f:
                    got = sum(1 for _ in f)
                if got != lines:
                    act["error"] = "paridad FALLA (%d vs %d) -> se conserva el jsonl" % (got, lines)
                    os.unlink(gz)
                else:
                    os.unlink(jsonl)
                    act["applied"] = True
                    act["bytes_gz"] = os.path.getsize(gz)
            acts.append(act)
    return {"today": today, "applied": bool(apply_), "history_bytes": _tree_bytes(hist),
            "actions": acts}


def _tree_bytes(path):
    tot = 0
    for root, _d, files in os.walk(path):
        for fn in files:
            try:
                tot += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return tot


def _age_days(date, today):
    a = time.mktime(time.strptime(date, "%Y-%m-%d"))
    b = time.mktime(time.strptime(today, "%Y-%m-%d"))
    return int(round((b - a) / 86400.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, metavar="SEC")
    ap.add_argument("--session-only", action="store_true",
                    help="no-op fuera de 09:25-16:10 en dia de mercado (para el cron)")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--retention", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.verify:
        print(json.dumps(verify(a.date or time.strftime("%Y-%m-%d")), indent=1))
        return
    if a.retention:
        r = retention(apply_=a.apply)
        print("%s: %d acciones, history %.2f MB" %
              ("APLICADO" if a.apply else "DRY-RUN", len(r["actions"]), r["history_bytes"] / 1e6))
        for x in r["actions"]:
            print("  %s %s files=%s applied=%s %s" % (x["action"], x["date"], x.get("files", "-"),
                                                      x["applied"], x.get("error", "")))
        return
    if a.loop:
        while True:
            try:
                h = snapshot(session_only=a.session_only)
                if h.get("written"):
                    print("%s slot %s: %d syms, %d stale" %
                          (h["date"], h["slot"], len(h["written"]), len(h["stale"])), flush=True)
            except Exception as e:                      # el bucle no muere, pero GRITA
                print("levels_5min_archive: FALLO %s" % e, file=sys.stderr, flush=True)
            nxt = slot_of(time.time()) + a.loop
            time.sleep(max(1.0, nxt - time.time()))
    h = snapshot(session_only=a.session_only)
    if a.once and h.get("skipped"):
        return
    print(json.dumps({k: v for k, v in h.items() if k != "levels"}, indent=1))


if __name__ == "__main__":
    main()
