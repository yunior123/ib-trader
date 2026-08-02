"""Un timeout puntual NO puede dejar a un simbolo de la flota sin mapa de opciones.

Medido el 2026-08-02: NFLX, GLD y XLK se quedaron sin data/opt_chain_*.txt mientras Polygon SI
los servia — el puente no reintentaba y una sola ReadTimeout los dejaba mudos toda la sesion.
Un ticker de la flota sin cadena no vota muros: es un agujero silencioso en el mapa.
"""
import asyncio
import importlib.util
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(sys.version_info < (3, 10), reason="el puente exige py3.10+")


def _load():
    path = os.path.join(REPO, "scripts", "provider_bridge.py")
    spec = importlib.util.spec_from_file_location("ibt_provider_bridge", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Opts:
    """Falla las primeras `fallos` veces y luego devuelve cadena."""

    def __init__(self, fallos):
        self.fallos = fallos
        self.llamadas = 0

    async def get_option_chain(self, sym):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise TimeoutError("ReadTimeout")
        return [types.SimpleNamespace(delta=0.5, strike=100.0)]  # forma real: _spot_from_chain lee .delta/.strike


def _correr(monkeypatch, mod, opts):
    escrito, logs = [], []
    monkeypatch.setattr(mod, "write_chain", lambda s, c, sp, p: escrito.append(s) or len(c))
    monkeypatch.setattr(mod, "write_status", lambda *a, **k: None)
    monkeypatch.setattr(mod, "log", lambda m: logs.append(m))
    async def _sin_espera(_s):        # mod.asyncio ES el asyncio global: parchear con
        return None                   # asyncio.sleep se llamaria a si mismo (recursion)
    monkeypatch.setattr(mod.asyncio, "sleep", _sin_espera)

    class _Mkt:
        async def get_quote(self, sym):
            raise RuntimeError("sin quote")   # el fallo de quote no debe tapar la cadena

    class _P:
        market = _Mkt()
        options = opts

    class _S:
        options_provider = "polygon"

    asyncio.run(mod.one_pass(_P(), _S(), ["NFLX"], {}, {}, False, True, []))
    return escrito, logs


def test_un_timeout_puntual_se_reintenta_y_la_cadena_se_escribe(monkeypatch):
    mod = _load()
    opts = _Opts(fallos=1)
    escrito, logs = _correr(monkeypatch, mod, opts)
    assert opts.llamadas == 2, "no reintento: un timeout dejaria el simbolo mudo"
    assert escrito == ["NFLX"]
    assert any("fallo 1/2" in m for m in logs)


def test_fallo_persistente_grita_SIN_MAPA_y_no_escribe_nada(monkeypatch):
    """Si de verdad no hay cadena, se dice fuerte y NO se escribe un fichero a medias."""
    mod = _load()
    opts = _Opts(fallos=9)
    escrito, logs = _correr(monkeypatch, mod, opts)
    assert opts.llamadas == 2, "el reintento esta acotado: 2 intentos, no un bucle"
    assert escrito == []
    assert any("SIN MAPA DE OPCIONES" in m for m in logs)


def test_a_la_primera_no_reintenta(monkeypatch):
    mod = _load()
    opts = _Opts(fallos=0)
    escrito, _ = _correr(monkeypatch, mod, opts)
    assert opts.llamadas == 1 and escrito == ["NFLX"]
