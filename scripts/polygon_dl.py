#!/usr/bin/env python3
"""polygon_dl.py — descarga histórico de Polygon y lo GUARDA en trades.db (orden Yunior
2026-07-24: "estar descargando y guardando a nuestra db" para backtest realtime).

Tablas nuevas (ADITIVO):
  poly_bars(sym, ts, o, h, l, c, v, PRIMARY KEY(sym, ts))           barras del subyacente
  poly_opt_bars(otk, sym, exp, strike, right, ts, o,h,l,c,v, PK(otk,ts))  barras de opción
  poly_dl_log(sym, kind, d0, d1, rows, ts)                          registro de descargas

Incremental + resumible: solo baja lo que falta (mira el último ts en la BD).
Rate-limit aware (Polygon free = 5 req/min; con --sleep ajustable). SEÑAL-SOLAMENTE.

Uso:
  python3 scripts/polygon_dl.py bars [--days 30] [--tf 1] [--syms QQQ SPY NVDA]   barras subyacente
  python3 scripts/polygon_dl.py opts --sym NVDA [--days 5] [--tf 5]               barras de opciones ATM
  python3 scripts/polygon_dl.py stats                                             qué hay en la BD
"""
import os, sys, json, time, sqlite3, urllib.request, urllib.parse, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
DB = os.path.join(REPO, "trades.db")
FLEET = open("data/fleet.txt").read().split() if os.path.exists("data/fleet.txt") else []

def _key():
    for src in ("feeds.env", "polygon.env"):
        p = os.path.join(REPO, src)
        if os.path.exists(p):
            for ln in open(p):
                if ln.startswith("POLYGON_KEY"):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    k = os.environ.get("POLYGON_KEY")
    if k:
        return k
    raise SystemExit("falta POLYGON_KEY en feeds.env")

KEY = _key()
SLEEP = float(os.environ.get("POLY_SLEEP", "13"))   # 5 req/min free; plan pagado ~0.2. Override: POLY_SLEEP=0.5

def poly(url, tries=4):
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}apiKey={KEY}"
    for i in range(tries):
        try:
            with urllib.request.urlopen(full, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:   # rate limit -> esperar y reintentar
                time.sleep(SLEEP * (i + 1)); continue
            if e.code in (403, 401):
                raise SystemExit(f"Polygon {e.code}: key sin acceso a este endpoint")
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return None

def db():
    c = sqlite3.connect(DB, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS poly_bars(
        sym TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
        PRIMARY KEY(sym, ts))""")
    c.execute("""CREATE TABLE IF NOT EXISTS poly_opt_bars(
        otk TEXT, sym TEXT, exp TEXT, strike REAL, right TEXT, ts INTEGER,
        o REAL, h REAL, l REAL, c REAL, v REAL, PRIMARY KEY(otk, ts))""")
    c.execute("""CREATE TABLE IF NOT EXISTS poly_dl_log(
        sym TEXT, kind TEXT, d0 TEXT, d1 TEXT, rows INTEGER, ts REAL)""")
    return c

def last_ts(c, table, key_col, key):
    r = c.execute(f"SELECT MAX(ts) FROM {table} WHERE {key_col}=?", (key,)).fetchone()
    return r[0] if r and r[0] else None

def dl_bars(syms, days, tf):
    c = db()
    d1 = dt.date.today()
    d0 = d1 - dt.timedelta(days=days)
    tot = 0
    for sym in syms:
        # incremental: si ya hay datos, arranca desde el día siguiente al último
        lt = last_ts(c, "poly_bars", "sym", sym.upper())
        start = d0
        if lt:
            start = max(d0, dt.date.fromtimestamp(lt / 1000) )
        url = (f"https://api.polygon.io/v2/aggs/ticker/{sym.upper()}/range/{tf}/minute/"
               f"{start:%Y-%m-%d}/{d1:%Y-%m-%d}?adjusted=true&sort=asc&limit=50000")
        d = poly(url)
        res = (d or {}).get("results") or []
        n = 0
        for b in res:
            try:
                c.execute("INSERT OR IGNORE INTO poly_bars VALUES(?,?,?,?,?,?,?)",
                          (sym.upper(), int(b["t"]), b["o"], b["h"], b["l"], b["c"], b.get("v", 0)))
                n += 1
            except Exception:
                pass
        c.execute("INSERT INTO poly_dl_log VALUES(?,?,?,?,?,?)",
                  (sym.upper(), f"bars{tf}m", f"{start}", f"{d1}", n, time.time()))
        c.commit()
        tot += n
        print(f"  {sym.upper():6s} {tf}m: +{n} barras [{start}..{d1}]")
        time.sleep(SLEEP)
    print(f"-> {tot} barras guardadas en poly_bars")

def dl_opts(sym, days, tf, band=0.06):
    """Baja barras de las opciones cercanas al ATM (±band) de los vencimientos próximos."""
    c = db()
    sym = sym.upper()
    # spot aprox del último bar
    r = c.execute("SELECT c FROM poly_bars WHERE sym=? ORDER BY ts DESC LIMIT 1", (sym,)).fetchone()
    spot = r[0] if r else None
    if not spot:
        print(f"  {sym}: sin spot en poly_bars — corre 'bars --syms {sym}' primero"); return
    lo, hi = spot * (1 - band), spot * (1 + band)
    d = poly(f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={sym}"
             f"&strike_price.gte={lo:.0f}&strike_price.lte={hi:.0f}&limit=250&expired=false")
    cons = (d or {}).get("results") or []
    d1 = dt.date.today(); d0 = d1 - dt.timedelta(days=days)
    tot = 0
    for k in cons[:40]:
        otk = k["ticker"]
        url = (f"https://api.polygon.io/v2/aggs/ticker/{otk}/range/{tf}/minute/"
               f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}?adjusted=true&sort=asc&limit=50000")
        dd = poly(url); res = (dd or {}).get("results") or []
        n = 0
        for b in res:
            try:
                c.execute("INSERT OR IGNORE INTO poly_opt_bars VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (otk, sym, k.get("expiration_date"), k.get("strike_price"),
                           k.get("contract_type"), int(b["t"]), b["o"], b["h"], b["l"], b["c"], b.get("v", 0)))
                n += 1
            except Exception:
                pass
        c.commit(); tot += n
        if n:
            print(f"  {otk}: +{n}")
        time.sleep(SLEEP)
    print(f"-> {tot} barras de opción guardadas para {sym}")

def stats():
    c = db()
    for t in ("poly_bars", "poly_opt_bars"):
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        syms = c.execute(f"SELECT COUNT(DISTINCT sym) FROM {t}").fetchone()[0] if t == "poly_bars" else \
               c.execute("SELECT COUNT(DISTINCT sym) FROM poly_opt_bars").fetchone()[0]
        print(f"  {t}: {n} filas, {syms} símbolos")
    print("  descargas recientes:")
    for row in c.execute("SELECT sym,kind,rows,datetime(ts,'unixepoch','localtime') FROM poly_dl_log ORDER BY ts DESC LIMIT 6"):
        print("   ", row)

def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    def opt(flag, default):
        return a[a.index(flag) + 1] if flag in a else default
    if cmd == "bars":
        syms = a[a.index("--syms") + 1:] if "--syms" in a else FLEET
        dl_bars(syms, int(opt("--days", 30)), int(opt("--tf", 1)))
    elif cmd == "opts":
        dl_opts(opt("--sym", "NVDA"), int(opt("--days", 5)), int(opt("--tf", 5)))
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
