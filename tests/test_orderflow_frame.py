import importlib.util
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chart_bridge_orderflow", ROOT / "scripts/chart_bridge.py")
CB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CB)


def test_missing_tape_is_explicit_not_zero(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, mt = CB.footprint_frame("QQQ", "5m")
    assert mt is None and frame["state"] == "NO_TAPE"
    assert frame["bars"] == [] and "cinta realtime completa" in frame["reason"]


def test_missing_tape_explains_active_delayed_provider(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    (data / "market_source.txt").write_text("intrinio\n")
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, _ = CB.footprint_frame("QQQ", "5m")
    assert frame["market_provider"] == "intrinio"
    assert "delayed 15m" in frame["reason"] and frame["bars"] == []


def test_selects_chart_timeframe_and_recomputes_freshness(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    now = int(time.time())
    raw = {
        "sym": "QQQ", "asof": now, "source": "IBKR AllLast realtime",
        "quality": "TRUE_L1_TAPE", "classification_pct": 98.5,
        "tick_size": 0.01, "doctrine": "DESCRIPTIVE_UNPROVEN_SIGNAL_ONLY",
        "timeframes": {
            "60": {"seconds": 60, "bars": [{"time": now - 60}]},
            "300": {"seconds": 300, "bars": [{"time": now - 300}]},
        },
    }
    (data / "footprint_qqq.json").write_text(json.dumps(raw))
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, mt = CB.footprint_frame("qqq", "5m")
    assert mt is not None and frame["state"] == "LIVE"
    assert frame["seconds"] == 300 and frame["bars"][0]["time"] == now - 300
    assert frame["quality"] == "TRUE_L1_TAPE" and frame["age_s"] < 2


def test_low_classification_is_visible_quality_state(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    now = int(time.time())
    (data / "footprint_spy.json").write_text(json.dumps({
        "asof": now, "classification_pct": 55, "quality": "TRUE_L1_TAPE",
        "timeframes": {"60": {"bars": []}},
    }))
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, _ = CB.footprint_frame("spy", "1m")
    assert frame["quality"] == "LOW_CLASSIFICATION"


def test_unsupported_timeframe_does_not_fake_aggregation(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, _ = CB.footprint_frame("QQQ", "45s")
    assert frame["state"] == "UNSUPPORTED_TF" and frame["bars"] == []


def test_perp_source_is_explicit_and_never_overwrites_equity_identity(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    now = int(time.time())
    (data / "footprint_qqqusdt.json").write_text(json.dumps({
        "asof": now, "source": "OKX signed perpetual tape",
        "quality": "VENUE_NATIVE_SIDE_THIN_PERP", "instrument_kind": "TOKENIZED_STOCK_PERPETUAL",
        "proxy_for": "QQQ", "side_provenance": "NATIVE", "classification_pct": 100,
        "timeframes": {"300": {"seconds": 300, "bars": [{"time": now - 1}]}},
    }))
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, _ = CB.footprint_frame("QQQ", "5m", "perp")
    assert frame["sym"] == "QQQUSDT" and frame["requested_sym"] == "QQQ"
    assert frame["tape_source"] == "perp" and frame["proxy_for"] == "QQQ"
    assert frame["instrument_kind"] == "TOKENIZED_STOCK_PERPETUAL"


def test_live_perp_socket_marks_silent_symbol_quiet_not_feed_stale(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    now = int(time.time())
    (data / "perp_ws_state.json").write_text(json.dumps({"latido": now, "mudos": []}))
    (data / "footprint_muusdt.json").write_text(json.dumps({
        "asof": now - 40, "instrument_kind": "TOKENIZED_STOCK_PERPETUAL",
        "timeframes": {"60": {"bars": [{"time": now - 60}]}},
    }))
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    frame, _ = CB.footprint_frame("MU", "1m", "perp")
    assert frame["state"] == "QUIET" and "socket PERP vivo" in frame["reason"]


def test_panel_asset_is_loaded_and_served():
    html = (ROOT / "charts/live.html").read_text()
    bridge = (ROOT / "scripts/chart_bridge.py").read_text()
    panel = (ROOT / "charts/orderflow_panel.js").read_text()
    assert '<script src="orderflow_panel.js"></script>' in html
    assert '@app.get("/orderflow_panel.js")' in bridge
    for label in ("BID × ASK", "POC cluster", "3× imbalance", "FORMING"):
        assert label in panel
