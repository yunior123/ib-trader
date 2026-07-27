"""pin_risk_score (gex_core) -- TODOS.md "buildeable ya": concentracion(|gamma|) x
proximidad(spot,POC) x 1/T, con 'fortress_pin' si el POC coincide con el call wall.
Protocolo oi-magnets-protocol: doctrina prohibe 0DTE comprado en zona de pin, y hasta hoy
esa zona se juzgaba a ojo.

Lo que se fija aqui: None (no un score fabricado) si falta HHI, POC o T; el piso de T evita
que 1/T se dispare a infinito al cierre; y fortress_pin es una comparacion exacta de nivel,
no una cercania.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core as G           # noqa: E402


def test_sin_hhi_es_none():
    assert G.pin_risk_score({"abs_wall": 700.0}, [{"T": 0.02}], 700.0) is None


def test_sin_poc_es_none():
    assert G.pin_risk_score({"hhi": 0.1}, [{"T": 0.02}], 700.0) is None


def test_sin_ningun_contrato_con_T_es_none():
    gi = {"hhi": 0.1, "abs_wall": 700.0}
    assert G.pin_risk_score(gi, [{"T": None}, {"T": 0}], 700.0) is None


def test_spot_cero_o_nulo_es_none():
    gi = {"hhi": 0.1, "abs_wall": 700.0}
    assert G.pin_risk_score(gi, [{"T": 0.02}], 0) is None
    assert G.pin_risk_score(gi, [{"T": 0.02}], None) is None


def test_fortress_pin_cuando_poc_es_el_call_wall():
    gi = {"hhi": 0.1, "abs_wall": 700.0, "call_wall": 700.0}
    r = G.pin_risk_score(gi, [{"T": 0.02}], 700.0)
    assert r["fortress_pin"] is True
    assert r["proximity_to_poc"] == 1.0


def test_no_fortress_cuando_poc_no_es_call_wall():
    gi = {"hhi": 0.1, "abs_wall": 690.0, "call_wall": 700.0}
    r = G.pin_risk_score(gi, [{"T": 0.02}], 700.0)
    assert r["fortress_pin"] is False


def test_toma_el_T_minimo_de_los_contratos():
    gi = {"hhi": 0.1, "abs_wall": 700.0}
    r = G.pin_risk_score(gi, [{"T": 0.05}, {"T": 0.01}, {"T": None}], 700.0)
    assert r["t_min_years"] == 0.01


def test_piso_de_T_evita_score_infinito_al_cierre():
    gi = {"hhi": 0.1, "abs_wall": 700.0}
    r = G.pin_risk_score(gi, [{"T": 1e-9}], 700.0)
    assert r["t_min_years"] == G.PIN_T_FLOOR
    assert r["score"] < 1e6


def test_score_sube_con_mas_concentracion():
    gi_thin = {"hhi": 0.05, "abs_wall": 700.0}
    gi_thick = {"hhi": 0.5, "abs_wall": 700.0}
    contracts = [{"T": 0.02}]
    r_thin = G.pin_risk_score(gi_thin, contracts, 700.0)
    r_thick = G.pin_risk_score(gi_thick, contracts, 700.0)
    assert r_thick["score"] > r_thin["score"]


def test_score_baja_con_poc_lejos_del_spot():
    gi_near = {"hhi": 0.1, "abs_wall": 700.0}
    gi_far = {"hhi": 0.1, "abs_wall": 650.0}
    contracts = [{"T": 0.02}]
    r_near = G.pin_risk_score(gi_near, contracts, 700.0)
    r_far = G.pin_risk_score(gi_far, contracts, 700.0)
    assert r_near["score"] > r_far["score"]
