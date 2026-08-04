"""Los MEJORES al X (Yunior 2026-08-04): flujo UW medido si, Finviz degradado."""
import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location("ibt_xsp", os.path.join(SCRIPTS, "x_signal_poster.py"))
X = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = X
spec.loader.exec_module(X)


def test_uw_flow_grande_califica_como_hecho():
    ok, key, text = X.qualifies_factual(
        "UW FLOW AMZN", "CALLS ask-side strike 300 exp 09-18 — premium 1.3M ask-side")
    assert ok and key.startswith("uwflow:AMZN:calls")
    assert "$AMZN" in text and "1.3M" in text and "Not financial advice" in text
    assert "%" not in text                      # cero probabilidad fabricada


def test_uw_flow_sweep_califica():
    ok, key, text = X.qualifies_factual(
        "UW FLOW AMD", "CALLS ask-side strike 502.5 exp 08-07 — SWEEP $931k")
    assert ok and "sweep" in text


def test_uw_flow_pequeno_no_califica():
    """vol/OI sin premium grande se queda en Discord: X es solo lo mas selectivo."""
    ok, _, _ = X.qualifies_factual(
        "UW FLOW QQQ", "CALLS bid-side strike 705 exp 08-07 — vol/OI 2.6 (posicion nueva) $315k")
    assert not ok


def test_titulos_normales_no_entran_por_la_rama_factual():
    for t, m in (("🎈 BB REBOTE", "mu puede bajar"), ("FINVIZ BUFFETT", "FSLR BUY"),
                 ("🧱 MUROS PREMARKET", "texto en espanol")):
        assert X.qualifies_factual(t, m)[0] is False


def test_finviz_degradado_en_x():
    assert X.MAX_FINVIZ_PER_DAY <= 3
    ok, why = X.finviz_relevance({"screen": "momentum", "weather": "BUY", "score": 6,
                                  "possible": 7, "change_pct": 2.0, "rvol": 1.6})
    assert not ok and "2.0x" in why             # RVOL>=2.0: el unico corte con vida propia


def test_finviz_rvol_alto_si_pasa():
    ok, _ = X.finviz_relevance({"screen": "momentum", "weather": "BUY", "score": 6,
                                "possible": 7, "change_pct": 2.0, "rvol": 2.4})
    assert ok
