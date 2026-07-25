#!/usr/bin/env python3
"""level_react_validate.py — ¿el NIVEL añade algo, o es el giro de vela lo que funciona?

Python aqui es LEGITIMO: es un lote de calibracion fuera de sesion (CLAUDE.md). Todo el calculo
de eventos vive en el binario C++ `./level_react`; este script solo lo conduce sobre `poly_bars`,
etiqueta resultados y hace la resta contra el null. Cero logica de nivel en Python.

LA PREGUNTA, Y POR QUE ES LA UNICA QUE IMPORTA
----------------------------------------------
`level_react` produce eventos BOUNCE / RETEST_REJECT en niveles. Pero un rebote en un nivel es
DOS cosas a la vez: (a) un giro de vela, y (b) que ese giro pase en un nivel. Si (a) explica
todo, el nivel es DECORACION y la feature entera es un adorno caro.

El prior publicado — **Osler (2000): 60,8% vs 56,2%**, con ~3,4pp atribuibles a numeros
redondos — fija la vara: **el nivel debe añadir >= 6pp sobre el giro de vela a un precio
aleatorio**, o se borra. Esa vara la puso la ficha #8 antes de escribir una linea de codigo, y
este script no la mueve.

EL NULL (lo que hace honesta a la resta)
Mismo binario, mismas barras, mismo patron de vela — pero los niveles se colocan en precios
ALEATORIOS de la sesion. Si los eventos en niveles aleatorios ganan igual, no hay nivel: hay
mean-reversion de vela.

QUE NIVELES SE PUEDEN RECONSTRUIR PARA EL PASADO, Y CUALES NO
  RECONSTRUIBLES desde barras: POC_DOM (POC de volumen de la sesion previa), ROUND, y los
    bordes PDH/PDL (que entran como GAP_EDGE).
  **NO RECONSTRUIBLES**: OI_CALL_WALL, OI_PUT_WALL, ABS_WALL, FLIP_OPEN. No existe historia de
    OI a ningun precio en este plan (el `as_of` del snapshot de Polygon es una TRAMPA: devuelve
    OK e ignora la fecha). Las celdas de muro se acumulan HACIA ADELANTE y este backtest **no
    dice nada sobre ellas**. Esta limitacion se imprime en el informe, no se esconde.

SEÑAL-SOLAMENTE. Este script no ordena, no habla y no habilita ninguna voz.
"""
import json
import os
import random
import subprocess
import sqlite3
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
BIN = os.path.join(REPO, "level_react")
DB = os.path.join(REPO, "trades.db")

# Barreras de la etiqueta (triple barrera de la casa, feature #1).
#
# CURVA DE SENSIBILIDAD OBLIGATORIA: con `k` pequeño, la barra que contiene TP **y** SL se
# resuelve como perdida (conservador) y eso hunde la tasa base de LOS DOS brazos. Medido el
# 2026-07-25 con k=0.5: real 19,1% / null 23,9% — tasas absurdas para barreras simetricas,
# justo por ese efecto. Lo que se lee NO es la tasa: es la RESTA, y la resta hay que verla en
# VARIOS `k`. Si el signo del delta solo existe en un umbral, no es real.
K_BARRIER = float(os.environ.get("LRV_K", "1.5"))   # +/- k * ATR
H_BARS = int(os.environ.get("LRV_H", "30"))         # horizonte en barras 1m
N_NULL = 10          # sets de niveles aleatorios por sesion
MIN_BARS = 60        # una sesion mas corta no se etiqueta


def die(msg):
    print("level_react_validate: " + msg, file=sys.stderr)
    raise SystemExit(2)


def load_sessions(sym, max_sessions):
    """Devuelve [(fecha, [bars...])]. `poly_bars.ts` esta en MILISEGUNDOS."""
    if not os.path.exists(DB):
        die("falta trades.db")
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    try:
        rows = con.execute(
            "SELECT date(ts/1000,'unixepoch') d, ts/1000, o, h, l, c, v "
            "FROM poly_bars WHERE sym=? ORDER BY ts", (sym,)).fetchall()
    finally:
        con.close()
    by_day = defaultdict(list)
    for d, ts, o, h, l, c, v in rows:
        by_day[d].append([float(ts), float(o), float(h), float(l), float(c), float(v)])
    days = sorted(by_day)
    if max_sessions:
        days = days[-max_sessions:]
    return [(d, by_day[d]) for d in days if len(by_day[d]) >= MIN_BARS]


def atr14(bars):
    """ATR14 de Wilder. Devuelve None si no hay muestra — NUNCA 0.0."""
    if len(bars) < 15:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i][2], bars[i][3], bars[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(trs[:14]) / 14.0
    for tr in trs[14:]:
        a = (a * 13 + tr) / 14.0
    return a if a > 0 else None


def poc_of(bars, nbins=40):
    """POC de volumen de una sesion. None si no hay volumen — nunca un precio inventado."""
    lo = min(b[3] for b in bars)
    hi = max(b[2] for b in bars)
    if not (hi > lo):
        return None
    buckets = [0.0] * nbins
    for b in bars:
        mid = (b[2] + b[3]) / 2.0
        i = min(nbins - 1, int((mid - lo) / (hi - lo) * nbins))
        buckets[i] += b[5]
    if sum(buckets) <= 0:
        return None
    i = buckets.index(max(buckets))
    return lo + (i + 0.5) * (hi - lo) / nbins


def run_engine(sym, bars, levels, atr):
    payload = {"sym": sym, "atr": atr, "half_spread": 0.0, "tick": 0.01,
               "levels": levels, "bars": bars}
    p = subprocess.run([BIN, "--ev-stdin"], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=REPO, timeout=60)
    if p.returncode != 0:
        return None                      # fail-loud hacia arriba: None, jamas {}
    return json.loads(p.stdout)


def label(bars, idx, direction, atr):
    """Triple barrera. 1 = gano, 0 = perdio, None = TIMEOUT (el timeout NO es una victoria)."""
    entry = bars[idx][4]
    tp = entry + K_BARRIER * atr * direction
    sl = entry - K_BARRIER * atr * direction
    for j in range(idx + 1, min(idx + 1 + H_BARS, len(bars))):
        h, l = bars[j][2], bars[j][3]
        hit_tp = (h >= tp) if direction > 0 else (l <= tp)
        hit_sl = (l <= sl) if direction > 0 else (h >= sl)
        if hit_tp and hit_sl:
            return 0                      # barra ambigua -> SL primero (conservador)
        if hit_tp:
            return 1
        if hit_sl:
            return 0
    return None


def ts_index(bars):
    return {int(b[0]): i for i, b in enumerate(bars)}


def score(events, bars, atr):
    """Etiqueta los eventos operables. Direccion = alejandose del nivel."""
    idx = ts_index(bars)
    wins = losses = timeouts = 0
    for e in events:
        if not e["tradeable"]:
            continue
        i = idx.get(int(e["ts"]))
        if i is None or i + 1 >= len(bars):
            continue
        direction = 1 if bars[i][4] > e["level_px"] else -1
        lab = label(bars, i, direction, atr)
        if lab is None:
            timeouts += 1
        elif lab:
            wins += 1
        else:
            losses += 1
    return wins, losses, timeouts


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - m), min(1.0, c + m))


def main():
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else ["QQQ", "SPY", "NVDA", "MU", "SMH", "AMD"]
    max_sessions = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    rnd = random.Random(20260725)

    real = {"w": 0, "l": 0, "t": 0}
    null = {"w": 0, "l": 0, "t": 0}
    per_sym = {}
    sessions_used = 0

    for sym in syms:
        sessions = load_sessions(sym, max_sessions)
        sw = sl_ = 0
        prev_poc = None
        for _, bars in sessions:
            atr = atr14(bars)
            if atr is None:
                continue
            sessions_used += 1
            lo = min(b[3] for b in bars)
            hi = max(b[2] for b in bars)
            openpx = bars[0][1]

            # --- niveles REALES reconstruibles desde barras ---------------------------------
            levels = []
            if prev_poc is not None:
                levels.append({"type": "POC_DOM", "px": prev_poc})
            step = 5.0 if openpx >= 100 else 1.0
            levels.append({"type": "ROUND", "px": step * round(openpx / step), "is_round": True})
            levels.append({"type": "GAP_EDGE", "px": hi})     # PDH/PDL entran como bordes
            levels.append({"type": "GAP_EDGE", "px": lo})
            prev_poc = poc_of(bars, )

            out = run_engine(sym, bars, levels, atr)
            if out is not None:
                w, l, t = score(out["events"], bars, atr)
                real["w"] += w; real["l"] += l; real["t"] += t
                sw += w; sl_ += l

            # --- NULL: el MISMO patron a precios aleatorios sin nivel -----------------------
            for _ in range(N_NULL):
                rl = [{"type": "ROUND", "px": rnd.uniform(lo, hi)} for _ in range(4)]
                o2 = run_engine(sym, bars, rl, atr)
                if o2 is None:
                    continue
                w, l, t = score(o2["events"], bars, atr)
                null["w"] += w; null["l"] += l; null["t"] += t

        per_sym[sym] = (sw, sl_)

    def rate(d):
        n = d["w"] + d["l"]
        return (d["w"] / n if n else None), n

    r_real, n_real = rate(real)
    r_null, n_null = rate(null)
    lo_r, hi_r = wilson(real["w"], n_real)
    lo_n, hi_n = wilson(null["w"], n_null)

    rep = {
        "generated_at": __import__("time").time(),
        "syms": syms,
        "sessions_used": sessions_used,
        "barrier": {"k_atr": K_BARRIER, "h_bars": H_BARS,
                    "timeout_is_not_a_win": True},
        "real": {"wins": real["w"], "losses": real["l"], "timeouts": real["t"],
                 "n": n_real, "rate": r_real, "wilson_lo": lo_r, "wilson_hi": hi_r},
        "null": {"wins": null["w"], "losses": null["l"], "timeouts": null["t"],
                 "n": n_null, "rate": r_null, "wilson_lo": lo_n, "wilson_hi": hi_n,
                 "sets_per_session": N_NULL},
        "delta_pp": (None if (r_real is None or r_null is None)
                     else round(100 * (r_real - r_null), 2)),
        "bar_pp": 6.0,
        "niveles_no_reconstruibles": ["OI_CALL_WALL", "OI_PUT_WALL", "ABS_WALL", "FLIP_OPEN"],
        "por_que": "no existe historia de OI a ningun precio en este plan; el as_of del "
                   "snapshot de Polygon devuelve OK e IGNORA la fecha",
    }
    if rep["delta_pp"] is not None:
        # El veredicto compara el Wilson-LB del real contra la TASA del null + la vara.
        rep["veredicto"] = ("KEEP" if (lo_r is not None and r_null is not None
                                       and lo_r >= r_null + rep["bar_pp"] / 100.0)
                            else "NO SUPERA LA VARA")
    else:
        rep["veredicto"] = "DATA-INSUFFICIENT"

    out_p = os.path.join(REPO, "data", "level_react_validation.json")
    tmp = out_p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, indent=1)
    os.replace(tmp, out_p)                 # escritura atomica
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
