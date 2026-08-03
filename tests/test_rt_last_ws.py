"""rt_last + puentes de WebSocket: un solo dueño por fichero y cero precios fabricados.

Contexto medido el 2026-08-02 (todas las keys de la casa, el mismo dia):
  Intrinio  -> 7 hosts, TLS valido, ALPN sin acordar, cierre a 5,13 s sin cabecera HTTP
  Polygon   -> `auth_failed "Your plan doesn't include websocket access"`
  UW        -> /api/socket acepta el TCP y corta al instante; el REST da {"data":[]}
  Finnhub   -> CONECTA, admite las 26 suscripciones y late
Con varios streams escribiendo el mismo `rt_last_<SYM>.txt`, el ultimo en llegar ganaria
aunque su tick fuese mas viejo: un precio rancio disfrazado de vivo.
"""
import importlib.util
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import rt_last  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "finnhub_ws_bridge", os.path.join(REPO, "scripts", "finnhub_ws_bridge.py")
)
FWB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FWB)


def _cd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)


def test_escribe_y_relee(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    ahora = time.time()
    assert rt_last.write_if_newer("SPY", ahora, 744.27, 100, "finnhub") is True
    ep, px, sz, src = rt_last.read("SPY")
    # tolerancia y no round(): el fichero guarda .3f y en el limite .x5 los dos redondeos
    # caian a lados distintos (flake real, visto 2026-08-03).
    assert abs(ep - ahora) < 0.01 and (px, sz, src) == (744.27, 100.0, "finnhub")


def test_un_tick_mas_viejo_NO_pisa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    a = time.time()
    rt_last.write_if_newer("SPY", a, 744.27, 1, "finnhub")
    assert rt_last.write_if_newer("SPY", a - 1, 700.00, 1, "intrinio") is False
    assert rt_last.read("SPY")[1] == 744.27


def test_mismo_epoch_NO_pisa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("SPY", 2000.0, 744.27, 1, "finnhub")
    assert rt_last.write_if_newer("SPY", 2000.0, 1.0, 1, "otro") is False


def test_tick_mas_nuevo_SI_pisa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    a = time.time()
    rt_last.write_if_newer("SPY", a - 5, 744.27, 1, "finnhub")
    assert rt_last.write_if_newer("SPY", a, 745.10, 2, "intrinio") is True
    assert rt_last.read("SPY")[3] == "intrinio"


def test_un_tick_que_NACE_VIEJO_no_entra(tmp_path, monkeypatch):
    """Intrinio entrega con 900 s impuestos (medido 2026-08-03: mediana 900,0 s, minimo 900,0).
    Cuando Finnhub callaba un rato, ese tick ganaba el fichero canonico y rt_last_SPY se quedaba
    con 904 s de antiguedad y pinta de vivo. Un dato que nace con 15 min no es un PRINT."""
    _cd(tmp_path, monkeypatch)
    assert rt_last.write_if_newer("SPY", time.time() - 900, 744.27, 1, "intrinio") is False
    assert rt_last.read("SPY") is None


def test_la_guarda_de_frescura_se_puede_desactivar(tmp_path, monkeypatch):
    """Para backfills y tests: max_age_s=0 apaga la guarda."""
    _cd(tmp_path, monkeypatch)
    assert rt_last.write_if_newer("SPY", 2000.0, 744.27, 1, "x", max_age_s=0) is True


def test_tick_fresco_de_fuente_lenta_SI_entra(tmp_path, monkeypatch):
    """La guarda mira la EDAD del tick, no quien lo manda: si Intrinio mandara uno fresco, entra."""
    _cd(tmp_path, monkeypatch)
    assert rt_last.write_if_newer("SPY", time.time() - 2, 744.27, 1, "intrinio") is True


def test_precio_cero_o_negativo_se_rechaza(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    assert rt_last.write_if_newer("SPY", 2000.0, 0.0, 1, "x") is False
    assert rt_last.write_if_newer("SPY", 2000.0, -3.0, 1, "x") is False
    assert rt_last.read("SPY") is None      # None, no un 0 plausible


def test_sin_epoch_se_rechaza(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    assert rt_last.write_if_newer("SPY", 0, 744.0, 1, "x") is False


def test_fichero_corrupto_devuelve_none(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    with open("data/rt_last_SPY.txt", "w") as f:
        f.write("basura\n")
    assert rt_last.read("SPY") is None


# ---------- puente Finnhub ----------

def test_universo_sale_de_provider_syms(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    with open("data/provider_syms.txt", "w") as f:
        f.write("QQQ SPY NVDA\n")
    assert FWB.simbolos(["finnhub_ws_bridge.py"]) == ["QQQ", "SPY", "NVDA"]


def test_syms_por_linea_de_comandos_manda(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    with open("data/provider_syms.txt", "w") as f:
        f.write("QQQ SPY\n")
    assert FWB.simbolos(["x", "--syms", "mu", "smh"]) == ["MU", "SMH"]


def test_estado_declara_que_no_hay_libro(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    monkeypatch.setattr(FWB, "STATUS", os.path.join(tmp_path, "data", "ws_finnhub_status.json"))
    FWB.estado(conectado=True, nbbo=None,
               nbbo_motivo="Finnhub gratis no trae libro: no se escribe nbbo_*")
    d = json.load(open(FWB.STATUS))
    assert d["nbbo"] is None and "libro" in d["nbbo_motivo"]


def test_estado_acumula_sin_perder_lo_anterior(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    monkeypatch.setattr(FWB, "STATUS", os.path.join(tmp_path, "data", "ws_finnhub_status.json"))
    FWB.estado(conectado=True, simbolos=["SPY"])
    FWB.estado(trades=7)
    d = json.load(open(FWB.STATUS))
    assert d["simbolos"] == ["SPY"] and d["trades"] == 7
