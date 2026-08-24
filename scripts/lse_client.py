#!/usr/bin/env python3
"""lse_client.py — cliente REST del vault de London Strategic Edge (stdlib, sin dependencias).

LOTE / DIAGNOSTICO, no camino de senal (~/CLAUDE.md: Python solo para lotes, tests y puentes).
Mueve bytes: cero computo de senal aqui dentro.

TODO lo de abajo esta MEDIDO el 2026-08-08 con la key real de config/feeds.env (comandos en
docs/LSE-CLIENTE.md), no recordado:
  auth   : cabecera `X-API-Key`. Sin ella -> 401 {"detail":"missing x-api-key"}.
  cuota  : /vault/usage -> 200 req/min, 5000 filas/peticion, vault_concurrency 2,
           50 GB/mes, 15 GB/semana, historical_data_months -1 (ilimitado).
  gasto  : cada 200 trae la cabecera `x-data-bytes` (5000 velas 1m de SPY = 601.717 bytes).
           Se ACUMULA en stats: el limite que muerde primero son los GB, no las peticiones.
  429    : 5 peticiones en paralelo -> 2 x 429 en 0,40 s, con cabecera `retry-after: 1`.
           Por eso hay limitador de ritmo (190/60 s) Y 2 huecos de concurrencia en disco.
  cadena : /options/chain SIN filtro devuelve 5000 filas y las 5000 estaban EXPIRADAS
           (SPY el 2026-08-08: expiry 2026-07-02..2026-07-28, last_trade_at max 2026-07-27).
           El recorte de 5000 corta ANTES de llegar al presente => entregar eso como
           "cadena viva" seria la mentira mas cara del fichero. options_chain() LEVANTA.
  filas de cadena: son fotos del ULTIMO TRADE de cada contrato, no una cadena sincronizada.
           `dte`, `underlying_price`, `iv` y las griegas van congeladas a `last_trade_at`
           (SPY expiry 2026-08-14: dte 7,8,9,10,11,14,15,16,17,18,21,35 en la MISMA
           expiracion, underlying_price 731,04..776,31). Un `max_dte` filtra por ese dte
           RANCIO -> devuelve expirados (max_dte=7 -> 200/200 filas expiry 2026-07-02).
  flujo  : /options/flow NO trae lado agresor (union de campos sobre 2000 filas:
           id ts underlying ticker strike expiry contract_type last_price volume premium
           underlying_price dte iv delta gamma theta vega rho — ni side, ni bid, ni ask).

Nada de valores por defecto plausibles: o el dato, o LSEError. Jamas 0, 0.0, {} ni [] fingido.
"""
import datetime as dt
import errno
import fcntl
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_URL = "https://api.londonstrategicedge.com/vault"
# Official SDK endpoint. Re-verified live 2026-08-12: authenticates both equity
# subscriptions and subscribe_options; the shorter ws host rejects option actions.
WS_URL = "wss://data-ws.londonstrategicedge.com"
UA = "ib-trader/1.0 (lse_client lote)"

MAX_ROWS = 5000                 # max_rows_per_request medido en /vault/usage
RATE_N = int(os.environ.get("LSE_RATE_N", "190"))        # tope 200/min: 10 de margen
RATE_WINDOW = float(os.environ.get("LSE_RATE_WINDOW", "62"))
CONCURRENCY = int(os.environ.get("LSE_CONCURRENCY", "2"))  # vault_concurrency medido
TIMEOUT_S = float(os.environ.get("LSE_TIMEOUT_S", "60"))
TRIES = 4
CATALOG_TTL_S = float(os.environ.get("LSE_CATALOG_TTL_S", "86400"))

try:
    import lse_budget                  # techo local + cortacircuito compartidos con el worker
except ImportError:
    lse_budget = None

STATE_DIR = os.path.join(REPO, "data")
RATE_STATE = os.path.join(STATE_DIR, "lse_rate_state.json")
SLOT_DIR = os.path.join(STATE_DIR, "lse_slots")
CATALOG_CACHE = os.path.join(STATE_DIR, "lse_catalog.json")

TIMEFRAMES = ("1s", "5s", "15s", "30s", "1m", "3m", "5m", "15m", "30m",
              "1h", "4h", "1d", "1w", "1mo")   # lista servida por el 400 del propio vault
ORDERS = ("asc", "desc")
OSI_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,9})(\d{6})([CP])(\d{8})$")
OPTION_TYPES = {"c": "call", "call": "call", "calls": "call",
                "p": "put", "put": "put", "puts": "put"}

# El vault sirve horas UTC como "YYYY-MM-DD hh:mm:ss[.ffffff]"; se normalizan a ISO-8601 con Z
# para que nadie las parsee como hora local.
TIME_KEYS = ("ts", "timestamp", "minute", "datetime", "last_trade_at", "updated_at",
             "created_at", "accepted_date", "fetched_at")
# Los flotantes llegan con la expansion binaria entera (strike 484.99999999999994). Se redondea
# a la precision que el feed cotiza de verdad. NADA mas se toca.
ROUND = {"strike": 4, "last_price": 4, "premium": 2, "premium_today": 2,
         "underlying_price": 4, "iv": 6, "iv_avg": 6, "delta": 6, "delta_avg": 6,
         "gamma": 8, "gamma_avg": 8, "theta": 6, "theta_avg": 6, "vega": 6,
         "vega_avg": 6, "rho": 6, "rho_avg": 6, "open": 4, "high": 4, "low": 4, "close": 4}


class LSEError(RuntimeError):
    """Fallo que el llamante DEBE ver. Lleva el status HTTP (0 = no hubo respuesta)."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------------ clave
def _feeds_env():
    """config/feeds.env -> dict. KEY=VALOR, ignora comentarios."""
    path = os.path.join(REPO, "config", "feeds.env")
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out


def api_key():
    """Entorno o feeds.env. Levanta si falta: sin key no existe 'valor por defecto'."""
    k = os.environ.get("LSE_API_KEY") or _feeds_env().get("LSE_API_KEY")
    if not k:
        raise LSEError("falta LSE_API_KEY (entorno ni config/feeds.env)")
    return k


def redact(text, key=None):
    """La key jamas se imprime ni se loguea."""
    if not text:
        return text
    try:
        k = key or api_key()
    except LSEError:
        return text
    return text.replace(k, "<LSE_API_KEY>") if len(k) > 8 else text


# ------------------------------------------------------------------ ritmo y concurrencia
class RateLimiter:
    """Ventana deslizante de N peticiones por W segundos, con estado en disco y flock:
    dos procesos (backfill + archivador) comparten la MISMA cuota. Patron copiado de
    scripts/poly_client.py:66."""

    def __init__(self, n=RATE_N, window=RATE_WINDOW, path=RATE_STATE):
        self.n = max(1, int(n))
        self.window = float(window)
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _read(self, fh):
        try:
            fh.seek(0)
            raw = fh.read()
            if not raw.strip():
                return []
            got = json.loads(raw)
            return [float(x) for x in got] if isinstance(got, list) else []
        except (ValueError, TypeError):
            return []          # estado corrupto: pierde cuota, JAMAS la inventa

    def acquire(self):
        """Bloquea hasta que quepa una peticion. Devuelve los segundos esperados."""
        waited = 0.0
        while True:
            with open(self.path, "a+") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                now = time.time()
                hits = [t for t in self._read(fh) if now - t < self.window]
                if len(hits) < self.n:
                    hits.append(now)
                    fh.seek(0)
                    fh.truncate()
                    fh.write(json.dumps(hits[-(self.n + 8):]))
                    fh.flush()
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    return waited
                sleep_for = self.window - (now - min(hits)) + 0.5
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            sleep_for = max(0.2, min(sleep_for, self.window + 5))
            time.sleep(sleep_for)
            waited += sleep_for


class Slots:
    """vault_concurrency=2: MEDIDO que 5 peticiones a la vez devuelven 429 en 0,40 s.
    N ficheros-cerrojo no bloqueantes; si todos estan tomados, espera y reintenta."""

    def __init__(self, n=CONCURRENCY, dirpath=SLOT_DIR, wait_s=30.0):
        self.n = max(1, int(n))
        self.dir = dirpath
        self.wait_s = float(wait_s)
        os.makedirs(self.dir, exist_ok=True)

    def acquire(self):
        """Devuelve un descriptor con el hueco tomado. Levanta si nadie lo suelta."""
        t0 = time.time()
        while True:
            for i in range(self.n):
                fh = open(os.path.join(self.dir, "slot%d.lock" % i), "a+")
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fh
                except OSError:
                    fh.close()
            if time.time() - t0 > self.wait_s:
                raise LSEError("los %d huecos de concurrencia siguen tomados tras %.0f s "
                               "(hay otro proceso LSE vivo)" % (self.n, self.wait_s), status=0)
            time.sleep(0.25)

    @staticmethod
    def release(fh):
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ------------------------------------------------------------------ salida a la red
def _http_get(url, headers, timeout):
    """UNICA salida a la red del modulo (los tests la sustituyen).
    Devuelve (status, cabeceras, cuerpo). Los fallos de transporte suben como OSError."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()


def _detail(body):
    """El vault anida el detalle: {"detail":"{\\"detail\\":\\"...\\"}"}. Se desenvuelve."""
    txt = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    for _ in range(3):
        try:
            j = json.loads(txt)
        except ValueError:
            break
        if isinstance(j, dict) and isinstance(j.get("detail"), str):
            txt = j["detail"]
            continue
        break
    return txt[:300]


# ------------------------------------------------------------------ normalizacion
def _isoify(rows):
    """Horas UTC del vault -> ISO-8601 con Z. No inventa campos que no vinieron."""
    for r in rows:
        for k in TIME_KEYS:
            v = r.get(k)
            if isinstance(v, str) and len(v) >= 19 and v[10] == " ":
                r[k] = v.replace(" ", "T", 1) + "Z"
    return rows


def _deround(rows):
    for r in rows:
        for k, nd in ROUND.items():
            v = r.get(k)
            if isinstance(v, float):
                r[k] = round(v, nd)
    return rows


def _norm(rows, raw=False):
    return rows if raw else _deround(_isoify(rows))


def capped(rows, limit):
    """True si la respuesta toco el techo => hay mas filas que no viste."""
    return len(rows) >= min(int(limit), MAX_ROWS)


def stale_seconds(row, field="last_trade_at", now=None):
    """Antiguedad real de una fila, en segundos. Levanta si el campo no esta o no parsea:
    devolver 0.0 convertiria 'no se' en 'es fresquisimo'."""
    v = row.get(field)
    if not isinstance(v, str) or not v:
        raise LSEError("la fila no trae '%s': no se puede afirmar frescura" % field)
    txt = v.replace("Z", "+00:00").replace(" ", "T", 1) if "T" not in v else v.replace("Z", "+00:00")
    try:
        t = dt.datetime.fromisoformat(txt)
    except ValueError:
        raise LSEError("'%s' no es una fecha ISO parseable: %r" % (field, v))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    ref = now or dt.datetime.now(dt.timezone.utc)
    return (ref - t).total_seconds()


def atomic_write(path, text):
    """tmp + os.replace: nadie lee un fichero a medio escribir."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ------------------------------------------------------------------ validadores locales
def _chk_tf(tf):
    t = str(tf).lower()
    if t not in TIMEFRAMES:
        raise LSEError("timeframe %r invalido; validos: %s" % (tf, ", ".join(TIMEFRAMES)))
    return t


def _chk_order(order):
    o = str(order).lower()
    if o not in ORDERS:
        raise LSEError("order %r invalido; solo %s" % (order, "/".join(ORDERS)))
    return o


def _chk_limit(limit):
    n = int(limit)
    if n < 1:
        raise LSEError("limit debe ser >= 1, llego %r" % (limit,))
    return min(n, MAX_ROWS)


def _chk_type(kind):
    if kind is None:
        return None
    right = OPTION_TYPES.get(str(kind).lower())
    if not right:
        raise LSEError("type debe ser call o put, llego %r" % (kind,))
    return right


def _chk_osi(ticker):
    osi = str(ticker).strip().upper()
    if not OSI_RE.match(osi):
        raise LSEError("%r no es un contrato OSI (ej. SPY260925P00780000)" % (ticker,))
    return osi


def _today():
    return dt.datetime.now(dt.timezone.utc).date()


# ------------------------------------------------------------------ cliente
class LSE:
    """Cliente fino. Cada metodo devuelve list[dict] tal cual los sirve el vault
    (horas a ISO-Z y flotantes des-ruidados) o LEVANTA LSEError. Nunca a medias."""

    def __init__(self, key=None, limiter=None, slots=None, timeout=TIMEOUT_S, tries=TRIES):
        self.key = key or api_key()
        self.limiter = limiter if limiter is not None else RateLimiter()
        self.slots = slots if slots is not None else Slots()
        self.timeout = float(timeout)
        self.tries = int(tries)
        self.stats = {"requests": 0, "ok": 0, "http_429": 0, "http_5xx": 0,
                      "net_err": 0, "bytes": 0, "waited_s": 0.0}
        self._catalog = None

    # -- transporte ---------------------------------------------------------
    def _url(self, path, params):
        qs = urllib.parse.urlencode([(k, str(v)) for k, v in params if v is not None])
        return VAULT_URL + path + ("?" + qs if qs else "")

    def rows(self, path, params):
        """GET con ritmo, hueco de concurrencia y reintentos SOLO para 429/5xx/red.
        401/403/400/404 levantan al primer intento: reintentarlos quema cuota sin arreglar nada."""
        url = self._url(path, params)
        headers = {"X-API-Key": self.key, "Accept": "application/json", "User-Agent": UA}
        last = None
        for attempt in range(self.tries):
            if lse_budget is not None:
                try:
                    lse_budget.consumir(1, quien="lse_client")
                except lse_budget.LSEBudgetError as e:
                    raise LSEError(str(e), status=429) from e
            self.stats["waited_s"] += self.limiter.acquire()
            slot = self.slots.acquire()
            self.stats["requests"] += 1
            try:
                status, hdrs, body = _http_get(url, headers, self.timeout)
            except OSError as e:
                if getattr(e, "errno", None) == errno.EINTR:
                    continue
                self.stats["net_err"] += 1
                last = "%s: %s" % (e.__class__.__name__, str(e)[:100])
                time.sleep(1.0 * (attempt + 1))
                continue
            finally:
                Slots.release(slot)

            if status == 200:
                try:
                    self.stats["bytes"] += int(hdrs.get("x-data-bytes")
                                               or hdrs.get("X-Data-Bytes") or 0)
                except (TypeError, ValueError):
                    pass                      # contabilidad de gasto, no dato de señal
                try:
                    out = json.loads(body.decode("utf-8", "replace"))
                except ValueError as e:
                    raise LSEError("%s devolvio un cuerpo que no es JSON: %s" % (path, e),
                                   status=200)
                if not isinstance(out, list):
                    raise LSEError("%s devolvio %s, se esperaba una lista de filas"
                                   % (path, type(out).__name__), status=200)
                self.stats["ok"] += 1
                if lse_budget is not None:
                    lse_budget.sonda_ok()
                return out
            if status == 429:
                self.stats["http_429"] += 1
                if "daily request limit" in _detail(body).lower():
                    if lse_budget is not None:
                        lse_budget.agotado("daily request limit reached (15000/day)")
                    raise LSEError("cuota diaria de LSE agotada (15.000/dia): todo cliente "
                                   "local queda cortado hasta el reset", status=429)
                try:
                    wait = float(hdrs.get("retry-after") or hdrs.get("Retry-After") or 1.0)
                except (TypeError, ValueError):
                    wait = 1.0
                time.sleep(min(max(wait, 0.5) + 0.25 * attempt, 30.0))
                last = "429 (retry-after %.1f)" % wait
                continue
            if 500 <= status < 600:
                self.stats["http_5xx"] += 1
                last = "HTTP %d" % status
                time.sleep(1.5 * (attempt + 1))
                continue
            raise LSEError("GET %s -> %d %s" % (path, status, redact(_detail(body), self.key)),
                           status=status)
        raise LSEError("GET %s agotados %d intentos: %s" % (path, self.tries, last), status=0)

    def report(self, prefix="lse"):
        s = self.stats
        return ("%s: %d peticiones (%d ok, %d 429, %d 5xx, %d red), %.1f MB de cuota, "
                "espera %.1f s" % (prefix, s["requests"], s["ok"], s["http_429"],
                                   s["http_5xx"], s["net_err"], s["bytes"] / 1e6,
                                   s["waited_s"]))

    # -- velas y series -----------------------------------------------------
    def candles(self, symbol, timeframe="1m", start=None, end=None, limit=MAX_ROWS,
                order="asc", dataset=None, raw=False):
        """OHLCV de cualquier instrumento NO opcion. Campos del vault: ts, symbol, open,
        high, low, close, volume. `ts` se deja con su nombre de cable (el SDK oficial lo
        renombra a `timestamp`; aqui NO, para que el fichero diga lo que dijo el servidor).
        Si pides un rango CERRADO (start y end) y la respuesta toca el techo de filas,
        LEVANTA: un rango truncado que parece completo es el bug caro."""
        if not symbol:
            raise LSEError("candles exige symbol")
        lim = _chk_limit(limit)
        p = [("symbol", symbol), ("timeframe", _chk_tf(timeframe)), ("order", _chk_order(order)),
             ("limit", lim), ("dataset", dataset), ("start", start), ("end", end)]
        out = _norm(self.rows("/candles", p), raw)
        if start and end and capped(out, lim):
            raise LSEError("rango %s..%s de %s truncado en %d filas (techo). Parte el rango: "
                           "entregarlo asi seria un PARCIAL disfrazado de completo"
                           % (start, end, symbol, lim), status=200)
        return out

    def series(self, symbol, dataset=None, start=None, end=None, limit=MAX_ROWS,
               order="asc", raw=False):
        """Serie (date, value): economics, tenores de bonos, y cualquier dataset con forma
        de serie. Campos: symbol, date, value."""
        if not symbol:
            raise LSEError("series exige symbol")
        p = [("symbol", symbol), ("dataset", dataset), ("start", start), ("end", end),
             ("order", _chk_order(order)), ("limit", _chk_limit(limit))]
        return _norm(self.rows("/series", p), raw)

    # -- opciones -----------------------------------------------------------
    def options_chain(self, underlying, kind=None, expiry=None, strike=None,
                      min_dte=None, max_dte=None, limit=MAX_ROWS, allow_expired=False,
                      raw=False):
        """Cadena de opciones: UNA FILA POR CONTRATO CON SU ULTIMO TRADE, no una foto
        sincronizada. `dte`, `underlying_price`, `iv` y las griegas son de `last_trade_at`.

        DOS guardias, ambas nacidas de medicion (2026-08-08, SPY):
          1. sin `expiry` y tocando el techo de filas -> LEVANTA: el recorte de 5000 corta
             antes del presente y devolvio 5000/5000 contratos EXPIRADOS.
          2. si ninguna fila vence hoy o despues -> LEVANTA salvo allow_expired=True.
        Pasa `expiry=` (o una ventana de strike) y esto se vuelve util y honesto."""
        if not underlying:
            raise LSEError("options_chain exige underlying")
        lim = _chk_limit(limit)
        p = [("underlying", str(underlying).upper()), ("limit", lim),
             ("type", _chk_type(kind)), ("expiry", expiry),
             ("min_dte", None if min_dte is None else int(min_dte)),
             ("max_dte", None if max_dte is None else int(max_dte))]
        if strike is not None:
            if isinstance(strike, (tuple, list)):
                p += [("strike_min", strike[0]), ("strike_max", strike[1])]
            else:
                p.append(("strike", strike))
        out = _norm(self.rows("/options/chain", p), raw)
        if not out:
            return out
        if not expiry and capped(out, lim):
            raise LSEError("cadena de %s truncada en %d filas sin filtro de expiry: MEDIDO que "
                           "el recorte devuelve contratos EXPIRADOS (SPY 2026-08-08: 5000/5000). "
                           "Llama con expiry= o una ventana de strike"
                           % (underlying, lim), status=200)
        if not allow_expired:
            hoy = _today().isoformat()
            vivos = sum(1 for r in out if str(r.get("expiry") or "") >= hoy)
            if vivos == 0:
                raise LSEError("la cadena servida de %s esta ENTERA EXPIRADA (%d filas, "
                               "expiry max %s). No es la cadena viva; usa allow_expired=True "
                               "si de verdad quieres el archivo"
                               % (underlying, len(out), max(str(r.get("expiry") or "")
                                                            for r in out)), status=200)
        return out

    def options_flow(self, underlying=None, kind=None, min_premium=None, expiry=None,
                     max_dte=None, start=None, end=None, limit=MAX_ROWS, order="desc",
                     raw=False):
        """Cinta de prints de opciones (semana corrida). Sin `underlying` barre el mercado
        entero; filtra con min_premium.

        NO trae lado agresor (medido: la union de campos sobre 2000 filas no tiene side, ni
        bid, ni ask) => de aqui NO sale delta firmado ni footprint.
        Densidad medida: 2000 filas del barrido global = 53 segundos de cinta. El techo de
        5000 filas son ~2 minutos: para una sesion entera hay que PAGINAR con start/end."""
        p = [("order", _chk_order(order)), ("limit", _chk_limit(limit)),
             ("start", start), ("end", end), ("type", _chk_type(kind)),
             ("underlying", str(underlying).upper() if underlying else None),
             ("min_premium", min_premium), ("expiry", expiry),
             ("max_dte", None if max_dte is None else int(max_dte))]
        return _norm(self.rows("/options/flow", p), raw)

    def option_candles(self, ticker, start=None, end=None, limit=MAX_ROWS, order="asc",
                       raw=False):
        """Velas 1m de UN contrato OSI, con volumen, prima y griegas PROMEDIADAS por barra
        (sufijo _avg). Es la historia anterior a la semana que cubre options_flow."""
        p = [("ticker", _chk_osi(ticker)), ("order", _chk_order(order)),
             ("limit", _chk_limit(limit)), ("start", start), ("end", end)]
        out = _norm(self.rows("/options/candles", p), raw)
        if start and end and capped(out, min(int(limit), MAX_ROWS)):
            raise LSEError("rango %s..%s de %s truncado en el techo de filas; parte el rango"
                           % (start, end, ticker), status=200)
        return out

    def osi(self, underlying, strike, expiry, kind):
        """Arma el ticker OSI localmente (cero peticiones). Levanta si algo no cuadra."""
        right = _chk_type(kind)
        if right is None:
            raise LSEError("osi() exige type call o put")
        exp = expiry if isinstance(expiry, dt.date) else dt.date.fromisoformat(str(expiry))
        return "%s%s%s%08d" % (str(underlying).upper(), exp.strftime("%y%m%d"),
                               "C" if right == "call" else "P", int(round(float(strike) * 1000)))

    # -- descubrimiento -----------------------------------------------------
    def usage(self):
        """Cuota viva. Es el UNICO endpoint que devuelve un dict, no una lista."""
        url = self._url("/usage", [])
        headers = {"X-API-Key": self.key, "Accept": "application/json", "User-Agent": UA}
        self.stats["waited_s"] += self.limiter.acquire()
        slot = self.slots.acquire()
        self.stats["requests"] += 1
        try:
            status, _h, body = _http_get(url, headers, self.timeout)
        finally:
            Slots.release(slot)
        if status != 200:
            raise LSEError("GET /usage -> %d %s" % (status, redact(_detail(body), self.key)),
                           status=status)
        out = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(out, dict):
            raise LSEError("/usage devolvio %s, se esperaba un dict" % type(out).__name__)
        self.stats["ok"] += 1
        return out

    def catalog(self, dataset=None, max_age_s=CATALOG_TTL_S, refresh=False, path=CATALOG_CACHE):
        """Catalogo completo (22.851 filas medidas, 8,7 MB): dataset, symbol, name, ticks,
        first_tick, last_tick. Cacheado en data/lse_catalog.json con escritura atomica —
        bajarlo en cada llamada quemaria la cuota de GB por nada.
        Si la cache esta corrupta se REBAJA, no se devuelve media."""
        rows = self._catalog
        if rows is None and not refresh and path and os.path.exists(path):
            try:
                age = time.time() - os.path.getmtime(path)
                if age <= max_age_s:
                    with open(path) as fh:
                        got = json.load(fh)
                    if isinstance(got, list) and got:
                        rows = got
            except (OSError, ValueError):
                rows = None                    # cache ilegible: se rebaja, no se finge
        if rows is None:
            rows = self.rows("/catalog", [("limit", MAX_ROWS)])
            if not rows:
                raise LSEError("/catalog devolvio 0 filas: el catalogo nunca esta vacio",
                               status=200)
            if path:
                atomic_write(path, json.dumps(rows))
        self._catalog = rows
        if dataset:
            return [r for r in rows if r.get("dataset") == dataset]
        return list(rows)

    def datasets(self):
        """{dataset: n_simbolos} desde el catalogo cacheado."""
        out = {}
        for r in self.catalog():
            out[r.get("dataset", "?")] = out.get(r.get("dataset", "?"), 0) + 1
        return out


# ------------------------------------------------------------------ CLI de diagnostico
def _print_rows(rows, n=10):
    for r in rows[:n]:
        print("  " + json.dumps(r, default=str))
    if len(rows) > n:
        print("  ... %d filas mas" % (len(rows) - n))
    print("  total: %d filas" % len(rows))


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="cliente LSE vault (diagnostico)")
    ap.add_argument("--candles", metavar="SYM")
    ap.add_argument("--series", metavar="SYM")
    ap.add_argument("--chain", metavar="SYM")
    ap.add_argument("--flow", metavar="SYM", nargs="?", const="", default=None)
    ap.add_argument("--optcandles", metavar="OSI")
    ap.add_argument("--catalog", metavar="DATASET", nargs="?", const="", default=None)
    ap.add_argument("--usage", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--tf", default="1d")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--order", default="desc")
    ap.add_argument("--expiry")
    ap.add_argument("--type", dest="kind")
    ap.add_argument("--min-premium", type=float)
    ap.add_argument("--max-dte", type=int)
    ap.add_argument("--allow-expired", action="store_true")
    ap.add_argument("--json", action="store_true", help="volcado JSON crudo a stdout")
    a = ap.parse_args(argv)

    c = LSE()
    rows = None
    try:
        if a.usage or a.probe:
            u = c.usage()
            print("usage: " + json.dumps(u))
        if a.probe:
            v = c.candles("SPY", "1d", limit=3, order="desc")
            print("probe SPY 1d:")
            _print_rows(v)
            print(" ", c.report())
            return 0
        if a.candles:
            rows = c.candles(a.candles, a.tf, start=a.start, end=a.end,
                             limit=a.limit, order=a.order)
        elif a.series:
            rows = c.series(a.series, start=a.start, end=a.end, limit=a.limit, order=a.order)
        elif a.chain:
            rows = c.options_chain(a.chain, kind=a.kind, expiry=a.expiry,
                                   max_dte=a.max_dte, limit=a.limit,
                                   allow_expired=a.allow_expired)
        elif a.flow is not None:
            rows = c.options_flow(a.flow or None, kind=a.kind, min_premium=a.min_premium,
                                  expiry=a.expiry, max_dte=a.max_dte, start=a.start,
                                  end=a.end, limit=a.limit, order=a.order)
        elif a.optcandles:
            rows = c.option_candles(a.optcandles, start=a.start, end=a.end,
                                    limit=a.limit, order=a.order)
        elif a.catalog is not None:
            rows = c.catalog(a.catalog or None)
            print("datasets: " + json.dumps(c.datasets()))
    except LSEError as e:
        print("LSEError(%s): %s" % (e.status, e), file=sys.stderr)
        return 2
    if rows is not None:
        if a.json:
            print(json.dumps(rows, default=str))
        else:
            _print_rows(rows)
        print(" ", c.report())
    elif not (a.usage or a.probe):
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
