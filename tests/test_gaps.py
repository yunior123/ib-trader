#!/usr/bin/env python3
"""tests/test_gaps.py — ficha 26 `gap-islands`. Sin red, sin TWS, sin BD viva."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import gaps  # noqa: E402


# --------------------------------------------------------------- utilidades
def flat_days(n, price=100.0, rng=1.0, start=1):
    """n sesiones planas de rango `rng` — ATR14 converge a `rng`."""
    out = []
    for i in range(n):
        out.append({"date": "2026-01-%02d" % (start + i), "o": price, "h": price + rng / 2,
                    "l": price - rng / 2, "c": price})
    return out


# ------------------------------------------------------------------ ATR
def test_atr_none_sin_historia():
    assert gaps.atr14([]) is None
    assert gaps.atr14([(1, 1, 1, 1)] * 10) is None       # <15 barras
    # 20 barras de rango cero: NO es un ATR de 0.0, es un dato roto -> None
    assert gaps.atr14([(1, 1, 1, 1)] * 20) is None


def test_atr_converge_al_rango():
    d = flat_days(40, rng=2.0)
    atr = gaps.atr14([(b["o"], b["h"], b["l"], b["c"]) for b in d])
    assert atr == pytest.approx(2.0, abs=0.01)


# ------------------------------------------- deteccion con el k correcto
def test_hueco_sintetico_se_detecta_con_el_k_correcto_y_no_con_uno_mayor():
    """ATR14 = 1.0; hueco fabricado de 2.0 => 2.0 ATR.
    Debe verse con k_on=1.0 y NO verse con k_on=3.0."""
    d = flat_days(30, price=100.0, rng=1.0)
    d.append({"date": "2026-02-01", "o": 102.0, "h": 102.5, "l": 101.5, "c": 102.0})

    g1 = gaps.detect_overnight_gaps(d, k_on=1.0)
    assert len(g1) == 1
    assert g1[0]["dir"] == 1
    assert g1[0]["size_atr"] == pytest.approx(2.0, abs=0.05)
    assert g1[0]["lo"] == pytest.approx(100.0)
    assert g1[0]["hi"] == pytest.approx(102.0)
    assert g1[0]["far_edge"] == pytest.approx(100.0)     # el cierre previo

    assert gaps.detect_overnight_gaps(d, k_on=3.0) == []   # 2.0 ATR no pasa un k de 3.0


def test_hueco_bajista_direccion_y_bordes():
    d = flat_days(30, price=100.0, rng=1.0)
    d.append({"date": "2026-02-01", "o": 97.0, "h": 97.5, "l": 96.5, "c": 97.0})
    g = gaps.detect_overnight_gaps(d, k_on=1.0)
    assert len(g) == 1 and g[0]["dir"] == -1
    assert (g[0]["lo"], g[0]["hi"]) == (97.0, 100.0)
    assert g[0]["far_edge"] == pytest.approx(100.0)


# ------------------------------------------- el registro se cierra al cruzar
def test_registro_abierto_mientras_no_se_cruza():
    d = flat_days(30, price=100.0, rng=1.0)
    # hueco al alza y luego 5 sesiones que NUNCA vuelven a 100.0
    for i in range(5):
        d.append({"date": "2026-02-%02d" % (i + 1), "o": 102.0, "h": 103.0,
                  "l": 101.0, "c": 102.0})
    live = gaps.open_gap_registry(d, k_on=1.0)
    assert len(live) == 1
    assert live[0]["age_days"] == 4
    assert live[0]["dir"] == 1


def test_registro_se_cierra_cuando_el_precio_lo_cruza():
    d = flat_days(30, price=100.0, rng=1.0)
    d.append({"date": "2026-02-01", "o": 102.0, "h": 103.0, "l": 101.0, "c": 102.0})
    assert len(gaps.open_gap_registry(d, k_on=1.0)) == 1
    # sesion que baja hasta 99.5 -> alcanza el borde lejano (100.0) -> hueco RELLENADO
    d.append({"date": "2026-02-02", "o": 101.5, "h": 102.0, "l": 99.5, "c": 100.5})
    assert gaps.open_gap_registry(d, k_on=1.0) == []


def test_registro_no_se_cierra_por_tocar_solo_el_borde_cercano():
    d = flat_days(30, price=100.0, rng=1.0)
    d.append({"date": "2026-02-01", "o": 102.0, "h": 103.0, "l": 101.0, "c": 102.0})
    # baja a 101.0: entra en la banda pero NO alcanza el cierre previo (100.0)
    d.append({"date": "2026-02-02", "o": 102.0, "h": 102.5, "l": 101.0, "c": 101.5})
    assert len(gaps.open_gap_registry(d, k_on=1.0)) == 1


# ------------------------------------------------------------- earnings_gap
def test_earnings_gap_es_None_nunca_False():
    d = flat_days(30, price=100.0, rng=1.0)
    d.append({"date": "2026-02-01", "o": 102.0, "h": 102.5, "l": 101.5, "c": 102.0})
    g = gaps.detect_overnight_gaps(d, k_on=1.0)[0]
    assert g["earnings_gap"] is None
    assert g["earnings_gap"] is not False        # False seria afirmar lo no medido
    live = gaps.open_gap_registry(d, k_on=1.0)[0]
    assert live["earnings_gap"] is None
    assert live["earnings_gap"] is not False


# ------------------------------------------------------------ p_fill AUSENTE
def _walk(o, hits):
    """Recolecta todas las claves de un objeto JSON anidado."""
    if isinstance(o, dict):
        for k, v in o.items():
            hits.add(k)
            _walk(v, hits)
    elif isinstance(o, list):
        for v in o:
            _walk(v, hits)
    return hits


def test_p_fill_no_existe_como_clave_en_el_json(tmp_path):
    """La AUSENCIA de `p_fill` es parte del contrato: el folklore no se afirma."""
    d = flat_days(30, price=100.0, rng=1.0)
    d.append({"date": "2026-02-01", "o": 102.0, "h": 103.0, "l": 101.0, "c": 102.0})
    atrs = gaps.atr14_series([(b["o"], b["h"], b["l"], b["c"]) for b in d])
    payload = {"SYN": {
        "open_gaps": gaps.open_gap_registry(d, 1.0, atrs),
        "island_cuts": gaps.island_cuts(gaps.detect_overnight_gaps(d, 1.0, atrs)),
        "proximity_atr": None, "nearest_edge": None}}
    p = tmp_path / "gaps.json"
    gaps.atomic_write(str(p), payload)
    keys = _walk(json.loads(p.read_text()), set())
    assert "p_fill" not in keys
    assert not any("fill" in k for k in keys)


def test_p_fill_no_esta_en_el_json_real_si_existe():
    real = os.path.join(ROOT, "data", "gaps.json")
    if not os.path.exists(real):
        pytest.skip("data/gaps.json aun no generado")
    obj = json.loads(open(real).read())
    keys = _walk(obj, set())
    assert "p_fill" not in keys


# --------------------------------------------------------- proximidad e islas
def test_gap_proximity_signo_y_borde():
    og = [{"lo": 100.0, "hi": 104.0, "far_edge": 100.0, "size_atr": 4.0, "dir": 1,
           "age_days": 1, "earnings_gap": None}]
    prox, edge = gaps.gap_proximity(105.0, og, atr=2.0)
    assert edge == 104.0
    assert prox == pytest.approx(0.5)
    prox, edge = gaps.gap_proximity(99.0, og, atr=2.0)
    assert edge == 100.0 and prox == pytest.approx(-0.5)


def test_gap_proximity_devuelve_None_sin_atr_o_sin_huecos():
    assert gaps.gap_proximity(100.0, [], 2.0) == (None, None)
    assert gaps.gap_proximity(100.0, [{"lo": 1, "hi": 2}], None) == (None, None)


def test_island_cuts_solo_por_encima_de_3_atr():
    g = [{"lo": 10, "hi": 11, "size_atr": 2.9, "date": "a"},
         {"lo": 20, "hi": 25, "size_atr": 3.1, "date": "b"}]
    cuts = gaps.island_cuts(g)
    assert len(cuts) == 1 and cuts[0]["date"] == "b"


def test_crosses_island():
    cuts = [{"lo": 100.0, "hi": 106.0}]
    assert gaps.crosses_island(99.0, 107.0, cuts) is True
    assert gaps.crosses_island(102.0, 104.0, cuts) is True
    assert gaps.crosses_island(90.0, 99.0, cuts) is False
    assert gaps.crosses_island(107.0, 110.0, cuts) is False


# --------------------------------------------------------- intradia + escritura
def test_discontinuidad_intradia():
    bars = [(i, 100.0, 100.2, 99.8, 100.0) for i in range(30)]
    bars.append((30, 101.0, 101.2, 100.9, 101.0))     # salto de 1.0 sobre ATR1m ~0.4
    atr = gaps.atr14([(b[1], b[2], b[3], b[4]) for b in bars])
    d = gaps.detect_intraday_discontinuities(bars, k_id=1.0, atr_1m=atr)
    assert d is not None and len(d) == 1 and d[0]["dir"] == 1
    assert gaps.detect_intraday_discontinuities(bars, k_id=50.0, atr_1m=atr) == []


def test_intradia_sin_atr_devuelve_None():
    assert gaps.detect_intraday_discontinuities([(0, 1, 1, 1, 1)], k_id=1.0) is None


def test_atomic_write(tmp_path):
    p = tmp_path / "sub" / "x.json"
    gaps.atomic_write(str(p), {"a": 1})
    assert json.loads(p.read_text()) == {"a": 1}
    assert not [f for f in os.listdir(p.parent) if f.endswith(".tmp")]
