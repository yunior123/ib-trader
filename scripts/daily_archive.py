#!/usr/bin/env python3
"""daily_archive.py — archivo HISTORICO diario para backtesting (orden Yunior
2026-07-22: "store the data of options chain, gexa, levels, charts data daily").

Cada corrida crea/actualiza data/history/YYYY-MM-DD/ con:
  - opt_chain_<sym>.txt        (cadenas: ultima foto del dia, + fotos horarias
                                que deja opt_chain_cache si estan)
  - gexa_snapshot.json         (regimen gamma del dia)
  - opt_flow.txt, opt_whale_state.json
  - levels.json                (muros OI top, max pain, P/C, flip gexa por sym
                                — via whales_week_map ya corrido, o del chain)
  - bars/<sym>.txt             (SOLO las barras 1m de HOY por simbolo)
  - nbbo_hist_qqq.txt          (ticks del dia si la grabadora esta viva)
  - whale_alerts.jsonl / whale_flow_hist.jsonl  (slice de hoy)
  - signals.txt                (el log de señales del Desktop de hoy)
  - ranking.json + WHALES-WEEK del dia si existen

Idempotente (re-correr solo re-copia). Degradacion limpia: lo que falte se
salta con aviso, jamas revienta. Cron: com.ibtrader.archive 16:10 ET.
Manual: ./venv/bin/python scripts/daily_archive.py [--date YYYY-MM-DD]
"""
import argparse, glob, json, os, shutil, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

def day_bounds(date):
    t0 = int(time.mktime(time.strptime(date, "%Y-%m-%d")))
    return t0, t0 + 86400

def cp(src, dstdir, warn=True):
    try:
        if os.path.exists(src) and os.path.getsize(src) > 0:
            shutil.copy2(src, dstdir)
            return True
        if warn: print(f"  skip (no existe/vacio): {src}", file=sys.stderr)
    except Exception as e:
        print(f"  FALLO {src}: {e}", file=sys.stderr)
    return False

def slice_epoch_file(src, dst, t0, t1, col=0):
    """copia solo las lineas cuyo epoch (columna col) cae en el dia."""
    try:
        if not os.path.exists(src): return 0
        n = 0
        with open(src) as f, open(dst, "w") as o:
            for ln in f:
                try:
                    ep = float(ln.split()[col])
                except Exception:
                    continue
                if t0 <= ep < t1:
                    o.write(ln); n += 1
        if n == 0: os.unlink(dst)
        return n
    except Exception as e:
        print(f"  FALLO slice {src}: {e}", file=sys.stderr)
        return 0

def slice_jsonl_ts(src, dst, t0, t1):
    try:
        if not os.path.exists(src): return 0
        n = 0
        with open(dst, "w") as o:
            for ln in open(src):
                try:
                    ts = json.loads(ln).get("ts", 0)
                except Exception:
                    continue
                if t0 <= ts < t1:
                    o.write(ln); n += 1
        if n == 0: os.unlink(dst)
        return n
    except Exception as e:
        print(f"  FALLO slice {src}: {e}", file=sys.stderr)
        return 0

def build_levels(hdir, date):
    """levels.json desde las cadenas archivadas: muros top-3, max pain, P/C + flip gexa."""
    levels = {}
    gexa = {}
    try: gexa = json.load(open(os.path.join(hdir, "gexa_snapshot.json")))
    except Exception: pass
    for p in glob.glob(os.path.join(hdir, "opt_chain_*.txt")):
        sym = os.path.basename(p)[10:-4].upper()
        if "_" in sym: continue          # fotos horarias: solo la principal
        try:
            spot, exp0, rows = 0.0, None, []
            for ln in open(p):
                if ln.startswith("#"):
                    if "spot " in ln:
                        try: spot = float(ln.split("spot ")[1].split(" |")[0].split()[0])
                        except Exception: pass
                    continue
                f = ln.split()
                if len(f) >= 7:
                    rows.append((float(f[0]), f[1], f[2], float(f[5]), float(f[6])))  # k right exp vol oi
            if not rows: continue
            exp0 = rows[0][2]
            cs = sorted([r for r in rows if r[1] == "C"], key=lambda r: -r[4])[:3]
            ps = sorted([r for r in rows if r[1] == "P"], key=lambda r: -r[4])[:3]
            ks = sorted({r[0] for r in rows})
            coi = {r[0]: r[4] for r in rows if r[1] == "C"}
            poi = {r[0]: r[4] for r in rows if r[1] == "P"}
            mp = min(ks, key=lambda k: sum(max(0, k - s) * coi.get(s, 0) for s in ks)
                                      + sum(max(0, s - k) * poi.get(s, 0) for s in ks)) if ks else 0
            toc = sum(coi.values()); top = sum(poi.values())
            levels[sym] = {"spot": spot, "exp": exp0,
                           "call_walls": [[r[0], int(r[4])] for r in cs],
                           "put_walls":  [[r[0], int(r[4])] for r in ps],
                           "max_pain": mp, "pc_oi": round(top / max(toc, 1), 3),
                           "gexa": gexa.get(sym)}
        except Exception as e:
            print(f"  levels {sym}: {e}", file=sys.stderr)
    with open(os.path.join(hdir, "levels.json"), "w") as f:
        json.dump({"date": date, "ts": int(time.time()), "levels": levels}, f, indent=1)
    return len(levels)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a = ap.parse_args()
    t0, t1 = day_bounds(a.date)
    hdir = os.path.join("data", "history", a.date)
    os.makedirs(os.path.join(hdir, "bars"), exist_ok=True)
    print(f"archivo -> {hdir}")

    # cadenas (ultima foto) + gexa + flow + estado ballenas
    for p in glob.glob("data/opt_chain_*.txt"): cp(p, hdir, warn=False)
    cp("data/gexa_snapshot.json", hdir)
    cp("data/opt_flow.txt", hdir)
    cp("data/opt_whale_state.json", hdir, warn=False)

    # barras 1m de HOY por simbolo (charts data)
    nb = 0
    for p in glob.glob("data/bars_*_ibkr.txt"):
        sym = os.path.basename(p)[5:-9]
        nb += 1 if slice_epoch_file(p, os.path.join(hdir, "bars", f"{sym}.txt"), t0, t1) else 0
    # ticks NBBO QQQ del dia
    for p in glob.glob(f"data/nbbo_hist_qqq_{a.date.replace('-','')}*.txt"): cp(p, hdir)
    # ballenas del dia
    slice_jsonl_ts("data/whale_alerts.jsonl", os.path.join(hdir, "whale_alerts.jsonl"), t0, t1)
    slice_jsonl_ts("data/whale_flow_hist.jsonl", os.path.join(hdir, "whale_flow_hist.jsonl"), t0, t1)
    # señales del Desktop + ranking + mapa semanal
    cp(os.path.expanduser(f"~/Desktop/trading-signals/{a.date}.txt"), hdir, warn=False)
    cp(os.path.expanduser(f"~/Desktop/planes-{a.date}/ranking.json"), hdir, warn=False)
    cp(f"docs/WHALES-WEEK-{a.date}.md", hdir, warn=False)

    # calibracion de flow_pulse (aditivo, degradacion limpia)
    try:
        import subprocess
        subprocess.run(["./venv/bin/python", "scripts/flow_pulse_calibrate.py", a.date],
                       timeout=120, capture_output=True)
    except Exception:
        pass

    nl = build_levels(hdir, a.date)
    print(f"OK: {nb} simbolos de barras, {nl} simbolos en levels.json")
    print("\n".join("  " + x for x in sorted(os.listdir(hdir))[:40]))

if __name__ == "__main__":
    main()
