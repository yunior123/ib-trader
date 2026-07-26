"""index_breadth.py:58-62 — pc/pl/ph deben venir del cierre ANTERIOR (iloc[-2]), no
de la vela de HOY (iloc[-1], parcial/en vivo) contra la que se comparaba `now`,
dejando gap~0 siempre."""
import numpy as np
import pandas as pd
import pytest


class _FakeHist:
    def __init__(self, closes, highs, lows):
        self.Close = pd.Series(closes)
        self.High = pd.Series(highs)
        self.Low = pd.Series(lows)

    def __len__(self):
        return len(self.Close)


class _FakeTicker:
    def __init__(self, closes, highs, lows):
        self._h = _FakeHist(closes, highs, lows)

    def history(self, period=None, interval=None):
        return self._h


def test_gap_uses_previous_close_not_today(breadth_mod, monkeypatch):
    # 4 dias: [d-3, d-2, d-1(ayer, close=100)], hoy (parcial, close-en-vivo=105).
    closes = [98, 99, 100, 105]
    highs = [99, 100, 101, 106]
    lows = [97, 98, 99, 104]
    monkeypatch.setattr(breadth_mod.yf, "Ticker",
                         lambda sym: _FakeTicker(closes, highs, lows))
    monkeypatch.setattr(breadth_mod, "latest_close", lambda sym: 105.0)
    lean, tag, gap = breadth_mod.component_lean("NVDA")
    # gap = (now - cierre DE AYER) / cierre DE AYER = (105-100)/100 = +5%, no ~0%.
    assert gap == pytest.approx(5.0, abs=0.01)
    assert tag != "s/d"


def test_gap_near_zero_when_today_equals_yesterday_close(breadth_mod, monkeypatch):
    closes = [98, 99, 100, 100]
    highs = [99, 100, 101, 101]
    lows = [97, 98, 99, 99]
    monkeypatch.setattr(breadth_mod.yf, "Ticker",
                         lambda sym: _FakeTicker(closes, highs, lows))
    monkeypatch.setattr(breadth_mod, "latest_close", lambda sym: 100.0)
    lean, tag, gap = breadth_mod.component_lean("NVDA")
    assert gap == pytest.approx(0.0, abs=0.01)


def test_insufficient_history_returns_no_data(breadth_mod, monkeypatch):
    # < 4 filas: no hay suficiente historia para aislar el cierre de ayer del de hoy.
    monkeypatch.setattr(breadth_mod.yf, "Ticker",
                         lambda sym: _FakeTicker([1, 2, 3], [2, 3, 4], [0, 1, 2]))
    lean, tag, gap = breadth_mod.component_lean("NVDA")
    assert (lean, tag, gap) == (0.0, "s/d", 0.0)
