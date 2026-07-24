#!/usr/bin/env python3
"""backtest_harness.py — backtest de TODAS las señales/engines contra el histórico de
Polygon (poly_bars), con DuckDB IN-MEMORY (medido ~16x vs SQLite). Orden Yunior 2026-07-24:
"full backtesting of engines and bots and alarms... backtest every signal so far".

Flujo:
  1. Carga poly_bars (SQLite) -> DuckDB :memory: (columnar, vectorizado).
  2. Carga TODAS las señales (tabla signals, todas las fechas).
  3. Para cada señal: precio de entrada = close de poly_bars en el instante; resultado a
     +15/+30/+60min; gana si se movió en la dirección de la TESIS (reusa eod_backtest.thesis).
  4. Agrega WR por fuente (Wilson) + guarda en backtest_results + backtest_signal_outcomes.

Uso: python3 scripts/backtest_harness.py [--h 15] [--realtime]
  --realtime: loop continuo (re-corre cada N min a medida que entran señales/datos nuevos).
SEÑAL-SOLAMENTE.
"""
import os, sys, time, math, sqlite3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
DB = os.path.join(REPO, "trades.db")
import eod_backtest as E   # reusa thesis() + wilson()

def _duck():
    import duckdb
    d = duckdb.connect()  # :memory:
    d.execute("INSTALL sqlite; LOAD sqlite;")
    d.execute(f"CREATE TABLE pb AS SELECT * FROM sqlite_scan('{DB}','poly_bars')")
    d.execute("CREATE INDEX ix ON pb(sym, ts)")
    return d

def ensure_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS backtest_results(
        run_ts REAL, source TEXT, horizon INTEGER, n INTEGER, wins INTEGER,
        wr INTEGER, lo INTEGER, hi INTEGER, avg_ret REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS backtest_signal_outcomes(
        run_ts REAL, date TEXT, ts_txt TEXT, symbol TEXT, source TEXT,
        horizon INTEGER, entry REAL, ret REAL, win INTEGER, thesis INTEGER)""")
    c.commit()

def run(horizons=(15, 30, 60)):
    d = _duck()
    have = set(r[0] for r in d.execute("SELECT DISTINCT sym FROM pb").fetchall())
    print(f"[harness] poly_bars: {len(have)} símbolos, {d.execute('SELECT COUNT(*) FROM pb').fetchone()[0]} barras")
    c = sqlite3.connect(DB); ensure_tables(c)
    sigs = c.execute("SELECT ts_epoch, ts_txt, date, kind, source, symbol, msg FROM signals "
                     "WHERE ts_epoch IS NOT NULL ORDER BY ts_epoch").fetchall()
    run_ts = time.time()
    from collections import defaultdict
    agg = {h: defaultdict(lambda: [0, 0, 0.0]) for h in horizons}   # h -> source -> [n, wins, sum_ret]
    skipped = 0
    for ep, ts_txt, date, kind, source, sym, msg in sigs:
        if not sym:
            sym = E.extract_symbol(kind or "", msg or "")
        if not sym or sym not in have:
            skipped += 1; continue
        th, _ = E.thesis(source or "", kind or "", msg or "")
        if th == 0:
            continue
        ms = int(ep * 1000)   # poly_bars.ts está en ms
        # entrada: close de la barra <= señal ; ventana: barras en (t, t+h]
        row = d.execute("SELECT c FROM pb WHERE sym=? AND ts<=? ORDER BY ts DESC LIMIT 1", [sym, ms]).fetchone()
        if not row:
            skipped += 1; continue
        entry = row[0]
        for h in horizons:
            end = ms + h * 60000
            r = d.execute("SELECT c FROM pb WHERE sym=? AND ts>? AND ts<=? ORDER BY ts DESC LIMIT 1",
                          [sym, ms, end]).fetchone()
            if not r:
                continue
            ret = (r[0] - entry) / entry * 100 * th
            win = 1 if ret > 0.05 else 0
            a = agg[h][source]; a[0] += 1; a[1] += win; a[2] += ret
            c.execute("INSERT INTO backtest_signal_outcomes VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (run_ts, date, ts_txt, sym, source, h, entry, round(ret, 3), win, th))
    c.commit()
    # reporte + persistencia agregada
    print(f"\n=== BACKTEST HARNESS (todas las señales, Polygon) — saltadas {skipped} (sin datos poly) ===")
    for h in horizons:
        print(f"\n--- horizonte +{h}min ---")
        tot_n = tot_w = 0
        for src, (n, w, sr) in sorted(agg[h].items(), key=lambda x: -x[1][0]):
            wr, lo, hi = E.wilson(w, n)
            print(f"  {src:11s} n={n:<5d} WR {wr:>3d}% [{lo:>2d},{hi:>3d}]  ret {sr/max(n,1):+.2f}%")
            c.execute("INSERT INTO backtest_results VALUES(?,?,?,?,?,?,?,?,?)",
                      (run_ts, src, h, n, w, wr, lo, hi, round(sr / max(n, 1), 3)))
            tot_n += n; tot_w += w
        if tot_n:
            wr, lo, hi = E.wilson(tot_w, tot_n)
            print(f"  {'TOTAL':11s} n={tot_n:<5d} WR {wr:>3d}% [{lo:>2d},{hi:>3d}]")
            c.execute("INSERT INTO backtest_results VALUES(?,?,?,?,?,?,?,?,?)",
                      (run_ts, "TOTAL", h, tot_n, tot_w, wr, lo, hi, 0.0))
    c.commit(); c.close(); d.close()
    print(f"\n-> guardado en trades.db: backtest_results + backtest_signal_outcomes (run {int(run_ts)})")

def main():
    a = sys.argv[1:]
    hs = (int(a[a.index("--h") + 1]),) if "--h" in a else (15, 30, 60)
    if "--realtime" in a:
        while True:
            run(hs); print("[harness] durmiendo 300s (realtime)…"); time.sleep(300)
    else:
        run(hs)

if __name__ == "__main__":
    main()
