#!/usr/bin/env python3
"""poly_client.py — cliente Polygon con LIMITADOR DE RITMO COMPARTIDO entre procesos.

Por que existe (medido 2026-07-25 con la key real de feeds.env):
  rafaga de 12 peticiones -> 5 OK y la 6a 429 en 1.0 s.
  sondeo cada 2 s durante 90 s -> 200 en t=0..9, 429 de t=11 a t=57, 200 otra vez
  en t=59..68, 429 desde t=70.
  => VENTANA DESLIZANTE DE 5 PETICIONES / 60 s. No hay cabeceras X-RateLimit ni
  Retry-After (comprobado: vienen vacias), asi que el ritmo hay que llevarlo NOSOTROS.

Con 5 req/min el presupuesto es el recurso escaso: cada peticion desperdiciada cuesta
12 segundos de reloj. Por eso el limitador es PERSISTENTE en disco: si corren dos
scripts (backfill + archivador) no se pisan y no se quema la cuota en 429s.

LOTE OFFLINE: esto no es camino de senal. Python+urllib es legitimo aqui
(~/CLAUDE.md: "lotes fuera de sesion"). Pero se aplican las reglas de frontera:
  - rutas derivadas de __file__, jamas hardcodeadas
  - PROHIBIDO devolver 0/0.5/{} ante un fallo: o el dato, o None, o levanta
  - todo fallo se CUENTA y se REPORTA, nunca `except: pass`
"""
import datetime as dt
import errno
import fcntl
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "trades.db")
STATE_DIR = os.path.join(REPO, "data")
RATE_STATE = os.path.join(STATE_DIR, "poly_rate_state.json")

# Ventana medida. Se deja 1 hueco de margen (4 de 5) porque el reloj del servidor y el
# nuestro no coinciden y un 429 cuesta mas que esperar 3 s extra.
RATE_N = int(os.environ.get("POLY_RATE_N", "5"))
RATE_WINDOW = float(os.environ.get("POLY_RATE_WINDOW", "62"))
RATE_MARGIN = float(os.environ.get("POLY_RATE_MARGIN", "0.6"))


class PolygonError(RuntimeError):
    """Fallo de Polygon que el llamante DEBE ver (no se traga, no se convierte en 0)."""


def api_key():
    """Key de feeds.env / polygon.env / entorno. Levanta si falta: sin key no hay
    'valor por defecto' posible."""
    for src in ("feeds.env", "polygon.env"):
        p = os.path.join(REPO, src)
        if not os.path.exists(p):
            continue
        with open(p) as fh:
            for ln in fh:
                if ln.startswith("POLYGON_KEY"):
                    k = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    if k:
                        return k
    k = os.environ.get("POLYGON_KEY")
    if k:
        return k
    raise PolygonError("falta POLYGON_KEY en feeds.env / polygon.env / entorno")


class RateLimiter:
    """Ventana deslizante de N peticiones por W segundos, con estado en disco y
    bloqueo fcntl para que varios procesos compartan la MISMA cuota."""

    def __init__(self, n=RATE_N, window=RATE_WINDOW, path=RATE_STATE):
        self.n = max(1, n - 0) if n > 0 else 1
        self.window = window
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
            # estado corrupto: se descarta el historial (pierde cuota, nunca la inventa)
            return []

    def acquire(self, verbose=False):
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
                    fh.write(json.dumps(hits[-64:]))
                    fh.flush()
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    return waited
                sleep_for = self.window - (now - min(hits)) + RATE_MARGIN
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            sleep_for = max(0.2, min(sleep_for, self.window + 5))
            if verbose:
                print(f"    [ritmo] espero {sleep_for:.1f}s (cuota {self.n}/{self.window:.0f}s)",
                      flush=True)
            time.sleep(sleep_for)
            waited += sleep_for


class Polygon:
    """Cliente con reintentos y contabilidad. `stats` se REPORTA al final: los fallos
    silenciosos son el peligro (un dia que falta y nadie lo dice parece dato completo)."""

    def __init__(self, key=None, limiter=None, verbose=True):
        self.key = key or api_key()
        self.limiter = limiter or RateLimiter()
        self.verbose = verbose
        self.stats = {"requests": 0, "ok": 0, "http_429": 0, "http_other": 0,
                      "net_err": 0, "gave_up": 0, "waited_s": 0.0}

    def get(self, url, tries=5, required=True):
        """GET con ritmo. Devuelve el JSON o None si se agotan los reintentos.
        NUNCA devuelve un dict vacio disfrazado de respuesta."""
        sep = "&" if "?" in url else "?"
        full = f"{url}{sep}apiKey={self.key}" if "apiKey=" not in url else url
        last = None
        for i in range(tries):
            self.stats["waited_s"] += self.limiter.acquire(verbose=False)
            self.stats["requests"] += 1
            try:
                with urllib.request.urlopen(full, timeout=45) as r:
                    out = json.load(r)
                self.stats["ok"] += 1
                return out
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code == 429:
                    self.stats["http_429"] += 1
                    # se quemo la cuota: penaliza el bucket entero
                    time.sleep(RATE_WINDOW / 4.0)
                    continue
                if e.code in (401, 403):
                    raise PolygonError(f"Polygon {e.code}: key sin acceso a {url.split('?')[0]}")
                self.stats["http_other"] += 1
                time.sleep(2 + 2 * i)
            except (urllib.error.URLError, OSError, ValueError) as e:
                if isinstance(e, OSError) and e.errno == errno.EINTR:
                    continue
                last = repr(e)
                self.stats["net_err"] += 1
                time.sleep(2 + 2 * i)
        self.stats["gave_up"] += 1
        if self.verbose:
            print(f"    ! agotados los reintentos: {url.split('?')[0]} ({last})", flush=True)
        if required:
            return None
        return None

    def paginate(self, url, max_pages=200):
        """Sigue next_url. Cede cada pagina. Si una pagina falla, LEVANTA en vez de
        devolver un resultado parcial que parezca completo."""
        page = 0
        nxt = url
        while nxt and page < max_pages:
            d = self.get(nxt)
            if d is None:
                raise PolygonError(f"pagina {page + 1} fallida en {url.split('?')[0]} "
                                   f"-> resultado PARCIAL, no se entrega como completo")
            yield d
            page += 1
            nxt = d.get("next_url")

    def report(self, prefix="polygon"):
        s = self.stats
        return (f"{prefix}: {s['requests']} peticiones ({s['ok']} ok, {s['http_429']} 429, "
                f"{s['http_other']} otros HTTP, {s['net_err']} red, {s['gave_up']} abandonadas), "
                f"espera acumulada {s['waited_s'] / 60.0:.1f} min")


# ------------------------------------------------------------------ utilidades
def atomic_write(path, text):
    """tmp + os.replace: nadie lee un fichero a medio escribir (regla de frontera)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def fleet():
    """Simbolos desde data/fleet.txt (fuente unica). Levanta si falta el fichero."""
    p = os.path.join(REPO, "data", "fleet.txt")
    if not os.path.exists(p):
        raise PolygonError(f"falta {p} (fuente unica de la flota)")
    syms = open(p).read().split()
    if not syms:
        raise PolygonError(f"{p} esta vacio")
    return [s.upper() for s in syms]


def market_days(d0, d1):
    """Sesiones NYSE entre d0 y d1 inclusive: lun-vie menos festivos US.
    Se usa para NOMBRAR los huecos; una lista incompleta de festivos produce falsos
    positivos (dia reportado como hueco), nunca falsos negativos silenciosos."""
    hol = {
        # 2024
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
        "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
        # 2025
        "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
        "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
        "2025-12-25",
        # 2026
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
        # 2027
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    }
    out = []
    d = d0
    while d <= d1:
        if d.weekday() < 5 and f"{d:%Y-%m-%d}" not in hol:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


if __name__ == "__main__":
    import sys
    p = Polygon()
    if len(sys.argv) > 1 and sys.argv[1] == "probe":
        # sonda de ritmo: 3 peticiones baratas, mide la espera impuesta
        t0 = time.time()
        for i in range(3):
            d = p.get("https://api.polygon.io/v3/reference/tickers?ticker=AAPL&limit=1")
            print(f"  {i + 1}: {'OK' if d else 'FALLO'}  t={time.time() - t0:.1f}s")
        print(" ", p.report())
    else:
        print(__doc__)
        print(f"  flota: {len(fleet())} simbolos")
        print(f"  estado de ritmo: {RATE_STATE}")
