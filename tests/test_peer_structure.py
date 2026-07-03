import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import peer_structure as PS


def _snap(tmp_path, entries, age_s=60):
    d = {"_meta": {"asof": time.time() - age_s}}
    d.update(entries)
    p = tmp_path / "snap.json"
    p.write_text(json.dumps(d))
    return str(p)


def test_side_spot_vs_flip_y_fallback_bias():
    assert PS._side("ZZZ", {"spot": 10, "flip": 9}) == 1.0
    assert PS._side("ZZZ", {"spot": 8, "flip": 9}) == -1.0
    assert PS._side("ZZZ", {"bias": "PUT"}) == -1.0
    assert PS._side("ZZZ", {"bias": "CALL"}) == 1.0
    assert PS._side("ZZZ", {}) is None
    assert PS._side("ZZZ", None) is None


def test_snapshot_rancio_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "SNAP_F", _snap(tmp_path, {"SPY": {"spot": 1, "flip": 0}},
                                            age_s=PS.SNAP_MAX_AGE_S + 10))
    assert PS.compute("QQQ") is None


def test_coef_cuantizado_y_neutral(monkeypatch):
    monkeypatch.setattr(PS, "compute", lambda i: {"score": 0.8, "comp": 0.9, "sib": 0.6,
                                                  "n_comp": 10, "n_sib": 5})
    assert PS.peer_coef("QQQ", +0.5)[0] == 1.25
    assert PS.peer_coef("QQQ", -0.5)[0] == 0.75
    assert PS.peer_coef("QQQ", 0.0) == (1.0, None)
    monkeypatch.setattr(PS, "compute", lambda i: {"score": 0.3, "comp": 0.3, "sib": 0.3,
                                                  "n_comp": 10, "n_sib": 5})
    assert PS.peer_coef("QQQ", +0.5) == (1.0, None)
    monkeypatch.setattr(PS, "compute", lambda i: None)
    assert PS.peer_coef("QQQ", +0.5) == (1.0, None)


def test_apply_peer_escala_solo_fleet_components():
    w = {"fleet": 1.4, "components": 1.3, "flip": 1.5}
    out = PS.apply_peer(w, 0.75)
    assert out["fleet"] == 1.05 and out["components"] == 0.975 and out["flip"] == 1.5
    assert w["fleet"] == 1.4  # no muta el original


def test_coef_impreso_en_why(monkeypatch):
    monkeypatch.setattr(PS, "compute", lambda i: {"score": -0.8, "comp": -0.9, "sib": -0.6,
                                                  "n_comp": 11, "n_sib": 6})
    coef, why = PS.peer_coef("QQQ", -1.0)
    assert coef == 1.25 and "estructura pares" in why and "×1.25" in why
