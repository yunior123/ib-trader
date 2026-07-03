#!/usr/bin/env python3
"""test_uw_prem_thresholds.py — umbral p97 propio de premium UW (capitanes solo con n>=30).
Carga el PREFIJO del modulo (antes de _watchdog): importarlo entero conecta a IB real y
arma el os._exit(1) del watchdog dentro de pytest (cazado 2026-07-28)."""
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("ib_insync")


def _load_prefix():
    path = os.path.join(REPO, "scripts", "opt_whale_watch.py")
    src = open(path).read()
    prefix = src[:src.index("\ndef _watchdog")]
    ns = {"__name__": "ibt_oww_uwprem", "__file__": path}
    exec(compile(prefix, path, "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def m():
    return _load_prefix()


def _write_hist(tmp_path, rows):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    with open(d / "uw_premium_flow_hist.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_n_suficiente_da_p97_simetrico_y_exit_mitad(m, tmp_path):
    _write_hist(tmp_path, [{"sym": "QQQ", "signed_premium": float(i * 100_000)}
                           for i in range(1, 41)])
    old, m["REPO"] = m["REPO"], str(tmp_path)
    try:
        th = m["uw_prem_thresholds"]()
    finally:
        m["REPO"] = old
    assert th["QQQ"]["n"] == 40
    assert th["QQQ"]["bull"] == 3_900_000.0          # p97 de 0.1M..4.0M: xs[int(0.97*40)]=xs[38]
    assert th["QQQ"]["bear"] == -th["QQQ"]["bull"]
    assert th["QQQ"]["exit"] == th["QQQ"]["bull"] / 2.0


def test_n_insuficiente_no_arma_umbral(m, tmp_path):
    _write_hist(tmp_path, [{"sym": "SPY", "signed_premium": 5_000_000.0}] * (m["UW_PREM_MIN_N"] - 1))
    old, m["REPO"] = m["REPO"], str(tmp_path)
    try:
        assert m["uw_prem_thresholds"]() == {}
    finally:
        m["REPO"] = old


def test_sin_fichero_devuelve_vacio(m, tmp_path):
    old, m["REPO"] = m["REPO"], str(tmp_path)
    try:
        assert m["uw_prem_thresholds"]() == {}
    finally:
        m["REPO"] = old


def test_filas_corruptas_o_sin_premium_se_ignoran(m, tmp_path):
    _write_hist(tmp_path, [{"sym": "SMH", "signed_premium": -float(i * 200_000)}
                           for i in range(1, 36)])
    with open(tmp_path / "data" / "uw_premium_flow_hist.jsonl", "a") as f:
        f.write("no-es-json\n")
        f.write(json.dumps({"sym": "SMH", "vc": 1}) + "\n")   # sin signed_premium
    old, m["REPO"] = m["REPO"], str(tmp_path)
    try:
        th = m["uw_prem_thresholds"]()
    finally:
        m["REPO"] = old
    assert th["SMH"]["n"] == 35 and th["SMH"]["bull"] > 0    # abs() del lado negativo


def test_capitanes_vienen_de_fleet(m):
    assert set(m["UW_CAPTAINS"]) <= set(m["FLEET"])
    assert set(m["UW_CAPTAINS"]) <= {"SPY", "QQQ", "SMH"}
