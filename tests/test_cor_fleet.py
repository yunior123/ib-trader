"""test_cor_fleet.py — ficha 23 `cor-fleet`.

Sin red, sin TWS, sin BD: todo sobre series sinteticas. Lo que se blinda aqui es
exactamente lo que la casa midio que se rompe en silencio:
  · un rho de 0.0 "plausible" cuando no hay dato,
  · un pct_60d de 0.5 cuando faltan sesiones,
  · un inner-join que descarta la mitad de los epochs y sigue tan campante,
  · un amortiguador ADITIVO colandose donde debe ser MULTIPLICATIVO.
"""
import json
import math
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import cor_fleet as CF  # noqa: E402


# ----------------------------------------------------------------- utilidades
def _series_from_returns(rets, start_epoch=1_700_000_000, price0=100.0):
    """{sym: {epoch: close}} a partir de {sym: array de retornos log}."""
    out = {}
    for sym, r in rets.items():
        px = price0 * np.exp(np.cumsum(np.concatenate([[0.0], r])))
        out[sym] = {start_epoch + 60 * i: float(p) for i, p in enumerate(px)}
    return out


def _perfect(n=90, k=4, seed=1):
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 0.001, n)
    return _series_from_returns({f"S{i}": base.copy() for i in range(k)})


def _independent(n=400, k=5, seed=7):
    rng = np.random.default_rng(seed)
    return _series_from_returns({f"S{i}": rng.normal(0, 0.001, n) for i in range(k)})


# ----------------------------------------------------------------- rho_real
def test_series_perfectamente_correlacionadas_rho_1_y_macro():
    r = CF.mean_pairwise_rho(_perfect(), strict=True)
    assert r["reason"] is None, r["reason"]
    assert r["rho"] == pytest.approx(1.0, abs=1e-9)
    assert r["n_pairs"] == 6                      # C(4,2)
    assert r["join_drop_pct"] == 0.0
    regime, cap, name, _ = CF.classify(r["rho"], None)
    assert regime == "MACRO"
    assert (cap, name) == (1.25, 0.8)


def test_series_independientes_rho_cero_y_dispersion():
    r = CF.mean_pairwise_rho(_independent(), strict=True)
    assert r["reason"] is None
    assert abs(r["rho"]) < 0.15                   # ~0 con n=400
    regime, cap, name, _ = CF.classify(r["rho"], None)
    assert regime == "DISPERSION"
    assert (cap, name) == (0.75, 1.2)


def test_zona_mixta_da_coeficientes_neutros():
    regime, cap, name, _ = CF.classify(0.60, None)
    assert regime == "MIXED"
    assert (cap, name) == (1.0, 1.0)


def test_rho_no_medible_nunca_devuelve_cero_plausible():
    # un solo sym: no hay pares. Prohibido devolver 0.0.
    r = CF.mean_pairwise_rho({"S0": {1: 10.0, 61: 10.1}}, strict=True)
    assert r["rho"] is None
    assert r["reason"]
    regime, cap, name, reason = CF.classify(r["rho"], None)
    assert (regime, cap, name) == (None, None, None)
    assert reason


def test_pocas_observaciones_da_none_con_motivo():
    r = CF.mean_pairwise_rho(_perfect(n=10), strict=True)
    assert r["rho"] is None
    assert "retornos" in r["reason"]


def test_huecos_no_producen_retornos_falsos():
    """Un salto de 20 minutos NO es un retorno de 1 minuto: se descarta."""
    base = _perfect(n=90)
    epochs = sorted(next(iter(base.values())).keys())
    hueco = set(epochs[30:50])
    trimmed = {s: {e: v for e, v in d.items() if e not in hueco} for s, d in base.items()}
    r = CF.mean_pairwise_rho(trimmed, strict=True)
    assert r["join_drop_pct"] == 0.0              # todos los syms pierden los MISMOS epochs
    assert r["n_obs"] == 90 - 20 - 1              # 1 retorno perdido por el salto


# ----------------------------------------------------------------- join drop
def test_tasa_de_descarte_se_calcula():
    s = _perfect(n=90, k=4)
    epochs = sorted(s["S0"].keys())
    for e in epochs[:9]:                          # 10% de agujeros en un solo sym
        del s["S0"][e]
    r = CF.mean_pairwise_rho(s, strict=True)
    assert r["join_drop_pct"] == pytest.approx(100 * 9 / 91, abs=0.01)
    assert r["drop_exceeded"] is False
    assert r["rho"] is not None


def test_descarte_por_encima_del_20pct_falla_ruidosamente():
    s = _perfect(n=200, k=4)
    epochs = sorted(s["S0"].keys())
    for e in epochs[:80]:                         # ~40% de descarte
        del s["S0"][e]
    with pytest.raises(CF.CorFleetError) as ei:
        CF.mean_pairwise_rho(s, strict=True)
    assert "descarte" in str(ei.value)

    # lenient: NUNCA sigue en silencio — marca el campo y rho queda None
    r = CF.mean_pairwise_rho(s, strict=False)
    assert r["drop_exceeded"] is True
    assert r["rho"] is None
    assert r["join_drop_pct"] > CF.MAX_JOIN_DROP_PCT
    assert r["reason"]


# ----------------------------------------------------------------- pct_60d
def test_pct_60d_none_con_menos_de_60_sesiones():
    for n in (0, 1, 10, 59):
        assert CF.percentile_of(0.7, [0.5] * n) is None, f"n={n}"


def test_pct_60d_nunca_es_medio_punto_por_defecto():
    """El bug de la casa: un 0.5 'plausible' donde deberia haber un None."""
    assert CF.percentile_of(0.7, [0.5] * 30) is not 0.5  # noqa: F632  (identidad a proposito)
    assert CF.percentile_of(0.7, [0.5] * 30) is None
    assert CF.percentile_of(None, [0.5] * 100) is None


def test_pct_60d_se_calcula_con_60_sesiones():
    hist = list(np.linspace(0.2, 0.8, 60))
    assert CF.percentile_of(0.81, hist) == pytest.approx(1.0)
    assert CF.percentile_of(0.19, hist) == pytest.approx(0.0)
    p = CF.percentile_of(0.5, hist)
    assert 0.4 < p < 0.6


def test_percentil_alto_fuerza_macro_aunque_rho_sea_medio():
    regime, cap, _, _ = CF.classify(0.60, 0.95)
    assert regime == "MACRO" and cap == 1.25


def test_percentil_bajo_fuerza_dispersion():
    regime, cap, name, _ = CF.classify(0.60, 0.05)
    assert regime == "DISPERSION" and (cap, name) == (0.75, 1.2)


# ----------------------------------------------------------------- amortiguador
def test_coeficientes_son_multiplicativos_no_aditivos():
    """La flecha tiene un tope duro de familias: el amortiguador MULTIPLICA los
    pesos EXISTENTES fleet(1.4)/components(1.3). Ningun factor nuevo se suma."""
    base_w = {"fleet": 1.4, "components": 1.3, "momentum": 1.0}
    for regime, (cap, name) in CF.COEFS.items():
        w = dict(base_w)
        w["fleet"] = round(w["fleet"] * cap, 4)
        w["components"] = round(w["components"] * cap, 4)
        assert set(w) == set(base_w), f"{regime} añadio una familia nueva"
        assert w["fleet"] == pytest.approx(1.4 * cap)
        assert w["momentum"] == 1.0            # intacto
        assert name > 0
    # neutralidad exacta de MIXED: multiplicar por 1.0 es la identidad
    assert CF.COEFS["MIXED"] == (1.0, 1.0)
    # y son coeficientes, no offsets: el producto de MACRO y DISPERSION rodea a 1
    assert CF.COEFS["MACRO"][0] > 1.0 > CF.COEFS["DISPERSION"][0]


def test_hook_ausente_es_neutro_multiplicativo(tmp_path):
    cap, name, why = CF.captain_damper(path=str(tmp_path / "no_existe.json"))
    assert (cap, name) == (1.0, 1.0) and why is None


def test_hook_rancio_es_neutro(tmp_path):
    p = tmp_path / "cor_fleet.json"
    p.write_text(json.dumps({"captain_coef": 1.25, "name_coef": 0.8,
                             "generated_at": 0, "why": "x"}))
    assert CF.captain_damper(path=str(p)) == (1.0, 1.0, None)


def test_hook_fresco_devuelve_el_coeficiente_y_su_why(tmp_path):
    import time
    p = tmp_path / "cor_fleet.json"
    p.write_text(json.dumps({"captain_coef": 1.25, "name_coef": 0.8,
                             "generated_at": int(time.time()), "data_age_s": 60,
                             "why": "cor-fleet MACRO: capitan x1.25, rho 0.81"}))
    cap, name, why = CF.captain_damper(path=str(p))
    assert (cap, name) == (1.25, 0.8)
    assert "x1.25" in why and "rho" in why


def test_hook_con_barras_rancias_es_neutro(tmp_path):
    """La flota parada deja los bars_*.txt en disco: un rho de hace 6 horas NO
    puede mover los pesos de la flecha de ahora."""
    import time
    p = tmp_path / "cor_fleet.json"
    p.write_text(json.dumps({"captain_coef": 1.25, "name_coef": 0.8,
                             "generated_at": int(time.time()), "data_age_s": 21600,
                             "why": "x"}))
    assert CF.captain_damper(path=str(p)) == (1.0, 1.0, None)
    p.write_text(json.dumps({"captain_coef": 1.25, "name_coef": 0.8,
                             "generated_at": int(time.time()), "why": "x"}))
    assert CF.captain_damper(path=str(p)) == (1.0, 1.0, None)   # sin campo = neutro


def test_why_siempre_imprime_el_coeficiente_aplicado():
    """Una flecha cuyos pesos se mueven con una variable invisible es inauditable."""
    w = CF.why_line("MACRO", 1.25, 0.81)
    assert "MACRO" in w and "1.25" in w and "0.81" in w
    w2 = CF.why_line(None, None, None)
    assert "no medible" in w2


# ----------------------------------------------------------------- head rho
def test_head_rho_ignora_la_pata_no_medible_y_nunca_inventa():
    assert CF.head_rho(0.8, None) == pytest.approx(0.8)
    assert CF.head_rho(None, 0.6) == pytest.approx(0.6)
    assert CF.head_rho(0.8, 0.6) == pytest.approx(0.7)
    assert CF.head_rho(None, None) is None


# ----------------------------------------------------------------- universos
def test_universos_se_leen_de_las_fuentes_reales():
    qqq = CF.qqq_components()
    semis = CF.semis_universe()
    assert len(qqq) >= 5 and "NVDA" in qqq
    assert "SMH" in semis and "MU" in semis
    assert all(isinstance(v, (int, float)) and v > 0 for v in qqq.values())


# ----------------------------------------------------------------- kill test
def test_kill_test_declara_refutada_si_un_regimen_domina():
    rows = [{"date": f"d{i}", "rho_head": 0.95} for i in range(120)]
    k = CF.kill_test(history=rows)
    assert k["frac"]["MACRO"] == 1.0
    assert "REFUTADA" in k["verdict"]


def test_kill_test_declara_sostenida_si_hay_dispersion_real():
    rows = [{"date": f"d{i}", "rho_head": 0.9 if i % 2 else 0.2} for i in range(120)]
    k = CF.kill_test(history=rows)
    assert k["frac"]["MACRO"] > 0.3 and k["frac"]["DISPERSION"] > 0.3
    assert "SOSTENIDA" in k["verdict"]


def test_kill_test_sin_historico_levanta():
    with pytest.raises(CF.CorFleetError):
        CF.kill_test(history=None, path=os.path.join(REPO, "data", "__no_existe__.json"))


# ----------------------------------------------------------------- io / vivo
def test_escritura_atomica(tmp_path):
    p = tmp_path / "out.json"
    CF.write_atomic(str(p), {"a": 1})
    assert json.loads(p.read_text())["a"] == 1
    assert not list(tmp_path.glob("*.tmp.*"))


def test_load_live_bars_lee_la_ventana(tmp_path, monkeypatch):
    monkeypatch.setattr(CF, "DATA", str(tmp_path))
    f = tmp_path / "bars_zzz_ibkr.txt"
    base = 1_700_000_000
    f.write_text("\n".join(f"{base+60*i} 1 2 3 {100+i} 10" for i in range(200)))
    win = CF.load_live_bars("ZZZ", window_min=60)
    assert win is not None and len(win) == 61
    assert max(win) == base + 60 * 199
    assert CF.load_live_bars("NOEXISTE") is None


def test_compute_live_no_revienta_y_es_señal_solamente(tmp_path):
    """Con las barras reales del repo: o mide, o dice por que — nunca un 0.0 mudo."""
    st = CF.compute_live(strict=False, history_path=str(tmp_path / "no_hay.json"))
    assert st["signal_only"] is True
    assert st["pct_60d"] is None and st["pct_60d_reason"]
    for k in ("rho_real_qqq", "rho_real_smh", "regime", "captain_coef",
              "name_coef", "join_drop_pct", "n_pairs", "generated_at"):
        assert k in st
    if st["rho_real_qqq"] is None:
        assert st["detail"]["qqq"]["reason"]
    else:
        assert -1.0 <= st["rho_real_qqq"] <= 1.0
    if st["regime"] is None:
        assert st["captain_coef"] is None and st["name_coef"] is None
    else:
        assert st["captain_coef"] in (0.75, 1.0, 1.25)
        assert not math.isnan(st["captain_coef"])


# ----------------------------------------------------------------- hook direction_view
def test_apply_damper_multiplica_y_no_añade_familias():
    w = {"flip": 0.9, "walls": 1.1, "fleet": 1.4, "components": 1.3, "momentum": 1.0}
    for regime, (cap, _n) in CF.COEFS.items():
        out = CF.apply_damper(w, cap)
        assert set(out) == set(w), f"{regime} añadio/quito familias"
        assert out["fleet"] == pytest.approx(1.4 * cap)
        assert out["components"] == pytest.approx(1.3 * cap)
        for k in ("flip", "walls", "momentum"):
            assert out[k] == w[k], "el amortiguador toco una familia que no es suya"
        assert w["fleet"] == 1.4, "apply_damper mutó la entrada"


def test_apply_damper_neutro_no_cambia_nada():
    w = {"fleet": 1.4, "components": 1.3}
    assert CF.apply_damper(w, 1.0) == w
    assert CF.apply_damper(w, None) == w


def test_hook_de_direction_view_esta_apagado_por_defecto():
    """NINGUNA VOZ NUEVA en esta ola: el amortiguador no toca la flecha sin flag."""
    src = open(os.path.join(REPO, "scripts", "direction_view.py"), encoding="utf-8").read()
    assert 'os.environ.get("COR_FLEET_DAMPER") == "1"' in src
    assert "apply_damper(weights, cap_coef)" in src
    assert "weights[" not in src.split("cor-fleet")[1].split("# 4c)")[0], \
        "el hook debe delegar en apply_damper, no escribir pesos a mano"
