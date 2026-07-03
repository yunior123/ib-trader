"""Widget de HUECO: el terminal no puede pintar un mapa rancio como si fuera de ahora.

Medido 2026-08-02 21:35 ET: US futures +0,39% de media mientras Corea caia -8,45% — 8,84 puntos
de brecha. Ese contraste es el unico dato de apertura que existe un domingo por la noche, y por
eso el widget lo declara; pero se etiqueta `base: doctrina` porque no hay n>=30 en el ledger.
"""
from __future__ import annotations

import json

from backend.app.analytics.overnight_futures import read_overnight


def _escribe(tmp_path, **kw):
    d = {"ts": 1000, "et": "2026-08-02 21:35:07", "futuros": [], "corea": {}, "avisos": []}
    d.update(kw)
    (tmp_path / "futures_overnight.json").write_text(json.dumps(d))
    return d


FUT_NQ = {"nombre": "NQ", "pct": 0.66, "last": 28592.25, "cash_proxy": "QQQ",
          "fuente": "yfinance", "lag_s": 600.6}
FUT_ES = {"nombre": "ES", "pct": 0.12, "last": 7553.25, "cash_proxy": "SPY",
          "fuente": "yfinance", "lag_s": 600.6}
COREA = {"kospi": {"pct": -8.65}, "samsung": {"pct": -8.77}}


def test_sin_fichero_lo_declara(tmp_path):
    d = read_overnight(base_dir=tmp_path)
    assert d["disponible"] is False and "no existe" in d["motivo"]


def test_fichero_ilegible_lo_declara(tmp_path):
    (tmp_path / "futures_overnight.json").write_text("{ no soy json")
    d = read_overnight(base_dir=tmp_path)
    assert d["disponible"] is False and "ilegible" in d["motivo"]


def test_mapa_rancio_se_rechaza(tmp_path):
    _escribe(tmp_path, futuros=[FUT_NQ])
    d = read_overnight(base_dir=tmp_path, now=1000 + 3600)   # 1 h despues
    assert d["disponible"] is False and "rancio" in d["motivo"]


def test_mapa_fresco_pasa(tmp_path):
    _escribe(tmp_path, futuros=[FUT_NQ], corea=COREA)
    d = read_overnight(base_dir=tmp_path, now=1060)
    assert d["disponible"] is True and d["edad_s"] == 60.0
    assert [f["nombre"] for f in d["futuros"]] == ["NQ"]


def test_filas_sin_pct_se_caen(tmp_path):
    """Una fila sin % no es un 0%: se va del mapa en vez de dibujarse plana."""
    _escribe(tmp_path, futuros=[FUT_NQ, {"nombre": "CL", "pct": None}])
    d = read_overnight(base_dir=tmp_path, now=1060)
    assert [f["nombre"] for f in d["futuros"]] == ["NQ"]


def test_ninguna_fila_utilizable_lo_declara(tmp_path):
    _escribe(tmp_path, futuros=[{"nombre": "CL", "pct": None}], avisos=["fuente caida"])
    d = read_overnight(base_dir=tmp_path, now=1060)
    assert d["disponible"] is False and d["avisos"] == ["fuente caida"]


def test_divergencia_us_arriba_corea_abajo(tmp_path):
    _escribe(tmp_path, futuros=[FUT_NQ, FUT_ES], corea=COREA)
    dv = read_overnight(base_dir=tmp_path, now=1060)["divergencia"]
    assert dv["hay"] is True
    assert dv["us_pct"] == 0.39 and dv["korea_pct"] == -8.71
    assert dv["brecha_pp"] == 9.1
    assert dv["base"] == "doctrina", "sin n>=30 no se llama probabilidad"


def test_sin_divergencia_cuando_van_al_mismo_lado(tmp_path):
    _escribe(tmp_path, futuros=[FUT_NQ], corea={"kospi": {"pct": 1.2}})
    assert read_overnight(base_dir=tmp_path, now=1060)["divergencia"]["hay"] is False


def test_sin_corea_no_hay_divergencia(tmp_path):
    _escribe(tmp_path, futuros=[FUT_NQ], corea={})
    assert read_overnight(base_dir=tmp_path, now=1060)["divergencia"] is None


def test_solo_cuentan_los_capitanes_con_proxy_de_contado(tmp_path):
    """CL no tiene proxy: no vota en la media US (no describe la apertura de nada nuestro)."""
    _escribe(tmp_path, futuros=[FUT_NQ, {"nombre": "CL", "pct": -4.7, "cash_proxy": None}],
             corea=COREA)
    dv = read_overnight(base_dir=tmp_path, now=1060)["divergencia"]
    assert dv["us_pct"] == 0.66
