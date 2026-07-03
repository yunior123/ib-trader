from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = (ROOT / "scripts" / "chart_bridge.py").read_text(encoding="utf-8")
STARTUP = (ROOT / "scripts" / "chart_qa_windows.sh").read_text(encoding="utf-8")


def test_polygon_oi_is_opt_in_and_disabled_on_normal_launch():
    assert 'os.environ.get("IBT_ENABLE_POLYGON_OI", "0")' in BRIDGE
    assert "if not oi_attached and POLYGON_OI_ENABLED:" in BRIDGE
    assert 'snapshot["polygon_oi_disabled"] = POLYGON_OI_DISABLED_REASON' in BRIDGE
    assert "IBT_ENABLE_POLYGON_OI=1" not in STARTUP


def test_keyless_free_oi_is_default_structural_lane():
    assert 'os.environ.get("IBT_ENABLE_FREE_OI", "1")' in BRIDGE
    assert "free_oi.load_or_fetch" in BRIDGE
    assert "lse_gamma_map.attach_oi" in BRIDGE


def test_disabled_lane_drops_cached_polygon_overlay_before_publish():
    assert 'snapshot.pop("polygon_oi_overlay", None)' in BRIDGE
    assert 'if snapshot.get("polygon_oi_disabled"):' in (
        ROOT / "scripts" / "lse_gamma_map.py"
    ).read_text(encoding="utf-8")
