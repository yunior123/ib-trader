from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta

import pytest

from backend.app.analytics.options_positioning import (
    MATRIX_BAND,
    compute_trace_matrix,
    current_session_date,
    read_trace_cube,
)
from backend.app.domain import OptionContract
from backend.app.providers.mock import MockProvider


@pytest.mark.asyncio
async def test_trace_gex_shape_banding_and_levels() -> None:
    provider = MockProvider()
    quote = await provider.get_quote("SPY")
    chain = await provider.get_option_chain("SPY")
    matrix = compute_trace_matrix("SPY", quote.last, chain, metric="gex")
    assert matrix["metric"] == "gex"
    assert matrix["strikes"] == sorted(matrix["strikes"], reverse=True)
    assert matrix["by_strike"]
    # Banding: every returned strike is within +/-MATRIX_BAND of spot.
    lo, hi = quote.last * (1 - MATRIX_BAND), quote.last * (1 + MATRIX_BAND)
    assert all(lo <= s <= hi for s in matrix["strikes"])
    # Levels present (from analyze_dealer_positioning).
    for key in ("call_wall", "put_wall", "gamma_flip", "max_pain"):
        assert key in matrix["levels"]


def test_trace_sign_convention_and_metrics() -> None:
    expiry = date.today() + timedelta(days=30)
    call = OptionContract(symbol="X", expiration=expiry, strike=100, option_type="call",
                          open_interest=1000, gamma=0.02, vega=0.1)
    put = call.model_copy(update={"option_type": "put"})
    # GEX: call +, put - (house sign).
    assert compute_trace_matrix("X", 100.0, [call], metric="gex")["by_strike"]["100"] > 0
    assert compute_trace_matrix("X", 100.0, [put], metric="gex")["by_strike"]["100"] < 0
    # Net OI: call +, put -.
    assert compute_trace_matrix("X", 100.0, [call], metric="netoi")["by_strike"]["100"] == 1000
    assert compute_trace_matrix("X", 100.0, [put], metric="netoi")["by_strike"]["100"] == -1000


def test_trace_fail_loud_empty_and_missing_greeks() -> None:
    expiry = date.today() + timedelta(days=30)
    # Empty chain -> empty by_strike (no fabricated 0).
    empty = compute_trace_matrix("X", 100.0, [], metric="gex")
    assert empty["by_strike"] == {} and empty["strikes"] == []
    # GEX omits strikes without measured gamma; Net OI still counts them.
    no_gamma = OptionContract(symbol="X", expiration=expiry, strike=100, option_type="call",
                              open_interest=500, gamma=None)
    assert compute_trace_matrix("X", 100.0, [no_gamma], metric="gex")["by_strike"] == {}
    assert compute_trace_matrix("X", 100.0, [no_gamma], metric="netoi")["by_strike"]["100"] == 500


def test_trace_bad_metric_raises() -> None:
    with pytest.raises(ValueError):
        compute_trace_matrix("X", 100.0, [], metric="bogus")


# ---- measured time axis (scripts/trace_cube.py) ---------------------------------

# cubo de la SESION VIGENTE: read_trace_cube rechaza los de otra sesion (ver
# test_trace_cube_freshness.py), asi que el fixture se fecha en vivo, no en duro.
SESSION = current_session_date()
EPOCHS = [int(datetime.combine(SESSION, dtime(9, 35)).timestamp()) + m * 60 for m in (0, 20, 60)]


def _cube() -> dict:
    return {
        "meta": {
            "sym": "X", "date": SESSION.isoformat(), "band": 0.12,
            "generated_epoch": EPOCHS[-1],
            "source": "ibkr_tws chain snapshots", "epochs": EPOCHS,
            "labels": ["09:35", "09:55", "10:35"], "spots": [100.5, 101.0, 101.5],
            "greeks_ok_pct": [1.0, 0.0, 1.0], "strikes": [101.0, 100.0],
            "columns": 3, "columns_with_gex": 2,
            "intraday_variation": {"gex": 1.0, "netoi": 0.0},
        },
        "cells": {
            # la foto del medio (09:55) NO tiene griegas -> ni una celda de gex: columna VACIA
            "gex": {"100|%d" % EPOCHS[0]: 4.0, "101|%d" % EPOCHS[0]: -2.0,
                    "100|%d" % EPOCHS[2]: 5.0, "101|%d" % EPOCHS[2]: -3.0},
            "netoi": {"100|%d" % e: 200.0 for e in EPOCHS} | {"101|%d" % e: -600.0 for e in EPOCHS},
        },
    }


def _write_cube(tmp_path, cube: dict, sym: str = "x"):
    (tmp_path / f"trace_cube_{sym}.json").write_text(json.dumps(cube))
    return tmp_path


def test_time_axis_flat_without_cube() -> None:
    call = OptionContract(symbol="X", expiration=date.today() + timedelta(days=30), strike=100,
                          option_type="call", open_interest=1000, gamma=0.02)
    matrix = compute_trace_matrix("X", 100.0, [call], metric="gex")
    assert matrix["time_axis"] == "flat_current"
    assert matrix["trace_time"] is None
    assert any("NOT measured" in c for c in matrix["caveats"])


def test_time_axis_measured_with_cube() -> None:
    call = OptionContract(symbol="X", expiration=date.today() + timedelta(days=30), strike=100,
                          option_type="call", open_interest=1000, gamma=0.02)
    matrix = compute_trace_matrix("X", 100.0, [call], metric="gex", cube=_cube())
    tt = matrix["trace_time"]
    assert matrix["time_axis"] == "measured"
    assert [c["epoch"] for c in tt["columns"]] == EPOCHS          # tantas columnas como el fichero
    assert len(tt["columns"]) == _cube()["meta"]["columns"]
    assert [c["has_data"] for c in tt["columns"]] == [True, False, True]   # la vacia se declara
    assert tt["cells"]["100|%d" % EPOCHS[0]] == 4.0
    assert tt["date"] == SESSION.isoformat() and tt["strikes"] == [101.0, 100.0]
    assert any("Time axis MEASURED: 2/3" in c for c in matrix["caveats"])


def test_measured_axis_per_metric() -> None:
    """netoi tiene las 3 columnas; gex solo 2. Cada metrica declara LO SUYO."""
    matrix = compute_trace_matrix("X", 100.0, [], metric="netoi", cube=_cube())
    assert matrix["time_axis"] == "measured"
    assert all(c["has_data"] for c in matrix["trace_time"]["columns"])
    assert matrix["trace_time"]["intraday_variation"] == 0.0
    assert any("T+1" in c for c in matrix["caveats"])


def test_cube_without_the_requested_metric_falls_back_to_flat() -> None:
    cube = _cube()
    cube["cells"]["gex"] = {}
    matrix = compute_trace_matrix("X", 100.0, [], metric="gex", cube=cube)
    assert matrix["time_axis"] == "flat_current" and matrix["trace_time"] is None


def test_read_trace_cube_paths_and_garbage(tmp_path) -> None:
    assert read_trace_cube("X", base_dir=tmp_path) is None            # no existe
    _write_cube(tmp_path, _cube())
    assert read_trace_cube("X", base_dir=tmp_path)["meta"]["sym"] == "X"
    assert read_trace_cube("x", base_dir=tmp_path) is not None        # case-insensitive
    (tmp_path / "trace_cube_y.json").write_text("{not json")
    assert read_trace_cube("Y", base_dir=tmp_path) is None            # ilegible -> flat, declarado
    (tmp_path / "trace_cube_z.json").write_text(json.dumps({"meta": {"epochs": []}, "cells": {}}))
    assert read_trace_cube("Z", base_dir=tmp_path) is None            # sin columnas -> flat


def test_read_trace_cube_env_override(tmp_path, monkeypatch) -> None:
    _write_cube(tmp_path, _cube())
    monkeypatch.setenv("MIT_TRACE_CUBE_DIR", str(tmp_path))
    assert read_trace_cube("X") is not None


@pytest.mark.asyncio
async def test_orchestrator_serves_the_measured_axis(tmp_path, monkeypatch) -> None:
    from backend.app.config import Settings
    from backend.app.engine.event_bus import EventBus
    from backend.app.engine.orchestrator import MarketIntelligenceEngine
    from backend.app.providers.registry import build_providers

    _write_cube(tmp_path, _cube(), sym="spy")
    monkeypatch.setenv("MIT_TRACE_CUBE_DIR", str(tmp_path))
    settings = Settings()
    engine = MarketIntelligenceEngine(settings, build_providers(settings), EventBus())
    try:
        measured = await engine.trace_matrix("SPY", metric="netoi")
        flat = await engine.trace_matrix("QQQ", metric="netoi")
    finally:
        await engine.close()
    assert measured["time_axis"] == "measured"
    assert len(measured["trace_time"]["columns"]) == 3
    # velas del proveedor: fuera de la sesion del cubo -> se filtran y queda el spot MEDIDO
    assert all(EPOCHS[0] - 3600 <= c["time"] <= EPOCHS[-1] + 3600 for c in measured["candles"])
    assert measured["price_source"] in {"candles", "spot_track"}
    assert [p["value"] for p in measured["spot_track"]] == [100.5, 101.0, 101.5]
    assert flat["time_axis"] == "flat_current" and flat["trace_time"] is None
    assert "spot_track" not in flat
