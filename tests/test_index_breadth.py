"""index_breadth.py — component_lean() no-data path, breadth() aggregation guards."""
import numpy as np
import pytest


def test_component_lean_no_data_graceful(breadth_mod, monkeypatch):
    # yfinance raising -> the broad except returns the neutral triple, no crash.
    def _boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(breadth_mod.yf, "Ticker", _boom)
    lean, tag, gap = breadth_mod.component_lean("NVDA")
    assert (lean, tag, gap) == (0.0, "s/d", 0.0)


def test_breadth_all_sd_no_div_zero(breadth_mod, monkeypatch):
    # Every component returns s/d -> tot==0 -> score guarded to 0.0, verdict NEUTRO.
    monkeypatch.setattr(breadth_mod, "component_lean", lambda s: (0.0, "s/d", 0.0))
    b = breadth_mod.breadth("QQQ")
    assert b["score"] == 0.0
    assert "NEUTRO" in b["verdict"]
    assert b["components"] == {}
    assert b["aligned_top"] == []


def test_breadth_all_neutral_score_zero_neutro(breadth_mod, monkeypatch):
    # Components present but flat (lean 0) -> weighted score 0 -> NEUTRO verdict.
    monkeypatch.setattr(breadth_mod, "component_lean", lambda s: (0.0, "rango", 0.0))
    b = breadth_mod.breadth("QQQ")
    assert b["score"] == pytest.approx(0.0, abs=1e-9)
    assert "NEUTRO" in b["verdict"]
    assert b["components"]  # they were counted
    assert b["breakdowns"] == [] and b["breakouts"] == []


def test_breadth_weight_normalization_partial(breadth_mod, monkeypatch):
    # Only NVDA has data (fully bullish); everything else s/d. Weighted score must
    # normalise over the AVAILABLE weight only -> score == NVDA's lean (1.0).
    def lean(sym):
        if sym == "NVDA":
            return 1.0, "ruptura alcista", 2.0
        return 0.0, "s/d", 0.0

    monkeypatch.setattr(breadth_mod, "component_lean", lean)
    b = breadth_mod.breadth("QQQ")
    assert b["score"] == pytest.approx(1.0, abs=1e-9)
    assert list(b["components"].keys()) == ["NVDA"]
    assert "ALCISTA" not in b["verdict"] or b["aligned_top"] == ["NVDA"]


def test_breadth_bearish_gear_verdict(breadth_mod, monkeypatch):
    # Top holdings all leaning hard down -> ENGRANAJE BAJISTA with >=2 aligned.
    monkeypatch.setattr(breadth_mod, "component_lean",
                        lambda s: (-0.8, "RUPTURA BAJISTA", -1.5))
    b = breadth_mod.breadth("SPY")
    assert b["score"] <= -0.35
    assert "BAJISTA" in b["verdict"]
    assert len(b["aligned_top"]) >= 2
    assert set(b["breakdowns"]) == set(b["components"].keys())


def test_breadth_unknown_index_empty_weights(breadth_mod):
    # An index with no weight table must degrade to neutral, not raise.
    b = breadth_mod.breadth("ZZZZ")
    assert b["score"] == 0.0
    assert b["components"] == {}
    assert "NEUTRO" in b["verdict"]
