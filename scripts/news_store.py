#!/usr/bin/env python3
"""news_store.py — memoria de titulares ya publicados. TTL 24 h y nada mas.

Orden de Yunior (2026-08-05): "make sure they dont get repeated, no need to store them more
than 24 h". Dos claves por titular: la URL canonica y el titulo normalizado. Un titular es
NUEVO solo si ninguna de las dos se ha visto — la misma nota llega por Finnhub, Polygon y
Google News con titulos distintos y con URLs distintas, asi que hace falta cruzar las dos.

Multi-proceso: lock exclusivo sobre <fichero>.lock + escritura atomica tmp+rename. Lo tocan
fleet_news_watch.py y asia_semis_watch.py, que corren por launchd y pueden solaparse.
Fail-loud: un fichero ilegible se DICE por stderr, nunca se traga en silencio (un store que
vuelve vacio en silencio republica el dia entero).
"""
import errno
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(REPO, "data", "news_seen.json")
TTL_S = 24 * 3600

# sufijo de publisher que Google News pega al titulo: " - Barron's", " — Reuters"
_PUB_SUFFIX = re.compile(r"\s+[-–—|]\s+[^-–—|]{2,40}$")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")
# ruido de plantilla: no aporta a la identidad de la noticia y varia entre agregadores
_STOP = frozenset("""a an the and or of for to in on at by with from as is are was were be
been this that these those it its his her their our your my what why how when will would
can could should may might said says say new now today s t""".split())
KEY_WORDS = 12          # prefijo de palabras significativas que define la identidad


def canon_url(url):
    """URL sin query, fragmento, www ni barra final. None si no es utilizable.

    Google News RSS devuelve enlaces de REDIRECCION (news.google.com/rss/articles/<blob>):
    unicos por item y distintos para la misma nota, asi que no sirven de clave y se descartan
    a proposito — para esos manda el titulo.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or not p.scheme.startswith("http"):
        return None
    if host in ("news.google.com", "finnhub.io"):
        return None                       # redirectores: la URL no identifica la noticia
    path = (p.path or "/").rstrip("/") or "/"
    return host + path


def norm_title(title):
    """Titulo reducido a su identidad: minusculas, sin publisher, sin relleno, N palabras."""
    if not title or not isinstance(title, str):
        return None
    t = _PUB_SUFFIX.sub("", title.strip())
    t = _NONWORD.sub(" ", t.lower())
    words = [w for w in _WS.split(t) if w and w not in _STOP]
    if len(words) < 3:                    # demasiado corto para identificar nada
        words = [w for w in _WS.split(_NONWORD.sub(" ", title.lower())) if w]
    if not words:
        return None
    return " ".join(words[:KEY_WORDS])


def keys(title, url=None):
    """Claves de dedup de un titular, de la mas fuerte a la mas debil. Lista (puede ser 1)."""
    out = []
    cu = canon_url(url)
    if cu:
        out.append("u:" + hashlib.sha1(cu.encode("utf-8")).hexdigest()[:16])
    nt = norm_title(title)
    if nt:
        out.append("t:" + hashlib.sha1(nt.encode("utf-8")).hexdigest()[:16])
    return out


class Store:
    """{clave: epoch_visto}. Poda a TTL_S en cada carga: nunca guarda mas de 24 h."""

    def __init__(self, path=DEFAULT_PATH, ttl_s=TTL_S):
        self.path = path
        self.ttl_s = ttl_s
        self.lock_path = path + ".lock"

    # --- disco ---------------------------------------------------------------------
    def _read(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            print("news_store: %s ilegible (%s) — se sigue con memoria vacia, habra "
                  "republicacion" % (self.path, e.__class__.__name__), file=sys.stderr)
            return {}
        if not isinstance(d, dict):
            print("news_store: %s no es un objeto — memoria vacia" % self.path, file=sys.stderr)
            return {}
        return {k: v for k, v in d.items() if isinstance(v, (int, float))}

    def _write(self, data):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp.%d" % os.getpid()
        with open(tmp, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, self.path)

    def _prune(self, data, now):
        return {k: v for k, v in data.items() if now - v < self.ttl_s}

    def load(self, now=None):
        """Contenido vigente (ya podado). Sin lock: solo para inspeccion/tests."""
        return self._prune(self._read(), now if now is not None else time.time())

    # --- API ------------------------------------------------------------------------
    def filter_new(self, items, now=None):
        """items: [(titulo, url, payload)] -> los que NUNCA se vieron, marcandolos vistos.

        Atomico entre procesos (lock exclusivo) y dentro del propio lote: dos titulares del
        mismo barrido que comparten clave salen UNA vez. Devuelve la sublista en el orden de
        entrada. Si el lote no se puede persistir, LEVANTA — republicar es mejor que creerse
        que se guardo y perder la memoria del dia.
        """
        now = time.time() if now is None else now
        out = []
        os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            data = self._prune(self._read(), now)
            for it in items:
                title, url = it[0], (it[1] if len(it) > 1 else None)
                ks = keys(title, url)
                if not ks:
                    continue                        # sin identidad: no se publica a ciegas
                if any(k in data for k in ks):
                    continue
                for k in ks:
                    data[k] = now
                out.append(it)
            self._write(data)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        return out

    def seen(self, title, url=None, now=None):
        """True si el titular ya se publico en las ultimas 24 h. No marca nada."""
        data = self.load(now)
        return any(k in data for k in keys(title, url))

    def stats(self, now=None):
        data = self.load(now)
        return {"claves": len(data), "ttl_h": self.ttl_s / 3600.0, "fichero": self.path}


def main():
    """Inspeccion: cuantas claves vivas y cuando expira la mas vieja."""
    s = Store()
    now = time.time()
    data = s.load(now)
    if not data:
        print("news_store vacio (%s)" % s.path)
        return 0
    vieja = min(data.values())
    print("news_store: %d claves vivas | mas vieja hace %.1f h | TTL %.0f h | %s"
          % (len(data), (now - vieja) / 3600.0, s.ttl_s / 3600.0, s.path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as e:
        if e.errno != errno.EPIPE:
            raise
