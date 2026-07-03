#!/usr/bin/env python3
"""tests/test_kde_levels.py — ficha 27 `kde-levels`. Sin red, sin TWS, sin BD viva."""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import kde_levels as K  # noqa: E402


# --------------------------------------------------------------- utilidades
def bar(i, px, rng=0.10):
    return (i, px, px + rng / 2, px - rng / 2, px, 1000.0)


def cluster_series(centers, per=120, rng=0.10, jitter=0.02, seed=3):
    """Barras que oscilan alrededor de `centers`, un bloque por centro."""
    r = np.random.default_rng(seed)
    out = []
    i = 0
    for cpx in centers:
        for _ in range(per):
            px = cpx + r.normal(0, jitter)
            out.append(bar(i, px, rng))
            i += 1
    return out


# --------------------------------------------------------------- prominencia
def test_peak_prominences_dos_picos():
    y = np.array([0, 1, 3, 1, 0, 1, 4, 1, 0], dtype=float)
    p = K.peak_prominences(y)
    assert [i for i, _ in p] == [2, 6]
    assert all(v > 0 for _, v in p)


def test_peak_prominences_meseta_no_es_pico_interior():
    y = np.array([0, 1, 2, 2, 1, 0], dtype=float)
    idx = [i for i, _ in K.peak_prominences(y)]
    assert len(idx) == 1          # la meseta cuenta UNA vez, no dos


# ------------------------------------------------- dos clusters -> 2 picos
def test_dos_clusters_sinteticos_dan_exactamente_dos_picos():
    """Dos nubes de precio bien separadas (100 y 110) con ATR 0.10:
    el ancho de banda 3*ATR=0.30 no puede fundirlas."""
    bars = cluster_series([100.0, 110.0], per=180, rng=0.10, jitter=0.02)
    lv = K.kde_levels(bars, atr=0.10)
    assert lv is not None
    assert len(lv) == 2, lv
    assert lv[0] == pytest.approx(100.0, abs=0.3)
    assert lv[1] == pytest.approx(110.0, abs=0.3)


def test_tres_clusters_dan_tres_picos():
    bars = cluster_series([100.0, 106.0, 112.0], per=120, rng=0.10, jitter=0.02)
    lv = K.kde_levels(bars, atr=0.10, window=400)
    assert lv is not None and len(lv) == 3, lv


# --------------------------------------------------------------- tope de 5
def test_tope_de_cinco_niveles_se_respeta():
    centers = [100.0 + 4.0 * i for i in range(9)]      # 9 clusters separados
    bars = cluster_series(centers, per=60, rng=0.10, jitter=0.02)
    lv = K.kde_levels(bars, atr=0.10, window=len(bars))
    assert lv is not None
    assert len(lv) <= K.CAP == 5


def test_cap_parametrizable():
    centers = [100.0 + 4.0 * i for i in range(6)]
    bars = cluster_series(centers, per=60, rng=0.10, jitter=0.02)
    lv = K.kde_levels(bars, atr=0.10, window=len(bars), cap=2)
    assert lv is not None and len(lv) == 2


# ------------------------------------------------------- dedup a 0.25*ATR
def test_dedup_dentro_de_025_atr():
    """Con un ATR ENORME (20.0) la dedup es 0.25*20 = 5.0: dos clusters a 100 y
    103 no pueden salir como dos niveles distintos."""
    bars = cluster_series([100.0, 103.0], per=180, rng=0.10, jitter=0.02)
    lv = K.kde_levels(bars, atr=20.0)
    if lv is not None:
        seps = [abs(lv[i + 1] - lv[i]) for i in range(len(lv) - 1)]
        assert all(s >= K.DEDUP_ATR * 20.0 for s in seps), lv
        assert len(lv) == 1, lv


def test_niveles_devueltos_siempre_separados_por_la_dedup():
    bars = cluster_series([100.0, 101.0, 102.0, 103.0], per=90, rng=0.10, jitter=0.02)
    atr = 0.5
    lv = K.kde_levels(bars, atr=atr, window=len(bars))
    if lv and len(lv) > 1:
        for i in range(len(lv) - 1):
            assert lv[i + 1] - lv[i] >= K.DEDUP_ATR * atr


# ---------------------------------------------------------------- islas
def test_ventana_con_hueco_mayor_3atr_no_genera_nivel_a_traves_del_hueco():
    """Cluster viejo en 100, salto de 10 (=10*ATR con ATR 1.0), cluster nuevo en 110.
    Con el corte de isla la ventana se recorta al lado NUEVO: ningun nivel puede
    caer dentro del hueco (100, 110), ni quedarse en el lado viejo."""
    bars = cluster_series([100.0, 110.0], per=180, rng=0.10, jitter=0.02)
    atr = 1.0
    lv = K.kde_levels(bars, atr=atr, island_atr=atr)
    assert lv is not None and len(lv) >= 1
    for px in lv:
        assert not (100.5 < px < 109.5), f"nivel {px} dentro del hueco"
        assert px > 105.0, f"nivel {px} en el lado viejo de la isla"


def test_sin_island_atr_no_se_recorta():
    """Sin ATR diario no se detectan islas propias: se ven los dos clusters."""
    bars = cluster_series([100.0, 110.0], per=180, rng=0.10, jitter=0.02)
    lv = K.kde_levels(bars, atr=0.10, island_atr=None)
    assert lv is not None and len(lv) == 2


def test_island_cuts_from_bars_detecta_el_salto():
    bars = cluster_series([100.0, 110.0], per=60, rng=0.10, jitter=0.02)
    cuts = K.island_cuts_from_bars(bars, atr=1.0)
    assert cuts is not None and len(cuts) == 1
    assert cuts[0]["lo"] == pytest.approx(100.0, abs=0.5)
    assert cuts[0]["hi"] == pytest.approx(110.0, abs=0.5)
    # con un ATR grande el mismo salto NO es isla
    assert K.island_cuts_from_bars(bars, atr=100.0) == []


def test_island_cuts_sin_atr_devuelve_None():
    assert K.island_cuts_from_bars(cluster_series([100.0]), atr=None) is None


def test_truncate_at_island():
    bars = cluster_series([100.0, 110.0], per=60, rng=0.10, jitter=0.02)
    cuts = [{"lo": 100.0, "hi": 110.0}]
    t = K.truncate_at_island(bars, cuts)
    assert len(t) == 60
    assert all(b[4] > 105.0 for b in t)
    assert len(K.truncate_at_island(bars, [])) == 120
    # un corte que las barras nunca ABARCAN entero no recorta nada
    assert len(K.truncate_at_island(bars, [{"lo": 130.0, "hi": 140.0}])) == 120


# ---------------------------------------------------------- fallos = None
def test_kde_devuelve_None_y_nunca_lista_vacia_por_fallo():
    assert K.kde_levels([], atr=1.0) is None
    assert K.kde_levels(cluster_series([100.0], per=10), atr=1.0) is None
    assert K.kde_levels(cluster_series([100.0], per=100), atr=0.0) is None
    # atr=None significa "calculalo": si las barras no tienen rango, ATR es None -> None
    plano = [(i, 100.0, 100.0, 100.0, 100.0, 1.0) for i in range(100)]
    assert K.kde_levels(plano, atr=None) is None
    # precios no positivos -> None, no un log(negativo)
    bad = [(i, -1.0, -0.5, -1.5, -1.0, 1.0) for i in range(100)]
    assert K.kde_levels(bad, atr=1.0) is None


# ------------------------------------------------------------ agregacion
def test_aggregate_ohlc():
    bars = [(i, 10 + i, 20 + i, 5 + i, 12 + i, 100.0) for i in range(10)]
    a = K.aggregate(bars, 5)
    assert len(a) == 2
    assert a[0][1] == 10 and a[0][4] == 16          # open del primero, close del ultimo
    assert a[0][2] == 24 and a[0][3] == 5           # high max, low min
    assert a[0][5] == 500.0
    assert K.aggregate(bars, 1) == bars


# --------------------------------------------------- print-o-nada / null
def test_bounce_stats_None_sin_atr_o_sin_niveles():
    sess = [bar(i, 100.0) for i in range(50)]
    assert K.bounce_stats(sess, [100.0], None) is None
    assert K.bounce_stats(sess, [100.0], 0.0) is None
    assert K.bounce_stats(sess, [], 1.0) is None
    assert K.bounce_stats([], [100.0], 1.0) is None


def ohlc_from_closes(closes, wick=0.05):
    """Barras realistas: el open de cada barra es el close de la anterior."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append((i, o, max(o, c) + wick, min(o, c) - wick, c, 1000.0))
        prev = c
    return out


def test_bounce_stats_cuenta_un_rebote_limpio():
    """ATR 1.0 -> banda [99.85, 100.15]. Baja, mecha dentro de la banda, cierra
    ARRIBA (el lado del que venia) y se va: un TOUCH, un BOUNCE, y la excursion
    favorable de 0.5*ATR se alcanza."""
    sess = ohlc_from_closes([104, 103, 102, 101, 100.4, 101, 102, 103, 104], wick=0.05)
    # la barra 4 baja hasta dentro de la banda antes de cerrar en 100.4
    ts, o, h, l, c, v = sess[4]
    sess[4] = (ts, o, h, 99.90, c, v)
    r = K.bounce_stats(sess, [100.0], atr1m=1.0)
    assert r is not None, r
    assert r["toques"] == 1, r
    assert r["rebotes"] == 1, r
    assert r["exc_n"] == 1 and r["exc_win"] == 1, r     # alcanza +0.5*ATR a favor


def test_bounce_stats_cuenta_una_ruptura_como_no_rebote():
    """Mismo toque, pero la barra siguiente atraviesa la banda de lado a lado:
    BREAK -> no hay BOUNCE, y la barrera se resuelve EN CONTRA."""
    sess = ohlc_from_closes([104, 103, 102, 101, 100.4, 99.4, 98.8, 98.0], wick=0.05)
    ts, o, h, l, c, v = sess[4]
    sess[4] = (ts, o, h, 99.90, c, v)
    r = K.bounce_stats(sess, [100.0], atr1m=1.0)
    assert r is not None
    assert r["toques"] == 1, r
    assert r["rebotes"] == 0, r
    assert r["exc_n"] == 1 and r["exc_win"] == 0, r


def test_histeresis_evita_contar_cuarenta_toques():
    """Precio pegado al nivel 60 barras sin alejarse: NO pueden salir 60 toques."""
    sess = [(i, 100.0, 100.05, 99.95, 100.0, 100.0) for i in range(60)]
    r = K.bounce_stats(sess, [100.0], atr1m=1.0)
    assert r is not None and r["toques"] <= 2


def test_null_aleatorio_da_una_tasa_base_creible():
    """El null de niveles aleatorios corre y devuelve una tasa base creible
    (ni 0 ni 1) sobre una caminata sintetica."""
    rng = np.random.default_rng(11)
    px = 100.0
    closes = []
    for _ in range(390):
        px += rng.normal(0, 0.05)
        closes.append(px)
    sess = ohlc_from_closes(closes, wick=0.02)
    atr1m = 0.10
    levels = 100.0 + rng.uniform(-2, 2, 500) * atr1m
    r = K.bounce_stats(sess, levels, atr1m)
    assert r is not None
    assert r["toques"] > 200, r
    tasa = r["rebotes"] / r["toques"]
    assert 0.3 < tasa < 0.99, tasa
    assert r["exc_n"] > 0
    exc = r["exc_win"] / r["exc_n"]
    assert 0.2 < exc < 0.99, exc


# ------------------------------------------------------------- rivales
def test_prev_session_levels():
    sess = [(i, 100 + i * 0.1, 100 + i * 0.1 + 0.2, 100 + i * 0.1 - 0.2,
             100 + i * 0.1, 10.0) for i in range(40)]
    sess[20] = (20, 102.0, 102.2, 101.8, 102.0, 100000.0)   # POC por volumen
    r = K.prev_session_levels(sess)
    assert r is not None
    assert r["PDH"] == pytest.approx(104.1, abs=0.01)      # 100+39*0.1+0.2
    assert r["PDL"] == pytest.approx(99.8, abs=0.01)        # 100+0*0.1-0.2
    assert r["POC_PROXY"] == pytest.approx(102.0, abs=0.15)


def test_prev_session_levels_None_si_no_hay_sesion():
    assert K.prev_session_levels([]) is None
    assert K.prev_session_levels([bar(0, 100.0)] * 5) is None
