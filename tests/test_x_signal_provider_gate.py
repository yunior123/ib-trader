"""Candle-derived X posts must not call a delayed bar feed realtime."""
import importlib.util
import json
import os


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "x_signal_provider_gate", os.path.join(REPO, "scripts", "x_signal_poster.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_delayed_market_provider_fails_closed(tmp_path):
    p = tmp_path / "provider.json"
    p.write_text(json.dumps({
        "market_provider": "intrinio",
        "proveedores": {"intrinio": {"latencia": "delayed_15m"}},
    }))
    assert mod.realtime_bar_feed_ready(str(p)) is False


def test_realtime_market_provider_opens_gate(tmp_path):
    p = tmp_path / "provider.json"
    p.write_text(json.dumps({
        "market_provider": "ibkr",
        "proveedores": {"ibkr": {"latencia": "tiempo_real"}},
    }))
    assert mod.realtime_bar_feed_ready(str(p)) is True
