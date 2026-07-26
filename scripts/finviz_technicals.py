#!/usr/bin/env python3
"""finviz_technicals.py — technicals por ticker (Finviz Elite v=171 + fallback
yfinance) para el widget nuevo del chart (TODOS.md ~205, Yunior 2026-07-25).

SOLO capa de datos: fetch + cache + procedencia. NADA de charts/live.html ni
chart_bridge.py (los toca otro agente). Uso previsto: `get_technicals(sym)`
on-demand por el ticker activo del chart (regla de Yunior: "solo el grafico
principal por defecto, los demas widgets bajo demanda" -> no hay loop/daemon
aqui, cada llamada es un fetch de UN simbolo).

Finviz v=171 da: Beta, ATR(14), SMA20/50/200 (distancia % al precio, no nivel
absoluto), 52W hi/lo (idem), RSI(14), Price, Change, ChangeFromOpen, Gap,
Volume. `nivel = price / (1 + pct/100)` recupera el nivel absoluto.
Finviz NO es tiempo real: `src`+`feed_ts` viajan dentro del dato siempre;
`feed_age_s` se recalcula en cada lectura, no se congela en el fichero.

SEÑAL-SOLAMENTE. Ningun fallo se disfraza de 0/0.0/{} — clave ausente o excepcion.
"""
import csv
import io
import json
import os
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
DEFAULT_TTL_S = 60          # doctrina finviz-elite: min 60s entre requests
V = 171
COLNAMES = ("Beta", "Average True Range", "20-Day Simple Moving Average",
            "50-Day Simple Moving Average", "200-Day Simple Moving Average",
            "52-Week High", "52-Week Low", "Relative Strength Index (14)",
            "Price", "Change", "Change from Open", "Gap", "Volume")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finviz_auth_check as fac  # noqa: E402  (reuso judge(): NO se toca ese fichero)


class TechnicalsUnavailable(Exception):
    """Ni Finviz ni yfinance ni cache -> no hay dato. Nunca se fabrica uno."""


def token():
    t = os.environ.get("FINVIZ_AUTH3", "").strip()
    if t:
        return t
    try:
        for ln in open(os.path.join(REPO, "feeds.env")):
            ln = ln.strip()
            if ln.startswith("FINVIZ_AUTH3="):
                return ln.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return None


def _pct(s):
    """'1.73%' -> 1.73 ; '' / '-' / None -> None (ausente, jamas 0.0)."""
    s = (s or "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s.rstrip("%"))
    except ValueError:
        return None


def _num(s):
    s = (s or "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _level_from_pct(price, pct):
    """Finviz da SMA/52w como distancia %; nivel = price/(1+pct/100)."""
    if price is None or pct is None or (1 + pct / 100.0) == 0:
        return None
    return round(price / (1 + pct / 100.0), 4)


def parse_finviz_csv(body):
    """CSV crudo -> {SYM: {campo: valor}}. Levanta si el header no es el
    esperado (feed movido/roto) — jamas parsea a ciegas."""
    r = csv.reader(io.StringIO(body))
    try:
        header = next(r)
    except StopIteration:
        raise TechnicalsUnavailable("finviz_technicals: CSV vacio")
    for want in COLNAMES:
        if want not in header:
            raise TechnicalsUnavailable(
                f"finviz_technicals: columna '{want}' ausente del header (v={V} cambio)")
    idx = {name: header.index(name) for name in COLNAMES}
    ticker_i = header.index("Ticker")
    out = {}
    for row in r:
        if len(row) < len(header):
            continue
        sym = row[ticker_i].strip().upper()
        price = _num(row[idx["Price"]])
        d = {"price": price,
             "beta": _num(row[idx["Beta"]]),
             "atr14": _num(row[idx["Average True Range"]]),
             "rsi14": _num(row[idx["Relative Strength Index (14)"]]),
             "change_pct": _pct(row[idx["Change"]]),
             "change_from_open_pct": _pct(row[idx["Change from Open"]]),
             "gap_pct": _pct(row[idx["Gap"]]),
             "volume": _num(row[idx["Volume"]])}
        for key, colname in (("sma20", "20-Day Simple Moving Average"),
                             ("sma50", "50-Day Simple Moving Average"),
                             ("sma200", "200-Day Simple Moving Average"),
                             ("wk52_hi", "52-Week High"),
                             ("wk52_lo", "52-Week Low")):
            pct = _pct(row[idx[colname]])
            if pct is not None:
                d[f"{key}_pct"] = pct
                lvl = _level_from_pct(price, pct)
                if lvl is not None:
                    d[key] = lvl
        d = {k: v for k, v in d.items() if v is not None}   # clave ausente, no 0/None
        out[sym] = d
    return out


def fetch_finviz(tickers, auth, timeout=20):
    """GET crudo. Levanta en cualquier fallo de red (el llamador decide fallback)."""
    url = (f"https://elite.finviz.com/export/screener?v={V}"
           f"&t={','.join(t.upper() for t in tickers)}&auth={auth}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.status
        body = resp.read().decode("utf-8", "replace")
    return status, body


def fetch_technicals_finviz(tickers):
    auth = token()
    if not auth:
        raise TechnicalsUnavailable("finviz_technicals: sin FINVIZ_AUTH3 (env ni feeds.env)")
    try:
        status, body = fetch_finviz(tickers, auth)
    except Exception as e:
        raise TechnicalsUnavailable(f"finviz_technicals: fetch fallo ({type(e).__name__}: {e})")
    sano, motivo = fac.judge(status, body, min_rows=len(tickers))
    if not sano:
        # doctrina: si da 403 (token caduca sabado) u otro fallo, se dice y se sigue (fallback)
        raise TechnicalsUnavailable(f"finviz_technicals: respuesta no sana ({motivo})")
    return parse_finviz_csv(body)


# --------------------------- fallback yfinance -------------------------------
def _wilder_rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0); losses += max(-ch, 0.0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0.0)) / n
        al = (al * (n - 1) + max(-ch, 0.0)) / n
    if ag + al == 0:
        return 50.0
    if al == 0:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + ag / al), 2)


def _wilder_atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return round(atr, 4)


def _sma(vals, n):
    if len(vals) < n:
        return None
    return round(sum(vals[-n:]) / n, 4)


def fetch_technicals_yfinance(sym):
    """Fallback declarado por Yunior. Historia insuficiente -> clave ausente,
    jamas 0/None disfrazado."""
    try:
        import yfinance as yf
    except Exception as e:
        raise TechnicalsUnavailable(f"finviz_technicals: yfinance no disponible ({type(e).__name__})")
    try:
        hist = yf.Ticker(sym).history(period="1y", interval="1d", auto_adjust=False)
    except Exception as e:
        raise TechnicalsUnavailable(f"finviz_technicals: yfinance fetch fallo ({type(e).__name__}: {e})")
    if hist is None or hist.empty or len(hist) < 15:
        raise TechnicalsUnavailable(f"finviz_technicals: yfinance sin historia util para {sym}")
    closes = hist["Close"].tolist()
    highs = hist["High"].tolist()
    lows = hist["Low"].tolist()
    opens = hist["Open"].tolist()
    vols = hist["Volume"].tolist()
    price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else None
    today_open = opens[-1]
    d = {"price": round(price, 4), "volume": int(vols[-1])}
    atr = _wilder_atr(highs, lows, closes)
    if atr is not None:
        d["atr14"] = atr
    rsi = _wilder_rsi(closes)
    if rsi is not None:
        d["rsi14"] = rsi
    for key, n in (("sma20", 20), ("sma50", 50), ("sma200", 200)):
        v = _sma(closes, n)
        if v is not None:
            d[key] = v
    lookback = highs[-252:] if len(highs) >= 252 else highs
    lookback_lo = lows[-252:] if len(lows) >= 252 else lows
    if lookback:
        d["wk52_hi"] = round(max(lookback), 4)
    if lookback_lo:
        d["wk52_lo"] = round(min(lookback_lo), 4)
    if prev_close:
        d["change_pct"] = round((price - prev_close) / prev_close * 100, 3)
        d["gap_pct"] = round((today_open - prev_close) / prev_close * 100, 3)
    if today_open:
        d["change_from_open_pct"] = round((price - today_open) / today_open * 100, 3)
    try:
        beta = yf.Ticker(sym).info.get("beta")
        if beta is not None:
            d["beta"] = float(beta)
    except Exception:
        pass   # beta es adorno; su ausencia de red no puede tumbar el resto del dato
    return d


# ------------------------------- orquestador ----------------------------------
def _cache_path(sym, data_dir):
    return os.path.join(data_dir, f"finviz_tech_{sym.lower()}.json")


def _load_cache(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=1)
    os.replace(tmp, path)


def get_technicals(sym, ttl_s=DEFAULT_TTL_S, data_dir=None):
    """Cache -> Finviz -> yfinance -> cache-viejo-como-ultimo-recurso -> excepcion.
    Devuelve SIEMPRE con feed_age_s recalculado AHORA (nunca congelado en disco)."""
    sym = sym.upper()
    data_dir = data_dir or DATA
    path = _cache_path(sym, data_dir)
    cached = _load_cache(path)
    now = time.time()
    if cached and (now - cached.get("feed_ts", 0)) < ttl_s:
        out = dict(cached)
        out["feed_age_s"] = round(now - cached["feed_ts"], 1)
        return out

    errores = []
    fields = None
    src = None
    try:
        fields = fetch_technicals_finviz([sym]).get(sym)
        if fields:
            src = "finviz"
    except TechnicalsUnavailable as e:
        errores.append(str(e))
        print(str(e), file=sys.stderr)

    if fields is None:
        try:
            fields = fetch_technicals_yfinance(sym)
            src = "yfinance"
        except TechnicalsUnavailable as e:
            errores.append(str(e))
            print(str(e), file=sys.stderr)

    if fields is None:
        if cached is not None:
            out = dict(cached)
            out["feed_age_s"] = round(now - cached.get("feed_ts", now), 1)
            out["stale"] = True
            print(f"finviz_technicals: {sym} sirve cache VIEJO ({out['feed_age_s']:.0f}s) "
                  f"tras fallar Finviz y yfinance", file=sys.stderr)
            return out
        raise TechnicalsUnavailable(
            f"finviz_technicals: {sym} sin dato (Finviz y yfinance fallaron, sin cache) — "
            + " | ".join(errores))

    payload = dict(fields)
    payload["sym"] = sym
    payload["src"] = src
    payload["feed_ts"] = now
    _write_cache(path, payload)
    out = dict(payload)
    out["feed_age_s"] = 0.0
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("uso: finviz_technicals.py SYM [SYM2 ...] [--ttl N]", file=sys.stderr)
        return 2
    ttl = DEFAULT_TTL_S
    for a in sys.argv[1:]:
        if a.startswith("--ttl="):
            ttl = int(a.split("=", 1)[1])
    rc = 0
    for sym in args:
        try:
            print(json.dumps(get_technicals(sym, ttl_s=ttl), indent=1))
        except TechnicalsUnavailable as e:
            print(str(e), file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
