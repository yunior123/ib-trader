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
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)

# --- reuso de la matematica de los engines (paridad con backtests) ---
import confluence_engine as ce   # sma, stdev, ema_series (causales, población ÷N)
import chart_levels              # gen(sym) -> charts/data/levels_<sym>.json
import narrator                  # narrador de mercado: determinista (gratis) + DeepSeek
import order_ticket              # ficha 0DTE lista para el HUMANO (build); SEÑAL-SOLAMENTE
import direction_view            # sesgo direccional compuesto (flecha overlay); SEÑAL-SOLAMENTE
import ib_mode                   # fuente única paper/live (data/ib_mode.txt) — sin puertos hardcodeados

# NOTA: importar confluence_engine hace os.chdir(REPO) (efecto de modulo). Reforzamos.
os.chdir(REPO)

LEVELS_DIR = os.path.join(REPO, "charts", "data")
LIVE_HTML = os.path.join(REPO, "charts", "live.html")
DEFAULT_SYM = "nvda"

# --- timeframes (TradingView-like) ---------------------------------------
# MOCK: la base del CSV es 5m; agregamos hacia arriba. "1m" no tiene fuente
# offline -> cae a 5m (con nota en consola). LIVE: se re-pide reqHistoricalData
# con el barSize nativo (ver live_reapply).
# IBKR barSizes VALIDOS: 1/5/10/15/20/30 min · 1/2/3/4/8 hour · 1 day/week/month.
# 45m NO existe en IBKR -> se OMITE (usariamos 15m nativo agregado, complica). Se añade
# 20m que SI es nativo. Todos los nuevos tienen barSize nativo -> LIVE limpio; en MOCK
# se agregan desde la base 5m (ce.aggregate, cualquier multiplo).
TF_LIST = ("1m", "5m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "1d", "1W", "1M")
TF_MIN = {"1m": 5, "5m": 5, "15m": 15, "20m": 20, "30m": 30, "1h": 60,
          "2h": 120, "3h": 180, "4h": 240, "1d": 1440,
          "1W": 10080, "1M": 43200}   # minutos por bucket (mock, agregacion 5m)
LIVE_BAR = {  # (barSizeSetting, durationStr) para reqHistoricalData en LIVE
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


def load_ibkr_bars(sym, tail=780):
    """Barras 1m VIVAS de data/bars_<sym>_ibkr.txt (el fleet bar_bridge las mantiene para
    los 33 símbolos). Archivo OS-page-cacheado -> lectura a velocidad RAM. Se usa para
    mostrar el chart AL INSTANTE al cambiar de símbolo (sin esperar el round-trip a TWS);
    la suscripción viva se re-ata en background. [ts,o,h,l,c,v]."""
    p = os.path.join(REPO, "data", f"bars_{sym.lower()}_ibkr.txt")
    rows = []
    if not os.path.exists(p):
        return rows
    for ln in open(p):
        f = ln.split()
        if len(f) >= 5:
            try:
                rows.append([int(f[0]), float(f[1]), float(f[2]), float(f[3]),
                             float(f[4]), float(f[5]) if len(f) > 5 else 0.0])
            except Exception:
                continue
    return rows[-tail:] if tail else rows


def load_levels(sym, max_age_s=2700, all_exp=False):
    """Lee charts/data/levels_<sym>.json. Si falta/está viejo intenta regenerar via
    chart_levels.gen (que lee el cache TWS opt_chain). Degradacion limpia: si no hay
    cache ni json, devuelve {} y el chart sigue sin overlays GEX."""
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


# ---- alarmas manuales estilo TradingView (escriben ~/Desktop/price-alerts.txt) ----
def _alarm_path():
    return os.path.expanduser("~/Desktop/price-alerts.txt")


def alarm_list(sym):
    """Alarmas ACTIVAS (no disparadas) del símbolo -> [{price, dir}]."""
    su = sym.upper()
    out = []
    try:
        for ln in open(_alarm_path(), errors="ignore"):
            s = ln.strip()
            if not s or s.startswith("#") or s.startswith("[DISPARADA"):
                continue
            p = s.split("#")[0].split()
            if len(p) >= 3 and p[0].upper() == su:
                try:
                    out.append({"price": float(p[1]), "dir": p[2].lower()})
                except Exception:
                    pass
    except Exception:
        pass
    return out


def alarm_add(sym, price, direction):
    """Añade una alarma manual (price_alarm la relee cada 1s). SEÑAL-SOLAMENTE."""
    line = f"{sym.lower()} {price:g} {('up' if direction=='up' else 'down')}        # manual chart {time.strftime('%H:%M')}\n"
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
    locales (data/bars_<sym>_ibkr.txt: epoch o h l c v). Degrada a None. SEÑAL-SOLAMENTE."""
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    try:
        rows = [ln.split() for ln in open(p) if ln.strip()]
        c = [(int(r[0]), float(r[4]), float(r[5])) for r in rows if len(r) >= 6]
    except Exception:
        c = []
    if not c:
        return {"last": None, "chg": None, "vol": None}
    last_day = time.localtime(c[-1][0]).tm_yday
    today = [x for x in c if time.localtime(x[0]).tm_yday == last_day]
    prev = [x for x in c if time.localtime(x[0]).tm_yday != last_day]
    last = today[-1][1]
    vol = sum(x[2] for x in today)
    prev_close = prev[-1][1] if prev else today[0][1]
    chg = round((last - prev_close) / prev_close * 100, 2) if prev_close else None
    return {"last": round(last, 2), "chg": chg, "vol": int(vol)}


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


def watchlist_payload():
    fleet = load_fleet(); user = load_user_watchlist()
    quotes = {s: watchlist_quote(s) for s in dict.fromkeys(fleet + user)}
    stats = load_watchlist_stats()   # feed opcional -> sobreescribe vol/chg/last si viene
    for s, q in quotes.items():
        st = stats.get(s) or stats.get(s.upper()) or stats.get(s.lower())
        if not isinstance(st, dict):
            continue
        # el feed usa {vol, pct|chg, price|last}; sólo sobreescribe cuando trae valor real
        for dst, keys in (("vol", ("vol",)), ("chg", ("chg", "pct")), ("last", ("last", "price"))):
            for k in keys:
                v = st.get(k)
                if v is not None:
                    q[dst] = v
                    break
    return {"type": "watchlist", "fleet": fleet, "user": user, "quotes": quotes}


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
    try:
        with open(zones_path(sym), "w") as f:
            json.dump(zones, f)
    except Exception as e:
        print(f"[zone] save falló ({e})")


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


def zone_add(sym, price, side, kind, exp=None, qty=1, instrument="opt"):
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
         "exec": False,                    # CANDADO: ficha-only (señal) por defecto
         "stop": {"on": side == "buy",     # stop propuesto por defecto en zonas de compra
                  "px": _default_stop_px(price, side, kind), "native": True},
         "armed_date": time.strftime("%Y-%m-%d")}   # caduca fin de día salvo re-arme
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
        if fields.get("exp"):
            z["exp"] = fields["exp"]
        if fields.get("qty") is not None:
            try:
                z["qty"] = max(1, int(fields["qty"]))
            except Exception:
                pass
        if fields.get("exec") is not None:
            z["exec"] = bool(fields["exec"])
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
_ACCT = {"ib": None, "port": None}
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


async def _acct_conn():
    """Conexión readonly al puerto del MODO actual (se reconecta si el modo cambió)."""
    port = ib_mode.get_port()
    a = _ACCT["ib"]
    if a is not None and a.isConnected() and _ACCT["port"] == port:
        return a
    if a is not None:
        try: a.disconnect()
        except Exception: pass
    from ib_async import IB
    ib = IB()
    await ib.connectAsync("127.0.0.1", port, clientId=63, readonly=True, timeout=10)
    _ACCT["ib"] = ib; _ACCT["port"] = port
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
        await ib.reqAllOpenOrdersAsync()
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
            summ = await ib.accountSummaryAsync()
            keep = {"NetLiquidation", "BuyingPower", "AvailableFunds", "UnrealizedPnL", "RealizedPnL"}
            out["summary"] = {v.tag: v.value for v in summ if v.tag in keep}
        except Exception:
            pass
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"
    return out


def route_order_action(act):
    """Escribe un comando para el order_engine (cancel/modify/close). El motor lo
    ejecuta con su doble llave (cancel siempre; modify/close-live requieren ARM_LIVE).
    El bridge JAMÁS coloca la orden él mismo (ley #0)."""
    import time as _t
    cmd = {"ts": int(_t.time() * 1000), "act": act.get("act"),
           "orderId": act.get("orderId"), "limit": act.get("limit"),
           "conId": act.get("conId"), "qty": act.get("qty"),
           "sym": act.get("sym"), "exp": act.get("exp"),
           "strike": act.get("strike"), "right": act.get("right")}
    try:
        os.makedirs(os.path.dirname(CMD_PATH), exist_ok=True)
        with open(CMD_PATH, "a") as f:
            f.write(json.dumps(cmd) + "\n")
        engine_up = bool(subprocess.run(["pgrep", "-f", "order_engine/order_engine"],
                                        capture_output=True).stdout.strip())
        return {"type": "order_action", "ok": True, "queued": cmd,
                "engine_up": engine_up,
                "note": "" if engine_up else "⚠ order_engine NO está corriendo — el comando se ejecuta cuando lo lances"}
    except Exception as e:
        return {"type": "order_action", "ok": False, "err": str(e)}


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


def _signals_file_line(sym, text):
    """Escribe la ficha en data/trading-signals/<fecha>.txt para que el relay de voz/teléfono
    la dispare (mismo canal que el resto de señales). SEÑAL-SOLAMENTE (solo texto)."""
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


async def broadcast_direction(state, lv=None):
    """Flecha direccional compuesta (direction_view) -> overlay del chart. Degrada limpio."""
    if not state.clients:
        return
    try:
        dv = direction_view.compute(state.sym, lv=lv if lv is not None else (state.levels or {}))
    except Exception as e:
        print(f"[dir] compute falló ({e})")
        return
    if not dv:
        return
    frame = {"type": "direction", "sym": state.sym.upper(), "dir": dv.get("dir", "flat"),
             "prob": dv.get("prob"), "score": dv.get("score"), "why": dv.get("why", []),
             "target": dv.get("target"), "target_label": dv.get("target_label"),
             "target_pct": dv.get("target_pct")}
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
        except Exception:
            state.clients.discard(ws)


def history_frame(bars, levels, tf=None):
    ind = compute_indicators(bars)
    return {
        "type": "history",
        "tf": tf,
        "bars": _candle_points(bars),
        "indicators": indicators_series(bars, ind),
        "levels": levels or {},
        "signals": load_signal_markers((levels or {}).get("sym", ""), bars),
        "engineOps": load_engine_ops((levels or {}).get("sym", ""), bars),
    }


def _last_point(pts):
    return pts[-1] if pts else None


def bar_frame(bars, levels, tf=None):
    """Frame incremental: última barra + últimos valores de cada indicador (update())."""
    ind = compute_indicators(bars)
    ser = indicators_series(bars, ind)
    last = bars[-1]
    return {
        "type": "bar",
        "tf": tf,
        "bar": {"time": last[0], "open": last[1], "high": last[2],
                "low": last[3], "close": last[4]},
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
        self.bars = []          # feed crudo: 5m (mock) / barSize nativo (live)
        self.levels = {}
        self.clients = set()    # WebSocket
        self.tf = DEFAULT_TF_MOCK if mock else DEFAULT_TF_LIVE
        self.all_exp = False    # scope GEX: False=0DTE, True=ALL-EXP
        self._vix = None        # último VIX (índice CBOE via ib_async)
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

    def set_bars(self, bars):
        self.bars = bars

    def upsert_bar(self, bar):
        """Reemplaza si mismo epoch (barra en curso), si no, agrega."""
        if self.bars and self.bars[-1][0] == bar[0]:
            self.bars[-1] = bar
        else:
            self.bars.append(bar)


def agg_view_bars(state):
    """Barras que VE el chart al tf actual.
    MOCK: base 5m -> se agrega hacia arriba (ce.aggregate, paridad con el engine).
          '1m' no tiene fuente offline -> 5m. LIVE: state.bars ya viene al barSize
          nativo pedido en live_reapply, así que se devuelve tal cual."""
    if not state.mock:
        return state.bars
    mins = TF_MIN.get(state.tf, 5)
    if mins <= 5:
        return state.bars
    return ce.aggregate(state.bars, mins)


async def set_timeframe(state, tf):
    """Cambia el tf global. MOCK: solo marca tf (la agregación hace el resto).
    LIVE: re-pide reqHistoricalData con el barSize nativo (cancela el anterior)."""
    if tf not in TF_MIN:
        return
    state.tf = tf
    if state.mock:
        if tf == "1m":
            print("[tf] '1m' sin fuente offline en --mock -> uso 5m")
        return
    if state._ib is not None:
        try:
            await live_reapply(state, tf)
        except Exception as e:
            print(f"[tf] live_reapply({tf}) falló ({e})")


async def live_reapply(state, tf):
    """LIVE: cancela la suscripción de barras vigente y re-pide al barSize nativo
    del tf, re-atando keepUpToDate. SEÑAL-SOLAMENTE: solo reqHistoricalData."""
    ib = state._ib
    if ib is None or state._contract is None:
        return
    if state._live_sub is not None:
        try:
            ib.cancelHistoricalData(state._live_sub)
        except Exception:
            pass
    bar_size, dur = LIVE_BAR.get(tf, ("1 min", "2 D"))
    bars = await ib.reqHistoricalDataAsync(   # async (ver live_feed)
        state._contract, endDateTime="", durationStr=dur, barSizeSetting=bar_size,
        whatToShow="TRADES", useRTH=False, keepUpToDate=True,
    )
    state.set_bars([[int(b.date.timestamp()), b.open, b.high, b.low, b.close, float(b.volume)]
                    for b in bars])
    bars.updateEvent += _make_on_bar(state)
    state._live_sub = bars
    print(f"[tf] LIVE {state.sym}: {bar_size} ({dur}) -> {len(state.bars)} barras")


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
        print(f"[sym] {sym.upper()}: {len(instant)} barras instantáneas (archivo, sin esperar TWS)")
    if state._ib is not None:
        # re-broadcast del history solo si NO hubo carga instantánea (símbolo fuera de la
        # flota) -> evita el DOBLE LOAD: con archivo, los updates incrementales bastan.
        asyncio.ensure_future(_relive_symbol(state, sym, rebroadcast=not instant))


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
        (contract,) = await ib.qualifyContractsAsync(contract)
    except Exception as e:
        print(f"[sym] no cualifica {sym.upper()} ({e})"); return
    state._contract = contract
    try: state._px_ticker = ib.reqMktData(contract, "", False, False)   # tick stream nuevo
    except Exception: pass
    await live_reapply(state, state.tf)
    if rebroadcast:   # solo si no hubo carga instantánea (símbolo fuera de la flota)
        frame = history_frame(agg_view_bars(state), state.levels, state.tf)
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

    @app.get("/lightweight-charts-v5.js")
    async def lib():
        p = os.path.join(os.path.dirname(LIVE_HTML), "lightweight-charts-v5.js")
        if os.path.exists(p):
            return FileResponse(p, media_type="application/javascript")
        return JSONResponse({"error": "lightweight-charts-v5.js no encontrado"}, status_code=404)

    @app.get("/favicon.svg")
    async def favicon():
        p = os.path.join(os.path.dirname(LIVE_HTML), "favicon.svg")
        if os.path.exists(p):
            return FileResponse(p, media_type="image/svg+xml")
        return JSONResponse({"error": "favicon.svg no encontrado"}, status_code=404)

    @app.get("/health")
    async def health():
        return {"sym": state.sym, "mock": state.mock, "bars": len(state.bars),
                "clients": len(state.clients), "signal_only": True}

    @app.websocket("/stream")
    async def stream(ws: WebSocket):
        await ws.accept()
        state.clients.add(ws)
        try:
            # frame de historia inmediato (setData once en el cliente), al tf actual
            await ws.send_json(history_frame(agg_view_bars(state), state.levels, state.tf))
            # watchlist (fleet + usuario), zonas 0DTE del símbolo y flecha direccional
            await ws.send_json(watchlist_payload())
            await ws.send_json(zones_frame(state))
            if any(z.get("exec") for z in state.zones):
                await ws.send_json({"type": "engine", "sym": state.sym.upper(),
                                    "rows": engine_state(state.sym)})
            await broadcast_direction(state)
            while True:
                # drenamos pings/close + controles del cliente (cambio de timeframe)
                txt = await ws.receive_text()
                try:
                    ctl = json.loads(txt)
                except Exception:
                    continue
                if isinstance(ctl, dict) and ctl.get("cmd") == "tf":
                    await set_timeframe(state, ctl.get("tf", state.tf))
                    # re-emite un frame de historia FRESCO al tf pedido
                    await ws.send_json(history_frame(agg_view_bars(state), state.levels, state.tf))
                elif isinstance(ctl, dict) and ctl.get("cmd") == "sym":
                    await set_symbol(state, ctl.get("sym", state.sym))
                    await ws.send_json(history_frame(agg_view_bars(state), state.levels, state.tf))
                    # zonas del nuevo símbolo + flecha direccional (actualización inmediata)
                    await ws.send_json(zones_frame(state))
                    await broadcast_direction(state)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "scope":
                    state.all_exp = (ctl.get("scope") == "ALL")   # 0DTE <-> ALL-EXP
                    sp = state.bars[-1][4] if state.bars else None
                    state.levels = chart_levels.gen(state.sym, spot=sp, write=False, all_exp=state.all_exp) or state.levels
                    await broadcast_levels(state)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "narrate":
                    if "on" in ctl:
                        state._narr_on = bool(ctl["on"])
                    if ctl.get("force"):
                        state._narr_force = True
                    if state._narr_on:
                        # respuesta inmediata (determinista) + AI si se forzó
                        await narrator_tick(state)
                    else:
                        await broadcast_narr(state)   # confirma OFF al cliente
                elif isinstance(ctl, dict) and ctl.get("cmd") == "alarm":
                    # alarma manual estilo TradingView: la escribe en ~/Desktop/price-alerts.txt
                    # (price_alarm C++ la relee cada 1s -> sirena+voz+registro). SEÑAL-SOLAMENTE.
                    act = ctl.get("act", "add")
                    sp = state.bars[-1][4] if state.bars else None
                    if act == "add":
                        price = ctl.get("price")
                        direction = ctl.get("dir") or ("up" if (sp and price and price >= sp) else "down")
                        if price:
                            alarm_add(state.sym, float(price), direction)
                    elif act == "del":
                        alarm_remove(state.sym, ctl.get("price"))
                    await ws.send_json({"type": "alarms", "sym": state.sym.upper(),
                                        "alarms": alarm_list(state.sym)})
                elif isinstance(ctl, dict) and ctl.get("cmd") == "watchlist":
                    # watchlist buscable/expandible: add (cualifica en LIVE) / del / list.
                    act = ctl.get("act", "list")
                    if act == "add":
                        s = (ctl.get("sym") or "").strip().upper()
                        if s:
                            ok = True
                            if not state.mock and state._ib is not None:
                                # LIVE: cualifica el contrato antes de aceptar (símbolo real)
                                try:
                                    from ib_async import Stock
                                    await state._ib.qualifyContractsAsync(Stock(s, "SMART", "USD"))
                                except Exception as e:
                                    ok = False
                                    print(f"[watchlist] no cualifica {s} ({e})")
                            if ok:
                                _watchlist_file_add(s)
                    elif act == "del":
                        _watchlist_file_del((ctl.get("sym") or "").strip().upper())
                    await ws.send_json(watchlist_payload())
                elif isinstance(ctl, dict) and ctl.get("cmd") == "zone":
                    # ZONA de ejecución (buy/sell call/put + exp/qty/exec/stop). El chart SÓLO
                    # PRODUCE exec_zones_<sym>.json; el order_engine C++ lo CONSUME. Aquí jamás
                    # se coloca una orden. exec=false = ficha-only (señal). SEÑAL-SOLAMENTE.
                    act = ctl.get("act", "list")
                    if act == "add" and ctl.get("price") is not None:
                        state.zones = zone_add(state.sym, ctl.get("price"),
                                               ctl.get("side"), ctl.get("kind"),
                                               exp=ctl.get("exp"), qty=ctl.get("qty") or 1,
                                               instrument=ctl.get("instrument") or "opt")
                    elif act == "del":
                        state.zones = zone_del(state.sym, price=ctl.get("price"), zid=ctl.get("id"))
                    elif act == "set" and ctl.get("id"):
                        # set exp/qty/exec/price/stop en una zona existente (arrastre del stop,
                        # armado exec, cambio de expiry...) -> persiste el contrato del motor.
                        state.zones = zone_update(
                            state.sym, ctl.get("id"),
                            exp=ctl.get("exp"), qty=ctl.get("qty"), exec=ctl.get("exec"),
                            price=ctl.get("price"), stop_px=ctl.get("stop_px"),
                            stop_on=ctl.get("stop_on"), stop_native=ctl.get("stop_native"))
                    else:
                        state.zones = zones_load(state.sym)
                    await ws.send_json(zones_frame(state))
                    if any(z.get("exec") for z in state.zones):
                        await broadcast_engine(state)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "optquote":
                    # previsualización TradingView-like del contrato (strike + bid/ask C/P) al
                    # precio y expiry elegidos en el popup de zona. Sólo LECTURA del cache.
                    q = chain_quote(state.sym, ctl.get("price"), ctl.get("exp"))
                    q.update({"type": "optquote", "sym": state.sym.upper(),
                              "price": ctl.get("price")})
                    await ws.send_json(q)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "prob":
                    # probabilidad de profit (order_engine/prob_profit.py, otro agente) -> chip.
                    # Sólo cómputo de probabilidad; NUNCA coloca órdenes. SEÑAL-SOLAMENTE.
                    res = run_prob(state.sym, ctl.get("price") if ctl.get("price") is not None
                                   else ctl.get("level"),
                                   ctl.get("side") or "buy", ctl.get("kind") or "call",
                                   ctl.get("exp"))
                    res.update({"type": "prob", "sym": state.sym.upper(), "id": ctl.get("id")})
                    await ws.send_json(res)
                elif isinstance(ctl, dict) and ctl.get("cmd") == "ticket":
                    # ficha 0DTE bajo demanda (order_ticket.build) -> tarjeta en el chart.
                    # PREPARA la orden; el HUMANO la ejecuta en IBKR. SEÑAL-SOLAMENTE.
                    t = build_ticket(ctl.get("sym") or state.sym, ctl.get("price"),
                                     ctl.get("side"), ctl.get("kind"))
                    await ws.send_json({"type": "ticket", "sym": state.sym.upper(), "t": t})
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
            state.clients.discard(ws)

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
        b = state.bars[-1]
        b[4] = px
        if px > b[2]:
            b[2] = px
        if px < b[3]:
            b[3] = px
        now = time.time()
        if now - state._last_tick_bcast < 0.12:
            return
        state._last_tick_bcast = now
        asyncio.ensure_future(broadcast_tick(state))
        # flecha direccional en TIEMPO REAL (throttle 2s; compute ~7ms, usa niveles cacheados)
        if now - getattr(state, "_last_dir_bcast", 0) >= 2.0:
            state._last_dir_bcast = now
            asyncio.ensure_future(broadcast_direction(state))
    return on_pending


async def broadcast(state):
    """Empuja el frame incremental a todos los clientes WS conectados."""
    if not state.clients:
        return
    view = agg_view_bars(state)
    if not view:
        return
    frame = bar_frame(view, state.levels, state.tf)
    dead = []
    for ws in list(state.clients):
        try:
            await ws.send_json(frame)
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


def _log_structural(state, sig):
    """Guarda la señal estructural en trades.db (source='structural') para el backtest EOD.
    Dedup por firma. SEÑAL-SOLAMENTE."""
    try:
        import sqlite3
        prob = f" · prob {sig['prob']}% (estructural, no WR medido)" if sig.get("prob") else ""
        msg = f"{sig['text']}{prob}"
        c = sqlite3.connect(os.path.join(REPO, "trades.db"), timeout=3)
        c.execute("PRAGMA busy_timeout=3000")
        c.execute("""INSERT OR IGNORE INTO signals
            (ts_epoch,ts_txt,date,kind,symbol,price,priority,source,msg,raw)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), time.strftime("%H:%M:%S"), time.strftime("%Y-%m-%d"),
             f"🧲 ESTRUCTURAL {sig.get('kind','')}", sig["sym"].upper(), sig.get("price"),
             "SIGNAL", "structural", msg, msg))
        c.commit(); c.close()
    except Exception as e:
        print(f"[struct] log falló ({e})")


async def structural_tick(state):
    """Genera la señal estructural (imán/flip) y la empuja al chart; la guarda en BD si cambió."""
    lv = state.levels or {}
    if not lv:
        return
    sig = narrator.structural_signal(lv, state.bars)
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
            _log_structural(state, sig)


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
            lv = chart_levels.gen(state.sym, spot=spot, write=False, all_exp=state.all_exp)
            if lv:
                lv["asof"] = int(time.time())   # asof fresco -> el cliente redibuja
                if state._vix_ticker is not None:
                    try:
                        v = state._vix_ticker.marketPrice()
                        if v and v == v and v > 0:
                            state._vix = round(v, 2)
                    except Exception:
                        pass
                if state._vix is not None:
                    lv["vix"] = state._vix
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
async def mock_feed(state, interval=1.0, warm=260):
    """Carga barras 5m del CSV: las primeras `warm` como historia, el resto se emiten
    una a una cada `interval`s (simula el tick de barra nueva). Prueba TODO el pipe
    sin TWS. Al agotarse, hace loop reiniciando el reloj (para demo continua)."""
    all_bars = load_csv_bars(state.sym)
    if not all_bars:
        print(f"[mock] sin CSV para {state.sym}; genero barras sintéticas")
        all_bars = _synthetic_bars(state.sym, 400)
    warm = min(warm, max(1, len(all_bars) - 20))
    state.set_bars(all_bars[:warm])
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
    cambiar de timeframe (live_reapply lo re-ata a la nueva suscripción)."""
    def on_bar(bars_, has_new):
        b = bars_[-1]
        state.upsert_bar([int(b.date.timestamp()), b.open, b.high, b.low,
                          b.close, float(b.volume)])
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
                await ib.connectAsync("127.0.0.1", port, clientId=client_id)
                print(f"[live] conectado TWS 127.0.0.1:{port} clientId={client_id}")
            except Exception as e:
                print(f"[live] reconnect en 5s ({e})")
                await asyncio.sleep(5)

    await connect()

    def on_disconnect():
        print("[live] desconectado; reintentando…")
        asyncio.ensure_future(connect())

    ib.disconnectedEvent += on_disconnect

    contract = Stock(state.sym.upper(), "SMART", "USD")
    (contract,) = await ib.qualifyContractsAsync(contract)
    state._ib = ib
    state._contract = contract
    ib.reqMarketDataType(1)   # REALTIME para TODO
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
        await ib.qualifyContractsAsync(vx)
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
    print(f"[live] {state.sym}: {len(state.bars)} barras {bar_size} iniciales (tf={state.tf})")

    bars.updateEvent += _make_on_bar(state)
    state._live_sub = bars
    # mantener vivo el loop de ib_async
    while True:
        await asyncio.sleep(3600)


# =============================== arranque servidor ===========================
def build_state_and_feed(args):
    sym = resolve_sym(args.sym)
    state = State(sym, mock=args.mock)
    state.levels = load_levels(sym)
    if not args.mock:
        # en modo live las barras iniciales las trae el feed; precarga vacía
        state.set_bars([])
    return state


async def _serve(args):
    import uvicorn
    state = build_state_and_feed(args)
    app = create_app(state)
    if args.mock:
        asyncio.ensure_future(mock_feed(state, interval=args.interval))
    else:
        asyncio.ensure_future(live_feed(state, args.port, args.client_id))
    asyncio.ensure_future(levels_loop(state))   # GEX/flip/muros en tiempo real
    config = uvicorn.Config(app, host=args.host, port=args.http_port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


# módulo-nivel `app` para `uvicorn scripts.chart_bridge:app` (live, defaults de env)
if HAVE_FASTAPI:
    def _app_factory():
        sym = resolve_sym(os.environ.get("CHART_SYM"))
        state = State(sym, mock=bool(os.environ.get("CHART_MOCK")))
        state.levels = load_levels(sym)
        app = create_app(state)
        port = int(os.environ.get("CHART_TWS_PORT") or ib_mode.get_port())  # sin hardcode: sigue el modo

        @app.on_event("startup")
        async def _start():
            if state.mock:
                asyncio.ensure_future(mock_feed(state, interval=float(os.environ.get("CHART_INTERVAL", "1.0"))))
            else:
                asyncio.ensure_future(live_feed(state, port, int(os.environ.get("CHART_CLIENT_ID", "60"))))
            asyncio.ensure_future(levels_loop(state))   # GEX/flip/muros en tiempo real
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
    bars = load_csv_bars(sym, tail=320)
    if not bars:
        print("[selftest] sin CSV -> sintéticas")
        bars = _synthetic_bars(sym, 320)
    levels = load_levels(sym)
    print(f"[selftest] barras={len(bars)}  niveles={'sí' if levels else 'no'}"
          + (f" (spot {levels.get('spot')}, regime {levels.get('regime')}, "
             f"CW {levels.get('call_wall')} PW {levels.get('put_wall')} flip {levels.get('flip')})" if levels else ""))

    # historia con todo menos las últimas 3 barras; luego 3 updates
    warm = bars[:-3]
    hf = history_frame(warm, levels, "5m")
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
        bf = bar_frame(agg_view_bars(st), st.levels, st.tf)
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
    hf15 = history_frame(view15, st.levels, st.tf)
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
    ap.add_argument("--selftest", action="store_true", help="valida frames sin fastapi/TWS")
    args = ap.parse_args()

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
