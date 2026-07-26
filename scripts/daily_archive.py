#!/usr/bin/env python3
"""daily_archive.py — archivo HISTORICO diario para backtesting (orden Yunior
2026-07-22: "store the data of options chain, gexa, levels, charts data daily").

Cada corrida crea/actualiza data/history/YYYY-MM-DD/ con:
  - opt_chain_<sym>.txt        (cadenas: ultima foto del dia, + fotos horarias
                                que deja opt_chain_cache si estan)
  - gex_snapshot.json          (regimen gamma del dia, MEDIDO en casa con las griegas
                                reales de Polygon — gexa.ai jubilado el 2026-07-25; los
                                dias anteriores conservan su `gexa_snapshot.json`)
  - opt_flow.txt, opt_whale_state.json
  - levels.json                (muros OI top, max pain, P/C, y el mapa gamma del dia bajo
                                la clave `gex` + `gex_src` con su PROCEDENCIA: medido en
                                casa o scrape historico de gexa)
  - bars/<sym>.txt             (SOLO las barras 1m de HOY por simbolo)
  - nbbo_hist_qqq.txt          (ticks del dia si la grabadora esta viva)
  - whale_alerts.jsonl / whale_flow_hist.jsonl  (slice de hoy)
  - signals.txt                (el log de señales del Desktop de hoy)
  - ranking.json + WHALES-WEEK del dia si existen

Idempotente (re-correr solo re-copia). Degradacion limpia: lo que falte se
salta con aviso, jamas revienta. Cron: com.ibtrader.archive 16:10 ET.
Manual: ./venv/bin/python scripts/daily_archive.py [--date YYYY-MM-DD]
"""
import argparse, glob, json, os, shutil, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
DATA = os.path.join(REPO, "data")

# ruta derivada (repunto 2026-07-26): mismo nombre que print_mon_plans.sh /
# price_alarm.cpp / chart_bridge.py. Candidatos por orden: carpeta nueva,
# raiz vieja del Desktop (pre-repunto), archivo/ (carpetas ya movidas).
IBT_DESKTOP_HOY = os.environ.get("IBT_DESKTOP_HOY", os.path.expanduser("~/Desktop/ib-trader/hoy"))


def ranking_json_candidates(date):
    return [
        os.path.join(IBT_DESKTOP_HOY, f"planes-{date}", "ranking.json"),
        os.path.expanduser(f"~/Desktop/planes-{date}/ranking.json"),
        os.path.expanduser(f"~/Desktop/ib-trader/archivo/planes-{date}/ranking.json"),
    ]


def find_ranking_json(date):
    """Primer candidato que exista y no este vacio. None si ninguno (nunca revienta)."""
    for p in ranking_json_candidates(date):
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return p
        except OSError:
            continue
    return None


def archive_ranking(hdir, date):
    """cp del ranking.json del dia; si no aparece en ningun candidato, GRITA
    (CRITICAL a stderr) en vez de callar (orden Yunior 2026-07-26)."""
    rk = find_ranking_json(date)
    if rk:
        return cp(rk, hdir)
    print(f"CRITICAL: ranking.json NO ENCONTRADO para {date} en ninguna ruta "
          f"({', '.join(ranking_json_candidates(date))}) — archivo del dia SIN ranking",
          file=sys.stderr)
    return False

# mapa gamma del dia: primero el nuestro (MEDIDO), y para los dias ya archivados antes del
# 2026-07-25 se admite el fichero de gexa.ai. La PROCEDENCIA viaja con el dato.
GEX_FILES = (
    ("gex_snapshot.json", "gex_snapshot.json (MEDIDO en casa: griegas reales de Polygon + gex_core)"),
    ("gexa_snapshot.json", "gexa_snapshot.json (scrape historico de gexa.ai, jubilado el 2026-07-25)"),
)

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

def read_gex_map(hdir):
    """El mapa gamma del dia archivado, con su procedencia: (mapa, src) o (None, None).
    Prefiere `gex_snapshot.json` (MEDIDO) y cae a `gexa_snapshot.json` para los dias
    historicos que solo tienen ese. Devuelve None —nunca {}— si no hay nada legible: un
    dict vacio se leeria como "no habia gamma ese dia", que es otra afirmacion."""
    for fn, src in GEX_FILES:
        p = os.path.join(hdir, fn)
        if not (os.path.exists(p) and os.path.getsize(p) > 2):
            continue
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            print(f"  gex map {fn} ILEGIBLE: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not isinstance(d, dict):
            print(f"  gex map {fn} no es un objeto JSON", file=sys.stderr)
            continue
        m = {k: v for k, v in d.items() if k != "_meta" and isinstance(v, dict)}
        if m:
            return m, src
        print(f"  gex map {fn} sin simbolos utiles", file=sys.stderr)
    return None, None

def build_levels(hdir, date):
    """levels.json desde las cadenas archivadas: muros top-3, max pain, P/C + el mapa gamma
    del dia (clave `gex`) con su procedencia (`gex_src`). Sin mapa: la clave va a None y se
    dice en la cabecera — jamas un flip/regimen inventado."""
    levels = {}
    gmap, gsrc = read_gex_map(hdir)
    if gmap is None:
        print("  levels: SIN mapa gamma archivado -> gex=None (no se inventa flip/regimen)",
              file=sys.stderr)
    else:
        print(f"  levels: mapa gamma de {gsrc} ({len(gmap)} simbolos)")
    for p in glob.glob(os.path.join(hdir, "opt_chain_*.txt")):
        sym = os.path.basename(p)[10:-4].upper()
        if "_" in sym: continue          # fotos horarias: solo la principal
        try:
            spot, exp0, rows = None, None, []      # spot None si no se lee: 0.0 seria mentira
            for ln in open(p):
                if ln.startswith("#"):
                    if "spot " in ln:
                        try: spot = float(ln.split("spot ")[1].split(" |")[0].split()[0])
                        except (IndexError, ValueError) as e:
                            print(f"  levels {sym}: cabecera sin spot legible ({type(e).__name__})",
                                  file=sys.stderr)
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
                                      + sum(max(0, s - k) * poi.get(s, 0) for s in ks)) if ks else None
            toc = sum(coi.values()); top = sum(poi.values())
            gsym = (gmap or {}).get(sym)
            levels[sym] = {"spot": spot, "exp": exp0,
                           "call_walls": [[r[0], int(r[4])] for r in cs],
                           "put_walls":  [[r[0], int(r[4])] for r in ps],
                           "max_pain": mp, "pc_oi": round(top / max(toc, 1), 3),
                           # `gex` sustituye a la vieja clave `gexa` (2026-07-25). La
                           # procedencia viaja PEGADA al dato: medido en casa vs scrape.
                           "gex": gsym, "gex_src": gsrc if gsym else None}
        except Exception as e:
            print(f"  levels {sym}: {e}", file=sys.stderr)
    out = {"date": date, "ts": int(time.time()), "gex_source": gsrc, "levels": levels}
    dst = os.path.join(hdir, "levels.json")
    tmp = dst + ".tmp"                                   # escritura ATOMICA
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, dst)
    return len(levels)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a = ap.parse_args()
    t0, t1 = day_bounds(a.date)
    hdir = os.path.join("data", "history", a.date)
    os.makedirs(os.path.join(hdir, "bars"), exist_ok=True)
    print(f"archivo -> {hdir}")

    # cadenas (ultima foto) + mapa gamma MEDIDO + flow + estado ballenas
    for p in glob.glob("data/opt_chain_*.txt"): cp(p, hdir, warn=False)
    cp(os.path.join(DATA, "gex_snapshot.json"), hdir)
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
    cp(os.path.join(DATA, "trading-signals", f"{a.date}.txt"), hdir, warn=False)
    archive_ranking(hdir, a.date)
    cp(os.path.join(REPO, "docs", f"WHALES-WEEK-{a.date}.md"), hdir, warn=False)

    # calibracion de flow_pulse (aditivo, degradacion limpia pero NUNCA muda)
    try:
        subprocess.run([os.path.join(REPO, "venv", "bin", "python"),
                        os.path.join(REPO, "scripts", "flow_pulse_calibrate.py"), a.date],
                       timeout=120, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  flow_pulse_calibrate no corrio: {type(e).__name__}: {e}", file=sys.stderr)

    nl = build_levels(hdir, a.date)
    print(f"OK: {nb} simbolos de barras, {nl} simbolos en levels.json")
    print("\n".join("  " + x for x in sorted(os.listdir(hdir))[:40]))

if __name__ == "__main__":
    main()
