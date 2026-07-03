"""IntrinioRealtimeProvider: lo unico que no puede fallar es que MIENTA.

Con el socket caido tiene que LEVANTAR, no devolver 0 ni el ultimo precio conocido: un precio
rancio servido como vivo pasa el gate de spread y compra el maximo.
"""
from __future__ import annotations

import sys
import types

import pytest

from backend.app.providers.base import PROVIDER_REGISTRY, ProviderError


def _stub_sdk(monkeypatch):
    """El SDK real abre sockets; aqui solo hace falta que el import exista."""
    mod = types.ModuleType("intriniorealtime.equities_client")
    mod.IntrinioRealtimeEquitiesClient = object
    pkg = types.ModuleType("intriniorealtime")
    monkeypatch.setitem(sys.modules, "intriniorealtime", pkg)
    monkeypatch.setitem(sys.modules, "intriniorealtime.equities_client", mod)
    return mod


def _provider(monkeypatch):
    from backend.app.config import Settings
    from backend.app.providers.intrinio_realtime import IntrinioRealtimeProvider

    monkeypatch.setenv("INTRINIO_API_KEY", "k-de-prueba")
    return IntrinioRealtimeProvider(Settings())


def test_registrado_como_plugin_de_market():
    import backend.app.providers.registry  # noqa: F401  — su import dispara el auto-discovery

    cls = PROVIDER_REGISTRY.get("intrinio_realtime")
    assert cls is not None, "el @register no llego al registro (¿fallo de import?)"
    assert cls.__capabilities__ == {"market"}


def test_sin_sdk_levanta_con_codigo_accionable(monkeypatch):
    from backend.app.config import Settings
    from backend.app.providers.intrinio_realtime import IntrinioRealtimeProvider

    monkeypatch.setenv("INTRINIO_API_KEY", "k-de-prueba")
    # None en sys.modules hace que el import levante ImportError (no lo resuelve del disco).
    monkeypatch.setitem(sys.modules, "intriniorealtime.equities_client", None)
    with pytest.raises(ProviderError) as e:
        IntrinioRealtimeProvider(Settings())
    assert e.value.error_code == "sdk_missing"


@pytest.mark.asyncio
async def test_socket_caido_levanta_no_devuelve_cero(monkeypatch):
    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    monkeypatch.setattr(p, "_connect_error", "socket Intrinio EQUITIES_EDGE no conecta")
    with pytest.raises(ProviderError) as e:
        await p.get_quote("SPY")
    assert e.value.error_code == "socket_down"


@pytest.mark.asyncio
async def test_tick_rancio_levanta(monkeypatch):
    """Un tick mas viejo que MAX_TICK_AGE_S no vale: se levanta en vez de servirlo como vivo."""
    import time

    from backend.app.providers import intrinio_realtime as rt

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    monkeypatch.setattr(p, "_ensure_client", lambda: None)
    monkeypatch.setattr(p, "_join", lambda s: None)
    monkeypatch.setattr(rt, "MAX_TICK_AGE_S", 5.0)
    p._trades["SPY"] = (time.time() - 600, 744.27, 100)  # epoch de bolsa viejo
    with pytest.raises(ProviderError) as e:
        await p.get_quote("SPY")
    assert e.value.error_code == "no_tick"


@pytest.mark.asyncio
async def test_tick_vivo_devuelve_quote_con_bid_ask_reales(monkeypatch):
    import time

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    monkeypatch.setattr(p, "_ensure_client", lambda: None)
    monkeypatch.setattr(p, "_join", lambda s: None)
    now = time.time()
    p._trades["SPY"] = (now, 744.27, 100)
    p._quotes["SPY"] = {"bid": (744.25, 300, now), "ask": (744.29, 200, now)}
    q = await p.get_quote("SPY")
    assert (q.last, q.bid, q.ask) == (744.27, 744.25, 744.29)
    assert q.bid_size == 300


@pytest.mark.asyncio
async def test_sin_quote_el_bid_ask_queda_en_cero_no_se_fabrica(monkeypatch):
    """Nunca derivar bid/ask del last: un spread falso estrecho pasa el gate. 0 -> el puente rechaza."""
    import time

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    monkeypatch.setattr(p, "_ensure_client", lambda: None)
    monkeypatch.setattr(p, "_join", lambda s: None)
    p._trades["SPY"] = (time.time(), 744.27, 100)
    q = await p.get_quote("SPY")
    assert q.bid == 0 and q.ask == 0


def test_quote_sin_lado_se_descarta(monkeypatch):
    """Un quote sin type bid/ask guardado a ciegas fabricaria un spread invertido."""
    import time

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    ns = int(time.time() * 1e9)
    p._on_quote(types.SimpleNamespace(symbol="SPY", price=744.0, size=10, type="unknown", timestamp=ns))
    assert "SPY" not in p._quotes
    p._on_quote(types.SimpleNamespace(symbol="SPY", price=744.0, size=10, type="bid", timestamp=ns))
    assert p._quotes["SPY"]["bid"][:2] == (744.0, 10.0)


def test_timestamp_es_de_bolsa_en_nanosegundos(monkeypatch):
    """El SDK entrega ns de bolsa. Si se guardara la hora de LLEGADA, un feed con retraso
    quedaria marcado como vivo y pasaria el gate de 10 s: justo el bug que costo dinero."""
    import time

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    exch = time.time() - 3
    p._on_trade(types.SimpleNamespace(symbol="SPY", price=744.0, size=5, timestamp=int(exch * 1e9)))
    assert abs(p._trades["SPY"][0] - exch) < 0.01


def test_timestamp_absurdo_descarta_el_tick(monkeypatch):
    """Segundos donde se esperaban nanosegundos = 1970. Se descarta, no se 'corrige'."""
    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    p._on_trade(types.SimpleNamespace(symbol="SPY", price=744.0, size=5, timestamp=1785650000))
    assert "SPY" not in p._trades


@pytest.mark.asyncio
async def test_lado_rancio_no_se_mezcla_con_trade_fresco(monkeypatch):
    """Bid de hace 10 min + last de hace 1 s = spread inventado. El lado viejo cae a 0."""
    import time

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    monkeypatch.setattr(p, "_ensure_client", lambda: None)
    monkeypatch.setattr(p, "_join", lambda s: None)
    now = time.time()
    p._trades["SPY"] = (now, 744.27, 100)
    p._quotes["SPY"] = {"bid": (700.0, 300, now - 600), "ask": (744.29, 200, now)}
    q = await p.get_quote("SPY")
    assert q.bid == 0 and q.ask == 744.29


def test_preflight_evita_el_hilo_infinito_del_sdk(monkeypatch):
    """equities_client.py:262 hace requests.get SIN timeout y connect() reintenta para siempre.
    Con el socket apagado (lo normal de noche) el pre-chequeo debe cortar ANTES de tocar el SDK."""
    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)

    class _Muerto:
        def get(self, *a, **k):
            assert k.get("timeout"), "el pre-chequeo DEBE llevar timeout"
            raise ConnectionError("Remote end closed connection without response")

    monkeypatch.setitem(sys.modules, "requests", _Muerto())
    motivo = p._auth_alcanzable()
    assert motivo and "equities-edge/auth no responde" in motivo

    hilos = []
    monkeypatch.setattr("threading.Thread", lambda *a, **k: hilos.append(k) or (_ for _ in ()).throw(
        AssertionError("no se debe arrancar el hilo del SDK con el auth caido")))
    with pytest.raises(ProviderError) as e:
        p._ensure_client()
    assert e.value.error_code == "socket_down"
    assert hilos == []


def test_preflight_deja_pasar_cuando_hay_token(monkeypatch):
    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)

    class _Resp:
        status_code = 200
        text = "T" * 60

    class _Vivo:
        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setitem(sys.modules, "requests", _Vivo())
    assert p._auth_alcanzable() is None


def test_preflight_no_traga_un_200_vacio(monkeypatch):
    """200 con cuerpo corto no es token: arrancar el SDK ahi seria el bucle infinito otra vez."""
    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)

    class _Resp:
        status_code = 200
        text = "  "

    class _Raro:
        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setitem(sys.modules, "requests", _Raro())
    assert "sin token" in (p._auth_alcanzable() or "")


def test_el_error_de_conexion_CADUCA_y_se_reintenta(monkeypatch):
    """Intrinio apaga el cluster de noche y lo enciende por la manana. Su propio SDK no se recupera
    (intrinio-realtime-options-python-sdk#7, abierto desde 2024-02: "cae sobre medianoche... el
    cliente sigue desconectado CUANDO EL MERCADO ABRE"). Si cacheamos el error para siempre, el
    provider queda muerto justo el dia que hace falta."""
    import time

    from backend.app.providers import intrinio_realtime as rt

    _stub_sdk(monkeypatch)
    p = _provider(monkeypatch)
    intentos = []
    monkeypatch.setattr(p, "_auth_alcanzable", lambda: intentos.append(1) or "socket apagado")
    monkeypatch.setattr(rt, "ERROR_TTL_S", 0.05)

    with pytest.raises(ProviderError) as e:      # 1a: el socket esta caido
        p._ensure_client()
    assert e.value.error_code == "socket_down"

    with pytest.raises(ProviderError):           # 2a inmediata: NO machaca al servidor
        p._ensure_client()
    assert len(intentos) == 1, "dentro del TTL no debe repreguntar"

    time.sleep(0.06)                             # pasa el TTL: el cluster pudo encender
    with pytest.raises(ProviderError):
        p._ensure_client()
    assert len(intentos) == 2, "tras el TTL DEBE reintentar; si no, queda muerto para siempre"
