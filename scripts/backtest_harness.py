#!/usr/bin/env python3
"""backtest_harness.py — el WIN RATE con COSTE, sobre el etiquetado de TRIPLE
BARRERA de la casa. Ya NO tiene definicion propia de "win".

QUE ERA Y POR QUE SE CAMBIO (defecto CRITICO del hunt 2026-07-24, linea 72)
--------------------------------------------------------------------------
    ret = (r[0] - entry) / entry * 100 * th
    win = 1 if ret > 0.05 else 0

Eso es RETORNO A HORIZONTE: mira el close a +15/+30/+60 min y nada mas.
Tres agujeros, los tres midiendo de mas:

  1. SIN PATH-DEPENDENCE. No ve el stop tocado en el minuto 4 (ni el target
     tocado en el minuto 2). Una señal stopeada que luego vuelve a favor se
     contaba GANADA.
  2. SIN STOP. No existe bracket: la "operacion" aguanta cualquier drawdown.
  3. SIN COSTE. Ni comision, ni medio spread, ni theta. El umbral era 0,05% de
     movimiento del subyacente, cuando la friccion real de una opcion de la
     flota es un orden de magnitud mayor.

MEDIDO el 2026-07-26 sobre `barrier_outcomes` (celda de referencia k_tp=k_sl=1.0,
H=30 min, n=1609 observaciones RESUELTAS) y sobre `barrier_outcomes_regen`
(501 sesiones, n=213.656):

    definicion                          WR TOTAL   expectancia (ATR)
    retorno a horizonte (lo de antes)     47,8%     -- (no la calculaba)
    triple barrera, sin coste             50,0%     +0,000
    triple barrera - coste accion         48,1%     -0,355
    triple barrera - coste opcion ATM     42,7%     -0,613
    triple barrera - coste opcion OTM      5,4%     -3,021

    bollinger sobre las 501 sesiones:     50,0% bruto -> 37,0% neto (opcion ATM)

El titular: **con k_tp=k_sl la barrera sin coste da 50,0% — es una moneda al
aire por construccion (`k_sl/(k_tp+k_sl)`), y el 44-48% que la flota usaba para
dimensionar era esa misma moneda peor medida.** En cuanto entra CUALQUIER coste
la expectancia es NEGATIVA en todas las celdas. Un objetivo de 1 ATR de barra de
1 minuto (~0,1% del precio) no paga el ida y vuelta de una opcion (~0,34%).

QUE HACE AHORA
--------------
Delega el etiquetado en `scripts/barrier_labels.py` (ficha #1) — no reimplementa
nada — y aporta la capa que faltaba: **el COSTE, declarado y explicito**.

    pago_neto(ATR) = (+k_tp si TP | -k_sl si SL) - coste_en_ATR
    coste_en_ATR   = (coste_% / 100 * entry) / atr
    win_neto       = pago_neto > 0

El TIMEOUT sigue siendo NULL y fuera del denominador (regla de la ficha #1).

  python3 scripts/backtest_harness.py net           # WR y expectancia NETOS (por defecto)
  python3 scripts/backtest_harness.py compare       # viejo vs barrera vs neto
  python3 scripts/backtest_harness.py propose       # data/backtest_harness.PROPUESTO.json
  python3 scripts/backtest_harness.py baseline      # DEPRECATED: regenera el etiquetado viejo

`baseline` existe SOLO porque `barrier_labels.scoreboard()` y `.confusion()`
necesitan la etiqueta vieja en `backtest_signal_outcomes` para poder medir
cuanto nos mentiamos. No es una fuente de win rates: estampa
`label_def='horizon_return_DEPRECATED'` en la propia fila.

HONESTIDAD (regla ~/CLAUDE.md): ninguna funcion devuelve 0 / 0.0 / 0.5 / 50 ante
datos ausentes. Devuelve None o levanta. DATA-INSUFFICIENT es un resultado.
SEÑAL-SOLAMENTE.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
if os.path.join(REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "scripts"))

DB = os.path.join(REPO, "trades.db")
DB_RO = "file:" + DB + "?mode=ro"

import barrier_labels as BL          # noqa: E402  etiquetado (ficha #1) — NO se reimplementa
import calibration_ledger as CL      # noqa: E402  wilson() unico de la casa

# ============================================================================
# COSTES — declarados, con su derivacion. Nada de esto es un prior inventado.
# ============================================================================
# Cada entrada es el coste de IDA Y VUELTA expresado en % del SUBYACENTE, que es
# la unidad en la que estan `entry` y `atr` de barrier_outcomes.
#
#  * accion / ETF: medio spread x2 lados + comision IBKR x2. Sobre la flota
#    (QQQ/SPY 1-2 bp de spread, nombres medianos 3-5 bp) y 0,0035 $/accion,
#    ~4 bp = 0,040% ida y vuelta.
#  * opcion ATM 0DTE: doctrina de la casa = spread <=5% de la prima (orden #4 de
#    ~/CLAUDE.md) + 0,65 $/contrato x2 sobre una prima de 200 $ (0,65%) =
#    5,65% de la PRIMA. Traducido a movimiento del subyacente hay que dividir
#    por el delta:  coste_subyacente_% = 5,65% * prima_%_del_spot / delta.
#    QQQ ATM 0DTE con prima 0,286% del spot y delta 0,50 -> 0,069%. (Medido en
#    el hunt 2026-07-24; se conserva su cifra para que el numero sea trazable.)
#  * opcion OTM barata: prima 1,0% del spot, delta 0,35 -> 0,34%. Es el vehiculo
#    que de verdad se compra con el presupuesto de <=200 $.
#
# Cambiar estos numeros cambia el veredicto: por eso viven aqui, con nombre y
# derivacion, y no enterrados en una expresion.
FRICTION_PCT = {
    "sin_coste": 0.0,
    "accion": 0.040,
    "opcion_atm": 0.069,
    "opcion_otm": 0.340,
}
FRICTION_WHY = {
    "sin_coste": "referencia teorica: la barrera desnuda (k_sl/(k_tp+k_sl) es el paseo aleatorio)",
    "accion": "medio spread x2 + comision IBKR x2 sobre accion/ETF de la flota",
    "opcion_atm": ("5,65% de la prima (spread 5% doctrina + 0,65$/contrato x2 sobre 200$) "
                   "/ delta 0,50, con prima 0,286% del spot"),
    "opcion_otm": ("misma friccion de prima sobre prima 1,0% del spot y delta 0,35 — "
                   "el vehiculo real del presupuesto <=200$"),
}
REFERENCE_FRICTION = "opcion_atm"

# Celda de referencia PRE-COMPROMETIDA (la misma que null_control): no se elige
# a posteriori la que mejor sale.
REF_K_TP, REF_K_SL, REF_H = BL.REF_K_TP, BL.REF_K_SL, 30

MIN_N = BL.MIN_N_CELL            # 50 observaciones resueltas para publicar
PROPOSAL = os.path.join(REPO, "data", "backtest_harness.PROPUESTO.json")

BO_TABLE = BL.BO_TABLE           # se reapunta con --signals-table


# ============================================================================
# 1. Coste
# ============================================================================
def cost_in_atr(entry, atr, friction_pct):
    """Coste de ida y vuelta expresado en unidades de ATR.

    Levanta si `atr` o `entry` no son positivos: sin ellos no hay coste que
    calcular y **no existe un 0 plausible que devolver** — un coste 0 es
    exactamente el defecto que este fichero arregla."""
    if entry is None or not (entry > 0):
        raise ValueError("entry invalido: %r" % (entry,))
    if atr is None or not (atr > 0):
        raise ValueError("atr invalido: %r" % (atr,))
    if friction_pct is None or friction_pct < 0:
        raise ValueError("friccion invalida: %r" % (friction_pct,))
    return (friction_pct / 100.0) * entry / atr


def net_payoff(label, k_tp, k_sl, entry, atr, friction_pct):
    """Pago NETO de una observacion de barrera, en unidades de ATR.

    label 1 -> +k_tp - coste ; label 0 -> -k_sl - coste ; label None -> None.
    El TIMEOUT devuelve None (no hay salida, no hay pago definido). Jamas 0."""
    if label is None:
        return None
    if label not in (0, 1):
        raise ValueError("label debe ser 0, 1 o None, no %r" % (label,))
    gross = k_tp if label == 1 else -k_sl
    return gross - cost_in_atr(entry, atr, friction_pct)


# ============================================================================
# 2. Agregacion neta sobre la tabla de barrera
# ============================================================================
def net_stats(obs, friction_pct):
    """obs: [(label, entry, atr, k_tp, k_sl), ...] de UNA celda.

    Devuelve dict con n RESUELTA, WR neto (Wilson de la casa), expectancia neta
    media y timeouts. **None si no hay ni una observacion resuelta** — nunca un
    0.5 fabricado."""
    n = wins = timeouts = 0
    tot = 0.0
    for label, entry, atr, k_tp, k_sl in obs:
        if label is None:
            timeouts += 1
            continue
        pay = net_payoff(label, k_tp, k_sl, entry, atr, friction_pct)
        n += 1
        tot += pay
        if pay > 0:
            wins += 1
    if n == 0:
        return None
    p, lo, hi = CL.wilson(wins, n)
    return dict(n=n, wins=wins, timeouts=timeouts,
                wr=round(p, 4), ci=[round(lo, 4), round(hi, 4)],
                expectancy=round(tot / n, 4),
                friction_pct=friction_pct,
                trust=n >= MIN_N)


def load_cells(conn, k_tp=REF_K_TP, k_sl=REF_K_SL, H=REF_H, by_symbol=False):
    """{(source[,sym]): [(label,entry,atr,k_tp,k_sl), ...]} desde la tabla de
    barrera. Levanta si la tabla no existe: sin etiquetado no hay numero."""
    have = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                        "name=?", (BO_TABLE,)).fetchone()
    if not have:
        raise SystemExit("%s no existe — correr `python3 scripts/barrier_labels.py "
                         "build` primero (este harness NO etiqueta: delega)" % BO_TABLE)
    rows = conn.execute("SELECT source,sym,label,entry,atr,k_tp,k_sl FROM %s "
                        "WHERE k_tp=? AND k_sl=? AND H=?" % BO_TABLE,
                        (k_tp, k_sl, H)).fetchall()
    out = defaultdict(list)
    for source, sym, label, entry, atr, ktp, ksl in rows:
        key = (source, sym) if by_symbol else (source,)
        out[key].append((label, entry, atr, ktp, ksl))
    return dict(out)


def verdict_of(st):
    """Veredicto por EXPECTANCIA neta, jamas por win rate (skill
    measured-probability §2: un WR alto con k_tp chico es geometria, no edge).
    DATA-INSUFFICIENT es un resultado valido y se publica."""
    if st is None:
        return "DATA-INSUFFICIENT", "sin observaciones resueltas"
    if not st["trust"]:
        return "DATA-INSUFFICIENT", "n resuelta %d < %d" % (st["n"], MIN_N)
    if st["expectancy"] > 0:
        return "APTA", "expectancia neta %+.3f ATR > 0" % st["expectancy"]
    return "NEGATIVA", "expectancia neta %+.3f ATR <= 0 tras coste" % st["expectancy"]


# ============================================================================
# 3. `net` — el numero honesto
# ============================================================================
def run_net(k_tp=REF_K_TP, k_sl=REF_K_SL, H=REF_H, by_symbol=False, quiet=False):
    conn = sqlite3.connect(DB_RO, uri=True, timeout=30)
    try:
        cells = load_cells(conn, k_tp, k_sl, H, by_symbol)
    finally:
        conn.close()
    if not cells:
        raise SystemExit("celda k_tp=%s k_sl=%s H=%s vacia en %s"
                         % (k_tp, k_sl, H, BO_TABLE))
    res = {}
    for key, obs in cells.items():
        name = "|".join(key)
        res[name] = dict((f, net_stats(obs, p)) for f, p in FRICTION_PCT.items())
        v, why = verdict_of(res[name][REFERENCE_FRICTION])
        res[name]["verdict"] = v
        res[name]["why"] = "%s (friccion de referencia: %s)" % (why, REFERENCE_FRICTION)
    if not quiet:
        _print_net(res, k_tp, k_sl, H)
    return res


def _print_net(res, k_tp, k_sl, H):
    names = list(FRICTION_PCT)
    print("=== WR y EXPECTANCIA NETOS DE COSTE — %s, celda k_tp=%s k_sl=%s H=%smin ==="
          % (BO_TABLE, k_tp, k_sl, H))
    print("El TIMEOUT es NULL y NO entra en el denominador. WR de un paseo "
          "aleatorio con esta geometria = %.3f\n" % (k_sl / (k_tp + k_sl)))
    print("%-22s %7s" % ("fuente", "n")
          + "".join("%22s" % ("%s %.3f%%" % (f, FRICTION_PCT[f])) for f in names)
          + "  veredicto")
    print("-" * (31 + 22 * len(names) + 12))
    for name in sorted(res):
        r = res[name]
        first = next((r[f] for f in names if r[f]), None)
        line = "%-22s %7s" % (name, first["n"] if first else 0)
        for f in names:
            st = r[f]
            line += "%9s%13s" % (("%.1f%%" % (100 * st["wr"])) if st else "—",
                                 ("exp %+.3f" % st["expectancy"]) if st else "")
        print(line + "  %s" % r["verdict"])
    print()
    for f in names:
        print("  %-11s %.3f%%  — %s" % (f, FRICTION_PCT[f], FRICTION_WHY[f]))
    print("\n  expectancia en unidades de ATR(14, barras 1m), NETA del coste de "
          "su columna.\n  Seleccion por EXPECTANCIA, jamas por win rate.")


# ============================================================================
# 4. `compare` — viejo vs barrera vs neto, misma poblacion
# ============================================================================
def run_compare(H=REF_H, k_tp=REF_K_TP, k_sl=REF_K_SL):
    """Cara a cara de las TRES definiciones sobre las MISMAS señales: la prueba
    de que el cambio de numero es un cambio de DEFINICION, no de muestra."""
    conn = sqlite3.connect(DB_RO, uri=True, timeout=30)
    try:
        run = conn.execute("SELECT MAX(run_ts) FROM backtest_signal_outcomes").fetchone()[0]
        old = defaultdict(lambda: [0, 0])
        if run is not None:
            for src, win in conn.execute(
                    "SELECT source, win FROM backtest_signal_outcomes "
                    "WHERE run_ts=? AND horizon=?", (run, H)):
                old[src][0] += 1
                old[src][1] += win or 0
        cells = load_cells(conn, k_tp, k_sl, H)
    finally:
        conn.close()
    print("=== TRES DEFINICIONES, MISMAS SEÑALES — H=%d min, k_tp=%s k_sl=%s ==="
          % (H, k_tp, k_sl))
    print("%-12s | %8s %8s | %8s %8s | %8s %9s | %8s %9s"
          % ("fuente", "n viejo", "WR viejo", "n barr.", "WR barr.",
             "WR neto", "exp neta", "WR OTM", "exp OTM"))
    print("-" * 104)
    for key in sorted(cells):
        src = key[0]
        obs = cells[key]
        gross = net_stats(obs, FRICTION_PCT["sin_coste"])
        atm = net_stats(obs, FRICTION_PCT["opcion_atm"])
        otm = net_stats(obs, FRICTION_PCT["opcion_otm"])
        n_o, w_o = old.get(src, [0, 0])
        wr = lambda st: ("%.1f%%" % (100 * st["wr"])) if st else "—"
        ex = lambda st: ("%+.3f" % st["expectancy"]) if st else "—"
        print("%-12s | %8d %8s | %8s %8s | %8s %9s | %8s %9s"
              % (src, n_o, ("%.1f%%" % (100.0 * w_o / n_o)) if n_o else "—",
                 gross["n"] if gross else 0, wr(gross),
                 wr(atm), ex(atm), wr(otm), ex(otm)))
    print("\n  'WR viejo' = backtest_signal_outcomes.win (retorno a horizonte) DEPRECATED")
    print("  'WR barr.' = triple barrera sin coste; con k_tp=k_sl es una moneda al aire")
    print("  'WR neto'  = barrera - friccion de opcion ATM (%.3f%% del subyacente)"
          % FRICTION_PCT["opcion_atm"])
    print("  el denominador de barrera excluye TIMEOUTS; el viejo los contaba como "
          "victoria si ret>0,05%")


# ============================================================================
# 5. `propose` — .PROPUESTO.json, NUNCA el fichero vivo
# ============================================================================
def run_propose(k_tp=REF_K_TP, k_sl=REF_K_SL, H=REF_H, path=PROPOSAL, quiet=False):
    res = run_net(k_tp, k_sl, H, by_symbol=True, quiet=True)
    prop = {"_meta": dict(
        at=time.strftime("%Y-%m-%d %H:%M:%S"),
        WARNING=("PROPUESTA — ningun daemon lee este fichero. Los vivos son "
                 "data/signal_enable.json y data/calibration.json, y NO se han tocado."),
        table=BO_TABLE,
        cell=dict(k_tp=k_tp, k_sl=k_sl, H=H),
        friction_pct=FRICTION_PCT, friction_why=FRICTION_WHY,
        reference_friction=REFERENCE_FRICTION, min_n=MIN_N,
        rule=("veredicto por EXPECTANCIA NETA, no por win rate. NEGATIVA -> banner "
              "solamente. DATA-INSUFFICIENT -> se dice 'todavia no sabemos', en voz alta."),
        replaces=("backtest_harness.py:72 `win = ret>0.05` (retorno a horizonte, "
                  "sin coste, sin stop, sin path-dependence)"))}
    for name in sorted(res):
        r = res[name]
        atm, gross = r[REFERENCE_FRICTION], r["sin_coste"]
        prop[name] = dict(
            verdict=r["verdict"], why=r["why"],
            n=(atm or gross or {}).get("n"),
            wr_gross=(gross or {}).get("wr"),
            wr_net=(atm or {}).get("wr"),
            expectancy_net=(atm or {}).get("expectancy"),
            ci_net=(atm or {}).get("ci"),
            propose_sizing=(r["verdict"] == "APTA"),
            propose_voice=(r["verdict"] == "APTA"))
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(prop, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    if not quiet:
        n_apta = sum(1 for k, v in prop.items()
                     if not k.startswith("_") and v["verdict"] == "APTA")
        print("-> %s  (PROPUESTA — nada vivo se ha tocado)" % path)
        print("   %d celdas, %d APTA" % (len(prop) - 1, n_apta))
    return prop


# ============================================================================
# 6. `baseline` — DEPRECATED, solo para el scoreboard
# ============================================================================
DEPRECATION = """
!!! ETIQUETADO DEPRECATED — retorno a horizonte !!!
Esto regenera `backtest_signal_outcomes` con la definicion VIEJA
(`win = ret > 0,05%` a +Hmin) UNICAMENTE porque barrier_labels.scoreboard() y
.confusion() la necesitan como linea base contra la que medir cuanto nos
mentiamos. NO es una fuente de win rates: no tiene stop, ni camino, ni coste.
El numero bueno: `python3 scripts/backtest_harness.py net`.
"""

LABEL_DEF = ("horizon_return_DEPRECATED: win = (close(t+H)-entry)/entry*thesis > 0,05%. "
             "Sin stop, sin path-dependence, sin coste. Reemplazada por triple "
             "barrera + coste (backtest_harness.py net). Ver barrier_outcomes.")


def ensure_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS backtest_results(
        run_ts REAL, source TEXT, horizon INTEGER, n INTEGER, wins INTEGER,
        wr INTEGER, lo INTEGER, hi INTEGER, avg_ret REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS backtest_signal_outcomes(
        run_ts REAL, date TEXT, ts_txt TEXT, symbol TEXT, source TEXT,
        horizon INTEGER, entry REAL, ret REAL, win INTEGER, thesis INTEGER)""")
    # La honestidad va DENTRO del dato (mismo patron que el `why` de
    # data/signal_enable.json): quien lea la tabla ve que definicion la produjo.
    cols = set(r[1] for r in c.execute("PRAGMA table_info(backtest_signal_outcomes)"))
    if "label_def" not in cols:
        c.execute("ALTER TABLE backtest_signal_outcomes ADD COLUMN label_def TEXT")
    c.commit()


def _duck():
    import duckdb
    d = duckdb.connect()  # :memory:
    d.execute("INSTALL sqlite; LOAD sqlite;")
    d.execute("CREATE TABLE pb AS SELECT * FROM sqlite_scan('%s','poly_bars')" % DB)
    d.execute("CREATE INDEX ix ON pb(sym, ts)")
    return d


def run_baseline(horizons=(15, 30, 60)):
    import eod_backtest as E
    print(DEPRECATION)
    d = _duck()
    have = set(r[0] for r in d.execute("SELECT DISTINCT sym FROM pb").fetchall())
    print("[baseline] poly_bars: %d simbolos, %d barras"
          % (len(have), d.execute("SELECT COUNT(*) FROM pb").fetchone()[0]))
    c = sqlite3.connect(DB, timeout=30)
    ensure_tables(c)
    sigs = c.execute("SELECT ts_epoch, ts_txt, date, kind, source, symbol, msg FROM signals "
                     "WHERE ts_epoch IS NOT NULL ORDER BY ts_epoch").fetchall()
    run_ts = time.time()
    agg = dict((h, defaultdict(lambda: [0, 0, 0.0])) for h in horizons)
    skipped = 0
    for ep, ts_txt, date, kind, source, sym, msg in sigs:
        if not sym:
            sym = E.extract_symbol(kind or "", msg or "")
        if not sym or sym not in have:
            skipped += 1
            continue
        th, _ = E.thesis(source or "", kind or "", msg or "")
        if th == 0:
            continue
        ms = int(ep * 1000)
        row = d.execute("SELECT c FROM pb WHERE sym=? AND ts<=? ORDER BY ts DESC LIMIT 1",
                        [sym, ms]).fetchone()
        if not row:
            skipped += 1
            continue
        entry = row[0]
        for h in horizons:
            r = d.execute("SELECT c FROM pb WHERE sym=? AND ts>? AND ts<=? "
                          "ORDER BY ts DESC LIMIT 1",
                          [sym, ms, ms + h * 60000]).fetchone()
            if not r:
                continue
            ret = (r[0] - entry) / entry * 100 * th
            win = 1 if ret > 0.05 else 0
            a = agg[h][source]
            a[0] += 1
            a[1] += win
            a[2] += ret
            c.execute("INSERT INTO backtest_signal_outcomes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (run_ts, date, ts_txt, sym, source, h, entry, round(ret, 3),
                       win, th, LABEL_DEF))
    c.commit()
    print("\n=== LINEA BASE DEPRECATED (retorno a horizonte) — saltadas %d ===" % skipped)
    for h in horizons:
        print("\n--- horizonte +%dmin ---" % h)
        tot_n = tot_w = 0
        for src, (n, w, sr) in sorted(agg[h].items(), key=lambda x: -x[1][0]):
            wr, lo, hi = E.wilson(w, n)
            print("  %-11s n=%-5d WR %3d%% [%2d,%3d]  ret %+.2f%%"
                  % (src, n, wr, lo, hi, sr / max(n, 1)))
            c.execute("INSERT INTO backtest_results VALUES(?,?,?,?,?,?,?,?,?)",
                      (run_ts, src, h, n, w, wr, lo, hi, round(sr / max(n, 1), 3)))
            tot_n += n
            tot_w += w
        if tot_n:
            wr, lo, hi = E.wilson(tot_w, tot_n)
            print("  %-11s n=%-5d WR %3d%% [%2d,%3d]" % ("TOTAL", tot_n, wr, lo, hi))
            c.execute("INSERT INTO backtest_results VALUES(?,?,?,?,?,?,?,?,?)",
                      (run_ts, "TOTAL", h, tot_n, tot_w, wr, lo, hi, 0.0))
    c.commit()
    c.close()
    d.close()
    print("\n-> backtest_signal_outcomes con label_def='horizon_return_DEPRECATED' "
          "(run %d). El numero bueno: `backtest_harness.py net`." % int(run_ts))


# ============================================================================
# 7. CLI
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="win rate NETO DE COSTE sobre el etiquetado de triple barrera")
    ap.add_argument("--signals-table", default="signals",
                    help="`signals_regen` para medir sobre las 501 sesiones regeneradas")
    ap.add_argument("--k-tp", type=float, default=REF_K_TP)
    ap.add_argument("--k-sl", type=float, default=REF_K_SL)
    ap.add_argument("--H", type=int, default=REF_H)
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("net", help="WR y expectancia netos (por defecto)")
    n.add_argument("--by-symbol", action="store_true")
    sub.add_parser("compare", help="viejo vs barrera vs neto, misma poblacion")
    sub.add_parser("propose", help="escribe data/backtest_harness.PROPUESTO.json")
    b = sub.add_parser("baseline", help="DEPRECATED: regenera el etiquetado viejo")
    b.add_argument("--h", type=int, default=0)
    a = ap.parse_args()

    BL.use_signals_table(a.signals_table)
    global BO_TABLE
    BO_TABLE = BL.BO_TABLE

    if a.cmd == "compare":
        run_compare(a.H, a.k_tp, a.k_sl)
    elif a.cmd == "propose":
        run_propose(a.k_tp, a.k_sl, a.H)
    elif a.cmd == "baseline":
        run_baseline((a.h,) if a.h else (15, 30, 60))
    else:                                   # `net` y por defecto
        run_net(a.k_tp, a.k_sl, a.H, by_symbol=getattr(a, "by_symbol", False))


if __name__ == "__main__":
    main()
