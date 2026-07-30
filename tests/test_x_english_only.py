import importlib.util
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


xc = load("x_post_common")
xs = load("x_signal_poster")


def test_public_guard_rejects_mixed_spanish_and_korean():
    assert not xc.public_text_is_english("Bullish wrapper: señal alcista de ballena")
    assert not xc.public_text_is_english("Samsung earnings 삼성전자")
    assert xc.public_text_is_english("Bullish reclaim confirmed. Not financial advice.")


def test_live_signal_does_not_copy_spanish_source_text():
    text = xs.build_post(
        "AAPL",
        "BALLENA DE CALLS",
        "tendencia alcista; ruptura confirmada; alto volumen",
        340.0,
        342.5,
        338.5,
        76,
    )
    assert xc.public_text_is_english(text)
    assert "Unusual call volume" in text
    assert "alcista" not in text.lower()
    assert "ruptura" not in text.lower()


def test_bearish_retest_is_rendered_in_english():
    text = xs.build_post(
        "QQQ", "SEÑAL", "SELL bajista retest-ok px=660", 660, 655, 663, 74
    )
    assert "Bearish break-and-retest confirmed" in text
    assert xc.public_text_is_english(text)
