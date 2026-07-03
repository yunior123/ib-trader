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

def test_universo_sale_del_fichero_del_repo():
    mapa = KNB.universo()
    assert mapa["samsung"] == ("stock", "005930")
    assert mapa["skhynix"] == ("stock", "000660")
    assert len(mapa) >= 3


# ---------- IBKR manda / el respaldo no inventa libro ----------

def test_se_aparta_si_el_gateway_vive(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: 4002)
    monkeypatch.setattr(KNB, "universo", lambda: {"samsung": ("stock", "005930")})
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
    monkeypatch.setattr(KNB, "universo", lambda: {"samsung": ("stock", "005930")})
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
    monkeypatch.setattr(KNB, "universo", lambda: {"samsung": ("stock", "005930")})
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
    monkeypatch.setattr(KNB, "universo", lambda: {"samsung": ("stock", "005930")})
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
    (tmp_path / "data" / "korea_endpoints.txt").write_text("# solo comentarios\n")
    with pytest.raises(RuntimeError, match="vacio"):
        KNB.universo()


# ---------- BUG 1: el indice NO es el ETF ----------

def test_num_parsea_valores_de_indice_con_decimales():
    """Los indices traen coma de miles Y punto decimal: '6,257.45'."""
    assert KNB._num("6,257.45") == 6257.45
    assert KNB._num("986.72") == 986.72
    assert KNB._num("-338.00") == -338.0


def test_campo_prefiere_raw_porque_el_volumen_del_indice_no_es_un_numero():
    # '272,959천주' = miles de acciones: sin el Raw el volumen del indice seria None
    row = {"accumulatedTradingVolume": "272,959천주",
           "accumulatedTradingVolumeRaw": "272959000"}
    assert KNB._num(row["accumulatedTradingVolume"]) is None
    assert KNB.campo(row, "accumulatedTradingVolume") == 272959000.0


def test_universo_separa_indice_de_etf():
    """kospi = INDICE; el ETF KODEX 200 vive aparte. El tipo sale del fichero, no del .py."""
    mapa = KNB.universo()
    assert mapa["kospi"] == ("index", "KOSPI")
    assert mapa["kospi200"] == ("index", "KPI200")
    assert mapa["kodex200"] == ("stock", "069500")
    assert "069500" not in [c for n, (_t, c) in mapa.items() if n == "kospi"]


def test_tipo_de_endpoint_desconocido_levanta(tmp_path, monkeypatch):
    monkeypatch.setattr(KNB, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "korea_endpoints.txt").write_text("KOSPI futuro KOSPI\n")
    with pytest.raises(RuntimeError, match="desconocido"):
        KNB.universo()


def test_universo_recoge_los_satelites_de_korea_contracts(tmp_path, monkeypatch):
    """Un satelite nuevo en el puente IBKR no puede quedar mudo aqui."""
    monkeypatch.setattr(KNB, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "korea_endpoints.txt").write_text("KOSPI index KOSPI\n")
    (tmp_path / "data" / "korea_contracts.txt").write_text("HANMI 44631844 042700\n")
    mapa = KNB.universo()
    assert mapa["kospi"] == ("index", "KOSPI") and mapa["hanmi"] == ("stock", "042700")


# ---------- BUG 2: la barra de la subasta de cierre ----------

_ROW_CIERRE = {
    "itemCode": "069500", "marketStatus": "CLOSE",
    "closePrice": "99,105", "compareToPreviousClosePrice": "-9,715",
    "accumulatedTradingVolume": "24,439,342",
    "localTradedAt": "2026-08-03T15:30:00+09:00",
    "stockExchangeType": {"endTime": "1530", "zoneId": "Asia/Seoul"},
}
EP_CIERRE = 1785738600.0                     # 2026-08-03 15:30:00 KST


def test_epoch_cierre_usa_endtime_no_localtradedat():
    """Los INDICES siguen moviendo localTradedAt tras el cierre (medido 18:59 con KRX cerrado
    a las 15:30): usar esa marca fabricaria barras de una sesion que no existe."""
    idx = {"localTradedAt": "2026-08-03T18:59:00+09:00",
           "stockExchangeType": {"endTime": "1530", "zoneId": "Asia/Seoul"}}
    assert KNB.epoch_de(idx) != EP_CIERRE
    assert KNB.epoch_cierre(idx) == EP_CIERRE
    assert KNB.epoch_cierre(_ROW_CIERRE) == EP_CIERRE


def test_epoch_cierre_sin_endtime_es_none():
    assert KNB.epoch_cierre({"localTradedAt": "2026-08-03T15:30:00+09:00"}) is None
    assert KNB.epoch_cierre(_ROW_CIERRE | {"localTradedAt": None}) is None


def test_cierre_oficial_vuelca_la_barra_de_la_subasta(tmp_path, monkeypatch):
    """Sin esto la barra de las 15:30 (precio oficial de la subasta) no se escribe JAMAS:
    localTradedAt se congela y nunca llega un minuto nuevo que la cierre."""
    a = _agg(tmp_path, monkeypatch, "kodex200")
    a.tick(EP_CIERRE - 70, 98625.0, 24_000_000.0)      # ultima barra continua, 15:28
    lineas = a.cierre_oficial(EP_CIERRE, 99105.0, 24_439_342.0)
    assert len(lineas) == 2                            # cierra la 15:28 y escribe la 15:30
    ep, o, h, l, c, v = lineas[-1].split()
    assert float(ep) == EP_CIERRE and float(c) == 99105.0


def test_cierre_oficial_es_idempotente(tmp_path, monkeypatch):
    """Con KRX cerrado el puente sondea cada 60s durante horas: la barra va UNA vez."""
    a = _agg(tmp_path, monkeypatch, "kodex200")
    a.tick(EP_CIERRE - 70, 98625.0, 24_000_000.0)
    lineas = a.cierre_oficial(EP_CIERRE, 99105.0, 24_439_342.0)
    with open("data/bars_kodex200.txt", "w") as f:
        f.writelines(lineas)
    for _ in range(60):
        assert a.cierre_oficial(EP_CIERRE, 99105.0, 24_439_342.0) == []
    # ...y tampoco tras un reinicio del proceso (last_emitted se relee del fichero)
    assert KNB.Agg("kodex200").cierre_oficial(EP_CIERRE, 99105.0, 24_439_342.0) == []
    assert len(open("data/bars_kodex200.txt").read().splitlines()) == 2


def test_prevclose_oficial_sale_del_delta_no_de_la_ultima_barra():
    """108.900 era la ultima barra intradia; el previo REAL es 99.105 + 9.715 = 108.820."""
    close, ep, ses = KNB.prevclose_oficial(_ROW_CIERRE)
    assert close == 108820.0
    assert ses == "2026-07-31"                          # viernes: salta el fin de semana
    assert ep < EP_CIERRE


def test_prevclose_oficial_no_se_fabrica_en_dia_sin_sesion():
    """Sabado: la fuente rellena con el cierre del viernes; no hay 'sesion anterior' que fijar."""
    sabado = _ROW_CIERRE | {"localTradedAt": "2026-08-08T18:59:00+09:00"}
    assert KNB.prevclose_oficial(sabado) is None
    assert KNB.prevclose_oficial(_ROW_CIERRE | {"closePrice": None}) is None


def test_persistir_prevclose_es_monotono_y_no_pisa_otros(tmp_path):
    p = str(tmp_path / "korea_prevclose.json")
    with open(p, "w") as f:
        json.dump({"samsung": {"close": 265000.0, "epoch": 1785479340, "session": "2026-07-31"}}, f)
    assert KNB.persistir_prevclose({"kodex200": (108820.0, 1785479400, "2026-07-31")}, p) == 1
    j = json.load(open(p))
    assert j["kodex200"]["close"] == 108820.0 and j["kodex200"]["oficial"] is True
    assert j["samsung"]["close"] == 265000.0                     # intacto
    # una sesion mas VIEJA no retrocede el fichero, y repetir no reescribe
    assert KNB.persistir_prevclose({"kodex200": (999.0, 1785000000, "2026-07-30")}, p) == 0
    assert KNB.persistir_prevclose({"kodex200": (108820.0, 1785479400, "2026-07-31")}, p) == 0
    assert json.load(open(p))["kodex200"]["close"] == 108820.0


def test_mercado_cerrado_escribe_la_subasta_y_el_prevclose_una_vez(monkeypatch, tmp_path):
    """El ciclo completo con KRX cerrado: barra de subasta + prev_close oficial, sin duplicar."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "PREVCLOSE_FILE", os.path.join(tmp_path, "data", "korea_prevclose.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: None)
    monkeypatch.setattr(KNB, "universo", lambda: {"kodex200": ("stock", "069500")})
    monkeypatch.setattr(KNB, "sondeo", lambda _c: [dict(_ROW_CIERRE)])
    monkeypatch.setattr(sys, "argv", ["korea_naver_bridge.py", "--once"])
    assert KNB.main() == 0
    barras = open("data/bars_kodex200.txt").read().splitlines()
    assert len(barras) == 1 and float(barras[0].split()[4]) == 99105.0
    assert json.load(open(KNB.PREVCLOSE_FILE))["kodex200"]["close"] == 108820.0
    assert json.load(open(KNB.SRC_FILE))["mercado_abierto"] is False
    assert KNB.main() == 0                       # segunda vuelta: nada nuevo
    assert len(open("data/bars_kodex200.txt").read().splitlines()) == 1


def test_cierre_en_el_futuro_no_escribe_barra(monkeypatch, tmp_path):
    """Antes de abrir, la fuente puede fechar hoy un cierre que aun no ha ocurrido."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(KNB, "SRC_FILE", os.path.join(tmp_path, "data", "korea_source.json"))
    monkeypatch.setattr(KNB, "PREVCLOSE_FILE", os.path.join(tmp_path, "data", "korea_prevclose.json"))
    monkeypatch.setattr(KNB, "gateway_vivo", lambda: None)
    monkeypatch.setattr(KNB, "universo", lambda: {"kodex200": ("stock", "069500")})
    import datetime as _dt
    manana = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1)).astimezone()
    monkeypatch.setattr(KNB, "sondeo", lambda _c: [
        dict(_ROW_CIERRE) | {"localTradedAt": manana.isoformat()}])
    monkeypatch.setattr(sys, "argv", ["korea_naver_bridge.py", "--once"])
    assert KNB.main() == 0
    assert not os.path.exists("data/bars_kodex200.txt")
