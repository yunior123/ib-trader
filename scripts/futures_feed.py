#!/usr/bin/env python3
"""futures_feed.py — el mapa de HUECO de la noche: futuros CME + la apertura US que implican.

Por que existe: entre el cierre del viernes y las 09:30 del lunes, las acciones US no imprimen
NADA (medido 2026-08-02 21:18 ET: el ultimo print de SPY/QQQ/NVDA/AAPL era del viernes 19:59, y
el WebSocket de Finnhub, conectado y suscrito a 26 simbolos, llevaba 0 trades). Lo unico que
cotiza en EE.UU. esa noche son los FUTUROS: CME abre domingo 18:00 ET. Si la casa se especializa
en anticipar movimientos, esa es la unica ventana que existe antes de la apertura.

FUENTES, por orden y con su retraso MEDIDO (2026-08-02 21:21 ET):
  1. Databento GLBX.MDP3 (historico)  — datos reales de CME MDP3, disponibles hasta 01:20 UTC
     cuando eran las 01:32 UTC: **~12 min de retraso**. Es la buena: OHLCV exacto, sin scraping.
     El API LIVE de Databento NO entra en nuestra licencia (`BentoError: A live data license is
     required to access GLBX.MDP3`), asi que se usa el historico, que va casi pegado.
  2. yfinance — respaldo. Medido el mismo minuto: tambien ~11 min de retraso.
Ninguna de las dos es tiempo real. **Se declara el retraso en cada fila** (`lag_s`, `fuente`)
y por doctrina de la casa nada de esto dispara una orden: describe el hueco, no el print.

Escribe `data/futures_overnight.json`:
  {"ts":…, "futuros":[{"nombre":"NQ","last":…,"prev_close":…,"pct":…,"rango":[lo,hi],
                       "fuente":"databento","lag_s":…,"cash_proxy":"QQQ","implied_open":…}, …],
   "corea": {...}, "avisos":[…]}

Uso: futures_feed.py [--once] [--intervalo 60]
"""
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

OUT = os.path.join(ROOT, "data", "futures_overnight.json")
UNIVERSO = os.path.join(ROOT, "data", "futures.txt")
HIST = "https://hist.databento.com/v0/timeseries.get_range"
DATASET = "GLBX.MDP3"
PRECIO_ESCALA = 1e-9          # DBN entrega precios en punto fijo 1e-9
INTERVALO_S = float(os.environ.get("FUTURES_FEED_S", "60"))


def universo(path=UNIVERSO):
    """[(nombre, raiz, yahoo, etiqueta, cash_proxy)] desde data/futures.txt. Jamas hardcodeado."""
    filas = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            p = ln.split(None, 4)
            if len(p) < 5:
                continue
            nombre, raiz, yahoo, resto = p[0], p[1], p[2], p[3] + (" " + p[4] if len(p) > 4 else "")
            # la etiqueta puede llevar espacios; el cash proxy es la ULTIMA palabra
            trozos = resto.split()
            cash = trozos[-1]
            etiqueta = " ".join(trozos[:-1])
            filas.append((nombre, raiz, yahoo, etiqueta, None if cash == "-" else cash))
    if not filas:
        raise RuntimeError(f"{path} sin futuros: sin universo no hay mapa de hueco")
    return filas


def _key():
    k = (os.environ.get("DATABENTO_API_KEY") or "").strip()
    if k:
        return k
    with open(os.path.join(ROOT, "config", "feeds.env")) as f:
        for ln in f:
            if ln.startswith("DATABENTO_API_KEY="):
                return ln.split("=", 1)[1].strip()
    return None


def _post(url, campos, key, timeout=45):
    import base64
    data = urllib.parse.urlencode(campos).encode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{key}:".encode()).decode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def databento_barras(raices, key, horas=8):
    """{raiz: [(epoch, o,h,l,c,v)]} de barras 1m de CME. Levanta si la peticion falla.

    El `end` se pide con margen NEGATIVO: la API responde 422 `data_end_after_available_end`
    si le pides mas alla de lo ingerido, y ese 422 no es un fallo nuestro sino su frontera.
    """
    fin = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
    ini = fin - dt.timedelta(hours=horas)
    campos = {
        "dataset": DATASET,
        "symbols": ",".join(f"{r}.c.0" for r in raices),
        "stype_in": "continuous", "schema": "ohlcv-1m", "encoding": "csv",
        "start": ini.strftime("%Y-%m-%dT%H:%M:%S"), "end": fin.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    txt = _post(HIST, campos, key)
    # el CSV no trae el simbolo, solo instrument_id -> se pide el mapa aparte
    mapa = _resolucion(raices, key, ini, fin)
    out = {}
    for row in csv.DictReader(io.StringIO(txt)):
        iid = row.get("instrument_id")
        raiz = mapa.get(str(iid))
        if not raiz:
            continue
        out.setdefault(raiz, []).append((
            int(row["ts_event"]) / 1e9,
            float(row["open"]) * PRECIO_ESCALA, float(row["high"]) * PRECIO_ESCALA,
            float(row["low"]) * PRECIO_ESCALA, float(row["close"]) * PRECIO_ESCALA,
            float(row["volume"]),
        ))
    for r in out:
        out[r].sort()
    return out


def _resolucion(raices, key, ini, fin):
    """instrument_id -> raiz, via symbology.resolve. Sin esto el CSV es anonimo."""
    campos = {
        "dataset": DATASET, "symbols": ",".join(f"{r}.c.0" for r in raices),
        "stype_in": "continuous", "stype_out": "instrument_id",
        "start_date": ini.date().isoformat(), "end_date": (fin.date() + dt.timedelta(days=1)).isoformat(),
    }
    try:
        d = json.loads(_post("https://hist.databento.com/v0/symbology.resolve", campos, key))
    except Exception:
        return {}
    out = {}
    for sym, tramos in (d.get("result") or {}).items():
        raiz = sym.split(".")[0]
        for t in tramos:
            out[str(t.get("s"))] = raiz
    return out


def yahoo_fila(yahoo):
    """(last, prev_close, lo, hi, epoch_ultima_barra) o None. Respaldo: tambien ~11 min tarde."""
    try:
        import yfinance as yf
        t = yf.Ticker(yahoo)
        fi = t.fast_info
        # fast_info NO es un dict: no tiene .get() (AttributeError -> el except se lo tragaba y
        # devolvia None para los 5 futuros. Medido 2026-08-02).
        last, prev = fi["last_price"], fi["previous_close"]
        if not last or not prev:
            return None
        h = t.history(period="1d", interval="1m")
        if len(h):
            return (float(last), float(prev), float(h["Low"].min()), float(h["High"].max()),
                    h.index[-1].timestamp())
        return (float(last), float(prev), None, None, None)
    except Exception:
        return None


def construir():
    filas = universo()
    key = _key()
    ahora = time.time()
    avisos = []
    db_barras = {}
    if key:
        try:
            db_barras = databento_barras([r[1] for r in filas], key)
        except urllib.error.HTTPError as e:
            # El 422 de Databento dice EXACTAMENTE donde acaba nuestra licencia. Medido
            # 2026-08-02 21:35 ET: "requires a subscription and/or license... Try again with an
            # end time before 2026-08-02T17:34:29Z" -> las ultimas ~8 h de CME estan fuera del
            # plan. Sirve para HISTORIA/backtest, no para la sesion de esta noche.
            det = ""
            try:
                det = json.loads(e.read().decode()).get("detail", {}).get("message", "")[:180]
            except Exception:
                pass
            avisos.append(f"Databento GLBX fuera de licencia para la sesion viva ({det}) "
                          f"— la fila viva sale de yfinance")
        except (urllib.error.URLError, OSError, ValueError) as e:
            avisos.append(f"Databento no respondio ({type(e).__name__}) — voy con yfinance")
    else:
        avisos.append("sin DATABENTO_API_KEY — voy con yfinance")

    futuros = []
    for nombre, raiz, yahoo, etiqueta, cash in filas:
        barras = db_barras.get(raiz) or []
        fila = None
        if len(barras) >= 2:
            ep, _o, _h, _l, c, _v = barras[-1]
            lo = min(b[3] for b in barras)
            hi = max(b[2] for b in barras)
            prev = _prev_close_yahoo(yahoo)
            fila = {"fuente": "databento_glbx", "last": round(c, 4), "prev_close": prev,
                    "rango": [round(lo, 4), round(hi, 4)], "lag_s": round(ahora - ep, 1),
                    "barras_1m": len(barras)}
        if fila is None:
            y = yahoo_fila(yahoo)
            if y is None:
                avisos.append(f"{nombre}: sin dato en ninguna fuente")
                continue
            last, prev, lo, hi, ep = y
            fila = {"fuente": "yfinance", "last": round(last, 4), "prev_close": round(prev, 4),
                    "rango": [None if lo is None else round(lo, 4),
                              None if hi is None else round(hi, 4)],
                    "lag_s": None if ep is None else round(ahora - ep, 1)}
        prev = fila.get("prev_close")
        fila["pct"] = (round((fila["last"] - prev) / prev * 100.0, 3)
                       if prev else None)   # None y no 0.0: un 0% es "plano", no "no se"
        fila.update({"nombre": nombre, "etiqueta": etiqueta, "cash_proxy": cash})
        fila["implied_open"] = _implied_open(cash, fila["pct"])
        futuros.append(fila)

    return {"ts": int(ahora), "et": time.strftime("%Y-%m-%d %H:%M:%S"),
            "futuros": futuros, "corea": _corea(), "avisos": avisos,
            "nota": ("Databento GLBX.MDP3 (historico) ~12 min de retraso medido; yfinance ~11 min. "
                     "NINGUNA es tiempo real: esto describe el HUECO, no dispara ordenes.")}


_PREV_CACHE = {}


def _prev_close_yahoo(yahoo, ttl=1800):
    """Cierre anterior del contrato. Databento no lo da (es un continuo); yfinance si, y cambia
    una vez al dia, asi que se cachea 30 min en vez de pedirlo en cada ciclo."""
    hit = _PREV_CACHE.get(yahoo)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        import yfinance as yf
        v = yf.Ticker(yahoo).fast_info["previous_close"]
        v = round(float(v), 4) if v else None
    except Exception:
        v = None
    _PREV_CACHE[yahoo] = (time.time(), v)
    return v


def _implied_open(cash, pct):
    """Apertura implicita del ETF: su ultimo cierre movido el % del futuro. None si falta algo —
    jamas el cierre a secas, que se leeria como 'abre plano'."""
    if not cash or pct is None:
        return None
    p = os.path.join(ROOT, "data", f"bars_{cash.lower()}_ibkr.txt")
    try:
        with open(p) as f:
            ult = [l for l in f if l.strip()][-1]
        cierre = float(ult.split()[4])
    except (OSError, ValueError, IndexError):
        return None
    return {"simbolo": cash, "cierre_previo": round(cierre, 4),
            "apertura_implicita": round(cierre * (1 + pct / 100.0), 4),
            "delta": round(cierre * pct / 100.0, 4)}


def _corea():
    """La otra mitad del mapa nocturno: Corea lidera ~13h. Sale de las barras que ya escribe
    korea_naver_bridge, sin volver a pedir nada."""
    out = {}
    try:
        prev = json.load(open(os.path.join(ROOT, "data", "korea_prevclose.json")))
    except (OSError, ValueError):
        prev = {}
    for n in ("kospi", "kospi200", "kodex200", "samsung", "skhynix"):
        try:
            with open(os.path.join(ROOT, "data", f"bars_{n}.txt")) as f:
                lineas = [l for l in f if l.strip()]
            ep, c = float(lineas[-1].split()[0]), float(lineas[-1].split()[4])
        except (OSError, ValueError, IndexError):
            continue
        # korea_prevclose.json guarda {"close":…,"epoch":…,"session":…}, no un numero pelado
        entrada = prev.get(n) or {}
        base = entrada.get("close") if isinstance(entrada, dict) else entrada
        out[n] = {"last": c, "edad_s": round(time.time() - ep, 1),
                  "sesion_ref": entrada.get("session") if isinstance(entrada, dict) else None,
                  "pct": round((c - base) / base * 100.0, 3) if base else None}
    return out


def escribir(d, path=OUT):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main():
    once = "--once" in sys.argv
    intervalo = INTERVALO_S
    if "--intervalo" in sys.argv:
        intervalo = float(sys.argv[sys.argv.index("--intervalo") + 1])
    while True:
        d = construir()
        escribir(d)
        vivos = [f for f in d["futuros"] if f.get("pct") is not None]
        print("[futuros] " + " | ".join(f"{f['nombre']} {f['pct']:+.2f}%" for f in vivos)
              + (f"  avisos: {'; '.join(d['avisos'])}" if d["avisos"] else ""), flush=True)
        if once:
            return 0 if vivos else 1
        time.sleep(intervalo)


if __name__ == "__main__":
    raise SystemExit(main())
