"""Tests de scripts/null_control.py — la puerta que RESTA.

Casos obligatorios de la ficha #2 (docs/FEATURES-MINED-2026-07-25.md):
  5. n_eff < n cuando rho>0 ; n_eff == n cuando rho==0
  6. Bootstrap: dos distribuciones IDENTICAS -> el CI del edge contiene 0
  7. Fuente moneda-al-aire -> edge ~ 0
  9. Nada de 0/0.5 fabricado ante datos insuficientes -> None / DATA-INSUFFICIENT
Mas: BH-FDR real de la skill, el fichero de propuesta NO puede ser el fichero
vivo, y la simetria de las dos ramas.
"""
import importlib.util
import json
import os
import random
import sqlite3
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")


def _load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def NC():
    return _load("null_control")


# ---------------------------------------------------------------- caso 5 -----
def test_n_eff_menor_que_n_con_rho_positiva(NC):
    assert NC.effective_n(300, 10, 0.8) < 300
    assert NC.effective_n(300, 10, 0.8) == pytest.approx(300 / (1 + 9 * 0.8))
    assert NC.effective_n(300, 26, 0.6) < NC.effective_n(300, 5, 0.6), \
        "mas simbolos agrupados => menos informacion independiente"
    assert NC.effective_n(300, 10, 0.9) < NC.effective_n(300, 10, 0.3), \
        "mas correlacion => menos informacion independiente"


def test_n_eff_igual_a_n_con_rho_cero(NC):
    assert NC.effective_n(300, 10, 0.0) == 300
    assert NC.effective_n(300, 1, 0.8) == 300, "un solo simbolo: k-1=0, sin correccion"


def test_n_eff_topado_por_clusters(NC):
    """n_clusters (sym,fecha) es el techo duro: 8 dias de flota no son 1154 obs."""
    assert NC.effective_n(1000, 2, 0.1, n_clusters=40) == 40


def test_n_eff_sin_rho_es_None_no_es_n(NC):
    """Sin rho NO se publica CI. Devolver n seria el bug anticonservador 3-4x."""
    assert NC.effective_n(300, 10, None) is None
    assert NC.effective_n(0, 10, 0.5) is None


def test_n_eff_nunca_menor_que_1(NC):
    assert NC.effective_n(5, 30, 0.95) >= 1.0


# ---------------------------------------------------------------- caso 6 -----
def test_bootstrap_distribuciones_identicas_contiene_cero(NC):
    a = [1, 0] * 300
    b = [1, 0] * 300
    r = NC.bootstrap_edge(a, b, n_boot=400, seed=1)
    assert r is not None
    assert r["edge"] == pytest.approx(0.0, abs=1e-12)
    assert r["ci"][0] <= 0 <= r["ci"][1], "distribuciones iguales: el CI DEBE contener 0"
    assert r["p_boot"] > 0.2


def test_bootstrap_detecta_una_diferencia_grande(NC):
    a = [1] * 300
    b = [0] * 300
    r = NC.bootstrap_edge(a, b, n_boot=400, seed=2)
    assert r["edge"] == pytest.approx(1.0)
    assert r["ci"][0] > 0.5, "una diferencia enorme no puede salir con CI que cruce 0"


def test_bootstrap_ignora_los_timeouts(NC):
    """Los None (timeout) no entran en el denominador."""
    a = [1, 1, 0, 0] * 50 + [None] * 500
    r = NC.bootstrap_edge(a, [1, 1, 0, 0] * 50, n_boot=200, seed=3)
    assert r["n_sig"] == 200, "500 timeouts fuera del denominador"
    assert r["p_sig"] == pytest.approx(0.5)


def test_bootstrap_sin_muestra_devuelve_None(NC):
    assert NC.bootstrap_edge([1, 0], [1, 0], n_boot=50) is None
    assert NC.bootstrap_edge([None] * 50, [1, 0] * 50, n_boot=50) is None, \
        "todo timeout => None, jamas un edge de 0.0 plausible"


# ---------------------------------------------------------------- caso 7 -----
def test_fuente_moneda_al_aire_edge_cero(NC):
    rng = random.Random(99)
    a = [1 if rng.random() < 0.5 else 0 for _ in range(1500)]
    b = [1 if rng.random() < 0.5 else 0 for _ in range(1500)]
    r = NC.bootstrap_edge(a, b, n_boot=600, seed=4)
    assert abs(r["edge"]) < 0.06, "moneda vs moneda: edge ~ 0"
    assert r["ci"][0] < 0 < r["ci"][1]
    assert (r["ci"][1] - r["ci"][0]) < 0.20, "y el CI tiene que ser ESTRECHO con n=1500"


def test_selftest_del_propio_null_control_pasa(NC):
    assert NC.selftest() is True, \
        "si el null no supera sus propias puertas, sus veredictos no valen"


# ---------------------------------------------------------------- caso 9 -----
def test_verdict_data_insufficient_no_se_afloja(NC):
    boot = dict(edge=0.30, ci=[0.20, 0.40], p_boot=0.001, n_sig=80, n_rand=80,
                p_sig=0.8, p_rand=0.5, boot_mean=0.3, boot_sd=0.05)
    v, why = NC.verdict_of(boot, n_eff=4.0, fdr_pass=True, dsr=0.99)
    assert v == "DATA-INSUFFICIENT", \
        "un edge enorme con n_eff=4 sigue siendo 'todavia no sabemos'"
    assert "n_eff" in why


def test_verdict_sin_rho_es_data_insufficient(NC):
    boot = dict(edge=0.3, ci=[0.2, 0.4], p_boot=0.001, n_sig=80, n_rand=80,
                p_sig=0.8, p_rand=0.5, boot_mean=0.3, boot_sd=0.05)
    v, _ = NC.verdict_of(boot, n_eff=None, fdr_pass=True, dsr=0.99)
    assert v == "DATA-INSUFFICIENT"


def test_verdict_dead_cuando_el_CI_es_negativo(NC):
    boot = dict(edge=-0.07, ci=[-0.14, -0.01], p_boot=0.02, n_sig=1154, n_rand=1900,
                p_sig=0.48, p_rand=0.55, boot_mean=-0.07, boot_sd=0.03)
    v, why = NC.verdict_of(boot, n_eff=90.0, fdr_pass=False, dsr=0.1)
    assert v == "DEAD" and "peor que entrada aleatoria" in why


def test_verdict_unproven_si_no_pasa_fdr_o_dsr(NC):
    boot = dict(edge=0.10, ci=[0.02, 0.18], p_boot=0.02, n_sig=400, n_rand=2000,
                p_sig=0.60, p_rand=0.50, boot_mean=0.1, boot_sd=0.04)
    v, why = NC.verdict_of(boot, n_eff=120.0, fdr_pass=False, dsr=0.99)
    assert v == "UNPROVEN" and "BH-FDR" in why
    v2, why2 = NC.verdict_of(boot, n_eff=120.0, fdr_pass=True, dsr=0.40)
    assert v2 == "UNPROVEN" and "DSR" in why2
    v3, _ = NC.verdict_of(boot, n_eff=120.0, fdr_pass=True, dsr=0.99)
    assert v3 == "PROBADO", "con todo pasado si puede ser PROBADO"


def test_verdict_sin_boot_es_data_insufficient(NC):
    v, _ = NC.verdict_of(None, n_eff=1000.0, fdr_pass=True, dsr=0.99)
    assert v == "DATA-INSUFFICIENT"


def test_two_prop_p_extremos(NC):
    assert NC.two_prop_p(50, 100, 50, 100) == pytest.approx(1.0, abs=1e-9)
    assert NC.two_prop_p(90, 100, 10, 100) < 1e-10
    assert NC.two_prop_p(5, 0, 5, 10) is None
    assert NC.two_prop_p(0, 10, 0, 10) is None, "sin varianza no hay test, y no se finge"


def test_two_prop_p_es_mas_conservador_con_n_eff(NC):
    """El punto que mas cambia los veredictos: el mismo WR con n efectiva
    da un p MUCHO mayor."""
    p_raw = NC.two_prop_p(600, 1000, 500, 1000)
    p_eff = NC.two_prop_p(60, 100, 50, 100)
    assert p_eff > p_raw * 5


# ------------------------------------------------------- BH-FDR de la skill --
def test_bh_fdr_de_la_skill_corrige(NC):
    mt = NC.stats()["mt"]
    # 20 p-valores uniformes (nulos) + uno genuinamente pequeno
    pv = [0.04 * (i + 1) for i in range(20)] + [0.0001]
    rej, q = mt.benjamini_hochberg(pv, alpha=0.10)
    assert rej[-1], "el genuino sobrevive"
    assert sum(rej) < len(pv), "y la mayoria de los nulos NO sobrevive"
    assert all(qq >= pp for qq, pp in zip(q, pv)), "las q-values nunca bajan de la p"


def test_bh_fdr_mata_el_falso_positivo_solitario(NC):
    mt = NC.stats()["mt"]
    pv = [0.03] + [0.5] * 60          # 0.03 solo, entre 60 nulos
    rej, q = mt.benjamini_hochberg(pv, alpha=0.10)
    assert not rej[0], "0.03 con 61 pruebas no es un hallazgo"
    assert q[0] > 0.10


# ---------------------------------------------------- ficheros y simetria ----
def test_el_fichero_de_propuesta_no_es_el_vivo(NC):
    assert NC.OUT_PROPOSAL.endswith("signal_enable.PROPUESTO.json")
    assert os.path.basename(NC.OUT_PROPOSAL) != "signal_enable.json", \
        "apagar una alarma en vivo lo decide Yunior, no este script"


def test_write_proposal_no_toca_el_fichero_vivo(NC, tmp_path, monkeypatch):
    live = os.path.join(REPO, "data", "signal_enable.json")
    before = open(live).read() if os.path.exists(live) else None
    prop = str(tmp_path / "prop.json")
    monkeypatch.setattr(NC, "OUT_PROPOSAL", prop)
    res = {"_meta": {"at": "x"},
           "whale": dict(verdict="DEAD", n=133, n_eff=18.7, edge=-0.1,
                         ci=[-0.2, -0.01], why="w"),
           "flow": dict(verdict="UNPROVEN", n=89, n_eff=14.5, edge=0.07,
                        ci=[-0.02, 0.17], why="f")}
    NC._write_proposal(res)
    d = json.load(open(prop))
    assert d["whale"]["propose_enabled"] is False
    assert d["flow"]["propose_enabled"] is True
    assert d["flow"]["propose_voice"] is False, "UNPROVEN = banner, jamas voz"
    assert "WARNING" in d["_meta"]
    after = open(live).read() if os.path.exists(live) else None
    assert after == before, "signal_enable.json NO se toca"


def test_ramas_simetricas_mismo_etiquetador(NC):
    """Las dos ramas tienen que pasar por label_entry -> triple_barrier de la
    ficha #1. Un null etiquetado con otro codigo mide el codigo, no el edge."""
    bars = [(1_000_000 + i * 60, 100.0, 100.0 + (i % 3) * 0.1,
             100.0 - (i % 3) * 0.1, 100.0) for i in range(200)]
    r, why = NC.label_entry(bars, 1_000_000 + 100 * 60, +1, 1.0, 1.0, 30)
    assert why == "ok" and r is not None
    assert set(r) >= {"label", "mfe", "mae", "t_touch", "ambig"}


def test_label_entry_motivos_explicitos(NC):
    assert NC.label_entry([], 1.0, +1)[1] == "no_bars"
    bars = [(2_000_000 + i * 60, 100, 100.2, 99.8, 100) for i in range(20)]
    assert NC.label_entry(bars, 1_000_000, +1)[1] == "no_prior_bar"
    assert NC.label_entry(bars, 2_000_000 + 19 * 60 + 99999, +1)[1] == "entry_stale"
    short = [(3_000_000 + i * 60, 100, 100.2, 99.8, 100) for i in range(5)]
    assert NC.label_entry(short, 3_000_000 + 4 * 60, +1)[1] == "atr_insufficient"


def test_payoff_series_usa_k_tp_y_k_sl(NC):
    obs = [dict(ts=1, label=1), dict(ts=2, label=0), dict(ts=3, label=None)]
    assert NC.payoff_series(obs, 1.5, 0.5) == [1.5, -0.5], "timeout sin pago definido"


def test_naive_verdict_es_mas_permisivo(NC):
    """La segunda puerta: sin la correccion, el mismo dato canta PROBADO."""
    boot = dict(edge=0.10, ci=[0.02, 0.18], p_boot=0.02, n_sig=400, n_rand=2000,
                p_sig=0.6, p_rand=0.5, boot_mean=0.1, boot_sd=0.04)
    assert NC.naive_verdict(boot, 400) == "PROBADO"
    con, _ = NC.verdict_of(boot, n_eff=20.0, fdr_pass=False, dsr=None)
    assert con != "PROBADO", "con n_eff + FDR el mismo dato NO se canta"


def test_bucket_windows_cubren_el_dia(NC):
    tot = sum(hi - lo for lo, hi in NC.BUCKET_WINDOW.values())
    assert tot == 1440, "los buckets de timeofday_calib deben cubrir el dia entero"


def test_et_midnight_es_medianoche_local(NC):
    import time as T
    t = NC.et_midnight("2026-07-24")
    lt = T.localtime(t)
    assert (lt.tm_year, lt.tm_mon, lt.tm_mday) == (2026, 7, 24)
    assert (lt.tm_hour, lt.tm_min) == (0, 0)


def test_session_regime_cache_ilegible_no_revienta(NC, tmp_path, monkeypatch):
    bad = str(tmp_path / "bad.json")
    open(bad, "w").write("{no es json")
    monkeypatch.setattr(NC, "REGIME_CACHE", bad)
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE poly_bars(sym TEXT, ts INTEGER, o REAL, h REAL, "
              "l REAL, c REAL, v REAL)")
    cells, sess = NC.session_regime(c)
    assert cells == {} and sess == {}, "sin barras: vacio, nunca un regimen inventado"
