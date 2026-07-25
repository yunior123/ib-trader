#!/usr/bin/env python3
"""iv_hist_build.py — la superficie de IV del PASADO, invertida por biseccion desde el precio.

Orden de Yunior 2026-07-25: *"solve data insufficient issues"*.

EL PROBLEMA QUE RESUELVE, Y EL QUE NO
-------------------------------------
`skew-lead` (#28) y toda la rejilla Compass/IV-rank piden **60 sesiones de superficie de IV**.
La tabla `iv_hist` **no existia** y el archivo de cadenas tiene **1 sola fecha**, asi que el
veredicto era DATA-INSUFFICIENT sin numero detras.

Pero la IV del pasado **NO es irrecuperable**: `poly_opt_bars` tiene el PRECIO de cada contrato
(5 minutos, 940 contratos, 8 syms) y `gex_core.implied_vol` invierte la IV por **biseccion**
sobre ese precio. Eso es exactamente lo que manda CLAUDE.md para el pasado: *"hay que invertir
IV por biseccion y calcular las griegas por Black-Scholes"*.

**LO QUE SIGUE SIENDO IMPOSIBLE, y no se finge**: el **OI historico**. No existe endpoint a
ningun precio en este plan (el `?as_of=` del snapshot devuelve `OK` e IGNORA la fecha). Asi que
esta tabla trae `iv` y `delta` REALES-reconstruidos y **NO trae OI**. Todo lo que dependa de OI
(muros, max-pain, GEX historico) sigue bloqueado y **se dice**, no se aproxima.

LA MARCA DE PROCEDENCIA ES PARTE DEL DATO
`iv_src='invertida_biseccion'` viaja en CADA fila. La IV invertida **jamas** se mezcla en una
serie con `implied_volatility` del snapshot de Polygon ni con `modelGreeks.impliedVol` de IBKR
(una salida de modelo suavizada). Mezclarlas produce una serie que parece continua y no lo es —
y ese es el modo de fallo que mata a una feature de skew.

Python legitimo: lote fuera de sesion. SEÑAL-SOLAMENTE.
"""
import json
import math
import os
import sqlite3
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear rutas
sys.path.insert(0, os.path.join(REPO, "scripts"))
DB = os.path.join(REPO, "trades.db")
OUT = os.path.join(REPO, "data", "iv_hist_health.json")

import gex_core  # noqa: E402  (tras fijar sys.path)

R_FREE = 0.045
MATCH_S = 300          # tolerancia para casar el bar de opcion con el spot (5 min)

DDL = """
CREATE TABLE IF NOT EXISTS iv_hist(
    sym       TEXT    NOT NULL,
    date      TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    exp       TEXT    NOT NULL,
    strike    REAL    NOT NULL,
    right     TEXT    NOT NULL,
    opt_close REAL    NOT NULL,
    spot      REAL    NOT NULL,
    t_years   REAL    NOT NULL,
    iv        REAL,
    delta     REAL,
    iv_src    TEXT    NOT NULL,
    oi        INTEGER,          -- SIEMPRE NULL: no existe historia de OI en este plan
    PRIMARY KEY(sym, date, exp, strike, right)
)
"""


def norm_exp(e):
    """`2026-07-24` o `20260724` -> `20260724`. None si no es una fecha — nunca una inventada."""
    if not e:
        return None
    s = str(e).replace("-", "")
    return s if (len(s) == 8 and s.isdigit()) else None


def bs_delta(S, K, T, iv, cp):
    """Delta de Black-Scholes. None si algun input no sirve — jamas 0.0 ni 0.5.

    Un delta 0.5 por defecto es el peor de los ceros plausibles aqui: colocaria un contrato
    justo en el ATM y contaminaria la interpolacion al 25 delta con un punto fantasma.
    """
    if None in (S, K, T, iv) or S <= 0 or K <= 0 or T <= 0 or iv <= 0:
        return None
    d1 = (math.log(S / K) + (R_FREE + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
    return nd1 if str(cp).upper().startswith("C") else nd1 - 1.0


def spot_index(con, sym, date):
    """{ts_segundos: close} de `poly_bars` para ese sym/dia. `poly_bars.ts` esta en MILISEGUNDOS."""
    rows = con.execute(
        "SELECT ts/1000, c FROM poly_bars WHERE sym=? AND date(ts/1000,'unixepoch')=?",
        (sym, date)).fetchall()
    return {int(t): float(c) for t, c in rows}


def nearest_spot(idx, keys, ts):
    """Spot mas cercano dentro de MATCH_S. None si no hay — no se estira el ultimo precio."""
    if not keys:
        return None
    import bisect
    i = bisect.bisect_left(keys, ts)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(keys):
            d = abs(keys[j] - ts)
            if d <= MATCH_S and (best is None or d < best[0]):
                best = (d, idx[keys[j]])
    return None if best is None else best[1]


def main():
    if not os.path.exists(DB):
        print("iv_hist_build: falta trades.db", file=sys.stderr)
        return 2

    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute(DDL)

    # Ultimo bar de cada contrato en cada sesion = el cierre de ese contrato ese dia.
    rows = con.execute("""
        SELECT b.sym, date(b.ts/1000,'unixepoch') d, b.ts/1000, b.exp, b.strike, b.right, b.c
        FROM poly_opt_bars b
        JOIN (SELECT otk, date(ts/1000,'unixepoch') d2, MAX(ts) mts
              FROM poly_opt_bars GROUP BY otk, d2) m
          ON b.otk = m.otk AND b.ts = m.mts
        ORDER BY b.sym, d, b.exp, b.strike
    """).fetchall()

    stats = {"filas_entrada": len(rows), "iv_ok": 0, "iv_none": 0,
             "sin_spot": 0, "exp_malo": 0, "t_no_positivo": 0}
    out, spot_cache = [], {}

    for sym, d, ts, exp, strike, right, close in rows:
        e = norm_exp(exp)
        if e is None:
            stats["exp_malo"] += 1
            continue
        key = (sym, d)
        if key not in spot_cache:
            idx = spot_index(con, sym, d)
            spot_cache[key] = (idx, sorted(idx))
        idx, keys = spot_cache[key]
        spot = nearest_spot(idx, keys, int(ts))
        if spot is None:
            stats["sin_spot"] += 1
            continue

        # T medido DESDE EL DIA DE LA BARRA, no desde hoy: `now=ts` es lo que hace que esto sea
        # historia y no una foto del presente mal fechada.
        T = gex_core._T_of(e, now=float(ts))
        if T is None or T <= 1e-5:
            stats["t_no_positivo"] += 1
            continue

        cp = "C" if str(right).lower().startswith("c") else "P"
        iv = gex_core.implied_vol(float(close), float(spot), float(strike), T, cp=cp, r=R_FREE)
        if iv is None:
            stats["iv_none"] += 1        # se cuenta, no se rellena
        else:
            stats["iv_ok"] += 1
        dlt = bs_delta(float(spot), float(strike), T, iv, cp) if iv is not None else None

        out.append((sym, d, int(ts), e, float(strike), cp, float(close), float(spot),
                    T, iv, dlt, "invertida_biseccion", None))

    con.executemany(
        "INSERT OR REPLACE INTO iv_hist(sym,date,ts,exp,strike,right,opt_close,spot,"
        "t_years,iv,delta,iv_src,oi) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", out)
    con.commit()

    per_sym = {}
    for sym, n, ns in con.execute(
            "SELECT sym, count(*), count(DISTINCT date) FROM iv_hist "
            "WHERE iv IS NOT NULL GROUP BY sym"):
        per_sym[sym] = {"filas": n, "sesiones": ns}
    total_sessions = con.execute(
        "SELECT count(DISTINCT date) FROM iv_hist WHERE iv IS NOT NULL").fetchone()[0]
    con.close()

    rep = {
        "generated_at": time.time(),
        "fuente": "poly_opt_bars (precio) + poly_bars (spot); IV invertida por biseccion",
        "iv_src": "invertida_biseccion",
        "oi": None,
        "oi_por_que": ("no existe historia de OI a ningun precio en este plan; el as_of del "
                       "snapshot de Polygon devuelve OK e IGNORA la fecha. Muros, max-pain y "
                       "GEX historico siguen BLOQUEADOS y no se aproximan"),
        "sesiones_distintas": total_sessions,
        "sesiones_necesarias_para_z": 60,
        "desbloqueado": bool(total_sessions >= 60),
        "por_sym": per_sym,
        "conteos": stats,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    os.replace(tmp, OUT)                 # escritura atomica
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
