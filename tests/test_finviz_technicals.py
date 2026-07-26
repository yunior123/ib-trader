"""test_finviz_technicals.py — widget de technicals Finviz (TODOS.md ~205).

Lo que importa: (1) un valor ausente en el CSV de Finviz (Beta en blanco para
tickers sin historia suficiente) se queda AUSENTE, nunca se convierte en 0.0;
(2) el cache respeta el TTL y no golpea la red de mas; (3) si Finviz falla
cae a yfinance, y si los dos fallan sirve el cache viejo marcado `stale`, y
solo si NO hay nada de nada levanta — jamas fabrica un dato.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import finviz_technicals as ft  # noqa: E402

HEADER = ('"No.","Ticker","Beta","Average True Range","20-Day Simple Moving Average",'
          '"50-Day Simple Moving Average","200-Day Simple Moving Average","52-Week High",'
          '"52-Week Low","Relative Strength Index (14)","Price","Change",'
          '"Change from Open","Gap","Volume"')


def _row(n, sym, beta, price, sma20, sma50, sma200, hi, lo, rsi="51.07",
         chg="-0.92%", cfo="-0.29%", gap="-0.63%", vol="114836805"):
    return (f'{n},"{sym}",{beta},7.25,{sma20},{sma50},{sma200},{hi},{lo},{rsi},'
            f'{price},{chg},{cfo},{gap},{vol}')


# ---------- parsers puros ----------

def test_pct_parsea_porcentaje():
    assert ft._pct("1.73%") == 1.73
    assert ft._pct("-12.56%") == -12.56


def test_pct_guion_es_ausente():
    assert ft._pct("-") is None


def test_pct_vacio_es_ausente_no_cero():
    assert ft._pct("") is None
    assert ft._pct(None) is None


def test_num_vacio_es_ausente():
    assert ft._num("") is None
    assert ft._num("-") is None


def test_level_from_pct_recupera_nivel_absoluto():
    # precio 12.56% POR ENCIMA de un nivel -> nivel = price/1.1256
    assert abs(ft._level_from_pct(112.56, 12.56) - 100.0) < 0.01


def test_level_from_pct_sin_precio_o_sin_pct_es_none():
    assert ft._level_from_pct(None, 1.0) is None
    assert ft._level_from_pct(100.0, None) is None


# ---------- parse_finviz_csv ----------

def test_beta_en_blanco_queda_ausente_no_cero():
    """El caso real (SPCX 2026-07-26): Finviz manda Beta vacio para tickers sin
    historia suficiente. 0.0 seria un beta MENTIROSO (beta cero = sin riesgo
    de mercado); la clave debe faltar."""
    body = HEADER + "\n" + _row(1, "SPCX", "", "115.07", "-18.42%", "-23.66%",
                                 "-23.66%", "-49.00%", "3.81%")
    out = ft.parse_finviz_csv(body)
    assert "beta" not in out["SPCX"]
    assert out["SPCX"]["price"] == 115.07


def test_fila_completa_trae_niveles_absolutos_derivados():
    body = HEADER + "\n" + _row(1, "NVDA", "2.21", "206.84", "1.73%", "-1.12%",
                                 "7.22%", "-12.56%", "26.07%")
    d = ft.parse_finviz_csv(body)["NVDA"]
    assert d["beta"] == 2.21
    assert "sma20" in d and "sma20_pct" in d
    assert abs(d["sma20"] - 206.84 / 1.0173) < 0.01


def test_header_movido_levanta_no_parsea_a_ciegas():
    body = '"No.","Ticker","Price"\n1,"NVDA",206.84'
    with pytest.raises(ft.TechnicalsUnavailable):
        ft.parse_finviz_csv(body)


def test_csv_vacio_levanta():
    with pytest.raises(ft.TechnicalsUnavailable):
        ft.parse_finviz_csv("")


# ---------- get_technicals: orquestacion (sin red, todo monkeypatched) ----------

def test_exito_finviz_escribe_cache_y_marca_procedencia(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "fetch_technicals_finviz",
                         lambda syms: {"NVDA": {"price": 206.84, "rsi14": 51.07}})
    out = ft.get_technicals("NVDA", ttl_s=60, data_dir=str(tmp_path))
    assert out["src"] == "finviz"
    assert out["feed_age_s"] == 0.0
    assert os.path.exists(os.path.join(str(tmp_path), "finviz_tech_nvda.json"))


def test_cache_fresco_no_vuelve_a_pedir_red(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ft, "fetch_technicals_finviz",
                         lambda syms: calls.append(1) or {"NVDA": {"price": 1.0}})
    ft.get_technicals("NVDA", ttl_s=120, data_dir=str(tmp_path))
    ft.get_technicals("NVDA", ttl_s=120, data_dir=str(tmp_path))
    assert len(calls) == 1, "el segundo get_technicals debio servir del cache, no pedir de nuevo"


def test_finviz_falla_cae_a_yfinance(tmp_path, monkeypatch):
    def boom(syms):
        raise ft.TechnicalsUnavailable("simulado: 403")
    monkeypatch.setattr(ft, "fetch_technicals_finviz", boom)
    monkeypatch.setattr(ft, "fetch_technicals_yfinance",
                         lambda sym: {"price": 313.0, "rsi14": 27.99})
    out = ft.get_technicals("TSLA", ttl_s=60, data_dir=str(tmp_path))
    assert out["src"] == "yfinance"


def test_los_dos_fallan_pero_hay_cache_viejo_sirve_stale(tmp_path, monkeypatch):
    path = os.path.join(str(tmp_path), "finviz_tech_qqq.json")
    ft._write_cache(path, {"price": 684.0, "src": "finviz", "feed_ts": time.time() - 999, "sym": "QQQ"})

    def boom_finviz(syms):
        raise ft.TechnicalsUnavailable("simulado finviz")

    def boom_yf(sym):
        raise ft.TechnicalsUnavailable("simulado yfinance")
    monkeypatch.setattr(ft, "fetch_technicals_finviz", boom_finviz)
    monkeypatch.setattr(ft, "fetch_technicals_yfinance", boom_yf)
    out = ft.get_technicals("QQQ", ttl_s=1, data_dir=str(tmp_path))
    assert out["stale"] is True
    assert out["feed_age_s"] > 900


def test_los_dos_fallan_sin_cache_levanta_no_fabrica_nada(tmp_path, monkeypatch):
    def boom_finviz(syms):
        raise ft.TechnicalsUnavailable("simulado finviz")

    def boom_yf(sym):
        raise ft.TechnicalsUnavailable("simulado yfinance")
    monkeypatch.setattr(ft, "fetch_technicals_finviz", boom_finviz)
    monkeypatch.setattr(ft, "fetch_technicals_yfinance", boom_yf)
    with pytest.raises(ft.TechnicalsUnavailable):
        ft.get_technicals("ZZZZ", ttl_s=1, data_dir=str(tmp_path))
