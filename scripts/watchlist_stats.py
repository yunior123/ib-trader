#!/usr/bin/env python3
"""watchlist_stats — productor STANDALONE de estadísticas TradingView-like para
la lista/watchlist del cockpit (charts/live.html) y cualquier consumidor.

Escribe data/watchlist_stats.json con, por cada símbolo de la flota
(data/fleet.txt) + la lista del usuario (data/watchlist_user.txt):

    { "NVDA": {"price":206.84,"prev_close":208.76,"pct":-0.92,"vol":58500000,
               "pct_fmt":"-0.92%","vol_fmt":"58.5M","src":"finnhub+ibkr",
               "vol_asof":"2026-07-24","ts":1784923200},
      ...,
      "_meta": {"ts":..., "generated":"...", "ok":28, "empty":2,
                "empty_syms":["..."], "source":"finnhub|finviz + ibkr-bars"} }

FUENTES REALTIME ÚNICAMENTE (AGENTS ley #6 — jamás yahoo/delayed):
  * %cambio del día y prev_close  -> Finnhub /quote (precio realtime + cierre
    previo REAL; TradingView mide vs cierre previo, no vs apertura).
    Fallback: cache Finviz Elite (data/finviz_<sym>.txt, campos price/change).
  * volumen del día               -> suma del volumen de las barras IBKR de HOY
    (data/bars_<sym>_ibkr.txt, feed realtime de la flota).
    Fallback: cache Finviz Elite (campo volume).

FALLAR EN VOZ ALTA: si ninguna fuente realtime responde para un símbolo, su
entrada queda con valores null y se lista en _meta.empty_syms + stderr. JAMÁS se
degrada en silencio a un dato delayed.

No es camino de órdenes — SEÑAL-SOLAMENTE. No toca charts/live.html ni
scripts/chart_bridge.py (otro agente los posee); solo escribe el .json que ellos
pueden leer y fusionar.

Uso:
  python3 scripts/watchlist_stats.py            # one-shot (default)
  python3 scripts/watchlist_stats.py --once     # idem, explícito
  python3 scripts/watchlist_stats.py --loop     # keepalive (RTH 60s, si no 180s)
  python3 scripts/watchlist_stats.py --loop --interval 45
  python3 scripts/watchlist_stats.py --syms NVDA MU  # subconjunto (debug)
"""
import json
import os
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "watchlist_stats.json")

_FINNHUB_KEY = None


def _load_finnhub_key():
    global _FINNHUB_KEY
    if _FINNHUB_KEY is not None:
        return _FINNHUB_KEY
    _FINNHUB_KEY = ""
    envp = os.path.join(REPO, "config", "feeds.env")
    if os.path.exists(envp):
        for line in open(envp):
            line = line.strip()
            if line.startswith("FINNHUB_KEY="):
                _FINNHUB_KEY = line.split("=", 1)[1].strip().strip('"')
    return _FINNHUB_KEY


def fleet():
    p = os.path.join(REPO, "data", "fleet.txt")
    try:
        return [s.upper() for s in open(p).read().split() if s.strip()]
    except Exception:
        return []


def user_watchlist():
    p = os.path.join(REPO, "data", "watchlist_user.txt")
    try:
        return [s.upper() for s in open(p).read().split() if s.strip()]
    except Exception:
        return []


def fmt_vol(v):
    """Igual que fmtVol() de charts/live.html — 1.2B / 58.5M / 903K."""
    if v is None:
        return ""
    v = float(v)
    if v >= 1e9:
        return f"{v/1e9:.1f}B"
    if v >= 1e6:
        return f"{v/1e6:.1f}M"
    if v >= 1e3:
        return f"{v/1e3:.0f}K"
    return str(int(v))


def fmt_pct(p):
    if p is None:
        return ""
    return f"{'+' if p > 0 else ''}{p:.2f}%"


# ---- fuentes realtime -------------------------------------------------------
def finnhub_quote(sym):
    """price + prev_close realtime desde Finnhub /quote. None si falla."""
    key = _load_finnhub_key()
    if not key:
        return None
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={sym}&token={key}"
        with urllib.request.urlopen(url, timeout=5) as r:
            q = json.load(r)
        if not q or not q.get("c"):
            return None
        price = float(q["c"])
        prev = float(q.get("pc") or 0)
        if price <= 0 or prev <= 0:
            return None
        return {"price": round(price, 4), "prev_close": round(prev, 4),
                "ts": int(q.get("t") or time.time())}
    except Exception:
        return None


def ibkr_today_volume(sym):
    """Volumen acumulado del día desde las barras IBKR realtime de la flota.
    Devuelve (vol:int, asof:'YYYY-MM-DD') o (None, None). El 'día' es la fecha
    local de la última barra (si el mercado está cerrado, es la última sesión —
    igual que TradingView cuando está cerrado)."""
    p = os.path.join(REPO, f"data/bars_{sym.lower()}_ibkr.txt")
    try:
        rows = [ln.split() for ln in open(p) if ln.strip()]
        c = [(int(r[0]), float(r[5])) for r in rows if len(r) >= 6]
    except Exception:
        return None, None
    if not c:
        return None, None
    last_day = time.strftime("%Y-%m-%d", time.localtime(c[-1][0]))
    vol = sum(v for t, v in c if time.strftime("%Y-%m-%d", time.localtime(t)) == last_day)
    return int(vol), last_day


def finviz_cache(sym):
    """Cache Finviz Elite realtime (data/finviz_<sym>.txt). Devuelve dict con
    los campos disponibles: price, pct (change), vol (volume), ts. {} si no hay."""
    p = os.path.join(REPO, f"data/finviz_{sym.lower()}.txt")
    if not os.path.exists(p):
        return {}
    kv = {}
    try:
        for ln in open(p):
            if "=" in ln:
                k, v = ln.strip().split("=", 1)
                kv[k] = v
    except Exception:
        return {}
    out = {}
    try:
        if kv.get("price"):
            out["price"] = float(kv["price"])
    except Exception:
        pass
    try:
        if kv.get("change"):
            out["pct"] = float(kv["change"].replace("%", "").strip())
    except Exception:
        pass
    try:
        if kv.get("volume"):
            out["vol"] = int(float(kv["volume"]))
    except Exception:
        pass
    try:
        out["ts"] = int(kv.get("ts") or 0)
    except Exception:
        out["ts"] = 0
    return out


# ---- ensamblaje -------------------------------------------------------------
def stats_for(sym):
    """Estadística TradingView-like de un símbolo, solo fuentes realtime.
    Devuelve un dict siempre; con null si no hay dato fresco (fallar en voz alta)."""
    price = prev_close = pct = vol = None
    vol_asof = None
    ts = int(time.time())
    src = []

    q = finnhub_quote(sym)
    if q:
        price = q["price"]
        prev_close = q["prev_close"]
        pct = round((price - prev_close) / prev_close * 100, 2)
        ts = q["ts"]
        src.append("finnhub")

    vol, vol_asof = ibkr_today_volume(sym)
    if vol is not None:
        src.append("ibkr")

    # Fallback Finviz Elite (realtime) para lo que falte.
    if pct is None or vol is None:
        fv = finviz_cache(sym)
        if pct is None and fv.get("pct") is not None:
            pct = round(fv["pct"], 2)
            if price is None and fv.get("price") is not None:
                price = fv["price"]
            src.append("finviz")
        if vol is None and fv.get("vol") is not None:
            vol = fv["vol"]
            vol_asof = time.strftime("%Y-%m-%d", time.localtime(fv.get("ts") or ts))
            if "finviz" not in src:
                src.append("finviz")

    return {
        "price": price,
        "prev_close": prev_close,
        "pct": pct,
        "vol": vol,
        "pct_fmt": fmt_pct(pct),
        "vol_fmt": fmt_vol(vol),
        "vol_asof": vol_asof,
        "src": "+".join(src) if src else "none",
        "ts": ts,
    }


def build(syms):
    out = {}
    empty = []
    for s in syms:
        st = stats_for(s)
        out[s] = st
        if st["pct"] is None and st["vol"] is None:
            empty.append(s)
    ok = len(syms) - len(empty)
    out["_meta"] = {
        "ts": int(time.time()),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": ok,
        "empty": len(empty),
        "empty_syms": empty,
        "source": "finnhub|finviz (pct/prev_close) + ibkr-bars|finviz (vol)",
    }
    return out, empty


def write_atomic(obj):
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, OUT)


def run_once(syms):
    obj, empty = build(syms)
    write_atomic(obj)
    m = obj["_meta"]
    print(f"[watchlist_stats] {m['ok']}/{len(syms)} ok -> {OUT}", file=sys.stderr)
    if empty:
        # Fallar EN VOZ ALTA: símbolos sin fuente realtime quedan null, jamás delayed.
        print(f"[watchlist_stats] SIN DATO REALTIME ({len(empty)}): {' '.join(empty)}",
              file=sys.stderr)
    return len(empty)


def _rth_now():
    """True si estamos ~en horario extendido/RTH ET (04:00-20:00). Aproxima con
    hora local; solo ajusta el intervalo del loop, no filtra datos."""
    lt = time.localtime()
    # ET ~= local del usuario (Toronto). Ventana amplia premarket->afterhours.
    return 4 <= lt.tm_hour < 20 and lt.tm_wday < 5


def main():
    args = sys.argv[1:]
    loop = "--loop" in args
    interval = None
    if "--interval" in args:
        try:
            interval = int(args[args.index("--interval") + 1])
        except Exception:
            interval = None
    syms = None
    if "--syms" in args:
        i = args.index("--syms")
        syms = [a.upper() for a in args[i + 1:] if not a.startswith("--")]
    if not syms:
        seen = dict.fromkeys(fleet() + user_watchlist())
        syms = list(seen)
    if not syms:
        print("[watchlist_stats] flota vacía (data/fleet.txt) — nada que hacer",
              file=sys.stderr)
        return 1

    if not loop:
        run_once(syms)
        return 0

    while True:
        try:
            run_once(syms)
        except Exception as e:
            print(f"[watchlist_stats] error de ciclo: {e}", file=sys.stderr)
        time.sleep(interval or (60 if _rth_now() else 180))


if __name__ == "__main__":
    sys.exit(main())
