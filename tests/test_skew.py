#!/usr/bin/env python3
"""test_skew.py — la red que impide que `skew.py` invente una sonrisa.

La ficha #28 embarca con veredicto DATA-INSUFFICIENT. El unico modo de que esta feature haga
daño es que rellene un hueco con un numero plausible: una IV extrapolada fuera de la banda que
compramos, o un `z` calculado sobre 1 sesion como si fueran 60. Estos tests cierran esas dos
puertas.
"""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

skew = pytest.importorskip("skew")


# ---------------------------------------------------------------------------------------
# Interpolacion: dentro de la banda se interpola, FUERA se suprime
# ---------------------------------------------------------------------------------------

def test_interpola_dentro_de_la_banda():
    pts = [(0.10, 0.30), (0.20, 0.26), (0.30, 0.22), (0.50, 0.20)]
    iv, ext = skew.interp_iv_at_delta(pts, 0.25)
    assert ext is False
    assert abs(iv - 0.24) < 1e-9, iv


def test_fuera_de_la_banda_SUPRIME_no_extrapola():
    """El 0.25 delta cae fuera de lo traido -> None. Extrapolar la sonrisa es inventarse el ala
    que no compramos, y sale como un numero creible."""
    pts = [(0.40, 0.20), (0.50, 0.19), (0.60, 0.185)]     # el 0.25 no esta dentro
    iv, ext = skew.interp_iv_at_delta(pts, 0.25)
    assert iv is None, "fuera de banda tiene que suprimir, no extrapolar"
    assert ext is True


def test_muestra_insuficiente_no_devuelve_cero():
    """Prohibido devolver 0/0.0 ante ausencia (CLAUDE.md, los 3 peligros medidos)."""
    for pts in ([], [(0.25, 0.2)]):
        iv, ext = skew.interp_iv_at_delta(pts, 0.25)
        assert iv is None, "con {} puntos el valor debe ser None, salio {}".format(len(pts), iv)
        assert ext is True


def test_ignora_ivs_no_positivas():
    pts = [(0.10, 0.0), (0.20, 0.26), (0.30, 0.22), (0.50, -1.0)]
    iv, ext = skew.interp_iv_at_delta(pts, 0.25)
    assert ext is False and iv is not None


# ---------------------------------------------------------------------------------------
# El RR de una cadena
# ---------------------------------------------------------------------------------------

def _chain(rows, iv_src="polygon_directo"):
    return {"meta": {"iv": iv_src}, "results": rows}


def _row(kind, strike, delta, iv, exp="2026-07-27"):
    return {"details": {"contract_type": kind, "strike_price": strike, "expiration_date": exp},
            "greeks": {"delta": delta}, "implied_volatility": iv}


def test_rr_es_put_menos_call():
    rows = []
    for d, iv in [(0.10, 0.32), (0.20, 0.28), (0.30, 0.24), (0.50, 0.22)]:
        rows.append(_row("put", 100 - d * 100, -d, iv))
    for d, iv in [(0.10, 0.26), (0.20, 0.23), (0.30, 0.21), (0.50, 0.20)]:
        rows.append(_row("call", 100 + d * 100, d, iv))
    out = skew.rr_for(_chain(rows))
    assert out is not None
    assert out["extrapolated"] == 0
    assert out["rr"] > 0, "puts mas caras que calls -> RR positivo"
    assert abs(out["rr"] - (0.26 - 0.22)) < 1e-9, out["rr"]


def test_si_falta_un_ala_el_rr_se_suprime():
    rows = [_row("put", 90, -0.4, 0.30), _row("put", 95, -0.5, 0.28),
            _row("call", 110, 0.4, 0.22), _row("call", 105, 0.5, 0.21)]
    out = skew.rr_for(_chain(rows))
    assert out["rr"] is None, "sin el 0.25 delta en banda no hay RR"
    assert out["extrapolated"] == 1
    assert out["suprimido_por"]


def test_z_y_drr_son_None_sin_historia():
    """z exige 60 sesiones y hay 1. Ese None SE MUESTRA, no se rellena con 0 ni con 0.5."""
    rows = [_row("put", 90, -0.2, 0.28), _row("put", 95, -0.3, 0.26),
            _row("call", 110, 0.2, 0.23), _row("call", 105, 0.3, 0.21)]
    out = skew.rr_for(_chain(rows))
    assert out["z"] is None
    assert out["drr_1d"] is None


def test_iv_src_se_arrastra_siempre():
    """La IV de Polygon jamas se mezcla con modelGreeks de IBKR en una serie. El unico modo de
    impedirlo es que la fuente viaje pegada al dato."""
    rows = [_row("put", 90, -0.2, 0.28), _row("put", 95, -0.3, 0.26),
            _row("call", 110, 0.2, 0.23), _row("call", 105, 0.3, 0.21)]
    out = skew.rr_for(_chain(rows, iv_src="polygon_directo"))
    assert out["iv_src"] == "polygon_directo"


def test_cadena_ausente_devuelve_None():
    assert skew.rr_for(None) is None
    assert skew.rr_for({"results": []}) is None


# ---------------------------------------------------------------------------------------
# El artefacto publicado dice DATA-INSUFFICIENT y no habla
# ---------------------------------------------------------------------------------------

def test_el_json_publicado_es_honesto():
    p = os.path.join(REPO, "data", "skew.json")
    if not os.path.exists(p):
        pytest.skip("data/skew.json aun no generado (corre scripts/skew.py)")
    d = json.load(open(p, encoding="utf-8"))
    assert d["veredicto"] == "DATA-INSUFFICIENT"
    assert d["voz"] == "OFF"
    assert d["factor_en_direction_view"] == "NINGUNO"
    assert d["n_hist_sessions"] < d["min_hist_for_z"]
    for sym, row in d["skew"].items():
        assert row["z"] is None, "{} publica un z sin las 60 sesiones".format(sym)
        if row["extrapolated"]:
            assert row["rr"] is None, "{} extrapolo fuera de banda".format(sym)
