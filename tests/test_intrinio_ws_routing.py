"""Intrinio products with delayed prices must not claim the canonical live print."""
import importlib.util
import os


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "intrinio_ws_routing", os.path.join(REPO, "scripts", "intrinio_ws_autostart.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_equities_edge_is_not_a_canonical_realtime_print():
    assert mod.provider_is_canonical_realtime("EQUITIES_EDGE") is False
    assert mod.provider_is_canonical_realtime("DELAYED_SIP") is False


def test_exchange_realtime_products_can_write_the_canonical_print():
    assert mod.provider_is_canonical_realtime("REALTIME") is True
    assert mod.provider_is_canonical_realtime("IEX") is True
