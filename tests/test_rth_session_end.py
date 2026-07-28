"""test_rth_session_end.py — el fin de RTH es 16:00, no 15:30.

BUG (Yunior 2026-07-27, dinero en vivo): "market time is 9:30->16:00, not
9:30->15:30. The fleet partially turns off with 30 min left." Los gates de
entrada (rth_entry + 2 trend_rth) de los 24 *_signal_bot.cpp cortaban en
`mins < 930` (15:30); dip_alert moria en `hm >= 1530`. La ultima media hora es
de las mas operativas (imanes de cierre, charm de tarde). Fin RTH = 960 (16:00).

Invariante de fuente (no compila): que nadie reintroduzca 930/1530 como cierre.
570=9:30, 930=15:30, 960=16:00.
"""
import glob
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOTS = sorted(glob.glob(os.path.join(REPO, "*_signal_bot.cpp")))

pytestmark = pytest.mark.skipif(not BOTS, reason="no hay *_signal_bot.cpp")


@pytest.mark.parametrize("src", BOTS, ids=lambda p: os.path.basename(p))
def test_bot_entry_gate_ends_at_1600(src):
    txt = open(src).read()
    assert "mins < 930" not in txt, (
        f"{os.path.basename(src)}: gate de entrada corta en 930 (15:30); "
        "el fin de RTH es 960 (16:00)"
    )
    # rth_entry + 2 trend_rth = 3 gates de entrada + 1 acumulador VWAP = 4
    assert txt.count("mins < 960") >= 3, (
        f"{os.path.basename(src)}: faltan gates de entrada con fin RTH 960"
    )


@pytest.mark.parametrize("src", BOTS, ids=lambda p: os.path.basename(p))
def test_bot_header_no_1530(src):
    txt = open(src).read()
    assert "9:30-15:30 ET (RTH rule)" not in txt, (
        f"{os.path.basename(src)}: la cabecera aun dice 9:30-15:30"
    )


def test_dip_alert_dies_at_1600():
    p = os.path.join(REPO, "scripts", "dip_alert.py")
    if not os.path.exists(p):
        pytest.skip("falta dip_alert.py")
    txt = open(p).read()
    assert "hm >= 1530" not in txt, "dip_alert muere a las 15:30; debe llegar a 16:00"
    assert "hm >= 1600" in txt, "dip_alert debe morir en hm >= 1600 (16:00)"
