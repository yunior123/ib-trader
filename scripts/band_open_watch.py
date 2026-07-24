#!/usr/bin/env python3
"""band_open_watch.py — patron de Yunior (2026-07-22): apertura FUERA de las
bandas de Bollinger 15m RTH (ancladas al cierre de ayer, como TradingView sin
extended hours) tiende a volver DENTRO.

PROBABILIDADES MEDIDAS (estudio 30d x flota, data/band_snap_stats.json):
  - se acerca a la banda en 30min: 60% | recorre >=50% del gap: 36%
  - señal fina = RE-ENTRADA impresa (1er cierre 1m dentro): avanza a la media 56%
  - CONTEXTO, no gatillo (doctrina patrones); earnings del ticker lo anula.

Corre 9:29-10:35 ET (keepalive lo lanza a diario). Por simbolo, maximo 2 cantos:
  1) 9:30+: "APERTURA FUERA DE BANDA {sym}" (prob 60/36 medida) — MIRAR
  2) cuando imprime la re-entrada: "RE-ENTRADA {sym} -> media {mid}" (prob 56)
SEÑAL-SOLAMENTE. Degradacion limpia si falta data de un simbolo.
"""
import os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from optgate import opt_vehicle    # gate de spread: verificar SIEMPRE antes de sugerir opciones

def fleet():
    try:
        return [s.lower() for s in open("data/fleet.txt").read().split()]
    except Exception:
        return ["qqq", "spy", "nvda", "mu", "smh", "dram"]

def say(title, msg, sound="ProAlert"):
    subprocess.Popen(["/bin/bash", "scripts/speak.sh", "SIGNAL", msg],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      f'display notification "{msg}" with title "{title}" sound name "{sound}"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt = time.localtime()
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")

def bars_of(sym):
    try:
        rows = [l.split() for l in open(f"data/bars_{sym}_ibkr.txt")]
        return [(int(float(r[0])), float(r[1]), float(r[4])) for r in rows if len(r) >= 6]
    except Exception:
        return []


def vol_confirm(sym):
    """Filtro de Yoel (est 5-8): la vela gatillo solo vale si su VOLUMEN cruza la
    MA50 del volumen. Medido 2026-07-23: +10pp en movimiento >=1.5 ATR a favor
    (37->47%), 29/30 tickers. Devuelve (ok, texto). Degradacion limpia: sin
    volumen suficiente -> (True, '') para no vetar de mas."""
    try:
        rows = [l.split() for l in open(f"data/bars_{sym}_ibkr.txt").readlines()[-60:]]
        vols = [float(r[5]) for r in rows if len(r) >= 6]
        if len(vols) < 51:
            return True, ""
        ma50 = sum(vols[-51:-1]) / 50
        cur = vols[-1]
        if ma50 <= 0:
            return True, ""
        if cur > ma50:
            return True, f" Volumen CONFIRMA (x{cur/ma50:.1f} la MA50, +10pp medido)"
        return False, f" volumen debil (x{cur/ma50:.1f} MA50) — sin confirmacion Yoel"
    except Exception:
        return True, ""

def bb15_prev_rth(bars, day0):
    """BB(20,2) de los 15m RTH del dia ANTERIOR (ultimas 20 velas hasta 16:00)."""
    prev_start, prev_end = day0 - 86400 + 9.5 * 3600, day0 - 86400 + 16 * 3600
    # si ayer fue finde, retroceder hasta hallar sesion con datos (max 4 dias)
    for back in range(1, 5):
        s, e = day0 - back * 86400 + 9.5 * 3600, day0 - back * 86400 + 16 * 3600
        rth = [(t, o, c) for t, o, c in bars if s <= t < e]
        if len(rth) >= 200:
            agg = {}
            for t, o, c in rth:
                k = t - t % 900
                agg.setdefault(k, [o, c])[1] = c
            closes = [v[1] for k, v in sorted(agg.items())][-20:]
            if len(closes) >= 20:
                m = sum(closes) / 20
                sd = (sum((c - m) ** 2 for c in closes) / 20) ** .5
                return m - 2 * sd, m, m + 2 * sd
    return None

def main():
    lt = time.localtime()
    day0 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    open930 = day0 + 9.5 * 3600
    state = {}   # sym -> {"out": lado, "band": px, "mid": px, "reentered": bool}
    while True:
        now = time.time()
        lt = time.localtime()
        hm = lt.tm_hour * 100 + lt.tm_min
        if hm >= 1035 or lt.tm_wday >= 5:
            break
        if hm >= 930:
            for sym in fleet():
                if sym in state and state[sym].get("done"):
                    continue
                bars = bars_of(sym)
                if not bars or now - bars[-1][0] > 240:
                    continue
                if sym not in state:
                    bbp = bb15_prev_rth(bars, day0)
                    o930 = next((o for t, o, c in bars if t >= open930), None)
                    if not bbp or not o930:
                        continue
                    lo, mid, up = bbp
                    out = "abajo" if o930 < lo else "arriba" if o930 > up else None
                    state[sym] = {"out": out, "lo": lo, "mid": mid, "up": up, "done": out is None}
                    if out:
                        band = lo if out == "abajo" else up
                        say("🎯 APERTURA FUERA DE BANDA",
                            f"{sym.upper()} abrio {o930:.2f} {out} de la banda 15m ({band:.2f}). "
                            f"Patron medido: 60 por ciento se acerca en 30 minutos. "
                            f"Esperar la re-entrada impresa, no perseguir")
                    continue
                st = state[sym]
                if st.get("out") and not st.get("done"):
                    band = st["lo"] if st["out"] == "abajo" else st["up"]
                    last_close = bars[-1][2]
                    if (st["out"] == "abajo" and last_close >= band) or \
                       (st["out"] == "arriba" and last_close <= band):
                        vok, vtxt = vol_confirm(sym)
                        say("🎯 RE-ENTRADA A BANDA" + (" +VOL" if vok and vtxt else ""),
                            f"{sym.upper()} imprimio re-entrada en {last_close:.2f}. "
                            f"Target la media {st['mid']:.2f}, prob medida 56 por ciento."
                            f"{vtxt} Contexto, no gatillo: pedir confluencia. {opt_vehicle(sym)}",
                            "ProChord")
                        st["done"] = True
        time.sleep(20)

if __name__ == "__main__":
    main()
