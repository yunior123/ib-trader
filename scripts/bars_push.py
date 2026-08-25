#!/usr/bin/env python3
"""Empuja a D1 las barras 1m que el Mac construye del WebSocket.

POR QUE: el historico del chart online entra por REST del vault y la cuota diaria es
COMPARTIDA. Cuando se agota, el grafico se queda con las velas del ultimo dia bueno y el
tick vivo suelto: un hueco de horas en pantalla (medido 2026-08-24 en las seis ventanas).
El WebSocket no gasta cuota y ya escribe data/bars_<sym>_ibkr.txt: esto solo lo sube.

Estado propio en data/bars_push_state.json (ultimo epoch subido por simbolo) para no
reenviar. Fail-loud: si el worker responde != 200 se levanta; nada de fallos mudos.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
ESTADO = os.path.join(DATA, "bars_push_state.json")
BASE = os.environ.get("IBT_WORKER", "https://ibtrader.quant-academy.workers.dev")
# Los seis del cockpit: son los que se miran. Subir los 36 multiplicaria las escrituras a D1.
COCKPIT = ["QQQ", "SPY", "NVDA", "TSLA", "SMH", "SPCX"]
TOPE = 2000          # el mismo tope que declara el endpoint
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
ATRAS_S = 6 * 3600   # de un arranque en frio se suben como mucho 6 h


def _key() -> str:
    v = os.environ.get("IBT_PUSH_KEY")
    if v:
        return v
    with open(os.path.join(REPO, "feeds.env"), encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("IBT_PUSH_KEY="):
                return ln.split("=", 1)[1].strip()
    raise SystemExit("falta IBT_PUSH_KEY (feeds.env o entorno)")


def _estado() -> dict:
    try:
        with open(ESTADO, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _guardar(d: dict) -> None:
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, separators=(",", ":"))
    os.replace(tmp, ESTADO)


def _barras(sym: str, desde: int) -> list[dict]:
    """Lee data/bars_<sym>_ibkr.txt: 'EPOCH O H L C V'. El ts que quiere D1 es UTC."""
    ruta = os.path.join(DATA, "bars_%s_ibkr.txt" % sym.lower())
    out = []
    try:
        with open(ruta, encoding="utf-8") as fh:
            for ln in fh:
                p = ln.split()
                if len(p) < 6:
                    continue
                try:
                    ep = int(float(p[0]))
                except ValueError:
                    continue
                if ep <= desde:
                    continue
                ts = dt.datetime.fromtimestamp(ep, dt.timezone.utc)
                out.append({"sym": sym, "tf": "1m",
                            "ts": ts.strftime("%Y-%m-%d %H:%M:%S.000000"),
                            "o": float(p[1]), "h": float(p[2]), "l": float(p[3]),
                            "c": float(p[4]), "v": float(p[5])})
    except OSError:
        return []
    return out[-TOPE:]


def main() -> int:
    key = _key()
    est = _estado()
    # --completo ignora el estado y reenvia la ventana entera. Hace falta porque el warmup del
    # vault mete barras ANTERIORES a la ultima subida (la manana que la cuota dejo sin cubrir),
    # y un push que solo avanza hacia adelante no las veria nunca. INSERT OR REPLACE en el
    # worker lo hace idempotente.
    completo = "--completo" in sys.argv
    if completo:
        est = {}
    corte = int(time.time()) - ATRAS_S
    total = 0
    for sym in COCKPIT:
        desde = max(int(est.get(sym, 0)), corte)
        filas = _barras(sym, desde)
        if not filas:
            continue
        req = urllib.request.Request(
            "%s/tarea/barras-push?key=%s" % (BASE, urllib.parse.quote(key)),
            data=json.dumps(filas).encode("utf-8"),
            # Sin User-Agent de navegador, Cloudflare responde 1010 (firma de bot) — medido.
            headers={"content-type": "application/json", "user-agent": UA}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise SystemExit("%s: worker HTTP %d %s" % (sym, e.code, e.read()[:200]))
        ultimo = int(dt.datetime.strptime(filas[-1]["ts"], "%Y-%m-%d %H:%M:%S.%f")
                     .replace(tzinfo=dt.timezone.utc).timestamp())
        est[sym] = ultimo
        total += res.get("guardadas", 0)
        print("%s: %d guardadas, %d descartadas" % (sym, res.get("guardadas", 0),
                                                    res.get("descartadas", 0)))
    _guardar(est)
    print("total %d barras" % total)
    return 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
