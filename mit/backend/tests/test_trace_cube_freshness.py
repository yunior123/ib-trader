"""Un cubo de otra sesion NO puede borrar el precio vivo del panel TRACE.

El orquestador recorta las velas a la ventana de epochs del cubo: si read_trace_cube sirve el
cubo del viernes, el lunes SPY se queda con candles=0, last_close=None y el panel se anuncia
'measured' pintando la sesion anterior. Aqui se fija que el cubo rancio se rechaza (-> None ->
time_axis flat_current) y que las velas VIVAS sobreviven.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta

import pytest

from backend.app.analytics.options_positioning import (
    current_session_date,
    read_trace_cube,
)

STALE_EPOCHS = [1785000900, 1785002100, 1785004500]  # 2026-07-24, otra sesion


def _cube(session: date, epochs: list[int] | None = None, generated: int | None = None) -> dict:
    epochs = epochs or [
        int(datetime.combine(session, dtime(9, 35)).timestamp()) + m * 60 for m in (0, 20, 60)
    ]
    return {
        "meta": {
            "sym": "SPY", "date": session.isoformat(), "band": 0.12,
            "generated_epoch": generated if generated is not None else epochs[-1],
            "source": "ibkr_tws chain snapshots", "epochs": epochs,
            "labels": ["09:35", "09:55", "10:35"], "spots": [100.5, 101.0, 101.5],
            "greeks_ok_pct": [1.0, 1.0, 1.0], "strikes": [101.0, 100.0],
            "columns": 3, "columns_with_gex": 3,
            "intraday_variation": {"gex": 1.0, "netoi": 0.0},
        },
        "cells": {
            "gex": {"100|%d" % e: 4.0 for e in epochs},
            "netoi": {"100|%d" % e: 200.0 for e in epochs},
        },
    }


def _write(tmp_path, cube: dict, sym: str = "spy"):
    (tmp_path / f"trace_cube_{sym}.json").write_text(json.dumps(cube))
    return tmp_path


# ---- sesion vigente -------------------------------------------------------------


def test_current_session_date_rolls_over_at_premarket() -> None:
    wed = datetime(2026, 8, 5, 10, 0)
    assert current_session_date(wed) == date(2026, 8, 5)
    assert current_session_date(datetime(2026, 8, 5, 4, 0)) == date(2026, 8, 5)
    # lunes antes del premercado y todo el fin de semana siguen colgando del viernes
    assert current_session_date(datetime(2026, 8, 3, 3, 0)) == date(2026, 7, 31)
    assert current_session_date(datetime(2026, 8, 1, 12, 0)) == date(2026, 7, 31)
    assert current_session_date(datetime(2026, 8, 2, 3, 50)) == date(2026, 7, 31)


def test_session_start_is_configurable_and_fails_loud(monkeypatch) -> None:
    monkeypatch.setenv("MIT_SESSION_START_HHMM", "0930")
    assert current_session_date(datetime(2026, 8, 3, 8, 0)) == date(2026, 7, 31)
    assert current_session_date(datetime(2026, 8, 3, 10, 0)) == date(2026, 8, 3)
    monkeypatch.setenv("MIT_SESSION_START_HHMM", "9:30")
    with pytest.raises(ValueError):
        current_session_date(datetime(2026, 8, 3, 10, 0))


# ---- read_trace_cube ------------------------------------------------------------


def test_cube_of_the_current_session_is_served(tmp_path) -> None:
    _write(tmp_path, _cube(current_session_date()))
    cube = read_trace_cube("SPY", base_dir=tmp_path)
    assert cube is not None and cube["meta"]["date"] == current_session_date().isoformat()


def test_cube_of_another_session_is_rejected(tmp_path) -> None:
    _write(tmp_path, _cube(date(2026, 7, 24), epochs=STALE_EPOCHS))
    assert read_trace_cube("SPY", base_dir=tmp_path) is None
    # ayer tampoco vale: el panel debe pintar la sesion de HOY o declararse flat
    _write(tmp_path, _cube(current_session_date() - timedelta(days=1)))
    assert read_trace_cube("SPY", base_dir=tmp_path) is None
    # y un cubo sin fecha en meta no se puede fechar -> fuera
    blind = _cube(current_session_date())
    del blind["meta"]["date"]
    _write(tmp_path, blind)
    assert read_trace_cube("SPY", base_dir=tmp_path) is None


def test_max_age_env_replaces_the_session_rule(tmp_path, monkeypatch) -> None:
    now = int(datetime.now().timestamp())
    monkeypatch.setenv("MIT_TRACE_CUBE_MAX_AGE_MIN", "45")
    _write(tmp_path, _cube(date(2026, 7, 24), epochs=STALE_EPOCHS, generated=now - 600))
    assert read_trace_cube("SPY", base_dir=tmp_path) is not None   # viejo de fecha, fresco de reloj
    _write(tmp_path, _cube(current_session_date(), generated=now - 3 * 3600))
    assert read_trace_cube("SPY", base_dir=tmp_path) is None       # de hoy pero el escritor murio
    stamp = _cube(current_session_date(), generated=now)
    del stamp["meta"]["generated_epoch"]
    _write(tmp_path, stamp)
    assert read_trace_cube("SPY", base_dir=tmp_path) is None       # sin sello no se puede fechar


# ---- el panel completo ----------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_cube_does_not_erase_the_live_price(tmp_path, monkeypatch) -> None:
    from backend.app.config import Settings
    from backend.app.engine.event_bus import EventBus
    from backend.app.engine.orchestrator import MarketIntelligenceEngine
    from backend.app.providers.registry import build_providers

    _write(tmp_path, _cube(date(2026, 7, 24), epochs=STALE_EPOCHS))
    monkeypatch.setenv("MIT_TRACE_CUBE_DIR", str(tmp_path))
    settings = Settings()
    engine = MarketIntelligenceEngine(settings, build_providers(settings), EventBus())
    try:
        stale = await engine.trace_matrix("SPY", metric="gex")
        _write(tmp_path, _cube(current_session_date()))
        fresh = await engine.trace_matrix("SPY", metric="gex")
    finally:
        await engine.close()
    # cubo rancio: se declara flat_current y las velas VIVAS siguen ahi
    assert stale["time_axis"] == "flat_current" and stale["trace_time"] is None
    assert len(stale["candles"]) > 1
    assert stale["price_source"] == "candles"
    assert stale["levels"]["last_close"] is not None
    assert "spot_track" not in stale
    # cubo de la sesion vigente: eje MEDIDO
    assert fresh["time_axis"] == "measured"
    assert len(fresh["trace_time"]["columns"]) == 3
    assert fresh["trace_time"]["date"] == current_session_date().isoformat()
