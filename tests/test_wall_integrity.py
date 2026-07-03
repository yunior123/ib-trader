import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from wall_integrity import WallIntegrityTracker


def levels(call_mass=100.0, *, flip=100.0):
    return {
        "profile_metric": "gamma_volume", "oi_available": False,
        "chain_ts": 10, "ws_events": int(call_mass),
        "call_wall": 101.0, "call_wall_gex": call_mass,
        "put_wall": 99.0, "put_wall_gex": -80.0,
        "magnet": 100.0, "abs_wall_gex": 90.0,
        "flip": flip, "net_gex": 12.0 if flip is not None else None,
        "activity_flip": 100.25, "activity_flip_strength": 70.0,
        "flip_why": "LSE options chain has no open_interest",
        "profile": [{"strike": 99, "gamma_volume": -80},
                    {"strike": 100, "gamma_volume": 90},
                    {"strike": 101, "gamma_volume": 100}],
    }


def hit_call(tracker, start):
    tracker.on_price(100.80, now=start)
    tracker.on_price(100.96, now=start + 1)
    tracker.on_price(100.80, now=start + 2)


def test_three_distinct_tests_exhaust_wall_bricks():
    tracker = WallIntegrityTracker("QQQ", cooldown_s=5)
    tracker.update_levels(levels(), now=0)
    for start in (10, 20, 30):
        hit_call(tracker, start)
    row = tracker.payload(now=40)["levels"]["call_wall"]
    assert row["hits"] == 3
    assert row["bricks_remaining"] == 0
    assert row["state"] == "EXHAUSTED"
    assert row["metric"] == "gamma_volume"


def test_reinforcement_restores_one_cluster_not_full_wall():
    tracker = WallIntegrityTracker("QQQ", cooldown_s=1)
    tracker.update_levels(levels(), now=0)
    hit_call(tracker, 10)
    before = tracker.payload(now=12)["levels"]["call_wall"]
    assert before["state"] == "TESTED"
    tracker.update_levels(levels(call_mass=120.0), now=20)
    after = tracker.payload(now=20)["levels"]["call_wall"]
    assert after["state"] == "REINFORCED"
    assert after["reinforcements"] == 1
    assert before["bricks_remaining"] < after["bricks_remaining"] <= after["capacity"]


def test_three_prices_beyond_confirm_break():
    tracker = WallIntegrityTracker("QQQ", cooldown_s=1, break_votes=3)
    tracker.update_levels(levels(), now=0)
    tracker.on_price(100.8, now=1)
    tracker.on_price(101.08, now=2)
    tracker.on_price(101.09, now=3)
    tracker.on_price(101.10, now=4)
    row = tracker.payload(now=4)["levels"]["call_wall"]
    assert row["state"] == "BROKEN"
    assert row["bricks_remaining"] == 0


def test_london_flip_is_data_not_animated_fake_level():
    tracker = WallIntegrityTracker("QQQ")
    tracker.update_levels(levels(flip=None), now=0)
    flip = tracker.payload(now=0)["levels"]["flip"]
    assert flip["state"] == "DATA"
    assert flip["level"] is None
    assert flip["capacity"] == 0
    assert "open_interest" in flip["why"]


def test_measured_gamma_flip_uses_same_hit_and_break_state_machine():
    tracker = WallIntegrityTracker("SPY", cooldown_s=1, break_votes=3)
    tracker.update_levels(levels(flip=100.0), now=0)
    tracker.on_price(99.80, now=1)
    tracker.on_price(99.96, now=2)
    assert tracker.payload(now=2)["levels"]["flip"]["hits"] == 1
    tracker.on_price(100.08, now=3)
    tracker.on_price(100.09, now=4)
    tracker.on_price(100.10, now=5)
    flip = tracker.payload(now=5)["levels"]["flip"]
    assert flip["state"] == "BROKEN"
    assert flip["bricks_remaining"] == 0


def test_activity_flip_has_its_own_animated_brick_lane():
    tracker = WallIntegrityTracker("QQQ", cooldown_s=1)
    tracker.update_levels(levels(flip=None), now=0)
    rows = tracker.payload(now=0)["levels"]
    assert rows["flip"]["state"] == "DATA"
    aflip = rows["activity_flip"]
    assert aflip["label"] == "A-FLIP"
    assert aflip["metric"] == "gamma_volume"
    assert aflip["capacity"] >= 6


def test_flip_transitions_from_data_lock_to_live_polygon_oi_lane():
    tracker = WallIntegrityTracker("QQQ")
    tracker.update_levels(levels(flip=None), now=0)
    assert tracker.payload(now=0)["levels"]["flip"]["state"] == "DATA"
    live = levels(flip=100.1)
    live["oi_available"] = True
    live["oi_source"] = "polygon_options_snapshot"
    live["chain_ts"] = 11
    tracker.update_levels(live, now=10)
    flip = tracker.payload(now=10)["levels"]["flip"]
    assert flip["state"] == "FRESH" and flip["level"] == 100.1
    assert flip["metric"] == "dealer_gex"
    assert flip["source_label"] == "Polygon OI × IV · London spot"
    live["ws_events"] += 1
    live["net_gex"] = 15.0
    tracker.update_levels(live, now=11)
    assert tracker.payload(now=11)["levels"]["flip"]["metric"] == "dealer_gex"


def test_visual_contract_has_bricks_and_animated_flip_guard():
    html = open(os.path.join(REPO, "charts", "live.html"), encoding="utf-8").read()
    assert "▦ Ladrillos" in html
    assert "class BrickView" in html
    assert "fillRect(x, yy, bw, bh)" in html
    assert 'push("flip", lv.flip' in html
    assert 'push("activity_flip", lv.activity_flip' in html
    assert 'activity_flip:{ rgb:"255,140,60"' in html
    assert "flip-data" in html
    assert 'id="h-fuel"' in html
    assert 'id="fuelpill"' in html
    assert "🔥 SQUEEZE FUEL" in html
    assert "function renderSqueezeFuel(fuel)" in html
    assert 'renderSqueezeFuel(msg.squeeze_fuel)' in html
    assert "short interest/borrow" in html.lower()
    assert "three_distinct_tests_to_exhaustion" not in html  # backend owns doctrine
