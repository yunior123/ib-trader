#!/usr/bin/env python3
"""signal_conditioning.py — capa que CONDICIONA la probabilidad de cada señal por tres
dimensiones (orden Yunior 2026-07-24: "si la flota tiende abajo y la señal dice arriba,
reflejarlo en el porcentaje; condicionar como el motor NVDA o mejor"):

  1. HORA DEL DÍA  (MEDIDO): factor de data/timeofday_factors.json (Wilson+shrinkage sobre
     nuestro propio backtest). El lunch-lull 11:30-14:00 y el power-hour salen de la data.
  2. DIRECCIÓN-FLOTA (DOCTRINA + vivo): jerarquía de capitanes CLAUDE.md — SPY/QQQ mercado,
     SMH semis. Si la señal va CONTRA el capitán que la gobierna -> penaliza fuerte o VETA
     (banner sin voz). Si concuerda -> refuerza. (No es WR medido aún: el harness no
     reconstruye snapshots de flota históricos; se declara como doctrina, no como medida.)
  3. INFLACIÓN (MEDIDO fundamentals): data/inflation_score.json. Inflada + señal bajista =
     amplifica; inflada + señal alcista = frena; barata/creciendo al revés.

Además aplica el APAGADO EN DURO de celdas muertas (data/signal_enable.json) y dos VETOS de
doctrina: la subasta 9:30-9:45 (jamás operar) y el capitán en contra.

  conditioned_prob(source, symbol, direction, base_prob, now_min=None) -> dict
     direction: +1 alcista / -1 bajista ; base_prob en %
     -> {prob, enabled, veto, speak, factors{...}, why[...]}
  should_speak = enabled AND not veto AND prob >= SPEAK_MIN

Degradación limpia: si falta cualquier .json, ese factor = 1.0 (neutro) y sigue.
SEÑAL-SOLAMENTE (solo lee data + bars; no dispara ni ejecuta nada).
"""
import os, sys, json, time, statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

SPEAK_MIN = float(os.environ.get("COND_SPEAK_MIN", "55"))   # umbral de voz (prob condicionada)
CAPTAINS = {"SPY", "QQQ", "SMH"}
SEMIS = {"NVDA", "AMD", "AVGO", "ASML", "TSM", "TXN", "QCOM", "LRCX", "INTC", "MU",
         "SKHY", "SNDK", "STX", "WDC", "SMH", "DRAM", "NOK"}
_CACHE = {"fleet": None, "fleet_ts": 0}


def _load(path, default):
    try:
        return json.load(open(os.path.join(REPO, path)))
    except Exception:
        return default


def _now_min():
    lt = time.localtime()
    return lt.tm_hour * 60 + lt.tm_min


def _bucket(now_min):
    from timeofday_calib import BUCKETS
    for name, lo, hi in BUCKETS:
        if lo <= now_min < hi:
            return name
    return None


def _mom(sym, n=6):
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(p):
        return None
    try:
        c = [float(l.split()[4]) for l in open(p) if l.strip()]
    except Exception:
        return None
    if len(c) < n + 1:
        return None
    return 100 * (c[-1] - c[-1 - n]) / c[-1 - n]


def _closes(sym):
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(p):
        return []
    try:
        return [float(l.split()[4]) for l in open(p) if l.strip()]   # space-delim: epoch o h l c v
    except Exception:
        return []


def component_bias(index, n=6, max_age=20):
    """Sesgo LOCAL y RÁPIDO de los componentes de QQQ/SPY (momentum ponderado desde bars
    locales, SIN red). Cache. -> score [-1..1]. Reemplaza el breadth() lento (yfinance 4s)."""
    key = f"comp_{index}"
    if _CACHE.get(key) and time.time() - _CACHE.get(key + "_ts", 0) < max_age:
        return _CACHE[key]
    try:
        import index_breadth
        W = index_breadth.WEIGHTS.get(index.upper(), {})
    except Exception:
        W = {}
    num = den = 0.0
    for sym, w in W.items():
        c = _closes(sym)
        if len(c) < n + 1:
            continue
        mom = (c[-1] - c[-1 - n]) / c[-1 - n] * 100
        num += max(-1.0, min(1.0, mom / 0.5)) * w
        den += w
    score = round(num / den, 3) if den else 0.0
    _CACHE[key] = score; _CACHE[key + "_ts"] = time.time()
    return score


def captain_flow_bias(window_min=8, max_age=15):
    """Sesgo por SPIKES de opciones de los CAPITANES (SPY/QQQ/SMH) en tiempo real, del ledger
    de señales (orden Yunior 2026-07-24: "spike calls/puts en SPY/QQQ/SMH influyen dirección,
    real time"). Doctrina: SPIKE/BALLENA PUTS del capitán = rebote ALCISTA; CALLS = techo BAJISTA.
    -> {'SPY':x,'QQQ':x,'SMH':x,'market':avg,'semis':x} en [-1..1]. Cache 15s."""
    if _CACHE.get("cflow") and time.time() - _CACHE.get("cflow_ts", 0) < max_age:
        return _CACHE["cflow"]
    import datetime as dt
    out = {c: 0.0 for c in CAPTAINS}
    path = os.path.join(REPO, "data", "trading-signals", f"{dt.date.today():%Y-%m-%d}.txt")
    now = time.localtime(); now_s = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    try:
        for ln in open(path):
            if "SPIKE" not in ln and "BALLENA" not in ln:
                continue
            up = ln.upper()
            cap = next((c for c in CAPTAINS if c in up), None)
            if not cap:
                continue
            try:
                hh, mm, ss = (int(x) for x in ln[:8].split(":"))
                age = now_s - (hh * 3600 + mm * 60 + ss)
            except Exception:
                age = 0
            if age < 0 or age > window_min * 60:
                continue
            recency = max(0.3, 1 - age / (window_min * 60))
            # PUTS del capitán = piso -> alcista (+) ; CALLS = techo -> bajista (-)
            sign = 1.0 if "PUTS" in up else -1.0 if "CALLS" in up else 0.0
            out[cap] = max(-1.0, min(1.0, out[cap] + sign * recency))
    except Exception:
        pass
    mk = 0.0
    if out.get("SPY") or out.get("QQQ"):
        mk = (out.get("SPY", 0) + out.get("QQQ", 0)) / 2
    out["market"] = round(mk, 3); out["semis"] = round(out.get("SMH", 0.0), 3)
    _CACHE["cflow"] = out; _CACHE["cflow_ts"] = time.time()
    return out


def fleet_bias(max_age=30):
    """Dirección de los capitanes AHORA: side-of-flip + momentum. Cache 30s.
    -> {'SPY':+1/-1/0, 'QQQ':..., 'SMH':..., 'market':dir, 'semis':dir} (0 = mudo)."""
    if _CACHE["fleet"] and time.time() - _CACHE["fleet_ts"] < max_age:
        return _CACHE["fleet"]
    import chart_levels
    out = {}
    for s in CAPTAINS:
        try:
            r = [l.split() for l in open(os.path.join(REPO, f"data/bars_{s.lower()}_ibkr.txt")) if l.strip()]
            c = [float(x[4]) for x in r]
            if len(c) < 7:
                out[s] = 0; continue
            spot = c[-1]
            lv = chart_levels.gen(s, spot=spot, write=False)
            flip = lv.get("flip") if lv else None
            side = 0
            if flip:
                side = 1 if spot >= flip else -1
            mom = 100 * (c[-1] - c[-6]) / c[-6]
            # confirmar side con momentum: si contradicen fuerte, mudo
            if side > 0 and mom < -0.10:
                side = 0
            elif side < 0 and mom > 0.10:
                side = 0
            out[s] = side
        except Exception:
            out[s] = 0
    # mercado = SPY y QQQ de acuerdo ; semis = SMH
    mk = 0
    if out.get("SPY", 0) == out.get("QQQ", 0) and out.get("SPY", 0) != 0:
        mk = out["SPY"]
    out["market"] = mk
    out["semis"] = out.get("SMH", 0)
    _CACHE["fleet"] = out; _CACHE["fleet_ts"] = time.time()
    return out


def governing_captain(symbol):
    """Qué capitán gobierna a este símbolo: SMH si es semi, si no el mercado (SPY/QQQ)."""
    s = symbol.upper()
    if s in ("SPY", "QQQ"):
        return "market", None            # es capitán de mercado; no lo gobierna otro
    if s == "SMH":
        return "semis", None
    if s in SEMIS:
        return "semis", "SMH"
    return "market", "SPY/QQQ"


def conditioned_prob(source, symbol, direction, base_prob, now_min=None):
    source = (source or "").lower(); symbol = (symbol or "").upper()
    direction = 1 if direction >= 0 else -1
    if now_min is None:
        now_min = _now_min()
    factors = {}
    why = []

    # --- 1. HORA DEL DÍA (medido) ---
    tof = _load("data/timeofday_factors.json", {})
    bkt = _bucket(now_min)
    f_time = 1.0
    if source in tof and bkt and bkt in tof[source]:
        f_time = tof[source][bkt].get("factor", 1.0)
        why.append(f"hora {bkt}: ×{f_time} (medido WR {tof[source][bkt].get('wr','?')}%)")
    factors["time"] = f_time

    # --- 2. DIRECCIÓN-FLOTA (doctrina viva) ---
    fb = fleet_bias()
    gov_key, gov_name = governing_captain(symbol)
    cap_dir = fb.get(gov_key, 0)
    f_fleet = 1.0
    veto = False
    if cap_dir != 0 and symbol not in ("SPY", "QQQ", "SMH"):
        if cap_dir == direction:
            f_fleet = 1.12
            why.append(f"capitán {gov_name or gov_key} A FAVOR: ×1.12")
        else:
            f_fleet = 0.55
            veto = True                  # capitán en contra = banner sin voz (regla #12)
            why.append(f"⛔ capitán {gov_name or gov_key} EN CONTRA -> VETO voz (×0.55)")
    # QQQ/SPY: cubrir vía sus componentes pesados (MSFT/AMZN/TSLA...) — LOCAL rápido, sin red
    if symbol in ("QQQ", "SPY"):
        comp = component_bias(symbol)                                # -1..+1
        if abs(comp) > 0.08:
            agree = (comp > 0) == (direction > 0)
            f_comp = 1.10 if agree else 0.72
            f_fleet *= f_comp
            why.append(f"componentes {symbol} {'a favor' if agree else 'EN CONTRA'} "
                       f"({comp:+.2f}): ×{round(f_comp,2)}")

    # SPIKES de opciones de capitanes en tiempo real (SPY/QQQ/SMH) influyen la dirección
    cf = captain_flow_bias()
    cf_gov = cf.get(gov_key, 0.0)
    if abs(cf_gov) > 0.25 and symbol not in ("SPY", "QQQ", "SMH"):
        agree = (cf_gov > 0) == (direction > 0)
        f_flow = 1.10 if agree else 0.80
        f_fleet *= f_flow
        why.append(f"spike-flow capitán {'a favor' if agree else 'en contra'} "
                   f"({cf_gov:+.2f}): ×{round(f_flow,2)}")
    factors["fleet"] = round(f_fleet, 3)

    # --- 3. INFLACIÓN (medido fundamentals) ---
    infl = _load("data/inflation_score.json", {})
    f_infl = 1.0
    row = infl.get(symbol) if isinstance(infl, dict) else None
    if row and row.get("score") is not None:
        sc = row["score"]                 # +inflada / -barata
        # inflada + bajista => acelera (>1) ; inflada + alcista => frena (<1)
        adj = -sc * direction * 0.12      # hasta ±12%
        f_infl = max(0.85, min(1.15, 1 + adj))
        if abs(sc) > 0.33:
            tag = "inflada" if sc > 0 else "barata/creciendo"
            why.append(f"valuación {tag} ({sc:+.2f}) señal {'↑' if direction>0 else '↓'}: ×{round(f_infl,2)}")
    factors["inflation"] = round(f_infl, 3)

    # --- combinación + clamps ---
    prob = base_prob * f_time * f_fleet * f_infl
    prob = max(5, min(92, prob))

    # --- apagado en duro + vetos de doctrina ---
    enable = _load("data/signal_enable.json", {})
    cell = enable.get(f"{source}|{symbol}")
    enabled = True
    if cell and not cell.get("enabled", True):
        enabled = False
        why.append(f"🔴 celda apagada ({cell.get('why','muerta')})")
    if bkt == "auction":
        veto = True
        why.append("⛔ subasta 9:30-9:45: jamás operar (veto doctrina)")

    speak = enabled and (not veto) and prob >= SPEAK_MIN
    return dict(prob=int(round(prob)), base=int(round(base_prob)), enabled=enabled,
                veto=veto, speak=speak, bucket=bkt, factors=factors,
                fleet=fb, why=why)


def _cli():
    a = sys.argv[1:]
    if not a:
        print("uso: signal_conditioning.py SOURCE SYMBOL DIR[+1/-1] BASE_PROB [now_min]")
        print("     signal_conditioning.py --fleet   (dirección de capitanes ahora)")
        return
    if a[0] == "--fleet":
        print(json.dumps(fleet_bias(), indent=1)); return
    source, symbol, d, base = a[0], a[1], int(a[2]), float(a[3])
    now = int(a[4]) if len(a) > 4 else None
    r = conditioned_prob(source, symbol, d, base, now)
    print(f"=== {source} {symbol} dir {'↑' if d>0 else '↓'} base {base:.0f}% -> COND {r['prob']}% "
          f"[{'HABLA' if r['speak'] else 'silenciosa'}{' VETO' if r['veto'] else ''}"
          f"{' APAGADA' if not r['enabled'] else ''}] bucket={r['bucket']}")
    print(f"    factores: {r['factors']}")
    for w in r["why"]:
        print(f"    · {w}")


if __name__ == "__main__":
    _cli()
