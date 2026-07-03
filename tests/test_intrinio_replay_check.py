"""El formato binario del replay de Intrinio, fijado con un mensaje construido a mano.

Si el SDK cambia su parser (o nuestra lectura del formato esta mal), este test se cae en seco en vez
de dejarnos descubrirlo el lunes a las 09:30 con dinero encima.
"""
import importlib.util
import os
import struct

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# El SDK solo vive en venv-mit (py3.12). Bajo el venv de la flota (py3.9) no es importable:
# se SALTA, no se finge que pasa. Correr con: ./venv-mit/bin/python -m pytest tests/test_intrinio_replay_check.py
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("intriniorealtime") is None,
    reason="intriniorealtime no importable en este interprete (usar venv-mit)",
)


def _load():
    path = os.path.join(REPO, "scripts", "intrinio_replay_check.py")
    spec = importlib.util.spec_from_file_location("ibt_intrinio_replay_check", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _trade_msg(symbol=b"SPY", price=745.25, size=100, ts_ns=1785600000000000000, volume=12345):
    """Layout leido de intriniorealtime/equities_client.py:parse_trade."""
    sl = len(symbol)
    largo = 27 + sl  # hasta condition_length (condicion vacia)
    b = bytearray(largo)
    b[0] = 0                 # tipo: trade
    b[1] = largo             # longitud del mensaje, incluidos estos 2 bytes
    b[2] = sl
    b[3:3 + sl] = symbol
    b[3 + sl] = 8            # subprovider 8 = EQUITIES_EDGE
    b[4 + sl:6 + sl] = " ".encode("utf-16-le") + b"\x00" * 0  # market_center, 2 bytes utf-16
    struct.pack_into("<fLQL", b, 6 + sl, price, size, ts_ns, volume)
    b[26 + sl] = 0           # condition_length
    return bytes(b) + struct.pack("<Q", ts_ns)  # + time_received


def test_parsea_un_trade_construido_a_mano():
    mod = _load()
    vistos = []
    r = mod.parsear(_trade_msg(), lambda t, backlog=0: vistos.append(t), lambda q, backlog=0: None)
    assert r["err"] == 0, "el parser del SDK rechaza nuestro layout: el formato cambio"
    assert r["ok"] == 1
    assert r["tipos"] == {0: 1}
    t = vistos[0]
    assert t.symbol == "SPY"
    assert abs(t.price - 745.25) < 0.01
    assert t.size == 100
    assert t.timestamp == 1785600000000000000
    assert t.subprovider == "EQUITIES_EDGE"


def test_varios_mensajes_seguidos_se_encadenan():
    """El avance es len+8; si estuviera mal, el segundo mensaje saldria basura."""
    mod = _load()
    vistos = []
    data = _trade_msg(b"SPY", 745.25) + _trade_msg(b"QQQ", 690.5) + _trade_msg(b"NVDA", 180.75)
    r = mod.parsear(data, lambda t, backlog=0: vistos.append(t), lambda q, backlog=0: None)
    assert (r["ok"], r["err"]) == (3, 0)
    assert [t.symbol for t in vistos] == ["SPY", "QQQ", "NVDA"]


def test_cola_truncada_no_revienta():
    """Un prefijo por HTTP Range casi siempre corta a mitad del ultimo mensaje: se ignora, no peta."""
    mod = _load()
    data = _trade_msg(b"SPY") + _trade_msg(b"QQQ")[:9]
    r = mod.parsear(data, lambda t, backlog=0: None, lambda q, backlog=0: None)
    assert (r["ok"], r["err"]) == (1, 0)


def test_ultimo_dia_habil_nunca_devuelve_hoy_ni_finde():
    """Pedir el replay de hoy o de un sabado da 404/403: la fecha por defecto tiene que ser util."""
    from datetime import date

    mod = _load()
    d = date.fromisoformat(mod.ultimo_dia_habil())
    assert d.weekday() < 5
    assert d < date.today()
