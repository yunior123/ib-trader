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
    assert rt_last.write_if_newer("SPY", 1785716902.5, 744.27, 100, "finnhub") is True
    ep, px, sz, src = rt_last.read("SPY")
    assert (round(ep, 1), px, sz, src) == (1785716902.5, 744.27, 100.0, "finnhub")


def test_un_tick_mas_viejo_NO_pisa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("SPY", 2000.0, 744.27, 1, "finnhub")
    assert rt_last.write_if_newer("SPY", 1999.0, 700.00, 1, "intrinio") is False
    assert rt_last.read("SPY")[1] == 744.27


def test_mismo_epoch_NO_pisa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("SPY", 2000.0, 744.27, 1, "finnhub")
    assert rt_last.write_if_newer("SPY", 2000.0, 1.0, 1, "otro") is False


def test_tick_mas_nuevo_SI_pisa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("SPY", 2000.0, 744.27, 1, "finnhub")
    assert rt_last.write_if_newer("SPY", 2001.0, 745.10, 2, "intrinio") is True
    assert rt_last.read("SPY")[3] == "intrinio"


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
