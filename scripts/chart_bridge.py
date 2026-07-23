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
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)

# --- reuso de la matematica de los engines (paridad con backtests) ---
import confluence_engine as ce   # sma, stdev, ema_series (causales, población ÷N)
import chart_levels              # gen(sym) -> charts/data/levels_<sym>.json
import narrator                  # narrador de mercado: determinista (gratis) + DeepSeek

# NOTA: importar confluence_engine hace os.chdir(REPO) (efecto de modulo). Reforzamos.
os.chdir(REPO)

LEVELS_DIR = os.path.join(REPO, "charts", "data")
LIVE_HTML = os.path.join(REPO, "charts", "live.html")
DEFAULT_SYM = "nvda"

# --- timeframes (TradingView-like) ---------------------------------------
# MOCK: la base del CSV es 5m; agregamos hacia arriba. "1m" no tiene fuente
# offline -> cae a 5m (con nota en consola). LIVE: se re-pide reqHistoricalData
# con el barSize nativo (ver live_reapply).
TF_LIST = ("1m", "5m", "15m", "1h", "1d")
TF_MIN = {"1m": 5, "5m": 5, "15m": 15, "1h": 60, "1d": 1440}   # minutos por bucket (mock)
LIVE_BAR = {  # (barSizeSetting, durationStr) para reqHistoricalData en LIVE
    "1m": ("1 min", "2 D"), "5m": ("5 mins", "5 D"), "15m": ("15 mins", "10 D"),
    "1h": ("1 hour", "30 D"), "1d": ("1 day", "1 Y"),
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
    if state.mock:
        base = load_csv_bars(sym, tail=400)
        state.set_bars(base)
        print(f"[sym] MOCK -> {sym.upper()} ({len(base)} barras 5m)")
        return
    ib = state._ib
    if ib is None:
        return
    if state._live_sub is not None:
        try:
            ib.cancelHistoricalData(state._live_sub)
        except Exception:
            pass
    from ib_async import Stock
    contract = Stock(sym.upper(), "SMART", "USD")
    try:
        (contract,) = await ib.qualifyContractsAsync(contract)
    except Exception as e:
        print(f"[sym] no cualifica {sym.upper()} ({e})"); return
    state._contract = contract
    await live_reapply(state, state.tf)
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
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            state.clients.discard(ws)

    return app


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
    # VIX (índice CBOE) — degradación limpia si no hay suscripción de índice
    try:
        from ib_async import Index
        ib.reqMarketDataType(1)   # REALTIME para TODO (nunca degradar la conexión a delayed)
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
        port = int(os.environ.get("CHART_TWS_PORT", "7496"))

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
    ap.add_argument("--port", type=int, default=7496, help="puerto TWS live 7496 / paper 7497")
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
