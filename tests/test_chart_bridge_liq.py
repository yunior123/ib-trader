#!/usr/bin/env python3
"""liq_frame: contexto VPVR/KDE — campos ausentes son null, jamás inventados."""
import importlib.util
import json
import os

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
