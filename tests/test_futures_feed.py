"""futures_feed: el mapa de HUECO de la noche.

Contexto medido el 2026-08-02 21:18 ET (domingo): el ultimo print de SPY/QQQ/NVDA/AAPL era del
viernes 19:59 y el WebSocket de Finnhub, conectado y suscrito a 26 simbolos, llevaba 0 trades.
Las acciones US no cotizan el domingo por la noche; los futuros si (CME abre 18:00 ET). Lo que
estos tests fijan es que el mapa no finja: nada de %0 cuando no hay dato, nada de "apertura
implicita" igual al cierre, y el retraso declarado en cada fila.
"""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

_spec = importlib.util.spec_from_file_location(
    "futures_feed", os.path.join(REPO, "scripts", "futures_feed.py")
)
FF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FF)


# ---------- universo desde fichero ----------

def test_universo_sale_del_fichero_del_repo():
    filas = FF.universo()
    nombres = [f[0] for f in filas]
    assert nombres[:2] == ["NQ", "ES"], "NQ y ES son los capitanes de la noche, en ese orden"
    por_nombre = {f[0]: f for f in filas}
    assert por_nombre["NQ"][4] == "QQQ" and por_nombre["ES"][4] == "SPY"
    assert por_nombre["CL"][4] is None, "'-' significa sin proxy de contado, no la cadena '-'"
    assert por_nombre["NQ"][3] == "Nasdaq-100 E-mini", "la etiqueta admite espacios"


def test_universo_vacio_levanta(tmp_path):
    p = tmp_path / "futures.txt"
    p.write_text("# solo comentarios\n\n")
    with pytest.raises(RuntimeError, match="sin futuros"):
        FF.universo(str(p))


# ---------- apertura implicita ----------

def _bars(tmp_path, sym, cierre):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / f"bars_{sym.lower()}_ibkr.txt").write_text(
        f"1785479280 1 1 1 {cierre} 0\n1785479340 1 1 1 {cierre} 0\n")


def test_apertura_implicita_mueve_el_cierre_por_el_pct(tmp_path, monkeypatch):
    monkeypatch.setattr(FF, "ROOT", str(tmp_path))
    _bars(tmp_path, "QQQ", 684.56)
    io = FF._implied_open("QQQ", 0.662)
    assert io["cierre_previo"] == 684.56
    assert io["apertura_implicita"] == pytest.approx(689.0918, abs=1e-3)
    assert io["delta"] == pytest.approx(4.5318, abs=1e-3)


def test_sin_pct_no_hay_apertura_implicita(tmp_path, monkeypatch):
    monkeypatch.setattr(FF, "ROOT", str(tmp_path))
    _bars(tmp_path, "QQQ", 684.56)
    # None y NO el cierre: devolver el cierre se leeria como "abre plano", que es una afirmacion
    assert FF._implied_open("QQQ", None) is None


def test_sin_barras_no_hay_apertura_implicita(tmp_path, monkeypatch):
    monkeypatch.setattr(FF, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir(exist_ok=True)
    assert FF._implied_open("QQQ", 1.0) is None


def test_sin_cash_proxy_no_hay_apertura_implicita(tmp_path, monkeypatch):
    monkeypatch.setattr(FF, "ROOT", str(tmp_path))
    assert FF._implied_open(None, 1.0) is None


# ---------- Corea ----------

def test_corea_lee_el_cierre_de_referencia_del_json(tmp_path, monkeypatch):
    monkeypatch.setattr(FF, "ROOT", str(tmp_path))
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "korea_prevclose.json").write_text(json.dumps(
        {"samsung": {"close": 265000.0, "epoch": 1785479340, "session": "2026-07-31"}}))
    (d / "bars_samsung.txt").write_text("1785715980 1 1 1 241750.0 0\n")
    kr = FF._corea()
    assert kr["samsung"]["pct"] == pytest.approx(-8.774, abs=1e-3)
    assert kr["samsung"]["sesion_ref"] == "2026-07-31"


def test_corea_sin_referencia_devuelve_none_no_cero(tmp_path, monkeypatch):
    monkeypatch.setattr(FF, "ROOT", str(tmp_path))
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "bars_kospi.txt").write_text("1785715980 1 1 1 99480.0 0\n")
    assert FF._corea()["kospi"]["pct"] is None


# ---------- escritura atomica ----------

def test_escribe_atomico_y_relee(tmp_path):
    p = tmp_path / "futures_overnight.json"
    FF.escribir({"ts": 1, "futuros": []}, str(p))
    assert json.loads(p.read_text())["ts"] == 1
    assert not (tmp_path / "futures_overnight.json.tmp").exists()
