"""test_uw_archive.py — archivador de Unusual Whales, SIN RED (monkeypatch de urlopen).

Lo que importa: (1) un endpoint que falla GRITA y NO deja un JSON escrito — un fichero vacio en
data/history/ parece dentro de tres meses "ese dia no hubo datos"; (2) el 403 de UW es AMBIGUO
(rate-limit o token muerto): se encola con backoff y solo tras agotarlo se acusa al token, jamas
se descarta en silencio; (3) el cupo ausente en cabeceras se queda None, nunca 0 ("sin gastar");
(4) 0 filas legitimas SI se archivan, diciendolo en _meta.
"""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import urllib.error  # noqa: E402
import uw_archive as ua  # noqa: E402


class _Resp:
    def __init__(self, payload, headers=None):
        self._b = json.dumps(payload).encode()
        self.headers = headers or {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http(code, headers=None):
    return urllib.error.HTTPError("u", code, "no", headers or {}, None)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(ua.time, "sleep", lambda s: slept.append(s))
    ua.QUOTA["usado"] = None
    ua.QUOTA["limite"] = None
    return slept


def _seq(monkeypatch, items):
    """urlopen devuelve/levanta `items` en orden; agotado -> IndexError (test mal escrito)."""
    it = iter(items)

    def fake(req, timeout=None):
        x = next(it)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(ua.urllib.request, "urlopen", fake)


# ---------- 403 = rate-limit: se ENCOLA, no se descarta ----------

def test_403_transitorio_se_reintenta_tras_esperar_y_acaba_en_200(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_http(403), _http(403), _Resp({"data": [1, 2, 3]})])
    payload, err = ua.fetch("/api/stock/QQQ/greek-exposure", "tok")
    assert err is None and ua.rows_of(payload) == 3
    assert _no_sleep[:2] == list(ua.BACKOFF_403_S[:2])   # espero de verdad, no fingio


def test_429_tambien_se_encola(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_http(429), _Resp({"data": []})])
    payload, err = ua.fetch("/api/market/market-tide", "tok")
    assert err is None and ua.rows_of(payload) == 0
    assert _no_sleep[0] == ua.BACKOFF_403_S[0]


def test_403_persistente_solo_acusa_al_token_tras_agotar_los_backoffs(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_http(403)] * 4)
    payload, err = ua.fetch("/api/stock/QQQ/greeks", "tok")
    assert payload is None and "NO AUTORIZADO" in err
    assert _no_sleep == list(ua.BACKOFF_403_S)


def test_401_es_inmediato_sin_esperas(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_http(401)])
    payload, err = ua.fetch("/api/stock/QQQ/greeks", "tok")
    assert payload is None and "401" in err and _no_sleep == []


def test_error_de_red_se_reintenta_y_al_final_se_reporta(monkeypatch, _no_sleep):
    _seq(monkeypatch, [OSError("timed out")] * ua.RETRIES)
    payload, err = ua.fetch("/api/stock/QQQ/greeks", "tok")
    assert payload is None and "OSError" in err


# ---------- fallo => NO se escribe fichero ----------

def test_endpoint_que_falla_no_escribe_json(tmp_path, monkeypatch, _no_sleep):
    _seq(monkeypatch, [_http(500)] * ua.RETRIES)
    st, n, why = ua.archive_one("greek_exposure", "/api/stock/QQQ/greek-exposure", "tok",
                                str(tmp_path), sym="QQQ")
    assert st == "FALLO" and n is None and "500" in why
    assert list(tmp_path.iterdir()) == []   # ni el fichero ni un .tmp huerfano


def test_cero_filas_si_se_archiva_pero_declarado(tmp_path, monkeypatch, _no_sleep):
    _seq(monkeypatch, [_Resp({"data": []})])
    st, n, _ = ua.archive_one("flow_alerts", "/api/stock/QQQ/flow-alerts", "tok",
                              str(tmp_path), sym="QQQ")
    assert st == "ok" and n == 0
    doc = json.loads((tmp_path / "uw_flow_alerts_qqq.json").read_text())
    assert doc["_meta"]["n_filas"] == 0 and doc["_meta"]["fuente"] == "unusual_whales_trial"
    assert doc["payload"] == {"data": []}


def test_idempotente_no_re_descarga_sin_force(tmp_path, monkeypatch, _no_sleep):
    (tmp_path / "uw_max_pain_qqq.json").write_text("{}")
    monkeypatch.setattr(ua.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("no debia tocar la red"))
    st, _, why = ua.archive_one("max_pain", "/api/stock/QQQ/max-pain", "tok",
                                str(tmp_path), sym="QQQ")
    assert st == "saltado" and "ya archivado" in why


def test_write_atomic_no_deja_tmp(tmp_path):
    p = str(tmp_path / "sub" / "x.json")
    ua.write_atomic(p, {"a": 1})
    assert json.loads(open(p).read()) == {"a": 1}
    assert not os.path.exists(p + ".tmp")


# ---------- procedencia y cupo ----------

def test_meta_lleva_endpoint_y_feed_ts_dentro_del_dato(tmp_path, monkeypatch, _no_sleep):
    _seq(monkeypatch, [_Resp({"data": [{"tape_time": "2026-07-27T13:45:00Z"},
                                       {"tape_time": "2026-07-27T13:50:00Z"}]})])
    ua.archive_one("net_prem_ticks", "/api/stock/QQQ/net-prem-ticks", "tok",
                   str(tmp_path), sym="QQQ")
    m = json.loads((tmp_path / "uw_net_prem_ticks_qqq.json").read_text())["_meta"]
    assert m["endpoint"] == "/api/stock/QQQ/net-prem-ticks" and m["sym"] == "QQQ"
    assert m["feed_ts"] == "2026-07-27T13:50:00Z"
    assert "caduca" in m["aviso"]


def test_feed_ts_ausente_es_none_no_se_inventa():
    assert ua.latest_feed_ts({"data": [{"strike": 700, "gamma": 1.0}]}) is None
    assert ua.latest_feed_ts({"data": []}) is None


def test_forma_desconocida_devuelve_menos_uno_no_cero():
    assert ua.rows_of({"foo": "bar"}) == -1
    assert ua.rows_of("texto") == -1
    assert ua.rows_of([1, 2]) == 2


def test_cupo_ausente_se_queda_none(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_Resp({"data": [1]}, headers={})])
    ua.fetch("/api/stock/QQQ/greeks", "tok")
    assert ua.QUOTA["usado"] is None and ua.QUOTA["limite"] is None


def test_cupo_se_lee_de_las_cabeceras_reales(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_Resp({"data": [1]}, headers={"x-uw-daily-req-count": "412",
                                                     "x-uw-token-req-limit": "30000"})])
    ua.fetch("/api/stock/QQQ/greeks", "tok")
    assert ua.QUOTA == {"usado": 412, "limite": 30000}


def test_cupo_tambien_se_lee_del_403(monkeypatch, _no_sleep):
    _seq(monkeypatch, [_http(403, {"x-uw-daily-req-count": "29999"}), _Resp({"data": [1]})])
    ua.fetch("/api/stock/QQQ/greeks", "tok")
    assert ua.QUOTA["usado"] == 29999


def test_fleet_es_la_canonica_y_no_una_lista_clavada():
    syms = ua.fleet()
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        assert syms == [s.upper() for s in f.read().split()]
