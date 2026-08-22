import datetime as dt
import io
import json
import os
import sys
import urllib.error
import urllib.parse


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


def london_rows(expiry="2026-08-28"):
    rows = []
    for strike in (85, 90, 95, 100, 105, 110, 115):
        for right, cp in (("call", "C"), ("put", "P")):
            rows.append({
                "expiry": expiry, "strike": strike, "contract_type": right,
                "ticker": "TEST%s%s%08d" %
                          (expiry[2:].replace("-", ""), cp, strike * 1000),
                "iv": .25,
            })
    return {expiry: rows}


def databento_opener(calls, expiry="2026-08-28"):
    stamp = expiry[2:].replace("-", "")
    header = ("ts_recv,ts_event,rtype,publisher_id,instrument_id,ts_ref,price,"
              "quantity,sequence,ts_in_delta,stat_type,channel_id,update_action,"
              "stat_flags,symbol\n")
    lines = []
    seq = 1
    for strike in (85, 90, 95, 100, 105, 110, 115):
        for cp in ("C", "P"):
            symbol = "TEST  %s%s%08d" % (stamp, cp, strike * 1000)
            # Duplicate publishers are expected; the final row must win.
            for publisher, oi in ((61, 111), (23, 222)):
                lines.append(("2026-08-28T10:30:00Z,2026-08-28T10:30:00Z,24,%d,1,,"
                              "9223372036854775807,%d,%d,0,9,61,1,0,%s\n") %
                             (publisher, oi, seq, symbol))
                seq += 1
    csv_body = (header + "".join(lines)).encode()

    def opener(request, timeout):
        calls.append((request.full_url, request.data, timeout,
                      dict(request.header_items())))
        if "metadata.get_cost" in request.full_url:
            return Response(b"0.0042")
        assert "timeseries.get_range" in request.full_url
        return Response(csv_body)
    return opener


def test_databento_fallback_is_exact_quoted_and_deduplicated(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    now = dt.datetime(2026, 8, 28, 15, tzinfo=dt.timezone.utc).timestamp()
    calls = []
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(F, "_secret", lambda name: "db-test-key")

    def nasdaq_down(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    out = F.fetch(
        "TEST", [expiry], 100, now=now, opener=nasdaq_down,
        london_rows=london_rows(expiry), databento_opener=databento_opener(calls, expiry))
    assert out["source"] == "databento_opra_statistics"
    assert out["quoted_cost_usd"] == .0042
    assert out["requested_contracts"] == 14
    assert len(out["contracts"]) == 14
    assert all(row["open_interest"] == 222 for row in out["contracts"])
    assert all(row["oi_date"] == "2026-08-28" for row in out["contracts"])
    assert len(calls) == 2
    quote_query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0][0]).query)
    assert quote_query["schema"] == ["statistics"]
    assert len(quote_query["symbols"][0].split(",")) == 14
    assert "Authorization" in calls[0][3]


def test_databento_cost_cap_stops_download(monkeypatch):
    expiry = "2026-08-28"
    calls = []
    monkeypatch.setattr(F, "_secret", lambda name: "db-test-key")

    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(b"0.050001")

    try:
        F.fetch_databento("TEST", [expiry], 100, london_rows(expiry),
                          now=1_788_000_000, opener=opener)
    except F.FreeOIError as exc:
        assert "hard cap" in str(exc)
    else:
        assert False, "expected hard-cap failure"
    assert len(calls) == 1 and "metadata.get_cost" in calls[0]


# ---------------------------------------------------------------- delay + ordering
IN_SESSION = dt.datetime(2026, 8, 21, 15, 0, tzinfo=F.ET).timestamp()   # Fri 15:00 ET
AFTER_HOURS = dt.datetime(2026, 8, 21, 18, 0, tzinfo=F.ET).timestamp()  # Fri 18:00 ET


def cboe_body(expiry="2026-08-28", last_trade_time="2026-08-21T14:45:00"):
    stamp = expiry[2:].replace("-", "")
    options = []
    for strike in (85, 90, 95, 100, 105, 110, 115):
        for cp, oi in (("C", 1000), ("P", 900)):
            options.append({
                "option": "TEST%s%s%08d" % (stamp, cp, strike * 1000),
                "open_interest": oi, "iv": .31, "gamma": .01, "volume": 5,
            })
    # Delayed IV/greeks are present but discarded; only OI crosses into the book.
    return {"timestamp": "2026-08-21 19:00:00", "symbol": "TEST", "data": {
        "current_price": 100.0, "last_trade_time": last_trade_time,
        "options": options,
    }}


def cboe_opener_for(body, calls):
    raw = json.dumps(body).encode()

    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(raw)
    return opener


def broken(*_args, **_kwargs):
    raise urllib.error.URLError("offline")


def test_provider_order_is_cost_then_reliability(monkeypatch):
    monkeypatch.delenv("IBT_FREE_OI_PROVIDERS", raising=False)
    assert F.providers() == ["nasdaq", "cboe", "tradier", "databento"]
    monkeypatch.setenv("IBT_FREE_OI_PROVIDERS", "cboe, nasdaq")
    assert F.providers() == ["cboe", "nasdaq"]


def test_unknown_provider_fails_closed_instead_of_silently_dropping(monkeypatch):
    monkeypatch.setenv("IBT_FREE_OI_PROVIDERS", "yfinance")
    try:
        F.providers()
    except F.FreeOIError as exc:
        assert "yfinance" in str(exc)
    else:
        assert False, "expected an unknown-provider failure"


def test_cboe_takes_over_when_nasdaq_fails_and_keeps_the_reason(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    monkeypatch.delenv("IBT_FREE_OI_PROVIDERS", raising=False)
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    urls = []
    out = F.fetch("TEST", [expiry], 100, now=IN_SESSION, opener=broken,
                  cboe_opener=cboe_opener_for(cboe_body(expiry), urls))
    assert out["source"] == "cboe_delayed_chain"
    assert out["provider_order"] == ["nasdaq", "cboe", "tradier", "databento"]
    assert out["provider_errors"] and out["provider_errors"][0].startswith("nasdaq:")
    assert len(out["contracts"]) == 14
    # CBOE serves IV and greeks, but they are delayed: London still supplies IV.
    assert all(row["iv"] is None for row in out["contracts"])
    assert urls and "cdn.cboe.com" in urls[0] and "apikey" not in urls[0].lower()


def test_cboe_measures_its_delay_in_session_and_refuses_to_invent_one_after(tmp_path,
                                                                           monkeypatch):
    expiry = "2026-08-28"
    monkeypatch.delenv("IBT_FREE_OI_PROVIDERS", raising=False)
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    body = cboe_body(expiry, "2026-08-21T14:45:00")
    live = F.fetch_cboe("TEST", [expiry], 100, now=IN_SESSION,
                        opener=cboe_opener_for(body, []))
    assert live["structural_delay_minutes"] == 15.0
    assert live["structural_delay_basis"] == "measured_in_session"

    closed = F.fetch_cboe("TEST", [expiry], 100, now=AFTER_HOURS,
                          opener=cboe_opener_for(body, []))
    # Fail loud: unknown stays None, never 0/0.0/15 "because it usually is".
    assert closed["structural_delay_minutes"] is None
    assert closed["structural_delay_basis"] == "not_measurable_outside_rth"
    assert closed["observed_quote_lag_minutes"] == 195.0


def test_every_structural_payload_declares_itself_delayed(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(F, "_secret", lambda name: "db-test-key")
    books = [
        F._parse("TEST", payload(expiry), "stocks", [expiry], 100, IN_SESSION),
        F.fetch_cboe("TEST", [expiry], 100, now=IN_SESSION,
                     opener=cboe_opener_for(cboe_body(expiry), [])),
        F.fetch_databento("TEST", [expiry], 100, london_rows(expiry),
                          now=dt.datetime(2026, 8, 28, 15,
                                          tzinfo=dt.timezone.utc).timestamp(),
                          opener=databento_opener([], expiry)),
    ]
    for book in books:
        assert book["realtime"] is False, book["source"]
        assert book["delay_policy"] == "structural_only_never_fires_an_order"
        assert book["structural_delay_basis"]
        delay = book["structural_delay_minutes"]
        assert delay is None or delay > 0, book["source"]


def test_attach_oi_refuses_a_provider_that_claims_realtime():
    expiry = "2026-08-28"
    book = F._parse("TEST", payload(expiry), "stocks", [expiry], 100, IN_SESSION)
    book["realtime"] = True
    snap = {"rows_by_expiry": {}}
    assert L.attach_oi(snap, book) is False
    assert "did not declare realtime=false" in snap["oi_overlay_error"]
    assert "oi_overlay" not in snap


def test_fetch_refuses_a_lane_that_does_not_declare_a_delay(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    monkeypatch.delenv("IBT_FREE_OI_PROVIDERS", raising=False)
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))

    real_cboe = F.fetch_cboe

    def liar(sym, expiries, spot, *, now=None, opener=None):
        book = real_cboe(sym, expiries, spot, now=now,
                         opener=cboe_opener_for(cboe_body(expiries[0]), []))
        book.pop("realtime")
        return book

    monkeypatch.setattr(F, "fetch_cboe", liar)
    try:
        F.fetch("TEST", [expiry], 100, now=IN_SESSION, opener=broken)
    except F.FreeOIError as exc:
        assert "did not declare itself delayed" in str(exc)
    else:
        assert False, "expected the undeclared lane to be refused"


def test_delay_reaches_levels_and_health_fields():
    expiry = "2026-08-28"
    book = F.fetch_cboe("TEST", [expiry], 100, now=IN_SESSION,
                        opener=cboe_opener_for(cboe_body(expiry), []))
    lse_rows = [{"strike": row["strike"], "contract_type": row["right"],
                 "iv": .28, "volume_today": 10} for row in book["contracts"]]
    snap = {"rows_by_expiry": {expiry: lse_rows}}
    assert L.attach_oi(snap, book)
    out = L._polygon_oi_structure(snap, 100, IN_SESSION)
    assert out["status"] == "OK" and out["source"] == "cboe_delayed_chain"
    assert out["realtime"] is False
    assert out["structural_delay_minutes"] == 15.0
    assert out["structural_delay_basis"] == "measured_in_session"


def test_structure_without_a_provider_reports_no_delay_number():
    out = L._polygon_oi_structure({"rows_by_expiry": {}}, 100, IN_SESSION)
    assert out["status"] == "DATA"
    assert out["realtime"] is False
    assert out["structural_delay_minutes"] is None
    assert out["structural_delay_basis"] == "no_structural_provider"


def tradier_body(expiry="2026-08-28", trade_date_ms=None):
    if trade_date_ms is None:
        trade_date_ms = int((IN_SESSION - 900) * 1000)
    rows = []
    for strike in (85, 90, 95, 100, 105, 110, 115):
        for right, oi in (("call", 1000), ("put", 900)):
            rows.append({"symbol": "TEST", "strike": strike, "option_type": right,
                         "open_interest": oi, "trade_date": trade_date_ms,
                         "greeks": {"mid_iv": .3}})
    return {"options": {"option": rows}}


def test_tradier_lane_without_a_token_fails_loud(monkeypatch):
    monkeypatch.setattr(F, "_secret", lambda name: None)
    try:
        F.fetch_tradier("TEST", ["2026-08-28"], 100, now=IN_SESSION, opener=broken)
    except F.FreeOIError as exc:
        assert "TRADIER_TOKEN" in str(exc)
    else:
        assert False, "expected the missing-token failure"


def test_tradier_chain_yields_oi_and_a_measured_delay(monkeypatch):
    expiry = "2026-08-28"
    monkeypatch.setattr(F, "_secret", lambda name: "tradier-test-token")
    calls = []
    raw = json.dumps(tradier_body(expiry)).encode()

    def opener(request, timeout):
        calls.append((request.full_url, dict(request.header_items())))
        return Response(raw)

    out = F.fetch_tradier("TEST", [expiry], 100, now=IN_SESSION, opener=opener)
    assert out["source"] == "tradier"
    assert len(out["contracts"]) == 14
    assert out["structural_delay_minutes"] == 15.0
    assert out["structural_delay_basis"] == "measured_in_session"
    assert "sandbox.tradier.com" in calls[0][0]
    assert calls[0][1]["Authorization"].startswith("Bearer ")


def test_cache_written_before_the_delay_fields_is_refetched(tmp_path, monkeypatch):
    expiry = "2026-08-28"
    monkeypatch.delenv("IBT_FREE_OI_PROVIDERS", raising=False)
    monkeypatch.setattr(F, "CACHE_DIR", str(tmp_path))
    calls = []
    opener = opener_for(payload(expiry), calls)
    F.load_or_fetch("TEST", [expiry], 100, now=IN_SESSION, opener=opener)
    stale = json.load(open(F._cache_path("TEST"), encoding="utf-8"))
    for field in ("realtime", "structural_delay_minutes", "structural_delay_basis"):
        stale.pop(field, None)
    F._atomic_write(F._cache_path("TEST"), stale)
    again = F.load_or_fetch("TEST", [expiry], 100, now=IN_SESSION + 60, opener=opener)
    assert again["cache"] == "MISS" and len(calls) == 2
    assert again["realtime"] is False
