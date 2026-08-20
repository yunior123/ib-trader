#!/usr/bin/env python3
"""equity_prints_archiver.py — OLA 1 feature #15: salva la CINTA FIRMADA antes de que
el bridge la destruya.

QUE SE PIERDE HOY (verificado en el codigo, 2026-07-25):
  scripts/ibkr_bar_bridge.py escribe cada print gordo del tape SIP a
  data/whale_<sym>.txt como "EPOCH PX USD DIR" (DIR: +1 agresor comprador si px>=ask,
  -1 vendedor si px<=bid, 0 indeterminado) y su prune_whales() RECORTA el fichero a los
  ultimos 900 s (bucle cada 600 s, solo si el fichero pasa de 64 KB). Es la unica cinta
  firmada que poseemos y la tiramos cada 15 minutos: sin archivo, la idea de absorcion de
  ballenas NO SE PUEDE TESTEAR NUNCA.

POR QUE NO TOCA EL BRIDGE: ibkr_bar_bridge.py es el UNICO productor de barras de toda la
flota y esta VIVO. El doc #15 proponia 5 lineas dentro del tick handler; aqui no hacen
falta: un archivador INDEPENDIENTE que relee el fichero cada 120 s es suficiente porque el
prune conserva 900 s (margen 7,5x) y NO añade ni un microsegundo de latencia al daemon mas
load-bearing del sistema. Verificado: prune cada 600 s + ventana de 900 s en
ibkr_bar_bridge.py:279-293 y :331-335.

  => No se propone ningun cambio al bridge. Si el archivador se cae mas de 900 s SI se
     pierden prints, y eso se DECLARA como hueco (`gaps`) en prints_coverage.json en vez
     de fingir continuidad.

COBERTURA HONESTA (no se puede sobre-afirmar):
  - WHALE_MIN_USD = 50000 (ibkr_bar_bridge.py:42) => esto es un perfil de BALLENAS,
    NO volume-by-price. Nombrarlo mal invitaria a usarlo como volumen real.
  - DIR se clasifica contra un NBBO cacheado en el bridge => mala clasificacion por
    rancidez. Se archiva tal cual y se avisa; jamas se "corrige".
  - whale_aapl/amd/asml/gld/qqq/spy/tsm/txn.txt son 0 bytes: el tick-by-tick solo corre
    para los syms de foco. Se reporta por sym (`zero_byte`), nunca se asume cobertura.
  - No existe NADA anterior a la primera corrida de este archivador. Dicho y contado.

SALIDA: data/prints/<fecha>/<sym>.txt   (append, rotado por dia segun el epoch de CADA
                                         linea, no la hora de la corrida)
        data/prints_state.json          (cursor por sym: idempotencia)
        data/prints_coverage.json       (cobertura honesta por sym)

TAMAÑO MEDIDO (2026-07-25, ficheros vivos del 24-jul): NOK 57 KB / NVDA 55 KB /
  TSLA 49 KB / SPCX 37 KB / DRAM 12 KB en la ventana de 15 min => los 5 syms con datos
  dan ~210 KB por cuarto de hora ~= 5,5 MB/dia de sesion. RETENCION 180 dias con gzip
  desde el dia 2 (texto plano comprime ~4x): ~1,4 MB/dia archivado => ~250 MB a 180 dias.
  Justificacion del 180: el motor de absorcion exige >=20 sesiones por sym para siquiera
  testearse y la calibracion trabaja en ventanas de 6 meses; mas alla, la cinta de ballenas
  envejece peor que el OI (cambia el regimen de liquidez) y no vale su disco.

DECISION RULE (doctrina, no codigo): NINGUN motor de absorcion hasta >=20 sesiones
archivadas del sym. Hasta entonces la cinta sigue alimentando opt_whale_watch igual que hoy.

Uso:
  ./venv/bin/python scripts/equity_prints_archiver.py --once
  ./venv/bin/python scripts/equity_prints_archiver.py --loop 120
  ./venv/bin/python scripts/equity_prints_archiver.py --coverage
  ./venv/bin/python scripts/equity_prints_archiver.py --retention [--apply]

SEÑAL-SOLAMENTE: lee la cinta, la copia. Cero red, cero ordenes, cero escritura en lo vivo.
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

SRC_GLOB = os.path.join("data", "whale_*.txt")
OUT_DIR = os.path.join("data", "prints")
STATE_PATH = os.path.join("data", "prints_state.json")
COVERAGE_PATH = os.path.join("data", "prints_coverage.json")

TRIM_WINDOW_S = 900          # lo que conserva prune_whales() en el bridge
POLL_DEFAULT = 120           # margen 7,5x contra la ventana de trim
RETENTION_DAYS = 180
GZIP_AFTER_DAYS = 2
RTH_MINUTES = 390            # 09:30-16:00


def atomic_write_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_lines(path, lines):
    """O_APPEND en UNA escritura: nunca se ve media linea, y no hay tmp+rename que
    pueda perder lo que otro proceso appendeo entre medias."""
    if not lines:
        return 0
    blob = "".join(lines).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, blob)
    finally:
        os.close(fd)
    return len(lines)


def parse_line(ln):
    """'EPOCH PX USD DIR' -> (ep, px, usd, dir) o None si la linea no es una impresion.
    None significa 'no es dato', jamas un print de precio 0."""
    t = ln.split()
    if len(t) < 4:
        return None
    try:
        ep = int(float(t[0]))
        px = float(t[1])
        usd = float(t[2])
        d = int(t[3])
    except ValueError:
        return None
    if ep <= 0 or px <= 0 or d not in (-1, 0, 1):
        return None
    return (ep, px, usd, d)


def _load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def new_lines(lines, last_ep, archived_at_last_ep, prev_run=0, now=None):
    """Lo que falta por archivar, con dedupe exacto en la FRONTERA del epoch.

    El fichero vivo esta ordenado por llegada y el prune solo QUITA por delante, asi que:
      - epoch > last_ep            -> nuevo seguro
      - epoch == last_ep           -> solo las ocurrencias por encima de las ya archivadas
                                      (si el prune se comio algunas, count < archivadas y
                                      no se archiva nada: no se duplica)
    Devuelve (lineas_nuevas, nuevo_last_ep, nuevas_archivadas_en_last_ep, gap_detectado).

    HUECO (honesto, no alarmista): que el fichero empiece despues de nuestro cursor es lo
    NORMAL — los prints de >=50k son esporadicos y puede no haber ninguno en minutos. Solo
    se declara hueco si ADEMAS estuvimos fuera mas que la ventana de trim (900 s), que es la
    unica situacion en la que el prune pudo comerse lineas sin archivar.
    """
    now = now or time.time()
    parsed = []
    for ln in lines:
        p = parse_line(ln)
        if p:
            parsed.append((p, ln if ln.endswith("\n") else ln + "\n"))
    if not parsed:
        return [], last_ep, archived_at_last_ep, False
    eps = [p[0][0] for p in parsed]
    file_min, file_max = min(eps), max(eps)
    if last_ep and file_max < last_ep:
        # el bridge trunco por cambio de dia (modo "w"): fichero nuevo, cursor a cero
        last_ep, archived_at_last_ep = 0, 0
    gap = bool(last_ep and file_min > last_ep
               and prev_run and (now - prev_run) > TRIM_WINDOW_S)
    at_boundary = [x for x in parsed if x[0][0] == last_ep]
    out = []
    if last_ep and len(at_boundary) > archived_at_last_ep:
        out += [x[1] for x in at_boundary[archived_at_last_ep:]]
    out += [x[1] for x in parsed if x[0][0] > last_ep]
    if not out:
        return [], last_ep, archived_at_last_ep, gap
    new_last = max(x[0][0] for x in parsed)
    n_at_new_last = sum(1 for x in parsed if x[0][0] == new_last)
    if new_last == last_ep:
        n_at_new_last = max(n_at_new_last, archived_at_last_ep + len(out))
    return out, new_last, n_at_new_last, gap


def archive_once(src_glob=None, out_dir=None, state_path=None, now=None):
    now = now or time.time()
    src_glob = src_glob or SRC_GLOB
    out_dir = out_dir or OUT_DIR
    global STATE_PATH
    if state_path:
        STATE_PATH = state_path
    state = _load_state()
    report = {"ts": int(now), "syms": {}, "rows": 0, "gaps": []}
    for src in sorted(glob.glob(src_glob)):
        m = re.match(r"^whale_([a-z0-9.]+)\.txt$", os.path.basename(src))
        if not m:
            continue
        sym = m.group(1).upper()
        st = state.setdefault(sym, {"last_ep": 0, "n_at_last_ep": 0, "rows": 0,
                                    "gaps": 0, "last_run": 0})
        try:
            size = os.path.getsize(src)
            with open(src, errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            report["syms"][sym] = {"err": str(e)}
            continue
        prev_run = st.get("last_run", 0)
        st["last_run"] = int(now)
        st["zero_byte"] = (size == 0)
        if size == 0:
            report["syms"][sym] = {"rows": 0, "zero_byte": True}
            continue
        fresh, last_ep, n_at, gap = new_lines(lines, st["last_ep"], st["n_at_last_ep"],
                                              prev_run=prev_run, now=now)
        if gap:
            st["gaps"] += 1
            report["gaps"].append(sym)
        # cada linea al fichero de SU dia (un print de 23:59 no cae en el dia siguiente)
        by_day = {}
        for ln in fresh:
            p = parse_line(ln)
            day = time.strftime("%Y-%m-%d", time.localtime(p[0]))
            by_day.setdefault(day, []).append(ln)
        n = 0
        for day, dl in sorted(by_day.items()):
            d = os.path.join(out_dir, day)
            os.makedirs(d, exist_ok=True)
            n += append_lines(os.path.join(d, "%s.txt" % sym.lower()), dl)
        st["last_ep"] = last_ep
        st["n_at_last_ep"] = n_at
        st["rows"] += n
        report["syms"][sym] = {"rows": n, "last_ep": last_ep, "gap": gap,
                               "total_archived": st["rows"]}
        report["rows"] += n
    atomic_write_json(STATE_PATH, state)
    return report


def coverage(out_dir=None, state_path=None):
    """Cobertura HONESTA por sym: sesiones, filas, % de minutos de RTH con al menos un
    print, y los ceros declarados. Nada de porcentajes inventados: si no hay dato, None."""
    out_dir = out_dir or OUT_DIR
    global STATE_PATH
    if state_path:
        STATE_PATH = state_path
    state = _load_state()
    cov = {"updated": int(time.time()),
           "whale_min_usd": 50000.0,
           "nota": "perfil de BALLENAS (>=50k USD), NO volume-by-price. DIR clasificado "
                   "contra un NBBO cacheado en el bridge -> mala clasificacion por rancidez.",
           "historia_previa": "no existe nada anterior a la primera corrida de este archivador",
           "syms": {}}
    days = sorted(d for d in (os.listdir(out_dir) if os.path.isdir(out_dir) else [])
                  if re.match(r"^\d{4}-\d{2}-\d{2}$", d))
    per_sym = {}
    for day in days:
        for p in sorted(glob.glob(os.path.join(out_dir, day, "*.txt")) +
                        glob.glob(os.path.join(out_dir, day, "*.txt.gz"))):
            sym = os.path.basename(p).split(".")[0].upper()
            opener = gzip.open if p.endswith(".gz") else open
            rows = 0
            minutes = set()
            first = last = None
            with opener(p, "rt", errors="replace") as f:
                for ln in f:
                    q = parse_line(ln)
                    if not q:
                        continue
                    rows += 1
                    minutes.add(q[0] // 60)
                    first = q[0] if first is None else min(first, q[0])
                    last = q[0] if last is None else max(last, q[0])
            s = per_sym.setdefault(sym, {"sessions": 0, "rows": 0, "days": {}})
            s["sessions"] += 1
            s["rows"] += rows
            s["days"][day] = {"rows": rows,
                              "minutes_with_print": len(minutes),
                              "pct_of_session_covered": round(100.0 * len(minutes) / RTH_MINUTES, 1),
                              "first_ts": first, "last_ts": last}
    for sym, s in sorted(per_sym.items()):
        st = state.get(sym, {})
        s["zero_byte"] = bool(st.get("zero_byte"))
        s["gaps"] = st.get("gaps", 0)
        s["absorption_ready"] = s["sessions"] >= 20      # regla dura del doc #15
        cov["syms"][sym] = s
    for sym, st in sorted(state.items()):
        if sym not in cov["syms"]:
            cov["syms"][sym] = {"sessions": 0, "rows": 0, "days": {},
                                "zero_byte": bool(st.get("zero_byte")),
                                "gaps": st.get("gaps", 0), "absorption_ready": False}
    atomic_write_json(COVERAGE_PATH, cov)
    return cov


def retention(apply_=False, today=None, out_dir=None):
    out_dir = out_dir or OUT_DIR
    today = today or time.strftime("%Y-%m-%d")
    acts = []
    if not os.path.isdir(out_dir):
        return {"applied": bool(apply_), "actions": acts}
    for day in sorted(os.listdir(out_dir)):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            continue
        age = _age_days(day, today)
        if age >= RETENTION_DAYS:
            act = {"action": "delete_day", "date": day, "age": age,
                   "bytes": _tree_bytes(os.path.join(out_dir, day)), "applied": False}
            if apply_:
                for p in glob.glob(os.path.join(out_dir, day, "*")):
                    os.unlink(p)
                os.rmdir(os.path.join(out_dir, day))
                act["applied"] = True
            acts.append(act)
            continue
        if age >= GZIP_AFTER_DAYS:
            for p in sorted(glob.glob(os.path.join(out_dir, day, "*.txt"))):
                act = {"action": "gzip", "date": day, "path": p,
                       "bytes": os.path.getsize(p), "applied": False}
                if apply_:
                    rows = sum(1 for _ in open(p, errors="replace"))
                    gz = p + ".gz"
                    tmp = gz + ".tmp.%d" % os.getpid()
                    with open(p, "rb") as f, gzip.open(tmp, "wb") as g:
                        g.write(f.read())
                    os.replace(tmp, gz)
                    with gzip.open(gz, "rt", errors="replace") as f:
                        got = sum(1 for _ in f)
                    if got != rows:
                        act["error"] = "paridad FALLA (%d vs %d) -> se conserva el .txt" % (got, rows)
                        os.unlink(gz)
                    else:
                        os.unlink(p)
                        act["applied"] = True
                        act["bytes_gz"] = os.path.getsize(gz)
                acts.append(act)
    return {"applied": bool(apply_), "today": today, "actions": acts,
            "bytes_total": _tree_bytes(out_dir)}


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
    ap.add_argument("--loop", type=int, metavar="SEC", nargs="?", const=POLL_DEFAULT)
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--retention", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.coverage:
        cov = coverage()
        for sym, s in sorted(cov["syms"].items()):
            print("%-6s sesiones=%d filas=%d huecos=%d %s" %
                  (sym, s["sessions"], s["rows"], s["gaps"],
                   "(0 bytes: sin tick-by-tick)" if s["zero_byte"] else ""))
        return
    if a.retention:
        r = retention(apply_=a.apply)
        print("%s: %d acciones, %.2f MB en data/prints" %
              ("APLICADO" if a.apply else "DRY-RUN", len(r["actions"]), r["bytes_total"] / 1e6))
        return
    if a.loop:
        if a.loop > TRIM_WINDOW_S / 2:
            print("equity_prints_archiver: poll %ds es MAS de la mitad de la ventana de trim "
                  "(%ds) -> riesgo de perder prints" % (a.loop, TRIM_WINDOW_S), file=sys.stderr)
        while True:
            try:
                r = archive_once()
                if r["rows"]:
                    print("%s: %d prints archivados%s" %
                          (time.strftime("%H:%M:%S"), r["rows"],
                           (" HUECOS en " + ",".join(r["gaps"])) if r["gaps"] else ""), flush=True)
            except Exception as e:
                print("equity_prints_archiver: FALLO %s" % e, file=sys.stderr, flush=True)
            time.sleep(a.loop)
    r = archive_once()
    coverage()
    if a.once and not r.get("rows") and not r.get("gaps"):
        return
    print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
