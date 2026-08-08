#!/usr/bin/env python3
"""liq_frame: contexto VPVR/KDE — campos ausentes son null, jamás inventados."""
import importlib.util
import json
import os
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def cb():
    spec = importlib.util.spec_from_file_location("cb_liq",
                                                  os.path.join(REPO, "scripts", "chart_bridge.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sandbox(cb, tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "REPO", str(tmp_path))
    monkeypatch.setattr(cb, "_VPVR_F", str(tmp_path / "data" / "vpvr.json"))
    (tmp_path / "data").mkdir()


def test_frame_completo(cb, tmp_path, monkeypatch):
    _sandbox(cb, tmp_path, monkeypatch)
    (tmp_path / "data" / "vpvr.json").write_text(json.dumps(
        {"TEST": {"poc_volume": 100.5, "vah": 110.0, "val": 95.0}}))
    (tmp_path / "data" / "levels_auto_TEST.json").write_text(json.dumps(
        {"tfs": {"1m": {"kde": [100.001, 105.0]}, "5m": {"kde": [105.0, 99.0]}}}))
    f, mts = cb.liq_frame("test")
    assert f["type"] == "liq_levels" and f["sym"] == "TEST"
    assert (f["poc_volume"], f["vah"], f["val"]) == (100.5, 110.0, 95.0)
    assert f["kde"] == [99.0, 100.0, 105.0]   # dedupe redondeado a 2dp + orden
    assert mts is not None and len(mts) == 2


def test_sin_ficheros_nulls(cb, tmp_path, monkeypatch):
    _sandbox(cb, tmp_path, monkeypatch)
    f, mts = cb.liq_frame("nada")
    assert (f["poc_volume"], f["vah"], f["val"]) == (None, None, None)
    assert f["kde"] == [] and mts is None


def test_sym_ausente_en_vpvr(cb, tmp_path, monkeypatch):
    _sandbox(cb, tmp_path, monkeypatch)
    (tmp_path / "data" / "vpvr.json").write_text(json.dumps({"OTRO": {"poc_volume": 1}}))
    f, mts = cb.liq_frame("test")
    assert f["poc_volume"] is None and mts is not None   # mtime cuenta: el fichero SÍ existe


def _chain(spot, rows):
    body = [f"# opt_chain TEST | epoch 1 | 2026-08-03 10:00:00 | spot {spot} | exps 20260803",
            "# strike right exp bid ask vol oi iv delta gamma"]
    body.extend(f"{strike:.2f} {right} 20260803 -1 -1 {vol} 1 -1 -1 -1"
                for strike, right, vol in rows)
    return "\n".join(body) + "\n"


def test_liq_map_reads_polygon_archive_and_fresh_live_cache(cb, tmp_path, monkeypatch):
    _sandbox(cb, tmp_path, monkeypatch)
    monkeypatch.setattr(cb, "_UW_TAPE_F", str(tmp_path / "data" / "uw.json"))
    day = cb.datetime.now().strftime("%Y-%m-%d")
    hist = tmp_path / "data" / "history" / day
    hist.mkdir(parents=True)
    (hist / "poly_chain_test_0936.txt").write_text(
        _chain(100, [(99, "C", 10), (99, "P", 5), (101, "C", 20)]))
    live = tmp_path / "data" / "opt_chain_test.txt"
    live.write_text(_chain(101, [(99, "C", 30), (101, "P", 40)]))
    # El mtime del live fija su columna y las columnas van en orden cronologico: si la suite
    # corre antes de las 09:36 el live se colaba DELANTE del archivo y el test fallaba por la
    # hora, no por el codigo. Se clava a las 10:00 de hoy para que el orden sea determinista.
    diez = cb.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0).timestamp()
    os.utime(live, (diez, diez))
    # Keep freshness deterministic even when the suite runs after market hours.
    monkeypatch.setattr(cb.time, "time", lambda: diez + 60)

    frame, fingerprint = cb.liq_map_frame("test")

    assert frame["why"] is None
    assert frame["cols"] == ["0936", cb.datetime.fromtimestamp(live.stat().st_mtime).strftime("%H%M")]
    assert frame["strikes"] == [99.0, 101.0]
    assert frame["heat"] == [[15, 30], [20, 40]]
    assert frame["sources"][0][1] == "poly_chain"
    assert frame["sources"][1][1] == "live_cache"
    assert fingerprint[0]


def test_liq_map_ignores_stale_live_cache(cb, tmp_path, monkeypatch):
    _sandbox(cb, tmp_path, monkeypatch)
    monkeypatch.setattr(cb, "_UW_TAPE_F", str(tmp_path / "data" / "uw.json"))
    live = tmp_path / "data" / "opt_chain_test.txt"
    live.write_text(_chain(100, [(100, "C", 1)]))
    old = time.time() - cb.LIQ_LIVE_CHAIN_MAX_AGE_S - 10
    os.utime(live, (old, old))

    frame, _ = cb.liq_map_frame("test")

    assert frame["cols"] == [] and frame["why"]
    assert "cache vivo fresco" in frame["why"]
