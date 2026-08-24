#!/usr/bin/env python3
"""Presupuesto y cortacircuito COMPARTIDOS de la cuota REST de London Strategic Edge.

Por que existe (medido 2026-08-24): la cuota es 15.000 peticiones/dia por API KEY, y la
comparten el Mac y el worker de Cloudflare. `provider_bridge` pedia NBBO cada 7 s para 32
simbolos (get_quote llamaba a get_bars(limit=1)) = ~274 pet/min -> la cuota moria en menos
de una hora, y despues seguia martilleando: 58.823 peticiones 429 en un dia, y el ib-trader
online congelado en las barras del viernes.

Reglas:
  · techo local (LSE_LOCAL_CAP, 4000 por defecto) para dejarle el resto al worker;
  · al ver "daily request limit reached" se BLOQUEA todo cliente local hasta el reset
    (00:00 UTC + margen) sin volver a tocar la red — un 429 gasta cuota igual;
  · fail-loud: se levanta LSEBudgetError. Jamas se devuelve un precio plausible.
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTADO = os.path.join(REPO, "data", "lse_budget.json")
CAP = int(os.environ.get("LSE_LOCAL_CAP", "4000"))
# El reset no viene en ninguna cabecera del 429 (medido: solo date/cf-ray). Se asume 00:00 UTC
# y se DECLARA; `sonda_ok()` lo corrige en cuanto una peticion real vuelve a pasar.
MARGEN_RESET_S = 120.0


class LSEBudgetError(RuntimeError):
    """La cuota local se agoto o la diaria esta bloqueada. No es un fallo de red."""


def _hoy_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _proximo_reset() -> float:
    ahora = datetime.now(timezone.utc)
    manana = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return manana.timestamp() + MARGEN_RESET_S


def _leer(fh) -> dict:
    fh.seek(0)
    try:
        d = json.load(fh)
    except ValueError:
        d = {}
    if not isinstance(d, dict) or d.get("dia") != _hoy_utc():
        d = {"dia": _hoy_utc(), "n": 0, "bloqueado_hasta": 0.0, "motivo": None}
    return d


def _escribir(fh, d: dict) -> None:
    fh.seek(0)
    fh.truncate()
    json.dump(d, fh, separators=(",", ":"))
    fh.flush()
    os.fsync(fh.fileno())


def _abrir():
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    fh = open(ESTADO, "a+", encoding="utf-8")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    return fh


def consumir(n: int = 1, quien: str = "") -> None:
    """Reserva n peticiones. Levanta LSEBudgetError si hay bloqueo o se pasa el techo."""
    fh = _abrir()
    try:
        d = _leer(fh)
        bloq = float(d.get("bloqueado_hasta") or 0.0)
        if bloq > time.time():
            raise LSEBudgetError(
                "cuota diaria de LSE agotada (%s); reintento a las %s UTC"
                % (d.get("motivo") or "429", datetime.fromtimestamp(bloq, timezone.utc).strftime("%H:%M")))
        if bloq:
            d["bloqueado_hasta"], d["motivo"] = 0.0, None
        if d["n"] + n > CAP:
            _escribir(fh, d)
            raise LSEBudgetError("techo local de %d peticiones/dia alcanzado (%d gastadas); "
                                "el resto de la cuota es del worker online" % (CAP, d["n"]))
        d["n"] += n
        d.setdefault("por_quien", {})
        if quien:
            d["por_quien"][quien] = int(d["por_quien"].get(quien, 0)) + n
        _escribir(fh, d)
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def agotado(motivo: str = "daily request limit reached") -> None:
    """El vault dijo que la cuota diaria murio: se corta a TODOS los clientes locales."""
    fh = _abrir()
    try:
        d = _leer(fh)
        d["bloqueado_hasta"] = _proximo_reset()
        d["motivo"] = str(motivo)[:120]
        _escribir(fh, d)
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def sonda_ok() -> None:
    """Una peticion real paso: se levanta el bloqueo (el reset llego antes de lo asumido)."""
    fh = _abrir()
    try:
        d = _leer(fh)
        if d.get("bloqueado_hasta"):
            d["bloqueado_hasta"], d["motivo"] = 0.0, None
            _escribir(fh, d)
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def bloqueado() -> bool:
    fh = _abrir()
    try:
        return float(_leer(fh).get("bloqueado_hasta") or 0.0) > time.time()
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def estado() -> dict:
    fh = _abrir()
    try:
        d = _leer(fh)
        d["techo"] = CAP
        d["restante"] = max(0, CAP - int(d.get("n") or 0))
        return d
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        os.path.exists(ESTADO) and os.remove(ESTADO)
        print("estado borrado")
    else:
        print(json.dumps(estado(), indent=1))
