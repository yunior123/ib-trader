"""Tests de scripts/backtest_finviz.py — la auditoria de las alertas Finviz.

Lo que se protege: (1) ningun fallo devuelve un numero plausible, (2) el timeout de la
triple barrera es NULL y no victoria, (3) Wilson/n_eff/BH-FDR contra valores de referencia,
(4) las alertas post-cierre se EXCLUYEN con razon, no se etiquetan.
"""
import json
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import backtest_finviz as bf  # noqa: E402


def bars(seq, t0=0):
    """seq = [(o,h,l,c), ...] -> barras 1m consecutivas."""
    return [{"t": t0 + i * 60000, "o": o, "h": h, "l": lo, "c": c, "v": 100}
            for i, (o, h, lo, c) in enumerate(seq)]


# ---------------------------------------------------------------- estadistica
def test_wilson_valores_de_referencia():
    lo, hi = bf.wilson(7, 10)
    assert lo == pytest.approx(0.3968, abs=1e-3)
    assert hi == pytest.approx(0.8922, abs=1e-3)
    lo, hi = bf.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3)
    assert hi == pytest.approx(0.5962, abs=1e-3)


def test_wilson_levanta_en_vez_de_devolver_medio():
    with pytest.raises(bf.DataMissing):
        bf.wilson(0, 0)
    with pytest.raises(bf.DataMissing):
        bf.wilson(5, 3)


def test_n_effective_reproduce_el_valor_de_referencia_de_la_casa():
    # measured-probability: bollinger n=1154, k=30 syms, rho=0.412 -> n_eff 89.2
    assert bf.n_effective(1154, 30, 0.412) == pytest.approx(89.2, abs=0.5)


def test_n_effective_degrada_con_rho_y_topa_en_clusters():
    # sin correlacion, n_eff = n
    assert bf.n_effective(60, 30, 0.0) == 60
    # mas correlacion -> menos muestra
    assert bf.n_effective(100, 10, 0.8) < bf.n_effective(100, 10, 0.1)
    # el tope por clusters (sym, fecha) manda
    assert bf.n_effective(1000, 2, 0.0, n_clusters=95) == 95


def test_n_effective_sin_rho_levanta():
    with pytest.raises(bf.DataMissing):
        bf.n_effective(100, 10, None)


def test_mean_pairwise_corr_devuelve_none_sin_muestra():
    assert bf.mean_pairwise_corr([]) is None
    assert bf.mean_pairwise_corr([{i: 0.1 for i in range(5)}] * 2) is None  # muy cortas


def test_mean_pairwise_corr_series_identicas_da_uno():
    s = {i: math.sin(i) for i in range(60)}
    assert bf.mean_pairwise_corr([s, s]) == pytest.approx(1.0, abs=1e-9)


def test_mean_pairwise_corr_alinea_por_timestamp_no_por_posicion():
    # misma serie, una desplazada 10 minutos: alineada por ts debe dar 1.0.
    # Truncando por longitud (el bug) daria ~0.
    base = {i: math.sin(i) for i in range(80)}
    shifted = {i: math.sin(i) for i in range(10, 80)}
    assert bf.mean_pairwise_corr([base, shifted]) == pytest.approx(1.0, abs=1e-9)


def test_mean_pairwise_corr_sin_solape_suficiente_es_none():
    a = {i: math.sin(i) for i in range(40)}
    b = {i: math.cos(i) for i in range(100, 140)}
    assert bf.mean_pairwise_corr([a, b]) is None


def test_binom_tail_p_referencia():
    # P[X >= 10 | n=10, p=0.5] = 1/1024
    assert bf.binom_tail_p(10, 10, 0.5) == pytest.approx(1 / 1024, rel=1e-6)
    assert bf.binom_tail_p(0, 10, 0.5) == pytest.approx(1.0, rel=1e-9)
    with pytest.raises(bf.DataMissing):
        bf.binom_tail_p(1, 0, 0.5)


def test_bh_fdr_referencia():
    # con q=0.10 sobre 4 p-valores, solo sobreviven los mas pequeños
    assert bf.bh_fdr([0.001, 0.04, 0.3, 0.9], 0.10) == [True, True, False, False]
    assert bf.bh_fdr([], 0.10) == []
    # nada pasa si todos son grandes
    assert bf.bh_fdr([0.5, 0.6, 0.7], 0.10) == [False, False, False]


# ---------------------------------------------------------------- barrera
def test_triple_barrera_timeout_es_none_no_victoria():
    b = bars([(10, 10.05, 9.95, 10)] * 30)
    lab, ambig, t = bf.triple_barrier(b, 0, 10.0, 1, atr=1.0, k_tp=1.0, k_sl=1.0, end_idx=29)
    assert lab is None and not ambig and t is None


def test_triple_barrera_tp_primero():
    b = bars([(10, 10.1, 9.9, 10), (10, 11.5, 9.9, 11.4), (10, 10, 8, 8.5)])
    lab, ambig, t = bf.triple_barrier(b, 0, 10.0, 1, atr=1.0, k_tp=1.0, k_sl=1.0, end_idx=2)
    assert (lab, ambig, t) == (1, False, 1)


def test_triple_barrera_sl_primero_y_ambigua_es_perdida():
    b = bars([(10, 10.1, 9.9, 10), (10, 11.5, 8.5, 10)])  # la barra toca TP y SL
    lab, ambig, _ = bf.triple_barrier(b, 0, 10.0, 1, atr=1.0, k_tp=1.0, k_sl=1.0, end_idx=1)
    assert lab == 0 and ambig is True


def test_triple_barrera_corto_invierte_las_barreras():
    b = bars([(10, 10.1, 9.9, 10), (10, 10.1, 8.5, 8.6)])
    lab, _, _ = bf.triple_barrier(b, 0, 10.0, -1, atr=1.0, k_tp=1.0, k_sl=1.0, end_idx=1)
    assert lab == 1


def test_triple_barrera_sin_atr_levanta():
    b = bars([(10, 10, 10, 10)] * 3)
    with pytest.raises(bf.DataMissing):
        bf.triple_barrier(b, 0, 10.0, 1, atr=None, k_tp=1.0, k_sl=1.0, end_idx=2)
    with pytest.raises(bf.DataMissing):
        bf.triple_barrier(b, 0, 10.0, 0, atr=1.0, k_tp=1.0, k_sl=1.0, end_idx=2)


def test_atr_none_si_faltan_barras():
    b = bars([(10, 10.5, 9.5, 10)] * 20)
    assert bf.atr_from_bars(b, 5) is None
    assert bf.atr_from_bars(b, 15) > 0


# ---------------------------------------------------------------- veredictos
def test_verdicto_data_insuficiente_por_debajo_de_n():
    assert bf.verdict(8, 10, n_eff=10, null_p=0.4, q_pass=True) == "DATA-INSUFICIENTE"


def test_verdicto_keep_exige_bh_fdr_y_lb_sobre_null():
    assert bf.verdict(90, 100, n_eff=100, null_p=0.4, q_pass=True) == "KEEP"
    assert bf.verdict(90, 100, n_eff=100, null_p=0.4, q_pass=False) != "KEEP"
    assert bf.verdict(20, 100, n_eff=100, null_p=0.5, q_pass=True) == "KILL"


# ---------------------------------------------------------------- E/S
def test_load_events_levanta_si_falta_campo(tmp_path):
    p = tmp_path / "ev.jsonl"
    p.write_text(json.dumps({"ts": 1785758984, "screen": "buffett", "ticker": "X"}) + "\n")
    with pytest.raises(bf.DataMissing):
        bf.load_events(str(p))


def test_load_events_lee_y_fecha(tmp_path):
    p = tmp_path / "ev.jsonl"
    p.write_text(json.dumps({"ts": 1785758984, "screen": "buffett", "ticker": "HLNE",
                             "event": "weather_change", "weather": "BUY",
                             "score": 3, "possible": 6}) + "\n\n")
    evs = bf.load_events(str(p))
    assert len(evs) == 1 and evs[0]["date"] == "2026-08-03"


def test_load_events_levanta_si_no_existe(tmp_path):
    with pytest.raises(bf.DataMissing):
        bf.load_events(str(tmp_path / "no-existe.jsonl"))


def test_atomic_write(tmp_path):
    p = tmp_path / "sub" / "x.md"
    bf.atomic_write(str(p), "hola")
    assert p.read_text() == "hola"
    assert not list((tmp_path / "sub").glob("*.tmp.*"))


# ---------------------------------------------------------------- cortes
def test_hour_bucket_marca_post_cierre():
    assert bf.hour_bucket("16:15") == ">=16:00 post-cierre"
    assert bf.hour_bucket("08:09") == "premarket <09:30"
    assert bf.hour_bucket("09:45") == "09:30-10:30 oro"
    assert bf.hour_bucket("12:00") == "11:30-14:00 picadora"


def test_rvol_bucket_sin_dato_no_inventa():
    assert bf.rvol_bucket(None) == "sin RVOL"
    assert bf.rvol_bucket(0.4) == "RVOL <1.0"
    assert bf.rvol_bucket(3.0) == "RVOL >=2.5"


def test_rate_ignora_timeouts():
    items = [{"label": 1}, {"label": 0}, {"label": None}, {"label": 1}]
    assert bf.rate(items) == (2, 3)


def test_label_events_excluye_post_cierre_y_watch(tmp_path, monkeypatch):
    ev = tmp_path / "ev.jsonl"
    base = {"screen": "momentum", "event": "new_match", "score": 7, "possible": 7}
    ev.write_text(
        json.dumps({**base, "ts": 1785787500, "ticker": "AAA", "weather": "BUY"}) + "\n" +
        json.dumps({**base, "ts": 1785770000, "ticker": "BBB", "weather": "WATCH"}) + "\n")
    monkeypatch.setattr(bf, "EVENTS", str(ev))
    monkeypatch.setattr(bf, "CACHE", str(tmp_path / "cache"))
    labeled, excluded = bf.label_events("2026-08-03")
    assert labeled == []
    reasons = sorted(e["reason"] for e in excluded)
    assert any("despues del cierre" in r for r in reasons)
    assert any("WATCH" in r for r in reasons)
