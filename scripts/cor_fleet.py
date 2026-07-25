#!/usr/bin/env python
"""cor_fleet.py — amortiguador de CORRELACION REALIZADA para la regla 12 (jerarquia de capitanes).

Ficha 23 `cor-fleet` de docs/FEATURES-MINED-2026-07-25.md · skill [[peer-captain-evidence]].

QUE HACE
  `rho_real` = correlacion de Pearson MEDIA POR PARES de retornos de 1 minuto sobre los ultimos
  60 minutos, computada DOS VECES: sobre los componentes de QQQ (pesos de index_breadth.WEIGHTS)
  y sobre signal_conditioning.SEMIS. Inner-join de epochs entre series, con la TASA DE DESCARTE
  PUBLICADA y fail-loud por encima del 20% (los nombres iliquidos tienen agujeros).

  `pct_60d` = percentil de `rho_real` frente a sus propias 60 sesiones previas (serie historica
  construida desde `poly_bars` con `--history`). Menos de 60 sesiones -> None CON MOTIVO.

  `regime` = MACRO (pct>0.7 o rho>0.75) / DISPERSION (pct<0.3 o rho<0.45) / MIXED.
  `captain_coef` = 1.25 / 1.0 / 0.75 ; `name_coef` = 0.8 / 1.0 / 1.2.

  ELIMINADO a proposito: `rho_imp` (version implicita). `iv_atm` esta poblado para ~6 de 30
  nombres -> seria un proxy del VIX disfrazado.

COMO ENTRA EN LA FLECHA
  Amortiguador MULTIPLICATIVO sobre los pesos EXISTENTES fleet(1.4) / components(1.3).
  JAMAS un factor aditivo nuevo. El coeficiente aplicado DEBE imprimirse en `why[]`.

LEYES
  SEÑAL-SOLAMENTE: este fichero no pone ordenes jamas.
  Ningun `except` devuelve 0 / 0.0 / 0.5 / 50 / {}. Solo None (con motivo) o levanta.
  Rutas derivadas de __file__. Escritura atomica tmp+os.rename. BD SOLO LECTURA.

USO
  ./venv/bin/python scripts/cor_fleet.py              # vivo -> data/cor_fleet.json
  ./venv/bin/python scripts/cor_fleet.py --history    # reconstruye data/cor_fleet_history.json
  ./venv/bin/python scripts/cor_fleet.py --kill-test  # distribucion de regimenes (¿variable o doctrina?)
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
DATA = os.path.join(REPO, "data")
DB_PATH = os.path.join(REPO, "trades.db")
OUT_PATH = os.path.join(DATA, "cor_fleet.json")
HIST_PATH = os.path.join(DATA, "cor_fleet_history.json")

# --- constantes de la ficha (no inventadas aqui: vienen de la ficha 23) ---
WINDOW_MIN = 60                 # ventana de 60 minutos
MAX_JOIN_DROP_PCT = 20.0        # fail loud por encima del 20%
MIN_RET_OBS = 30                # menos observaciones que esto -> None, no un rho de mentira
HIST_MIN_SESSIONS = 60          # pct_60d exige 60 sesiones previas
MIN_SYMS = 3                    # con 2 syms "media por pares" es un solo par: no es flota

RHO_MACRO = 0.75
RHO_DISP = 0.45
PCT_MACRO = 0.70
PCT_DISP = 0.30

COEFS = {                       # (captain_coef, name_coef)
    "MACRO": (1.25, 0.8),
    "MIXED": (1.0, 1.0),
    "DISPERSION": (0.75, 1.2),
}

# Cobertura MEDIDA 2026-07-25 en poly_bars: 26/30 syms >= 512 sesiones, pero
# SNDK 376, SPCX 388, DRAM 78, SKHY 10. Un sym con 10 sesiones NO entra en un
# percentil de 60 sesiones -> se excluye del HISTORICO con motivo, no se rellena.
HIST_MIN_SYM_SESSIONS = 450


class CorFleetError(RuntimeError):
    """Fallo ruidoso. Preferido siempre a un numero plausible."""


# ---------------------------------------------------------------- universos
def qqq_components():
    """Componentes de QQQ con sus pesos, leidos de scripts/index_breadth.py.

    Se parsea con `ast` en vez de importar el modulo: index_breadth hace
    `import yfinance` (545 ms medidos) y un `os.chdir` al importarse. Si el
    diccionario no esta, se LEVANTA — nunca una lista hardcodeada de respaldo.
    """
    src_path = os.path.join(SCRIPTS, "index_breadth.py")
    try:
        tree = ast.parse(open(src_path, encoding="utf-8").read())
    except Exception as exc:
        raise CorFleetError(f"no se pudo parsear {src_path}: {exc}") from exc
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "WEIGHTS":
                weights = ast.literal_eval(node.value)
                qqq = weights.get("QQQ")
                if not qqq:
                    raise CorFleetError("index_breadth.WEIGHTS no tiene clave 'QQQ'")
                return dict(qqq)
    raise CorFleetError("index_breadth.py no define WEIGHTS")


def semis_universe():
    """signal_conditioning.SEMIS — la tropa de semis del capitan SMH."""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    try:
        from signal_conditioning import SEMIS
    except Exception as exc:
        raise CorFleetError(f"no se pudo leer SEMIS de signal_conditioning: {exc}") from exc
    if not SEMIS:
        raise CorFleetError("signal_conditioning.SEMIS vacio")
    return set(SEMIS)


# ---------------------------------------------------------------- matematica
def inner_join(series):
    """Inner-join por epoch de {sym: {epoch: close}}.

    -> (syms_ordenados, matriz (n_syms x n_epochs) de closes, epochs, join_drop_pct)
    `join_drop_pct` = 100 * (1 - |interseccion| / |union|). Denominador = UNION:
    es la lectura conservadora, la que grita cuando un nombre iliquido tiene agujeros.
    """
    syms = sorted(s for s, d in series.items() if d)
    if len(syms) < MIN_SYMS:
        return syms, None, [], None
    sets = [set(series[s].keys()) for s in syms]
    common = set.intersection(*sets)
    union = set.union(*sets)
    if not union:
        return syms, None, [], None
    drop = 100.0 * (1.0 - len(common) / len(union))
    epochs = sorted(common)
    if not epochs:
        return syms, None, [], drop
    mat = np.array([[series[s][e] for e in epochs] for s in syms], dtype=float)
    return syms, mat, epochs, drop


def mean_pairwise_rho(series, strict=True, max_drop_pct=MAX_JOIN_DROP_PCT):
    """Correlacion de Pearson MEDIA POR PARES de los retornos de 1 minuto.

    series: {sym: {epoch_segundos: close}}. Solo se usan retornos entre epochs
    CONSECUTIVOS del grid comun separados exactamente 60 s (un "retorno" que salta
    un hueco de 20 minutos no es un retorno de 1 minuto).

    strict=True  -> levanta CorFleetError si la tasa de descarte supera el umbral.
    strict=False -> devuelve rho=None con drop_exceeded=True y el motivo.

    NUNCA devuelve un rho por defecto: si no se puede medir, `rho` es None y
    `reason` dice por que.
    """
    out = {"rho": None, "n_pairs": 0, "n_obs": 0, "join_drop_pct": None,
           "syms": [], "drop_exceeded": False, "reason": None}
    syms, mat, epochs, drop = inner_join(series)
    out["syms"] = syms
    if drop is not None:
        out["join_drop_pct"] = round(drop, 3)
    if len(syms) < MIN_SYMS:
        out["reason"] = f"solo {len(syms)} syms con datos (minimo {MIN_SYMS})"
        return out
    if mat is None:
        out["reason"] = "inner-join de epochs vacio"
        return out
    if drop > max_drop_pct:
        out["drop_exceeded"] = True
        out["reason"] = (f"tasa de descarte del inner-join {drop:.1f}% > {max_drop_pct}% "
                         f"({len(epochs)} epochs comunes) — dato no fiable")
        if strict:
            raise CorFleetError(out["reason"])
        return out

    ep = np.asarray(epochs, dtype=np.int64)
    gap_ok = np.diff(ep) == 60
    rets = np.diff(np.log(mat), axis=1)          # (n_syms x n_epochs-1)
    rets = rets[:, gap_ok]
    n_obs = rets.shape[1]
    out["n_obs"] = int(n_obs)
    if n_obs < MIN_RET_OBS:
        out["reason"] = f"solo {n_obs} retornos de 1m utilizables (minimo {MIN_RET_OBS})"
        return out

    sd = rets.std(axis=1)
    live = sd > 0                                 # un sym plano no tiene correlacion definida
    if int(live.sum()) < MIN_SYMS:
        out["reason"] = f"solo {int(live.sum())} syms con varianza no nula"
        return out
    rets = rets[live]
    out["syms"] = [s for s, k in zip(syms, live) if k]

    cm = np.corrcoef(rets)
    iu = np.triu_indices_from(cm, k=1)
    pairs = cm[iu]
    pairs = pairs[np.isfinite(pairs)]
    if pairs.size == 0:
        out["reason"] = "ningun par con correlacion finita"
        return out
    out["rho"] = float(np.mean(pairs))
    out["n_pairs"] = int(pairs.size)
    return out


def percentile_of(value, history):
    """Percentil empirico de `value` en `history` (fraccion estrictamente menor), en [0,1].

    Devuelve None si no hay HIST_MIN_SESSIONS valores. NUNCA 0.5.
    """
    if value is None:
        return None
    hist = [h for h in (history or []) if h is not None]
    if len(hist) < HIST_MIN_SESSIONS:
        return None
    arr = np.asarray(hist[-HIST_MIN_SESSIONS:], dtype=float)
    return float(np.mean(arr < value))


def classify(rho, pct):
    """(regime, captain_coef, name_coef, reason). rho None -> todo None CON MOTIVO."""
    if rho is None:
        return None, None, None, "rho_real no medible"
    if (pct is not None and pct > PCT_MACRO) or rho > RHO_MACRO:
        regime = "MACRO"
    elif (pct is not None and pct < PCT_DISP) or rho < RHO_DISP:
        regime = "DISPERSION"
    else:
        regime = "MIXED"
    cap, name = COEFS[regime]
    return regime, cap, name, None


def head_rho(rho_qqq, rho_smh):
    """El rho que gobierna el regimen: media de las dos patas medibles.

    Si solo una es medible, esa. Si ninguna, None (jamas un 0.0 plausible).
    """
    vals = [v for v in (rho_qqq, rho_smh) if v is not None]
    if not vals:
        return None
    return float(np.mean(vals))


# ---------------------------------------------------------------- lectura de barras vivas
def _bars_path(sym):
    return os.path.join(DATA, f"bars_{sym.lower()}_ibkr.txt")


def load_live_bars(sym, window_min=WINDOW_MIN, now=None):
    """Ultimos `window_min` minutos de data/bars_<sym>_ibkr.txt -> {epoch: close} o None."""
    path = _bars_path(sym)
    if not os.path.exists(path):
        return None
    rows = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                p = ln.split()
                if len(p) < 5:
                    continue
                try:
                    rows[int(float(p[0]))] = float(p[4])
                except ValueError:
                    continue
    except OSError:
        return None
    if not rows:
        return None
    end = max(rows) if now is None else int(now)
    start = end - window_min * 60
    win = {e: c for e, c in rows.items() if start <= e <= end and c > 0}
    return win or None


def live_group(symbols, window_min=WINDOW_MIN, now=None):
    series = {}
    missing = []
    for s in sorted(symbols):
        d = load_live_bars(s, window_min=window_min, now=now)
        if d:
            series[s] = d
        else:
            missing.append(s)
    return series, missing


# ---------------------------------------------------------------- historico (poly_bars)
def _ro_conn(db_path=DB_PATH):
    """SOLO LECTURA. Hay otro proceso escribiendo trades.db: no lo bloqueamos."""
    if not os.path.exists(db_path):
        raise CorFleetError(f"no existe {db_path}")
    uri = "file:" + db_path.replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def db_session_coverage(conn):
    """{sym: n_sesiones} en poly_bars. OJO: `ts` esta en MILISEGUNDOS."""
    q = ("select sym, count(distinct date(ts/1000,'unixepoch')) "
         "from poly_bars group by sym")
    return {s: n for s, n in conn.execute(q)}


def _rth_bounds_utc(day):
    """Ventana RTH (09:30-16:00 ET) del dia `day` (YYYY-MM-DD) en epoch UTC segundos.

    ET = UTC-4 en EDT, UTC-5 en EST. Se resuelve con zoneinfo, sin hardcodear el offset.
    """
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    y, m, d = (int(x) for x in day.split("-"))
    o = datetime(y, m, d, 9, 30, tzinfo=ny).astimezone(timezone.utc).timestamp()
    c = datetime(y, m, d, 16, 0, tzinfo=ny).astimezone(timezone.utc).timestamp()
    return int(o), int(c)


def session_rho(conn, day, symbols, step_min=15, strict=False):
    """rho_real de una sesion historica = MEDIANA de las ventanas de 60 min de la RTH.

    Una sesion no tiene "un" rho instantaneo: la ficha define rho_real sobre 60 minutos.
    Para el percentil de 60 sesiones se resume la sesion por la mediana de sus ventanas
    solapadas (paso de 15 min), que es el valor tipico del dia, no su extremo.
    -> {"rho": float|None, "windows": int, "join_drop_pct": float|None, "reason": str|None}
    """
    o, c = _rth_bounds_utc(day)
    ph = ",".join("?" * len(symbols))
    q = (f"select sym, ts/1000, c from poly_bars where sym in ({ph}) "
         "and ts >= ? and ts <= ? order by ts")
    series = {}
    for sym, ts, close in conn.execute(q, list(symbols) + [o * 1000, c * 1000]):
        if close and close > 0:
            series.setdefault(sym, {})[int(ts)] = float(close)
    if len(series) < MIN_SYMS:
        return {"rho": None, "windows": 0, "join_drop_pct": None,
                "reason": f"solo {len(series)} syms con barras el {day}"}
    rhos, drops = [], []
    t = o
    while t + WINDOW_MIN * 60 <= c:
        sub = {s: {e: v for e, v in d.items() if t <= e <= t + WINDOW_MIN * 60}
               for s, d in series.items()}
        sub = {s: d for s, d in sub.items() if d}
        r = mean_pairwise_rho(sub, strict=strict)
        if r["join_drop_pct"] is not None:
            drops.append(r["join_drop_pct"])
        if r["rho"] is not None:
            rhos.append(r["rho"])
        t += step_min * 60
    if not rhos:
        return {"rho": None, "windows": 0,
                "join_drop_pct": round(float(np.median(drops)), 3) if drops else None,
                "reason": f"ninguna ventana de 60m medible el {day}"}
    return {"rho": float(np.median(rhos)), "windows": len(rhos),
            "join_drop_pct": round(float(np.median(drops)), 3) if drops else None,
            "reason": None}


def build_history(limit_sessions=None, verbose=True):
    """Serie diaria historica de rho_real desde poly_bars -> dict listo para JSON."""
    conn = _ro_conn()
    try:
        cov = db_session_coverage(conn)
        qqq_w = qqq_components()
        semis = semis_universe()
        excluded = {}
        def keep(group):
            out = []
            for s in group:
                n = cov.get(s)
                if n is None:
                    excluded[s] = "ausente en poly_bars"
                elif n < HIST_MIN_SYM_SESSIONS:
                    excluded[s] = f"solo {n} sesiones (< {HIST_MIN_SYM_SESSIONS})"
                else:
                    out.append(s)
            return sorted(out)
        g_qqq = keep(qqq_w.keys())
        g_smh = keep(semis)
        if len(g_qqq) < MIN_SYMS or len(g_smh) < MIN_SYMS:
            raise CorFleetError(f"universos insuficientes: qqq={g_qqq} semis={g_smh}")
        days = [d for (d,) in conn.execute(
            "select distinct date(ts/1000,'unixepoch') from poly_bars order by 1")]
        days = [d for d in days if d]
        if limit_sessions:
            days = days[-limit_sessions:]
        rows = []
        for i, day in enumerate(days):
            rq = session_rho(conn, day, g_qqq)
            rs = session_rho(conn, day, g_smh)
            rows.append({
                "date": day,
                "rho_qqq": None if rq["rho"] is None else round(rq["rho"], 4),
                "rho_smh": None if rs["rho"] is None else round(rs["rho"], 4),
                "rho_head": None if head_rho(rq["rho"], rs["rho"]) is None
                            else round(head_rho(rq["rho"], rs["rho"]), 4),
                "windows_qqq": rq["windows"], "windows_smh": rs["windows"],
                "join_drop_qqq": rq["join_drop_pct"], "join_drop_smh": rs["join_drop_pct"],
                # MEDIDO 2026-07-25: las 39 fechas sin rho son 34 sabados (filas UTC del
                # after-hours del viernes) + 5 festivos con NYSE cerrada. Cero sesiones
                # reales perdidas. El motivo se guarda para que sea auditable, no se borra.
                "reason": rq["reason"] or rs["reason"],
                "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][
                    datetime(*(int(x) for x in day.split("-"))).weekday()],
            })
            if verbose and (i + 1) % 25 == 0:
                print(f"  ... {i+1}/{len(days)} sesiones", file=sys.stderr, flush=True)
        return {
            "generated_at": int(time.time()),
            "source": "poly_bars (ts en MILISEGUNDOS; RTH 09:30-16:00 ET)",
            "window_min": WINDOW_MIN, "step_min": 15,
            "universe_qqq": g_qqq, "universe_semis": g_smh,
            "excluded": excluded,
            "sessions": rows,
        }
    finally:
        conn.close()


def load_history(path=HIST_PATH):
    """-> lista de sesiones o None (jamas [] silencioso disfrazado de 'no hay regimen')."""
    if not os.path.exists(path):
        return None
    try:
        h = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    rows = h.get("sessions")
    return rows if rows else None


# ---------------------------------------------------------------- kill-test
def kill_test(history=None, path=HIST_PATH):
    """¿VARIABLE DE ESTADO o DOCTRINA? Distribucion de regimenes sobre el historico.

    Para cada sesion se clasifica con su propio pct_60d (60 sesiones PREVIAS, sin
    mirar el futuro). Si MACRO > 90% de las sesiones, el amortiguador es una
    CONSTANTE y la feature queda REFUTADA como variable de estado — eso es un
    resultado valido, no un fallo.
    """
    rows = history if history is not None else load_history(path)
    if not rows:
        raise CorFleetError(f"no hay historico en {path}: corre --history primero")
    heads = [r["rho_head"] for r in rows]
    counts = {"MACRO": 0, "MIXED": 0, "DISPERSION": 0}
    unclassified = 0
    detail = []
    for i, r in enumerate(rows):
        rho = r["rho_head"]
        pct = percentile_of(rho, heads[:i])
        reg, cap, name, _ = classify(rho, pct)
        if reg is None:
            unclassified += 1
            continue
        counts[reg] += 1
        detail.append({"date": r["date"], "rho": rho, "pct": pct, "regime": reg,
                       "captain_coef": cap, "name_coef": name})
    n = sum(counts.values())
    if n == 0:
        raise CorFleetError("ninguna sesion clasificable")
    frac = {k: v / n for k, v in counts.items()}
    n_pct = sum(1 for d in detail if d["pct"] is not None)
    vals = [h for h in heads if h is not None]
    verdict = ("REFUTADA como variable de estado -> DOCTRINA FIJA"
               if max(frac.values()) > 0.90 else
               "SOSTENIDA como variable de estado")
    return {
        "n_sessions": n, "unclassified": unclassified,
        "counts": counts, "frac": {k: round(v, 4) for k, v in frac.items()},
        "n_with_pct": n_pct,
        "rho_head_stats": {
            "min": round(float(np.min(vals)), 4), "p05": round(float(np.percentile(vals, 5)), 4),
            "p25": round(float(np.percentile(vals, 25)), 4),
            "median": round(float(np.median(vals)), 4),
            "p75": round(float(np.percentile(vals, 75)), 4),
            "p95": round(float(np.percentile(vals, 95)), 4),
            "max": round(float(np.max(vals)), 4), "mean": round(float(np.mean(vals)), 4),
        },
        "dominant_frac": round(max(frac.values()), 4),
        "verdict": verdict,
        "detail": detail,
    }


# ---------------------------------------------------------------- vivo
def compute_live(now=None, strict=True, history_path=HIST_PATH):
    """Estado actual -> dict con el esquema de la ficha 23."""
    qqq_w = qqq_components()
    semis = semis_universe()
    s_qqq, miss_qqq = live_group(qqq_w.keys(), now=now)
    s_smh, miss_smh = live_group(semis, now=now)
    r_qqq = mean_pairwise_rho(s_qqq, strict=strict)
    r_smh = mean_pairwise_rho(s_smh, strict=strict)

    rho_head = head_rho(r_qqq["rho"], r_smh["rho"])
    hist = load_history(history_path)
    pct = None
    pct_reason = None
    if hist is None:
        pct_reason = f"sin historico ({os.path.basename(history_path)} ausente): corre --history"
    else:
        heads = [h for h in (r["rho_head"] for r in hist) if h is not None]
        pct = percentile_of(rho_head, heads)
        if pct is None:
            pct_reason = (f"solo {len(heads)} sesiones de historia (< {HIST_MIN_SESSIONS}) "
                          "o rho_real no medible")
    regime, cap, name, reason = classify(rho_head, pct)

    drops = [d for d in (r_qqq["join_drop_pct"], r_smh["join_drop_pct"]) if d is not None]
    # EDAD DEL DATO, no de la escritura: con la flota parada los bars_*.txt siguen ahi
    # y un rho de hace 6 horas moveria los pesos de la flecha de hoy. Se publica.
    last_bar = max([max(d) for d in list(s_qqq.values()) + list(s_smh.values())] or [0])
    data_age_s = int((now or time.time()) - last_bar) if last_bar else None
    return {
        "rho_real_qqq": None if r_qqq["rho"] is None else round(r_qqq["rho"], 4),
        "rho_real_smh": None if r_smh["rho"] is None else round(r_smh["rho"], 4),
        "rho_head": None if rho_head is None else round(rho_head, 4),
        "pct_60d": None if pct is None else round(pct, 4),
        "pct_60d_reason": pct_reason,
        "regime": regime,
        "captain_coef": cap,
        "name_coef": name,
        "join_drop_pct": round(max(drops), 3) if drops else None,
        "n_pairs": r_qqq["n_pairs"] + r_smh["n_pairs"],
        "generated_at": int(time.time()),
        "data_age_s": data_age_s,
        "window_min": WINDOW_MIN,
        "detail": {
            "qqq": {k: r_qqq[k] for k in ("n_pairs", "n_obs", "join_drop_pct",
                                          "drop_exceeded", "reason", "syms")},
            "smh": {k: r_smh[k] for k in ("n_pairs", "n_obs", "join_drop_pct",
                                          "drop_exceeded", "reason", "syms")},
            "missing_bars_qqq": miss_qqq, "missing_bars_smh": miss_smh,
            "regime_reason": reason,
        },
        "why": why_line(regime, cap, rho_head),
        "signal_only": True,
    }


def why_line(regime, captain_coef, rho):
    """La linea que DEBE acabar en why[] de la flecha — inauditable si no se imprime."""
    if regime is None or captain_coef is None:
        return "cor-fleet: rho_real no medible -> sin amortiguador (coef 1.0 implicito)"
    return (f"cor-fleet {regime}: capitan x{captain_coef:g}, rho {rho:.2f}"
            if rho is not None else f"cor-fleet {regime}: capitan x{captain_coef:g}")


# ---------------------------------------------------------------- consumidores
def captain_damper(path=OUT_PATH, max_age_s=1800, max_data_age_s=1800):
    """Hook para direction_view: (captain_coef, name_coef, why) o (1.0, 1.0, None).

    MULTIPLICATIVO sobre pesos EXISTENTES. Si el fichero falta, esta rancio, o las
    BARRAS que lo alimentaron estan rancias, los coeficientes son 1.0 = NEUTRO
    MULTIPLICATIVO (la identidad, no un valor inventado: multiplicar por 1 es
    exactamente "no aplicar amortiguador").
    """
    try:
        st = json.load(open(path, encoding="utf-8"))
    except Exception:
        return 1.0, 1.0, None
    if time.time() - st.get("generated_at", 0) > max_age_s:
        return 1.0, 1.0, None
    age = st.get("data_age_s")
    if age is None or age > max_data_age_s:
        return 1.0, 1.0, None
    cap, name = st.get("captain_coef"), st.get("name_coef")
    if not isinstance(cap, (int, float)) or not isinstance(name, (int, float)):
        return 1.0, 1.0, None
    return float(cap), float(name), st.get("why")


def apply_damper(weights, captain_coef, families=("fleet", "components")):
    """Aplica el amortiguador a los pesos EXISTENTES. MULTIPLICATIVO, in-place-free.

    Devuelve un dict NUEVO con exactamente las MISMAS claves: si esta funcion
    añadiera una familia, la flecha rompería su tope duro de familias. Por eso el
    invariante se comprueba aqui y se levanta si se viola.
    """
    out = dict(weights)
    if captain_coef is None or captain_coef == 1.0:
        return out
    for fam in families:
        if fam in out:
            out[fam] = round(float(out[fam]) * float(captain_coef), 4)
    if set(out) != set(weights):
        raise CorFleetError("el amortiguador añadio una familia de pesos: prohibido")
    return out


# ---------------------------------------------------------------- io
def write_atomic(path, obj):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="cor-fleet — correlacion realizada de la flota")
    ap.add_argument("--history", action="store_true",
                    help="reconstruye data/cor_fleet_history.json desde poly_bars")
    ap.add_argument("--kill-test", action="store_true",
                    help="distribucion de regimenes: ¿variable de estado o doctrina?")
    ap.add_argument("--sessions", type=int, default=None,
                    help="limitar el historico a las N ultimas sesiones")
    ap.add_argument("--lenient", action="store_true",
                    help="no levantar si la tasa de descarte supera el umbral (marca el campo)")
    a = ap.parse_args(argv)

    if a.history:
        h = build_history(limit_sessions=a.sessions)
        write_atomic(HIST_PATH, h)
        ok = sum(1 for r in h["sessions"] if r["rho_head"] is not None)
        print(f"historico: {len(h['sessions'])} sesiones, {ok} con rho_head -> {HIST_PATH}")
        print(f"universo QQQ ({len(h['universe_qqq'])}): {' '.join(h['universe_qqq'])}")
        print(f"universo SEMIS ({len(h['universe_semis'])}): {' '.join(h['universe_semis'])}")
        print(f"excluidos: {h['excluded']}")
        return 0

    if a.kill_test:
        k = kill_test()
        print(f"n={k['n_sessions']} sesiones ({k['n_with_pct']} con pct_60d), "
              f"{k['unclassified']} sin clasificar")
        for reg in ("MACRO", "MIXED", "DISPERSION"):
            print(f"  {reg:11} {k['counts'][reg]:4}  {k['frac'][reg]*100:5.1f}%")
        print(f"rho_head: {k['rho_head_stats']}")
        print(f"VEREDICTO: {k['verdict']} (dominante {k['dominant_frac']*100:.1f}%)")
        return 0

    st = compute_live(strict=not a.lenient)
    write_atomic(OUT_PATH, st)
    print(json.dumps({k: v for k, v in st.items() if k != "detail"},
                     indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
