import datetime as dt
import io
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import free_oi as F
import lse_gamma_map as L


def payload(expiry="2026-08-28"):
    stamp = expiry[2:].replace("-", "")
    rows = []
    for strike in (85, 90, 95, 100, 105, 110, 115):
        rows.append({
            "expiryDate": "Aug 28", "strike": "%.2f" % strike,
            "c_Openinterest": "1,000", "p_Openinterest": "900",
            "drillDownURL": ("/market-activity/stocks/test/option-chain/"
                             "call-put-options/test--%sc%08d" %
                             (stamp, strike * 1000)),
        })
    # Missing is unknown, not zero: this leg must not enter the contract list.
    rows[0]["p_Openinterest"] = "--"
    return {"status": {"rCode": 200}, "data": {
        "lastTrade": "LAST TRADE: $100 (AS OF AUG 21, 2026 3:12 PM ET)",
        "table": {"rows": rows},
    }}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def opener_for(body, calls):
    raw = json.dumps(body).encode()

    def opener(request, timeout):
        calls.append((request.full_url, timeout, dict(request.header_items())))
        return Response(raw)
    return opener


def test_keyless_nasdaq_fetch_is_bounded_and_preserves_unknown_oi(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    calls = []
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    out = F.fetch("test", [expiry], 100, now=1_787_932_800,
                  opener=opener_for(payload(expiry), calls))
    assert out["status"] == "OK"
    assert out["source"] == "nasdaq_public_option_chain"
    assert out["strike_low"] == 80 and out["strike_high"] == 120
    assert out["coverage"][expiry]["put_oi_unknown"] == 1
    assert len(out["contracts"]) == 13
    assert all(row["open_interest"] is not None for row in out["contracts"])
    assert "api.nasdaq.com/api/quote/TEST/option-chain" in calls[0][0]
    assert "apikey" not in calls[0][0].lower()


def test_cache_requires_expiry_freshness_and_sweep_band(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    calls = []
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    opener = opener_for(payload(expiry), calls)
    first = F.load_or_fetch("TEST", [expiry], 100, now=1000, opener=opener)
    second = F.load_or_fetch("TEST", [expiry], 101, now=1100, opener=opener)
    assert first["cache"] == "MISS" and second["cache"] == "HIT"
    assert len(calls) == 1


def test_free_oi_joins_matching_london_iv_and_builds_gex():
    expiry = "2026-08-28"
    now = dt.datetime(2026, 8, 21, 15, 0, tzinfo=dt.timezone.utc).timestamp()
    book = F._parse("TEST", payload(expiry), "stocks", [expiry], 100, now)
    lse_rows = []
    for row in book["contracts"]:
        lse_rows.append({"strike": row["strike"], "contract_type": row["right"],
                         "iv": .28, "volume_today": 10})
    snap = {"rows_by_expiry": {expiry: lse_rows}}
    assert L.attach_oi(snap, book)
    out = L._polygon_oi_structure(snap, 100, now)
    assert out["status"] == "OK" and out["net_gex"] is not None
    assert out["source"] == "nasdaq_public_option_chain"
    assert out["contracts_usable"] == len(book["contracts"])
    assert "matching London IV" in out["flip_method"]


def test_missing_matching_london_iv_fails_data_instead_of_inventing_it():
    expiry = "2026-08-28"
    now = dt.datetime(2026, 8, 21, 15, 0, tzinfo=dt.timezone.utc).timestamp()
    book = F._parse("TEST", payload(expiry), "stocks", [expiry], 100, now)
    snap = {"rows_by_expiry": {expiry: []}, "oi_overlay": book}
    out = L._polygon_oi_structure(snap, 100, now)
    assert out["status"] == "DATA"
    assert out["contracts_usable"] == 0
    assert out["net_gex"] is None and out["flip"] is None
