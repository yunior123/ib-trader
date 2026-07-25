"""Tests del VETO POR CALIDAD DE LIBRO — feature minada #3 (2026-07-25).

La feature existe para BORRAR confirmaciones falsas, no para añadir una señal: con
`coef = 0.0` la lectura es "los niveles gamma son decoracion hoy para este nombre".
Medido el 2026-07-25: NOK tiene **1 strike poblado** y DRAM **7** — y la casa cantaba
veredictos de muro y regimen sobre eso igual que sobre QQQ (48 strikes).
"""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core as G           # noqa: E402
import book_quality as BQ      # noqa: E402


# ======================================== 4. libro tipo NOK -> THIN y coef 0.0
def test_libro_tipo_nok_es_THIN_con_coef_cero():
    """4 strikes (la cadena real de NOK) no puede DEFINIR un muro."""
    ev = BQ.evaluate(gross=3.9e5, net=-3.9e5, hhi=0.5, n_strikes=4,
                     greeks_ok_pct=1.0, spot=9.09, flip=9.0)
    assert ev["book_label"] == "THIN"
    assert ev["coef"] == 0.0
    assert any("strikes poblados" in w for w in ev["why"])
    assert any("decoracion" in w for w in ev["why"])


def test_THIN_por_griegas_ausentes():
    """Un libro ancho pero sin griegas tambien es THIN: 40 strikes con iv=-1 no son un mapa."""
    ev = BQ.evaluate(gross=None, net=None, hhi=None, n_strikes=40,
                     greeks_ok_pct=0.0, spot=100.0, flip=None)
    assert ev["book_label"] == "THIN"
    assert ev["coef"] == 0.0
    assert any("griegas" in w for w in ev["why"])


def test_THIN_por_percentil_de_libro():
    ev = BQ.evaluate(gross=1e6, net=5e5, hhi=0.05, n_strikes=30, greeks_ok_pct=1.0,
                     spot=100.0, flip=90.0, book_pctile=0.10, impact_pctile=0.9)
    assert ev["book_label"] == "THIN"
    assert ev["coef"] == 0.0


def test_THIN_es_prioritario_sobre_cualquier_otra_etiqueta():
    """Cerca del flip Y fino: manda THIN (mutea todo), no NEAR_FLIP (que solo degrada)."""
    ev = BQ.evaluate(gross=1e5, net=-1e5, hhi=0.9, n_strikes=3, greeks_ok_pct=1.0,
                     spot=100.0, flip=100.05)
    assert ev["book_label"] == "THIN"
    assert ev["coef"] == 0.0


# ============================== 5. libro denso y sano -> STABLE_PIN con coef alto
def test_libro_denso_y_sano_es_STABLE_PIN_con_coef_alto():
    ev = BQ.evaluate(gross=8.0e8, net=6.0e8, hhi=0.04, n_strikes=48, greeks_ok_pct=0.98,
                     spot=684.0, flip=660.0, book_pctile=0.82, impact_pctile=0.90)
    assert ev["book_label"] == "STABLE_PIN"
    # 0.35 + 0.65*min(0.82, 0.90) = 0.883
    assert ev["coef"] == pytest.approx(0.35 + 0.65 * 0.82, abs=1e-4)
    assert ev["coef"] > 0.8
    assert ev["coef_basis"] == "percentiles"


def test_sin_percentiles_el_coef_cae_al_SUELO_y_lo_declara():
    """No hay 20 sesiones de snapshot completo de Polygon todavia. El coef NO se inventa:
    cae al suelo conservador y `coef_basis` lo dice."""
    ev = BQ.evaluate(gross=8.0e8, net=6.0e8, hhi=0.04, n_strikes=48, greeks_ok_pct=0.98,
                     spot=684.0, flip=660.0)
    assert ev["book_label"] == "STABLE_PIN"
    assert ev["coef"] == BQ.COEF_FLOOR
    assert ev["coef_basis"] == "suelo_sin_percentiles"
    assert any("percentil" in w for w in ev["why"])


def test_bifurcated_solo_con_libro_grande_y_net_negativo():
    """gross/|net| alto con net<0 = mucha gamma total y poca neta: scalps nivel-a-nivel SI,
    direccion-por-regimen NO. Exige book_pctile>0.5 (si el libro es chico, es THIN o ruido)."""
    ev = BQ.evaluate(gross=1.0e9, net=-1.0e8, hhi=0.03, n_strikes=50, greeks_ok_pct=1.0,
                     spot=100.0, flip=90.0, book_pctile=0.9, impact_pctile=0.7)
    assert ev["book_label"] == "BIFURCATED"
    assert any("direccion-por-regimen NO" in w for w in ev["why"])
    # el mismo libro sin percentil medido NO puede afirmarse bifurcado
    ev2 = BQ.evaluate(gross=1.0e9, net=-1.0e8, hhi=0.03, n_strikes=50, greeks_ok_pct=1.0,
                      spot=100.0, flip=90.0)
    assert ev2["book_label"] != "BIFURCATED"


def test_near_flip():
    ev = BQ.evaluate(gross=8e8, net=1e6, hhi=0.04, n_strikes=48, greeks_ok_pct=1.0,
                     spot=684.0, flip=684.5, book_pctile=0.8, impact_pctile=0.8)
    assert ev["book_label"] == "NEAR_FLIP"
    ev2 = BQ.evaluate(gross=8e8, net=1e6, hhi=0.04, n_strikes=48, greeks_ok_pct=1.0,
                      spot=684.0, flip=690.0, book_pctile=0.8, impact_pctile=0.8)
    assert ev2["book_label"] == "STABLE_PIN"


def test_abs_wall_sign_sale_del_REGIMEN_no_del_signo_crudo():
    """El discriminador NO es el signo del perfil (con calls+/puts- un put wall es negativo
    POR CONSTRUCCION y se etiquetaria TODO como trampilla): es el regimen acumulado en el
    nivel, de que lado del flip cae."""
    pin = BQ.evaluate(1e9, 5e8, 0.04, 40, 1.0, 100.0, 90.0, abs_wall_regime="POS")
    trap = BQ.evaluate(1e9, 5e8, 0.04, 40, 1.0, 100.0, 90.0, abs_wall_regime="NEG")
    nada = BQ.evaluate(1e9, 5e8, 0.04, 40, 1.0, 100.0, 90.0, abs_wall_regime=None)
    assert pin["abs_wall_sign"] == "+"
    assert trap["abs_wall_sign"] == "-"
    assert nada["abs_wall_sign"] is None
    assert any("TRAMPILLA" in w and "VETO DURO" in w for w in trap["why"])


# ================== 6. bifurcation / HHI calculados A MANO sobre un perfil sintetico
def test_gross_net_bifurcation_y_hhi_a_mano():
    """spot=100, scale='house' -> mult=100. GEX_strike = gamma*oi*100*mult.
        C K=100 oi=10 gamma=0.010 ->  0.010*10*100*100 = +1000
        P K= 95 oi=20 gamma=0.020 ->  0.020*20*100*100 = -4000
        C K=105 oi= 5 gamma=0.005 ->  0.005* 5*100*100 =  +250
      gross = 5250 ; net = -2750 ; bifurcation = 5250/2750
      HHI = (4000/5250)^2 + (1000/5250)^2 + (250/5250)^2 = 0.6190476..."""
    cons = [
        {"strike": 100.0, "right": "C", "oi": 10, "gamma": 0.010, "iv": 0.3, "T": 0.02},
        {"strike": 95.0, "right": "P", "oi": 20, "gamma": 0.020, "iv": 0.3, "T": 0.02},
        {"strike": 105.0, "right": "C", "oi": 5, "gamma": 0.005, "iv": 0.3, "T": 0.02},
    ]
    g = G.build_gex(cons, 100.0, scale="house")
    assert g["profile"] == {100.0: 1000.0, 95.0: -4000.0, 105.0: 250.0}
    assert g["gross_gex"] == pytest.approx(5250.0)
    assert g["net_gex"] == pytest.approx(-2750.0)
    assert g["bifurcation"] == pytest.approx(5250.0 / 2750.0, rel=1e-12)
    assert g["hhi"] == pytest.approx(0.6190476190476191, rel=1e-12)
    assert g["n_strikes_populated"] == 3
    # HHI: un libro concentrado en UN strike da 1.0; repartido en 4 iguales, 0.25
    uno = G.build_gex([cons[0]], 100.0)
    assert uno["hhi"] == pytest.approx(1.0)
    assert uno["bifurcation"] == pytest.approx(1.0)


def test_agregados_son_None_cuando_no_hay_perfil():
    """Libro sin griegas: gross/hhi/bifurcation a None. Un 0 en `hhi` se leeria como
    'libro perfectamente repartido', que es lo contrario de 'no lo se'."""
    cons = [{"strike": 100.0, "right": "C", "oi": 10, "gamma": None, "iv": None, "T": 0.02}]
    g = G.build_gex(cons, 100.0)
    assert g["gross_gex"] is None
    assert g["hhi"] is None
    assert g["bifurcation"] is None
    assert g["net_gex"] is None
    assert g["n_strikes_populated"] == 0
    assert g["n_oi_no_greeks"] == 1
    # el OI si es real: el muro por OI puro sobrevive
    assert g["oi_call_wall"] == 100.0


# ---------------------------------------------------------------- percentiles
def test_percentil_no_se_publica_con_muestra_corta():
    assert BQ.percentile(5.0, [1, 2, 3]) is None                  # n < HIST_MIN
    assert BQ.percentile(5.0, []) is None
    assert BQ.percentile(None, [1, 2, 3, 4, 5, 6]) is None
    assert BQ.percentile(5.0, [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert BQ.percentile(0.5, [1, 2, 3, 4, 5]) == pytest.approx(0.0)
    assert BQ.percentile(3.0, [1, 2, 3, 4, 5]) == pytest.approx(0.6)


def test_ledger_ignora_lineas_corruptas(tmp_path):
    p = tmp_path / "h.jsonl"
    p.write_text('{"sym":"QQQ","gross":10,"impact":1e-9}\n'
                 'basura no json\n'
                 '{"sym":"QQQ","gross":20}\n')
    h = BQ.load_hist(str(p))
    assert h["QQQ"]["gross"] == [10.0, 20.0]
    assert h["QQQ"]["impact"] == [1e-9]


# ------------------------------------- contrato con el consumidor C++ (./compass)
def test_contrato_book_quality_json_para_compass():
    """./compass hace json_section(bq, SYM) y luego jstr("book_label") / jnum("coef").
    Eso exige que cada simbolo sea un OBJETO con esas dos claves exactas."""
    p = os.path.join(REPO, BQ.OUT_JSON)
    if not os.path.exists(p):
        pytest.skip("data/book_quality.json aun no generado")
    d = json.load(open(p))
    syms = [k for k in d if k.isupper()]
    assert syms, "book_quality.json sin ningun simbolo"
    for s in syms:
        assert isinstance(d[s], dict)
        assert "book_label" in d[s] and "coef" in d[s]
        assert d[s]["book_label"] in ("THIN", "BIFURCATED", "NEAR_FLIP", "STABLE_PIN")
        assert 0.0 <= d[s]["coef"] <= 1.0
        if d[s]["book_label"] == "THIN":
            assert d[s]["coef"] == 0.0
        assert d[s].get("abs_wall_sign") in (None, "+", "-")


def test_libros_finos_de_la_flota_quedan_muteados():
    """Resultado ESPERADO Y DESEADO de la feature: silencio gamma en los libros de 3
    contratos. Si alguno de estos deja de estar THIN con una cadena tan corta, es un bug."""
    p = os.path.join(REPO, BQ.OUT_JSON)
    if not os.path.exists(p):
        pytest.skip("data/book_quality.json aun no generado")
    d = json.load(open(p))
    for s in ("NOK", "DRAM", "SPCX", "SKHY"):
        if s not in d:
            continue
        n = d[s].get("n_strikes_populated")
        if n is not None and n >= BQ.THIN_STRIKES and (d[s].get("greeks_ok_pct") or 0) >= 0.5:
            continue          # si algun dia tiene libro de verdad, que no falle el test
        assert d[s]["book_label"] == "THIN", f"{s} con {n} strikes deberia estar THIN"
        assert d[s]["coef"] == 0.0
