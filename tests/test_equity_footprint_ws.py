import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("equity_footprint_ws", ROOT / "scripts/equity_footprint_ws.py")
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)


def test_quote_rule_uses_only_earlier_fresh_nbbo():
    c = MOD.Classifier(quote_max_age_s=2)
    c.quote("QQQ", 100.0, 10.00, 10.02)
    assert c.trade("QQQ", 101.0, 10.02) == (1, 10.00, 10.02, "Q")
    assert c.trade("QQQ", 101.1, 10.00) == (-1, 10.00, 10.02, "Q")
    # Future quote relative to trade is forbidden.
    c.quote("QQQ", 105.0, 10.00, 10.02)
    assert c.trade("QQQ", 104.0, 10.01)[3] != "Q"


def test_tick_rule_and_unknown_are_not_forced_to_a_side():
    c = MOD.Classifier()
    assert c.trade("MU", 100, 20.00) == (0, 0.0, 0.0, "U")
    assert c.trade("MU", 101, 20.01)[0::3] == (1, "T")
    assert c.trade("MU", 102, 20.01)[0::3] == (1, "T")
    assert c.trade("MU", 103, 19.99)[0::3] == (-1, "T")


def test_writer_keeps_method_and_unknown(tmp_path):
    w = MOD.TapeWriter(tmp_path)
    w.write("SPY", 123.5, 700.1, 4, 0, 700.0, 700.2, "U"); w.close()
    row = (tmp_path / "footprint_tape_spy.txt").read_text().split()
    assert row[0] == "123.500000" and row[3] == "0" and row[-1] == "U"
