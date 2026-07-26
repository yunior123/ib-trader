"""Tests de scripts/direction_view.py — CABLEAR la calibracion (TODOS.md, item 89).

direction_view.compute() calculaba prob = 50 + |score|*40, un plausible inventado
(~/CLAUDE.md #3). Aqui se prueba el reemplazo, patron exacto de scripts/compass.cpp
prob_of()/calib_context ya aplicado en order_engine/prob_profit.py._measured_prob:
  - sin bucket "direction_view|<regime>" medido en data/calibration.json -> prob None,
    prob_source "sin_medir", doctrine_score sigue siendo CONTEXTO (nunca "prob").
  - con bucket trust+n>=CALIB_MIN_N -> prob es el medido, prob_source "medido".
  - calib_context lee null_control.json (veredicto CRUDO) como CONTEXTO, nunca numero.
"""
import importlib.util
import json
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")


def _load():
    path = os.path.join(SCRIPTS, "direction_view.py")
    spec = importlib.util.spec_from_file_location("ibt_direction_view", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def DV(monkeypatch):
    """Stubbea signal_conditioning/candles/narrator: solo flip+walls quedan vivos,
    para que score/dir sean deterministas (sin depender de bars/flujo en vivo)."""
    scm = types.ModuleType("signal_conditioning")
    scm.fleet_bias = lambda: {}
    scm.governing_captain = lambda sym: ("market", None)
    scm.component_bias = lambda sym: 0.0
    scm.captain_flow_bias = lambda: {}
    monkeypatch.setitem(sys.modules, "signal_conditioning", scm)

    cdl = types.ModuleType("candles")
    cdl.read = lambda sym, tf: {"patterns": []}
    monkeypatch.setitem(sys.modules, "candles", cdl)

    nr = types.ModuleType("narrator")
    nr.structural_signal = lambda lv: None
    monkeypatch.setitem(sys.modules, "narrator", nr)

    return _load()


LV_DOWN = {"spot": 100.0, "flip": 100.0, "regime": "POS",
           "em": 2.0, "call_wall": 101.0, "put_wall": 95.0, "pressure": 0}


def test_sin_bucket_prob_es_none_nunca_un_plausible(DV, tmp_path, monkeypatch):
    monkeypatch.setattr(DV, "CALIB_PATH", str(tmp_path / "no_existe.json"))
    r = DV.compute("ZZZFAKE", lv=LV_DOWN)
    assert r["dir"] != "flat"
    assert r["prob"] is None
    assert r["prob_source"] == "sin_medir"
    assert isinstance(r["doctrine_score"], int)
    assert any("SIN MEDIR" in w for w in r["why"])


def test_bucket_con_trust_y_n_suficiente_es_medido(DV, tmp_path, monkeypatch):
    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"direction_view|POS": {"rate": 0.71, "n": 25, "trust": True}}))
    monkeypatch.setattr(DV, "CALIB_PATH", str(cal))
    r = DV.compute("ZZZFAKE", lv=LV_DOWN)
    assert r["prob"] == 71
    assert r["prob_source"] == "medido"


def test_bucket_sin_trust_sigue_sin_medir(DV, tmp_path, monkeypatch):
    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"direction_view|POS": {"rate": 0.9, "n": 3, "trust": False}}))
    monkeypatch.setattr(DV, "CALIB_PATH", str(cal))
    r = DV.compute("ZZZFAKE", lv=LV_DOWN)
    assert r["prob"] is None
    assert r["prob_source"] == "sin_medir"


def test_estado_flat_prob_50_doctrina_no_sin_medir(DV, tmp_path, monkeypatch):
    monkeypatch.setattr(DV, "CALIB_PATH", str(tmp_path / "no_existe.json"))
    lv_flat = {"spot": 100.0, "flip": 100.0, "regime": "POS",
               "em": 2.0, "call_wall": None, "put_wall": None, "pressure": 0}
    r = DV.compute("ZZZFAKE", lv=lv_flat)
    assert r["dir"] == "flat"
    assert r["prob"] == 50
    assert r["prob_source"] == "doctrina"


def test_calib_context_lee_null_control_como_contexto(DV, tmp_path, monkeypatch):
    nc = tmp_path / "null_control.json"
    nc.write_text(json.dumps({"bollinger": {"verdict": "UNPROVEN", "n_eff": 89.2,
                                             "fdr_cells_passed": 0}}))
    monkeypatch.setattr(DV, "NC_PATH", str(nc))
    ctx = DV._calib_context({"bollinger": 0.8}, {"bollinger": 1.15})
    assert ctx == "bollinger:UNPROVEN n_eff=89 fdr_ok=0"


def test_calib_context_none_sin_familia_medida(DV, tmp_path, monkeypatch):
    nc = tmp_path / "null_control.json"
    nc.write_text(json.dumps({"bollinger": {"verdict": "UNPROVEN", "n_eff": 89.2,
                                             "fdr_cells_passed": 0}}))
    monkeypatch.setattr(DV, "NC_PATH", str(nc))
    assert DV._calib_context({"flip": 0.5}, {"flip": 1.5}) is None


def test_calib_context_nunca_es_una_probabilidad(DV, tmp_path, monkeypatch):
    """El veredicto es CONTEXTO: jamas contamina prob/prob_source ni es un numero solo."""
    nc = tmp_path / "null_control.json"
    nc.write_text(json.dumps({"structural": {"verdict": "DATA-INSUFFICIENT", "n_eff": 4.0,
                                              "fdr_cells_passed": 0}}))
    monkeypatch.setattr(DV, "NC_PATH", str(nc))
    monkeypatch.setattr(DV, "CALIB_PATH", str(tmp_path / "no_existe.json"))
    ctx = DV._calib_context({"magnet": 1.0}, {"magnet": 1.1})
    assert ctx is not None and "DATA-INSUFFICIENT" in ctx
    assert not ctx[0].isdigit()
