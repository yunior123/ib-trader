#!/usr/bin/env python3
"""options_hunter.py — cazador de candidatos JUGOSOS para opciones (2026-07-18).

NO ACTIVADO en keepalives (orden Yunior: "for the future"). Correr a mano:
    ./venv/bin/python scripts/options_hunter.py [N]

Filosofía: dinero en la subida O en la caída — lo que buscamos es MOVIMIENTO
con opciones LÍQUIDAS (spreads finos), no dirección. La dirección la sugiere
el propio dato (bias CALL/PUT) y la decide el humano con el playbook.

Filtros duros (lecciones del backtest 2026-07-18 + ley de liquidez):
  - optionable + avg vol >= 2M accs/día  → cadenas con spreads finos
  - market cap >= 2B                     → sin micro-basura (7% win la mata)
  - precio >= 15                         → strikes decentes, sin chatarra
  - volatilidad semanal >= 4%            → jugo real para el premium
Lanes:
  A jugosas      : movimiento HOY con rvol alto (momentum vivo, cualquier lado)
  B catalizador  : earnings <=5 días (IV en rampa; jugar direccional o vender crush)

Score = rvol × |change| × log10($vol) — acción real, no ilusión.
Ley Finviz: export 1 llamada/lane, >=60s entre llamadas, cache 15 min.
Señal-solamente: imprime y escribe data/options_picks.txt. Jamás ordena.
"""
import csv, io, math, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
CACHE_S = 900

def auth():
    for line in open("feeds.env"):
        line = line.strip()
        for k in ("FINVIZ_AUTH3", "FINVIZ_AUTH"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("SIN TOKEN finviz (feeds.env)")

# c=: 1 Ticker, 6 MCap, 42 PerfW, 59 RSI, 60 ChgOpen, 63 AvgVol, 64 RelVol,
#     65 Price, 66 Change, 67 Volume, 68 Earnings (mapa validado 2026-07-18)
COLS = "1,6,42,59,60,63,64,65,66,67,68"
BASE = ("https://elite.finviz.com/export/screener?v=152&f={f}&auth={a}&c=" + COLS)
LANES = {
    "jugosas": "sh_opt_option,sh_avgvol_o2000,sh_price_o15,cap_midover,"
               "ta_volatility_wo4,sh_relvol_o1.5",
    "catalizador": "sh_opt_option,sh_avgvol_o1000,sh_price_o15,cap_midover,"
                   "earningsdate_nextdays5,ta_volatility_wo3",
}

def fetch(lane, filt):
    cache = f"data/options_hunt_{lane}.csv"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < CACHE_S:
        return open(cache).read()
    stamp = "data/.finviz_last_call"
    if os.path.exists(stamp):
        wait = 61 - (time.time() - os.path.getmtime(stamp))
        if wait > 0:
            time.sleep(wait)                    # ley: >=60s entre llamadas
    url = BASE.format(f=filt, a=auth())
    r = subprocess.run(["curl", "-s", "--max-time", "20", url],
                       capture_output=True, text=True)
    open(stamp, "w").close()
    body = r.stdout
    if not body.startswith('"Ticker"'):
        sys.exit(f"FINVIZ ROTO lane {lane}: {body[:100]!r}")   # fail-loud (ley 2)
    open(cache, "w").write(body)
    return body

def num(s):
    # caza de bugs 2026-07-28: devolvia 0.0 en cualquier fallo de parseo, indistinguible de
    # "el campo real es 0" -- un RSI ilegible pasaba como "0 = sobrevendido" (falso positivo) y
    # un Change/Change-from-Open ilegible forzaba bias MIXTO en vez de "sin dato" (regla #3).
    try:
        return float(str(s).replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return None

def parse(lane, body):
    rows = []
    for r in csv.DictReader(io.StringIO(body)):
        px, chg = num(r.get("Price")), num(r.get("Change"))
        rvol, vol = num(r.get("Relative Volume")), num(r.get("Volume"))
        # sin precio/volumen/rvol/change fiables no hay score ni gate de $ que calcular de
        # verdad -- se descarta la fila entera en vez de fabricar un 0.0 que parezca dato real.
        if px is None or vol is None or rvol is None or chg is None:
            continue
        dollar = px * vol
        if dollar < 30e6:                      # $30M negociados hoy mínimo
            continue
        score = rvol * max(abs(chg), 0.3) * math.log10(max(dollar, 10))
        chg_open = num(r.get("Change from Open"))
        rsi = num(r.get("Relative Strength Index (14)"))
        if chg_open is None:
            bias = "SINDATO"                   # no se sabe si confirma -- distinto de MIXTO (si se sabe y discrepa)
        elif chg > 0 and chg_open > 0:
            bias = "CALL"
        elif chg < 0 and chg_open < 0:
            bias = "PUT"
        else:
            bias = "MIXTO"
        if rsi is not None:
            if rsi >= 75:
                bias += "!sobrecomprado"       # ley flujo: techo local probable
            elif rsi <= 25:
                bias += "!sobrevendido"
        perfw = num(r.get("Performance (Week)"))
        rows.append({"sym": r["Ticker"], "lane": lane, "px": px, "chg": chg,
                     "rvol": rvol, "rsi": rsi if rsi is not None else float("nan"),
                     "perfw": perfw if perfw is not None else float("nan"),
                     "dollar_m": dollar / 1e6, "earn": r.get("Earnings Date", ""),
                     "score": score, "bias": bias})
    return rows

allr = []
for lane, filt in LANES.items():
    allr += parse(lane, fetch(lane, filt))
best = {}
for r in allr:                                  # dedupe: mejor score gana
    if r["sym"] not in best or r["score"] > best[r["sym"]]["score"]:
        best[r["sym"]] = r
top = sorted(best.values(), key=lambda r: -r["score"])[:N]

out = [f"# options_picks — {time.strftime('%Y-%m-%d %H:%M')} (señal-only, humano decide)",
       f"# {'SYM':<6} {'LANE':<12} {'BIAS':<18} {'PX':>8} {'CHG%':>6} {'RVOL':>5} "
       f"{'RSI':>4} {'PERFW%':>7} {'$VOL(M)':>8}  EARNINGS"]
for r in top:
    out.append(f"{r['sym']:<8} {r['lane']:<12} {r['bias']:<18} {r['px']:>8.2f} "
               f"{r['chg']:>6.1f} {r['rvol']:>5.1f} {r['rsi']:>4.0f} "
               f"{r['perfw']:>7.1f} {r['dollar_m']:>8.0f}  {r['earn']}")
print("\n".join(out))
open("data/options_picks.txt", "w").write("\n".join(out) + "\n")
print(f"\n→ data/options_picks.txt ({len(top)} candidatos de {len(best)} únicos)")
