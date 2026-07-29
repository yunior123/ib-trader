#!/usr/bin/env python3
"""finviz_valuation.py — snapshot DIARIO de valuacion de la flota via Finviz
Elite export (2026-07-22, mision B5: "no queremos comprar una empresa
inflada; Forward P/E entre otros factores").

UN solo request para toda la flota (t=QQQ,SPY,...) -> data/finviz_valuation.csv.
Pensado para 1x/dia premarket (lo engancha el keepalive; este script NO toca
launchd). Si el CSV existente tiene <24h, NO re-baja (FORCE_VALUATION=1 fuerza).

Columnas (ids verificados empiricamente 2026-07-22 contra el header CSV):
  1=Ticker 2=Company 7=P/E 8=Forward P/E 9=PEG 10=P/S 13=P/FCF
  18=EPS Growth Next Year 30=Short Float 42=Perf Week 43=Perf Month
  57=52-Week High (distancia %) 59=RSI(14) 65=Price
URL: /export/screener (la vieja export.ashx devuelve vacio — skill finviz-elite).
Token: FINVIZ_AUTH3 de feeds.env — JAMAS se imprime en logs.
Degradacion limpia: si el fetch falla, el CSV viejo queda intacto (atomic write)
y se sale con codigo 1 EN VOZ ALTA (stderr) para que el keepalive lo loguee.
SEÑAL-SOLAMENTE: solo datos, jamas ordenes.
"""
import os, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "finviz_valuation.csv")
MAX_AGE_S = 24 * 3600
COLS = "1,2,7,8,9,10,13,18,30,42,43,57,59,65"
MIN_ROWS = 20          # <20 filas de 30 tickers = feed roto, no pisar cache

def token():
    """FINVIZ_AUTH3: env primero, luego feeds.env. Nunca imprimirlo."""
    t = os.environ.get("FINVIZ_AUTH3", "").strip()
    if t:
        return t
    try:
        for ln in open(os.path.join(REPO, "config", "feeds.env")):
            ln = ln.strip()
            if ln.startswith("FINVIZ_AUTH3="):
                return ln.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return ""

def fleet():
    try:
        return [s.upper() for s in
                open(os.path.join(REPO, "data", "fleet.txt")).read().split()]
    except Exception:
        return ["QQQ", "SPY", "NVDA", "MU", "SMH", "DRAM"]

def fresh_enough():
    try:
        return time.time() - os.path.getmtime(OUT) < MAX_AGE_S
    except Exception:
        return False

def main():
    if fresh_enough() and os.environ.get("FORCE_VALUATION") != "1":
        age_h = (time.time() - os.path.getmtime(OUT)) / 3600
        print(f"finviz_valuation: CSV fresco ({age_h:.1f}h < 24h) — no re-bajo.")
        return 0
    auth = token()
    if not auth:
        print("finviz_valuation ROTO: sin FINVIZ_AUTH3 (env ni feeds.env)", file=sys.stderr)
        return 1
    syms = fleet()
    url = (f"https://elite.finviz.com/export/screener?v=152"
           f"&t={','.join(syms)}&auth={auth}&c={COLS}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"finviz_valuation ROTO: fetch fallo ({type(e).__name__})", file=sys.stderr)
        return 1
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines or "Forward P/E" not in lines[0] or len(lines) - 1 < MIN_ROWS:
        # HTML de login / CSV vacio / columnas movidas -> FALLAR EN VOZ ALTA,
        # sin pisar el cache bueno. (Jamas imprimir el body: puede ecoar el token.)
        print(f"finviz_valuation ROTO: respuesta invalida "
              f"({len(lines)-1 if lines else 0} filas, header sin Forward P/E)",
              file=sys.stderr)
        return 1
    lt = time.localtime()
    stamp = (f"# fetched_epoch={int(time.time())} "
             f"fetched_at={lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d} "
             f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}")
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(stamp + "\n" + "\n".join(lines) + "\n")
    os.replace(tmp, OUT)
    print(f"finviz_valuation OK: {len(lines)-1} filas -> {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
