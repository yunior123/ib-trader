#!/usr/bin/env python3
"""barrier_labels.py — etiquetado de TRIPLE BARRERA (ficha #1 de
docs/FEATURES-MINED-2026-07-25.md). Arregla el DENOMINADOR de todas las
probabilidades que la flota canta.

EL BUG QUE ARREGLA
------------------
Hoy la etiqueta es RETORNO A HORIZONTE (`backtest_signal_outcomes.win = ret>0.05%`
a +5/+15/+30/+60 min). Ese retorno **no puede ver el stop siendo tocado en el
camino**: una señal que fue stopeada en el minuto 4 y volvió a favor en el 14 se
cuenta como GANADA. Todos los win rates que cantamos son optimistas por una
cantidad no medida (prior: bollinger h=15 publica 0.436 con n=822).

QUE HACE
--------
Por cada señal de `trades.db signals` con dirección derivable:
    TP = entry + k_tp*ATR14_1m*dir      SL = entry - k_sl*ATR14_1m*dir
Recorre la ruta 1m de t+1 a t+H:
    label = 1  si TP toca primero
    label = 0  si SL toca primero
    label = NULL en timeout   <-- EL TIMEOUT NO ES VICTORIA
Barra que contiene TP **y** SL = AMBIGUA: no hay ruta sub-minuto, así que se
resuelve **SL primero** (conservador) y la tasa se PUBLICA como `ambig_pct`.
Es una limitación real del dato, se declara, no se esconde.

Registra además MFE (excursión favorable máxima / ATR), MAE (adversa / ATR) y
`t_touch` en minutos: esas distribuciones SON el bracket del ticket, no una
opinión.

Walk-forward con PURGA y EMBARGO: fuera del entrenamiento toda observación cuyo
[t, t+H] solape el bloque de test; embargo de H minutos tras cada test.

HONESTIDAD (fail-loud, regla ~/CLAUDE.md)
-----------------------------------------
Ninguna función devuelve 0/0.5/50 ante datos ausentes. Devuelve None o levanta.
Cada señal descartada se cuenta y se reporta con su motivo (nunca un `except:
continue` silencioso que encoja el denominador).

USO
    python3 scripts/barrier_labels.py build            # etiqueta y escribe la tabla
    python3 scripts/barrier_labels.py report           # tabla de celdas por fuente
    python3 scripts/barrier_labels.py scoreboard       # docs/EDGE-SCOREBOARD-<fecha>.md
    python3 scripts/barrier_labels.py wf               # chequeo de purga/embargo

SEÑAL-SOLAMENTE: solo lee barras y señales; jamás ordena nada.
"""
import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
from bisect import bisect_right
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
if os.path.join(REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "scripts"))

DB = os.path.join(REPO, "data", "trades.db")
DB_RO = "file:" + DB + "?mode=ro"

# ---- TABLAS (aditivo 2026-07-25, ficha de regeneracion) ---------------------
# Por defecto EXACTAMENTE lo de siempre: `signals` (ledger vivo) -> `barrier_outcomes`.
# `--signals-table signals_regen` reapunta la MISMA maquinaria a las señales regeneradas
# sobre las 501 sesiones de poly_bars, y su salida va a una tabla PARALELA
# (`barrier_outcomes_regen`) para no pisar ni un byte de la medicion viva.
SIG_TABLE = "signals"
BO_TABLE = "barrier_outcomes"


def use_signals_table(name):
    """Reapunta entrada y salida a la vez. Sin esto, etiquetar regen sobreescribiria
    barrier_outcomes (PRIMARY KEY por signal_id: los ids colisionan entre tablas)."""
    global SIG_TABLE, BO_TABLE
    if not name or name == "signals":
        SIG_TABLE, BO_TABLE = "signals", "barrier_outcomes"
        return
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise SystemExit("nombre de tabla invalido: %r" % name)
    SIG_TABLE = name
    BO_TABLE = "barrier_outcomes_" + (name[len("signals_"):] if name.startswith("signals_")
                                      else name)

# ---- barrido de la ficha #1 -------------------------------------------------
K_TP = (0.5, 0.75, 1.0, 1.5)
K_SL = (0.5, 0.75, 1.0)
# H=15 se AÑADE al barrido de la ficha {10,30,60,120} porque el número que hay
# que desmentir es "bollinger h=15 = 0.436 n=822": sin H=15 no hay comparación
# exacta contra backtest_signal_outcomes.
HORIZONS = (10, 15, 30, 60, 120)
MODE = "conservative"          # ambigüedad resuelta SL-primero

ATR_PERIOD = 14
ATR_MAX_LOOKBACK_BARS = 240    # barras causales que se miran para el Wilder
ATR_LOOKBACK_S = 5 * 86400     # ventana temporal del lookback de ATR
GAP_MAX_S = 300                # >5 min sin barra: TR sin close previo (gap)
ENTRY_MAX_STALE_S = 900        # el close usado como entry no puede ser más viejo
MIN_N_CELL = 50                # n RESUELTA mínima para publicar una prob (ficha 1)

# Configuración de referencia para el titular del scoreboard.
REF_K_TP, REF_K_SL = 1.0, 1.0

SCHEMA_TPL = """CREATE TABLE IF NOT EXISTS %s(
    signal_id INTEGER, sym TEXT, source TEXT, date TEXT, ts_epoch REAL,
    direction INTEGER, entry REAL, atr REAL,
    k_tp REAL, k_sl REAL, H INTEGER, mode TEXT,
    label INTEGER, mfe REAL, mae REAL, t_touch REAL, ambig INTEGER,
    run_ts REAL,
    PRIMARY KEY(signal_id, k_tp, k_sl, H, mode))"""


def _schema():
    return SCHEMA_TPL % BO_TABLE


# ============================================================================
# 1. ATR14 Wilder sobre barras 1m — causal y a prueba de huecos
# ============================================================================
def true_range(bar, prev=None, gap_max_s=GAP_MAX_S):
    """TR de una barra. `prev` solo se usa si la barra anterior está a <=gap_max_s
    (si no, es un hueco de sesión/premarket y el close previo no es comparable)."""
    ts, o, h, l, c = bar[0], bar[1], bar[2], bar[3], bar[4]
    if h < l:
        raise ValueError("barra invalida: high<low en ts=%s" % ts)
    if prev is None or (ts - prev[0]) > gap_max_s:
        return h - l
    pc = prev[4]
    return max(h - l, abs(h - pc), abs(l - pc))


def wilder_atr(bars, period=ATR_PERIOD, gap_max_s=GAP_MAX_S):
    """ATR de Wilder sobre `bars` = [(ts,o,h,l,c), ...] ordenadas.
    Devuelve una lista del mismo largo: None hasta que hay `period` TRs, luego
    el ATR suavizado. None NUNCA se sustituye por 0 (regla fail-loud)."""
    n = len(bars)
    out = [None] * n
    if n == 0:
        return out
    trs = []
    atr = None
    for i, b in enumerate(bars):
        tr = true_range(b, bars[i - 1] if i > 0 else None, gap_max_s)
        if atr is None:
            trs.append(tr)
            if len(trs) == period:
                atr = sum(trs) / period
                out[i] = atr
        else:
            atr = (atr * (period - 1) + tr) / period
            out[i] = atr
    return out


def atr_at(bars, idx, period=ATR_PERIOD, gap_max_s=GAP_MAX_S,
           max_lookback=ATR_MAX_LOOKBACK_BARS):
    """ATR14 causal en la barra `idx` (incluida). None si no hay `period` barras
    previas suficientes — jamás un ATR inventado."""
    if idx < 0 or idx >= len(bars):
        return None
    lo = max(0, idx - max_lookback + 1)
    seq = bars[lo:idx + 1]
    if len(seq) < period:
        return None
    a = wilder_atr(seq, period, gap_max_s)
    return a[-1]


# ============================================================================
# 2. Triple barrera
# ============================================================================
def triple_barrier(path, entry, direction, tp_price, sl_price, atr,
                   entry_ts=None):
    """Recorre `path` = [(ts,o,h,l,c), ...] POSTERIOR a la entrada (ya recortado
    al horizonte) y resuelve la triple barrera.

    Devuelve dict(label, mfe, mae, t_touch, ambig, bars):
      label   1 = TP primero | 0 = SL primero | None = TIMEOUT (no es victoria)
      mfe     excursión favorable máxima en unidades de ATR, hasta la barra que
              resuelve (incluida)
      mae     excursión adversa máxima en ATR, misma ventana
      t_touch minutos desde la entrada hasta el toque (None en timeout)
      ambig   1 si la barra resolutoria contenía TP y SL a la vez (se resolvió
              SL primero, conservador)
    Levanta si atr<=0 o direction no es ±1: no hay número plausible que devolver.
    """
    if direction not in (1, -1):
        raise ValueError("direction debe ser +1 o -1, no %r" % (direction,))
    if atr is None or not (atr > 0):
        raise ValueError("atr invalido: %r" % (atr,))
    if entry_ts is None and path:
        entry_ts = path[0][0] - 60
    d = float(direction)
    best_fav = 0.0
    worst_adv = 0.0
    for k, b in enumerate(path):
        ts, _o, h, l, _c = b[0], b[1], b[2], b[3], b[4]
        # excursión de la barra en la dirección de la tesis
        hi_ex = d * (h - entry)
        lo_ex = d * (l - entry)
        fav = max(hi_ex, lo_ex)
        adv = -min(hi_ex, lo_ex)
        if fav > best_fav:
            best_fav = fav
        if adv > worst_adv:
            worst_adv = adv
        hit_tp = (h >= tp_price) if direction == 1 else (l <= tp_price)
        hit_sl = (l <= sl_price) if direction == 1 else (h >= sl_price)
        if hit_tp or hit_sl:
            ambig = 1 if (hit_tp and hit_sl) else 0
            label = 0 if hit_sl else 1        # SL manda en la barra ambigua
            tmin = (ts - entry_ts) / 60.0
            return dict(label=label, mfe=best_fav / atr, mae=worst_adv / atr,
                        t_touch=tmin, ambig=ambig, bars=k + 1)
    return dict(label=None, mfe=best_fav / atr, mae=worst_adv / atr,
                t_touch=None, ambig=0, bars=len(path))


# ============================================================================
# 3. Walk-forward con purga + embargo (Lopez de Prado)
# ============================================================================
def purged_folds(starts, horizon_min, n_folds=5, embargo_min=None):
    """Bloques de test contiguos en el tiempo con PURGA y EMBARGO.

    starts: epochs (segundos) de las observaciones. La vida de cada observación
    es [t, t + horizon_min*60].
    Devuelve [ {test:[idx...], train:[idx...], t0:.., t1:..}, ... ].

    Purga: se saca del train toda observación cuya vida solape la ventana del
    test. Embargo: además se sacan las que ARRANCAN dentro de embargo_min
    después del final del test (sirve el efecto de arrastre serial).
    """
    if embargo_min is None:
        embargo_min = horizon_min
    n = len(starts)
    if n == 0 or n_folds < 2:
        return []
    life = horizon_min * 60.0
    emb = embargo_min * 60.0
    order = sorted(range(n), key=lambda i: starts[i])
    folds = []
    size = max(1, n // n_folds)
    for f in range(n_folds):
        a = f * size
        b = n if f == n_folds - 1 else min(n, (f + 1) * size)
        if a >= b:
            continue
        test = order[a:b]
        t0 = min(starts[i] for i in test)
        t1 = max(starts[i] for i in test) + life
        tset = set(test)
        train = []
        for i in order:
            if i in tset:
                continue
            s = starts[i]
            e = s + life
            if e >= t0 and s <= t1:      # solapa la ventana de test -> PURGADA
                continue
            if t1 < s <= t1 + emb:       # dentro del embargo -> fuera
                continue
            train.append(i)
        folds.append(dict(test=test, train=train, t0=t0, t1=t1,
                          horizon_min=horizon_min, embargo_min=embargo_min))
    return folds


def folds_are_clean(starts, folds):
    """True si NINGUNA observación de train solapa la ventana de su test.
    Se usa en los tests y en el subcomando `wf` (no se asume, se comprueba)."""
    for fd in folds:
        life = fd["horizon_min"] * 60.0
        for i in fd["train"]:
            s = starts[i]
            e = s + life
            if e >= fd["t0"] and s <= fd["t1"]:
                return False
    return True


# ============================================================================
# 4. Carga de datos
# ============================================================================
def _thesis_mod():
    import eod_backtest as E
    return E


def direction_of(source, kind, msg):
    """Dirección de la tesis: +1 espera subir, -1 bajar, None indefinida.
    REUSA `eod_backtest.thesis()` sin modificarla, para que la población sea
    IDÉNTICA a la de backtest_signal_outcomes y el delta del scoreboard sea
    puro re-etiquetado (no un cambio de muestra)."""
    th, _why = _thesis_mod().thesis(source or "", kind or "", msg or "")
    return th if th in (1, -1) else None


def load_signals(conn):
    """Señales con dirección derivable. Devuelve (rows, stats) — cada descarte
    se cuenta con su motivo, nunca se traga en silencio."""
    E = _thesis_mod()
    cur = conn.execute(
        "SELECT id, ts_epoch, ts_txt, date, kind, source, symbol, msg "
        "FROM %s WHERE ts_epoch IS NOT NULL ORDER BY ts_epoch" % SIG_TABLE)
    rows = []
    st = defaultdict(int)
    for sid, ep, ts_txt, date, kind, source, sym, msg in cur:
        st["total"] += 1
        if not sym:
            sym = E.extract_symbol(kind or "", msg or "")
        if not sym:
            st["skip_no_symbol"] += 1
            continue
        d = direction_of(source, kind, msg)
        if d is None:
            st["skip_no_direction"] += 1
            continue
        rows.append(dict(id=sid, ts=float(ep), ts_txt=ts_txt, date=date,
                         kind=kind or "", source=source or "", sym=sym,
                         msg=msg or "", direction=d))
    st["labelable_candidates"] = len(rows)
    return rows, dict(st)


def load_bars(conn, syms, t0_s, t1_s):
    """{sym: [(ts_s,o,h,l,c), ...]} de poly_bars (ts en MILISEGUNDOS en la BD)."""
    out = {}
    for sym in sorted(syms):
        cur = conn.execute(
            "SELECT ts, o, h, l, c FROM poly_bars WHERE sym=? AND ts>=? AND ts<=? "
            "ORDER BY ts", (sym, int(t0_s * 1000), int(t1_s * 1000)))
        out[sym] = [(r[0] / 1000.0, r[1], r[2], r[3], r[4]) for r in cur]
    return out


# ============================================================================
# 5. Construcción de las etiquetas
# ============================================================================
def label_all(sig_rows, bars_by_sym, k_tps=K_TP, k_sls=K_SL, horizons=HORIZONS):
    """Devuelve (out_rows, stats). out_rows: tuplas listas para insertar."""
    out = []
    st = defaultdict(int)
    max_h = max(horizons)
    for s in sig_rows:
        bars = bars_by_sym.get(s["sym"])
        if not bars:
            st["skip_no_bars_for_symbol"] += 1
            continue
        ts_list = [b[0] for b in bars]
        i = bisect_right(ts_list, s["ts"]) - 1
        if i < 0:
            st["skip_no_prior_bar"] += 1
            continue
        if s["ts"] - ts_list[i] > ENTRY_MAX_STALE_S:
            st["skip_entry_stale"] += 1
            continue
        entry = bars[i][4]
        if not (entry > 0):
            st["skip_entry_nonpositive"] += 1
            continue
        atr = atr_at(bars, i)
        if atr is None or not (atr > 0):
            st["skip_atr_insufficient"] += 1
            continue
        # ruta máxima una sola vez; luego se recorta por horizonte
        j_end = bisect_right(ts_list, s["ts"] + max_h * 60)
        full_path = bars[i + 1:j_end]
        if not full_path:
            st["skip_no_forward_bars"] += 1
            continue
        st["labeled_signals"] += 1
        d = s["direction"]
        for H in horizons:
            hi = bisect_right(ts_list, s["ts"] + H * 60)
            path = bars[i + 1:hi]
            if not path:
                st["cell_no_forward_bars"] += 1
                continue
            for k_tp in k_tps:
                tp = entry + k_tp * atr * d
                for k_sl in k_sls:
                    sl = entry - k_sl * atr * d
                    r = triple_barrier(path, entry, d, tp, sl, atr, s["ts"])
                    out.append((s["id"], s["sym"], s["source"], s["date"],
                                s["ts"], d, entry, atr, k_tp, k_sl, H, MODE,
                                r["label"], round(r["mfe"], 5),
                                round(r["mae"], 5),
                                None if r["t_touch"] is None else round(r["t_touch"], 3),
                                r["ambig"]))
                    st["rows"] += 1
                    if r["label"] is None:
                        st["timeout_null"] += 1
                    elif r["ambig"]:
                        st["ambig"] += 1
    return out, dict(st)


def connect_rw():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def write_rows(conn, rows, run_ts, batch=4000):
    """Idempotente: PRIMARY KEY(signal_id,k_tp,k_sl,H,mode) + INSERT OR REPLACE.
    Dos corridas no duplican filas."""
    conn.execute(_schema())
    conn.execute("CREATE INDEX IF NOT EXISTS ix_%s_src ON %s(source)" % (BO_TABLE, BO_TABLE))
    conn.execute("CREATE INDEX IF NOT EXISTS ix_%s_cell ON %s(source,k_tp,k_sl,H)" % (BO_TABLE, BO_TABLE))
    conn.commit()
    sql = ("INSERT OR REPLACE INTO " + BO_TABLE + "(signal_id,sym,source,date,"
           "ts_epoch,direction,entry,atr,k_tp,k_sl,H,mode,label,mfe,mae,"
           "t_touch,ambig,run_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    n = 0
    for a in range(0, len(rows), batch):
        chunk = [tuple(r) + (run_ts,) for r in rows[a:a + batch]]
        conn.executemany(sql, chunk)
        conn.commit()
        n += len(chunk)
    return n


# ============================================================================
# 6. Agregación (vía calibration_ledger) + selección de celda
# ============================================================================
def _wilson():
    """wilson() de calibration_ledger — la misma que ya calibra la casa.
    Import perezoso: calibration_ledger arrastra yfinance y esto es un lote
    offline. Si falta, se LEVANTA (no hay CI plausible que inventar)."""
    import calibration_ledger as CL
    return CL.wilson


def cell_stats(labels, k_tp, k_sl, n_eff=None):
    """Estadística de una celda a partir de la lista de labels (None incluidos).
    Devuelve None si no hay observación RESUELTA — nunca 0.5 fabricado."""
    resolved = [x for x in labels if x is not None]
    n = len(resolved)
    if n == 0:
        return None
    w = sum(resolved)
    wilson = _wilson()
    n_stat = n if n_eff is None else max(1.0, float(n_eff))
    # Wilson necesita enteros coherentes: se escala el conteo a la muestra efectiva
    w_stat = w * n_stat / n
    p, lo, hi = wilson(w_stat, n_stat)
    exp = p * k_tp - (1 - p) * k_sl
    exp_lo = lo * k_tp - (1 - lo) * k_sl
    exp_hi = hi * k_tp - (1 - hi) * k_sl
    return dict(n=n, n_eff=(None if n_eff is None else round(n_stat, 1)),
                wins=w, p=round(p, 4), ci=[round(lo, 4), round(hi, 4)],
                timeouts=len(labels) - n, resolved_pct=round(n / len(labels), 4),
                expectancy=round(exp, 4), exp_ci=[round(exp_lo, 4), round(exp_hi, 4)],
                trust=(n >= MIN_N_CELL))


def load_barrier(conn, source=None):
    q = ("SELECT source,sym,date,ts_epoch,k_tp,k_sl,H,label,mfe,mae,t_touch,ambig "
         "FROM %s" % BO_TABLE)
    args = ()
    if source:
        q += " WHERE source=?"
        args = (source,)
    return conn.execute(q + " ORDER BY ts_epoch", args).fetchall()


def aggregate(rows):
    """(source,k_tp,k_sl,H) -> stats. Reusa el wilson de calibration_ledger."""
    cells = defaultdict(list)
    ambig = defaultdict(int)
    for r in rows:
        key = (r[0], r[4], r[5], r[6])
        cells[key].append(r[7])
        ambig[key] += r[11] or 0
    out = {}
    for key, labels in cells.items():
        st = cell_stats(labels, key[1], key[2])
        if st is None:
            out[key] = None
            continue
        st["ambig"] = ambig[key]
        st["ambig_pct"] = round(ambig[key] / max(1, st["n"]), 4)
        out[key] = st
    return out


def best_cell(agg, source, min_n=MIN_N_CELL):
    """Celda que maximiza el Wilson-LB de la EXPECTANCIA (no del win rate).
    Devuelve (key, stats) o None si ninguna celda llega a min_n resueltas."""
    best = None
    for key, st in agg.items():
        if key[0] != source or st is None or st["n"] < min_n:
            continue
        if best is None or st["exp_ci"][0] > best[1]["exp_ci"][0]:
            best = (key, st)
    return best


def mfe_mae_percentiles(rows, source, k_tp, k_sl, H):
    """Percentiles de MFE/MAE/t_touch de una celda -> parámetros del bracket."""
    mfe, mae, tt = [], [], []
    for r in rows:
        if (r[0], r[4], r[5], r[6]) != (source, k_tp, k_sl, H):
            continue
        if r[8] is not None:
            mfe.append(r[8])
        if r[9] is not None:
            mae.append(r[9])
        if r[10] is not None:
            tt.append(r[10])
    if not mfe:
        return None

    def pct(v, q):
        if not v:
            return None
        v = sorted(v)
        k = (len(v) - 1) * q
        f = int(math.floor(k))
        c = min(f + 1, len(v) - 1)
        return round(v[f] + (v[c] - v[f]) * (k - f), 3)
    return dict(n=len(mfe),
                mfe_p40=pct(mfe, 0.40), mfe_p60=pct(mfe, 0.60), mfe_p80=pct(mfe, 0.80),
                mae_p50=pct(mae, 0.50), mae_p80=pct(mae, 0.80), mae_p95=pct(mae, 0.95),
                t_touch_p50=pct(tt, 0.50), t_touch_p80=pct(tt, 0.80))


# ============================================================================
# 7. Scoreboard: WR viejo (horizonte) vs WR nuevo (barrera)
# ============================================================================
def old_wr_by_source(conn):
    """WR por (source,horizon) del run más reciente de backtest_signal_outcomes,
    + el set de claves (date,ts_txt,symbol,source) que ese run cubrió."""
    run = conn.execute("SELECT MAX(run_ts) FROM backtest_signal_outcomes").fetchone()[0]
    if run is None:
        return None, None, {}
    rows = conn.execute(
        "SELECT date,ts_txt,symbol,source,horizon,win FROM backtest_signal_outcomes "
        "WHERE run_ts=?", (run,)).fetchall()
    agg = defaultdict(lambda: [0, 0])
    keys = defaultdict(set)
    for date, ts_txt, sym, src, h, win in rows:
        agg[(src, h)][0] += 1
        agg[(src, h)][1] += win or 0
        keys[h].add((date, ts_txt, sym, src))
    return run, agg, keys


def matched_barrier_wr(conn, keys_by_h, k_tp=REF_K_TP, k_sl=REF_K_SL):
    """WR de barrera restringido a las MISMAS señales que el run viejo etiquetó
    (join por (date,ts_txt,symbol,source)), para que el delta sea puro
    re-etiquetado. Devuelve {(source,H): stats}."""
    sig = {}
    for sid, date, ts_txt, sym, src in conn.execute(
            "SELECT id,date,ts_txt,symbol,source FROM %s" % SIG_TABLE):
        sig.setdefault((date, ts_txt, sym, src), []).append(sid)
    out = {}
    for H, keys in keys_by_h.items():
        ids = set()
        for k in keys:
            for sid in sig.get(k, []):
                ids.add(sid)
        if not ids:
            continue
        qmarks = ",".join("?" * min(len(ids), 900))
        rows = []
        ids_l = sorted(ids)
        for a in range(0, len(ids_l), 900):
            chunk = ids_l[a:a + 900]
            rows += conn.execute(
                "SELECT source,label,ambig FROM " + BO_TABLE + " WHERE H=? AND "
                "k_tp=? AND k_sl=? AND signal_id IN (%s)" % ",".join("?" * len(chunk)),
                tuple([H, k_tp, k_sl] + chunk)).fetchall()
        by = defaultdict(list)
        amb = defaultdict(int)
        for src, lab, ambig in rows:
            by[src].append(lab)
            amb[src] += ambig or 0
        for src, labels in by.items():
            st = cell_stats(labels, k_tp, k_sl)
            if st is None:
                out[(src, H)] = None
                continue
            st["ambig"] = amb[src]
            st["ambig_pct"] = round(amb[src] / max(1, st["n"]), 4)
            out[(src, H)] = st
    return out


def confusion(conn, k_tp=REF_K_TP, k_sl=REF_K_SL):
    """Matriz de confusión etiqueta VIEJA (retorno a horizonte) x etiqueta NUEVA
    (triple barrera) sobre las MISMAS señales y el MISMO horizonte.

    Es el número que dice cuánto nos mentíamos:
      old=1 & new=0    -> contada GANADA pero el SL se tocó primero  (LA MENTIRA)
      old=0 & new=1    -> contada PERDIDA pero el TP se tocó primero (el reverso)
      old=1 & new=NULL -> contada GANADA sin resolver ninguna barrera
    Devuelve {(source,H): counters}.
    """
    run = conn.execute("SELECT MAX(run_ts) FROM backtest_signal_outcomes").fetchone()[0]
    if run is None:
        return {}, None
    old = {}
    for date, ts_txt, sym, src, h, win in conn.execute(
            "SELECT date,ts_txt,symbol,source,horizon,win FROM backtest_signal_outcomes "
            "WHERE run_ts=?", (run,)):
        old[(date, ts_txt, sym, src, h)] = win or 0
    sigkey = {}
    for sid, date, ts_txt, sym, src in conn.execute(
            "SELECT id,date,ts_txt,symbol,source FROM %s" % SIG_TABLE):
        sigkey[sid] = (date, ts_txt, sym, src)
    out = defaultdict(lambda: defaultdict(int))
    for sid, H, label in conn.execute(
            "SELECT signal_id,H,label FROM " + BO_TABLE + " WHERE k_tp=? AND k_sl=?",
            (k_tp, k_sl)):
        k = sigkey.get(sid)
        if k is None:
            continue
        ow = old.get((k[0], k[1], k[2], k[3], H))
        if ow is None:
            continue
        c = out[(k[3], H)]
        c["n"] += 1
        if label is None:
            c["old%d_newNULL" % ow] += 1
        else:
            c["old%d_new%d" % (ow, label)] += 1
    return dict(out), run


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def scoreboard(conn, out_path=None):
    run, old, keys = old_wr_by_source(conn)
    rows = load_barrier(conn)
    if not rows:
        raise SystemExit("%s vacia — correr `build` primero" % BO_TABLE)
    agg = aggregate(rows)
    new_matched = matched_barrier_wr(conn, keys) if keys else {}
    dates = sorted(set(r[2] for r in rows))
    syms = sorted(set(r[1] for r in rows))
    n_sig = len(set((r[0], r[3]) for r in rows))

    L = []
    L.append("# EDGE SCOREBOARD — %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("")
    L.append("Etiquetado de **triple barrera** (ficha #1) contra el etiquetado por "
             "**retorno a horizonte** que la flota usa hoy. El timeout es `NULL`, "
             "no una victoria. Barra que contiene TP y SL: **SL primero** "
             "(conservador), y la tasa se publica como `ambig_pct`.")
    L.append("")
    L.append("- Observaciones de barrera: **%d** filas / %d señales etiquetadas / "
             "%d símbolos / %d fechas (%s → %s)"
             % (len(rows), n_sig, len(syms), len(dates),
                dates[0] if dates else "?", dates[-1] if dates else "?"))
    L.append("- Barrido: `k_tp` %s × `k_sl` %s × `H` %s min · modo `%s`"
             % (list(K_TP), list(K_SL), list(HORIZONS), MODE))
    L.append("- `n` = observaciones **resueltas** (TP o SL tocado). `timeouts` no "
             "cuentan en el denominador del WR: se declaran aparte.")
    L.append("")

    L.append("## 1. WR VIEJO (retorno a horizonte) vs WR NUEVO (triple barrera) "
             "— misma población")
    L.append("")
    if not old:
        L.append("> `backtest_signal_outcomes` vacía: no hay baseline con la que comparar.")
    else:
        L.append("Join por `(date, ts_txt, symbol, source)` contra el run viejo "
                 "`%s`. Barrera de referencia `k_tp=%s, k_sl=%s`." % (int(run), REF_K_TP, REF_K_SL))
        L.append("")
        L.append("| fuente | H | n viejo | WR viejo | n resuelta | WR barrera | Wilson barrera | Δ (pp) | timeouts | ambig_pct |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for (src, h) in sorted(old.keys()):
            n_o, w_o = old[(src, h)]
            wr_o = w_o / n_o if n_o else None
            st = new_matched.get((src, h))
            if st is None:
                L.append("| %s | %d | %d | %.3f | — | — | — | **sin barrera** | — | — |"
                         % (src, h, n_o, wr_o))
                continue
            d = (st["p"] - wr_o) * 100
            L.append("| %s | %d | %d | %.3f | %d | **%.3f** | [%.3f, %.3f] | **%+.1f** | %d | %.1f%% |"
                     % (src, h, n_o, wr_o, st["n"], st["p"], st["ci"][0], st["ci"][1],
                        d, st["timeouts"], 100 * st["ambig_pct"]))
    L.append("")

    L.append("### 1b. ¿Cuánto nos mentíamos? Matriz de confusión vieja × nueva")
    L.append("")
    L.append("Sobre las MISMAS señales y el MISMO horizonte, `k_tp=k_sl=%s`:" % REF_K_TP)
    L.append("")
    conf, _crun = confusion(conn)
    if not conf:
        L.append("> sin baseline: `backtest_signal_outcomes` vacía.")
    else:
        L.append("| fuente | H | n | de acuerdo | **vieja=GANADA, barrera=SL primero** | vieja=PERDIDA, barrera=TP primero | vieja=GANADA, barrera sin resolver |")
        L.append("|---|---|---|---|---|---|---|")
        for (src, H) in sorted(conf.keys()):
            c = conf[(src, H)]
            n = c["n"]
            agree = c["old1_new1"] + c["old0_new0"]
            L.append("| %s | %d | %d | %d (%.0f%%) | **%d (%.1f%%)** | %d (%.1f%%) | %d |"
                     % (src, H, n, agree, 100.0 * agree / max(1, n),
                        c["old1_new0"], 100.0 * c["old1_new0"] / max(1, n),
                        c["old0_new1"], 100.0 * c["old0_new1"] / max(1, n),
                        c["old1_newNULL"]))
        L.append("")
        L.append("La columna en negrita es el bug de la ficha #1 hecho número: señales "
                 "que el sistema cuenta como GANADAS y que en un bracket real habrían "
                 "sido **stopeadas antes**. La columna siguiente es el efecto opuesto y "
                 "también real: el retorno a horizonte no ve el TP tocado a mitad de "
                 "camino. **El re-etiquetado no es una resta uniforme: es un cambio de "
                 "definición, y la barrera es la que corresponde a cómo se opera "
                 "(bracket con TP y SL).**")
    L.append("")

    L.append("## 2. Todas las celdas por fuente (población completa de barrera)")
    L.append("")
    L.append("`WR paseo` = win rate ANALÍTICO de un paseo aleatorio sin deriva con esa "
             "geometría de barreras: `k_sl/(k_tp+k_sl)`. Un WR alto con `k_tp` chico no "
             "es edge, es geometría. La columna que importa es **Δ vs paseo**.")
    L.append("")
    L.append("| fuente | k_tp | k_sl | H | n res. | timeouts | WR | Wilson | WR paseo | Δ vs paseo (pp) | expectancia (ATR) | exp CI | ambig_pct | n≥%d |" % MIN_N_CELL)
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for key in sorted(agg.keys()):
        st = agg[key]
        if st is None:
            L.append("| %s | %s | %s | %s | 0 | — | — | — | — | — | — | — | — | no |" % key)
            continue
        p_rw = key[2] / (key[1] + key[2])
        L.append("| %s | %s | %s | %s | %d | %d | %.3f | [%.3f, %.3f] | %.3f | %+.1f | %+.3f | [%+.3f, %+.3f] | %.1f%% | %s |"
                 % (key[0], key[1], key[2], key[3], st["n"], st["timeouts"], st["p"],
                    st["ci"][0], st["ci"][1], p_rw, 100 * (st["p"] - p_rw),
                    st["expectancy"], st["exp_ci"][0],
                    st["exp_ci"][1], 100 * st["ambig_pct"], "SI" if st["trust"] else "no"))
    L.append("")

    L.append("## 3. Celda elegida por fuente (máx Wilson-LB de la EXPECTANCIA) + bracket")
    L.append("")
    L.append("Regla de la ficha: se elige por expectancia, no por win rate. Si el CI "
             "de expectancia de la mejor celda **incluye 0**, la fuente es **NO-TRADE**. "
             "Ninguna celda con n resuelta < %d puede publicar prob." % MIN_N_CELL)
    L.append("")
    L.append("> **ADVERTENCIA DE MULTIPLE TESTING**: esta tabla es el **argmax sobre "
             "hasta %d celdas** por fuente. Un `APTA` aquí NO autoriza voz: es el "
             "mejor de %d intentos y su CI no está corregido ni por multiple testing "
             "ni por correlación entre símbolos. La puerta que decide es "
             "`scripts/null_control.py` (`data/null_control.json`). Hasta que esa "
             "puerta diga `PROBADO`, todo esto es **banner solamente**."
             % (len(K_TP) * len(K_SL) * len(HORIZONS),
                len(K_TP) * len(K_SL) * len(HORIZONS)))
    L.append("")
    L.append("| fuente | celda (k_tp/k_sl/H) | n | WR | exp | exp CI | veredicto | MFE p60 | MAE p80 | t_touch p50 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    srcs = sorted(set(k[0] for k in agg.keys()))
    for src in srcs:
        b = best_cell(agg, src)
        if b is None:
            nmax = max([st["n"] for k, st in agg.items() if k[0] == src and st] or [0])
            L.append("| %s | — | max %d | — | — | — | **DATA-INSUFFICIENT** (n<%d) | — | — | — |"
                     % (src, nmax, MIN_N_CELL))
            continue
        key, st = b
        pc = mfe_mae_percentiles(rows, *key) or {}
        verdict = "NO-TRADE (CI de expectancia cruza 0)" if st["exp_ci"][0] <= 0 <= st["exp_ci"][1] \
            else ("APTA" if st["exp_ci"][0] > 0 else "NEGATIVA (perdedora medida)")
        L.append("| %s | %s/%s/%s | %d | %.3f | %+.3f | [%+.3f, %+.3f] | **%s** | %s | %s | %s |"
                 % (src, key[1], key[2], key[3], st["n"], st["p"], st["expectancy"],
                    st["exp_ci"][0], st["exp_ci"][1], verdict,
                    pc.get("mfe_p60"), pc.get("mae_p80"), pc.get("t_touch_p50")))
    L.append("")
    L.append("## 4. Limitaciones declaradas")
    L.append("")
    amb_all = sum(r[11] or 0 for r in rows)
    res_all = sum(1 for r in rows if r[7] is not None)
    L.append("- **Ambigüedad sub-minuto**: %d de %d observaciones resueltas (%.1f%%) "
             "se resolvieron en una barra que tocaba TP **y** SL. No existe ruta "
             "sub-minuto en `poly_bars`, así que se resolvieron **SL primero**. El "
             "WR real está entre el publicado y el publicado + %.1f pp."
             % (amb_all, res_all, 100.0 * amb_all / max(1, res_all),
                100.0 * amb_all / max(1, res_all)))
    L.append("- **Timeouts**: %d de %d observaciones (%.1f%%) no tocaron ninguna "
             "barrera. Salen del denominador (antes contaban como victoria si el "
             "retorno era >0.05%%)."
             % (len(rows) - res_all, len(rows),
                100.0 * (len(rows) - res_all) / max(1, len(rows))))
    L.append("- **Muestra efectiva**: los Wilson de esta tabla usan `n` CRUDA. La "
             "corrección por correlación (`n_eff`) y el multiple testing viven en "
             "`scripts/null_control.py` → `data/null_control.json` + "
             "`docs/NULL-CONTROL-%s.md`. **Leer los dos**: medido allí, ρ̄≈0.41 en la "
             "flota deja el `n=1154` de bollinger en `n_eff≈89` (los CI de arriba "
             "están estrechados ×3.6)." % time.strftime("%Y-%m-%d"))
    L.append("- **SEÑAL-SOLAMENTE**: nada de esto ordena al broker.")
    L.append("")
    text = "\n".join(L) + "\n"
    if out_path is None:
        out_path = os.path.join(REPO, "docs",
                                "EDGE-SCOREBOARD-%s.md" % time.strftime("%Y-%m-%d"))
    atomic_write(out_path, text)
    return out_path, agg, new_matched


# ============================================================================
# 8. CLI
# ============================================================================
def cmd_build(args):
    ro = sqlite3.connect(DB_RO, uri=True, timeout=30)
    sigs, st = load_signals(ro)
    if not sigs:
        raise SystemExit("ninguna señal con dirección derivable — nada que etiquetar")
    if args.limit:
        sigs = sigs[-args.limit:]
    t0 = min(s["ts"] for s in sigs) - ATR_LOOKBACK_S
    t1 = max(s["ts"] for s in sigs) + (max(HORIZONS) + 5) * 60
    syms = set(s["sym"] for s in sigs)
    bars = load_bars(ro, syms, t0, t1)
    nb = {k: len(v) for k, v in bars.items()}
    empty = sorted(k for k, v in nb.items() if v == 0)
    ro.close()
    rows, st2 = label_all(sigs, bars)
    st.update(st2)
    print("=== barrier_labels build ===")
    print("  señales en BD .............. %d" % st.get("total", 0))
    print("  sin símbolo ................ %d" % st.get("skip_no_symbol", 0))
    print("  sin dirección derivable .... %d  (source='signal' es un relé "
          "heterogéneo: eod_backtest.thesis() no le da tesis)" % st.get("skip_no_direction", 0))
    print("  candidatas ................. %d" % st.get("labelable_candidates", 0))
    for k in ("skip_no_bars_for_symbol", "skip_no_prior_bar", "skip_entry_stale",
              "skip_entry_nonpositive", "skip_atr_insufficient", "skip_no_forward_bars"):
        if st.get(k):
            print("  %-26s %d" % (k + " ....", st[k]))
    print("  ETIQUETADAS ................ %d" % st.get("labeled_signals", 0))
    print("  filas de barrera ........... %d" % st.get("rows", 0))
    print("  de ellas timeout (NULL) .... %d (%.1f%%)"
          % (st.get("timeout_null", 0),
             100.0 * st.get("timeout_null", 0) / max(1, st.get("rows", 1))))
    print("  de ellas ambiguas .......... %d (%.1f%% de las resueltas)"
          % (st.get("ambig", 0),
             100.0 * st.get("ambig", 0) /
             max(1, st.get("rows", 1) - st.get("timeout_null", 0))))
    if empty:
        print("  SIN BARRAS EN poly_bars: %s" % ", ".join(empty))
    if args.dry_run:
        print("  (dry-run: no se escribió nada)")
        return
    rw = connect_rw()
    n = write_rows(rw, rows, time.time())
    rw.close()
    print("  escritas ................... %d filas en trades.db %s" % (n, BO_TABLE))


def cmd_report(args):
    ro = sqlite3.connect(DB_RO, uri=True, timeout=30)
    rows = load_barrier(ro)
    ro.close()
    if not rows:
        raise SystemExit("%s vacia — correr `build` primero" % BO_TABLE)
    agg = aggregate(rows)
    print("=== celdas de barrera (n = RESUELTAS; timeout no cuenta) ===")
    print("%-11s %5s %5s %4s %6s %8s %6s %16s %8s" %
          ("fuente", "k_tp", "k_sl", "H", "n", "timeout", "WR", "Wilson", "exp(ATR)"))
    for key in sorted(agg.keys()):
        st = agg[key]
        if st is None:
            continue
        print("%-11s %5s %5s %4s %6d %8d %6.3f [%.3f,%.3f] %+8.3f"
              % (key[0], key[1], key[2], key[3], st["n"], st["timeouts"], st["p"],
                 st["ci"][0], st["ci"][1], st["expectancy"]))
    print("\n=== celda elegida por fuente (max Wilson-LB de la EXPECTANCIA) ===")
    for src in sorted(set(k[0] for k in agg)):
        b = best_cell(agg, src)
        if b is None:
            print("  %-11s DATA-INSUFFICIENT (ninguna celda con n>=%d)" % (src, MIN_N_CELL))
            continue
        key, st = b
        print("  %-11s k_tp=%s k_sl=%s H=%s  n=%d WR=%.3f exp=%+.3f CI[%+.3f,%+.3f]"
              % (src, key[1], key[2], key[3], st["n"], st["p"], st["expectancy"],
                 st["exp_ci"][0], st["exp_ci"][1]))


def cmd_scoreboard(args):
    ro = sqlite3.connect(DB_RO, uri=True, timeout=30)
    path, agg, matched = scoreboard(ro, args.out)
    ro.close()
    print("scoreboard -> %s" % path)
    for (src, h) in sorted(matched.keys()):
        st = matched[(src, h)]
        if st:
            print("  %-11s H=%-4d WR barrera %.3f (n res=%d, timeouts=%d, ambig %.1f%%)"
                  % (src, h, st["p"], st["n"], st["timeouts"], 100 * st["ambig_pct"]))


def cmd_wf(args):
    ro = sqlite3.connect(DB_RO, uri=True, timeout=30)
    rows = load_barrier(ro)
    ro.close()
    if not rows:
        raise SystemExit("%s vacia — correr `build` primero" % BO_TABLE)
    H = args.H
    obs = sorted(set((r[3], r[0]) for r in rows if r[6] == H))
    starts = [o[0] for o in obs]
    folds = purged_folds(starts, H, args.folds)
    clean = folds_are_clean(starts, folds)
    print("walk-forward purgado H=%d min, %d folds sobre %d observaciones"
          % (H, len(folds), len(starts)))
    for i, fd in enumerate(folds):
        print("  fold %d: test n=%-5d train n=%-5d purgadas+embargo=%d"
              % (i, len(fd["test"]), len(fd["train"]),
                 len(starts) - len(fd["test"]) - len(fd["train"])))
    print("  purga/embargo LIMPIA: %s" % ("SI" if clean else "NO — CONTAMINADO"))
    if not clean:
        raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser(description="etiquetado de triple barrera (ficha #1)")
    ap.add_argument("--signals-table", default="signals",
                    help="tabla de señales (default `signals`; `signals_regen` para la "
                         "historia regenerada -> escribe en barrier_outcomes_regen)")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build");      b.add_argument("--limit", type=int, default=0); b.add_argument("--dry-run", action="store_true")
    sub.add_parser("report")
    s = sub.add_parser("scoreboard"); s.add_argument("--out", default=None)
    w = sub.add_parser("wf");         w.add_argument("--H", type=int, default=30); w.add_argument("--folds", type=int, default=5)
    a = ap.parse_args()
    use_signals_table(a.signals_table)
    if a.cmd == "build":
        cmd_build(a)
    elif a.cmd == "report":
        cmd_report(a)
    elif a.cmd == "scoreboard":
        cmd_scoreboard(a)
    elif a.cmd == "wf":
        cmd_wf(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
