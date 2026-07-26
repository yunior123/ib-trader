#!/usr/bin/env python3
"""tests/test_vw_drops.py — ficha 4 `vw-drops`. Sin red, sin TWS."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import vw_drops as V  # noqa: E402


def bar(ts, h, l, c, v, o=None):
    return (ts, o if o is not None else c, h, l, c, v)


# ------------------------------------------------------------------- raindrop
def test_raindrop_rising_series_valores_exactos():
    bars = [bar(i, 100 + i + 0.5, 100 + i - 0.5, 100 + i, 100.0) for i in range(10)]
    d = V.raindrop(bars)
    assert d is not None
    assert d["lv"] == pytest.approx(102.0)
    assert d["rv"] == pytest.approx(107.0)
    assert d["oc2"] == pytest.approx(104.5)
    assert d["mass"] == pytest.approx(104.5)
    assert d["h"] == pytest.approx(109.5)
    assert d["l"] == pytest.approx(99.5)
    assert d["flip"] == pytest.approx(0.5)
    assert d["flip_state"] == "FULL"
    assert d["color"] == "GREEN"
    assert d["balloon"] is False


def test_raindrop_falling_series_es_RED_y_flip_negativo():
    bars = [bar(i, 110 - i + 0.5, 110 - i - 0.5, 110 - i, 100.0) for i in range(10)]
    d = V.raindrop(bars)
    assert d["color"] == "RED"
    assert d["flip"] < 0
    assert d["flip_state"] == "FULL"


def test_raindrop_none_por_pocas_subbarras():
    assert V.raindrop([bar(0, 1, 1, 1, 100)] * 3) is None    # half<2


def test_raindrop_none_sin_volumen():
    bars = [bar(i, 101, 99, 100, 0.0) for i in range(10)]
    assert V.raindrop(bars) is None


def test_raindrop_none_rango_nulo():
    bars = [bar(i, 100, 100, 100, 100.0) for i in range(10)]
    assert V.raindrop(bars) is None


def test_balloon_true_cuando_volumen_se_concentra_arriba():
    bars = [bar(0, 101, 100, 100.5, 100.0)]
    bars += [bar(i, 110, 109, 109.5, 100.0) for i in range(1, 10)]
    d = V.raindrop(bars)
    assert d["h"] == pytest.approx(110.0)
    assert d["l"] == pytest.approx(100.0)
    assert d["lv"] > 106.0 and d["rv"] > 106.0
    assert d["balloon"] is True


def test_balloon_false_cuando_bars_cubren_todo_el_rango():
    bars = [bar(i, 110, 100, 105, 100.0) for i in range(10)]
    d = V.raindrop(bars)
    assert d["balloon"] is False   # vol_frac_above = 0.4 < 0.80 por construccion


# --------------------------------------------------------------- migracion
def test_migration_live_none_sin_barras():
    assert V.migration_live([], 100.0, 110.0, 100.0) is None


def test_migration_live_none_rango_nulo():
    assert V.migration_live([bar(0, 105, 104, 104.5, 10)], 100.0, 100.0, 100.0) is None


def test_migration_live_valor_esperado():
    partial = [bar(0, 106, 104, 105.0, 100.0)]
    m = V.migration_live(partial, left_vwap=100.0, hi=110.0, lo=100.0)
    # typical del bar parcial = (106+104+105)/3 = 105.0 -> (105-100)/10 = 0.5
    assert m == pytest.approx(0.5)


# ------------------------------------------------------------------------ %B
def test_rolling_pctb_none_bajo_ventana_o_banda_plana():
    flat = [100.0] * 25
    out = V.rolling_pctb(flat, n=20)
    assert all(x is None for x in out[:19])
    assert out[19] is None       # std=0 -> banda plana, None (no 0.5 fabricado)


def test_rolling_pctb_extremo_alto():
    vals = [100.0] * 19 + [110.0]
    out = V.rolling_pctb(vals, n=20)
    assert out[19] is not None and out[19] > 1.0     # rompe la banda superior


# ------------------------------------------------------------- session_periods
def test_session_periods_trocea_y_descarta_cola_corta():
    bars = [bar(i, 101, 99, 100, 10.0) for i in range(37)]     # 15+15+7 (7>=MIN_SUBBARS)
    chunks = V.session_periods(bars, period_min=15)
    assert len(chunks) == 3
    bars2 = [bar(i, 101, 99, 100, 10.0) for i in range(33)]    # 15+15+3 (3<MIN_SUBBARS)
    chunks2 = V.session_periods(bars2, period_min=15)
    assert len(chunks2) == 2


def test_session_periods_rechaza_period_menor_10():
    with pytest.raises(ValueError):
        V.session_periods([], period_min=5)


def test_raindrop_series_session_produce_periodos_validos():
    bars = [bar(i, 100 + i * 0.01 + 0.5, 100 + i * 0.01 - 0.5, 100 + i * 0.01, 50.0)
            for i in range(45)]
    drops = V.raindrop_series_session(bars, period_min=15)
    assert len(drops) == 3
    assert all(d["oc2"] > 0 for d in drops)


# --------------------------------------------------------------- reversion
def test_label_reversion_hit_y_timeout_y_none_al_final():
    # extremo alto en i=0, cruza <=0.5 en i=2 -> hit True dentro de horizon=8
    pctb = [0.97, 0.8, 0.4, 0.9, 0.95, 0.2, 0.1, 0.3, 0.9]
    assert V._label_reversion(pctb, 0, side=1, horizon=8) is True
    # nunca cruza <=0.5 -> False (band-walk / continuacion)
    pctb2 = [0.97] + [0.9] * 8
    assert V._label_reversion(pctb2, 0, side=1, horizon=8) is False
    # no hay suficientes periodos por delante -> None (timeout, no se cuenta)
    pctb3 = [0.97, 0.9, 0.9]
    assert V._label_reversion(pctb3, 0, side=1, horizon=8) is None


def test_label_reversion_None_si_hay_hueco_en_la_ventana():
    pctb = [0.97, None, 0.4, 0.9, 0.95, 0.2, 0.1, 0.3, 0.9]
    assert V._label_reversion(pctb, 0, side=1, horizon=8) is None


# --------------------------------------------------------------- integracion
def test_validate_devuelve_data_insufficient_sin_historia(tmp_path, monkeypatch):
    import sqlite3
    dbp = str(tmp_path / "empty.db")
    c = sqlite3.connect(dbp)
    c.execute("CREATE TABLE poly_bars(sym TEXT, ts INTEGER, o REAL, h REAL, l REAL, "
              "c REAL, v REAL)")
    c.commit()
    c.close()
    res = V.validate(syms=["QQQ"], db=dbp)
    assert res["verdict"] == "DATA-INSUFFICIENT"


def test_validate_real_db_si_existe():
    if not os.path.exists(V.G.DB):
        pytest.skip("trades.db no disponible")
    res = V.validate(syms=["QQQ"], db=V.G.DB)
    assert res.get("verdict") in ("KEEP", "UNPROVEN", "DEAD", "DATA-INSUFFICIENT")
    if res["verdict"] != "DATA-INSUFFICIENT":
        assert res["n_dias"] > 0
        assert 0.0 <= res["price_rate"] <= 1.0
        assert 0.0 <= res["vw_rate"] <= 1.0
