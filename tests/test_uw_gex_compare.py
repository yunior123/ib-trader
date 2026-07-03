"""Referee Unusual Whales por PATA (2026-07-27).

UW manda `null` en la pata que no existe en un strike. `float(None)` tumbaba el simbolo
COMPLETO: TSLA (8 filas) y GOOGL (2) se quedaron sin referee de 30. Se cae la pata, nunca
el simbolo, y jamas se rellena con 0.0 — un cero es una exposicion medida de cero.
"""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    import sys
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibuw_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = [path]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


@pytest.fixture(scope="module")
def uw():
    return _load("uw_gex_compare")


def _fila(k, cg="1.0", pg="-2.0", cd="10.0", pd="-20.0"):
    return {"date": "2026-07-24", "strike": str(k), "call_gex": cg, "put_gex": pg,
            "call_delta": cd, "put_delta": pd}


def _blob(tmp_path, rows):
    p = tmp_path / "uw.json"
    p.write_text(json.dumps({"_meta": {"fuente": "unusual_whales_trial"},
                             "payload": {"data": rows}}))
    return str(p)


def test_pata_null_no_tumba_el_simbolo(uw, tmp_path):
    rows = [_fila(100 + i) for i in range(10)]
    rows.append(_fila(257.5, cg=None, cd=None))     # el caso real de TSLA/GOOGL
    per, meta = uw.uw_legs(_blob(tmp_path, rows))
    assert len(per) == 11
    assert meta["n_patas_nulas"] == 2
    assert per[257.5] == {"put_gex": -2.0, "put_dex": -20.0}      # sin call_*: no se inventa 0
    assert "call_gex" not in per[257.5] and "call_dex" not in per[257.5]


def test_una_fila_toda_null_no_entra(uw, tmp_path):
    per, meta = uw.uw_legs(_blob(tmp_path, [_fila(50, None, None, None, None)]))
    assert per == {} and meta["n_patas_nulas"] == 4


def test_la_n_de_cada_pata_es_la_suya(uw, tmp_path, monkeypatch):
    """Con una pata a null en algunos strikes, publicar una `n` global mentiria."""
    monkeypatch.setattr(uw, "MIN_STRIKES", 3)
    hd = tmp_path / "data" / "history" / "2026-07-26"
    hd.mkdir(parents=True)
    ks = [100.0 + i for i in range(12)]
    res = []
    for i, k in enumerate(ks):
        for typ in ("call", "put"):
            res.append({"details": {"strike_price": k, "contract_type": typ,
                                    "expiration_date": "2026-08-21"},
                        "greeks": {"gamma": 0.01 + i * 0.001, "delta": 0.4},
                        "open_interest": 500 + 10 * i})
    (hd / "chain_full_zz.json").write_text(json.dumps(
        {"meta": {"spot": 105.0, "band": 0.6, "exp_hasta": "2026-08-21"}, "results": res}))
    rows = [_fila(k, cg=(None if k >= 108 else str(1.0 + k)), cd=(None if k >= 108 else "9.0"))
            for k in ks]
    (hd / "uw_greek_exposure_strike_zz.json").write_text(json.dumps(
        {"payload": {"data": rows}}))
    monkeypatch.setattr(uw, "REPO", str(tmp_path))
    r = uw.compare_sym("ZZ", "2026-07-26")
    assert r["estado"] == "ok"
    assert r["put_gex"]["n"] == 12
    assert r["call_gex"]["n"] == 8            # los 4 strikes >=108 no tienen la pata call
    assert r["call_gex"]["spearman"] is not None
