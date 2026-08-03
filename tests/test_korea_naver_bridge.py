"""korea_naver_bridge: respaldo KRX cuando no hay Gateway (orden Yunior 2026-08-02 "no ibkr this week").

Lo que fijan estos tests es lo que se puede fabricar sin querer: un precio 0 al parsear
"1,589,000", un volumen negativo al rodar el dia, una barra con la hora de LLEGADA en vez
de la de Seul, y un `nbbo_*` inventado (Naver no publica libro -> `askingPrice` da 404).
"""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

_spec = importlib.util.spec_from_file_location(
    "korea_naver_bridge", os.path.join(REPO, "scripts", "korea_naver_bridge.py")
)
KNB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(KNB)


# ---------- parseo de numeros: None, jamas 0 ----------

def test_num_parsea_miles_coreanos():
    assert KNB._num("1,589,000") == 1589000.0
    assert KNB._num("99,855") == 99855.0
    assert KNB._num("-17,500") == -17500.0


def test_num_devuelve_none_no_cero():
    # Un 0 aqui seria un PRECIO de cero, indistinguible de una medicion real.
    for basura in (None, "", "-", "N/A", "거래정지"):
        assert KNB._num(basura) is None


# ---------- reloj de BOLSA, no de llegada ----------

def test_epoch_usa_el_reloj_de_seul():
    ep = KNB.epoch_de({"localTradedAt": "2026-08-03T09:05:34.861334+09:00"})
    assert ep is not None
    # 09:05:34 KST = 00:05:34 UTC del mismo dia
    import datetime as dt
    assert dt.datetime.utcfromtimestamp(ep).strftime("%Y-%m-%dT%H:%M:%S") == "2026-08-03T00:05:34"


def test_epoch_sin_marca_es_none():
    assert KNB.epoch_de({}) is None
    assert KNB.epoch_de({"localTradedAt": "no-es-una-fecha"}) is None


# ---------- agregacion a 1 minuto ----------

def _agg(tmp_path, monkeypatch, name="samsung"):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    return KNB.Agg(name)


def test_barra_se_cierra_al_cambiar_de_minuto(tmp_path, monkeypatch):
    a = _agg(tmp_path, monkeypatch)
    base = 1785715740.0                      # multiplo de 60
    assert a.tick(base + 1, 241000.0, 1000.0) is None
    assert a.tick(base + 20, 243000.0, 1500.0) is None
    assert a.tick(base + 40, 242000.0, 1800.0) is None
    linea = a.tick(base + 61, 242500.0, 2000.0)   # minuto siguiente -> cierra el anterior
    assert linea is not None
    ep, o, h, l, c, v = linea.split()
    assert float(ep) == base
    assert (float(o), float(h), float(l), float(c)) == (241000.0, 243000.0, 241000.0, 242000.0)
    assert float(v) == 800.0                 # 1800 - 1000, delta del acumulado del dia


def test_volumen_nunca_negativo_al_rodar_el_dia(tmp_path, monkeypatch):
    a = _agg(tmp_path, monkeypatch)
    base = 1785715740.0
    a.tick(base + 1, 100.0, 5_000_000.0)     # acumulado alto (fin de sesion)
    a.tick(base + 30, 101.0, 12.0)           # nueva sesion: el acumulado se reinicia
    linea = a.tick(base + 61, 102.0, 20.0)
    assert float(linea.split()[5]) >= 0.0


def test_no_reemite_un_minuto_ya_escrito(tmp_path, monkeypatch):
    a = _agg(tmp_path, monkeypatch)
    base = 1785715740.0
    a.last_emitted = base                    # ese minuto ya esta en el fichero
    a.tick(base + 1, 100.0, 10.0)
    assert a.tick(base + 61, 101.0, 20.0) is None


def test_last_emitted_se_lee_del_fichero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    with open("data/bars_kospi.txt", "w") as f:
        f.write("1785715680 1 1 1 1 0\n1785715740 2 2 2 2 0\n")
    assert KNB.Agg("kospi").last_emitted == 1785715740.0


# ---------- universo desde fichero, no hardcodeado ----------

def test_contratos_salen_del_fichero_del_repo():
    mapa = KNB.contratos()
    assert mapa["samsung"] == "005930"
    assert mapa["skhynix"] == "000660"
    assert len(mapa) >= 3


# ---------- IBKR manda / el respaldo no inventa libro ----------

def test_se_aparta_si_el_gateway_vive(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: 4002)
    monkeypatch.setattr(KNB, "contratos", lambda: {"samsung": "005930"})
    monkeypatch.setattr(sys, "argv", ["korea_naver_bridge.py", "--once"])

    def _no_sondear(_codes):
        raise AssertionError("con Gateway vivo no se debe sondear Naver")

    monkeypatch.setattr(KNB, "sondeo", _no_sondear)
    assert KNB.main() == 0
    assert json.load(open(KNB.SRC_FILE))["fuente"] == "ibkr"


def test_declara_procedencia_y_no_escribe_nbbo(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: None)
    monkeypatch.setattr(KNB, "contratos", lambda: {"samsung": "005930"})
    monkeypatch.setattr(sys, "argv", ["korea_naver_bridge.py", "--once"])
    monkeypatch.setattr(KNB, "sondeo", lambda _c: [{
        "itemCode": "005930", "marketStatus": "OPEN", "closePrice": "244,000",
        "accumulatedTradingVolume": "2,853,471",
        "localTradedAt": "2026-08-03T09:06:36.000000+09:00",
    }])
    assert KNB.main() == 0
    src = json.load(open(KNB.SRC_FILE))
    assert src["fuente"] == "naver_polling"
    assert src["nbbo"] is None and "404" in src["nbbo_motivo"]
    assert src["mercado_abierto"] is True
    assert not os.path.exists("data/nbbo_samsung.txt")   # jamas un bid=ask=last (spread 0%)


def test_fila_sin_precio_no_escribe_barra(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: None)
    monkeypatch.setattr(KNB, "contratos", lambda: {"samsung": "005930"})
    monkeypatch.setattr(sys, "argv", ["korea_naver_bridge.py", "--once"])
    monkeypatch.setattr(KNB, "sondeo", lambda _c: [{
        "itemCode": "005930", "marketStatus": "CLOSE", "closePrice": None,
        "accumulatedTradingVolume": None, "localTradedAt": None,
    }])
    assert KNB.main() == 0
    assert not os.path.exists("data/bars_samsung.txt")


def test_sondeo_roto_sale_con_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: None)
    monkeypatch.setattr(KNB, "contratos", lambda: {"samsung": "005930"})
    monkeypatch.setattr(sys, "argv", ["korea_naver_bridge.py", "--once"])

    def _revienta(_c):
        raise RuntimeError("Naver respondio sin 'datas'")

    monkeypatch.setattr(KNB, "sondeo", _revienta)
    assert KNB.main() == 1                      # fail-loud: rc distinto de 0, sin datos inventados


def test_universo_vacio_levanta(monkeypatch, tmp_path):
    p = tmp_path / "korea_contracts.txt"
    p.write_text("")
    monkeypatch.setattr(KNB, "ROOT", str(tmp_path))
    os.makedirs(tmp_path / "data", exist_ok=True)
    (tmp_path / "data" / "korea_contracts.txt").write_text("\n")
    with pytest.raises(RuntimeError, match="vacio"):
        KNB.contratos()
