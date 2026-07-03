import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import ta_view  # noqa: E402


def test_massive_failure_is_data_not_fake_orderflow(monkeypatch, tmp_path):
    monkeypatch.setattr(ta_view, "DATA", str(tmp_path))
    (tmp_path / "equity_footprint_ws_state.json").write_text(json.dumps({
        "provider": "massive", "status": "FAILED",
        "reason": "plan has no websocket", "doctrine": "REALTIME_OR_FAIL_CLOSED",
    }))
    line = ta_view._house_orderflow("SOFI")
    assert "DATA" in line
    assert "FAILED" in line
    assert "plan has no websocket" in line


def test_heatmap_preserves_activity_vs_dealer_gex_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(ta_view, "DATA", str(tmp_path))
    (tmp_path / "gex_heatmap_sofi.json").write_text(json.dumps({
        "spot": 18.43, "date": "2026-08-13", "fetch_ts": 2, "source_ts": 1,
        "stale": True, "metric": "gamma_volume",
        "architect": {"activity_score": 25, "activity_side": "CALL_ACTIVITY",
                      "dealer_gex_available": False,
                      "note": "volume activity is not dealer GEX"},
        "oi_structure": {"status": "OK", "source": "polygon_options_snapshot",
                         "net_gex": 10, "flip": 17, "regime": "POS"},
    }))
    line = ta_view._house_heatmap("SOFI")
    assert '"dealer_gex_available":false' in line
    assert '"source":"polygon_options_snapshot"' in line
    assert '"stale":true' in line
