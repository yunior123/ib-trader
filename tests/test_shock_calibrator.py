"""test_shock_calibrator — series diarias sinteticas con shocks conocidos: valida la matematica
de reversion, el intervalo Wilson y el fail-loud None por debajo del piso.

Necesita venv-mit (py3.12) + PYTHONPATH=mit porque shock_calibrator importa la capa mit/ dentro
de run() — pero analyze/reversion_sample/wilson son puros y no tocan la red. La captura del
proveedor async se hace con un stub (sin red). Correr:
  PYTHONPATH=/Users/yuniorrodriguezosorio/ib-trader/mit \
    ./venv-mit/bin/python -m pytest tests/test_shock_calibrator.py -q
"""
from __future__ import annotations

import asyncio
import math
import sys
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import shock_calibrator as sc  # noqa: E402


def _p(**kw):
    base = dict(shock_pct=10.0, extreme_shock_pct=15.0, shock_zscore=2.5,
               reversion_lookback_days=756, reversal_horizon_days=2, reversion_min_n=20)
    base.update(kw)
    return sc.Params(**base)


# ---------- wilson ----------

def test_wilson_matches_closed_form():
    p, lo, hi = sc.wilson(6, 10)
    assert p == 0.6
    # Wilson 95% para 6/10 ~ [0.3127, 0.8318]
    assert abs(lo - 0.3127) < 1e-3
    assert abs(hi - 0.8318) < 1e-3
    assert lo < p < hi


def test_wilson_all_wins_lower_below_one():
    p, lo, hi = sc.wilson(30, 30)
    assert p == 1.0
    assert lo < 1.0            # el limite INFERIOR no colapsa a 1 (30/30 no es certeza)
    assert hi <= 1.0 + 1e-9


def test_wilson_zero_n_raises():
    try:
        sc.wilson(0, 0)
    except ValueError:
        return
    raise AssertionError("wilson(0,0) debe levantar, no devolver 0.5 plausible")


# ---------- daily returns ----------

def test_daily_returns_alignment():
    r = sc.daily_returns_pct([100.0, 110.0, 99.0])
    assert r[0] is None
    assert abs(r[1] - 10.0) < 1e-9
    assert abs(r[2] - (-10.0)) < 1e-9


# ---------- reversion sample (mecanica conocida) ----------

def test_reversion_all_shocks_revert():
    # cada shock +20% seguido SIEMPRE por una bajada al dia siguiente -> 100% reversion.
    closes = []
    base = 100.0
    for _ in range(30):
        closes.append(base)
        up = base * 1.20      # shock +20%
        closes.append(up)
        base = up * 0.95      # baja despues (reversion)
    wins, n = sc.reversion_sample(closes, threshold=10.0, horizon=2)
    assert n >= 20
    assert wins == n  # todos revierten


def test_reversion_none_revert_when_trend_continues():
    # shocks +20% seguidos SIEMPRE de mas subida -> 0 reversiones (con horizonte 1).
    closes = [100.0]
    for _ in range(40):
        closes.append(closes[-1] * 1.20)  # sube siempre, monotono
    wins, n = sc.reversion_sample(closes, threshold=10.0, horizon=1)
    assert n >= 20
    assert wins == 0  # nunca hay cierre opuesto (todo sube)


def test_reversion_threshold_filters_small_moves():
    # movimientos de 1%: con threshold 10% no entra ningun shock a la muestra.
    closes = [100.0 * (1.01 ** i) for i in range(60)]
    wins, n = sc.reversion_sample(closes, threshold=10.0, horizon=2)
    assert n == 0
    assert wins == 0


# ---------- analyze: severidad + fail-loud None ----------

def _series_with_final_shock(n_history: int, shock_pct: float) -> list[float]:
    # n_history dias planos-ish, luego un shock final de shock_pct.
    closes = [100.0 + 0.01 * i for i in range(n_history)]  # deriva minima
    closes.append(closes[-1] * (1 + shock_pct / 100.0))
    return closes


def test_analyze_insufficient_data_is_none_not_zero():
    row = sc.analyze([100.0, 101.0], _p())
    assert row["severity"] == "INSUFFICIENT_DATA"
    assert row["change_pct"] is None  # jamas 0.0 plausible
    assert row["reversion_prob"] is None


def test_analyze_none_below_floor():
    # solo ~10 shocks resueltos < piso 20 -> prob None aunque haya shocks.
    closes = []
    base = 100.0
    for _ in range(10):
        closes.append(base)
        base = base * 1.20      # shock
        closes.append(base)
        base = base * 0.90      # reversion
    row = sc.analyze(closes, _p(reversion_min_n=20))
    assert row["n"] < 20
    assert row["reversion_prob"] is None
    assert row["wilson_lo"] is None and row["wilson_hi"] is None


def test_analyze_publishes_above_floor_with_wilson():
    closes = []
    base = 100.0
    for _ in range(40):
        closes.append(base)
        base = base * 1.20
        closes.append(base)
        base = base * 0.90
    row = sc.analyze(closes, _p(reversion_min_n=20, reversal_horizon_days=1))
    assert row["n"] >= 20
    assert row["reversion_prob"] is not None
    assert row["wilson_lo"] <= row["reversion_prob"] <= row["wilson_hi"] + 1e-9


def test_analyze_severity_warning_and_critical():
    warn = sc.analyze(_series_with_final_shock(30, 11.0), _p())
    assert warn["severity"] == "WARNING"
    assert warn["direction"] == "UP"
    crit = sc.analyze(_series_with_final_shock(30, -16.0), _p())
    assert crit["severity"] == "CRITICAL"
    assert crit["direction"] == "DOWN"
    assert crit["change_pct"] < 0


def test_analyze_zscore_watch():
    # historia de vol baja (~0.5% diario) + un ultimo dia de +4% => z alto pero abs<shock_pct.
    closes = [100.0]
    for i in range(60):
        closes.append(closes[-1] * (1 + (0.005 if i % 2 == 0 else -0.004)))
    closes.append(closes[-1] * 1.04)
    row = sc.analyze(closes, _p())
    assert row["zscore"] is not None and abs(row["zscore"]) >= 2.5
    assert row["severity"] == "WATCH"  # z-shock aunque abs<10%


# ---------- gather_snapshot con proveedor STUB (sin red) ----------

class _StubMarket:
    def __init__(self, series_by_sym):
        self.series = series_by_sym

    async def get_daily_bars(self, sym, *, limit=756):
        closes = self.series[sym]
        t0 = datetime(2024, 1, 1, tzinfo=UTC)
        return [SimpleNamespace(timestamp=t0 + timedelta(days=i), close=c)
                for i, c in enumerate(closes)]


def test_gather_snapshot_shape_and_metric_label():
    closes = []
    base = 100.0
    for _ in range(40):
        closes.append(base)
        base = base * 1.20
        closes.append(base)
        base = base * 0.90
    providers = SimpleNamespace(market=_StubMarket({"NVDA": closes}))
    snap = asyncio.run(sc.gather_snapshot(providers, ["NVDA"], _p(reversal_horizon_days=1)))
    assert "NVDA" in snap["symbols"]
    assert "OCURRENCIA" in snap["metric"] and "first-touch" in snap["metric"]
    row = snap["symbols"]["NVDA"]
    assert row["n"] >= 20
    assert row["reversion_prob"] is not None
    assert row["asof"] is not None


def test_gather_snapshot_provider_error_is_failloud_none():
    class _Boom:
        async def get_daily_bars(self, sym, *, limit=756):
            raise RuntimeError("provider down")
    providers = SimpleNamespace(market=_Boom())
    snap = asyncio.run(sc.gather_snapshot(providers, ["MU"], _p()))
    row = snap["symbols"]["MU"]
    assert row["severity"] == "ERROR"
    assert row["reversion_prob"] is None  # jamas se fabrica un numero ante error
