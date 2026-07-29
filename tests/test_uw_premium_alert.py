import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_premium_alert as A  # noqa: E402

NOW = 1_000_000
BULL = {"signed_premium": 2_718_874, "net_call_premium": 2_041_298,
        "net_put_premium": -677_576}
BEAR = {"signed_premium": -2_500_000, "net_call_premium": -400_000,
        "net_put_premium": 2_100_000}


def levels(**overrides):
    base = {"sym": "TEST", "asof": NOW - 30, "spot": 100, "flip": 95,
            "regime": "POS", "pressure": 50, "em": 3,
            "abs_wall": 100, "abs_wall_gex": 10_000_000,
            "call_wall": 105, "call_wall_gex": 5_000_000,
            "put_wall": 95, "put_wall_gex": -2_000_000}
    base.update(overrides)
    return base


def test_aapl_flujo_alcista_en_pin_340_no_confirma_continuacion():
    ctx = A.structural_context(
        levels(sym="AAPL", abs_wall=340, spot=340.23, flip=334, em=5), 340.4, NOW)
    alert = A.build_alert("AAPL", BULL, ctx)
    assert ctx["kind"] == "pin"
    assert "FLUJO AGRESOR ALCISTA" in alert["title"]
    assert "flujo alcista, pero AAPL fijado al pin 340" in alert["message"]
    assert "continuación NO confirmada" in alert["voice"]
    assert "compra" not in alert["voice"].lower()


def test_googl_acercandose_a_muro_superior_es_objetivo_no_breakout():
    ctx = A.structural_context(
        levels(sym="GOOGL", abs_wall=335, spot=333, flip=328, em=4.5), 333.0, NOW)
    alert = A.build_alert("GOOGL", BULL, ctx)
    assert ctx["kind"] == "magnet" and ctx["dir"] == "up"
    assert "objetivo 335 (imán/muro superior)" in alert["message"]
    assert "no asumir ruptura, esperar aceptación/retest" in alert["voice"]
    assert "breakout" not in alert["message"].lower()


def test_bajista_hacia_iman_inferior_es_espejo():
    ctx = A.structural_context(
        levels(sym="TEST", abs_wall=95, abs_wall_gex=10_000_000,
               spot=97, flip=90, em=4), 97.0, NOW)
    alert = A.build_alert("TEST", BEAR, ctx)
    assert ctx["kind"] == "magnet" and ctx["dir"] == "down"
    assert "FLUJO AGRESOR BAJISTA" in alert["title"]
    assert "objetivo 95 (imán/muro inferior)" in alert["message"]
    assert "no asumir ruptura" in alert["voice"]


def test_levels_stale_o_missing_degradan_a_solo_flujo():
    assert A.structural_context(levels(asof=NOW - 601), 100, NOW) is None
    assert A.structural_context(None, 100, NOW) is None
    assert A.structural_context(levels(), None, NOW) is None
    alert = A.build_alert("AAPL", BULL, None)
    assert "Flujo agresor alcista en AAPL" in alert["message"]
    assert "pin" not in alert["message"] and "imán" not in alert["message"]


def test_uw_agregado_declara_strike_no_disponible_en_texto_y_voz():
    alert = A.build_alert("AAPL", BULL)
    expected = "strike no disponible (flujo agregado)"
    assert expected in alert["message"]
    assert expected in alert["voice"]
    assert "netos comprados en calls" not in alert["voice"]
