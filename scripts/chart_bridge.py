#!/usr/bin/env python3
"""chart_bridge.py — puente REALTIME para el chart estilo TradingView (2026-07-23).

SEÑAL-SOLAMENTE. Este proceso JAMAS coloca/modifica/cancela ordenes: solo LEE barras
(reqHistoricalData keepUpToDate) y las sirve por WebSocket al chart. Sin `placeOrder`,
sin `bracketOrder`, sin ejecucion en ninguna rama (ver assert_signal_only()).

Reutiliza el MISMO calculo que los engines/backtests (paridad total):
  - indicadores BB(20,2)/SMA20,40,100,200/VWAP-dia/MACD(12,26,9): confluence_engine.
  - GEX / gamma-flip / muros put-call: gex_core via charts/data/levels_<sym>.json
    (lo genera chart_levels.py; aqui SOLO se consume, no se recomputa).

Combo = BB + set SMA de Yoel + VWAP + MACD + volumen  +  overlays GEX/flip/muros.

Arquitectura:
  - FastAPI (uvicorn) sirve charts/live.html en `/` y el stream en `/stream` (WS).
  - Fuente de barras:
      LIVE  : ib_async (clientId 60, port 7496 live / 7497 paper) reqHistoricalData
              1-min keepUpToDate=True, useRTH=False (premarket/afterhours).
      MOCK  : lee el tail de data/backtest/bars3mo5m_<sym>.csv y lo emite en un timer,
              para probar TODO el pipeline OFFLINE sin TWS (--mock).
  - Al conectar un cliente WS: frame {type:"history", bars, indicators, levels}.
    Por cada barra nueva: broadcast {type:"bar", bar, indicators, levels}.

Python 3.10+ requerido para ib_async (fork mantenido de ib_insync). El venv del repo
es 3.9 SIN fastapi/ib_async: crear uno nuevo -> ver docs/CHART-LIVE-2026-07-23.md.
El nucleo de indicadores + carga de niveles NO depende de fastapi/ib_async: se puede
importar y auto-testear en 3.9 con `--selftest`.

Uso:
  python -m uvicorn scripts.chart_bridge:app                # live 7496, sym focus/nvda
  python scripts/chart_bridge.py --mock --sym nvda          # demo offline (necesita fastapi)
  python scripts/chart_bridge.py --mock --mock-dir /tmp/rp --sym qqq   # sandbox de ./replay
  python3 scripts/chart_bridge.py --selftest --sym nvda     # sin fastapi: valida frames
  python scripts/chart_bridge.py --sym mu --port 7497       # live paper
"""
import argparse
import asyncio
import csv
import glob
import json
import math
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)

# --- reuso de la matematica de los engines (paridad con backtests) ---
import confluence_engine as ce   # sma, stdev, ema_series (causales, población ÷N)
import chart_levels              # gen(sym) -> charts/data/levels_<sym>.json
import narrator                  # narrador de mercado: determinista (gratis) + DeepSeek
import order_ticket              # ficha 0DTE lista para el HUMANO (build); SEÑAL-SOLAMENTE
import direction_view            # sesgo direccional compuesto (flecha overlay); SEÑAL-SOLAMENTE
import signal_conditioning       # SPEAK_MIN: umbral de voz único (regla should_speak)
import ib_mode                   # fuente única paper/live (data/ib_mode.txt) — sin puertos hardcodeados
import rt_last                   # print WS canónico: epoch/precio/fuente con guarda de frescura

# NOTA: importar confluence_engine hace os.chdir(REPO) (efecto de modulo). Reforzamos.
os.chdir(REPO)

LEVELS_DIR = os.path.join(REPO, "charts", "data")
LIVE_HTML = os.path.join(REPO, "charts", "live.html")
DEFAULT_SYM = "nvda"

# SANDBOX DE REPLAY (--mock-dir): barras y cadena del MISMO instante. El CSV de backtest
# arranca en 2026-04-23 y su spot cae fuera de la banda de strikes de cualquier cadena de
# hoy -> perfil vacío y muros None: con ese arnés no se puede QA-ear un muro.
MOCK_DIR = None
MOCK_DIR_MARKER = ".replay-sandbox"


def set_mock_dir(path):
    """Fija el sandbox de ./replay como fuente del modo mock (exige su marcador: sin él
    podríamos estar apuntando a producción y el mock jamás lee producción)."""
    global MOCK_DIR
    if not path:
        return None
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(os.path.join(p, MOCK_DIR_MARKER)):
        sys.exit(f"--mock-dir {p} no es un sandbox de replay (falta {MOCK_DIR_MARKER})")
    if os.path.realpath(p) == os.path.realpath(REPO):
        sys.exit("--mock-dir no puede ser el repo (el mock nunca lee producción)")
    MOCK_DIR = p
    return p

# --- timeframes (TradingView-like) ---------------------------------------
# MOCK: la base del CSV es 5m; agregamos hacia arriba. "1m" no tiene fuente
# offline -> cae a 5m (con nota en consola). LIVE: se re-pide reqHistoricalData
# con el barSize nativo (ver live_reapply).
# IBKR barSizes VALIDOS: 1/5/10/15/30 secs · 1/5/10/15/20/30 min · 1/2/3/4/8 hour ·
# 1 day/week/month. 45m NO existe en IBKR -> se OMITE. Se añade 20m que SI es nativo.
# Todos los de minutos/horas tienen barSize nativo -> LIVE limpio; en MOCK se agregan
# desde la base 5m (ce.aggregate, cualquier multiplo).
#
# SEGUNDOS (Yunior 2026-07-26, orden vieja recuperada de TODOS.md): 5s/15s/30s son
# NATIVOS de reqHistoricalData; 45s NO existe en IBKR -> se AGREGA de 15s x3 por
# epoch (agg_epoch, ver AGG_TF). MOCK no tiene fuente sub-minuto (CSV 5m / sandbox
# 1m) -> set_timeframe degrada con nodata en vez de fingir. Profundidad MEDIDA contra
# el Gateway LIVE (4001, QQQ, 2026-07-26 domingo RTH cerrado): "1 secs" tope duro
# 1800 S (invalid step con 3600 S+); "5 secs" OK hasta 1 D (11520 barras); "15 secs"
# OK hasta 2 D; "30 secs" OK hasta 5 D. Duraciones abajo son subconjuntos seguros de
# lo medido (payload inicial liviano, ~200-700 barras) — nunca superan el techo.
SEC_TF = frozenset({"5s", "15s", "30s", "45s"})
AGG_TF = {"45s": ("15s", 45)}   # tf derivado -> (tf base nativo, bucket en segundos)
TF_LIST = ("5s", "15s", "30s", "45s",
           "1m", "5m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "1d", "1W", "1M")
TF_MIN = {"1m": 5, "5m": 5, "15m": 15, "20m": 20, "30m": 30, "1h": 60,
          "2h": 120, "3h": 180, "4h": 240, "1d": 1440,
          "1W": 10080, "1M": 43200}   # minutos por bucket (mock, agregacion 5m)
ALL_TF = frozenset(TF_MIN) | SEC_TF   # tf validos para {cmd:"tf"} (set_timeframe)
# segundos por bucket de los tf intradia (1d+ fuera: su vela no se mueve overnight)
TF_S = {"5s": 5, "15s": 15, "30s": 30, "45s": 45, "1m": 60, "5m": 300, "15m": 900,
        "20m": 1200, "30m": 1800, "1h": 3600, "2h": 7200, "3h": 10800, "4h": 14400}
STALE_SUB_S = 120   # sub keepUpToDate sin barra nueva en N s = congelada (medido: para a las 20:00 ET)
RT_FALLBACK_MAX_AGE_S = 10.0  # un print WS más viejo no mueve una vela ni parece realtime
RT_FALLBACK_SOURCES = frozenset({"finnhub"})
BAR_FALLBACK_POLL_S = 5.0     # OHLC/volumen lento; no releer 780 líneas a ritmo de tick
LIVE_BAR = {  # (barSizeSetting, durationStr) para reqHistoricalData en LIVE
    "5s": ("5 secs", "3600 S"), "15s": ("15 secs", "7200 S"), "30s": ("30 secs", "14400 S"),
    "1m": ("1 min", "2 D"), "5m": ("5 mins", "5 D"), "15m": ("15 mins", "10 D"),
    "20m": ("20 mins", "10 D"), "30m": ("30 mins", "20 D"),
    "1h": ("1 hour", "30 D"), "2h": ("2 hours", "60 D"),
    "3h": ("3 hours", "90 D"), "4h": ("4 hours", "120 D"),
    "1d": ("1 day", "1 Y"), "1W": ("1 week", "1 Y"), "1M": ("1 month", "2 Y"),
}
DEFAULT_TF_MOCK = "5m"
DEFAULT_TF_LIVE = "1m"


# ============================ SEÑAL-SOLAMENTE (guardia) =======================
def assert_signal_only():
    """Fail-loud: este modulo no debe INVOCAR ninguna función de ejecución de órdenes.
    Barrera de la ley 2026-07-16 (ib-trader nunca ejecuta). Se inspecciona el AST y se
    miran las LLAMADAS reales (ast.Call), no el texto — así los nombres prohibidos que
    aparecen en esta lista o en el docstring no dan falso positivo."""
    import ast as _ast
    banned = {"placeOrder", "bracketOrder", "reqExecutions", "marketOrder",
              "limitOrder", "stopOrder", "cancelOrder", "reqGlobalCancel"}
    try:
        tree = _ast.parse(open(os.path.abspath(__file__)).read())
    except Exception:
        return
    hits = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, _ast.Attribute) else (
                fn.id if isinstance(fn, _ast.Name) else None)
            if name in banned:
                hits.add(name)
    assert not hits, f"SEÑAL-SOLAMENTE VIOLADO: se invoca {hits} en chart_bridge.py"


# ================================ datos / sym =================================
def resolve_sym(cli_sym):
    if cli_sym:
        return cli_sym.lower()
    ft = os.path.join(REPO, "data", "focus_ticker")
    try:
        with open(ft) as f:
            first = f.readline().split()
            if first:
                return first[0].lower()
    except Exception:
        pass
    return DEFAULT_SYM


def load_csv_bars(sym, tail=None):
    """Barras 5m de data/backtest/bars3mo5m_<sym>.csv -> [[epoch,o,h,l,c,v], ...]."""
    p = os.path.join(REPO, "data", "backtest", f"bars3mo5m_{sym}.csv")
    rows = []
    if not os.path.exists(p):
        return rows
    for r in csv.reader(open(p)):
        if not r or r[0] == "epoch":
            continue
        try:
            rows.append([int(r[0]), float(r[1]), float(r[2]),
                         float(r[3]), float(r[4]), float(r[5])])
        except Exception:
            continue
    rows.sort(key=lambda x: x[0])
    if tail:
        rows = rows[-tail:]
    return rows


def _bars_from_txt(path, tail):
    """`ts o h l c v` por línea (formato de ibkr_bar_bridge::emit y del sandbox de replay)."""
    rows = []
    if not os.path.exists(path):
        return rows
    for ln in open(path):
        f = ln.split()
        if len(f) >= 5:
            try:
                rows.append([int(f[0]), float(f[1]), float(f[2]), float(f[3]),
                             float(f[4]), float(f[5]) if len(f) > 5 else 0.0])
            except Exception:
                continue
    return rows[-tail:] if tail else rows


# korea_bar_bridge.py escribe realtime IBKR (mdt=1, sub waived) SIN el sufijo _ibkr:
# data/bars_<stem>.txt. Nombre de display = stem en mayúsculas -> sym.lower() == stem,
# no hace falta tabla de mapeo. Proceso propio (clientId 86), no el contrato de este bridge.
# Fuente unica del set (orden Yunior 2026-07-27 "avoid hardcoded shit"): korea_bar_bridge.py
# escribe data/korea_syms.txt con sus KOREA.keys() vigentes; aqui solo se LEE, cacheado.
_KOREA_SYMS_PATH = os.path.join(REPO, "data", "korea_syms.txt")
_korea_syms_cache = {"t": 0.0, "syms": frozenset()}


def KOREA_SYMS():
    """frozenset de simbolos KRX vigentes. Vacio (no crashea) si el puente aun no escribio
    el fichero -> sin Korea en la watchlist hasta que exista, nunca una lista adivinada."""
    now = time.time()
    if now - _korea_syms_cache["t"] > 30:
        try:
            with open(_KOREA_SYMS_PATH) as f:
                _korea_syms_cache["syms"] = frozenset(
                    ln.strip().upper() for ln in f if ln.strip())
        except OSError:
            pass
        _korea_syms_cache["t"] = now
    return _korea_syms_cache["syms"]


def load_ibkr_bars(sym, tail=780):
    """Barras 1m VIVAS de data/bars_<sym>_ibkr.txt (el fleet bar_bridge las mantiene para
    los 33 símbolos). Archivo OS-page-cacheado -> lectura a velocidad RAM. Se usa para
    mostrar el chart AL INSTANTE al cambiar de símbolo (sin esperar el round-trip a TWS);
    la suscripción viva se re-ata en background. [ts,o,h,l,c,v]."""
    if sym.upper() in KOREA_SYMS():
        return _bars_from_txt(os.path.join(REPO, "data", f"bars_{sym.lower()}.txt"), tail)
    return _bars_from_txt(os.path.join(REPO, "data", f"bars_{sym.lower()}_ibkr.txt"), tail)


def load_sandbox_bars(sym, tail=780):
    """Barras 1m del sandbox de ./replay: las MISMAS que lee compass, y del mismo instante
    que la cadena que el replay publica ahí -> el spot cae DENTRO del libro."""
    if not MOCK_DIR:
        return []
    return _bars_from_txt(os.path.join(MOCK_DIR, "data", f"bars_{sym.lower()}_ibkr.txt"), tail)


def load_sandbox_levels(sym):
    """Mapa del sandbox tal cual lo dejó ./replay (chart_levels con el reloj congelado en el
    as-of de la cadena). NO se regenera aquí: la cadena es histórica y el reloj de este
    proceso es el de hoy -> gen() la daría por expirada. None = no hay mapa (no {})."""
    if not MOCK_DIR:
        return None
    try:
        with open(os.path.join(MOCK_DIR, "charts", "data", f"levels_{sym.lower()}.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_levels(sym, max_age_s=2700, all_exp=False):
    """Lee charts/data/levels_<sym>.json. Si falta/está viejo intenta regenerar via
    chart_levels.gen (que lee el cache TWS opt_chain). Degradacion limpia: si no hay
    cache ni json, devuelve {} y el chart sigue sin overlays GEX."""
    if MOCK_DIR:
        return load_sandbox_levels(sym)
    p = os.path.join(LEVELS_DIR, f"levels_{sym}.json")
    fresh = os.path.exists(p) and (time.time() - os.path.getmtime(p) < max_age_s)
    if not fresh:
        try:
            g = chart_levels.gen(sym, all_exp=all_exp)
            if g:
                return g
        except Exception as e:
            print(f"[levels] gen({sym}) falló ({e}); uso json en disco si existe")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return {}
    return {}


WALL_KEYS = ("call_wall", "put_wall", "flip")


def chain_strike_range(lv):
    """(min,max) de strikes de la cadena con la que se calculó el mapa; None si no se puede
    leer — sin cadena no se afirma por qué faltan los muros."""
    p = (lv or {}).get("chain_path")
    if not p:
        return None
    if not os.path.isabs(p):
        p = os.path.join(MOCK_DIR or REPO, p)
    lo = hi = None
    try:
        with open(p) as f:
            for ln in f:
                if ln.startswith("#"):
                    continue
                try:
                    k = float(ln.split()[0])
                except (IndexError, ValueError):
                    continue
                lo = k if lo is None or k < lo else lo
                hi = k if hi is None or k > hi else hi
    except OSError:
        return None
    return (lo, hi) if lo is not None else None


def walls_status(lv, spot):
    """None si los muros traen NUMEROS; si no, la razón. Un muro fabricado es peor que
    ningún muro: el chart publicaba `None` mudo y el QA no distinguía 'no hay libro' de
    'el cálculo falló'."""
    if not lv:
        return "sin mapa GEX"
    if all(lv.get(k) is not None for k in WALL_KEYS):
        return None
    rng = chain_strike_range(lv)
    if rng and spot is not None and not (rng[0] <= spot <= rng[1]):
        return "spot fuera del libro"
    if not (lv.get("profile") or []):
        return "perfil GEX vacío"
    return "muros sin calcular"


# =============================== indicadores =================================
def _wilder_atr(bars, n):
    """ATR de Wilder (RMA) — igual que ta.atr de Pine (el default del Supertrend de
    combo_tl con changeATR=true). Semilla SMA del TR y luego suavizado de Wilder.
    Local al chart: NO toca ce.atr_series (que es SMA y da paridad con los backtests)."""
    out = [None] * len(bars)
    trs = []
    atr = None
    for i in range(len(bars)):
        h, l = bars[i][2], bars[i][3]
        tr = (h - l) if i == 0 else max(h - l, abs(h - bars[i - 1][4]), abs(l - bars[i - 1][4]))
        trs.append(tr)
        if i + 1 == n:
            atr = sum(trs) / n; out[i] = atr
        elif i + 1 > n:
            atr = (atr * (n - 1) + tr) / n; out[i] = atr
    return out


def supertrend(bars, period=10, mult=3.0):
    """Supertrend clásico (ATR 10 Wilder/RMA, mult 3.0) — igual que combo_tl.pine.
    Devuelve (stUp, stDn, markers): stUp[i]=valor si tendencia ALCISTA (línea bajo
    precio) else None; stDn[i]=valor si BAJISTA else None (huecos None = estilo
    'break' como plot.style_linebr en Pine). markers = flips Buy/Sell."""
    n = len(bars)
    atr = _wilder_atr(bars, period)
    stUp = [None] * n
    stDn = [None] * n
    markers = []
    prev_fu = prev_fl = prev_st = None
    prev_dir = 0
    for i in range(n):
        if atr[i] is None:
            continue
        h, l, c = bars[i][2], bars[i][3], bars[i][4]
        hl2 = (h + l) / 2.0
        bu = hl2 + mult * atr[i]
        bl = hl2 - mult * atr[i]
        pc = bars[i - 1][4] if i > 0 else c
        fu = bu if (prev_fu is None or bu < prev_fu or pc > prev_fu) else prev_fu
        fl = bl if (prev_fl is None or bl > prev_fl or pc < prev_fl) else prev_fl
        if prev_st is None:
            cur_dir = 1 if c >= hl2 else -1
            cur_st = fl if cur_dir == 1 else fu
        else:
            if prev_st == prev_fu:            # venía en banda superior (bajista)
                cur_st = fu if c <= fu else fl
            else:                             # venía en banda inferior (alcista)
                cur_st = fl if c >= fl else fu
            cur_dir = 1 if cur_st == fl else -1
        if cur_dir == 1:
            stUp[i] = round(cur_st, 4)
        else:
            stDn[i] = round(cur_st, 4)
        if prev_dir != 0 and cur_dir != prev_dir:
            if cur_dir == 1:   # flip alcista -> "Buy" verde abajo (como combo_tl.pine)
                markers.append({"time": bars[i][0], "position": "belowBar",
                                "color": "#26a69a", "shape": "arrowUp", "text": "Buy"})
            else:              # flip bajista -> "Sell" rojo arriba
                markers.append({"time": bars[i][0], "position": "aboveBar",
                                "color": "#ef5350", "shape": "arrowDown", "text": "Sell"})
        prev_fu, prev_fl, prev_st, prev_dir = fu, fl, cur_st, cur_dir
    return stUp, stDn, markers


def compute_trendlines(bars, lb=5):
    """Auto-trendlines con breaks (esencia LuxAlgo, no 1:1). Pivotes causales
    (confirmados lb barras después). Últimos 2 pivot-LOWS -> línea alcista;
    últimos 2 pivot-HIGHS -> línea bajista. Cada punto = {time, value}."""
    n = len(bars)
    ph, pl = [], []
    if n >= 2 * lb + 2:
        for i in range(lb, n - lb):
            wh = [bars[j][2] for j in range(i - lb, i + lb + 1)]
            wl = [bars[j][3] for j in range(i - lb, i + lb + 1)]
            if bars[i][2] == max(wh):
                ph.append({"time": bars[i][0], "value": round(bars[i][2], 4)})
            if bars[i][3] == min(wl):
                pl.append({"time": bars[i][0], "value": round(bars[i][3], 4)})
    up = {"p1": pl[-2], "p2": pl[-1]} if len(pl) >= 2 else None
    dn = {"p1": ph[-2], "p2": ph[-1]} if len(ph) >= 2 else None
    return {"up": up, "dn": dn}


# --- Madrid Moving Average Ribbon (combo_tl ④, MPL 2.0) ----------------------
# 18 EMAs (5..90 paso 5) coloreadas POR SEGMENTO vs la EMA100 de referencia,
# igual que el pine: LIMA (sube y>ref) / MARRON (baja y>ref) / ROJO (baja y<ref)
# / VERDE (sube y<ref) / GRIS. Las de 5 y 90 van más gruesas.
MMA_LENS = list(range(5, 95, 5))   # 5,10,...,90  (18 medias)
MMA_LIME, MMA_GREEN, MMA_RUBI, MMA_MAROON, MMA_GRAY = "#00e676", "#00796b", "#ff1744", "#8e2b2b", "#5c6470"


def _mma_color(ma, ma_prev, ref):
    if ma is None or ref is None:
        return None
    diff = 0.0 if ma_prev is None else ma - ma_prev
    if diff >= 0 and ma > ref:
        return MMA_LIME
    if diff < 0 and ma > ref:
        return MMA_MAROON
    if diff <= 0 and ma < ref:
        return MMA_RUBI
    if diff >= 0 and ma < ref:
        return MMA_GREEN
    return MMA_GRAY


def madrid_ribbon(bars):
    """Devuelve {"ma05":[{time,value,color}], ...} para las 18 EMAs + su ancho."""
    closes = [b[4] for b in bars]
    ref = ce.ema_series(closes, 100)
    out = {}
    for L in MMA_LENS:
        e = ce.ema_series(closes, L)
        key = f"ma{L:02d}"
        pts = []
        for i in range(len(bars)):
            if e[i] is None:
                continue
            col = _mma_color(e[i], e[i - 1] if i > 0 else None, ref[i])
            pts.append({"time": bars[i][0], "value": round(e[i], 2), "color": col or MMA_GRAY})
        out[key] = pts
    return out


def compute_indicators(bars):
    """Arrays alineados a `bars` (mismo índice). None donde no hay warmup.
    Usa EXACTAMENTE la matemática de confluence_engine (BB %B, SMA, EMA/MACD, VWAP)."""
    n = len(bars)
    closes = [b[4] for b in bars]
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]
    vols = [b[5] for b in bars]
    opens = [b[1] for b in bars]

    sma20 = [ce.sma(closes, 20, i) for i in range(n)]
    sma40 = [ce.sma(closes, 40, i) for i in range(n)]
    sma100 = [ce.sma(closes, 100, i) for i in range(n)]
    sma200 = [ce.sma(closes, 200, i) for i in range(n)]

    bbUpper = [None] * n
    bbLower = [None] * n
    bbMid = [None] * n
    for i in range(n):
        m = sma20[i]
        if m is None:
            continue
        sd = ce.stdev(closes, 20, i, m)   # población ÷N (igual que el engine)
        bbMid[i] = m
        if sd and sd > 0:
            bbUpper[i] = m + 2 * sd
            bbLower[i] = m - 2 * sd

    # MACD(12,26,9): mismas EMAs y trato de None->0.0 para la señal que el engine
    e12 = ce.ema_series(closes, 12)
    e26 = ce.ema_series(closes, 26)
    macd = [(e12[i] - e26[i]) if (e12[i] is not None and e26[i] is not None) else None
            for i in range(n)]
    signal = ce.ema_series([m if m is not None else 0.0 for m in macd], 9)
    hist = [(macd[i] - signal[i]) if (macd[i] is not None and signal[i] is not None) else None
            for i in range(n)]
    # oculta la señal/hist durante el warmup del MACD (donde macd aún es None)
    for i in range(n):
        if macd[i] is None:
            signal[i] = None
            hist[i] = None

    # VWAP diario (reset por día local) — idéntico a votes_for_series
    vwap = [None] * n
    cumPV = 0.0
    cumV = 0.0
    cur_day = None
    for i in range(n):
        day = time.strftime("%Y-%m-%d", time.localtime(bars[i][0]))
        if day != cur_day:
            cur_day = day
            cumPV = 0.0
            cumV = 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cumPV += tp * vols[i]
        cumV += vols[i]
        vwap[i] = cumPV / cumV if cumV > 0 else None

    volume = [{"i": i, "v": vols[i], "up": closes[i] >= opens[i]} for i in range(n)]

    # combo_tl: Supertrend (ATR 10, mult 3.0) — dos ramas alcista/bajista
    stUp, stDn, stMarkers = supertrend(bars, 10, 3.0)

    return {
        "bbUpper": bbUpper, "bbLower": bbLower, "bbMid": bbMid,
        "sma20": sma20, "sma40": sma40, "sma100": sma100, "sma200": sma200,
        "vwap": vwap, "macd": macd, "signal": signal, "hist": hist, "volume": volume,
        "stUp": stUp, "stDn": stDn, "stMarkers": stMarkers,
    }


# --------- serialización a puntos lightweight-charts (time = epoch seg) -------
UP_COL = "rgba(38,166,154,0.55)"
DN_COL = "rgba(239,83,80,0.55)"


def _line_points(bars, arr):
    """[{time,value}] saltando None (setData exige tiempos únicos, ordenados, sin nulos)."""
    return [{"time": bars[i][0], "value": round(arr[i], 4)}
            for i in range(len(bars)) if arr[i] is not None]


def _break_points(bars, arr):
    """Como _line_points pero conserva TODOS los tiempos: donde arr[i] es None emite
    un punto whitespace {time} (sin value). Así lightweight-charts ROMPE la línea en
    esos huecos (estilo plot.style_linebr de Pine) en vez de unir a través del hueco —
    lo usa el Supertrend (rama alcista/bajista) para no cruzar el lado contrario."""
    out = []
    for i in range(len(bars)):
        if arr[i] is not None:
            out.append({"time": bars[i][0], "value": round(arr[i], 4)})
        else:
            out.append({"time": bars[i][0]})
    return out


def _hist_points(bars, arr):
    return [{"time": bars[i][0], "value": round(arr[i], 6),
             "color": "#26a69a" if arr[i] is not None and arr[i] >= 0 else "#ef5350"}
            for i in range(len(bars)) if arr[i] is not None]


def _vol_points(bars, volarr):
    out = []
    for v in volarr:
        i = v["i"]
        out.append({"time": bars[i][0], "value": v["v"],
                    "color": UP_COL if v["up"] else DN_COL})
    return out


def _candle_points(bars):
    return [{"time": b[0], "open": b[1], "high": b[2], "low": b[3], "close": b[4]}
            for b in bars]


def indicators_series(bars, ind):
    """Convierte los arrays a series de puntos listas para setData en el cliente."""
    return {
        "bbUpper": _line_points(bars, ind["bbUpper"]),
        "bbLower": _line_points(bars, ind["bbLower"]),
        "bbMid": _line_points(bars, ind["bbMid"]),
        "sma20": _line_points(bars, ind["sma20"]),
        "sma40": _line_points(bars, ind["sma40"]),
        "sma100": _line_points(bars, ind["sma100"]),
        "sma200": _line_points(bars, ind["sma200"]),
        "vwap": _line_points(bars, ind["vwap"]),
        "macd": _line_points(bars, ind["macd"]),
        "signal": _line_points(bars, ind["signal"]),
        "hist": _hist_points(bars, ind["hist"]),
        "volume": _vol_points(bars, ind["volume"]),
        # combo_tl: Supertrend (2 ramas con huecos None = break) + marcadores + trendlines
        "stUp": _break_points(bars, ind["stUp"]),
        "stDn": _break_points(bars, ind["stDn"]),
        "stMarkers": ind["stMarkers"],
        "trendlines": compute_trendlines(bars),
        "madrid": madrid_ribbon(bars),   # ribbon Madrid: 18 EMAs con color por punto
    }


# ======================= PULSO RSI/BB (panel arriba-izquierda) ===============
# Se calcula AQUI (no en JS) por tres razones: (1) el front solo tiene las velas del tf
# ACTIVO, y el panel necesita 1m y 15m a la vez; (2) fuente unica de verdad — mismas
# ce.sma/ce.stdev que dibujan las bandas del chart y que usa bollinger_alarm, y el mismo
# ce.rsi_series del confluence_engine: reimplementarlo en JS es la deriva que ya costo
# un 18,5% de dilucion en la flota; (3) fail-loud con el motivo exacto (n insuficiente),
# imposible de fabricar en el cliente.
PULSE_TAIL_1M = 1400        # ~23h de 1m -> ~93 velas de 15m: warmup sobrado para RSI(14)
_pulse_bars_cache = {}      # sym -> (monotonic, bars)


def pulse_bars_1m(sym, max_age_s=1.0):
    """1m crudas del fichero del bar_bridge (LA misma fuente que bollinger_alarm.py).
    Cache corta: bar_frame se emite cada pocos segundos y el fichero no cambia mas rapido."""
    key = sym.lower()
    now = time.monotonic()
    hit = _pulse_bars_cache.get(key)
    if hit and now - hit[0] < max_age_s:
        return hit[1]
    bars = load_sandbox_bars(sym, PULSE_TAIL_1M) if MOCK_DIR else load_ibkr_bars(sym, PULSE_TAIL_1M)
    _pulse_bars_cache[key] = (now, bars)
    return bars


def bb_state(closes):
    """BB(20,2) sobre el ULTIMO cierre -> %B y ancho relativo. None si no hay 20 cierres
    o la desviacion es cero (banda degenerada): jamas un 0.5 plausible."""
    i = len(closes) - 1
    m = ce.sma(closes, 20, i)
    if m is None or m <= 0:
        return None
    sd = ce.stdev(closes, 20, i, m)
    if not sd or sd <= 0:
        return None
    up, lo = m + 2 * sd, m - 2 * sd
    return {"pctb": (closes[i] - lo) / (up - lo), "bw": (up - lo) / m,
            "upper": up, "lower": lo, "mid": m}


def pulse_row(tf, bars, active=False):
    """Fila del panel para un timeframe. RSI y %B se calculan por SEPARADO con su propio
    warmup: sin barras suficientes queda None y `why` dice exactamente cuantas hay."""
    n = len(bars)
    row = {"tf": tf, "n": n, "active": active, "rsi": None, "pctb": None,
           "bw": None, "ts": bars[-1][0] if bars else None, "why": None}
    faltas = []
    closes = [b[4] for b in bars]
    if n < 20:
        faltas.append(f"BB(20) exige 20, hay {n}")
    else:
        bb = bb_state(closes)
        if bb is None:
            faltas.append("banda degenerada (sd=0)")
        else:
            row["pctb"] = round(bb["pctb"], 4)
            row["bw"] = round(bb["bw"] * 100, 3)
            row["mid"] = round(bb["mid"], 4)
            row["upper"] = round(bb["upper"], 4)
            row["lower"] = round(bb["lower"], 4)
    if n < 15:   # ce.rsi_series siembra en el indice 14: hacen falta 15 cierres
        faltas.append(f"RSI(14) exige 15, hay {n}")
    else:
        r = ce.rsi_series(closes, 14)[-1]
        if r is None:
            faltas.append("RSI sin warmup")
        else:
            row["rsi"] = round(r, 2)
    if faltas:
        row["why"] = " · ".join(faltas)
    return row


def pulse_verdict(rows):
    """BAJISTA / ALCISTA / NEUTRO segun la doctrina Bollinger de la casa (CLAUDE.md regla 1):
    banda reventada en >=2 timeframes = BAND-WALK (continuacion, no fadear); reventada en UNO
    solo = ELASTICO (reversion corta hacia la media, o sea sesgo CONTRARIO al lado roto).
    Sin ninguna fila con %B: SIN DATOS — no existe el "neutro por defecto"."""
    usable = [r for r in rows if r.get("pctb") is not None]
    if not usable:
        why = "; ".join(f"{r['tf']}: {r['why']}" for r in rows if r.get("why")) or "sin barras"
        return {"label": "SIN DATOS", "kind": "nodata", "why": why, "tfs": []}
    ups = [r["tf"] for r in usable if r["pctb"] > 1.0]
    dns = [r["tf"] for r in usable if r["pctb"] < 0.0]
    if len(ups) >= 2:
        return {"label": "ALCISTA", "kind": "bandwalk", "tfs": ups,
                "why": f"band-walk arriba en {'+'.join(ups)} — continuacion, NO fadear"}
    if len(dns) >= 2:
        return {"label": "BAJISTA", "kind": "bandwalk", "tfs": dns,
                "why": f"band-walk abajo en {'+'.join(dns)} — continuacion, NO fadear"}
    if len(ups) == 1:
        return {"label": "BAJISTA", "kind": "elastico", "tfs": ups,
                "why": f"banda superior reventada solo en {ups[0]} — elastico: reversion a la media"}
    if len(dns) == 1:
        return {"label": "ALCISTA", "kind": "elastico", "tfs": dns,
                "why": f"banda inferior reventada solo en {dns[0]} — elastico: rebote a la media"}
    return {"label": "NEUTRO", "kind": "neutro", "tfs": [],
            "why": "precio dentro de las bandas en todos los marcos"}


def compute_pulse(sym, view_bars, tf):
    """{rows, verdict, sym, tf, ts}. El tf ACTIVO sale de las MISMAS velas que dibuja el
    chart (para no contradecir las bandas en pantalla); 1m/15m salen del fichero 1m."""
    tf = tf or "1m"
    base = pulse_bars_1m(sym)
    rows = []
    for label in ("1m", "15m"):
        if tf == label:
            rows.append(pulse_row(label, view_bars, active=True))
        elif not base:
            rows.append({"tf": label, "n": 0, "active": False, "rsi": None, "pctb": None,
                         "bw": None, "ts": None, "why": f"sin data/bars_{sym.lower()}_ibkr.txt"})
        else:
            rows.append(pulse_row(label, base if label == "1m" else agg_epoch(base, 900)))
    if tf not in ("1m", "15m"):
        rows.append(pulse_row(tf, view_bars, active=True))
    return {"sym": sym.upper(), "tf": tf, "rows": rows, "verdict": pulse_verdict(rows),
            "ts": max([r["ts"] for r in rows if r["ts"]], default=None)}


def _marker_for(source, up):
    """Mapea una señal a un marcador de chart. TODAS las fuentes visibles para que
    Yunior debuguee visualmente (orden 2026-07-23). ABAJO/ARRIBA da la posición."""
    ab = "ARRIBA" in up or "CALLS" in up or "SELL" in up or " PUT" in up
    if source == "whale":
        return {"position": "belowBar", "color": "#26a69a", "shape": "circle", "text": "🐋P"} if "PUTS" in up \
            else {"position": "aboveBar", "color": "#ef5350", "shape": "circle", "text": "🐋C"}
    if source == "flow":   # 🚀 spike de flujo
        return {"position": ("aboveBar" if "CALLS" in up else "belowBar"),
                "color": "#ab47bc", "shape": "arrowDown" if "CALLS" in up else "arrowUp", "text": "🚀"}
    if source == "dip":    # 🩸 dip real
        return {"position": "belowBar", "color": "#42a5f5", "shape": "arrowUp", "text": "🩸"}
    if source == "bollinger":  # 🎈 rebote/band-walk BB
        return {"position": ("aboveBar" if "ARRIBA" in up else "belowBar"),
                "color": "#ffa726", "shape": "circle", "text": "🎈"}
    if source == "cusum":  # 🌋 terremoto/CUSUM
        return {"position": ("aboveBar" if ab else "belowBar"), "color": "#8d6e63", "shape": "square", "text": "🌋"}
    if source == "price_alarm":  # ⏰ alarma de precio (manual o sirena)
        return {"position": ("aboveBar" if ab else "belowBar"), "color": "#f4c430", "shape": "square", "text": "⏰"}
    if source == "structural":   # 🧲 señal estructural (imán/flip)
        return {"position": ("aboveBar" if ab else "belowBar"), "color": "#f4c430", "shape": "circle", "text": "🧲"}
    return {"position": ("aboveBar" if ab else "belowBar"), "color": "#78909c", "shape": "circle", "text": "•"}


def load_signal_markers(sym, bars):
    """TODAS nuestras señales/notificaciones/alarmas del día, desde la BD (trades.db
    tabla `signals`, que las clasifica por fuente), filtradas al símbolo y al rango de
    barras. Yunior lo usa para debug visual + feedback EOD. Feature única nuestra."""
    if not bars or not sym:
        return []
    day = time.strftime("%Y-%m-%d", time.localtime(bars[-1][0]))
    su = sym.upper()
    t0, t1 = bars[0][0], bars[-1][0] + 3600
    base = time.localtime(bars[-1][0])
    try:
        import sqlite3
        c = sqlite3.connect(f"file:{os.path.join(REPO, 'trades.db')}?mode=ro", uri=True, timeout=3)
        c.execute("PRAGMA busy_timeout=2000")
        rows = c.execute(
            "SELECT ts_txt, kind, source, priority, msg FROM signals "
            "WHERE date=? AND (symbol=? OR upper(msg) LIKE ?)",
            (day, su, f"%{su}%")).fetchall()
        c.close()
    except Exception:
        rows = []
    out, seen = [], set()
    for ts_txt, kind, source, prio, msg in rows:
        try:
            hh, mm, ss = (int(x) for x in (ts_txt or "").split(":"))
        except Exception:
            continue
        ep = int(time.mktime((base.tm_year, base.tm_mon, base.tm_mday, hh, mm, ss, 0, 0, -1)))
        if ep < t0 or ep > t1:
            continue
        key = (ep, source, (kind or "")[:12])
        if key in seen:
            continue
        seen.add(key)
        up = ((kind or "") + " " + (msg or "")).upper()
        m = _marker_for(source or "", up)
        m["time"] = ep
        m["tip"] = (kind or "").strip()   # tooltip para el debug de Yunior
        out.append(m)
    out.sort(key=lambda x: x["time"])
    return out


def load_engine_ops(sym, bars):
    """Operaciones de NUESTROS engines desde trades.db (bot_trades + etf_operations),
    filtradas al símbolo y al día. Hoy están en modo señal/paper (no operan), pero el
    chart ya las muestra: cuando el mejor algoritmo empiece a operar solo, se verá aquí.
    Marcadores ⚙ BUY (verde) / SELL (rojo), tooltip 'bot·modo'. SEÑAL-SOLAMENTE."""
    if not bars or not sym:
        return []
    day = time.strftime("%Y-%m-%d", time.localtime(bars[-1][0]))
    su = sym.upper()
    t0, t1 = bars[0][0], bars[-1][0] + 3600
    base = time.localtime(bars[-1][0])
    rows = []
    try:
        import sqlite3
        c = sqlite3.connect(f"file:{os.path.join(REPO, 'trades.db')}?mode=ro", uri=True, timeout=3)
        c.execute("PRAGMA busy_timeout=2000")
        # bot_trades: ts, bot, mode, symbol, side, qty, price
        for ts, bot, mode, side, qty, price in c.execute(
                "SELECT ts,bot,mode,side,qty,price FROM bot_trades WHERE symbol=? AND ts LIKE ?",
                (su, f"{day}%")):
            rows.append((ts, bot, mode, side, price))
        # etf_operations: ts, event, etf, base, side, px  (base = subyacente)
        for ts, event, etf, bside, side, px in c.execute(
                "SELECT ts,event,etf,base,side,px FROM etf_operations WHERE (base=? OR etf=?) AND ts LIKE ?",
                (su, su, f"{day}%")):
            rows.append((ts, etf or "etf", event, side, px))
        c.close()
    except Exception:
        return []
    out = []
    for ts, bot, mode, side, price in rows:
        m = re.match(r"(\d{2}):(\d{2}):(\d{2})", (ts or "")[11:19])
        if not m:
            continue
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ep = int(time.mktime((base.tm_year, base.tm_mon, base.tm_mday, hh, mm, ss, 0, 0, -1)))
        if ep < t0 or ep > t1:
            continue
        buy = "BUY" in (side or "").upper()
        out.append({"time": ep, "position": "belowBar" if buy else "aboveBar",
                    "color": "#00e676" if buy else "#ff1744",
                    "shape": "arrowUp" if buy else "arrowDown",
                    "text": f"⚙{'▲' if buy else '▼'}",
                    "tip": f"{bot}·{mode}·{price}"})
    out.sort(key=lambda x: x["time"])
    return out


# ---- alarmas manuales estilo TradingView (repunto 2026-07-26, ruta derivada) ----
def _alarm_path():
    d = os.environ.get("IBT_DESKTOP_HOY", os.path.expanduser("~/Desktop/ib-trader/hoy"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "price-alerts.txt")


def alarm_list(sym):
    """Alarmas ACTIVAS (no disparadas/caducadas) del símbolo -> [{price, dir, exp}]."""
    su = sym.upper()
    out = []
    try:
        for ln in open(_alarm_path(), errors="ignore"):
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith("[DISPARADA") or s.startswith("[CADUCADA"):
                continue
            p = s.split("#")[0].split()
            if len(p) >= 3 and p[0].upper() == su:
                try:
                    m = re.search(r"exp=(\d{4}-\d{2}-\d{2})", s)
                    out.append({"price": float(p[1]), "dir": p[2].lower(),
                                "exp": m.group(1) if m else None})
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _alarm_default_exp(bizdays=5):
    """+N días hábiles — TTL por defecto: alarmas de hace 1-2 semanas cantaban con tesis muertas."""
    t, n = time.time(), 0
    while n < bizdays:
        t += 86400
        if time.localtime(t).tm_wday < 5:
            n += 1
    return time.strftime("%Y-%m-%d", time.localtime(t))


def alarm_add(sym, price, direction, exp=None):
    """Añade una alarma manual (price_alarm la relee cada 1s; entiende exp=YYYY-MM-DD y
    la marca [CADUCADA] al vencer). SEÑAL-SOLAMENTE."""
    if not (isinstance(exp, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", exp)):
        exp = _alarm_default_exp()
    line = (f"{sym.lower()} {price:g} {('up' if direction=='up' else 'down')}        "
            f"# manual chart {time.strftime('%H:%M')} exp={exp}\n")
    try:
        with open(_alarm_path(), "a") as f:
            f.write(line)
        return True
    except Exception:
        return False


def alarm_remove(sym, price):
    """Elimina (comenta) la alarma manual del símbolo a ese precio."""
    su = sym.upper()
    path = _alarm_path()
    try:
        lines = open(path, errors="ignore").readlines()
        out = []
        for ln in lines:
            p = ln.strip().split("#")[0].split()
            if (len(p) >= 3 and p[0].upper() == su and price is not None
                    and abs(float(p[1]) - float(price)) < 1e-6 and not ln.lstrip().startswith("[")):
                continue   # la quitamos
            out.append(ln)
        with open(path, "w") as f:
            f.writelines(out)
        return True
    except Exception:
        return False


# ---- watchlist (fleet fija + añadidos del usuario, buscable/expandible) ----------
def load_fleet():
    """30 tickers desde data/fleet.txt (fuente única). Una línea, separados por espacios."""
    p = os.path.join(REPO, "data", "fleet.txt")
    try:
        return [s.upper() for s in open(p).read().split() if s.strip()]
    except Exception:
        return []


def _watchlist_user_path():
    return os.path.join(REPO, "data", "watchlist_user.txt")


def load_user_watchlist():
    """Símbolos añadidos por el usuario (data/watchlist_user.txt, uno por línea/espacio)."""
    try:
        return [s.upper() for s in open(_watchlist_user_path()).read().split() if s.strip()]
    except Exception:
        return []


def watchlist_quote(sym):
    """Último precio, %cambio del día y volumen del día (estilo TradingView) desde los bars
    locales (data/bars_<sym>_ibkr.txt, o data/bars_<stem>.txt para KOREA_SYMS: epoch o h l c
    v). Degrada a None. SEÑAL-SOLAMENTE."""
    fname = f"bars_{sym.lower()}.txt" if sym.upper() in KOREA_SYMS() else f"bars_{sym.lower()}_ibkr.txt"
    p = os.path.join(REPO, "data", fname)
    try:
        rows = [ln.split() for ln in open(p) if ln.strip()]
        c = [(int(r[0]), float(r[4]), float(r[5])) for r in rows if len(r) >= 6]
    except Exception:
        c = []
    if not c:
        # Fuera de la flota no hay fichero 1m (lo escribe ibkr_bar_bridge solo para fleet.txt):
        # la fila salia en blanco aunque el chart SI tuviera el simbolo vivo (TQQQ/MSFU/MUU,
        # medido 2026-07-30). Si hay un State abierto, sus barras son la misma verdad.
        stt = STATES.get(sym.lower())
        c = [(int(b[0]), float(b[4]), float(b[5]) if len(b) > 5 else 0.0)
             for b in (stt.bars if stt else [])]
        if not c:
            return {"last": None, "chg": None, "vol": None}
    last_day = time.localtime(c[-1][0]).tm_yday
    today = [x for x in c if time.localtime(x[0]).tm_yday == last_day]
    prev = [x for x in c if time.localtime(x[0]).tm_yday != last_day]
    last = today[-1][1]
    vol = sum(x[2] for x in today)
    prev_close = prev[-1][1] if prev else today[0][1]
    chg = round((last - prev_close) / prev_close * 100, 2) if prev_close else None
    # age_s: edad de la ULTIMA barra — la UI atenua filas viejas (jamas viejo como actual)
    return {"last": round(last, 2), "chg": chg, "vol": int(vol),
            "age_s": int(time.time() - c[-1][0])}


async def qualify_watchlist_sym(st, s):
    """(ok, motivo) de añadir S a la watchlist. qualifyContractsAsync NO lanza con un simbolo
    inexistente: devuelve lista VACIA y solo loguea "Unknown contract" -> el codigo viejo
    aceptaba cualquier basura (ZZZZZ, ZQXWV9 quedaron en watchlist_user.txt). Se mira el
    RESULTADO. Sin conexion no se adivina: se rechaza diciendolo (fail-loud)."""
    if st.mock:
        return True, "mock"
    if s in KOREA_SYMS():
        return True, "KRX (contrato por conId, no SMART/USD)"
    if st._ib is None:
        return False, "sin conexión a TWS: no puedo verificar que el símbolo exista"
    try:
        from ib_async import Stock
        res = await asyncio.wait_for(
            st._ib.qualifyContractsAsync(Stock(s, "SMART", "USD")), 15)
    except asyncio.TimeoutError:
        return False, "TWS no respondió en 15s"
    except Exception as e:
        return False, f"error cualificando ({e})"
    if not res or not getattr(res[0], "conId", 0):
        return False, f"IBKR no conoce «{s}» como acción/ETF US (SMART/USD)"
    return True, f"conId {res[0].conId}"


def load_watchlist_stats():
    """Feed OPCIONAL de otro agente: data/watchlist_stats.json con volumen diario + %cambio
    (más fino que nuestro cálculo desde bars). Degradación LIMPIA: si falta -> {} y usamos los
    quotes calculados localmente. Acepta {SYM:{vol,chg,last}} o wrappers {stats|quotes:...}."""
    p = os.path.join(REPO, "data", "watchlist_stats.json")
    try:
        d = json.load(open(p))
    except Exception:
        return {}
    if isinstance(d, dict) and ("stats" in d or "quotes" in d):
        d = d.get("stats") or d.get("quotes") or {}
    return d if isinstance(d, dict) else {}


def load_perp_stocks():
    """Perpetuos Bybit 24/7 de data/perp_stocks.json (scripts/perp_stock_fetch.py, fuente
    única). feed_age_s del fichero queda CONGELADO al valor de escritura (siempre 0.0) ->
    se recalcula aquí desde feed_ts, nunca se confía en el campo guardado. Degrada a {}.
    STX/GLD nunca aparecen (excluidos aguas arriba: colisión STXUSDT=Stacks / sin perp)."""
    p = os.path.join(REPO, "data", "perp_stocks.json")
    try:
        d = json.load(open(p))
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    now = time.time()
    for s, v in d.items():
        if isinstance(v, dict) and isinstance(v.get("feed_ts"), (int, float)):
            v["feed_age_s"] = round(now - v["feed_ts"], 1)
    return d


def watchlist_payload():
    fleet = load_fleet(); user = load_user_watchlist()
    quotes = {s: watchlist_quote(s) for s in dict.fromkeys(fleet + user)}
    korea = sorted(KOREA_SYMS())
    quotes.update({s: watchlist_quote(s) for s in korea})
    stats = load_watchlist_stats()   # feed opcional -> sobreescribe vol/chg/last si viene
    for s, q in quotes.items():
        st = stats.get(s) or stats.get(s.upper()) or stats.get(s.lower())
        if not isinstance(st, dict):
            continue
        # STALE JAMAS PISA FRESCO (cazado 2026-07-28: stats del 24-jul pintaba MU 920.95
        # "edad 93s" con MU real en 832): sin ts o ts viejo -> no sobreescribe precio/chg
        st_ts = st.get("ts")
        st_fresh = isinstance(st_ts, (int, float)) and time.time() - st_ts < 600
        # el feed usa {vol, pct|chg, price|last}; sólo sobreescribe cuando trae valor real
        for dst, keys in (("vol", ("vol",)), ("chg", ("chg", "pct")), ("last", ("last", "price"))):
            if dst in ("last", "chg") and not st_fresh:
                continue
            for k in keys:
                v = st.get(k)
                if v is not None:
                    q[dst] = v
                    break
    return {"type": "watchlist", "fleet": fleet, "user": user, "korea": korea,
            "quotes": quotes, "perp": load_perp_stocks()}


async def broadcast_watchlist(state):
    if not state.clients:
        return
    pl = watchlist_payload()
    for ws in list(state.clients):
        try:
            await ws.send_json(pl)
        except Exception:
            state.clients.discard(ws)


def _watchlist_file_add(sym):
    """Añade sym al archivo del usuario (dedup contra fleet + user). SEÑAL-SOLAMENTE."""
    sym = (sym or "").strip().upper()
    if not sym:
        return False
    if sym in load_fleet() or sym in load_user_watchlist():
        return True
    user = load_user_watchlist() + [sym]
    try:
        with open(_watchlist_user_path(), "w") as f:
            f.write("\n".join(user) + "\n")
        return True
    except Exception:
        return False


def _watchlist_file_del(sym):
    """Quita sym del archivo del usuario (no toca la fleet fija)."""
    sym = (sym or "").strip().upper()
    user = [s for s in load_user_watchlist() if s != sym]
    try:
        with open(_watchlist_user_path(), "w") as f:
            f.write(("\n".join(user) + "\n") if user else "")
        return True
    except Exception:
        return False


# ---- ZONAS DE EJECUCIÓN 0DTE (como alarmas pero TIPADAS buy/sell call/put) --------
# Persistidas en data/exec_zones_<sym>.json. Al cruzar el spot una zona, se emite la
# FICHA (order_ticket.build) al chart + se registra en trading-signals. NUNCA se envía
# orden a TWS: el software PREPARA, el humano da el clic en IBKR. SEÑAL-SOLAMENTE.
def zones_path(sym):
    return os.path.join(REPO, "data", f"exec_zones_{sym.lower()}.json")


def zones_load(sym):
    p = zones_path(sym)
    if os.path.exists(p):
        try:
            d = json.load(open(p))
            return d if isinstance(d, list) else []
        except Exception:
            return []
    return []


def zones_save(sym, zones):
    # bug cazado en caza de bugs 2026-07-28: escritura directa sin tmp+rename — order_engine.cpp
    # relee este fichero CADA CICLO en caliente; una escritura a mitad podia entregarle un JSON
    # con kind/side ausentes, y order_engine defaulteaba silenciosamente a "buy"/"call".
    try:
        tmp = zones_path(sym) + f".{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(zones, f)
        os.replace(tmp, zones_path(sym))
    except Exception as e:
        print(f"[zone] save falló ({e})")


# VIX del mercado ENTERO -> un solo fichero compartido que compass.cpp lee. Cualquier bridge
# con VIX lo escribe (last-writer-wins es correcto: el VIX no es por símbolo). Atómico tmp+replace.
_VIX_JSON = os.path.join(REPO, "data", "vix.json")
_vix_last_written = None


def persist_vix(vix, vix_live):
    global _vix_last_written
    if vix is None:
        return
    key = (vix, bool(vix_live))
    if key == _vix_last_written:
        return
    tmp = _VIX_JSON + f".{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as f:
            # vix_live como 0/1: compass.cpp lo lee con jnum (from_chars), un boolean no parsea
            json.dump({"vix": vix, "vix_live": 1 if vix_live else 0, "ts": int(time.time())}, f)
        os.replace(tmp, _VIX_JSON)
        _vix_last_written = key
    except Exception as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        print(f"[vix] persist falló ({e})")


_WHALE_PRIORITY_F = os.path.join(REPO, "data", "whale_priority.txt")
_WHALE_FILTER_F = os.path.join(REPO, "data", "whale_alert_filter.txt")


def _atomic_write(path, text):
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[whale_cfg] escritura fallo ({path}: {e})")


def whale_cfg_status():
    """Panel de ballenas (Yunior 2026-07-28 'ajustar desde el macos o chrome app'): lee
    data/whale_priority.txt + data/whale_alert_filter.txt tal como los lee
    opt_whale_watch.py — mismo patron, ausente/vacio -> lista/dict vacio, nunca inventado."""
    try:
        priority = open(_WHALE_PRIORITY_F).read().split()
    except Exception:
        priority = []
    filters = {}
    try:
        for line in open(_WHALE_FILTER_F):
            parts = line.split()
            if len(parts) >= 2 and parts[1].upper() in ("CALLS", "PUTS", "BOTH"):
                filters[parts[0].upper()] = parts[1].upper()
    except Exception:
        pass
    return {"type": "whale_cfg", "priority": priority, "filters": filters, "priority_max": 5}


_UW_TAPE_F = os.path.join(REPO, "data", "uw_flow_tape.json")


def uw_tape_frame():
    """(frame, mtime) de data/uw_flow_tape.json (lo escribe uw_flow_tape.py), o (None, None).
    El contenido va TAL CUAL (rows o error): el widget muestra el motivo, aqui no se maquilla."""
    try:
        mt = os.path.getmtime(_UW_TAPE_F)
        with open(_UW_TAPE_F) as f:
            d = json.load(f)
    except Exception:
        return None, None
    if not isinstance(d, dict):
        return None, None
    d["type"] = "uw_tape"
    return d, mt


async def uw_tape_loop():
    """Empuja la cinta UW a TODOS los clientes cada 30 s si el fichero cambio (mtime)."""
    last_mt = None
    while True:
        await asyncio.sleep(30)
        try:
            frame, mt = uw_tape_frame()
            if frame is None or mt == last_mt:
                continue
            last_mt = mt
            for st in list(STATES.values()):
                for ws in list(st.clients):
                    try:
                        await ws.send_json(frame)
                    except Exception:
                        st.clients.discard(ws)
        except Exception as e:
            print(f"[uw_tape] {e}")


_VPVR_F = os.path.join(REPO, "data", "vpvr.json")
LIQ_LIVE_CHAIN_MAX_AGE_S = 15 * 60


def liq_frame(sym):
    """(frame, mtimes) liquidez VPVR (POCv/VAH/VAL) + KDE — CONTEXTO, no gatillo
    (docs/LEVEL-REACT-2026-07-25: 37,3% vs 36,1% azar). Solo LECTURA; campos ausentes -> null."""
    s = sym.upper()
    poc = vah = val = None
    kde, mts = [], []
    try:
        mts.append(os.path.getmtime(_VPVR_F))
        with open(_VPVR_F) as f:
            v = (json.load(f) or {}).get(s) or {}
        poc, vah, val = v.get("poc_volume"), v.get("vah"), v.get("val")
    except Exception:
        pass
    p = os.path.join(REPO, "data", f"levels_auto_{s}.json")
    try:
        mts.append(os.path.getmtime(p))
        with open(p) as f:
            tfs = (json.load(f) or {}).get("tfs") or {}
        seen = set()
        for tf in tfs.values():
            for x in (tf.get("kde") or []):
                r = round(float(x), 2)
                if r not in seen:
                    seen.add(r)
                    kde.append(r)
    except Exception:
        pass
    return ({"type": "liq_levels", "sym": s, "poc_volume": poc, "vah": vah,
             "val": val, "kde": sorted(kde)}, tuple(mts) or None)


def liq_map_frame(sym):
    """(frame, fingerprint) mapa liquidez estilo Bookmap con datos REALES: cubo de fotos
    5-min de hoy (heat=vol opciones C+P por strike), whale prints de acciones, sweeps UW
    y bandas VPVR. Nada inventado; sin dato -> listas vacías con 'why'."""
    s = sym.upper()
    day = datetime.now().strftime("%Y-%m-%d")
    hdir = os.path.join(REPO, "data", "history", day)
    cols, per_col = [], []
    spot = None
    # TWS used to archive opt_chain_<sym>_HHMM. With market_source=intrinio, the real
    # snapshots are poly_chain_<sym>_HHMM and the rotating live cache is opt_chain_<sym>.txt.
    # Discover all three, dedupe by minute, and prefer live > TWS > Polygon archive.
    candidates = {}
    try:
        for fn in os.listdir(hdir):
            m = re.fullmatch(rf"(opt_chain|poly_chain)_{re.escape(s.lower())}_(\d{{4}})\.txt", fn)
            if not m:
                continue
            source, hhmm = m.group(1), m.group(2)
            rank = 2 if source == "opt_chain" else 1
            path = os.path.join(hdir, fn)
            if hhmm not in candidates or rank > candidates[hhmm][0]:
                candidates[hhmm] = (rank, path, source)
    except Exception:
        pass
    live_path = os.path.join(REPO, "data", f"opt_chain_{s.lower()}.txt")
    try:
        mt = os.path.getmtime(live_path)
        age = time.time() - mt
        if datetime.fromtimestamp(mt).strftime("%Y-%m-%d") == day and age <= LIQ_LIVE_CHAIN_MAX_AGE_S:
            hhmm = datetime.fromtimestamp(mt).strftime("%H%M")
            candidates[hhmm] = (3, live_path, "live_cache")
    except Exception:
        pass
    snaps = [(hhmm, *candidates[hhmm][1:]) for hhmm in sorted(candidates)]
    source_meta = []
    for hhmm, path, source in snaps:
        vols = {}
        try:
            with open(path) as f:
                for ln in f:
                    if ln.startswith("#"):
                        if " spot " in ln:
                            try:
                                spot = float(ln.split(" spot ")[1].split()[0])
                            except Exception:
                                pass
                        continue
                    p = ln.split()
                    if len(p) < 6:
                        continue
                    try:
                        k, v = float(p[0]), int(float(p[5]))
                    except Exception:
                        continue
                    vols[k] = vols.get(k, 0) + max(0, v)
        except Exception:
            continue
        cols.append(hhmm)
        per_col.append(vols)
        try:
            source_meta.append([hhmm, source, round(time.time() - os.path.getmtime(path), 1)])
        except Exception:
            source_meta.append([hhmm, source, None])
    strikes = []
    if spot:
        lo, hi = spot * 0.94, spot * 1.06
        strikes = sorted({k for vols in per_col for k in vols if lo <= k <= hi})
    heat = [[vols.get(k, 0) for vols in per_col] for k in strikes]
    whales = []
    try:
        with open(os.path.join(REPO, "data", f"whale_{s.lower()}.txt")) as f:
            for ln in f:
                p = ln.split()
                if len(p) >= 4:
                    try:
                        whales.append([int(float(p[0])), float(p[1]), int(float(p[2])), int(p[3])])
                    except Exception:
                        continue
    except Exception:
        pass
    if len(whales) > 600:   # tope de payload: se quedan los prints más gordos
        whales = sorted(whales, key=lambda w: -w[2])[:600]
        whales.sort(key=lambda w: w[0])
    sweeps = []
    try:
        with open(_UW_TAPE_F) as f:
            for r in (json.load(f).get("rows") or []):
                if r.get("sym") == s and r.get("strike") is not None:
                    sweeps.append([round(float(r["ts"])), float(r["strike"]),
                                   int(r.get("premium") or 0), 1 if r.get("type") == "C" else -1,
                                   1 if r.get("sweep") else 0])
    except Exception:
        pass
    vah = val = None
    hvn = []
    try:
        with open(_VPVR_F) as f:
            v = (json.load(f) or {}).get(s) or {}
        vah, val, hvn = v.get("vah"), v.get("val"), v.get("hvn") or []
    except Exception:
        pass
    why = None
    if not cols:
        why = f"sin fotos de cadena hoy en data/history/{day} ni cache vivo fresco"
    elif spot is None:
        why = "fotos de cadena sin spot parseable"
    elif not strikes:
        why = "fotos sin strikes dentro de ±6% del spot"
    frame = {"type": "liq_map", "sym": s, "spot": spot, "cols": cols, "strikes": strikes,
             "heat": heat, "whales": whales, "sweeps": sweeps,
             "vah": vah, "val": val, "hvn": hvn, "sources": source_meta, "why": why}
    sig = []
    for hhmm, path, source in snaps:
        try:
            sig.append((hhmm, source, os.path.getmtime(path), os.path.getsize(path)))
        except Exception:
            sig.append((hhmm, source, None, None))
    return frame, (tuple(sig), len(whales), len(sweeps))


async def liq_loop():
    """Reempuja liq_levels y liq_map por símbolo cuando su fuente cambia (mtime/huella)."""
    last, last_map = {}, {}
    while True:
        await asyncio.sleep(30)
        try:
            for st in list(STATES.values()):
                out = []
                frame, mts = liq_frame(st.sym)
                if mts is not None and last.get(st.sym) != mts:
                    last[st.sym] = mts
                    out.append(frame)
                mframe, fp = liq_map_frame(st.sym)
                if last_map.get(st.sym) != fp:
                    last_map[st.sym] = fp
                    out.append(mframe)
                for f in out:
                    for ws in list(st.clients):
                        try:
                            await ws.send_json(f)
                        except Exception:
                            st.clients.discard(ws)
        except Exception as e:
            print(f"[liq] {e}")


def chain_exps(sym):
    """Expiries del cache opt_chain (línea header '# ... exps YYYYMMDD YYYYMMDD ...').
    Degradación limpia -> []. Sólo LECTURA."""
    p = os.path.join(REPO, "data", f"opt_chain_{sym.lower()}.txt")
    try:
        with open(p) as f:
            for ln in f:
                if ln.startswith("#"):
                    if "exps " in ln:
                        return ln.split("exps ")[1].split()
                else:
                    break
    except Exception:
        pass
    return []


def chain_contract(sym, price, kind, exp=None):
    """Contrato (strike más cercano a `price`) para (kind, exp) desde el cache opt_chain
    reutilizando el parser de order_ticket. Sólo LECTURA (bid/ask/OI para previsualizar en
    el chart, estilo TradingView). Devuelve dict o None. SEÑAL-SOLAMENTE."""
    try:
        ch = order_ticket._parse_chain(sym)
    except Exception:
        ch = None
    if not ch or not ch.get("rows"):
        return None
    right = "P" if str(kind).lower().startswith("p") else "C"
    exp = exp or (ch["exps"][0] if ch.get("exps") else None)
    cand = [r for r in ch["rows"] if r["right"] == right and (exp is None or r["exp"] == exp)]
    if not cand:
        return None
    c = min(cand, key=lambda r: abs(r["strike"] - float(price)))
    return {"strike": c["strike"], "right": right, "exp": exp,
            "bid": c["bid"], "ask": c["ask"], "oi": c["oi"], "delta": c.get("delta")}


def chain_quote(sym, price, exp=None):
    """Previsualización del contrato que se USARÍA a ese precio: strike + bid/ask de CALL y
    PUT para el expiry elegido (o el 0DTE por defecto). Sólo LECTURA. SEÑAL-SOLAMENTE."""
    if price is None:
        return {"strike": None, "exp": exp, "call": None, "put": None}
    c = chain_contract(sym, price, "call", exp)
    p = chain_contract(sym, price, "put", exp)
    ref = c or p or {}
    pick = lambda o: {k: o.get(k) for k in ("bid", "ask", "oi")} if o else None
    return {"strike": ref.get("strike"), "exp": ref.get("exp") or exp,
            "call": pick(c), "put": pick(p)}


def _default_stop_px(price, side, kind):
    """Stop protectivo por defecto EN EL SUBYACENTE (~1.5%; Yunior lo arrastra en el chart).
    Alcista (buy-call / sell-put) -> stop DEBAJO; bajista (buy-put / sell-call) -> ENCIMA."""
    price = float(price)
    bullish = str(kind).lower().startswith("c") == str(side).lower().startswith("b")
    off = round(price * 0.015, 2)
    return round(price - off, 2) if bullish else round(price + off, 2)


def zone_add(sym, price, side, kind, exp=None, qty=1, instrument="opt",
             confirmed_exec=False, overnight_gap_ack=False,
             reviewed_strike=None, reviewed_right=None, reviewed_limit=None):
    """Añade una zona con el ESQUEMA EXTENDIDO (ORDER-ENGINE.md §3). CANDADO señal-solamente:
    exec=False por defecto (ficha-only) — sólo el order_engine C++ con doble llave ejecuta.
    instrument: 'opt' (opciones) | 'stk' (acciones, 24/5)."""
    zones = zones_load(sym)
    side = "sell" if str(side).lower().startswith("s") else "buy"
    kind = "put" if str(kind).lower().startswith("p") else "call"
    instrument = "stk" if str(instrument).lower().startswith("s") else "opt"
    price = round(float(price), 2)
    if not exp and instrument == "opt":
        ex = chain_exps(sym)
        exp = ex[0] if ex else None
    z = {"id": str(int(time.time() * 1000)),
         "price": price, "side": side, "kind": kind,
         "instrument": instrument,         # opt | stk (acciones tradean 24/5)
         "exp": exp,                       # expiry elegida en el chart (no solo 0DTE)
         "qty": max(1, int(qty or 1)),
         "exec": bool(confirmed_exec),     # default duro False; True sólo tras token humano
         "stop": {"on": side == "buy",     # stop propuesto por defecto en zonas de compra
                  "px": _default_stop_px(price, side, kind), "native": True},
         "armed_date": time.strftime("%Y-%m-%d")}   # caduca fin de día salvo re-arme
    if confirmed_exec:
        if instrument == "stk" and overnight_gap_ack is not True:
            z["exec"] = False
            z["confirm_error"] = (
                "debe aceptar explícitamente que IBKR no ofrece STP/GTC overnight")
        else:
            z["confirm_id"] = secrets.token_hex(16)
            z["confirmed_at"] = int(time.time() * 1000)
            if instrument == "stk":
                z["overnight_gap_ack"] = True
                try:
                    z["locked_limit"] = round(float(reviewed_limit), 2)
                except Exception:
                    z["locked_limit"] = 0.0
                if z["locked_limit"] <= 0:
                    z["exec"] = False
                    z["confirm_error"] = "límite revisado inválido"
                    z.pop("confirm_id", None)
                    z.pop("confirmed_at", None)
            else:
                locked = chain_contract(sym, price, kind, exp)
                try:
                    wanted_strike = round(float(reviewed_strike), 4)
                    wanted_limit = round(float(reviewed_limit), 2)
                except Exception:
                    wanted_strike, wanted_limit = 0.0, 0.0
                quote = (locked or {}).get("ask" if side == "buy" else "bid")
                if (not locked or wanted_strike <= 0 or wanted_limit <= 0
                        or abs(float(locked["strike"]) - wanted_strike) > 1e-9
                        or locked["right"] != reviewed_right
                        or round(float(quote or 0), 2) != wanted_limit):
                    z["exec"] = False
                    z["confirm_error"] = "contrato/cotización cambió después del preflight"
                    z.pop("confirm_id", None)
                    z.pop("confirmed_at", None)
                else:
                    z["locked_strike"] = wanted_strike
                    z["locked_right"] = locked["right"]
                    z["locked_exp"] = locked["exp"]
                    z["locked_limit"] = wanted_limit
    zones.append(z)
    zones_save(sym, zones)
    return zones


def zone_update(sym, zid, **fields):
    """Actualiza campos de una zona por id y persiste el contrato. Campos aceptados:
    exp, qty, exec, price, stop_px, stop_on, stop_native. SEÑAL-SOLAMENTE: sólo escribe el
    json que CONSUME el order_engine; jamás coloca órdenes."""
    zones = zones_load(sym)
    for z in zones:
        if z.get("id") != zid:
            continue
        # Cambiar contrato/precio/cantidad invalida una autorización anterior. El
        # humano debe volver a pulsar EXEC después de ver los términos finales.
        material = any(fields.get(k) is not None for k in ("exp", "qty", "price"))
        if material and fields.get("exec") is not True:
            z["exec"] = False
            z.pop("confirm_id", None)
            z.pop("confirmed_at", None)
        if fields.get("exp"):
            z["exp"] = fields["exp"]
        if fields.get("qty") is not None:
            try:
                z["qty"] = max(1, int(fields["qty"]))
            except Exception:
                pass
        if fields.get("exec") is not None:
            z["exec"] = bool(fields["exec"])
            if z["exec"]:
                # Prueba backend de la acción humana. No es una llave de ejecución:
                # el motor aún exige --arm-live + ARM_LIVE de hoy.
                import secrets
                z["confirm_id"] = secrets.token_hex(16)
                z["confirmed_at"] = int(time.time() * 1000)
                z["armed_date"] = time.strftime("%Y-%m-%d")
                if z.get("instrument") == "stk":
                    z["overnight_gap_ack"] = fields.get("overnight_gap_ack") is True
            else:
                z.pop("confirm_id", None)
                z.pop("confirmed_at", None)
        if fields.get("price") is not None:
            try:
                z["price"] = round(float(fields["price"]), 2)
            except Exception:
                pass
        st = z.get("stop") or {"on": True, "native": True}
        if fields.get("stop_px") is not None:
            try:
                st["px"] = round(float(fields["stop_px"]), 2)
            except Exception:
                pass
        if fields.get("stop_on") is not None:
            st["on"] = bool(fields["stop_on"])
        if fields.get("stop_native") is not None:
            st["native"] = bool(fields["stop_native"])
        z["stop"] = st
        if z.get("exec") and z.get("instrument", "opt") == "opt":
            locked = chain_contract(sym, z.get("price"), z.get("kind"), z.get("exp"))
            try:
                wanted_strike = round(float(fields.get("locked_strike")), 4)
                wanted_limit = round(float(fields.get("reviewed_limit")), 2)
            except Exception:
                wanted_strike, wanted_limit = 0.0, 0.0
            wanted_right = str(fields.get("locked_right") or "")
            quote = (locked or {}).get("ask" if z.get("side") == "buy" else "bid")
            if (not locked or wanted_strike <= 0 or wanted_limit <= 0
                    or abs(float(locked["strike"]) - wanted_strike) > 1e-9
                    or locked["right"] != wanted_right
                    or round(float(quote or 0), 2) != wanted_limit):
                z["exec"] = False
                z.pop("confirm_id", None)
                z.pop("confirmed_at", None)
                z["confirm_error"] = "contrato/cotización cambió después del preflight"
            else:
                z["locked_strike"] = wanted_strike
                z["locked_right"] = locked["right"]
                z["locked_exp"] = locked["exp"]
                z["locked_limit"] = wanted_limit
                z.pop("confirm_error", None)
        elif z.get("instrument") == "stk":
            for key in ("locked_strike", "locked_right", "locked_exp"):
                z.pop(key, None)
            if z.get("exec"):
                try:
                    z["locked_limit"] = round(float(fields.get("reviewed_limit")), 2)
                except Exception:
                    z["locked_limit"] = 0.0
            if z.get("exec") and not z.get("overnight_gap_ack"):
                z["exec"] = False
                z.pop("confirm_id", None)
                z.pop("confirmed_at", None)
                z["confirm_error"] = (
                    "debe aceptar explícitamente que IBKR no ofrece STP/GTC overnight")
        break
    zones_save(sym, zones)
    return zones


def zone_del(sym, price=None, zid=None):
    out = []
    for z in zones_load(sym):
        if zid is not None and z.get("id") == zid:
            continue
        if zid is None and price is not None and abs(z.get("price", 1e18) - float(price)) < 1e-6:
            continue
        out.append(z)
    zones_save(sym, out)
    return out


def zones_frame(state):
    """Frame de zonas + expiries disponibles (para el selector del popup en el chart)."""
    return {"type": "zones", "sym": state.sym.upper(),
            "zones": state.zones, "exps": chain_exps(state.sym)}


# --- probabilidad de profit: la calcula OTRO agente (order_engine/prob_profit.py). El chart
# la INVOCA por CLI y RELAYA su JSON. NO ejecuta órdenes: es puro cómputo de probabilidad. ----
PROB_SCRIPT = os.path.join(REPO, "order_engine", "prob_profit.py")


def run_prob(sym, level, side, kind, exp=None):
    """Ejecuta `python3 order_engine/prob_profit.py SYM LEVEL SIDE KIND EXP` y parsea su JSON.
    Degradación LIMPIA si el script aún no existe (lo escribe otro agente) o falla."""
    out = {"prob": None, "verdict": "—", "why": [], "regime": None,
           "magnet": None, "walls": None}
    if level is None or not os.path.exists(PROB_SCRIPT):
        out["why"] = ["prob_profit no disponible aún"]
        return out
    try:
        if not exp:
            ex = chain_exps(sym)
            exp = ex[0] if ex else ""
        p = subprocess.run(
            [sys.executable, PROB_SCRIPT, sym.upper(), str(level),
             (side or "buy"), (kind or "call"), str(exp or "")],
            capture_output=True, text=True, timeout=12, cwd=REPO)
        txt = (p.stdout or "").strip()
        d = json.loads(txt.splitlines()[-1]) if txt else {}
        if isinstance(d, dict):
            out.update(d)
        elif p.returncode != 0:
            out["why"] = [f"prob_profit rc={p.returncode}"]
    except Exception as e:
        out["why"] = [f"prob_profit error: {e}"]
    return out


# ============================================================================
# CUENTA (posiciones / órdenes / balance) + switcher paper-live + acciones.
# READ: conexión dedicada al puerto del MODO (sigue data/ib_mode.txt), readonly.
# ACCIONES (cancel/sell/modify): se RUTEAN al order_engine (único autorizado a
# ordenar, ley #0). El bridge NUNCA coloca órdenes -> escribe un comando en
# order_engine/commands.jsonl que el motor ejecuta con su doble llave.
# ============================================================================
_ACCT = {"ib": None, "port": None, "cid": None}
# clientId de cuenta ÚNICO por ventana: 63 compartido por 6 procesos = error 326
# ("client ya utilizado") y TimeoutError en 5 de 6 ventanas (bug NOK 2026-07-29 23:45).
_ACCT_CID = {"v": 63}
CMD_PATH = os.path.join(REPO, "order_engine", "commands.jsonl")


def _port_listening(port):
    import socket
    s = socket.socket(); s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", int(port))); return True
    except Exception:
        return False
    finally:
        s.close()


def ib_mode_status():
    """Estado del switcher: modo, puerto, cuenta, y si TWS escucha en cada puerto."""
    m = ib_mode.get_mode()
    return {"type": "ibmode", "mode": m, "port": ib_mode.get_port(),
            "account": ib_mode.get_account(),
            "paper_up": ib_mode.any_up("paper"),
            "live_up": ib_mode.any_up("live")}


def execution_guard_status(now=None):
    """Estado visible de las guardas; sólo lectura y sin armar nada."""
    now = now or time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    arm_path = os.path.join(REPO, "order_engine", "ARM_LIVE")
    try:
        arm_file_today = open(arm_path).read().strip() == today
    except Exception:
        arm_file_today = False
    try:
        ps = subprocess.run(["pgrep", "-af", "order_engine/order_engine"],
                            capture_output=True, text=True, timeout=2)
        cmdline = ps.stdout or ""
    except Exception:
        cmdline = ""
    engine_up = bool(cmdline.strip())
    engine_arm_flag = engine_up and "--arm-live" in cmdline
    return {"engine_up": engine_up, "arm_file_today": arm_file_today,
            "engine_arm_flag": engine_arm_flag,
            "double_arm": bool(arm_file_today and engine_arm_flag)}


def order_preflight(sym, request):
    """Normaliza una intención para la UI. Nunca persiste ni llama al broker."""
    errors, warnings = [], []
    symbol = str(sym or "").strip().upper()
    instrument = str(request.get("instrument") or "").lower()
    side = str(request.get("side") or "").lower()
    kind = str(request.get("kind") or "").lower()
    exp = str(request.get("exp") or "")
    try:
        price = round(float(request.get("price")), 2)
    except Exception:
        price = 0.0
    try:
        qty = int(request.get("qty"))
    except Exception:
        qty = 0
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        errors.append("símbolo inválido")
    if instrument not in ("stk", "opt"):
        errors.append("instrumento debe ser acciones u opciones")
    if side not in ("buy", "sell"):
        errors.append("lado debe ser BUY o SELL")
    if price <= 0:
        errors.append("nivel/trigger debe ser positivo")
    if qty < 1 or qty > 10000:
        errors.append("cantidad fuera de 1..10000")

    right = strike = limit_estimate = None
    overnight_eligible = instrument == "stk"
    session = "OVERNIGHT+DAY" if overnight_eligible else "DAY (RTH)"
    if instrument == "opt":
        if kind not in ("call", "put"):
            errors.append("right debe ser CALL o PUT")
        if not re.fullmatch(r"\d{8}", exp):
            errors.append("expiry debe tener formato YYYYMMDD")
        contract = chain_contract(symbol, price, kind, exp) if not errors else None
        if contract is None and not errors:
            errors.append("contrato no disponible en la cadena local")
        elif contract:
            right = contract["right"]
            strike = contract["strike"]
            quote = contract["ask"] if side == "buy" else contract["bid"]
            if quote is None or float(quote) <= 0:
                errors.append("sin bid/ask válido para estimar límite")
            else:
                limit_estimate = round(float(quote), 2)
        warnings.append("Opciones: sesión DAY/RTH solamente.")
    elif instrument == "stk" and price > 0 and side in ("buy", "sell"):
        limit_estimate = round(price * (1.002 if side == "buy" else 0.998), 2)
        warnings.append("Overnight+DAY se solicita sólo para acciones; IBKR revalida elegibilidad al enviar.")
        warnings.append("IBKR no admite STP/GTC en overnight (20:00–03:50 ET): la salida protectiva nativa sólo cubre pre/post y RTH.")

    if side == "sell":
        warnings.append("SELL sólo pasará si reduce inventario largo confirmado por IBKR; short/naked falla cerrado.")
    guard = execution_guard_status()
    mode = ib_mode.get_mode()
    connected = ib_mode.any_up(mode)
    account = ib_mode.get_account()
    if not account:
        warnings.append("Cuenta no configurada.")
    if not connected:
        warnings.append("IB Gateway no está conectado en el modo seleccionado.")
    if not guard["double_arm"]:
        warnings.append("Doble llave incompleta: el motor permanecerá DRY.")
    draft = {"sym": symbol, "instrument": instrument, "side": side,
             "kind": kind if instrument == "opt" else "",
             "exp": exp if instrument == "opt" else "", "price": price, "qty": qty,
             "right": right, "strike": strike, "reviewed_limit": limit_estimate}
    return {"type": "order_preflight", "ok": not errors, "can_prepare": not errors,
            "signal_only": True, "draft": draft, "limit_estimate": limit_estimate,
            "limit_policy": "estimación; el motor recalcula el LMT al trigger",
            "session": session, "overnight_eligible": overnight_eligible,
            "mode": mode, "account": account, "connected": connected,
            "guard": guard, "errors": errors, "warnings": warnings}


_ARM_CONFIRMATIONS = {}
_ARM_CONFIRM_TTL_S = 120


def _zone_confirmation_signature(sym, zone):
    """Campos que cambian dinero/contrato; editar cualquiera invalida el token."""
    instrument = str(zone.get("instrument") or "opt")
    return (str(sym).upper(), str(zone.get("id") or ""),
            instrument, str(zone.get("side") or ""),
            str(zone.get("kind") or "") if instrument == "opt" else "",
            str(zone.get("exp") or "") if instrument == "opt" else "",
            round(float(zone.get("price") or 0), 4), int(zone.get("qty") or 0))


def _new_zone_confirmation_signature(sym, draft):
    """Firma de un ticket aún no persistido (sin id)."""
    copy = dict(draft or {})
    copy["id"] = ""
    return _zone_confirmation_signature(sym, copy)


def _reviewed_terms(draft):
    try:
        strike = round(float(draft.get("strike") or 0), 4)
        limit = round(float(draft.get("reviewed_limit") or 0), 2)
    except Exception:
        strike, limit = 0.0, 0.0
    return (strike, str(draft.get("right") or ""),
            str(draft.get("exp") or ""), limit)


def issue_arm_confirmation(sym, zone_id, preflight, now=None):
    """Challenge de un uso sólo si el preflight coincide con la zona persistida."""
    now = time.monotonic() if now is None else float(now)
    zone = next((z for z in zones_load(sym) if str(z.get("id")) == str(zone_id)), None)
    if zone is None:
        return None, "zona no encontrada"
    draft = preflight.get("draft") or {}
    expected = _zone_confirmation_signature(sym, zone)
    reviewed = _zone_confirmation_signature(sym, {
        "id": zone_id, "instrument": draft.get("instrument"), "side": draft.get("side"),
        "kind": draft.get("kind"), "exp": draft.get("exp"), "price": draft.get("price"),
        "qty": draft.get("qty"),
    })
    if expected != reviewed:
        return None, "el preflight no coincide con la zona actual"
    token = secrets.token_urlsafe(24)
    _ARM_CONFIRMATIONS[token] = {"signature": expected,
                                 "review": _reviewed_terms(draft),
                                 "expires": now + _ARM_CONFIRM_TTL_S}
    for old, record in list(_ARM_CONFIRMATIONS.items()):
        if record["expires"] < now:
            _ARM_CONFIRMATIONS.pop(old, None)
    return token, None


def issue_new_arm_confirmation(sym, preflight, now=None):
    """Challenge para crear+armar en una única confirmación final."""
    now = time.monotonic() if now is None else float(now)
    signature = _new_zone_confirmation_signature(sym, preflight.get("draft") or {})
    token = secrets.token_urlsafe(24)
    _ARM_CONFIRMATIONS[token] = {
        "signature": signature,
        "review": _reviewed_terms(preflight.get("draft") or {}),
        "expires": now + _ARM_CONFIRM_TTL_S, "new": True,
    }
    return token


def consume_arm_confirmation(sym, zone_id, token, human_confirmed, request=None, now=None):
    """Consume el challenge ANTES de permitir exec=true. Fail-closed y one-shot."""
    if human_confirmed is not True or not token:
        return False, "confirmación humana y token requeridos"
    now = time.monotonic() if now is None else float(now)
    record = _ARM_CONFIRMATIONS.pop(str(token), None)
    if record is None:
        return False, "token ausente, inválido o ya usado"
    if record["expires"] < now:
        return False, "token de confirmación expirado"
    zone = next((z for z in zones_load(sym) if str(z.get("id")) == str(zone_id)), None)
    if zone is None or record["signature"] != _zone_confirmation_signature(sym, zone):
        return False, "la zona cambió después del preflight"
    if record.get("review") != _reviewed_terms(request or {}):
        return False, "strike/right/límite cambiaron después del preflight"
    return True, None


def consume_new_arm_confirmation(sym, request, token, human_confirmed, now=None):
    """Valida el ticket nuevo contra el challenge y lo consume antes de persistir."""
    if human_confirmed is not True or not token:
        return False, "confirmación humana y token requeridos"
    now = time.monotonic() if now is None else float(now)
    record = _ARM_CONFIRMATIONS.pop(str(token), None)
    if record is None or not record.get("new"):
        return False, "token ausente, inválido o ya usado"
    if record["expires"] < now:
        return False, "token de confirmación expirado"
    draft = {"instrument": request.get("instrument"), "side": request.get("side"),
             "kind": request.get("kind"), "exp": request.get("exp"),
             "price": request.get("price"), "qty": request.get("qty"),
             "strike": request.get("strike"), "right": request.get("right"),
             "reviewed_limit": request.get("reviewed_limit")}
    if record["signature"] != _new_zone_confirmation_signature(sym, draft):
        return False, "el ticket cambió después del preflight"
    if record.get("review") != _reviewed_terms(draft):
        return False, "strike/right/límite cambiaron después del preflight"
    return True, None


def local_websocket_origin(origin):
    """Los controles de dinero sólo se aceptan desde el cockpit local."""
    if not origin:
        return True
    try:
        from urllib.parse import urlparse
        host = (urlparse(origin).hostname or "").lower()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1")


async def _acct_conn():
    """Conexión readonly al puerto del MODO actual (se reconecta si el modo cambió)."""
    port = ib_mode.get_port()
    cid = _ACCT_CID["v"]
    a = _ACCT["ib"]
    if a is not None and a.isConnected() and _ACCT["port"] == port and _ACCT["cid"] == cid:
        return a
    if a is not None:
        try: a.disconnect()
        except Exception: pass
    from ib_async import IB
    ib = IB()
    await ib.connectAsync("127.0.0.1", port, clientId=cid, readonly=True, timeout=10)
    _ACCT["ib"] = ib; _ACCT["port"] = port; _ACCT["cid"] = cid
    return ib


def _con_label(c):
    if getattr(c, "secType", "") == "OPT":
        return f"{c.symbol} {c.lastTradeDateOrContractMonth} {c.strike:g}{c.right}"
    return f"{c.symbol} {getattr(c, 'secType', '')}".strip()


async def account_snapshot():
    """Posiciones + órdenes de trabajo + balance del MODO actual (readonly)."""
    out = {"type": "account", "mode": ib_mode.get_mode(), "port": ib_mode.get_port(),
           "positions": [], "orders": [], "summary": {}, "err": None}
    try:
        ib = await _acct_conn()
        await asyncio.wait_for(ib.reqAllOpenOrdersAsync(), 15)  # RequestTimeout no cubre *Async
        pnl = {}
        try:
            for pi in ib.portfolio():
                pnl[pi.contract.conId] = (pi.marketPrice, pi.unrealizedPNL)
        except Exception:
            pass
        for p in ib.positions():
            if not p.position:
                continue
            mp, upl = pnl.get(p.contract.conId, (None, None))
            out["positions"].append({
                "conId": p.contract.conId, "label": _con_label(p.contract),
                "sym": p.contract.symbol, "secType": p.contract.secType,
                "right": getattr(p.contract, "right", ""), "strike": getattr(p.contract, "strike", 0),
                "exp": getattr(p.contract, "lastTradeDateOrContractMonth", ""),
                "qty": p.position, "avg": round(p.avgCost / (100 if p.contract.secType == "OPT" else 1), 4),
                "mkt": mp, "upl": round(upl, 2) if upl is not None else None})
        for t in ib.openTrades():
            o, c, st = t.order, t.contract, t.orderStatus
            out["orders"].append({
                "orderId": o.orderId, "ref": o.orderRef, "label": _con_label(c),
                "conId": c.conId, "action": o.action, "type": o.orderType,
                "qty": float(o.totalQuantity), "limit": o.lmtPrice, "aux": o.auxPrice,
                "status": st.status, "ours": str(o.orderRef or "").startswith("OE:")})
        try:
            summ = await asyncio.wait_for(ib.accountSummaryAsync(), 15)
            keep = {"NetLiquidation", "BuyingPower", "AvailableFunds", "UnrealizedPnL", "RealizedPnL"}
            out["summary"] = {v.tag: v.value for v in summ if v.tag in keep}
        except Exception:
            pass
        out["ts"] = int(time.time() * 1000)   # sello de frescura: la UI muestra la EDAD del dato
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"
    return out


LEDGER_PATH = os.path.join(REPO, "order_engine", "ledger", "orders.jsonl")
_VERDICT_RANK = {"dry": 1, "rejected": 2, "accepted": 3, "filled": 4}


def _ledger_tail_lines(nbytes=262144):
    with open(LEDGER_PATH, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - nbytes))
        raw = f.read()
    lines = raw.decode("utf-8", "replace").splitlines()
    if size > nbytes and lines:
        lines = lines[1:]   # la primera puede venir cortada por el seek
    return lines


def _classify_ledger(ev, msg):
    if ev == "fill":
        return "filled"
    if ev in ("intent", "ack"):
        return "accepted"
    if ev == "note":
        u = (msg or "").upper()
        if "RECHAZAD" in u:
            return "rejected"
        if "DRY" in u:
            return "dry"
    return None


def order_verdict(sym, since_ms, window_ms=180000):
    """Veredicto REAL del motor para un comando ya escrito: se lee su ledger, no se adivina.
    verdict ∈ pending|dry|rejected|accepted|filled|unknown. 'unknown' = no se sabe (fail-loud)."""
    sym = (sym or "").strip().upper()
    if not sym or not isinstance(since_ms, int) or since_ms <= 0:
        return None
    now_ms = int(time.time() * 1000)
    if not os.path.exists(LEDGER_PATH):
        return {"sym": sym, "verdict": "unknown", "msg": "order_engine/ledger/orders.jsonl no existe",
                "events": [], "context": [], "ledger_age_s": None, "since": since_ms, "now": now_ms}
    try:
        lines = _ledger_tail_lines()
        age = round(now_ms / 1000.0 - os.path.getmtime(LEDGER_PATH), 1)
    except Exception as e:
        return {"sym": sym, "verdict": "unknown", "msg": f"ledger ilegible: {type(e).__name__}: {e}",
                "events": [], "context": [], "ledger_age_s": None, "since": since_ms, "now": now_ms}

    rx = re.compile(r"\b" + re.escape(sym) + r"\b")
    hi = since_ms + max(1000, int(window_ms))
    events, context = [], []
    for ln in lines:
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            e = json.loads(ln)
        except Exception:
            continue
        ts = e.get("ts")
        if not isinstance(ts, (int, float)) or ts < since_ms or ts > hi:
            continue
        ev, msg = e.get("ev"), e.get("msg") or ""
        csym = str((e.get("contract") or {}).get("sym") or "").upper()
        rec = {"ts": int(ts), "ev": ev, "msg": msg, "sym": csym,
               "px": e.get("px"), "qty": e.get("qty"), "orderId": e.get("orderId")}
        if csym == sym or (not csym and rx.search(msg)):
            rec["verdict"] = _classify_ledger(ev, msg)
            events.append(rec)
        elif ev == "note" and not csym and not re.search(r"\b[A-Z]{2,5}\b", msg):
            context.append(rec)   # solo cháchara GENÉRICA del motor (p.ej. "frozen: error 1100")

    best, msg = None, ""
    for r in events:
        v = r.get("verdict")
        if v and _VERDICT_RANK[v] >= _VERDICT_RANK.get(best, 0):
            best, msg = v, r["msg"] or (f"fill {r.get('qty')} @ {r.get('px')}" if v == "filled" else "")
    return {"sym": sym, "verdict": best or "pending", "msg": msg,
            "events": events[-12:], "context": context[-6:],
            "ledger_age_s": age, "since": since_ms, "now": now_ms}


def route_order_action(act):
    """Escribe un comando para el order_engine (cancel/modify/close). El motor lo
    ejecuta con su doble llave (cancel siempre; modify/close-live requieren ARM_LIVE).
    El bridge JAMÁS coloca la orden él mismo (ley #0)."""
    import time as _t
    # `side` y `secType` SE PASAN (fix 2026-07-24): se perdian aqui, y el motor caia a su
    # default SELL (order_engine.cpp:559-562). Cerrar un CORTO manda "buy" desde el chart
    # (live.html:888) -> con el default se vendia otra vez y se DUPLICABA el corto en vez
    # de cerrarlo. Para largos coincidia por casualidad, asi que nunca se noto.
    cmd = {"ts": int(_t.time() * 1000), "act": act.get("act"),
           "orderId": act.get("orderId"), "limit": act.get("limit"),
           "conId": act.get("conId"), "qty": act.get("qty"),
           "sym": act.get("sym"), "exp": act.get("exp"),
           "strike": act.get("strike"), "right": act.get("right"),
           "side": act.get("side"), "secType": act.get("secType")}
    try:
        engine_up = bool(subprocess.run(
            ["pgrep", "-f", "order_engine/order_engine"],
            capture_output=True, timeout=2).stdout.strip())
        if not engine_up:
            # El motor arranca deliberadamente al EOF para no ejecutar comandos
            # envejecidos. Por tanto encolar ahora sería una falsa promesa.
            return {"type": "order_action", "ok": False, "engine_up": False,
                    "err": "order_engine no está corriendo; no se encoló ningún comando"}
        os.makedirs(os.path.dirname(CMD_PATH), exist_ok=True)
        with open(CMD_PATH, "a") as f:
            f.write(json.dumps(cmd) + "\n")
        return {"type": "order_action", "ok": True, "queued": cmd,
                "engine_up": True, "note": ""}
    except Exception as e:
        return {"type": "order_action", "ok": False, "err": str(e)}


def _nbbo_good(x):
    import math
    return x is not None and isinstance(x, (int, float)) and not math.isnan(float(x)) and float(x) > 0


def build_quick_order_cmd(symbol, instrument, side, qty, limit, exp="", strike=None, right=None):
    """Línea de comando para el motor. BUY abre ('open'); SELL SIEMPRE viaja como
    'close' reduce-only (el motor jamás abre cortos/naked). Pura y testeable."""
    base = {"ts": int(time.time() * 1000), "sym": symbol,
            "secType": "OPT" if instrument == "opt" else "STK",
            "qty": qty, "exp": exp if instrument == "opt" else "",
            "strike": float(strike or 0), "right": str(right or "")}
    if side == "buy":
        base.update({"act": "open", "side": "buy", "limit": limit})
    else:
        base.update({"act": "close", "side": "sell"})
    return base


async def stock_quote(symbol, side):
    """(precio, fuente, error) para CUALQUIER acción, rápido: stream de mktData con
    salida temprana al primer NBBO bueno (~1s en sesión), fallback last/close.
    reqTickersAsync tardaba ~11s fijos -> TimeoutError (bug NOK 2026-07-29)."""
    try:
        from ib_async import Stock
        ib = await _acct_conn()
        qcs = await asyncio.wait_for(
            ib.qualifyContractsAsync(Stock(symbol, "SMART", "USD")), 8)
        if not qcs:
            return None, None, f"{symbol} no cualifica en IBKR"
        tk = ib.reqMktData(qcs[0], "", False, False)
        try:
            best = None
            for i in range(35):                     # sale al primer NBBO (~0.4s en sesión)
                await asyncio.sleep(0.2)
                q = tk.ask if side == "buy" else tk.bid
                if _nbbo_good(q):
                    return float(q), "nbbo", None
                if best is None:
                    for cand, name in ((tk.last, "last"), (tk.close, "close")):
                        if _nbbo_good(cand):
                            best = (float(cand), name); break
                if best and i >= 11:                # 2.4s sin NBBO: last/close basta, rápido
                    return best[0], best[1], None
            if best:
                return best[0], best[1], None
            return None, None, f"sin NBBO/last/close para {symbol} ahora mismo"
        finally:
            try: ib.cancelMktData(qcs[0])
            except Exception: pass
    except Exception as e:
        return None, None, f"sin NBBO para {symbol}: {type(e).__name__}"


_QUICK_LAST = {}


def quick_order_duplicate(symbol, instrument, side, qty, now=None):
    """Doble toque = dos órdenes REALES. Mismo (sym,inst,side,qty) en <2.5s se ignora."""
    now = time.monotonic() if now is None else float(now)
    key = (symbol, instrument, side, int(qty))
    prev = _QUICK_LAST.get(key)
    _QUICK_LAST[key] = now
    return prev is not None and (now - prev) < 2.5


async def quick_order(sym, request):
    """Un toque = orden encolada al motor con su doble llave. El bridge cotiza el
    NBBO fresco (CUALQUIER acción vía IBKR) o la cadena local (opciones del universo),
    fija el límite marketable como TOPE humano y encola. JAMÁS coloca él mismo (ley #0)."""
    symbol = str(request.get("sym") or sym or "").strip().upper()
    instrument = str(request.get("instrument") or "stk").lower()
    side = str(request.get("side") or "").lower()
    kind = str(request.get("kind") or "").lower()
    exp = str(request.get("exp") or "")
    try:
        qty = int(request.get("qty"))
    except Exception:
        qty = 0
    errors = []
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol):
        errors.append("símbolo inválido")
    if side not in ("buy", "sell"):
        errors.append("lado debe ser BUY o SELL")
    if qty < 1 or qty > 10000:
        errors.append("cantidad fuera de 1..10000")
    if instrument not in ("stk", "opt"):
        errors.append("instrumento inválido")
    guard = execution_guard_status()
    account = ib_mode.get_account()
    if not account:
        errors.append("cuenta no configurada")
    if not guard["engine_up"]:
        errors.append("order_engine APAGADO: no se encola (arrancarlo y re-tocar)")
    res = {"type": "quick_order_result", "sym": symbol, "side": side, "qty": qty,
           "instrument": instrument, "armed": guard["double_arm"],
           "mode": ib_mode.get_mode()}
    if errors:
        res.update({"ok": False, "errors": errors})
        return res
    if quick_order_duplicate(symbol, instrument, side, qty):
        res.update({"ok": False, "errors": ["doble toque ignorado: misma orden hace <2.5s"]})
        return res

    limit = strike = right = None
    if instrument == "opt":
        try:
            level = float(request.get("strike") or request.get("price") or 0)
        except Exception:
            level = 0.0
        contract = None
        if kind in ("call", "put") and re.fullmatch(r"\d{8}", exp or ""):
            contract = chain_contract(symbol, level, kind, exp)
        if not contract:
            res.update({"ok": False, "errors": [
                "opción sin cadena local para ese sym/exp (usa un ticker del universo)"]})
            return res
        strike, right = contract["strike"], contract["right"]
        q = contract["ask"] if side == "buy" else contract["bid"]
        if not _nbbo_good(q):
            res.update({"ok": False, "errors": ["sin bid/ask válido en la cadena"]})
            return res
        limit = round(float(q), 2)
    else:
        q, src, err = await stock_quote(symbol, side)
        if err:
            res.update({"ok": False, "errors": [err]})
            return res
        # colchón para asegurar el fill; ese número ES el tope humano que viaja.
        # NBBO vivo = 0.1%; last/close (sin NBBO en ese instante) = 0.3% y se avisa.
        cushion = 0.001 if src == "nbbo" else 0.003
        limit = round(float(q) * (1 + cushion if side == "buy" else 1 - cushion), 2)
        if src != "nbbo":
            res.setdefault("warnings_extra", []).append(
                f"límite desde {src} (sin NBBO vivo ahora mismo)")

    cmd = build_quick_order_cmd(symbol, instrument, side, qty, limit, exp, strike, right)
    os.makedirs(os.path.dirname(CMD_PATH), exist_ok=True)
    with open(CMD_PATH, "a") as f:
        f.write(json.dumps(cmd) + "\n")
    warnings = list(res.pop("warnings_extra", []))
    if not guard["double_arm"]:
        warnings.append("motor SIN doble llave: el comando quedará DRY (no ejecuta)")
    if instrument == "stk" and side == "buy":
        warnings.append("overnight: LMT sin stop nativo hasta 03:50 ET")
    warnings.append("quick-order no arma stop automático")
    res.update({"ok": True, "queued": cmd, "limit": limit, "warnings": warnings})
    return res


def engine_state(sym, n=12):
    """Últimas N líneas de order_engine/state/<sym>.jsonl (lo escribe el motor C++). SÓLO
    LECTURA: el chart RELAYA el estado del motor; nunca ejecuta. Degrada a []."""
    p = os.path.join(REPO, "order_engine", "state", f"{sym.lower()}.jsonl")
    rows = []
    try:
        with open(p) as f:
            lines = f.readlines()[-n:]
    except Exception:
        return []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            rows.append({"raw": ln})
    return rows


async def broadcast_engine(state):
    """Empuja el estado del order_engine (para las zonas exec=true) al chart."""
    if not state.clients:
        return
    rows = engine_state(state.sym)
    if not rows:
        return
    frame = {"type": "engine", "sym": state.sym.upper(), "rows": rows}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


MOCK = False   # lo fija main() desde --mock; ver la guarda de integridad de _log_structural


def _signals_file_line(sym, text):
    """Escribe la ficha en data/trading-signals/<fecha>.txt para que el relay de voz/teléfono
    la dispare (mismo canal que el resto de señales). SEÑAL-SOLAMENTE (solo texto).

    En `--mock` NO escribe: el feed sintético cruza zonas y dispararía fichas por el canal de
    voz/teléfono de produccion. Misma guarda que `_log_structural` (2026-07-25)."""
    if MOCK:
        print(f"[zone] MOCK: NO se registra en produccion -> {sym.upper()} {text}")
        return
    try:
        d = time.strftime("%Y-%m-%d")
        path = os.path.join(REPO, "data", "trading-signals", f"{d}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} | 🎯 ZONA {sym.upper()} | {text}\n")
    except Exception as e:
        print(f"[zone] signals-file falló ({e})")


def build_ticket(sym, price, side, kind):
    """Envuelve order_ticket.build con degradación limpia. NO ejecuta nada."""
    try:
        return order_ticket.build(sym, price, side or "buy", kind or "call")
    except Exception as e:
        return {"ok": False, "verdict": "NO-GO", "sym": (sym or "").upper(),
                "why": [f"error armando ficha: {e}"],
                "ticket": f"❌ {(sym or '').upper()}: error armando ficha"}


ZONE_REFIRE_S = 30   # histéresis: mínimo N s entre disparos de la MISMA zona


async def check_zone_crossings(state, spot):
    """Dispara la ficha una vez por cruce del spot sobre una zona (histéresis anti-jitter).
    Emite {type:'ticket', triggered:true} + registra en trading-signals. SEÑAL-SOLAMENTE."""
    if not spot or not state.zones:
        state._zone_prev_spot = spot
        return
    prev = state._zone_prev_spot
    state._zone_prev_spot = spot
    if prev is None:
        return
    now = time.time()
    for z in state.zones:
        # zona ARMADA (exec=true): la EJECUCIÓN la maneja el order_engine C++ (lee exec_zones,
        # gate, coloca under-the-ground). El chart NO arma ficha ni ejecuta — su estado se relaya
        # aparte via broadcast_engine(). check_zone_crossings sigue INTACTO para exec=false.
        if z.get("exec"):
            continue
        price = z.get("price")
        if price is None:
            continue
        crossed = (prev < price <= spot) or (prev > price >= spot)
        if not crossed:
            continue
        zid = z.get("id")
        if now - state._zone_fired.get(zid, 0) < ZONE_REFIRE_S:
            continue
        state._zone_fired[zid] = now
        t = build_ticket(state.sym, price, z.get("side", "buy"), z.get("kind", "call"))
        _signals_file_line(state.sym, t.get("ticket", ""))
        frame = {"type": "ticket", "sym": state.sym.upper(), "t": t, "triggered": True}
        for ws in list(state.clients):
            try:
                await ws.send_json(frame)
            except Exception:
                state.clients.discard(ws)


COMPASS_MAX_AGE = float(os.environ.get("COMPASS_MAX_AGE", "8"))   # s; mas viejo = flecha RANCIA
DIR_BCAST_S = float(os.environ.get("DIR_BCAST_S", "0.2"))         # s entre frames de flecha


def read_compass(sym):
    """LEE data/compass_<sym>.json (lo escribe ./compass, C++). CERO computo aqui.

    Arquitectura (Yunior 2026-07-25): "python solo para test, la computacion en C++" +
    "si la flecha apunta con retraso de 2 segundos y compramos call en el retroceso cuando
    esta en su punto maximo, no bueno". Antes este callback llamaba a direction_view.compute()
    (100-180 ms POR SIMBOLO, throttle de 2.0 s). Ahora la brujula corre en su propio bucle C++
    (1.09 ms/simbolo) y aqui solo se lee un JSON: microsegundos.

    Si el JSON esta RANCIO se devuelve marcado como tal — NUNCA se recalcula en Python por
    detras: eso seria degradacion silenciosa (una flecha vieja disfrazada de fresca).
    """
    p = os.path.join(REPO, "data", f"compass_{sym.lower()}.json")
    try:
        age = time.time() - os.path.getmtime(p)
        with open(p) as f:
            d = json.load(f)
    except Exception as e:
        return None, f"sin brujula ({type(e).__name__})"
    if age > COMPASS_MAX_AGE:
        d["stale"] = True
        d["stale_age"] = round(age, 1)
        return d, f"brujula RANCIA ({age:.0f}s) — arranca ./compass --loop 0.25"
    d["stale"] = False
    d["stale_age"] = round(age, 2)
    return d, None


async def broadcast_direction(state, lv=None):
    """Flecha-BRUJULA -> overlay del chart. Solo LEE el JSON del binario C++."""
    if not state.clients:
        return
    dv, warn = read_compass(state.sym)
    if warn:
        # fail-loud: se avisa por consola, y si no hay nada que pintar no se pinta
        if getattr(state, "_compass_warn", None) != warn:
            print(f"[dir] {warn}")
            state._compass_warn = warn
    if not dv:
        return
    frame = {"type": "direction", "sym": state.sym.upper(), "dir": dv.get("dir", "flat"),
             "candidate_dir": dv.get("candidate_dir", "flat"),
             "signal_kind": dv.get("signal_kind", "unknown"),
             "prob": dv.get("prob"), "why": dv.get("state_why", []),
             "state": dv.get("state"), "state_pending": dv.get("state_pending"),
             "prob_source": dv.get("prob_source"), "prob_n": dv.get("prob_n"),
             "prob_lo": dv.get("prob_lo"),
             "pending_print": dv.get("pending_print"),
             "families": dv.get("families"), "fading": dv.get("fading", []),
             "vetoes": dv.get("vetoes", []), "level": dv.get("level"),
             "amplitude": dv.get("amplitude"), "mag": dv.get("mag", 0.0),
             "overnight_context": dv.get("overnight_context"),
             "drivers_text": dv.get("drivers_text"), "drivers": dv.get("drivers", []),
             "grade": dv.get("grade"), "stale": dv.get("stale"),
             "stale_age": dv.get("stale_age"),
             "target": dv.get("target"), "target_label": (dv.get("grade") or "objetivo"),
             "target_pct": (None if not dv.get("target") or not dv.get("level")
                            else round((dv["target"] / (dv["level"]["price"] or 1) - 1) * 100, 2))}
    # CALIDAD DEL LIBRO: con coef 0 (THIN) los niveles gamma son decoracion hoy para este
    # nombre y la flecha ya no los pesa (direction_view) ni la brujula da lectura (compass).
    # El chart lo DICE en vez de dejar al operador creerse un mapa que no manda.
    bq_coef, bq_label = direction_view.book_coef(state.sym)
    frame["book_label"] = bq_label
    frame["book_coef"] = bq_coef
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


def history_frame(bars, levels, tf=None, nodata=None, mock=False, kind="history",
                   exhausted=None, exhausted_reason=None, sym=None):
    ind = compute_indicators(bars)
    frame = {
        "type": kind,
        "tf": tf,
        "bars": _candle_points(bars),
        "indicators": indicators_series(bars, ind),
        "pulse": compute_pulse(sym or (levels or {}).get("sym", ""), bars, tf),
        "levels": levels or {},
        "signals": load_signal_markers((levels or {}).get("sym", ""), bars),
        "engineOps": load_engine_ops((levels or {}).get("sym", ""), bars),
        "nodata": nodata if not bars else None,
        # REPLAY: cero "premium disfrazado de real" en la UI (Yunior 2026-07-26). El
        # header debe gritarlo; la fecha la deriva el cliente de bars[-1].time.
        "mock": bool(mock),
    }
    if exhausted is not None:
        frame["exhausted"] = exhausted   # backfill: True = no hay más historia atrás
        frame["reason"] = exhausted_reason if exhausted else None   # la UI lo dice UNA vez
    return frame


def _last_point(pts):
    return pts[-1] if pts else None


def bar_frame(bars, levels, tf=None, sym=None):
    """Frame incremental: última barra + últimos valores de cada indicador (update())."""
    ind = compute_indicators(bars)
    ser = indicators_series(bars, ind)
    last = bars[-1]
    return {
        "type": "bar",
        "tf": tf,
        "bar": {"time": last[0], "open": last[1], "high": last[2],
                "low": last[3], "close": last[4]},
        "pulse": compute_pulse(sym or (levels or {}).get("sym", ""), bars, tf),
        "indicators": {
            "bbUpper": _last_point(ser["bbUpper"]),
            "bbLower": _last_point(ser["bbLower"]),
            "bbMid": _last_point(ser["bbMid"]),
            "sma20": _last_point(ser["sma20"]),
            "sma40": _last_point(ser["sma40"]),
            "sma100": _last_point(ser["sma100"]),
            "sma200": _last_point(ser["sma200"]),
            "vwap": _last_point(ser["vwap"]),
            "macd": _last_point(ser["macd"]),
            "signal": _last_point(ser["signal"]),
            "hist": _last_point(ser["hist"]),
            "volume": _last_point(ser["volume"]),
            "stUp": _last_point(ser["stUp"]),
            "stDn": _last_point(ser["stDn"]),
            "trendlines": ser["trendlines"],   # objeto -> el cliente redibuja
            "madrid": {k: _last_point(v) for k, v in ser["madrid"].items()},
        },
        "levels": levels or {},
    }


# ================================ estado global ==============================
class State:
    """Barras vivas + niveles + clientes WS. Compartido entre el feed y FastAPI."""
    def __init__(self, sym, mock=False):
        self.sym = sym
        self.mock = mock
        self.bars = []          # feed crudo: 5m (mock CSV) / 1m (mock sandbox) / nativo (live)
        self._nodata_reason = None   # por qué self.bars sigue [] (None = aun no se sabe / hay datos)
        self.levels = {}
        self.clients = set()    # WebSocket
        self.base_min = 5 if (mock and not MOCK_DIR) else 1
        self.tf = DEFAULT_TF_MOCK if (mock and not MOCK_DIR) else DEFAULT_TF_LIVE
        self.walls_why = None   # razón por la que los muros vienen a None (o None si vienen)
        self.all_exp = False    # scope GEX: False=0DTE, True=ALL-EXP
        self._vix = None        # último VIX (índice CBOE via ib_async)
        self._vix_live = False  # False = es el cierre anterior, no un tick vivo
        self._vix_ticker = None
        self._px_ticker = None      # reqMktData del stock -> ticks sub-segundo (precio VIVO)
        self._last_tick_bcast = 0.0 # throttle del broadcast de ticks (~8/s)
        # narrador de mercado (tipo gexa): OFF por defecto (thrift de tokens)
        self._narr_on = False       # el usuario lo enciende con el botón
        self._narr_text = ""        # última narración emitida
        self._narr_src = "det"      # "det" (gratis) | "ai" (DeepSeek)
        self._narr_key = None       # firma del estado material (para decidir si vale AI)
        self._narr_ai_ts = 0.0      # última llamada a DeepSeek (throttle)
        self._narr_force = False    # botón ↻: forzar AI ya
        # señal ESTRUCTURAL (imán/flip) mostrada en el chart + guardada en BD
        self._struct = None         # último dict {text,prob,dir,kind,price}
        self._struct_key = None     # firma para dedupe (no spamear BD/voz)
        # ZONAS de ejecución 0DTE (buy/sell call/put) + detección de cruce del spot
        self.zones = zones_load(sym)   # [{id,price,side,kind}] desde disco (degrada a [])
        self._zone_prev_spot = None    # último spot visto (para detectar cruces)
        self._zone_fired = {}          # id_zona -> epoch último disparo (histéresis)
        # refs para re-pedir reqHistoricalData al cambiar de tf en LIVE
        self._ib = None
        self._contract = None
        self._live_sub = None
        self._agg_step = None   # tf agregado (45s -> 45); None = barSize nativo directo
        self._agg_raw = []      # buffer del barSize base cuando _agg_step está activo
        self._backfilling = False   # un solo "more" a la vez por symbol/State compartido
        self._backfill_reason = None   # por qué el ultimo backfill dijo exhausted (UI lo dice UNA vez)
        self._last_sub_ts = 0.0     # ultimo update de la sub keepUpToDate (0 = nunca llego)
        self._last_tick_ts = 0.0    # ultimo tick valido de reqMktData
        self._rt_source = None      # fallback WS canónico cuando TWS/Gateway no está disponible
        self._rt_tick_epoch = 0.0   # epoch de bolsa del último print fallback aplicado
        self._last_file_poll = 0.0  # throttle independiente del tick WS (fichero de barras)
        self._stale_note = None     # banner "sin fuente sub-minuto" vigente (None = sin banner)

    def set_bars(self, bars):
        self.bars = bars

    def upsert_bar(self, bar):
        """Reemplaza si mismo epoch (barra en curso), si no, agrega."""
        if self.bars and self.bars[-1][0] == bar[0]:
            self.bars[-1] = bar
        else:
            self.bars.append(bar)


def agg_epoch(bars, step_s):
    """Bars -> buckets de `step_s` segundos, fijados por EPOCH (no indice): una barra
    que falta no corre el reloj. Mismo patron que opening_plan.py::agg (en minutos)."""
    out = []
    for b in bars:
        k = b[0] - (b[0] % step_s)
        if out and out[-1][0] == k:
            c = out[-1]
            c[2] = max(c[2], b[2]); c[3] = min(c[3], b[3]); c[4] = b[4]; c[5] += b[5]
        else:
            out.append([k, b[1], b[2], b[3], b[4], b[5]])
    return out


def tf_minutes(state):
    """Minutos del tf pedido. TF_MIN mapea '1m'->5 porque la base del mock-CSV es 5m; con
    --mock-dir la base SI es 1m (barras del sandbox de replay)."""
    base = getattr(state, "base_min", 5)
    if state.tf == "1m":
        return base
    return TF_MIN.get(state.tf, base)


def agg_view_bars(state):
    """Barras que VE el chart al tf actual.
    MOCK: base 5m (CSV) o 1m (--mock-dir) -> se agrega hacia arriba (ce.aggregate, paridad
          con el engine); SEC_TF no tiene fuente sub-minuto -> [] (nunca finge, y NUNCA
          destruye state.bars: el CSV base sigue intacto para el siguiente tf). LIVE:
          state.bars ya viene al barSize nativo pedido en live_reapply, tal cual."""
    if not state.mock:
        return state.bars
    if state.tf in SEC_TF:
        return []
    base = getattr(state, "base_min", 5)
    mins = tf_minutes(state)
    if mins <= base:
        return state.bars
    return ce.aggregate(state.bars, mins)


async def set_timeframe(state, tf):
    """Cambia el tf global. MOCK: solo marca tf (agg_view_bars agrega o declara vacío para
    SEC_TF, state.bars NUNCA se toca). LIVE: re-pide reqHistoricalData con el barSize
    nativo (cancela el anterior)."""
    if tf not in ALL_TF:
        return
    state.tf = tf
    if state.mock:
        if tf in SEC_TF:
            state._nodata_reason = (f"{tf}: sin fuente offline en --mock "
                                     f"(base ≥1m) — prueba con el Gateway LIVE")
        else:
            state._nodata_reason = None
            if tf == "1m" and getattr(state, "base_min", 5) > 1:
                print("[tf] '1m' sin fuente offline en --mock -> uso 5m")
        return
    if state._ib is not None:
        try:
            await live_reapply(state, tf)
        except Exception as e:
            print(f"[tf] live_reapply({tf}) falló ({e})")


async def live_reapply(state, tf):
    """LIVE: cancela la suscripción de barras vigente y re-pide al barSize nativo
    del tf, re-atando keepUpToDate. tf en AGG_TF (45s): pide el nativo base (15s) y
    agrega por epoch (agg_epoch) — 45s no existe en IBKR. SEÑAL-SOLAMENTE: solo
    reqHistoricalData."""
    ib = state._ib
    if ib is None or state._contract is None:
        return
    if state._live_sub is not None:
        try:
            ib.cancelHistoricalData(state._live_sub)
        except Exception:
            pass
    if tf in AGG_TF:
        base_tf, step_s = AGG_TF[tf]
        bar_size, dur = LIVE_BAR[base_tf]
        state._agg_step = step_s
    else:
        bar_size, dur = LIVE_BAR.get(tf, ("1 min", "2 D"))
        state._agg_step = None
        state._agg_raw = []
    bars = await asyncio.wait_for(ib.reqHistoricalDataAsync(   # async (ver live_feed)
        state._contract, endDateTime="", durationStr=dur, barSizeSetting=bar_size,
        whatToShow="TRADES", useRTH=False, keepUpToDate=True,
    ), 20)
    raw = [[int(b.date.timestamp()), b.open, b.high, b.low, b.close, float(b.volume)]
           for b in bars]
    if state._agg_step:
        state._agg_raw = raw
        state.set_bars(agg_epoch(raw, state._agg_step))
    else:
        state.set_bars(raw)
    tag = f"{bar_size} agregado a {tf}" if state._agg_step else bar_size
    state._nodata_reason = None if state.bars else f"TWS sin barras para {state.sym.upper()} ({tag})"
    state._last_sub_ts = time.time()
    bars.updateEvent += _make_on_bar(state)
    state._live_sub = bars
    print(f"[tf] LIVE {state.sym}: {tag} -> {len(state.bars)} barras")


async def fetch_more_history(state, before_epoch):
    """Pan-scroll hacia atrás (Yunior 2026-07-26 "load data on demand when scrolling,
    priority to live data"): UN request de más barras viejas, keepUpToDate=False -> nunca
    toca ni compite con la suscripción viva (state._live_sub sigue intacta, el tick sigue
    empujando en su propia corrutina). MOCK: el CSV entero ya está en memoria desde el
    arranque -> no hay más que traer, se declara agotado. False = sin barras nuevas
    (agotado o error de TWS); nunca se finge continuidad."""
    if not before_epoch:
        state._backfill_reason = "sin ancla (before) del cliente"
        return False
    if state.mock:
        state._backfill_reason = "modo mock: toda la historia ya esta en memoria desde el arranque"
        return False
    if state._ib is None:
        state._backfill_reason = "este bridge no esta conectado a IBKR — sin historia que pedir"
        return False
    if state._contract is None:
        # Antes decia "conexion TWS no lista": mentira en el caso coreano, donde la conexion
        # esta perfecta y lo que falta es el contrato KRX. Se dice cual de las dos es.
        state._backfill_reason = (f"{state.sym.upper()}: contrato aun sin cualificar en IBKR "
                                  f"— reintenta al hacer scroll de nuevo")
        return False
    if state._backfilling:
        return False   # ya hay una peticion en vuelo (misma State) -> se ignora, sin pisar la reason previa
    state._backfilling = True
    try:
        base_tf = AGG_TF[state.tf][0] if state.tf in AGG_TF else state.tf
        bar_size, dur = LIVE_BAR.get(base_tf, ("1 min", "2 D"))
        end = datetime.fromtimestamp(float(before_epoch), timezone.utc)
        try:
            bars = await state._ib.reqHistoricalDataAsync(
                state._contract, endDateTime=end, durationStr=dur, barSizeSetting=bar_size,
                whatToShow="TRADES", useRTH=False, keepUpToDate=False,
            )
        except Exception as e:
            print(f"[more] {state.sym} {base_tf} antes de {end}: fallo ({e})")
            state._backfill_reason = f"IBKR rechazo la peticion ({base_tf}): {e}"
            return False
        raw = [[int(b.date.timestamp()), b.open, b.high, b.low, b.close, float(b.volume)]
               for b in bars if b.date.timestamp() < before_epoch]
        if not raw:
            state._backfill_reason = (f"IBKR sin mas historia de {state.sym.upper()} "
                                       f"({base_tf}) antes de {end:%Y-%m-%d %H:%M} UTC "
                                       f"— tope de profundidad de este barSize")
            return False
        state._backfill_reason = None
        base = state._agg_raw if state._agg_step else state.bars
        merged = {r[0]: r for r in raw}
        for r in base:
            merged[r[0]] = r
        ordered = [merged[k] for k in sorted(merged)]
        if state._agg_step:
            state._agg_raw = ordered
            state.set_bars(agg_epoch(ordered, state._agg_step))
        else:
            state.set_bars(ordered)
        print(f"[more] {state.sym} {state.tf}: +{len(raw)} barras antes de {end} "
              f"-> {len(state.bars)} totales")
        return True
    finally:
        state._backfilling = False


# ===================== REGISTRO DE ESTADOS: UNO POR SIMBOLO ==================
# Yunior 2026-07-25: "when changing symbol in one graph the other graphs change too,
# they should be independent entirely". Antes habia UN State global y TODAS las ventanas
# lo compartian: la que cambiaba de ticker se lo cambiaba a las demas. Peor: las otras
# conservaban sus velas viejas y recibian los NIVELES del ticker nuevo, asi que el chart
# mezclaba velas de SPY (710) con muros de AAPL (330) y el autoscale estiraba la escala
# de 328 a 743 — el sintoma "la barra de precios muestra precios incorrectos".
#
# Ahora: un State por SIMBOLO, creado bajo demanda y APAGADO cuando se queda sin
# ventanas. Dos ventanas en el mismo ticker COMPARTEN estado (una sola suscripcion a
# TWS, un solo levels_loop) — que es lo que hace barato tener seis.
# LIMITACION CONOCIDA: el timeframe va por SIMBOLO, no por ventana. Dos ventanas del
# MISMO ticker con tf distinto se pisan; con tickers distintos, cada una manda en el suyo.
STATES = {}            # sym (minusculas) -> State
STATE_CFG = {"mock": False, "port": None, "client_id": 60, "interval": 1.0}
SHARED_IB = {"ib": None}   # conexion ib_async unica, compartida por todos los estados
PRIMARY_SYM = {"sym": None}


def _prime_bars(st):
    """Carga SINCRONA de las barras de arranque, ANTES de que el State se devuelva a nadie.
    Medido 2026-07-26 (ws_probe2): sin esto, el primer history_frame tras {cmd:"sym"} salia
    con bars=0 el 100% de las veces (get_state agendaba _spawn_state con ensure_future y el
    handler mandaba el frame antes de que corriera) -> ventana muda tras elegir un simbolo
    nuevo en la watchlist. Si de verdad no hay dato (sandbox sin ese simbolo, o sin archivo
    de barras 1m) se deja constancia en st._nodata_reason en vez de quedar en silencio."""
    if st.mock:
        all_bars, warm, reason = _mock_load(st.sym)
        if reason:
            st._nodata_reason = reason
        elif all_bars:
            st.set_bars(all_bars[:warm])
    else:
        bars = load_ibkr_bars(st.sym, tail=780)
        if bars:
            st.set_bars(bars)
        else:
            reason = (f"sin barras 1m locales para {st.sym.upper()} "
                      f"(data/bars_{st.sym}_ibkr.txt) — esperando TWS")
            perp = load_perp_stocks().get(st.sym.upper())
            if perp:
                reason += (f" | PERP bybit {perp['px']:g} (edad {perp['feed_age_s']:.0f}s, "
                           f"NO es precio de la acción)")
            st._nodata_reason = reason


def get_state(sym):
    """State del simbolo (lo crea y arranca sus bucles si no existia)."""
    sym = (sym or "").strip().lower()
    st = STATES.get(sym)
    if st is not None:
        return st
    st = State(sym, mock=STATE_CFG["mock"])
    st.levels = load_levels(sym) or {}
    _prime_bars(st)
    STATES[sym] = st
    asyncio.ensure_future(_spawn_state(st))
    print(f"[multi] estado NUEVO {sym.upper()} (abiertos: {len(STATES)})")
    return st


async def korea_poll_feed(st, interval=5.0):
    """KOREA_SYMS no tienen contrato propio en este bridge: el realtime (mdt=1, IBKR) lo
    escribe korea_bar_bridge.py (clientId 86) a data/bars_<stem>.txt. Aquí solo se TAIL-ea
    ese archivo — sin qualify, sin reqHistoricalData duplicado."""
    while True:
        await asyncio.sleep(interval)
        bars = load_ibkr_bars(st.sym, tail=780)
        if bars and (not st.bars or bars[-1] != st.bars[-1]):
            st.set_bars(bars)
            st._nodata_reason = None
            asyncio.ensure_future(broadcast(st))
        elif not bars and st.bars is not None and not st._nodata_reason:
            st._nodata_reason = (f"sin barras KRX para {st.sym.upper()} "
                                  f"(data/bars_{st.sym}.txt) — korea_bar_bridge.py caído?")


async def send_stale_note(st, text):
    """Banner de staleness al chart (text=None lo retira). No toca nodata (eso es bars=[])."""
    st._stale_note = text
    frame = {"type": "stale", "sym": st.sym.upper(), "text": text}
    for ws in list(st.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            st.clients.discard(ws)


def apply_realtime_fallback_tick(st, max_age_s=RT_FALLBACK_MAX_AGE_S):
    """Apply one fresh canonical websocket print to the in-progress chart candle.

    This is the live-price fallback when TWS/IB Gateway is unavailable. It accepts only
    sources that write exchange timestamps through rt_last.write_if_newer(), never REST
    quotes or delayed bars. Returns the source name when a new tick was applied, else None.
    """
    if st.mock or st.sym.upper() in KOREA_SYMS() or not st.bars:
        return None
    tick = rt_last.fresh(st.sym, max_age_s=max_age_s)
    if tick is None:
        return None
    price, epoch, source, _age = tick
    source = str(source).lower()
    if source not in RT_FALLBACK_SOURCES or epoch <= st._rt_tick_epoch:
        return None
    step = st._agg_step or TF_S.get(st.tf)
    if not step:  # daily/weekly/monthly candles keep their native TWS semantics
        return None
    bucket = int(epoch) - int(epoch) % step
    if bucket < st.bars[-1][0]:
        return None
    if bucket > st.bars[-1][0]:
        st.bars.append([bucket, price, price, price, price, 0.0])
    else:
        bar = st.bars[-1]
        bar[2] = max(bar[2], price)
        bar[3] = min(bar[3], price)
        bar[4] = price
    st._last_tick_ts = time.time()
    st._rt_tick_epoch = epoch
    st._rt_source = source
    return source


def _hm_et(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


async def us_stale_feed(st, interval=0.5):
    """La sub keepUpToDate US se CONGELA a las 20:00 ET (medido: ultima barra 19:59 con
    data/bars_<sym>_ibkr.txt fresco toda la noche). Mismo patron que korea_poll_feed: sub
    muda >STALE_SUB_S -> tail del fichero 1m del bar_bridge (agregado al tf si hace falta);
    cuando la sub vuelve a empujar, recupera el mando sola. SEÑAL-SOLAMENTE."""
    while True:
        await asyncio.sleep(interval)
        try:
            if st.mock or st.sym.upper() in KOREA_SYMS():
                continue
            now = time.time()
            if now - st._last_sub_ts < STALE_SUB_S:
                if st._stale_note:
                    await send_stale_note(st, None)
                continue
            # TWS is absent/frozen, but the canonical websocket print can still move the
            # current candle in realtime. The slower bar file below backfills OHLC/volume.
            rt_source = apply_realtime_fallback_tick(st)
            if rt_source:
                if st._stale_note:
                    await send_stale_note(st, None)
                await broadcast_tick(st)
            if st.tf in SEC_TF:
                # bar_bridge es 1m: sin fuente sub-minuto. Si hay ticks, _make_on_tick ya
                # construye las velas; si no, se dice — jamas se ensena 19:59 como viva.
                if now - st._last_tick_ts > STALE_SUB_S:
                    hm = _hm_et(st.bars[-1][0]) + " ET" if st.bars else "—"
                    await send_stale_note(st, f"sin datos sub-minuto fuera de sesión — usa 1m+ "
                                              f"(última vela {hm})")
                elif st._stale_note:
                    await send_stale_note(st, None)
                continue
            step = TF_S.get(st.tf)
            if step is None:
                continue   # 1d/1W/1M: la vela del dia no se mueve overnight
            if now - st._last_file_poll < BAR_FALLBACK_POLL_S:
                continue
            st._last_file_poll = now
            fresh = load_ibkr_bars(st.sym, tail=780)
            if not fresh:
                continue
            if step > 60:
                fresh = agg_epoch(fresh, step)
            # merge COMPLETO por epoch: si un tick abrio ya el bucket de ahora, "solo
            # despues de la ultima" tiraba TODO el backfill 20:00->ahora (hueco medido:
            # 1921 barras en vez de ~2200). Fichero manda en barras CERRADAS (volumen);
            # el bucket en formacion se queda con los ticks (sin flicker hacia atras).
            cur = {b[0]: b for b in st.bars}
            form = int(now) - int(now) % step
            appended = changed = 0
            for b in fresh:
                old = cur.get(b[0])
                if old is None:
                    cur[b[0]] = b
                    appended += 1
                elif old != b and b[0] < form:
                    cur[b[0]] = b
                    changed += 1
            if not (appended or changed):
                continue
            bars = [cur[k] for k in sorted(cur)]
            st.set_bars(bars[-6000:] if len(bars) > 6000 else bars)
            st._nodata_reason = None
            if appended > 1:   # catch-up con hueco -> history completo, no un update suelto
                frame = history_frame(agg_view_bars(st), st.levels, st.tf,
                                       nodata=None, mock=st.mock, sym=st.sym)
                for ws in list(st.clients):
                    try:
                        await ws.send_json(frame)
                    except Exception:
                        st.clients.discard(ws)
                print(f"[stale] {st.sym.upper()}: sub congelada, +{appended} barras del fichero (tf={st.tf})")
            else:
                await broadcast(st)
        except Exception as e:
            print(f"[stale] {st.sym} watchdog falló ({e})")


async def _spawn_state(st):
    """Arranca el feed y el levels_loop de un estado recien creado."""
    try:
        if st.mock:
            st._tasks = [asyncio.ensure_future(mock_feed(st, interval=STATE_CFG["interval"]))]
        elif st.sym.upper() in KOREA_SYMS():
            st._tasks = [asyncio.ensure_future(korea_poll_feed(st))]
        else:
            st._tasks = [asyncio.ensure_future(us_stale_feed(st))]
            ib = SHARED_IB["ib"]
            if ib is not None:
                # se REUSA la conexion (un solo clientId): cada estado añade su propio
                # contrato + tick stream. Nada de una conexion por ventana.
                st._ib = ib
                base = st.bars   # _prime_bars ya la cargo sincrono (sin carrera)
                try:
                    ib.pendingTickersEvent += _make_on_tick(st)
                except Exception:
                    pass
                await _relive_symbol(st, st.sym, rebroadcast=not base)
        st._tasks.append(asyncio.ensure_future(levels_loop(st)))
    except Exception as e:
        print(f"[multi] no pude arrancar {st.sym.upper()}: {e}")


def reap_state(st):
    """Apaga un estado SECUNDARIO que se quedo sin ventanas: cancela sus bucles y suelta
    la suscripcion de TWS. El PRIMARIO nunca se apaga (es el que arranco el bridge)."""
    if st is None or st.clients:
        return
    if st.sym == PRIMARY_SYM["sym"]:
        return
    for t in getattr(st, "_tasks", []):
        try: t.cancel()
        except Exception: pass
    ib = st._ib
    if ib is not None:
        if st._live_sub is not None:
            try: ib.cancelHistoricalData(st._live_sub)
            except Exception: pass
        if st._contract is not None:
            try: ib.cancelMktData(st._contract)   # libera la data line (son limitadas)
            except Exception: pass
    STATES.pop(st.sym, None)
    print(f"[multi] estado CERRADO {st.sym.upper()} (abiertos: {len(STATES)})")


async def set_symbol(state, sym):
    """Cambia el TICKER. LIVE: re-cualifica el contrato y re-pide barras al tf actual.
    MOCK: recarga el CSV base del nuevo símbolo. En ambos: regenera niveles GEX.
    SEÑAL-SOLAMENTE."""
    sym = (sym or "").strip().lower()
    if not sym or sym == state.sym:
        return
    state.sym = sym
    state.levels = load_levels(sym, all_exp=state.all_exp)
    state.zones = zones_load(sym)      # zonas 0DTE del nuevo símbolo
    state._zone_prev_spot = None
    state._zone_fired = {}
    if state.mock:
        base = load_csv_bars(sym, tail=400)
        state.set_bars(base)
        print(f"[sym] MOCK -> {sym.upper()} ({len(base)} barras 5m)")
        return
    # LIVE — SWITCH INSTANTÁNEO (TradingView-like): muestra ya las barras del archivo
    # OS-cacheado (el fleet bar_bridge las mantiene para los 33); la suscripción viva a
    # TWS (qualify + reqHistoricalData + tick stream) se re-ata en BACKGROUND y re-emite
    # un history fresco cuando llega. Antes bloqueaba ~1-2s en 2 round-trips a TWS.
    instant = load_ibkr_bars(sym, tail=780)
    if instant:
        state.set_bars(instant)
        state._nodata_reason = None
        print(f"[sym] {sym.upper()}: {len(instant)} barras instantáneas (archivo, sin esperar TWS)")
    else:
        # SIN archivo para el nuevo símbolo: JAMÁS dejar las velas del símbolo VIEJO en
        # pantalla con la etiqueta nueva puesta encima (precio de X mostrado como si fuera
        # de Y — el "cero plausible" prohibido, versión gráfico). Vacío hasta que llegue algo
        # real (instante o TWS).
        state.set_bars([])
        reason = f"sin barras 1m locales para {sym.upper()} — esperando TWS"
        perp = load_perp_stocks().get(sym.upper())
        if perp:
            reason += (f" | PERP bybit {perp['px']:g} (edad {perp['feed_age_s']:.0f}s, "
                       f"NO es precio de la acción)")
        state._nodata_reason = reason
    if sym.upper() in KOREA_SYMS():
        # El vivo lo tail-ea korea_poll_feed, pero el contrato del simbolo VIEJO se quedaba
        # aqui: fetch_more_history lo daba por bueno y rellenaba el chart coreano con barras
        # de QQQ. Se limpia YA y se cualifica el KRX de verdad para que el scroll funcione.
        state._contract = None
        if state._ib is not None:
            asyncio.ensure_future(_relive_korea(state, sym))
    elif state._ib is not None:
        # re-broadcast del history solo si NO hubo carga instantánea (símbolo fuera de la
        # flota) -> evita el DOBLE LOAD: con archivo, los updates incrementales bastan.
        asyncio.ensure_future(_relive_symbol(state, sym, rebroadcast=not instant))


def _krx_conid(sym):
    """conId KRX de data/korea_contracts.txt (lo escribe korea_bar_bridge, fuente unica).
    None si no esta -> el caller lo dice, no adivina un contrato."""
    try:
        with open(os.path.join(REPO, "data", "korea_contracts.txt")) as f:
            for ln in f:
                p = ln.split()
                if len(p) >= 2 and p[0].upper() == sym.upper():
                    return int(p[1])
    except (OSError, ValueError):
        pass
    return None


async def _relive_korea(state, sym):
    """Cualifica el contrato KRX para que el scroll hacia atras traiga historia REAL del
    simbolo coreano. El vivo sigue viniendo del archivo (korea_poll_feed); esto es solo
    para reqHistoricalData. SEÑAL-SOLAMENTE."""
    ib = state._ib
    cid = _krx_conid(sym)
    if ib is None or cid is None:
        state._backfill_reason = (f"{sym.upper()}: sin conId KRX en data/korea_contracts.txt "
                                  f"— el scroll no puede pedir historia a IBKR")
        return
    from ib_async import Contract
    try:
        # wait_for obligatorio: RequestTimeout NO cubre las llamadas *Async (solo el camino
        # sincrono via util.run) — sin esto, TWS mudo congela esta task para siempre (caza 2026-07-28)
        (c,) = await asyncio.wait_for(
            ib.qualifyContractsAsync(Contract(conId=cid, exchange="KRX")), 15)
    except Exception as e:
        state._backfill_reason = f"{sym.upper()}: IBKR no cualifica el KRX conId {cid} ({e})"
        print(f"[sym] KRX no cualifica {sym.upper()} conId {cid} ({e})")
        return
    state._contract = c
    print(f"[sym] {sym.upper()}: contrato KRX {c.localSymbol} listo (scroll con historia real)")


async def _relive_symbol(state, sym, rebroadcast=False):
    """Re-ata la suscripción VIVA a TWS al nuevo símbolo, en background. Solo re-emite un
    history frame si rebroadcast=True (no hubo carga instantánea) -> evita doble render.
    SEÑAL-SOLAMENTE."""
    ib = state._ib
    if ib is None:
        return
    if state._live_sub is not None:
        try: ib.cancelHistoricalData(state._live_sub)
        except Exception: pass
    if state._contract is not None:
        try: ib.cancelMktData(state._contract)   # libera la data line del símbolo viejo
        except Exception: pass
    from ib_async import Stock
    contract = Stock(sym.upper(), "SMART", "USD")
    try:
        (contract,) = await asyncio.wait_for(ib.qualifyContractsAsync(contract), 15)
    except Exception as e:
        print(f"[sym] no cualifica {sym.upper()} ({e})")
        if not state.bars:   # sin archivo instantáneo Y sin contrato -> decirlo, no callar
            state._nodata_reason = f"IBKR no reconoce el símbolo {sym.upper()} ({e})"
            frame = history_frame(agg_view_bars(state), state.levels, state.tf,
                                   nodata=state._nodata_reason, mock=state.mock, sym=state.sym)
            for ws in list(state.clients):
                try: await ws.send_json(frame)
                except Exception: state.clients.discard(ws)
        return
    state._contract = contract
    try: state._px_ticker = ib.reqMktData(contract, "", False, False)   # tick stream nuevo
    except Exception: pass
    await live_reapply(state, state.tf)
    if rebroadcast:   # solo si no hubo carga instantánea (símbolo fuera de la flota)
        frame = history_frame(agg_view_bars(state), state.levels, state.tf, nodata=state._nodata_reason, mock=state.mock, sym=state.sym)
        for ws in list(state.clients):
            try: await ws.send_json(frame)
            except Exception: state.clients.discard(ws)
    print(f"[sym] LIVE -> {sym.upper()}")


# ============================== FastAPI (opcional) ===========================
# Guardado: en 3.9/sin fastapi el módulo sigue importable para --selftest.
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse
    HAVE_FASTAPI = True
except Exception:
    HAVE_FASTAPI = False


def create_app(state):
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI(title="ib-trader chart bridge (signal-only)")

    @app.get("/")
    async def index():
        if os.path.exists(LIVE_HTML):
            return FileResponse(LIVE_HTML)
        return JSONResponse({"error": "charts/live.html no encontrado"}, status_code=404)

    try:  # version publica secuencial; el hash queda solo como diagnostico interno
        with open(os.path.join(REPO, "macapp", "VERSION"), encoding="utf-8") as f:
            public_version = f.read().strip()
        if not public_version.isdigit():
            raise ValueError("macapp/VERSION debe ser un entero")
        _ver = {"version": public_version,
                "commit_date": subprocess.check_output(
                    ["git", "-C", REPO, "show", "-s", "--format=%cd",
                     "--date=format:%Y-%m-%d %H:%M", "HEAD"], text=True).strip()}
    except Exception:
        _ver = {"version": None, "commit_date": None}

    @app.get("/version")
    async def version():
        return JSONResponse(_ver)

    @app.get("/lightweight-charts-v5.js")
    async def lib():
        p = os.path.join(os.path.dirname(LIVE_HTML), "lightweight-charts-v5.js")
        if os.path.exists(p):
            return FileResponse(p, media_type="application/javascript")
        return JSONResponse({"error": "lightweight-charts-v5.js no encontrado"}, status_code=404)

    @app.get("/order_ticket_ui.js")
    async def ticket_ui():
        # Sin este fichero OrderTicketUI no existe y "Revisar" muere mudo (bug NOK 2026-07-29).
        p = os.path.join(os.path.dirname(LIVE_HTML), "order_ticket_ui.js")
        if os.path.exists(p):
            return FileResponse(p, media_type="application/javascript")
        return JSONResponse({"error": "order_ticket_ui.js no encontrado"}, status_code=404)

    @app.get("/uw_widgets.js")
    async def uw_widgets_js():
        p = os.path.join(os.path.dirname(LIVE_HTML), "uw_widgets.js")
        if os.path.exists(p):
            return FileResponse(p, media_type="application/javascript")
        return JSONResponse({"error": "uw_widgets.js no encontrado"}, status_code=404)

    @app.get("/indicator_panel.js")
    async def indicator_panel_ui():
        p = os.path.join(os.path.dirname(LIVE_HTML), "indicator_panel.js")
        if os.path.exists(p):
            return FileResponse(p, media_type="application/javascript")
        return JSONResponse({"error": "indicator_panel.js no encontrado"}, status_code=404)

    @app.get("/favicon.svg")
    async def favicon():
        p = os.path.join(os.path.dirname(LIVE_HTML), "favicon.svg")
        if os.path.exists(p):
            return FileResponse(p, media_type="image/svg+xml")
        return JSONResponse({"error": "favicon.svg no encontrado"}, status_code=404)

    @app.get("/technicals")
    async def technicals(sym: str = ""):
        # Finviz NO es tiempo real: se sirve con procedencia y edad, y el frontend las
        # ensena. Fuera de alcance -> 503 con el motivo, nunca un dict a medias.
        s = (sym or state.sym).upper()
        try:
            import finviz_technicals as ft
            return JSONResponse(await asyncio.to_thread(ft.get_technicals, s))
        except Exception as e:
            return JSONResponse({"sym": s, "error": f"{type(e).__name__}: {e}"},
                                status_code=503)


    @app.get("/api/book_quality")
    async def book_quality(sym: str = ""):
        s = (sym or state.sym).upper()
        try:
            import opt_book_quality as obq
            result = obq.assess_book(s)
            if not result:
                return JSONResponse({"sym": s, "error": "sin libro"}, status_code=404)
            return JSONResponse({"sym": s, **result})
        except Exception as e:
            return JSONResponse({"sym": s, "error": str(e)}, status_code=500)

    _DATA_WL = ("iv_regime.json", "rv_iv_spread.json",   # whitelist: jamas servir data/ entero (BD, envs)
                "uw_darkpool.json", "uw_net_prem.json", "uw_gex_expiry.json")
    @app.get("/data/{fname}")
    async def data_json(fname: str):
        if not (fname in _DATA_WL or (fname.startswith("strike_heatmap_") and fname.endswith(".json"))):
            return JSONResponse({"error": "no servido"}, status_code=404)
        p = os.path.join(REPO, "data", os.path.basename(fname))
        if not os.path.exists(p):
            return JSONResponse({"error": "sin dato aun"}, status_code=404)
        with open(p) as f:
            return JSONResponse(json.load(f))

    @app.get("/api/gamma_decay")
    async def gamma_decay(sym: str = ""):
        s = (sym or state.sym).upper()
        try:
            import json, os, gex_core
            # Leer opt_chain fresco y calcular gamma_by_expiry
            with open(f"data/opt_chain_{s.lower()}.txt") as f:
                rows, spot = [], None
                for ln in f:
                    if ln.startswith("#"):
                        if "spot" in ln:
                            try: spot = float(ln.split("spot ")[1].split()[0])
                            except: pass
                        continue
                    p = ln.split()
                    if len(p) >= 7:
                        try:
                            rows.append({"strike": float(p[0]), "right": p[1], "exp": p[2],
                                         "oi": float(p[6]), "gamma": float(p[-1]) if len(p)>9 else 0})
                        except: pass
            if not rows or not spot:
                return JSONResponse({"sym": s, "error": "sin chain"}, status_code=404)
            decay = gex_core.gamma_by_expiry(rows, spot)
            # el widget espera lista ordenada [{dte, gamma}] (gdecayDraw hace d.slice)
            return JSONResponse([{"dte": k, "gamma": v} for k, v in sorted(decay.items())])
        except Exception as e:
            return JSONResponse({"sym": s, "error": str(e)}, status_code=500)

    @app.get("/api/order_verdict")
    async def order_verdict_route(sym: str = "", since: int = 0, window: int = 180000):
        v = order_verdict(sym, int(since), int(window))
        if v is None:
            return JSONResponse({"error": "faltan sym o since(ms>0)"}, status_code=400)
        return JSONResponse(v)

    @app.get("/health")
    async def health():
        def _one(st):
            lv = st.levels or {}
            spot = st.bars[-1][4] if st.bars else None
            rng = chain_strike_range(lv)
            return {"sym": st.sym, "bars": len(st.bars), "clients": len(st.clients),
                    "tf": st.tf, "spot": spot,
                    "realtime_source": st._rt_source,
                    "realtime_age_s": (round(time.time() - st._rt_tick_epoch, 3)
                                       if st._rt_tick_epoch else None),
                    "call_wall": lv.get("call_wall"), "put_wall": lv.get("put_wall"),
                    "flip": lv.get("flip"), "profile_strikes": len(lv.get("profile") or []),
                    "chain_strikes": list(rng) if rng else None,
                    "walls_unavailable": walls_status(lv, spot)}
        out = _one(state)
        out.update(mock=state.mock, mock_dir=MOCK_DIR, signal_only=True,
                   states={s: _one(st) for s, st in STATES.items()})
        return out

    @app.websocket("/stream")
    async def stream(ws: WebSocket):
        if not local_websocket_origin(ws.headers.get("origin")):
            await ws.close(code=1008, reason="origin no permitido")
            return
        await ws.accept()
        # CADA CONEXION VIVE EN SU PROPIO ESTADO (Yunior 2026-07-25: "when changing
        # symbol in one graph the other graphs change too, they should be independent
        # entirely"). `state` es solo el estado PRIMARIO = el simbolo con el que
        # arranco el bridge; al cambiar de ticker esta conexion se MUEVE a otro State.
        st = state
        st.clients.add(ws)
        try:
            # frame de historia inmediato (setData once en el cliente), al tf actual
            await ws.send_json(history_frame(agg_view_bars(st), st.levels, st.tf, nodata=st._nodata_reason, mock=st.mock, sym=st.sym))
            # watchlist (fleet + usuario), zonas 0DTE del símbolo y flecha direccional
            await ws.send_json(watchlist_payload())
            await ws.send_json(zones_frame(st))
            if any(z.get("exec") for z in st.zones):
                await ws.send_json({"type": "engine", "sym": st.sym.upper(),
                                    "rows": engine_state(st.sym)})
            await broadcast_direction(st)
            uw0, _ = uw_tape_frame()
            if uw0:
                await ws.send_json(uw0)
            await ws.send_json(liq_frame(st.sym)[0])   # liquidez VPVR/KDE (contexto, no gatillo)
            await ws.send_json(liq_map_frame(st.sym)[0])   # mapa liquidez (widget)
            while True:
                # drenamos pings/close + controles del cliente (cambio de timeframe)
                txt = await ws.receive_text()
                try:
                    ctl = json.loads(txt)
                except Exception:
                    continue
                if isinstance(ctl, dict) and ctl.get("cmd") == "tf":
                    await set_timeframe(st, ctl.get("tf", st.tf))
                    # re-emite un frame de historia FRESCO al tf pedido
                    await ws.send_json(history_frame(agg_view_bars(st), st.levels, st.tf, nodata=st._nodata_reason, mock=st.mock, sym=st.sym))
                elif isinstance(ctl, dict) and ctl.get("cmd") == "more":
                    # pan-scroll hacia atrás: request aparte, keepUpToDate=False, nunca
                    # bloquea el tick vivo (corre en su propia corrutina de broadcast).
                    got = await fetch_more_history(st, ctl.get("before"))
                    await ws.send_json(history_frame(agg_view_bars(st), st.levels, st.tf,
                                        nodata=st._nodata_reason, mock=st.mock,
                                        kind="backfill", exhausted=not got,
                                        exhausted_reason=st._backfill_reason, sym=st.sym))
                elif isinstance(ctl, dict) and ctl.get("cmd") == "sym":
                    # NO se muta el estado compartido: se MUEVE esta conexión al State del
                    # nuevo símbolo (creándolo si no existe). Las demás ventanas ni se
                    # enteran — que era justo el fallo: una cambiaba de ticker y las otras
                    # se quedaban con sus velas y los niveles del ticker ajeno (escala de
                    # precios reventada, medido con 6 ventanas el 2026-07-25).
                    want = (ctl.get("sym") or st.sym).strip().lower()
                    if want and want != st.sym:
                        st.clients.discard(ws)
                        reap_state(st)
                        st = get_state(want)
                        st.clients.add(ws)
                    await ws.send_json(history_frame(agg_view_bars(st), st.levels, st.tf, nodata=st._nodata_reason, mock=st.mock, sym=st.sym))
                    # zonas del nuevo símbolo + flecha direccional (actualización inmediata)
                    await ws.send_json(zones_frame(st))
                    await ws.send_json(liq_frame(st.sym)[0])   # liquidez del nuevo símbolo
                    await ws.send_json(liq_map_frame(st.sym)[0])
                    await broadcast_direction(st)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "scope":
                    st.all_exp = (ctl.get("scope") == "ALL")   # 0DTE <-> ALL-EXP
                    sp = st.bars[-1][4] if st.bars else None
                    st.levels = chart_levels.gen(st.sym, spot=sp, write=False, all_exp=st.all_exp) or st.levels
                    await broadcast_levels(st)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "narrate":
                    if "on" in ctl:
                        st._narr_on = bool(ctl["on"])
                    if ctl.get("force"):
                        st._narr_force = True
                    if st._narr_on:
                        # respuesta inmediata (determinista) + AI si se forzó
                        await narrator_tick(st)
                    else:
                        await broadcast_narr(st)   # confirma OFF al cliente
                elif isinstance(ctl, dict) and ctl.get("cmd") == "alarm":
                    # alarma manual estilo TradingView: la escribe en ~/Desktop/price-alerts.txt
                    # (price_alarm C++ la relee cada 1s -> sirena+voz+registro). SEÑAL-SOLAMENTE.
                    act = ctl.get("act", "add")
                    sp = st.bars[-1][4] if st.bars else None
                    if act == "add":
                        price = ctl.get("price")
                        direction = ctl.get("dir") or ("up" if (sp and price and price >= sp) else "down")
                        if price:
                            alarm_add(st.sym, float(price), direction, exp=ctl.get("exp"))
                    elif act == "del":
                        alarm_remove(st.sym, ctl.get("price"))
                    await ws.send_json({"type": "alarms", "sym": st.sym.upper(),
                                        "alarms": alarm_list(st.sym)})
                elif isinstance(ctl, dict) and ctl.get("cmd") == "watchlist":
                    # watchlist buscable/expandible: add (cualifica en LIVE) / del / list.
                    act = ctl.get("act", "list")
                    if act == "add":
                        s = (ctl.get("sym") or "").strip().upper()
                        if s:
                            ok, why = await qualify_watchlist_sym(st, s)
                            if ok:
                                _watchlist_file_add(s)
                            else:
                                print(f"[watchlist] RECHAZADO {s}: {why}")
                                await ws.send_json({"type": "watchlist_reject",
                                                    "sym": s, "why": why})
                    elif act == "del":
                        _watchlist_file_del((ctl.get("sym") or "").strip().upper())
                    await ws.send_json(watchlist_payload())
                elif isinstance(ctl, dict) and ctl.get("cmd") == "zone":
                    # ZONA de ejecución (buy/sell call/put + exp/qty/exec/stop). El chart SÓLO
                    # PRODUCE exec_zones_<sym>.json; el order_engine C++ lo CONSUME. Aquí jamás
                    # se coloca una orden. exec=false = ficha-only (señal). SEÑAL-SOLAMENTE.
                    act = ctl.get("act", "list")
                    if act == "add" and ctl.get("price") is not None:
                        confirmed_exec = False
                        if ctl.get("exec") is True:
                            confirmed_exec, why = consume_new_arm_confirmation(
                                st.sym, ctl, ctl.get("confirmation_token"),
                                ctl.get("human_confirmed"))
                            if not confirmed_exec:
                                await ws.send_json({"type": "order_confirmation", "ok": False,
                                                    "err": why})
                        if ctl.get("exec") is not True or confirmed_exec:
                            st.zones = zone_add(
                                st.sym, ctl.get("price"), ctl.get("side"), ctl.get("kind"),
                                exp=ctl.get("exp"), qty=ctl.get("qty") or 1,
                                instrument=ctl.get("instrument") or "opt",
                                confirmed_exec=confirmed_exec,
                                overnight_gap_ack=ctl.get("overnight_gap_ack") is True,
                                reviewed_strike=ctl.get("strike"),
                                reviewed_right=ctl.get("right"),
                                reviewed_limit=ctl.get("reviewed_limit"))
                    elif act == "del":
                        st.zones = zone_del(st.sym, price=ctl.get("price"), zid=ctl.get("id"))
                    elif act == "set" and ctl.get("id"):
                        # set exp/qty/exec/price/stop en una zona existente (arrastre del stop,
                        # armado exec, cambio de expiry...) -> persiste el contrato del motor.
                        allow = True
                        if ctl.get("exec") is True:
                            allow, why = consume_arm_confirmation(
                                st.sym, ctl.get("id"), ctl.get("confirmation_token"),
                                ctl.get("human_confirmed"), ctl)
                            if not allow:
                                await ws.send_json({"type": "order_confirmation", "ok": False,
                                                    "err": why, "id": ctl.get("id")})
                        if allow:
                            st.zones = zone_update(
                                st.sym, ctl.get("id"),
                            exp=ctl.get("exp"), qty=ctl.get("qty"), exec=ctl.get("exec"),
                            price=ctl.get("price"), stop_px=ctl.get("stop_px"),
                            stop_on=ctl.get("stop_on"), stop_native=ctl.get("stop_native"),
                            overnight_gap_ack=ctl.get("overnight_gap_ack"),
                            locked_strike=ctl.get("strike"), locked_right=ctl.get("right"),
                            reviewed_limit=ctl.get("reviewed_limit"))
                    else:
                        st.zones = zones_load(st.sym)
                    await ws.send_json(zones_frame(st))
                    if any(z.get("exec") for z in st.zones):
                        await broadcast_engine(st)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "optquote":
                    # previsualización TradingView-like del contrato (strike + bid/ask C/P) al
                    # precio y expiry elegidos en el popup de zona. Sólo LECTURA del cache.
                    q = chain_quote(st.sym, ctl.get("price"), ctl.get("exp"))
                    q.update({"type": "optquote", "sym": st.sym.upper(),
                              "price": ctl.get("price")})
                    await ws.send_json(q)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "quick_order":
                    # Un toque = orden real (orden de Yunior 2026-07-29). El bridge cotiza
                    # y ENCOLA; ejecuta el motor con doble llave. Cualquier acción; opciones
                    # del universo con cadena local.
                    qr = await quick_order(ctl.get("sym") or st.sym, ctl)
                    await ws.send_json(qr)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "order_preflight":
                    # Ticket de revisión únicamente: normaliza contrato/límite/sesión y expone
                    # guardas. No escribe zona/comando y jamás toca IBKR.
                    pf = order_preflight(ctl.get("sym") or st.sym, ctl)
                    if pf.get("ok") and ctl.get("purpose") in ("arm", "arm_new"):
                        if ctl.get("purpose") == "arm":
                            token, why = issue_arm_confirmation(st.sym, ctl.get("zone_id"), pf)
                        else:
                            token, why = issue_new_arm_confirmation(st.sym, pf), None
                        if not token:
                            pf["ok"] = pf["can_prepare"] = False
                            pf.setdefault("errors", []).append(why)
                        else:
                            pf["confirmation_token"] = token
                            pf["confirmation_expires_s"] = _ARM_CONFIRM_TTL_S
                    await ws.send_json(pf)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "prob":
                    # probabilidad de profit (order_engine/prob_profit.py, otro agente) -> chip.
                    # Sólo cómputo de probabilidad; NUNCA coloca órdenes. SEÑAL-SOLAMENTE.
                    res = run_prob(st.sym, ctl.get("price") if ctl.get("price") is not None
                                   else ctl.get("level"),
                                   ctl.get("side") or "buy", ctl.get("kind") or "call",
                                   ctl.get("exp"))
                    res.update({"type": "prob", "sym": st.sym.upper(), "id": ctl.get("id")})
                    await ws.send_json(res)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "ticket":
                    # ficha 0DTE bajo demanda (order_ticket.build) -> tarjeta en el chart.
                    # PREPARA la orden; el HUMANO la ejecuta en IBKR. SEÑAL-SOLAMENTE.
                    t = build_ticket(ctl.get("sym") or st.sym, ctl.get("price"),
                                     ctl.get("side"), ctl.get("kind"))
                    await ws.send_json({"type": "ticket", "sym": st.sym.upper(), "t": t})
                elif isinstance(ctl, dict) and ctl.get("cmd") == "ibmode":
                    # switcher PAPER<->LIVE (fuente única data/ib_mode.txt). Solo cambia el
                    # modo; el motor y los lectores toman el puerto de ahí. NUNCA ordena aquí.
                    if ctl.get("act") == "set" and ctl.get("mode") in ("paper", "live"):
                        try:
                            ib_mode.set_mode(ctl.get("mode"))
                            # reinicia el lector de cadena para que reconecte al nuevo puerto
                            subprocess.run(["pkill", "-f", "opt_chain_cache.py"],
                                           capture_output=True)
                        except Exception:
                            pass
                    await ws.send_json(ib_mode_status())
                elif isinstance(ctl, dict) and ctl.get("cmd") == "whale_cfg":
                    # panel de ballenas: carril rapido (<=5 tickers) + filtro CALLS/PUTS/BOTH por
                    # ticker. opt_whale_watch.py relee data/whale_priority.txt y
                    # data/whale_alert_filter.txt cada ciclo (~5min), sin reiniciar el proceso.
                    if ctl.get("act") == "set":
                        pr = [s.strip().upper() for s in (ctl.get("priority") or [])
                              if isinstance(s, str) and s.strip()][:5]
                        _atomic_write(_WHALE_PRIORITY_F, " ".join(pr))
                        filt = ctl.get("filters") or {}
                        filt_lines = [f"{str(k).upper()} {str(v).upper()}" for k, v in filt.items()
                                      if isinstance(v, str) and v.upper() in ("CALLS", "PUTS", "BOTH")]
                        _atomic_write(_WHALE_FILTER_F, "\n".join(filt_lines))
                    await ws.send_json(whale_cfg_status())
                elif isinstance(ctl, dict) and ctl.get("cmd") == "account":
                    # posiciones + órdenes + balance del MODO actual (readonly).
                    await ws.send_json(await account_snapshot())
                elif isinstance(ctl, dict) and ctl.get("cmd") == "order_action":
                    # cancel/sell/modify -> RUTEA al order_engine (único autorizado). El bridge
                    # solo escribe el comando; el motor C++ lo ejecuta con su doble llave.
                    await ws.send_json(route_order_action(ctl))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            st.clients.discard(ws)
            reap_state(st)   # estado secundario sin clientes -> se apaga y libera TWS

    return app


async def broadcast_tick(state):
    """Empuja SOLO la última vela (precio vivo por tick) -> el cliente hace series.update()
    O(1), render instantáneo. Blazing-fast: el precio se mueve sub-segundo, sin esperar la
    barra de IBKR (~5s). SEÑAL-SOLAMENTE."""
    if not state.clients:
        return
    view = agg_view_bars(state)
    if not view:
        return
    b = view[-1]
    frame = {"type": "tick", "bar": {"time": b[0], "open": b[1], "high": b[2],
                                     "low": b[3], "close": b[4]}}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


def _make_on_tick(state):
    """Callback de reqMktData: actualiza la vela EN FORMACIÓN (close/high/low) con el último
    precio y la emite (throttle ~8/s). El precio se ve moverse en vivo entre barras."""
    def on_pending(tickers):
        want = state.sym.upper()
        tk = None
        for t in tickers:
            ct = getattr(t, "contract", None)
            if ct and getattr(ct, "symbol", None) == want and getattr(ct, "secType", None) == "STK":
                tk = t
                break
        if tk is None or not state.bars:
            return
        px = tk.last if (tk.last is not None and tk.last == tk.last and tk.last > 0) else tk.marketPrice()
        if not px or px != px or px <= 0:
            return
        now = time.time()
        state._last_tick_ts = now
        state._rt_source = "ibkr"
        state._rt_tick_epoch = now
        # sub congelada (20:00 ET) pero ticks vivos -> las velas nuevas se abren desde el
        # tick (unica fuente sub-minuto overnight; sin volumen). En sesion no interviene.
        step = state._agg_step or TF_S.get(state.tf)
        if step:
            bucket = int(now) - int(now) % step
            if bucket > state.bars[-1][0]:
                if now - state._last_sub_ts > STALE_SUB_S:
                    state.bars.append([bucket, px, px, px, px, 0.0])
                else:
                    # tick de un bucket FUTURO con sub aun viva/en warmup: jamas ensuciar
                    # una vela vieja con el precio de ahora (velon 19:59->overnight)
                    return
        b = state.bars[-1]
        b[4] = px
        if px > b[2]:
            b[2] = px
        if px < b[3]:
            b[3] = px
        if now - state._last_tick_bcast < 0.12:
            return
        state._last_tick_bcast = now
        asyncio.ensure_future(broadcast_tick(state))
        # flecha-BRUJULA en TIEMPO REAL. El throttle era de 2.0 s cuando esto CALCULABA en
        # Python (100-180 ms/simbolo). Ahora solo LEE data/compass_<sym>.json (microsegundos),
        # asi que baja a 0.2 s: el retraso de la flecha lo fija el bucle de ./compass, no esto.
        # "Si la flecha apunta con retraso de 2 segundos y compramos call en el retroceso
        # cuando esta en su punto maximo, no bueno" (Yunior 2026-07-25).
        if now - getattr(state, "_last_dir_bcast", 0) >= DIR_BCAST_S:
            state._last_dir_bcast = now
            asyncio.ensure_future(broadcast_direction(state))
    return on_pending


SEND_TIMEOUT_S = 5.0    # un cliente que no lee NO puede parar el puente


async def broadcast(state):
    """Empuja el frame incremental a todos los clientes WS conectados."""
    if not state.clients:
        return
    view = agg_view_bars(state)
    if not view:
        return
    frame = bar_frame(view, state.levels, state.tf, sym=state.sym)
    dead = []
    for ws in list(state.clients):
        try:
            # con timeout: un navegador que deja de leer aplica backpressure y `send_json`
            # se queda esperando para siempre. Medido: una pestaña de Chrome abierta dejaba
            # el puente sin responder ni a /health, y al cerrarla revivia.
            await asyncio.wait_for(ws.send_json(frame), timeout=SEND_TIMEOUT_S)
        except asyncio.TimeoutError:
            print(f"[ws] cliente lento en {state.sym}: se descarta (>{SEND_TIMEOUT_S}s)")
            dead.append(ws)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.clients.discard(ws)


LEVELS_REFRESH_S = 15   # recomputa GEX/flip/muros al SPOT VIVO cada N segundos


async def broadcast_levels(state):
    """Empuja SOLO los niveles (GEX/flip/muros) a los clientes -> redibujo inmediato
    sin esperar a la próxima barra."""
    if not state.clients:
        return
    frame = {"type": "levels", "tf": state.tf, "levels": state.levels or {}}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


NARR_AI_MIN_S = 90   # throttle: mínimo N segundos entre llamadas a DeepSeek (thrift)


async def broadcast_narr(state):
    if not state.clients:
        return
    frame = {"type": "narrator", "text": state._narr_text, "src": state._narr_src,
             "on": state._narr_on, "asof": int(time.time())}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


async def broadcast_signals(state):
    """Empuja los marcadores de señales/notificaciones al chart (refresco en vivo para
    el debug visual de Yunior)."""
    if not state.clients:
        return
    mk = load_signal_markers(state.sym, state.bars)
    ops = load_engine_ops(state.sym, state.bars)
    frame = {"type": "signals", "sym": state.sym.upper(), "signals": mk, "engineOps": ops}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


def _session_open(sym):
    """Sesion del simbolo ABIERTA. Espejos de krx_market (korea_bar_bridge.py:157, no
    importable aqui: trae ib_insync) y de RTH US 9:30-16:00 ET (Toronto == ET)."""
    if sym.upper() in KOREA_SYMS():
        lt = time.gmtime(time.time() + 9 * 3600)
        return lt.tm_wday < 5 and (9, 0) <= (lt.tm_hour, lt.tm_min) <= (15, 30)
    lt = time.localtime()
    hm = lt.tm_hour * 100 + lt.tm_min
    return lt.tm_wday < 5 and 930 <= hm < 1600


_STRUCT_LAST = os.path.join(REPO, "data", "struct_last.json")


def _struct_already(sym, key, ttl=14400):
    """El cooldown vivia solo en memoria: reiniciar los bridges RE-CANTABA el ultimo iman
    (AAPL/MSFT 00:37 despertaron a Yunior). Persistido en disco, el restart calla."""
    try:
        e = json.load(open(_STRUCT_LAST)).get(sym.upper())
        return bool(e) and e.get("key") == key and time.time() - e.get("ts", 0) < ttl
    except Exception:
        return False


def _struct_remember(sym, key):
    try:
        d = json.load(open(_STRUCT_LAST))
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    d[sym.upper()] = {"key": key, "ts": time.time()}
    try:
        tmp = _STRUCT_LAST + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, _STRUCT_LAST)
    except Exception as e:
        print(f"[struct] persist cooldown falló ({e})")


def _log_structural(state, sig, key=None):
    """Guarda la señal estructural en trades.db (source='structural') para el backtest EOD.
    Dedup por firma. SEÑAL-SOLAMENTE.

    GUARDA DE INTEGRIDAD DE MUESTRA (2026-07-25). Esta funcion escribe a DOS destinos de
    PRODUCCION: la tabla `signals` (poblacion del backtest) y `data/trading-signals/<fecha>.txt`
    (canal de voz/telefono via notify_relay.sh). Lo hacia SIN mirar si el bridge corria en
    modo de pruebas.

    Medido hoy: de las 89 filas `source='structural'` de la BD, **7 eran de un sabado con el
    mercado CERRADO** — 4 de QQQ con el precio congelado en 694.0 repetido, y 3 de NVDA
    girando ↑34% -> pin -> ↓67% en 30 segundos. Un 8% de la poblacion entera, y `structural`
    es precisamente la fuente que medimos con WR alto sobre n=5. Un backtest no puede
    etiquetar una señal emitida con el mercado cerrado: no hay retorno futuro que medir, asi
    que la etiqueta que salga es ficcion.

    En `--mock` no se escribe NADA a produccion: se imprime y se sale. Probar la UI es
    obligatorio (asi se verifica el chart sin TWS) y no puede costar contaminar la muestra
    ni hacer sonar el telefono."""
    if getattr(state, "mock", False):
        print(f"[struct] MOCK: NO se registra en produccion -> {sig.get('kind','')} "
              f"{sig.get('sym','')} {sig.get('text','')}")
        return
    # FUERA DE SESION (RTH US / KRX Corea) NO se registra ni canta: el mapa GEX es del
    # cierre y la etiqueta del backtest seria ficcion (2026-07-28 00:37: AAPL/MSFT iman
    # nocturno con voz — WR30 27% n=67, la peor fuente, y encima con mercado cerrado).
    if not _session_open(state.sym):
        print(f"[struct] fuera de sesión {state.sym.upper()}: banner sin registro -> {sig.get('text','')}")
        return
    if key and _struct_already(state.sym, key):
        return
    try:
        import sqlite3
        prob = f" · prob {sig['prob']}% (estructural, no WR medido)" if sig.get("prob") else ""
        msg = f"{sig['text']}{prob}"
        c = sqlite3.connect(os.path.join(REPO, "data", "trades.db"), timeout=3)
        c.execute("PRAGMA busy_timeout=3000")
        c.execute("""INSERT OR IGNORE INTO signals
            (ts_epoch,ts_txt,date,kind,symbol,price,priority,source,msg,raw)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), time.strftime("%H:%M:%S"), time.strftime("%Y-%m-%d"),
             f"🧲 ESTRUCTURAL {sig.get('kind','')}", sig["sym"].upper(), sig.get("price"),
             "SIGNAL", "structural", msg, msg))
        c.commit(); c.close()
        # AL ARCHIVO TAMBIEN (fix 2026-07-24): antes esto SOLO tocaba la BD, asi que
        # las ~77 señales estructurales del dia no llegaban a NINGUN canal — ni voz,
        # ni telefono. notify_relay.sh ya filtra por 🧲, pero nunca las veia porque
        # nadie las escribia en data/trading-signals/<fecha>.txt.
        # prob < SPEAK_MIN (regla should_speak): BD si (poblacion del backtest), voz NO.
        p = sig.get("prob")
        if p is not None and p >= signal_conditioning.SPEAK_MIN:
            try:
                d = time.strftime("%Y-%m-%d")
                path = os.path.join(REPO, "data", "trading-signals", f"{d}.txt")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a") as f:
                    f.write(f"{time.strftime('%H:%M:%S')} | 🧲 ESTRUCTURAL {sig.get('kind','')} "
                            f"{sig['sym'].upper()} | {msg}\n")
            except Exception as e2:
                print(f"[struct] signals-file falló ({e2})")
        else:
            print(f"[struct] prob {p} < {signal_conditioning.SPEAK_MIN:g}: BD sin voz -> {sig.get('text','')}")
        if key:
            _struct_remember(state.sym, key)
    except Exception as e:
        print(f"[struct] log falló ({e})")


async def structural_tick(state):
    """Genera la señal estructural (imán/flip) y la empuja al chart; la guarda en BD si cambió."""
    lv = state.levels or {}
    if not lv:
        return
    sig = narrator.structural_signal(lv, state.bars)
    # SANITY: iman a mas de ~1 EM del spot = nivel viejo/basura (MSFT 390 con iman 430 =
    # 10%!). Ni se pinta ni se canta: None limpia el pill.
    if sig and sig.get("price") is not None and state.bars:
        spot = state.bars[-1][4]
        lim = lv.get("em") or (spot * 0.02 if spot else None)
        if spot and lim and abs(sig["price"] - spot) > lim:
            print(f"[struct] iman {sig['price']} a {abs(sig['price']-spot):.1f} del spot "
                  f"{spot:.1f} (> EM {lim:.1f}): descartado")
            sig = None
    state._struct = sig
    frame = {"type": "structural", "sym": state.sym.upper(), "sig": sig}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)
    if sig:
        key = f"{sig['sym']}|{sig['kind']}|{sig.get('price')}|{sig['dir']}"
        if key != state._struct_key:
            state._struct_key = key
            _log_structural(state, sig, key)


async def narrator_tick(state):
    """Actualiza el narrador tras cada refresh de niveles. Capa DETERMINISTA siempre (gratis).
    DeepSeek SOLO si (a) el usuario forzó ↻, o (b) cambió el estado material Y pasó el throttle.
    Corre urllib en un hilo para no bloquear el event loop. SEÑAL-SOLAMENTE."""
    if not state._narr_on:
        return
    lv = state.levels or {}
    if not lv:
        return
    det = narrator.deterministic(lv, state.bars)
    key = narrator.trigger_key(lv)
    now = time.time()
    want_ai = state._narr_force or (key != state._narr_key and (now - state._narr_ai_ts) >= NARR_AI_MIN_S)
    changed = det != state._narr_text
    if want_ai:
        state._narr_ai_ts = now
        state._narr_force = False
        state._narr_key = key
        ai = await asyncio.to_thread(narrator.deepseek, lv, state.bars, state._narr_text)
        if ai:
            state._narr_text = ai; state._narr_src = "ai"
            await broadcast_narr(state)
            return
        # AI falló -> caemos al determinista
    if changed or want_ai:
        state._narr_text = det; state._narr_src = "det"
        state._narr_key = key
        await broadcast_narr(state)


async def levels_loop(state):
    """REAL TIME de GEX/flip/muros: cada LEVELS_REFRESH_S recalcula al SPOT VIVO (última
    barra) desde el cache de opciones (OI/gamma lento; el flip y los muros se DESPLAZAN
    con el precio) y lo empuja al chart. SEÑAL-SOLAMENTE (solo lee cache + calcula)."""
    while True:
        await asyncio.sleep(LEVELS_REFRESH_S)
        try:
            spot = state.bars[-1][4] if state.bars else None
            if not spot:
                continue
            # --mock-dir: el mapa lo regenera ./replay al avanzar su reloj virtual; aquí solo
            # se re-lee (gen() con el reloj de hoy daría la cadena histórica por expirada).
            lv = (load_sandbox_levels(state.sym) if MOCK_DIR else
                  chart_levels.gen(state.sym, spot=spot, write=False, all_exp=state.all_exp))
            why = walls_status(lv, spot)
            if why != state.walls_why:
                state.walls_why = why
                print(f"[levels] {state.sym.upper()} muros: "
                      + (f"NO DISPONIBLES ({why}) spot={spot}" if why else "con números"))
            if lv:
                lv["asof"] = int(time.time())   # asof fresco -> el cliente redibuja
                if state._vix_ticker is not None:
                    try:
                        t = state._vix_ticker
                        v = t.marketPrice()
                        # marketPrice() retiene el ULTIMO tick: fuera de sesion el VIX no
                        # tickea y ese numero es de las 16:15 — sin mirar la EDAD del tick
                        # se marcaba vivo toda la noche. Vivo = tick de <10 min.
                        tt = getattr(t, "time", None)
                        tick_fresh = tt is not None and (time.time() - tt.timestamp()) < 600
                        if v and v == v and v > 0 and tick_fresh:
                            state._vix, state._vix_live = round(v, 2), True
                        else:
                            # premarket/overnight: sin tick fresco todo es CIERRE (marcado).
                            c = v if (v and v == v and v > 0) else getattr(t, "close", None)
                            if c and c == c and c > 0:
                                state._vix, state._vix_live = round(c, 2), False
                    except Exception:
                        pass
                if state._vix is not None:
                    lv["vix"] = state._vix
                    lv["vix_live"] = state._vix_live
                    persist_vix(state._vix, state._vix_live)   # -> data/vix.json para compass.cpp
                state.levels = lv
                await broadcast_levels(state)
                await narrator_tick(state)
                await structural_tick(state)   # señal imán/flip -> chart + BD
                await broadcast_signals(state)  # refresca marcadores (debug visual)
                await check_zone_crossings(state, spot)   # ZONAS ficha-only -> ficha al cruzar
                if any(z.get("exec") for z in state.zones):
                    await broadcast_engine(state)         # estado del motor para zonas ARMADAS
                await broadcast_direction(state, lv=lv)   # flecha direccional compuesta
                await broadcast_watchlist(state)          # quotes watchlist (último/%día/vol)
        except Exception as e:
            print(f"[levels] refresh falló ({e})")


# ============================== feed MOCK (offline) ==========================
def _mock_load(sym, warm_default=260):
    """Carga SINCRONA (archivo local, sin TWS) de la historia mock de un simbolo: sandbox de
    replay si hay --mock-dir, si no el CSV bars3mo5m. Devuelve (all_bars, warm, reason) donde
    reason != None solo cuando NO hay dato real disponible (sandbox sin barras para ese sym).
    Compartida por get_state (carga instantanea, sin carrera con el primer history_frame) y
    mock_feed (arranque + streaming)."""
    if MOCK_DIR:
        all_bars = load_sandbox_bars(sym)
        if not all_bars:
            return [], 0, (f"sandbox sin barras para {sym.upper()} "
                            f"({MOCK_DIR}/data/bars_{sym}_ibkr.txt)")
        # el sandbox se reproduce por el FINAL: la cadena que publicó el replay es la del
        # último instante, así que un warm corto dejaría el spot lejos del libro otra vez.
        warm = max(1, len(all_bars) - 20)
        return all_bars, warm, None
    all_bars = load_csv_bars(sym)
    if not all_bars:
        all_bars = _synthetic_bars(sym, 400)
    warm = min(warm_default, max(1, len(all_bars) - 20))
    return all_bars, warm, None


async def mock_feed(state, interval=1.0, warm=260):
    """Prueba TODO el pipe sin TWS: la historia ya la puso _prime_bars (sincrono, sin carrera);
    aqui solo streamea el resto una a una cada `interval`s (simula el tick de barra nueva)."""
    all_bars, warm, reason = _mock_load(state.sym, warm_default=warm)
    if reason:
        state._nodata_reason = reason
        print(f"[mock] FATAL: {reason}")
        return
    if not state.bars:   # _prime_bars ya pudo haberla cargado; no pisar/duplicar log
        state.set_bars(all_bars[:warm])
    state._nodata_reason = None
    print(f"[mock] {state.sym}: historia={warm} barras, streaming {len(all_bars)-warm} restantes @ {interval}s")
    idx = warm
    while True:
        if idx >= len(all_bars):
            await asyncio.sleep(interval)
            continue
        state.upsert_bar(all_bars[idx])
        idx += 1
        await broadcast(state)
        await asyncio.sleep(interval)


def _synthetic_bars(sym, n):
    """Random-walk determinista (semilla por sym) para demo sin datos."""
    import random
    rnd = random.Random(sum(ord(c) for c in sym))
    px = 100.0
    t0 = int(time.time()) - n * 300
    out = []
    for i in range(n):
        o = px
        px *= (1 + rnd.uniform(-0.004, 0.004))
        c = px
        h = max(o, c) * (1 + abs(rnd.uniform(0, 0.003)))
        l = min(o, c) * (1 - abs(rnd.uniform(0, 0.003)))
        v = rnd.randint(50000, 500000)
        out.append([t0 + i * 300, round(o, 2), round(h, 2), round(l, 2), round(c, 2), v])
    return out


# ============================== feed LIVE (ib_async) =========================
def _make_on_bar(state):
    """Callback updateEvent: upsert de la última barra + broadcast. Se re-usa al
    cambiar de timeframe (live_reapply lo re-ata a la nueva suscripción).
    Si state._agg_step está activo (tf derivado, ej. 45s) el bar nativo entra al
    buffer crudo y se re-agrega por epoch antes del upsert -> el chart ve 45s, no
    el 15s que llegó de TWS."""
    def on_bar(bars_, has_new):
        state._last_sub_ts = time.time()   # la sub sigue viva (el watchdog de stale lo mira)
        state._rt_source = "ibkr"
        state._rt_tick_epoch = state._last_sub_ts
        b = bars_[-1]
        raw = [int(b.date.timestamp()), b.open, b.high, b.low, b.close, float(b.volume)]
        step = state._agg_step
        if step:
            buf = state._agg_raw
            if buf and buf[-1][0] == raw[0]:
                buf[-1] = raw
            else:
                buf.append(raw)
                if len(buf) > 6000:
                    del buf[:-6000]
            agg = agg_epoch(buf, step)
            if agg:
                state.upsert_bar(agg[-1])
        else:
            state.upsert_bar(raw)
        asyncio.ensure_future(broadcast(state))
    return on_bar


async def live_feed(state, port, client_id=60):
    """Conecta ib_async, pide barras keepUpToDate al tf por defecto y empuja cada
    barra nueva. SEÑAL-SOLAMENTE: solo reqHistoricalData; ninguna ejecución."""
    from ib_async import IB, Stock, util   # 3.10+; fork mantenido de ib_insync

    ib = IB()
    loop = asyncio.get_event_loop()

    async def connect():
        while not ib.isConnected():
            try:
                await asyncio.wait_for(ib.connectAsync("127.0.0.1", port, clientId=client_id), 15)
                print(f"[live] conectado TWS 127.0.0.1:{port} clientId={client_id}")
            except Exception as e:
                print(f"[live] reconnect en 5s ({e})")
                await asyncio.sleep(5)

    await connect()

    def on_disconnect():
        print("[live] desconectado; reintentando…")
        asyncio.ensure_future(connect())

    ib.disconnectedEvent += on_disconnect

    # El arranque pedia SIEMPRE Stock(SMART,USD): con --sym samsung eso es "Unknown contract"
    # y la tarea moria con AttributeError -> _ib nunca se asignaba y el chart decia "conexion
    # TWS no lista" con la conexion perfecta. Los KRX van por conId.
    state._ib = ib
    SHARED_IB["ib"] = ib      # los estados nuevos REUSAN esta conexion
    ib.reqMarketDataType(1)   # REALTIME para TODO
    contract = None
    if state.sym.upper() in KOREA_SYMS():
        await _relive_korea(state, state.sym)
        contract = state._contract
        if contract is None:
            print(f"[live] {state.sym.upper()}: sin contrato KRX; el vivo sigue por archivo")
    else:
        try:
            (contract,) = await asyncio.wait_for(ib.qualifyContractsAsync(
                Stock(state.sym.upper(), "SMART", "USD")), 15)
        except Exception as e:
            print(f"[live] {state.sym.upper()} no cualifica ({e})")
        state._contract = contract
    if contract is None:
        return   # sin contrato no hay suscripcion viva; el archivo/korea_poll_feed cubre
    # TICK STREAM del precio (blazing-fast: la vela se mueve sub-segundo, no cada ~5s)
    try:
        ib.pendingTickersEvent += _make_on_tick(state)
        state._px_ticker = ib.reqMktData(contract, "", False, False)
        print(f"[live] tick stream ON ({state.sym})")
    except Exception as e:
        print(f"[tick] no disponible ({e})")
    # VIX (índice CBOE) — degradación limpia si no hay suscripción de índice
    try:
        from ib_async import Index
        vx = Index("VIX", "CBOE")
        await asyncio.wait_for(ib.qualifyContractsAsync(vx), 15)
        state._vix_ticker = ib.reqMktData(vx, "", False, False)  # solo llena si hay sub CBOE realtime
    except Exception as e:
        print(f"[vix] no disponible ({e})")

    bar_size, dur = LIVE_BAR.get(state.tf, ("1 min", "2 D"))
    bars = await ib.reqHistoricalDataAsync(   # async: NO usar el sync dentro del loop de uvicorn (util.run choca)
        contract, endDateTime="", durationStr=dur, barSizeSetting=bar_size,
        whatToShow="TRADES", useRTH=False, keepUpToDate=True,
    )
    state.set_bars([[int(b.date.timestamp()), b.open, b.high, b.low, b.close, float(b.volume)]
                    for b in bars])
    state._last_sub_ts = time.time()
    print(f"[live] {state.sym}: {len(state.bars)} barras {bar_size} iniciales (tf={state.tf})")

    bars.updateEvent += _make_on_bar(state)
    state._live_sub = bars
    # mantener vivo el loop de ib_async
    while True:
        await asyncio.sleep(3600)


# =============================== arranque servidor ===========================
def build_state_and_feed(args):
    global MOCK
    MOCK = bool(args.mock)   # guarda de integridad: en pruebas no se escribe a produccion
    set_mock_dir(getattr(args, "mock_dir", None))
    sym = resolve_sym(args.sym)
    state = State(sym, mock=args.mock)
    state.levels = load_levels(sym) or {}
    if not args.mock:
        # en modo live las barras iniciales las trae el feed; precarga vacía
        state.set_bars([])
    # registro multi-símbolo: éste es el estado PRIMARIO (nunca se apaga). Los demás
    # los crea get_state() cuando una ventana pide otro ticker.
    STATES.clear()   # el `app` de módulo se construye al importar y deja un estado fantasma
    STATES[sym] = state
    PRIMARY_SYM["sym"] = sym
    STATE_CFG.update(mock=bool(args.mock), interval=float(getattr(args, "interval", 1.0) or 1.0),
                     client_id=int(getattr(args, "client_id", 60) or 60))
    return state


async def _serve(args):
    import uvicorn
    state = build_state_and_feed(args)
    if MOCK_DIR and not load_sandbox_bars(state.sym):
        sys.exit(f"--mock-dir {MOCK_DIR} sin barras para {state.sym.upper()}: "
                 f"lanza ./replay con ese --out y ese símbolo")
    app = create_app(state)
    if args.mock:
        asyncio.ensure_future(mock_feed(state, interval=args.interval))
    else:
        asyncio.ensure_future(live_feed(state, args.port, args.client_id))
        asyncio.ensure_future(us_stale_feed(state))   # anti-congelada 20:00 ET (skip mock/korea)
    asyncio.ensure_future(levels_loop(state))   # GEX/flip/muros en tiempo real
    asyncio.ensure_future(uw_tape_loop())   # cinta de ballenas UW -> wgt-flow
    asyncio.ensure_future(liq_loop())       # liquidez VPVR/KDE -> pricelines (contexto)
    config = uvicorn.Config(app, host=args.host, port=args.http_port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


# módulo-nivel `app` para `uvicorn scripts.chart_bridge:app` (live, defaults de env)
if HAVE_FASTAPI:
    def _app_factory():
        set_mock_dir(os.environ.get("CHART_MOCK_DIR"))
        sym = resolve_sym(os.environ.get("CHART_SYM"))
        state = State(sym, mock=bool(os.environ.get("CHART_MOCK")))
        state.levels = load_levels(sym) or {}
        # registro multi-simbolo: este es el estado PRIMARIO (nunca se apaga)
        STATES[sym] = state
        PRIMARY_SYM["sym"] = sym
        STATE_CFG.update(mock=state.mock,
                         interval=float(os.environ.get("CHART_INTERVAL", "1.0")))
        app = create_app(state)
        port = int(os.environ.get("CHART_TWS_PORT") or ib_mode.get_port())  # sin hardcode: sigue el modo

        @app.on_event("startup")
        async def _start():
            if state.mock:
                asyncio.ensure_future(mock_feed(state, interval=float(os.environ.get("CHART_INTERVAL", "1.0"))))
            else:
                asyncio.ensure_future(live_feed(state, port, int(os.environ.get("CHART_CLIENT_ID", "60"))))
            asyncio.ensure_future(levels_loop(state))   # GEX/flip/muros en tiempo real
            asyncio.ensure_future(uw_tape_loop())   # cinta de ballenas UW -> wgt-flow
            asyncio.ensure_future(liq_loop())       # liquidez VPVR/KDE -> pricelines (contexto)
        return app

    app = _app_factory()
else:
    app = None


# ================================== self-test ================================
def selftest(args):
    """Sin fastapi/TWS: alimenta barras del CSV (o sintéticas), construye el frame de
    historia y unos frames incrementales, y valida que el JSON esté bien formado."""
    assert_signal_only()
    sym = resolve_sym(args.sym)
    print(f"[selftest] sym={sym}")
    bars = load_sandbox_bars(sym, tail=320) if MOCK_DIR else load_csv_bars(sym, tail=320)
    if not bars:
        print("[selftest] sin CSV -> sintéticas")
        bars = _synthetic_bars(sym, 320)
    levels = load_levels(sym) or {}
    print(f"[selftest] muros: {walls_status(levels, bars[-1][4] if bars else None) or 'con números'}")
    print(f"[selftest] barras={len(bars)}  niveles={'sí' if levels else 'no'}"
          + (f" (spot {levels.get('spot')}, regime {levels.get('regime')}, "
             f"CW {levels.get('call_wall')} PW {levels.get('put_wall')} flip {levels.get('flip')})" if levels else ""))

    # historia con todo menos las últimas 3 barras; luego 3 updates
    warm = bars[:-3]
    hf = history_frame(warm, levels, "5m", sym=sym)
    txt = json.dumps(hf)   # debe serializar sin error
    print(f"\n[selftest] HISTORY frame OK — {len(txt)} bytes")
    print(f"[selftest] top-level keys: {sorted(hf.keys())}")
    print(f"[selftest] indicators keys: {sorted(hf['indicators'].keys())}")
    ind = hf["indicators"]
    print(f"[selftest] bars={len(hf['bars'])}  "
          + "  ".join(f"{k}={len(v) if isinstance(v, list) else 'obj'}" for k, v in ind.items()))

    # --- combo_tl: Supertrend + trendlines DEBEN existir ---
    assert isinstance(ind.get("stUp"), list), "falta stUp (array)"
    assert isinstance(ind.get("stDn"), list), "falta stDn (array)"
    assert isinstance(ind.get("trendlines"), dict), "falta trendlines (obj)"
    tl = ind["trendlines"]
    assert "up" in tl and "dn" in tl, "trendlines sin up/dn"
    print(f"[selftest] combo_tl: stUp={len(ind['stUp'])} pts  stDn={len(ind['stDn'])} pts  "
          f"stMarkers={len(ind['stMarkers'])}  trendlines up={'sí' if tl['up'] else 'no'} "
          f"dn={'sí' if tl['dn'] else 'no'}")
    if ind["stUp"]:
        print(f"[selftest] sample stUp[-1]: {json.dumps(ind['stUp'][-1])}")
    if ind["stDn"]:
        print(f"[selftest] sample stDn[-1]: {json.dumps(ind['stDn'][-1])}")
    if tl["up"]:
        print(f"[selftest] sample trendline up: {json.dumps(tl['up'])}")
    b0 = hf["bars"][0]
    print(f"[selftest] sample bar[0]: {json.dumps(b0)}")
    for k in ("sma20", "bbUpper", "vwap", "macd"):
        pts = hf["indicators"][k]
        if pts:
            print(f"[selftest] sample {k}[-1]: {json.dumps(pts[-1])}")
    print(f"[selftest] levels.profile strikes: {len(levels.get('profile', []))}")

    # frames incrementales (tf base 5m)
    st = State(sym, mock=True)
    st.set_bars(list(warm))
    st.levels = levels
    for extra in bars[-3:]:
        st.upsert_bar(extra)
        bf = bar_frame(agg_view_bars(st), st.levels, st.tf, sym=st.sym)
        json.dumps(bf)  # valida
    print(f"\n[selftest] BAR frame OK — keys {sorted(bf.keys())}, "
          f"indicator points {sorted(bf['indicators'].keys())}")
    print(f"[selftest] sample bar update: {json.dumps(bf['bar'])}")
    print(f"[selftest] sample sma20 update: {json.dumps(bf['indicators']['sma20'])}")
    assert bf["indicators"].get("stUp") is not None or bf["indicators"].get("stDn") is not None, \
        "bar_frame sin Supertrend"
    assert isinstance(bf["indicators"].get("trendlines"), dict), "bar_frame sin trendlines"

    # --- tf-switch: simula {cmd:"tf","tf":"15m"} en --mock (agrega 5m -> 15m) ---
    st.tf = "15m"
    view15 = agg_view_bars(st)
    hf15 = history_frame(view15, st.levels, st.tf, mock=st.mock, sym=st.sym)
    json.dumps(hf15)  # valida
    print(f"\n[selftest] TF-SWITCH 5m->15m: base(5m)={len(st.bars)} barras -> "
          f"view(15m)={len(hf15['bars'])} barras  (tf={hf15['tf']})")
    assert hf15["tf"] == "15m" and len(hf15["bars"]) >= 1, "tf-switch history inválido"
    assert len(hf15["bars"]) < len(st.bars), "15m debería tener MENOS barras que 5m"
    assert isinstance(hf15["indicators"].get("trendlines"), dict), "tf-switch sin trendlines"
    print(f"[selftest] TF-SWITCH OK ✓  indicators keys: {sorted(hf15['indicators'].keys())}")

    print("\n[selftest] OK ✓  (frames bien formados; combo_tl + tf-switch; señal-solamente verificado)")


# ==================================== main ===================================
def main():
    ap = argparse.ArgumentParser(description="ib-trader realtime chart bridge (signal-only)")
    ap.add_argument("--sym", default=None, help="ticker (default: data/focus_ticker o nvda)")
    ap.add_argument("--port", type=int, default=(int(os.environ.get("CHART_TWS_PORT") or ib_mode.get_port())),
                    help="puerto TWS (default: data/ib_mode.txt — 7497 paper / 7496 live)")
    ap.add_argument("--http-port", type=int, default=8080, help="puerto HTTP/WS del chart")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--client-id", type=int, default=60, help="clientId IBKR (60 libre)")
    ap.add_argument("--interval", type=float, default=1.0, help="seg entre barras en --mock")
    ap.add_argument("--mock", action="store_true", help="feed offline desde CSV (sin TWS)")
    ap.add_argument("--mock-dir", default=None,
                    help="sandbox de ./replay (--out): barras 1m + cadena + niveles COHERENTES")
    ap.add_argument("--selftest", action="store_true", help="valida frames sin fastapi/TWS")
    args = ap.parse_args()
    _ACCT_CID["v"] = 6300 + int(args.http_port) % 100   # único por ventana (8080->6380...)

    set_mock_dir(args.mock_dir)
    if args.mock_dir and not (args.mock or args.selftest):
        sys.exit("--mock-dir exige --mock (es la fuente del feed offline)")

    assert_signal_only()

    if args.selftest:
        selftest(args)
        return

    if not HAVE_FASTAPI:
        print("ERROR: fastapi/uvicorn no instalados (venv 3.9). Crea venv-chart 3.10+:\n"
              "  python3.11 -m venv venv-chart && ./venv-chart/bin/pip install ib_async fastapi uvicorn\n"
              "  ./venv-chart/bin/python scripts/chart_bridge.py --mock --sym nvda\n"
              "O corre el validador offline:  python3 scripts/chart_bridge.py --selftest --sym nvda")
        sys.exit(2)

    # --http-port es el del navegador (WS/HTTP); --port es el de TWS
    asyncio.run(_serve(args))


if __name__ == "__main__":
    main()
