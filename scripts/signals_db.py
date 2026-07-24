#!/usr/bin/env python3
"""signals_db.py — captura TODAS las señales/alarmas/notificaciones en trades.db
para el backtest del software completo (orden Yunior 2026-07-23).

Fuente: los archivos planos ~/Desktop/trading-signals/YYYY-MM-DD.txt donde TODOS los
emisores (signal bots, opt_whale_watch, price_alarm, bollinger/band, flow, dip) ya
escriben cada evento como  `HH:MM:SS | <tipo> | <mensaje>`.

Tablas nuevas en trades.db (ADITIVO, no toca las existentes):
  signals(id, ts_epoch, ts_txt, date, kind, symbol, price, priority, source, msg, raw, UNIQUE(date,ts_txt,msg))
  voice_log(id, ts_epoch, action, priority, msg)   <- lo llena voice_queue.sh (qué se habló/descartó)

Modos:
  python3 scripts/signals_db.py --init           crea las tablas
  python3 scripts/signals_db.py --backfill        ingiere TODOS los .txt históricos
  python3 scripts/signals_db.py --backfill-today  solo hoy
  python3 scripts/signals_db.py --daemon          tail en vivo del archivo de HOY (poll 2s)
  python3 scripts/signals_db.py --stats           resumen (para el backtest 4pm)

SEÑAL-SOLAMENTE: solo lee archivos y escribe en la BD local. Cero red, cero órdenes.
"""
import os, re, sys, time, glob, sqlite3, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
DB = os.path.join(REPO, "trades.db")
SIGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
FLEET = open("data/fleet.txt").read().split() if os.path.exists("data/fleet.txt") else []
FLEET_SET = set(FLEET)

# tipo de evento -> prioridad y fuente (heurística por el emoji/etiqueta del kind)
def classify(kind, msg):
    k = (kind or "").upper()
    blob = (kind or "") + " " + (msg or "")
    pr = "SIGNAL"
    if any(t in blob for t in ("🐋", "BALLENA", "🚀", "SPIKE", "🩸", "DIP REAL", "TERREMOTO", "DISPARADA", "⏰", "SIRENA")):
        pr = "DANGER"
    elif any(t in k for t in ("MUTED", "VETO", "INFO", "NOTA")):
        pr = "INFO"
    src = "signal"
    if "🐋" in blob or "BALLENA" in blob: src = "whale"
    elif "SPIKE" in blob: src = "flow"
    elif "BB " in blob or "BANDA" in blob or "REBOTE" in blob: src = "bollinger"
    elif "DIP" in blob: src = "dip"
    elif "TERREMOTO" in blob or "CUSUM" in blob: src = "cusum"
    elif "DISPARADA" in blob or "⏰" in blob: src = "price_alarm"
    return pr, src

def extract_symbol(kind, msg):
    for tok in re.findall(r"\b[A-Z]{1,5}\b", (kind or "") + " " + (msg or "")):
        if tok in FLEET_SET:
            return tok
    return None

def extract_price(msg):
    # "px 175.70", "en 391.68", "en 282.20", "high de ... 380.21", primer decimal razonable
    m = re.search(r"(?:px|en|@|precio)\s+\$?(\d{1,6}\.\d{1,2})", msg or "", re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"\b(\d{1,6}\.\d{2})\b", msg or "")
    return float(m.group(1)) if m else None

def connect():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_epoch REAL, ts_txt TEXT, date TEXT, kind TEXT, symbol TEXT,
        price REAL, priority TEXT, source TEXT, msg TEXT, raw TEXT,
        UNIQUE(date, ts_txt, msg))""")
    c.execute("""CREATE TABLE IF NOT EXISTS voice_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_epoch REAL, action TEXT, priority TEXT, msg TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_sig_date ON signals(date)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_sig_sym ON signals(symbol)")
    c.commit()

def parse_line(line, date):
    line = line.rstrip("\n")
    if not line.strip() or line.lstrip().startswith("#"):
        return None
    parts = line.split(" | ")
    if len(parts) >= 3:
        ts_txt, kind, msg = parts[0].strip(), parts[1].strip(), " | ".join(parts[2:]).strip()
    elif len(parts) == 2:
        ts_txt, kind, msg = parts[0].strip(), "", parts[1].strip()
    else:
        m = re.match(r"^(\d{2}:\d{2}:\d{2})\s+(.*)$", line.strip())
        if not m:
            return None
        ts_txt, kind, msg = m.group(1), "", m.group(2)
    if not re.match(r"^\d{2}:\d{2}:\d{2}$", ts_txt):
        return None
    try:
        ep = dt.datetime.strptime(f"{date} {ts_txt}", "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        ep = None
    pr, src = classify(kind, msg)
    return (ep, ts_txt, date, kind, extract_symbol(kind, msg), extract_price(msg), pr, src, msg, line)

def ingest_file(c, path):
    date = os.path.basename(path)[:10]
    n = 0
    with open(path, errors="replace") as f:
        for line in f:
            row = parse_line(line, date)
            if not row:
                continue
            try:
                c.execute("""INSERT OR IGNORE INTO signals
                    (ts_epoch,ts_txt,date,kind,symbol,price,priority,source,msg,raw)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", row)
                if c.total_changes:
                    n += c.execute("SELECT changes()").fetchone()[0]
            except Exception:
                pass
    c.commit()
    return n

def backfill(c, today_only=False):
    files = [f"{SIGDIR}/{dt.date.today():%Y-%m-%d}.txt"] if today_only \
        else sorted(glob.glob(f"{SIGDIR}/*.txt"))
    tot = 0
    for p in files:
        if os.path.exists(p):
            k = ingest_file(c, p)
            tot += k
            print(f"  {os.path.basename(p)}: +{k}")
    print(f"-> {tot} señales nuevas ingeridas")

def daemon(c):
    print(f"[signals_db] daemon tail — poll 2s, BD {DB}")
    offsets = {}
    while True:
        path = f"{SIGDIR}/{dt.date.today():%Y-%m-%d}.txt"
        if os.path.exists(path):
            date = os.path.basename(path)[:10]
            off = offsets.get(path, 0)
            sz = os.path.getsize(path)
            if sz < off:   # archivo rotado/reescrito
                off = 0
            if sz > off:
                with open(path, errors="replace") as f:
                    f.seek(off)
                    for line in f:
                        row = parse_line(line, date)
                        if row:
                            try:
                                c.execute("""INSERT OR IGNORE INTO signals
                                    (ts_epoch,ts_txt,date,kind,symbol,price,priority,source,msg,raw)
                                    VALUES (?,?,?,?,?,?,?,?,?,?)""", row)
                            except Exception:
                                pass
                    offsets[path] = f.tell()
                c.commit()
        time.sleep(2)

def stats(c):
    print("=== SIGNALS DB (para backtest 4pm) ===")
    tot = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    print(f"total señales: {tot}")
    print("por día:")
    for d, n in c.execute("SELECT date,COUNT(*) FROM signals GROUP BY date ORDER BY date DESC LIMIT 5"):
        print(f"  {d}: {n}")
    print("hoy por fuente:")
    today = f"{dt.date.today():%Y-%m-%d}"
    for s, n in c.execute("SELECT source,COUNT(*) FROM signals WHERE date=? GROUP BY source ORDER BY n DESC", (today,)) if False else \
                c.execute("SELECT source,COUNT(*) as n FROM signals WHERE date=? GROUP BY source ORDER BY n DESC", (today,)):
        print(f"  {s}: {n}")
    vt = c.execute("SELECT COUNT(*) FROM voice_log").fetchone()[0]
    print(f"voice_log filas: {vt}")
    if vt:
        for a, n in c.execute("SELECT action,COUNT(*) FROM voice_log GROUP BY action"):
            print(f"  voz {a}: {n}")

def main():
    args = set(sys.argv[1:])
    c = connect(); init(c)
    if "--daemon" in args:
        daemon(c)
    elif "--backfill" in args:
        backfill(c)
    elif "--backfill-today" in args:
        backfill(c, today_only=True)
    elif "--stats" in args:
        stats(c)
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
