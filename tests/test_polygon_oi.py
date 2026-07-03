import datetime as dt
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import polygon_oi as P
import lse_gamma_map as L


class FakePolygon:
    def __init__(self, rows):
        self.rows = rows
        self.urls = []

    def paginate(self, url, max_pages):
        self.urls.append((url, max_pages))
        yield {"results": self.rows}


def prow(expiry, strike, right, oi, iv=.25):
    letter = "C" if right == "call" else "P"
    return {
        "details": {"ticker": f"O:QQQ260814{letter}{int(strike * 1000):08d}",
                    "expiration_date": expiry, "strike_price": strike,
                    "contract_type": right},
        "open_interest": oi, "implied_volatility": iv,
        "greeks": {"gamma": .01, "delta": .25 if right == "call" else -.25},
    }


def test_polygon_fetch_is_explicit_bounded_and_preserves_zero_oi(tmp_path, monkeypatch):
    expiry = "2026-08-14"
    fake = FakePolygon([
        prow(expiry, 80, "put", 0), prow(expiry, 90, "put", 100),
        prow(expiry, 110, "call", 100), prow(expiry, 120, "call", 0),
    ])
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path))
    out = P.fetch("qqq", [expiry], 100, now=1_786_546_860, client=fake)
    assert out["status"] == "OK" and out["expiries"] == [expiry]
    assert out["strike_low"] == 80 and out["strike_high"] == 120
    assert out["coverage"][expiry]["oi_fields"] == 4
    assert any(row["open_interest"] == 0 for row in out["contracts"])
    assert "expiration_date.gte=2026-08-14" in fake.urls[0][0]
    assert "strike_price.gte=80.0" in fake.urls[0][0]


def test_polygon_cache_requires_expiries_freshness_and_sweep_band(tmp_path, monkeypatch):
    expiry = "2026-08-14"
    fake = FakePolygon([
        prow(expiry, 80, "put", 10), prow(expiry, 90, "put", 100),
        prow(expiry, 110, "call", 100), prow(expiry, 120, "call", 10),
    ])
    monkeypatch.setattr(P, "CACHE_DIR", str(tmp_path))
    first = P.load_or_fetch("QQQ", [expiry], 100, now=1000, client=fake)
    second = P.load_or_fetch("QQQ", [expiry], 101, now=1100, client=fake)
    assert first["cache"] == "MISS" and second["cache"] == "HIT"
    assert len(fake.urls) == 1


def test_polygon_oi_structure_produces_real_flip_without_replacing_lse_activity():
    expiry = "2026-08-14"
    contracts = []
    for strike in (80, 85, 90, 95):
        contracts.append({"expiry": expiry, "strike": strike, "right": "put",
                          "open_interest": 1000, "iv": .25})
    for strike in (105, 110, 115, 120):
        contracts.append({"expiry": expiry, "strike": strike, "right": "call",
                          "open_interest": 1000, "iv": .25})
    # Add enough both-side contracts for the explicit quality floor.
    contracts += [
        {"expiry": expiry, "strike": 97, "right": "put", "open_interest": 500, "iv": .27},
        {"expiry": expiry, "strike": 103, "right": "call", "open_interest": 500, "iv": .23},
    ]
    now = dt.datetime(2026, 8, 11, 13, 31, tzinfo=dt.timezone.utc).timestamp()
    snap = {"polygon_oi_overlay": {
        "status": "OK", "fetched_at": now, "fetch_date_et": "2026-08-11",
        "expiries": [expiry], "contracts": contracts,
        "coverage": {expiry: {"contracts": len(contracts), "calls": 5, "puts": 5,
                                "oi_fields": len(contracts)}},
    }}
    out = L._polygon_oi_structure(snap, 100, now)
    assert out["status"] == "OK" and out["net_gex"] is not None
    assert out["flip"] is not None and 80 < out["flip"] < 120
    assert out["source"] == "polygon_options_snapshot"
    assert out["spot_source"] == "lse_realtime"


def test_explicitly_disabled_polygon_never_uses_a_cached_overlay():
    snap = {
        "polygon_oi_disabled": "Polygon OI disabled by default",
        "polygon_oi_overlay": {"status": "OK", "contracts": [
            {"expiry": "2026-08-28", "strike": 100, "right": "call",
             "open_interest": 9999, "iv": .25},
        ]},
    }
    out = L._polygon_oi_structure(snap, 100, 1_787_932_800)
    assert out["status"] == "DATA"
    assert out["source"] == "disabled_polygon"
    assert out["net_gex"] is None and out["flip"] is None
    assert out["why"] == "Polygon OI disabled by default"


def test_squeeze_fuel_combines_oi_call_ladder_with_live_london_velocity():
    expiry = "2026-08-14"
    now = dt.datetime(2026, 8, 13, 15, 0, tzinfo=dt.timezone.utc).timestamp()
    contracts = []
    for strike in (100, 101, 102, 103, 104, 105):
        contracts.append({"expiry": expiry, "strike": strike, "right": "call",
                          "open_interest": 2500, "iv": .30})
    for strike in (95, 96, 97, 98, 99, 100):
        contracts.append({"expiry": expiry, "strike": strike, "right": "put",
                          "open_interest": 250, "iv": .30})
    snap = {"polygon_oi_overlay": {
        "status": "OK", "fetched_at": now, "fetch_date_et": "2026-08-13",
        "expiries": [expiry], "contracts": contracts, "coverage": {},
    }}
    oi = L._polygon_oi_structure(snap, 100, now)
    fuel = L._squeeze_fuel_structure(snap, 100, now, oi)
    assert fuel["status"] == "OK"
    assert fuel["call_convexity_share_pct"] > 55
    assert fuel["ladder"] and fuel["dealer_inventory_confirmed"] is False
    assert fuel["equity_short_interest_status"] == "DATA"

    levels = {"squeeze_fuel": fuel, "flip": None}
    bars = [
        [now - 300, 100, 100, 100, 100, 1],
        [now - 60, 100.1, 100.1, 100.1, 100.1, 1],
        [now, 100.3, 100.3, 100.3, 100.3, 1],
    ]
    L.update_squeeze_fuel(levels, 100.3, bars, now=now)
    assert levels["squeeze_fuel"]["label"] == "ACTIVE"
    assert levels["squeeze_fuel"]["short_covering_confirmed"] is False
    assert levels["squeeze_fuel"]["return_5m_pct"] == 0.3
