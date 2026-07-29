#!/usr/bin/env python3
"""regen_signals.py — REGENERAR las señales de la flota sobre las 540 sesiones de poly_bars.

LA IDEA (Yunior 2026-07-25): *"usa los datos de polygon y reproduce... olvidate del
websocket de IBKR, reproduce local como si estuviera conectado a IBKR."*

EL CUELLO DE BOTELLA QUE ESTO ABRE
----------------------------------
`poly_bars` tiene 8.950.177 barras 1m / 540 sesiones / 30 simbolos (2024-07-25 -> 2026-07-24).
`trades.db signals` tiene 11 FECHAS (desde 2026-07-15). Con rho medio 0.41 de la flota,
`bollinger n=1154` se queda en n_eff=89 y sale UNPROVEN; 0 de 131 celdas pasan BH-FDR q=0.10.
No falta señal nueva: falta HISTORIA de la señal que ya tenemos. Esto la fabrica corriendo
los MISMOS generadores contra el pasado real.

COMO (dos arneses, los dos bar-a-bar, los dos sin look-ahead POR CONSTRUCCION)
-----------------------------------------------------------------------------
1. **bots C++ `<sym>_signal_bot --stdin`** (modo replay que ya tenian). Se les alimenta el
   stream "EPOCH O H L C V" en orden. Un proceso que lee de una tuberia NO PUEDE ver una
   barra que aun no se ha escrito: el no-look-ahead es estructural, no una promesa.
   Emiten CUSUM / SUPERTREND / DONCHIAN / BUY / SELL a stdout con `[HH:MM]` de la BARRA.
2. **`scripts/bollinger_alarm.py` en LOCKSTEP** contra un sandbox, con el reloj virtual de
   `scripts/regen_shim/` (time.time/localtime -> instante virtual; time.sleep -> avanza el
   reloj y materializa las barras CERRADAS en ese instante). El script no se modifica: solo
   cambia el reloj y se muteanel audio. Escribe su fichero de señales con timestamp virtual.

Ambos escriben SIEMPRE en un sandbox temporal; los `data/*.txt` reales de la flota viva no se
tocan (guardia dura en `_sandbox_guard`).

LIMITES HONESTOS — declarados, no disimulados
---------------------------------------------
· **Cadenas de opciones: solo 4 dias** (`data/history/2026-07-21..25`). Las fuentes que
  dependen de GEX/muros/flip — `whale`, `flow`, `structural` — NO SE PUEDEN REGENERAR y no
  aparecen en `signals_regen`. Regenerable = lo que vive del PRECIO: `bollinger`, `cusum`.
· Sin NBBO tick a tick ni cadena, los bots corren DEGRADADOS a precio puro (su gate de
  spread lee 0 = "sin dato" y no opina; el contexto de opciones queda vacio). Una señal
  regenerada NO es una grabacion de la que emitio el bot en vivo: es una señal REPRODUCIBLE
  sobre precio real. La tasa de coincidencia contra los 11 dias vivos se MIDE (`coincide`).
· poly_bars es 1m: no hay ruta sub-minuto, asi que la ambigüedad TP/SL dentro de la misma
  barra sigue siendo irreducible (barrier_labels la publica como `ambig_pct`).

TABLA NUEVA, JAMAS `signals`
----------------------------
Escribe SOLO en `signals_regen` (mismo esquema que `signals` + run_id/seed/source_kind).
`signals` es el ledger vivo de 8 daemons: contaminarlo seria irreversible. Verificado por
tests/test_regen_signals.py (count + mtime antes/despues).

USO
    python3 scripts/regen_signals.py plan                      # sesiones + ETA
    python3 scripts/regen_signals.py run --limit 1             # una sesion (cronometrar)
    python3 scripts/regen_signals.py run                       # todas las pendientes
    python3 scripts/regen_signals.py run --dates 2026-07-23
    python3 scripts/regen_signals.py verify-replay --date D    # feeder == ./replay --end
    python3 scripts/regen_signals.py nolookahead --date D      # invariante ts+60 <= V
    python3 scripts/regen_signals.py coincide                  # regen vs vivo (11 dias)
    python3 scripts/regen_signals.py stats

SEÑAL-SOLAMENTE: no ordena nada, no habla, no toca TWS.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import datetime as dt
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
if os.path.join(REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "scripts"))

DB = os.path.join(REPO, "data", "trades.db")
DB_RO = "file:" + DB + "?mode=ro"
SHIM = os.path.join(REPO, "scripts", "regen_shim")
PY = os.path.join(REPO, "venv", "bin", "python")
if not os.path.exists(PY):
    PY = sys.executable

BAR_S = 60
WARM_BARS = 780                 # = replay.cpp K::WARM_BARS (13h de contexto)
SESS_START = "09:30"
SESS_END = "16:00"
BOLL_START = "09:34"            # bollinger_alarm arranca a 9:35; entra un tick antes
BOLL_END = "15:56"              # el propio script rompe en 15:55
DEFAULT_SEED = 7

# --------------------------------------------------------------------------
# 1. Mapa stdout-de-bot -> (kind, source) EN EL FORMATO VIVO
# --------------------------------------------------------------------------
# Por que hace falta: `barrier_labels.direction_of` -> `eod_backtest.thesis(source,kind,msg)`
# solo mira `source` y palabras clave del blob. Si el `kind` regenerado no dice lo que decia
# el vivo, la POBLACION cambia y el delta ya no es puro re-etiquetado. El bot escribe el
# titulo vivo en <sym>_operations.log, pero con el reloj de PARED (time(nullptr)), inutil en
# un lote; el stdout si trae la hora de la BARRA. Asi que el titulo se reconstruye aqui con
# una tabla EXPLICITA y deterministica, y la linea cruda se guarda en `raw` para auditarla.
# (verificado contra las lineas reales de mu_operations.log en un replay de 2026-07-10)
BOT_KINDS = (
    # (regex sobre el texto de stdout, plantilla de kind, priority)
    (re.compile(r"^CUSUM:\s+\S+\s+SUBIENDO", re.I), "{SYM} TERREMOTO ALZA"),
    (re.compile(r"^CUSUM:\s+\S+\s+CAYENDO", re.I), "{SYM} TERREMOTO CAIDA"),
    (re.compile(r"^SUPERTREND:", re.I), "{SYM} tendencia"),
    (re.compile(r"^DONCHIAN:.*maximo", re.I), "{SYM} breakout"),
    (re.compile(r"^DONCHIAN:.*minimo", re.I), "{SYM} breakdown"),
    (re.compile(r"\*\*\*.*\b(BUY|COMPRAR)\b", re.I), "{SYM}: BUY"),
    (re.compile(r"\*\*\*.*\b(SELL|VENDER|PUT)\b", re.I), "{SYM}: SELL"),
)
BOT_LINE = re.compile(r"^\[(\d{2}):(\d{2})\]\s+(.*\S)\s*$")
# ruido de depuracion del bot: nunca fue una notificacion en vivo, no es una señal
BOT_NOISE = re.compile(r"^(V6-DBG|.*V6 TRAMPA-EVITADA|TREND-ENTRY armado|TREND-PUT armado|"
                       r"v3-ARM|confirm BLOQUEADO)", re.I)


def bot_kind(sym_up, text):
    """-> kind vivo o None si la linea es ruido de depuracion/desconocida."""
    if BOT_NOISE.match(text):
        return None
    for rx, tpl in BOT_KINDS:
        if rx.search(text):
            return tpl.format(SYM=sym_up)
    return None


# --------------------------------------------------------------------------
# 2. Utilidades de fecha / BD
# --------------------------------------------------------------------------
def ro():
    c = sqlite3.connect(DB_RO, uri=True, timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    return c


def rw():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def epoch_of(date, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    y, mo, d = (int(x) for x in date.split("-"))
    # hora LOCAL del Mac == ET (Toronto), igual que replay.cpp epoch_of()
    return time.mktime((y, mo, d, h, m, 0, 0, 0, -1))


def sessions(conn):
    """Fechas con barras de RTH en poly_bars, ordenadas. Una sesion = un dia natural."""
    q = ("SELECT DISTINCT date(ts/1000,'unixepoch','localtime') AS d, count(*) "
         "FROM poly_bars GROUP BY d ORDER BY d")
    return [(d, n) for d, n in conn.execute(q) if d]


def fleet():
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        return [s.upper() for s in f.read().split()]


def poly_syms(conn):
    return {r[0] for r in conn.execute("SELECT DISTINCT sym FROM poly_bars")}


def bots_available():
    """{SYM: ruta} de los bots C++ compilados que existen AHORA."""
    out = {}
    bdir = os.path.join(REPO, "bots")
    for fn in sorted(os.listdir(bdir)):
        if not fn.endswith("_signal_bot"):
            continue
        p = os.path.join(bdir, fn)
        if os.access(p, os.X_OK):
            out[fn[:-len("_signal_bot")].upper()] = p
    return out


# --------------------------------------------------------------------------
# 2b. PARAMETROS DE PRODUCCION por ticker (scripts/<sym>_keepalive.sh)
# --------------------------------------------------------------------------
# MEDIDO 2026-07-25: sin esto la regeneracion emitia 544 `cusum` contra 149 vivos
# (precision 15%). El motivo no era el arnes: `mu_keepalive.sh` exporta
# MU_QUAKE_MIN=0.05 y el binario trae 0.02 por defecto -> el bot regenerado usaba un
# umbral de terremoto 2.5x mas laxo que el de produccion. Los parametros del bot NO
# son un detalle de arranque: son el bot. Se leen del mismo fichero que la flota viva.
ENV_LINE = re.compile(r"^\s*export\s+([A-Z][A-Z0-9_]*)=([^\s#$`\'\"]+)\s*$")


def keepalive_env(sym_up):
    """{VAR: valor} exportadas por scripts/<sym>_keepalive.sh. Solo literales simples:
    cualquier linea con $, comillas o backticks se IGNORA y se cuenta (jamas se
    ejecuta el shell para averiguar un parametro)."""
    p = os.path.join(REPO, "scripts", "%s_keepalive.sh" % sym_up.lower())
    out, skipped = {}, 0
    if not os.path.exists(p):
        return out, 0
    with open(p, errors="replace") as f:
        for ln in f:
            if not ln.lstrip().startswith("export "):
                continue
            m = ENV_LINE.match(ln)
            if m:
                out[m.group(1)] = m.group(2)
            else:
                skipped += 1
    return out, skipped


def load_bars(conn, sym_up, t0, t1):
    """Mismas reglas que replay.cpp db_bars(): ts en MILISEGUNDOS, alineado a 60s, c>0."""
    q = ("SELECT ts,o,h,l,c,v FROM poly_bars WHERE sym=? AND ts>=? AND ts<? ORDER BY ts")
    out = []
    for ts, o, h, l, c, v in conn.execute(q, (sym_up, int(t0) * 1000, int(t1) * 1000)):
        t = int(ts // 1000)
        t -= t % BAR_S
        if c is not None and c > 0:
            out.append((t, float(o), float(h), float(l), float(c), float(v)))
    return out


def load_session_bars(conn, sym_up, date, t_start, t_end, warm=WARM_BARS):
    """Warm-up (pasado) + sesion, recortado a `warm` barras antes de t_start.
    Copia exacta del recorte de replay.cpp (lineas 626-634)."""
    bars = load_bars(conn, sym_up, t_start - warm * BAR_S - 4 * 86400, t_end)
    k = 0
    while k < len(bars) and bars[k][0] + BAR_S <= t_start:
        k += 1
    if k > warm:
        bars = bars[k - warm:]
    return bars


# --------------------------------------------------------------------------
# 3. Esquema
# --------------------------------------------------------------------------
SCHEMA_SIGNALS_REGEN = """CREATE TABLE IF NOT EXISTS signals_regen(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_epoch REAL, ts_txt TEXT, date TEXT, kind TEXT, symbol TEXT,
    price REAL, priority TEXT, source TEXT, msg TEXT, raw TEXT,
    run_id TEXT, seed INTEGER, source_kind TEXT DEFAULT 'regen',
    UNIQUE(run_id, date, ts_txt, symbol, msg))"""

SCHEMA_PROGRESS = """CREATE TABLE IF NOT EXISTS regen_progress(
    run_id TEXT, date TEXT, status TEXT, n_signals INTEGER,
    secs REAL, err TEXT, updated_at REAL,
    PRIMARY KEY(run_id, date))"""


def ensure_schema(conn):
    conn.execute(SCHEMA_SIGNALS_REGEN)
    conn.execute(SCHEMA_PROGRESS)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sgr_date ON signals_regen(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sgr_src ON signals_regen(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sgr_run ON signals_regen(run_id)")
    conn.commit()


def run_id_of(seed, sources, syms):
    """Determinista: misma configuracion -> mismo run_id (reanudable, idempotente)."""
    blob = "|".join([str(seed), ",".join(sorted(sources)), ",".join(sorted(syms))])
    return "r" + hashlib.sha1(blob.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------
# 4. Sandbox
# --------------------------------------------------------------------------
_SB_BAD = ("", "/data", "/charts/data", "/charts", "/scripts")


def _sandbox_guard(sb):
    """Preferimos morir antes que escribir sobre los data/*.txt de la flota VIVA."""
    r = os.path.realpath(REPO)
    o = os.path.realpath(sb) if os.path.exists(sb) else os.path.abspath(sb)
    for bad in _SB_BAD:
        if o == r + bad:
            raise SystemExit("sandbox invalido %s (contaminaria la flota viva)" % o)
    # OJO macOS: realpath("/tmp") == "/private/tmp". Comparar sin normalizar dejaba
    # pasar /tmp como sandbox (cazado por tests/test_regen_signals.py).
    forbidden = {os.path.realpath(x) for x in ("/", "/tmp", "/var/tmp", os.path.expanduser("~"))}
    if o in forbidden:
        raise SystemExit("sandbox invalido: %s" % o)
    if o.startswith(r + os.sep):
        raise SystemExit("el sandbox no puede vivir DENTRO del repo: %s" % o)


# ficheros de CONFIG (no cotizaciones) que los generadores necesitan para no degradar a
# otra cosa distinta de produccion. Se enlazan; nada se copia de vuelta.
SB_LINK_DATA = ("fleet.txt", "bollinger_probs.json", "bollinger_plus.json",
                "signal_enable.json", "momentum_decay.json", "etf_weights.json",
                "book_quality.json", "peer_weights.json")


def make_sandbox(sb):
    _sandbox_guard(sb)
    for d in ("data/trading-signals", "charts/data", "scripts", "_regen"):
        os.makedirs(os.path.join(sb, d), exist_ok=True)
    with open(os.path.join(sb, ".replay-sandbox"), "w") as f:
        f.write("sandbox de regen_signals.py — NO es el repo\n")
    # scripts/: enlaces a los .py REALES. Truco clave: los generadores derivan su REPO de
    # os.path.abspath(__file__) (que NO resuelve symlinks) -> su REPO pasa a ser el sandbox
    # y su os.chdir(REPO) ya no vuelve al repo vivo.
    for fn in os.listdir(os.path.join(REPO, "scripts")):
        src = os.path.join(REPO, "scripts", fn)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(sb, "scripts", fn)
        if not os.path.lexists(dst):
            os.symlink(src, dst)
    for fn in ("gate", "compass"):
        src, dst = os.path.join(REPO, fn), os.path.join(sb, fn)
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(src, dst)
    for fn in SB_LINK_DATA:
        src, dst = os.path.join(REPO, "data", fn), os.path.join(sb, "data", fn)
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(src, dst)
    return sb


def reset_sandbox_session(sb):
    """Entre sesiones: fuera barras, señales, posiciones y reloj. La config enlazada queda."""
    d = os.path.join(sb, "data")
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if os.path.islink(p) or os.path.isdir(p):
            continue
        os.unlink(p)
    ts = os.path.join(d, "trading-signals")
    for fn in os.listdir(ts):
        os.unlink(os.path.join(ts, fn))
    fr = os.path.join(sb, "_regen")
    for fn in os.listdir(fr):
        os.unlink(os.path.join(fr, fn))
    # Limpiar logs en la raíz (legacy) y en logs/ (nuevo)
    for fn in os.listdir(sb):
        if fn.endswith("_operations.log") or fn == "clock.txt":
            os.unlink(os.path.join(sb, fn))
    logs_dir = os.path.join(sb, "logs")
    if os.path.isdir(logs_dir):
        for fn in os.listdir(logs_dir):
            if fn.endswith("_operations.log"):
                os.unlink(os.path.join(logs_dir, fn))


# --------------------------------------------------------------------------
# 5. Generador A: bots C++ via --stdin (bar-a-bar por tuberia)
# --------------------------------------------------------------------------
def run_bots(sb, date, bars_by_sym, bots, timeout=300):
    """-> (rows, fails). rows = [(ts_epoch, ts_txt, kind, sym, msg, raw)]"""
    rows, fails = [], []
    unmapped = defaultdict(int)
    for sym_up, exe in sorted(bots.items()):
        bars = bars_by_sym.get(sym_up)
        if not bars:
            continue
        feed = "".join("%d %.4f %.4f %.4f %.4f %.0f\n" % b for b in bars)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        kenv, skipped = keepalive_env(sym_up)
        env.update(kenv)
        if skipped:
            fails.append("%s %s: %d export(s) del keepalive no literales, IGNORADOS"
                         % (date, sym_up, skipped))
        try:
            p = subprocess.run([exe, "--stdin"], input=feed, capture_output=True,
                               text=True, cwd=sb, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            fails.append("%s %s: TIMEOUT %ss" % (date, sym_up, timeout))
            continue
        if p.returncode != 0:
            fails.append("%s %s: rc=%d %s" % (date, sym_up, p.returncode,
                                              (p.stderr or "").strip()[:120]))
            continue
        for ln in (p.stdout or "").splitlines():
            m = BOT_LINE.match(ln)
            if not m:
                continue
            hh, mm, text = int(m.group(1)), int(m.group(2)), m.group(3)
            kind = bot_kind(sym_up, text)
            if kind is None:
                if not BOT_NOISE.match(text):
                    unmapped[text.split()[0][:24]] += 1
                continue
            # epoch de la BARRA: preferimos el t= explicito; si no, HH:MM del dia
            mt = re.search(r"\bt=(\d{9,12})\b", text)
            if mt:
                ep = float(mt.group(1))
                lt = time.localtime(ep)
                ts_txt = "%02d:%02d:%02d" % (lt.tm_hour, lt.tm_min, lt.tm_sec)
                d_txt = "%04d-%02d-%02d" % (lt.tm_year, lt.tm_mon, lt.tm_mday)
            else:
                ep = epoch_of(date, "%02d:%02d" % (hh, mm))
                ts_txt = "%02d:%02d:00" % (hh, mm)
                d_txt = date
            if d_txt != date:          # barra de warm-up de otro dia: no es de esta sesion
                continue
            rows.append((ep, ts_txt, d_txt, kind, sym_up, text, ln))
    return rows, fails, dict(unmapped)


# --------------------------------------------------------------------------
# 6. Generador B: bollinger_alarm.py en lockstep con reloj virtual
# --------------------------------------------------------------------------
def run_bollinger(sb, date, bars_by_sym, t0, t1, timeout=1800):
    """Corre scripts/bollinger_alarm.py SIN MODIFICAR contra el sandbox. Cosecha el
    fichero data/trading-signals/<fecha>.txt que el propio script escribe."""
    fr = os.path.join(sb, "_regen")
    n_bars = 0
    for sym_up, bars in bars_by_sym.items():
        p = os.path.join(fr, "allbars_%s.txt" % sym_up.lower())
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            for b in bars:
                f.write("%d %.4f %.4f %.4f %.4f %.0f\n" % b)
                n_bars += 1
        os.replace(tmp, p)
    if n_bars == 0:
        return [], ["%s bollinger: cero barras" % date]

    env = dict(os.environ)
    env["PYTHONPATH"] = SHIM + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["IBT_REGEN_SANDBOX"] = sb
    env["IBT_REGEN_T0"] = "%.3f" % t0
    env["IBT_REGEN_TEND"] = "%.3f" % t1
    script = os.path.join(sb, "scripts", "bollinger_alarm.py")
    try:
        p = subprocess.run([PY, script], capture_output=True, text=True,
                           cwd=sb, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return [], ["%s bollinger: TIMEOUT %ss" % (date, timeout)]
    fails = []
    if p.returncode != 0:
        fails.append("%s bollinger: rc=%d %s" % (date, p.returncode,
                                                 (p.stderr or "").strip()[:200]))
    return harvest_signal_file(sb, date), fails


def harvest_signal_file(sb, date):
    """Lee <sandbox>/data/trading-signals/<fecha>.txt con el MISMO parser que la BD viva."""
    import signals_db as SDB
    path = os.path.join(sb, "data", "trading-signals", "%s.txt" % date)
    if not os.path.exists(path):
        return []
    out = []
    with open(path, errors="replace") as f:
        for ln in f:
            r = SDB.parse_line(ln, date)
            if not r:
                continue
            ep, ts_txt, d, kind, sym, price, pr, src, msg, raw = r
            if "WARMUP" in (kind or "") or "WARMUP" in (raw or ""):
                continue
            out.append((ep, ts_txt, d, kind, sym, msg, raw))
    return out


# --------------------------------------------------------------------------
# 7. Clasificacion + escritura
# --------------------------------------------------------------------------
def classify_rows(rows):
    """-> filas listas para signals_regen, usando el MISMO classify/extract de signals_db."""
    import signals_db as SDB
    out = []
    for ep, ts_txt, date, kind, sym, msg, raw in rows:
        pr, src = SDB.classify(kind, msg)
        s = sym or SDB.extract_symbol(kind, msg)
        px = SDB.extract_price(msg)
        out.append((ep, ts_txt, date, kind, s, px, pr, src, msg, raw))
    return out


def write_signals(conn, rows, run_id, seed, batch=2000):
    sql = ("INSERT OR IGNORE INTO signals_regen(ts_epoch,ts_txt,date,kind,symbol,price,"
           "priority,source,msg,raw,run_id,seed,source_kind) "
           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'regen')")
    n = 0
    for a in range(0, len(rows), batch):
        conn.executemany(sql, [r + (run_id, seed) for r in rows[a:a + batch]])
        conn.commit()
        n += len(rows[a:a + batch])
    return n


def mark(conn, run_id, date, status, n=0, secs=0.0, err=None):
    conn.execute("INSERT OR REPLACE INTO regen_progress(run_id,date,status,n_signals,secs,"
                 "err,updated_at) VALUES(?,?,?,?,?,?,?)",
                 (run_id, date, status, n, secs, err, time.time()))
    conn.commit()


def done_dates(conn, run_id):
    return {d for (d,) in conn.execute(
        "SELECT date FROM regen_progress WHERE run_id=? AND status='ok'", (run_id,))}


# --------------------------------------------------------------------------
# 8. Comandos
# --------------------------------------------------------------------------
def cmd_plan(args):
    c = ro()
    sess = sessions(c)
    syms = poly_syms(c) & set(fleet())
    bots = {k: v for k, v in bots_available().items() if k in syms}
    print("=== PLAN DE REGENERACION ===")
    print("sesiones en poly_bars ....... %d  (%s -> %s)" % (len(sess), sess[0][0], sess[-1][0]))
    print("simbolos flota en poly_bars . %d  %s" % (len(syms), " ".join(sorted(syms))))
    print("bots C++ disponibles ........ %d  %s" % (len(bots), " ".join(sorted(bots))))
    print("fuentes REGENERABLES ........ bollinger (bollinger_alarm.py), cusum + signal (bots)")
    print("fuentes NO regenerables ..... whale, flow, structural  <- exigen cadena de "
          "opciones; solo hay 4 dias en data/history/")
    ensure_schema_ro_check(c)
    c.close()


def ensure_schema_ro_check(c):
    try:
        n = c.execute("SELECT count(*), count(DISTINCT date) FROM signals_regen").fetchone()
        p = c.execute("SELECT count(*) FROM regen_progress WHERE status='ok'").fetchone()
        print("signals_regen ............... %d filas / %d fechas (%d sesiones ok)"
              % (n[0], n[1], p[0]))
    except sqlite3.OperationalError:
        print("signals_regen ............... (aun no existe)")


def cmd_run(args):
    c_ro = ro()
    all_sess = [d for d, _ in sessions(c_ro)]
    syms = sorted(poly_syms(c_ro) & set(fleet()))
    bots = {k: v for k, v in bots_available().items() if k in syms}
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    for s in sources:
        if s not in ("bots", "bollinger"):
            raise SystemExit("fuente desconocida: %s (bots|bollinger)" % s)

    rid = args.run_id or run_id_of(args.seed, sources, syms)
    conn = rw()
    ensure_schema(conn)
    done = done_dates(conn, rid)

    if args.dates:
        todo = [d.strip() for d in args.dates.split(",") if d.strip()]
        bad = [d for d in todo if d not in all_sess]
        if bad:
            raise SystemExit("fechas sin barras en poly_bars: %s" % ",".join(bad))
    else:
        todo = [d for d in all_sess if d not in done]
        if args.since:
            todo = [d for d in todo if d >= args.since]
        if args.until:
            todo = [d for d in todo if d <= args.until]
    if args.limit:
        todo = todo[:args.limit]

    sb = args.sandbox or os.path.join(tempfile.gettempdir(), "ibt-regen-%s" % rid)
    make_sandbox(sb)
    print("[regen] run_id=%s seed=%d fuentes=%s" % (rid, args.seed, ",".join(sources)))
    print("[regen] sandbox=%s" % sb)
    print("[regen] %d sesiones pendientes (%d ya hechas)" % (len(todo), len(done)))

    t_all = time.time()
    n_tot = 0
    failed = []
    for i, date in enumerate(todo, 1):
        t_sess = time.time()
        reset_sandbox_session(sb)
        t_start = epoch_of(date, SESS_START)
        t_end = epoch_of(date, SESS_END)
        bars_by_sym = {}
        for s in syms:
            b = load_session_bars(c_ro, s, date, t_start, t_end, args.warm)
            if b:
                bars_by_sym[s] = b
        if not bars_by_sym:
            mark(conn, rid, date, "empty", 0, time.time() - t_sess, "sin barras")
            failed.append("%s: sin barras" % date)
            continue

        rows, fails = [], []
        if "bots" in sources:
            r, f, unmapped = run_bots(sb, date, bars_by_sym, bots)
            rows += r
            fails += f
            if unmapped:
                fails.append("%s bots: lineas sin mapear %s" % (date, unmapped))
        if "bollinger" in sources:
            r, f = run_bollinger(sb, date, bars_by_sym,
                                 epoch_of(date, BOLL_START), epoch_of(date, BOLL_END))
            rows += r
            fails += f

        n = write_signals(conn, classify_rows(rows), rid, args.seed)
        secs = time.time() - t_sess
        n_tot += n
        if fails:
            # una sesion que falla se CUENTA y se NOMBRA (jamas un except: continue que
            # encoja el denominador — la leccion de fleet_consensus 21/26 vs 21/30)
            mark(conn, rid, date, "partial", n, secs, " ; ".join(fails)[:900])
            failed.append("%s: %s" % (date, fails[0][:110]))
        else:
            mark(conn, rid, date, "ok", n, secs)
        el = time.time() - t_all
        print("[regen] %4d/%d %s  n=%-5d %5.1fs  (acum %d señales, %.1f min, ETA %.1f min)%s"
              % (i, len(todo), date, n, secs, n_tot, el / 60,
                 (el / i) * (len(todo) - i) / 60, "  FALLOS" if fails else ""),
              flush=True)

    print("\n[regen] terminado: %d sesiones, %d señales, %.1f min"
          % (len(todo), n_tot, (time.time() - t_all) / 60))
    if failed:
        print("[regen] %d sesiones con fallo (NOMBRADAS, no escondidas):" % len(failed))
        for f in failed[:40]:
            print("   -", f)
    conn.close()
    c_ro.close()


def cmd_nolookahead(args):
    """PRUEBA DEL INVARIANTE: en el instante virtual V, ninguna barra ni nivel del sandbox
    tiene ts + 60 > V. Muestrea el sandbox mientras el reloj avanza."""
    sys.path.insert(0, SHIM)
    from vclock import VClock
    c = ro()
    date = args.date
    syms = sorted((poly_syms(c) & set(fleet())))[:args.nsyms]
    t0, t1 = epoch_of(date, SESS_START), epoch_of(date, SESS_END)
    bars = {}
    for s in syms:
        b = load_session_bars(c, s, date, t0, t1, args.warm)
        if b:
            bars[s.lower()] = b
    if not bars:
        raise SystemExit("sin barras para %s" % date)
    sb = os.path.join(tempfile.gettempdir(), "ibt-regen-nla")
    shutil.rmtree(sb, ignore_errors=True)
    make_sandbox(sb)
    vc = VClock(sb, t0, t1, bars)
    checks = viol = 0
    worst = None
    v = t0
    while v <= t1:
        vc.t = v
        vc.materialize()
        clk = float(open(vc.clock_path()).read().split()[0])
        for s in bars:
            p = os.path.join(sb, "data", "bars_%s_ibkr.txt" % s)
            if not os.path.exists(p):
                continue
            last = None
            with open(p) as f:
                for ln in f:
                    ts = int(ln.split()[0])
                    checks += 1
                    if ts + BAR_S > clk:
                        viol += 1
                        if worst is None or ts + BAR_S - clk > worst[2]:
                            worst = (s, ts, ts + BAR_S - clk)
                    last = ts
            if last is not None and clk - (last + BAR_S) < 0:
                viol += 1
        v += args.step
    vc.close()
    print("=== PRUEBA DE NO-LOOK-AHEAD  %s ===" % date)
    print("simbolos ......... %d   paso ........ %ds" % (len(bars), args.step))
    print("barras revisadas . %d" % checks)
    print("VIOLACIONES ...... %d  %s" % (viol, "" if not viol else "PEOR: %s" % (worst,)))
    print("VEREDICTO ........ %s" % ("SIN LOOK-AHEAD" if viol == 0 else "LOOK-AHEAD DETECTADO"))
    c.close()
    return 0 if viol == 0 else 1


def cmd_verify_replay(args):
    """El feeder de vclock.py debe producir bars_<sym>_ibkr.txt IDENTICO a ./replay --end.
    Asi no se reinventa el arnes: se demuestra equivalente al que ya existe."""
    sys.path.insert(0, SHIM)
    from vclock import VClock
    exe = os.path.join(REPO, "bin", "replay")
    if not os.path.exists(exe):
        raise SystemExit("falta bin/replay (corre scripts/build_replay.sh)")
    date, sym, end = args.date, args.sym.lower(), args.end
    c = ro()
    t0, t1 = epoch_of(date, SESS_START), epoch_of(date, end)
    bars = load_session_bars(c, sym.upper(), date, t0, t1, args.warm)
    c.close()
    if not bars:
        raise SystemExit("sin barras para %s %s" % (sym, date))
    sb_a = os.path.join(tempfile.gettempdir(), "ibt-verify-mine")
    sb_b = os.path.join(tempfile.gettempdir(), "ibt-verify-replay")
    for d in (sb_a, sb_b):
        shutil.rmtree(d, ignore_errors=True)
    make_sandbox(sb_a)
    vc = VClock(sb_a, t1, t1, {sym: bars})
    vc.close()
    p = subprocess.run([exe, "--date", date, "--syms", sym, "--out", sb_b,
                        "--end", end, "--speed", "max", "--warm", str(args.warm),
                        "--chains", "off", "--levels", "off", "--no-ticks", "--quiet"],
                       capture_output=True, text=True, cwd=REPO, timeout=600)
    if p.returncode != 0:
        raise SystemExit("bin/replay fallo: %s" % (p.stderr or p.stdout)[:400])
    fa = os.path.join(sb_a, "data", "bars_%s_ibkr.txt" % sym)
    fb = os.path.join(sb_b, "data", "bars_%s_ibkr.txt" % sym)
    A = [l.split() for l in open(fa).read().split("\n") if l.strip()]
    B = [l.split() for l in open(fb).read().split("\n") if l.strip()]
    print("=== FEEDER vs bin/replay  %s %s hasta %s ===" % (sym.upper(), date, end))
    print("lineas mias .... %d" % len(A))
    print("lineas replay .. %d" % len(B))
    ok = len(A) == len(B)
    dif = 0
    for a, b in zip(A, B):
        # replay imprime con su propio formato; comparamos NUMEROS, no texto
        if a[0] != b[0] or any(abs(float(x) - float(y)) > 1e-4 for x, y in zip(a[1:], b[1:])):
            dif += 1
    print("filas distintas  %d" % dif)
    print("VEREDICTO ...... %s" % ("EQUIVALENTE a bin/replay" if ok and dif == 0
                                   else "DIVERGE — revisar"))
    return 0 if (ok and dif == 0) else 1


def cmd_coincide(args):
    """TASA DE COINCIDENCIA regen vs VIVO en las fechas que existen en las dos.
    Es la prueba de validez: si no se parecen, ese ES el resultado."""
    c = ro()
    try:
        rr = c.execute("SELECT date,source,symbol,ts_epoch,kind,msg FROM signals_regen "
                       "WHERE ts_epoch IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        raise SystemExit("signals_regen no existe todavia")
    live = c.execute("SELECT date,source,symbol,ts_epoch,kind,msg FROM signals "
                     "WHERE ts_epoch IS NOT NULL").fetchall()
    c.close()
    d_regen = {r[0] for r in rr}
    d_live = {r[0] for r in live}
    common = sorted(d_regen & d_live)
    tol = args.tol
    print("=== COINCIDENCIA regen vs VIVO ===")
    print("fechas regen %d | fechas vivo %d | comunes %d" % (len(d_regen), len(d_live), len(common)))
    if not common:
        print("SIN FECHAS COMUNES -> no se puede medir. Corre `run --dates <fecha viva>`.")
        return 1
    print("tolerancia de emparejamiento: +-%d min, mismo (fecha,simbolo,fuente)\n" % (tol // 60))
    hdr = "%-12s %6s %6s %7s %7s  %s"
    print(hdr % ("fuente", "vivo", "regen", "match", "recall", "precision"))
    tot = defaultdict(lambda: [0, 0, 0])
    for src in sorted({r[1] for r in live} | {r[1] for r in rr}):
        L = [r for r in live if r[1] == src and r[0] in common and r[2]]
        R = [r for r in rr if r[1] == src and r[0] in common and r[2]]
        used = set()
        m = 0
        for l in L:
            best, bi = None, None
            for i, g in enumerate(R):
                if i in used or g[0] != l[0] or g[2] != l[2]:
                    continue
                d = abs(g[3] - l[3])
                if d <= tol and (best is None or d < best):
                    best, bi = d, i
            if bi is not None:
                used.add(bi)
                m += 1
        rec = m / len(L) if L else None
        pre = m / len(R) if R else None
        tot[src] = [len(L), len(R), m]
        print(hdr % (src, len(L), len(R), m,
                     "-" if rec is None else "%.0f%%" % (100 * rec),
                     "-" if pre is None else "%.0f%%" % (100 * pre)))
    print("\nLEER ASI: recall = de las señales VIVAS, cuantas reprodujo el arnes. "
          "precision = de las regeneradas, cuantas existieron de verdad.")
    print("Las fuentes con 0 regen son las que NO se pueden regenerar (whale/flow/"
          "structural: exigen cadena de opciones).")
    return 0


def cmd_stats(args):
    c = ro()
    try:
        print("=== signals_regen ===")
        for row in c.execute("SELECT source, count(*), count(DISTINCT date), "
                             "count(DISTINCT symbol||date) FROM signals_regen "
                             "GROUP BY source ORDER BY 2 DESC"):
            print("  %-12s n=%-7d fechas=%-4d clusters=%d" % row)
        n, f = c.execute("SELECT count(*), count(DISTINCT date) FROM signals_regen").fetchone()
        print("  TOTAL        n=%-7d fechas=%d" % (n, f))
        print("\n=== progreso ===")
        for row in c.execute("SELECT run_id,status,count(*),round(avg(secs),1) "
                             "FROM regen_progress GROUP BY run_id,status"):
            print("  %s %-8s %4d sesiones  %.1fs/sesion" % row)
        print("\n=== signals (VIVO, intacta) ===")
        n, f = c.execute("SELECT count(*), count(DISTINCT date) FROM signals").fetchone()
        print("  n=%d fechas=%d" % (n, f))
    finally:
        c.close()


def main():
    ap = argparse.ArgumentParser(description="regeneracion de señales sobre poly_bars")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--dates", default=None, help="lista YYYY-MM-DD,... (si no: pendientes)")
    r.add_argument("--since", default=None)
    r.add_argument("--until", default=None)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--seed", type=int, default=DEFAULT_SEED)
    r.add_argument("--warm", type=int, default=WARM_BARS)
    r.add_argument("--sources", default="bots,bollinger")
    r.add_argument("--sandbox", default=None)
    r.add_argument("--run-id", default=None)
    n = sub.add_parser("nolookahead")
    n.add_argument("--date", required=True)
    n.add_argument("--step", type=int, default=137, help="paso del reloj virtual (s)")
    n.add_argument("--nsyms", type=int, default=3)
    n.add_argument("--warm", type=int, default=WARM_BARS)
    v = sub.add_parser("verify-replay")
    v.add_argument("--date", required=True)
    v.add_argument("--sym", default="qqq")
    v.add_argument("--end", default="11:00")
    v.add_argument("--warm", type=int, default=WARM_BARS)
    co = sub.add_parser("coincide")
    co.add_argument("--tol", type=int, default=600, help="tolerancia en segundos")
    sub.add_parser("stats")
    a = ap.parse_args()
    if a.cmd == "plan":
        return cmd_plan(a)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "nolookahead":
        return cmd_nolookahead(a)
    if a.cmd == "verify-replay":
        return cmd_verify_replay(a)
    if a.cmd == "coincide":
        return cmd_coincide(a)
    if a.cmd == "stats":
        return cmd_stats(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
