#!/usr/bin/env python3
"""test_volume_profile.py — arnes del POC de VOLUMEN (scripts/volume_profile.cpp).

Python aqui es SOLO arnes (orden Yunior 2026-07-25: "python solo para test, la computacion en
C++"). Todo el calculo vive en ./volume_profile; estos tests le inyectan barras por stdin con
--stdin y verifican el JSON. Cero computo en Python.

LO QUE ESTE FICHERO PROTEGE
  1. El POC de volumen cae donde de verdad se cruzo el papel (no donde el precio ESTUVO mas
     tiempo: una barra de 1m con volumen 10 no pesa como una con volumen 10.000).
  2. El area de valor CONTIENE al POC y cubre al menos la fraccion pedida.
  3. Nada devuelve un numero plausible cuando no sabe: sin muestra, sin rango o sin volumen el
     simbolo sale con `poc_volume: null` + `skip_reason`. JAMAS un POC de 0 (la ley de la casa:
     un cero plausible convierte "no se" en "se, y es cero").
  4. Sin POC de gamma para el simbolo, `confluence` es null — no "APART", que seria afirmar
     que estan lejos cuando lo que pasa es que no hay con que comparar.
  5. El fichero se declara DESCRIPTIVO: los umbrales de confluencia son convencion, no medida,
     y eso viaja DENTRO del JSON para que ningun consumidor futuro lo confunda con probabilidad.
  6. No se publica ninguna probabilidad. Ninguna clave del JSON puede llamarse prob/edge/wr.

Requiere el binario: ./scripts/build_volume_profile.sh
"""
import json
import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "volume_profile")

pytestmark = pytest.mark.skipif(
    not os.path.exists(BIN),
    reason="falta el binario ./volume_profile — corre ./scripts/build_volume_profile.sh")

TS0 = 1721894400000  # 2024-07-25 en ms


def bars(rows, start=TS0):
    """rows = [(high, low, volume, repeticiones)] -> texto `sym ts o h l c v`."""
    out, ts = [], start
    for hi, lo, vol, n in rows:
        mid = (hi + lo) / 2.0
        for _ in range(n):
            out.append(f"TST {ts} {mid} {hi} {lo} {mid} {vol}")
            ts += 60000
    return "\n".join(out) + "\n"


def run(stdin_text, *args, gex=None, expect_rc=0):
    argv = [BIN, "--stdin", "--out", "-", "--min-bars", "10", *args]
    if gex is not None:
        argv += ["--gex", gex]
    p = subprocess.run(argv, input=stdin_text, capture_output=True, text=True, cwd=REPO,
                       timeout=60)
    assert p.returncode == expect_rc, f"rc={p.returncode} stderr={p.stderr}"
    if expect_rc != 0:
        return p.stderr
    return json.loads(p.stdout)


# ---------------------------------------------------------------- el POC
def test_poc_lands_on_the_traded_price():
    """500 barras clavadas en 105 con volumen 1000 contra 110 dispersas con volumen 10."""
    txt = bars([(105.05, 104.95, 1000, 500)]) + bars(
        [(100.05, 99.95, 10, 55), (110.05, 109.95, 10, 55)], start=TS0 + 500 * 60000)
    d = run(txt, "--bins", "200")["TST"]
    assert abs(d["poc_volume"] - 105.0) < 0.10, d["poc_volume"]


def test_poc_follows_volume_not_time():
    """El precio pasa MAS TIEMPO en 101 pero el papel se cruza en 109. Gana 109."""
    txt = bars([(101.05, 100.95, 1, 400), (109.05, 108.95, 5000, 40)])
    d = run(txt, "--bins", "200")["TST"]
    assert abs(d["poc_volume"] - 109.0) < 0.15, d["poc_volume"]


def test_lo_hi_span_the_sample():
    txt = bars([(105.05, 104.95, 1000, 200), (99.5, 98.0, 100, 20), (120.0, 119.0, 100, 20)])
    d = run(txt)["TST"]
    assert d["lo"] == pytest.approx(98.0)
    assert d["hi"] == pytest.approx(120.0)


# ---------------------------------------------------------------- area de valor
def test_value_area_contains_poc_and_covers_fraction():
    txt = bars([(105.05, 104.95, 1000, 300), (103.05, 102.95, 400, 200),
                (107.05, 106.95, 400, 200), (99.05, 98.95, 5, 100)])
    d = run(txt, "--bins", "200", "--va", "0.70")["TST"]
    assert d["val"] <= d["poc_volume"] <= d["vah"], d
    assert d["va_volume_frac"] >= 0.70, d["va_volume_frac"]


def test_narrower_value_area_is_contained_in_wider_one():
    txt = bars([(105.05, 104.95, 1000, 300), (103.05, 102.95, 400, 200),
                (107.05, 106.95, 400, 200), (99.05, 98.95, 50, 100)])
    n = run(txt, "--bins", "200", "--va", "0.50")["TST"]
    w = run(txt, "--bins", "200", "--va", "0.90")["TST"]
    assert w["val"] <= n["val"] and n["vah"] <= w["vah"], (n, w)


def test_poc_appears_in_hvn():
    """Una MESETA plana tambien es un pico: con comparacion estricta a los dos lados el
    propio POC se quedaba fuera de hvn (bug cazado con estos datos)."""
    txt = bars([(105.05, 104.95, 1000, 500), (100.05, 99.95, 10, 55)])
    d = run(txt, "--bins", "200")["TST"]
    assert d["hvn"], "hvn vacio pese a haber un pico evidente"
    assert min(abs(h - d["poc_volume"]) for h in d["hvn"]) <= 3 * d["bucket"]


# ------------------------------------------- no inventar numeros (la ley de la casa)
def test_insufficient_sample_is_null_not_zero():
    txt = bars([(105.05, 104.95, 1000, 5)])
    d = run(txt, "--min-bars", "500")["TST"]
    assert d["poc_volume"] is None
    assert d["vah"] is None and d["val"] is None
    assert "insuficiente" in d["skip_reason"]


def test_flat_price_is_null_not_zero():
    """Rango degenerado: hi == lo. No puede salir un POC, y menos un 0."""
    txt = "\n".join(f"TST {TS0 + i * 60000} 100 100 100 100 500" for i in range(50)) + "\n"
    d = run(txt)["TST"]
    assert d["poc_volume"] is None
    assert "degenerado" in d["skip_reason"]


def test_zero_volume_is_null_not_zero():
    txt = bars([(105.05, 104.95, 0, 50), (106.05, 105.95, 0, 50)])
    d = run(txt)["TST"]
    assert d["poc_volume"] is None
    assert "volumen total 0" in d["skip_reason"]


def test_no_key_ever_holds_a_zero_poc():
    """Barrido: en ningun escenario degradado puede aparecer poc_volume == 0."""
    for txt in [bars([(105.05, 104.95, 1000, 3)]),
                "\n".join(f"TST {TS0 + i * 60000} 7 7 7 7 9" for i in range(40)) + "\n",
                bars([(105.05, 104.95, 0, 40)])]:
        d = run(txt, "--min-bars", "20")["TST"]
        assert d["poc_volume"] != 0, d


# ---------------------------------------------------------------- confluencia
def _gex(tmp_path, poc, spot):
    p = tmp_path / "gex.json"
    p.write_text(json.dumps({"_meta": {"x": 1}, "TST": {"poc": poc, "spot": spot,
                                                        "regime": "NEGATIVE"}}))
    return str(p)


def test_confluence_when_pocs_coincide(tmp_path):
    txt = bars([(105.05, 104.95, 1000, 300)])
    d = run(txt, "--bins", "200", gex=_gex(tmp_path, 105.0, 105.0))["TST"]
    assert d["confluence"] == "CONFLUENCE", d
    assert d["poc_gamma"] == pytest.approx(105.0)


def test_apart_when_pocs_are_far(tmp_path):
    txt = bars([(105.05, 104.95, 1000, 300)])
    d = run(txt, "--bins", "200", gex=_gex(tmp_path, 130.0, 105.0))["TST"]
    assert d["confluence"] == "APART", d
    assert d["dist_pct"] > 20


def test_near_is_between(tmp_path):
    txt = bars([(105.05, 104.95, 1000, 300)])
    d = run(txt, "--bins", "200", gex=_gex(tmp_path, 105.35, 105.0))["TST"]
    assert d["confluence"] == "NEAR", d


def test_missing_gamma_poc_is_null_not_apart(tmp_path):
    """Sin con que comparar, `confluence` es null. Decir APART seria afirmar algo falso."""
    txt = bars([(105.05, 104.95, 1000, 300)])
    d = run(txt, "--bins", "200", gex=str(tmp_path / "no_existe.json"))["TST"]
    assert d["confluence"] is None
    assert d["poc_gamma"] is None
    assert d["dist_pct"] is None


def test_null_gamma_poc_is_not_zero(tmp_path):
    """`"poc": null` en el mapa NO puede convertirse en un POC de gamma de 0."""
    p = tmp_path / "gex.json"
    p.write_text(json.dumps({"TST": {"poc": None, "spot": 105.0}}))
    d = run(bars([(105.05, 104.95, 1000, 300)]), "--bins", "200", gex=str(p))["TST"]
    assert d["poc_gamma"] is None
    assert d["confluence"] is None


# ---------------------------------------------------------------- honestidad del fichero
def test_meta_declares_convention_not_measurement():
    d = run(bars([(105.05, 104.95, 1000, 300)]))
    m = d["_meta"]
    assert m["thresholds_are_convention_not_measured"] is True
    assert m["signal_only"] is True
    assert "no publica probabilidad" in m["no_probability"]
    assert "UNIFORMEMENTE" in m["method"], "la aproximacion intra-barra debe ir declarada"


def test_no_probability_key_anywhere():
    d = run(bars([(105.05, 104.95, 1000, 300)]))
    blob = json.dumps(d).lower()
    for banned in ['"prob"', '"probability"', '"win_rate"', '"wr"', '"edge"', '"p_"']:
        assert banned not in blob, f"el fichero publica {banned}: es DESCRIPTIVO"


def test_sessions_are_counted():
    """Dos dias distintos = 2 sesiones (corte UTC-5h, no parte RTH)."""
    day2 = TS0 + 86400 * 1000
    txt = bars([(105.05, 104.95, 1000, 30)]) + bars([(106.05, 105.95, 1000, 30)], start=day2)
    d = run(txt)["TST"]
    assert d["n_sessions"] == 2, d
    assert d["n_bars"] == 60


def test_deterministic():
    txt = bars([(105.05, 104.95, 1000, 300), (103.05, 102.95, 400, 200)])
    assert run(txt, "--bins", "200") == run(txt, "--bins", "200")


# ---------------------------------------------------------------- CLI
def test_bad_option_fails_loud():
    err = run("", "--sarasa", expect_rc=2)
    assert "desconocida" in err


def test_bad_bins_fails_loud():
    err = run("", "--bins", "2", expect_rc=2)
    assert "bins" in err


def test_bad_va_fails_loud():
    err = run("", "--va", "1.5", expect_rc=2)
    assert "--va" in err
