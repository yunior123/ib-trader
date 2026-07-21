#!/usr/bin/env python3
"""
pattern_detect.py — Detector ALGORITMICO de patrones clasicos de chart + medicion EMPIRICA.

Filosofia anti-hardcode:
  - Nada de "NVDA hace doble techo". Los patrones se detectan por GEOMETRIA pura
    sobre los swing points (zigzag), con tolerancias relativas al ATR o al % del precio.
  - La tasa de acierto NO se inventa: se mide escaneando la PROPIA historia del ticker
    (period=2y) y contando cuantas veces, tras el gatillo (ruptura de neckline), el precio
    alcanzo el objetivo (measured-move) ANTES de tocar el stop. Win rate + n reales.
  - Si n < 8 para un ticker, se POOL-ea con la flota pasada y se reporta "pooled".
  - Jamas una tasa sin su n. n=0 -> "sin muestra — no fiable".

Uso:
  pattern_detect.py SYM [SYM2 ...]
  pattern_detect.py --fleet
Escribe data/patterns.json legible por maquina.

DISCLAIMER: los patrones son señales PROBABILISTICAS que a veces se forman, no garantias.
"""
import sys, os, json, warnings
warnings.filterwarnings("ignore")
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO, "data")
OUT_JSON = os.path.join(DATA_DIR, "patterns.json")

FLEET = ["QQQ","SPY","NVDA","TSLA","MU","SMH","AMD","AAPL","MSFT","META","AMZN",
         "GOOGL","INTC","TSM","ASML","TXN","QCOM","AVGO","NFLX","NOK","GLD"]

# ----------------------------------------------------------------------------- datos
def fetch(sym):
    """Descarga OHLC diario 2y. Devuelve dict de arrays numpy o None si falla."""
    import yfinance as yf
    df = yf.download(sym, period="2y", interval="1d", progress=False, auto_adjust=True)
    if df is None or len(df) < 60:
        return None
    # yfinance puede devolver columnas MultiIndex cuando pasas un solo ticker
    def col(name):
        c = df[name]
        return np.asarray(c).reshape(-1).astype(float)
    return {"close": col("Close"), "high": col("High"), "low": col("Low"),
            "n": len(df)}

def atr(high, low, close, period=14):
    """ATR de Wilder (simplificado con media movil de True Range)."""
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    out = np.zeros(len(close))
    out[:period] = tr[:period].mean() if period <= len(tr) else tr.mean()
    a = out[period-1] if period-1 < len(out) else tr.mean()
    for i in range(period, len(close)):
        a = (a*(period-1) + tr[i]) / period
        out[i] = a
    return out

# ----------------------------------------------------------------------------- zigzag
def zigzag(high, low, close, atr_arr, k=1.0):
    """
    Detector de swing points basado en ATR.
    Un nuevo swing se confirma cuando el precio revierte >= k*ATR desde el extremo previo.
    Devuelve lista ordenada de (index, price, type) alternando 'H'/'L'.
    """
    n = len(close)
    if n < 5:
        return []
    pivots = []
    # arrancamos buscando direccion: asumimos primer pivote provisional en 0
    last_ext_i = 0
    last_ext_p = close[0]
    direction = 0  # 0 sin definir, 1 buscando high, -1 buscando low
    for i in range(1, n):
        thr = k * atr_arr[i] if atr_arr[i] > 0 else k * close[i] * 0.01
        if direction >= 0:
            # actualizamos maximo tentativo
            if high[i] > last_ext_p:
                last_ext_p = high[i]; last_ext_i = i
            # reversion a la baja confirma un swing HIGH
            if last_ext_p - low[i] >= thr:
                pivots.append((last_ext_i, last_ext_p, "H"))
                direction = -1
                last_ext_p = low[i]; last_ext_i = i
                continue
        if direction <= 0:
            if low[i] < last_ext_p:
                last_ext_p = low[i]; last_ext_i = i
            if high[i] - last_ext_p >= thr:
                pivots.append((last_ext_i, last_ext_p, "L"))
                direction = 1
                last_ext_p = high[i]; last_ext_i = i
                continue
    # limpiar duplicados consecutivos del mismo tipo (nos quedamos con el extremo)
    clean = []
    for p in pivots:
        if clean and clean[-1][2] == p[2]:
            if (p[2] == "H" and p[1] > clean[-1][1]) or (p[2] == "L" and p[1] < clean[-1][1]):
                clean[-1] = p
        else:
            clean.append(p)
    return clean

# ----------------------------------------------------------------------------- detectores
# Cada detector recibe la sub-secuencia de swings mas reciente y arrays de precio.
# Devuelve dict o None. Confianza 0-1 = que tan limpia es la geometria.

def _tol_pct(a, b):
    """Diferencia relativa entre dos precios (0 = identicos)."""
    return abs(a-b) / ((a+b)/2.0)

def det_head_shoulders(sw, price):
    """
    H&S (bajista) e inverse H&S (alcista) sobre los ultimos 5 swings.
    Bajista: L H L H L con el H central > hombros; hombros ~nivel; neckline = valles.
    """
    if len(sw) < 5:
        return None
    s = sw[-5:]
    types = "".join(t for _,_,t in s)
    prices = [p for _,p,_ in s]
    idxs = [i for i,_,_ in s]
    # ---- H&S bajista: patron H L H L H  (hombro-valle-cabeza-valle-hombro)
    if types == "HLHLH":
        ls, v1, head, v2, rs = prices
        if head > ls and head > rs and _tol_pct(ls, rs) < 0.06:
            neckline = (v1 + v2) / 2.0
            height = head - neckline
            target = neckline - height           # measured move a la baja
            stop = head                          # invalidacion por encima de la cabeza
            # confianza: hombros nivelados + cabeza prominente + valles nivelados
            conf = 1.0 - _tol_pct(ls, rs)*3 - _tol_pct(v1, v2)*2
            conf = max(0.0, min(1.0, conf * (min(head-ls, head-rs)/head*8)))
            return dict(pattern="head_shoulders", direction="bear",
                        trigger_level=neckline, target=target, stop=stop,
                        formed_bars_ago=len(price)-1-idxs[-1],
                        confidence=round(float(conf),2))
    # ---- inverse H&S alcista: L H L H L
    if types == "LHLHL":
        ls, p1, head, p2, rs = prices
        if head < ls and head < rs and _tol_pct(ls, rs) < 0.06:
            neckline = (p1 + p2) / 2.0
            height = neckline - head
            target = neckline + height
            stop = head
            conf = 1.0 - _tol_pct(ls, rs)*3 - _tol_pct(p1, p2)*2
            conf = max(0.0, min(1.0, conf * (min(ls-head, rs-head)/head*8)))
            return dict(pattern="head_shoulders", direction="bull",
                        trigger_level=neckline, target=target, stop=stop,
                        formed_bars_ago=len(price)-1-idxs[-1],
                        confidence=round(float(conf),2))
    return None

def det_double(sw, price):
    """
    Doble techo (bajista) / doble suelo (alcista) sobre los ultimos 3 swings.
    Techo: H L H con los dos H dentro de tolerancia; neckline = valle intermedio.
    """
    if len(sw) < 3:
        return None
    s = sw[-3:]
    types = "".join(t for _,_,t in s)
    prices = [p for _,p,_ in s]
    idxs = [i for i,_,_ in s]
    if types == "HLH":
        t1, valley, t2 = prices
        if _tol_pct(t1, t2) < 0.03:            # dos techos ~iguales
            neckline = valley
            height = ((t1+t2)/2.0) - valley
            target = neckline - height
            stop = max(t1, t2)
            conf = max(0.0, min(1.0, (1.0 - _tol_pct(t1,t2)*10) * min(1.0, height/neckline*12)))
            return dict(pattern="double_top", direction="bear",
                        trigger_level=neckline, target=target, stop=stop,
                        formed_bars_ago=len(price)-1-idxs[-1],
                        confidence=round(float(conf),2))
    if types == "LHL":
        b1, peak, b2 = prices
        if _tol_pct(b1, b2) < 0.03:
            neckline = peak
            height = peak - ((b1+b2)/2.0)
            target = neckline + height
            stop = min(b1, b2)
            conf = max(0.0, min(1.0, (1.0 - _tol_pct(b1,b2)*10) * min(1.0, height/neckline*12)))
            return dict(pattern="double_bottom", direction="bull",
                        trigger_level=neckline, target=target, stop=stop,
                        formed_bars_ago=len(price)-1-idxs[-1],
                        confidence=round(float(conf),2))
    return None

def _fit_slope(idxs, prices):
    """Pendiente de regresion lineal + R^2 (que tan bien alinean los puntos)."""
    x = np.asarray(idxs, float); y = np.asarray(prices, float)
    if len(x) < 2:
        return 0.0, 0.0
    A = np.vstack([x, np.ones_like(x)]).T
    (m, b), _, _, _ = np.linalg.lstsq(A, y, rcond=None)
    pred = m*x + b
    ss_res = np.sum((y-pred)**2); ss_tot = np.sum((y-y.mean())**2)
    r2 = 1.0 - ss_res/ss_tot if ss_tot > 0 else 0.0
    return m, r2

def det_triangle(sw, price):
    """
    Triangulos sobre los ultimos >=4 swings: ajusta trendline de highs y de lows.
    Ascendente: highs planos, lows subiendo (alcista).
    Descendente: lows planos, highs bajando (bajista).
    Simetrico: highs bajan y lows suben (convergen) -> direccion por breakout, neutral.
    """
    if len(sw) < 4:
        return None
    s = sw[-6:] if len(sw) >= 6 else sw
    highs = [(i,p) for i,p,t in s if t == "H"]
    lows  = [(i,p) for i,p,t in s if t == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    mh, r2h = _fit_slope([i for i,_ in highs], [p for _,p in highs])
    ml, r2l = _fit_slope([i for i,_ in lows],  [p for _,p in lows])
    last_close = price[-1]
    # normalizamos pendientes a %/bar sobre el precio
    sh = mh / last_close; sl = ml / last_close
    flat = 0.0008   # umbral "plano": <0.08%/bar
    last_high = max(p for _,p in highs); last_low = min(p for _,p in lows)
    height = last_high - last_low
    conf_base = max(0.0, min(1.0, (r2h + r2l)/2.0))
    idx_last = s[-1][0]; bars_ago = len(price)-1-idx_last

    if abs(sh) < flat and sl > flat:            # ascendente
        trig = last_high
        return dict(pattern="triangle_ascending", direction="bull",
                    trigger_level=trig, target=trig+height, stop=last_low,
                    formed_bars_ago=bars_ago, confidence=round(conf_base,2))
    if abs(sl) < flat and sh < -flat:           # descendente
        trig = last_low
        return dict(pattern="triangle_descending", direction="bear",
                    trigger_level=trig, target=trig-height, stop=last_high,
                    formed_bars_ago=bars_ago, confidence=round(conf_base,2))
    if sh < -flat and sl > flat:                # simetrico (convergente)
        # direccion tentativa: hacia el lado de la tendencia previa (usamos ultimo swing)
        direction = "bull" if s[-1][2] == "L" else "bear"
        trig = last_high if direction == "bull" else last_low
        tgt = trig + height if direction == "bull" else trig - height
        stop = last_low if direction == "bull" else last_high
        return dict(pattern="triangle_symmetric", direction=direction,
                    trigger_level=trig, target=tgt, stop=stop,
                    formed_bars_ago=bars_ago, confidence=round(conf_base*0.85,2))
    return None

DETECTORS = [det_head_shoulders, det_double, det_triangle]
PATTERN_TYPES = ["head_shoulders","double_top","double_bottom",
                 "triangle_ascending","triangle_descending","triangle_symmetric"]

# ----------------------------------------------------------------------------- empirico
def evaluate_outcome(price, trig_idx, d):
    """
    Tras la barra de deteccion, ¿el precio toco el target antes que el stop?
    Simula desde trig_idx+1 hasta 60 barras. Devuelve 1(win)/0(loss)/None(sin resolver).
    """
    tgt, stop, direction = d["target"], d["stop"], d["direction"]
    end = min(len(price), trig_idx + 61)
    for j in range(trig_idx+1, end):
        px = price[j]
        if direction == "bull":
            if px >= tgt: return 1
            if px <= stop: return 0
        else:
            if px <= tgt: return 1
            if px >= stop: return 0
    return None  # no resuelto dentro del horizonte -> no cuenta

def scan_history(sym_data, atr_arr):
    """
    Recorre TODA la historia: en cada barra evalua la ventana de swings hasta ahi y,
    si un detector dispara un patron NUEVO, registra su desenlace empirico.
    Devuelve {pattern_type: [outcomes...]}.
    """
    close, high, low = sym_data["close"], sym_data["high"], sym_data["low"]
    results = {pt: [] for pt in PATTERN_TYPES}
    seen = set()   # (pattern_type, trig_idx) para no contar el mismo patron dos veces
    full_sw = zigzag(high, low, close, atr_arr)
    if len(full_sw) < 3:
        return results
    # para cada swing (a partir del 3ro), miramos la secuencia que termina ahi
    for end_i in range(3, len(full_sw)+1):
        sub = full_sw[:end_i]
        trig_bar = sub[-1][0]                    # barra del ultimo swing (approx. gatillo)
        if trig_bar >= len(close)-1:
            continue
        for det in DETECTORS:
            d = det(sub, close[:trig_bar+1])
            if not d:
                continue
            key = (d["pattern"], trig_bar)
            if key in seen:
                continue
            seen.add(key)
            out = evaluate_outcome(close, trig_bar, d)
            if out is not None:
                results[d["pattern"]].append(out)
    return results

def rate_block(outcomes):
    n = len(outcomes)
    if n == 0:
        return {"n": 0, "rate": None, "note": "sin muestra — no fiable"}
    return {"n": n, "rate": round(sum(outcomes)/n, 3)}

# ----------------------------------------------------------------------------- por-ticker
def detect_active(sym_data, atr_arr, recent_bars=15):
    """Patron que se esta formando AHORA: ultimo swing dentro de las ~15 barras finales."""
    close, high, low = sym_data["close"], sym_data["high"], sym_data["low"]
    sw = zigzag(high, low, close, atr_arr)
    if len(sw) < 3:
        return None
    best = None
    for det in DETECTORS:
        d = det(sw, close)
        if d and d["formed_bars_ago"] <= recent_bars:
            if best is None or d["confidence"] > best["confidence"]:
                best = d
    if best:
        best["last_close"] = round(float(close[-1]), 2)
        for kk in ("trigger_level","target","stop"):
            best[kk] = round(float(best[kk]), 2)
    return best

def process(sym):
    """Devuelve (active_dict_or_None, {pattern_type: outcomes[]}) o (None, None) si falla."""
    try:
        data = fetch(sym)
        if data is None:
            return None, None, "sin datos"
        a = atr(data["high"], data["low"], data["close"])
        active = detect_active(data, a)
        hist = scan_history(data, a)
        return active, hist, None
    except Exception as e:
        return None, None, f"error: {e}"

# ----------------------------------------------------------------------------- main
def main():
    args = sys.argv[1:]
    if not args:
        print("uso: pattern_detect.py SYM [SYM2 ...]  |  --fleet")
        return
    fleet_mode = "--fleet" in args
    syms = FLEET if fleet_mode else [a.upper() for a in args if not a.startswith("--")]
    if not syms:
        syms = FLEET

    per_ticker = {}    # sym -> (active, hist, err)
    pooled = {pt: [] for pt in PATTERN_TYPES}
    for s in syms:
        active, hist, err = process(s)
        per_ticker[s] = (active, hist, err)
        if hist:
            for pt in PATTERN_TYPES:
                pooled[pt].extend(hist[pt])

    out = {}
    print("="*72)
    print("DETECTOR DE PATRONES — geometria algoritmica + tasa EMPIRICA (2y diario)")
    print("="*72)
    for s in syms:
        active, hist, err = per_ticker[s]
        if err:
            print(f"\n{s}: {err} (saltado, no rompe el run)")
            out[s] = {"active": None, "empirical": {}, "error": err}
            continue

        # empirico por-ticker; si n<8 usamos pool de la corrida
        emp = {}
        for pt in PATTERN_TYPES:
            own = hist[pt]
            blk = rate_block(own)
            if blk["n"] < 8:
                pool_blk = rate_block(pooled[pt])
                if pool_blk["n"] > blk["n"]:
                    pool_blk["source"] = "pooled"
                    pool_blk["own_n"] = blk["n"]
                    blk = pool_blk
            emp[pt] = blk

        # reporte del patron activo
        print(f"\n----- {s}  (ultimo close {active['last_close'] if active else '—'}) -----")
        if not active:
            print("  Sin patron formandose en las ultimas ~15 barras.")
        else:
            pt = active["pattern"]
            e = emp.get(pt, {"n":0,"rate":None})
            n = e.get("n",0); rate = e.get("rate")
            tradeable = active["confidence"] >= 0.5 and n >= 8
            tag = "ACTIVO/OPERABLE" if tradeable else \
                  "detectado pero sin muestra suficiente — solo contexto"
            arrow = "bajista" if active["direction"]=="bear" else "alcista"
            print(f"  Patron: {pt} ({arrow})  [{tag}]")
            print(f"    conf {active['confidence']}  formado hace {active['formed_bars_ago']} barras")
            print(f"    gatillo {active['trigger_level']}  ->  target {active['target']}  | stop {active['stop']}")
            if rate is None:
                print(f"    empirico: sin muestra — no fiable (n=0)")
            else:
                src = e.get("source","propio")
                extra = f" [{src}, propio n={e.get('own_n',n)}]" if src=="pooled" else ""
                print(f"    empirico: {rate*100:.1f}% acierto  (n={n}){extra}")

        # resumen empirico compacto de todos los tipos
        emp_clean = {}
        for pt, blk in emp.items():
            emp_clean[pt] = {"n": blk["n"], "rate": blk.get("rate")}
            if blk.get("source"): emp_clean[pt]["source"] = blk["source"]
        out[s] = {"active": active, "empirical": emp_clean}

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print("\n" + "="*72)
    print(f"Escrito: {OUT_JSON}")
    print("DISCLAIMER: los patrones son señales PROBABILISTICAS que a veces se forman —")
    print("NO garantias. Operar solo con confianza>=0.5 Y n>=8; el resto es contexto.")
    print("="*72)

if __name__ == "__main__":
    main()
