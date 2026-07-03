#!/usr/bin/env python3
"""tests/test_peer_health.py — el arnés que justifica la feature 29.

El test central es `test_factor_control_kills_spurious_lead`: dos series que son
ambas f(t)+ruido con el MISMO factor y CERO lead real, una muestreada con retraso
(asincronía). La correlación cruzada CRUDA encuentra un pico a lag != 0 —el
resultado espurio de libro de texto— y el control de factor común lo MATA.

Sin red, sin TWS, <60s. Los datos reales solo se leen SOLO-LECTURA y con LIMIT.
"""
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import peer_health as ph  # noqa: E402

BAR = ph.BAR_MS
SH = 200          # barajados suficientes para p<0.05 y rápido en test


def _ts(n, start=1_721_894_400_000):
    return start + np.arange(n, dtype=np.int64) * BAR


# --------------------------------------------------------------- EL test

def test_factor_control_kills_spurious_lead():
    """Factor común + muestreo asíncrono => pico crudo a lag != 0, PERO no sobrevive."""
    rng = np.random.default_rng(7)
    n = 4000
    f = rng.standard_normal(n)                    # el factor común (SMH/QQQ)
    peer = f + 0.30 * rng.standard_normal(n)      # cotiza al día
    tgt = np.empty(n)
    tgt[0] = 0.0
    # cotización RANCIA: el target refleja el factor con retraso (asincronía pura)
    tgt[1:] = 0.30 * f[1:] + 0.70 * f[:-1] + 0.30 * rng.standard_normal(n - 1)
    ts = _ts(n)

    # (a) la correlación cruzada CRUDA sí encuentra un pico a lag != 0
    lags, corrs, _ = ph.xcorr_profile(ts, tgt, peer)
    raw_lag, _ = ph._peak(lags, corrs)
    assert raw_lag != 0, "el montaje debe producir un pico crudo espurio a lag no-cero"

    # (b) tras residualizar sobre el factor común, el pico NO sobrevive
    r = ph.pair_health(ts, tgt, peer, controls=[f], n_shuffle=SH)
    assert r["lead_min"] == raw_lag
    assert r["lead_survives"] == 0
    assert r["note"] is not None


# --------------------------------------------------------------- lead real

def test_real_injected_lead_survives():
    """y[t] = x[t-3] + ruido pequeño: el lead REAL sí sobrevive ambos controles."""
    rng = np.random.default_rng(11)
    n = 4000
    peer = rng.standard_normal(n)
    ctrl = rng.standard_normal(n)                 # control independiente
    tgt = np.empty(n)
    tgt[:3] = rng.standard_normal(3)
    tgt[3:] = peer[:-3] + 0.20 * rng.standard_normal(n - 3)
    ts = _ts(n)

    r = ph.pair_health(ts, tgt, peer, controls=[ctrl], n_shuffle=SH)
    assert r["lead_min"] == 3, r
    assert r["resid_lead_min"] == 3
    assert r["shuffle_p"] < 0.05 and r["resid_shuffle_p"] < 0.05
    assert r["lead_survives"] == 1
    assert r["beta"] is not None and r["r2"] is not None


# --------------------------------------------------------------- null

def test_shuffle_null_high_p_for_independent_series():
    rng = np.random.default_rng(3)
    n = 3000
    a = rng.standard_normal(n)
    b = rng.standard_normal(n)
    ts = _ts(n)
    out = ph.shuffle_null(ts, a, b, n_shuffle=SH, seed=99)
    assert out is not None
    p, _, _ = out
    assert p > 0.05, f"series independientes no deben batir el null (p={p})"

    r = ph.pair_health(ts, a, b, controls=[rng.standard_normal(n)], n_shuffle=SH)
    assert r["lead_survives"] == 0


# --------------------------------------------------------------- join / descarte

def test_inner_join_drop_rate_published():
    ts_a = _ts(10)
    ts_b = _ts(10)[2:]                            # al peer le faltan 2 epochs
    series = {"A": (ts_a, np.arange(10.0)), "B": (ts_b, np.arange(8.0))}
    j = ph.inner_join(series, ["A", "B"])
    assert j is not None
    ts, vals, drop = j
    assert ts.size == 8
    assert drop == pytest.approx(1 - 8 / 10)
    assert vals["A"].size == 8 and vals["B"].size == 8

    assert ph.inner_join(series, ["A", "NOPE"]) is None


def test_lag_pairs_respect_time_not_position():
    """Un hueco de datos no puede convertirse en un lag falso."""
    ts = np.array([0, BAR, 3 * BAR, 4 * BAR], dtype=np.int64)  # falta 2*BAR
    it, ip = ph._lag_pairs(ts, 1)
    assert list(zip(ts[it].tolist(), ts[ip].tolist())) == [(BAR, 0), (4 * BAR, 3 * BAR)]


# --------------------------------------------------------------- fail-loud

def test_insufficient_data_returns_none_never_zero():
    rng = np.random.default_rng(5)
    n = 50                                        # < MIN_N
    a, b = rng.standard_normal(n), rng.standard_normal(n)
    r = ph.pair_health(_ts(n), a, b, controls=[rng.standard_normal(n)], n_shuffle=10)
    for k in ("corr", "se", "tstat", "lead_min", "shuffle_p", "resid_corr", "beta"):
        assert r[k] is None, f"{k} debe ser None con datos insuficientes, no un número"
    assert r["lead_survives"] == 0
    assert "insuficiente" in r["note"]


def test_degenerate_inputs_return_none():
    ts = _ts(1000)
    const = np.zeros(1000)
    rng = np.random.default_rng(1)
    assert ph.hac_corr(const, rng.standard_normal(1000)) is None
    assert ph.hac_corr(np.arange(5.0), np.arange(5.0)) is None
    assert ph.ols_beta(np.arange(10.0), np.zeros(10)) is None
    assert ph.residualize(rng.standard_normal(10), []) is None
    r = ph.pair_health(ts, const, rng.standard_normal(1000), controls=[np.zeros(1000)],
                       n_shuffle=10)
    assert r["lead_survives"] == 0


# --------------------------------------------------------------- HAC

def test_hac_corr_matches_pearson_and_widens_se_under_autocorrelation():
    rng = np.random.default_rng(17)
    n = 4000
    x = rng.standard_normal(n)
    y = 0.5 * x + rng.standard_normal(n)
    h = ph.hac_corr(x, y)
    assert h["corr"] == pytest.approx(float(np.corrcoef(x, y)[0, 1]), abs=1e-9)
    assert h["tstat"] > 5 and 0 < h["n_eff"] <= n * 3

    # con regresor Y residuos autocorrelados el SE HAC debe ser MAYOR que el iid ingenuo
    e = np.zeros(n)
    x2 = np.zeros(n)
    for i in range(1, n):
        e[i] = 0.8 * e[i - 1] + rng.standard_normal()
        x2[i] = 0.8 * x2[i - 1] + rng.standard_normal()
    y2 = 0.2 * x2 + e
    x = x2
    h2 = ph.hac_corr(x, y2)
    iid_se = np.sqrt((1 - h2["corr"] ** 2) / (n - 2))
    assert h2["se"] > iid_se


# --------------------------------------------------------------- datos reales (RO)

def test_load_returns_handles_milliseconds():
    """`ts` está en MILISEGUNDOS: si se tratara como segundos, no habría retornos."""
    if not os.path.exists(ph.DB):
        pytest.skip("trades.db ausente")
    s = ph.load_returns(["NVDA"], limit=3000)
    assert "NVDA" in s
    ts, r = s["NVDA"]
    assert r.size > 500
    assert np.median(np.diff(ts)) == BAR
    assert np.all(np.isfinite(r))
    # 2024+ en milisegundos, no en segundos
    assert ts[0] > 1_500_000_000_000
