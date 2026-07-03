import datetime as dt
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import lse_gamma_map as M
import architect_lse as A


class FakeLSE:
    def __init__(self, by_expiry):
        self.by_expiry = by_expiry
        self.calls = []

    def options_chain(self, sym, expiry, limit):
        self.calls.append((sym, expiry, limit))
        return self.by_expiry.get(expiry, [])


def row(strike, right, gamma, volume, when="2026-08-11T13:30:00Z", **extra):
    return {"strike": strike, "contract_type": right, "gamma": gamma,
            "volume_today": volume, "last_trade_at": when, **extra}


def test_london_map_is_gamma_volume_and_never_claims_gex_or_flip():
    today = dt.date(2026, 8, 11)
    ex1, ex2 = today.isoformat(), "2026-08-14"
    fake = FakeLSE({
        ex1: [row(720, "call", .01, 100, delta=.55, iv=.30),
              row(715, "put", .02, 80, delta=-.45, iv=.32)],
        ex2: [row(725, "call", .015, 50, delta=.40, iv=.28),
              row(710, "put", .01, 40, delta=-.35, iv=.31)],
    })
    now = dt.datetime(2026, 8, 11, 13, 31, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, expiries = M.build("qqq", 722, [ex1, ex2], client=fake, now=now)
    assert heat["src"] == "lse" and heat["metric"] == "gamma_volume"
    assert heat["oi_available"] is False and "sin open interest" in heat["note"]
    assert levels["net_gex"] is None and levels["flip"] is None
    assert levels["squeeze_fuel"]["status"] == "DATA"
    assert levels["squeeze_fuel"]["short_covering_confirmed"] is False
    assert "open_interest" in levels["flip_why"]
    assert levels["call_wall"] == 725 and levels["put_wall"] == 715
    assert levels["magnet"] == 715 and heat["magnet"] == 715
    assert levels["refresh"]["heatmap"] == int(now + M.REFRESH_S)
    assert levels["refresh"]["gamma_flip"] == int(now + M.REFRESH_S)
    assert expiries == [ex1, ex2]
    assert levels["exp"] == "20260811"
    assert levels["dte"] is not None
    assert heat["architect"]["option_source_ts"] is not None
    assert heat["architect"]["raw"]["delta_volume_gross"] >= 0
    assert heat["mm_fractal"]["src"] == "lse"
    assert heat["mm_fractal"]["proprietary_replication"] is False
    assert heat["mm_fractal"]["active_lane"] == "OMM"
    assert levels["mm_fractal"] == heat["mm_fractal"]
    assert levels["dealer_activity_daily"]["expiry"] == ex1
    assert levels["dealer_activity_weekly"]["expiry"] == ex2
    assert levels["mm_top_profit_daily"]["expiry"] == ex1
    assert levels["mm_top_profit_weekly"]["expiry"] == ex2
    assert heat["daily_activity"]["horizon"] == "daily nearest-active"
    assert heat["weekly_activity"]["horizon"] == "weekly Friday"
    assert levels["weekly_dealer_activity"]["expiry"] == ex2
    assert levels["weekly_dealer_activity"]["level"] == 716.7826
    assert levels["weekly_dealer_activity"]["proprietary_replication"] is False
    # Both observed strikes have zero terminal payout in this sparse two-contract
    # example; the deterministic tie-break picks the candidate nearest spot.
    assert levels["mm_top_profit"]["level"] == 725
    assert levels["mm_top_profit"]["proprietary_replication"] is False


def test_expiry_discovery_skips_weekends_and_stops_after_three_nonempty():
    got = M.candidate_expiries(dt.date(2026, 8, 14), days=5)
    assert got == ["2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19"]


def test_fetch_priority_guarantees_next_friday_without_expanding_three_slots():
    today = dt.date(2026, 8, 12)  # Wednesday
    fake = FakeLSE({
        "2026-08-12": [row(100, "call", .01, 1)],
        "2026-08-13": [row(100, "call", .01, 1)],
        "2026-08-14": [row(100, "call", .01, 1)],
        "2026-08-17": [row(100, "call", .01, 1)],
    })
    got = M._fetch_expiries(fake, "QQQ", ["2026-08-12", "2026-08-13", "2026-08-17"], today)
    assert list(got) == ["2026-08-12", "2026-08-14", "2026-08-13"]
    assert len(got) == M.MAX_EXPIRIES == 3


def test_expired_0dte_is_rolled_out_at_1600_et():
    today = dt.date(2026, 8, 11)
    expired, live = today.isoformat(), "2026-08-12"
    fake = FakeLSE({
        expired: [row(100, "call", 9, 9999, when="2026-08-10T20:00:00Z")],
        live: [row(105, "call", .01, 10, when="2026-08-11T20:00:00Z", delta=.25, iv=.2),
               row(95, "put", .01, 10, when="2026-08-11T20:00:00Z", delta=-.25, iv=.22)],
    })
    now = dt.datetime(2026, 8, 11, 20, 1, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, expiries = M.build("qqq", 100, [expired, live], client=fake, now=now)
    assert expired not in expiries
    assert expired not in heat["session_dates"]
    assert all(call[1] != expired for call in fake.calls)
    assert levels["magnet"] in (95, 105)


def test_walls_stay_on_their_side_and_architect_activity_is_not_dealer_gex():
    today = dt.date(2026, 8, 11)
    expiry = "2026-08-14"
    fake = FakeLSE({expiry: [
        row(95, "call", .03, 900, delta=.7, iv=.30, dte=3, premium_today=90000),
        row(105, "call", .01, 100, delta=.25, iv=.40, dte=3, premium_today=10000),
        row(95, "put", .01, 100, delta=-.25, iv=.20, dte=3, premium_today=5000),
        row(105, "put", .04, 1000, delta=-.7, iv=.28, dte=3, premium_today=50000),
    ]})
    now = dt.datetime(2026, 8, 11, 13, 31, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, _ = M.build("qqq", 100, [expiry], client=fake, now=now)
    assert levels["call_wall"] == 105
    assert levels["put_wall"] == 95
    assert levels["magnet"] == 105
    arch = heat["architect"]
    assert arch["dealer_gex_available"] is False
    assert arch["validation"] == "UNPROVEN_DESCRIPTIVE_SIGNAL_ONLY"
    assert arch["expiries"][0]["rr25"]["rr25_vol_points"] == 20.0
    assert arch["activity_score"] is not None


def test_old_per_contract_snapshot_is_not_mixed_into_latest_session():
    today = dt.date(2026, 8, 11)
    expiry = "2026-08-14"
    fake = FakeLSE({expiry: [
        row(100, "call", 9, 9999, when="2026-07-29T20:00:00Z", delta=.5, iv=.9,
            dte=16, premium_today=999999),
        row(105, "call", .01, 10, when="2026-08-10T20:00:00Z", delta=.25, iv=.2,
            dte=4, premium_today=1000),
        row(95, "put", .01, 10, when="2026-08-10T20:00:00Z", delta=-.25, iv=.22,
            dte=4, premium_today=1000),
    ]})
    now = dt.datetime(2026, 8, 11, 13, 31, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, _ = M.build("qqq", 100, [expiry], client=fake, now=now)
    assert heat["stale_session_rows_dropped"] == 1
    assert heat["contracts_used"] == 2
    assert 100 not in heat["strikes"]
    assert levels["magnet"] in (95, 105)


def test_whole_stale_expiry_is_excluded_when_another_expiry_has_current_session():
    stale, fresh = "2026-08-12", "2026-08-14"
    fake = FakeLSE({
        stale: [row(98, "put", .50, 10000, when="2026-08-11T19:55:00Z",
                    delta=-.5, iv=.3, ticker="QQQ260812P00098000")],
        fresh: [row(105, "call", .01, 100, when="2026-08-12T15:00:00Z",
                    delta=.3, iv=.2, ticker="QQQ260814C00105000"),
                row(100, "put", .02, 100, when="2026-08-12T15:00:01Z",
                    delta=-.3, iv=.25, ticker="QQQ260814P00100000")],
    })
    now = dt.datetime(2026, 8, 12, 15, 1, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, expiries = M.build("qqq", 102, [stale, fresh], client=fake, now=now)
    assert expiries == [fresh]
    assert levels["put_wall"] == 100
    assert heat["active_session_date"] == "2026-08-12"
    assert heat["excluded_expiries"][stale]["session_date"] == "2026-08-11"


def test_websocket_option_print_updates_cached_volume_and_refits_without_rest():
    expiry = "2026-08-14"
    fake = FakeLSE({expiry: [
        row(105, "call", .01, 10, when="2026-08-12T15:00:00Z",
            delta=.3, iv=.2, last_price=2.0, ticker="QQQ260814C00105000"),
        row(100, "put", .02, 100, when="2026-08-12T15:00:00Z",
            delta=-.3, iv=.25, ticker="QQQ260814P00100000"),
    ]})
    now = dt.datetime(2026, 8, 12, 15, 1, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, expiries, snap = M.build(
        "qqq", 102, [expiry], client=fake, now=now, return_snapshot=True)
    calls_before = levels["call_profile"][0]["gamma_volume"]
    assert M.apply_option_tick(snap, "QQQ", {
        "type": "tick", "symbol": "QQQ260814C00105000", "price": 2.5,
        "volume": 200, "ts": "2026-08-12T15:01:10Z"})
    heat2, levels2, _ = M.build("qqq", 102, expiries, now=now + 11, snapshot=snap)
    assert levels2["call_profile"][0]["gamma_volume"] > calls_before
    assert heat2["ws_events"] == 1
    assert heat2["source_ts"] == int(dt.datetime(
        2026, 8, 12, 15, 1, 10, tzinfo=dt.timezone.utc).timestamp())
    assert heat2["next_refresh_ts"] == heat["next_refresh_ts"]
    assert levels2["option_tape"]["prints"] == 1
    assert levels2["option_tape"]["reversal_triad_eligible"] is False
    assert levels2["option_tape"]["tick_rule_prints"] == 1


def test_quote_and_tick_rule_are_forward_audit_not_bid_ask_truth():
    expiry = "2026-08-14"
    fake = FakeLSE({expiry: [
        row(105, "call", .01, 10, when="2026-08-12T15:00:00Z",
            delta=.3, iv=.2, last_price=2.0, ticker="QQQ260814C00105000"),
        row(95, "put", .01, 10, when="2026-08-12T15:00:00Z",
            delta=-.3, iv=.2, last_price=2.0, ticker="QQQ260814P00095000"),
    ]})
    now = dt.datetime(2026, 8, 12, 15, 1, tzinfo=dt.timezone.utc).timestamp()
    _, _, expiries, snap = M.build(
        "QQQ", 100, [expiry], client=fake, now=now, return_snapshot=True)
    assert M.apply_option_tick(snap, "QQQ", {
        "symbol": "QQQ260814C00105000", "price": 2.1, "bid": 2.0,
        "ask": 2.1, "volume": 3, "ts": "2026-08-12T15:01:10Z"})
    assert M.apply_option_tick(snap, "QQQ", {
        "symbol": "QQQ260814P00095000", "price": 1.9,
        "volume": 2, "ts": "2026-08-12T15:01:11Z"})
    _, levels, _ = M.build("QQQ", 100, expiries, now=now + 12, snapshot=snap)
    tape = levels["option_tape"]
    assert tape["prints"] == 2 and tape["quote_rule_prints"] == 1
    assert tape["tick_rule_prints"] == 1 and tape["classified_pct"] == 100.0
    assert tape["reversal_triad_eligible"] is False
    assert "not Bid×Ask footprint" in tape["guard"]


def test_activity_flip_is_repriced_gamma_volume_and_real_flip_stays_locked():
    expiry = "2026-08-14"
    fake = FakeLSE({expiry: [
        row(95, "put", .01, 1000, delta=-.25, iv=.25,
            ticker="QQQ260814P00095000"),
        row(105, "call", .01, 1000, delta=.25, iv=.25,
            ticker="QQQ260814C00105000"),
    ]})
    now = dt.datetime(2026, 8, 11, 13, 31, tzinfo=dt.timezone.utc).timestamp()
    heat, levels, _ = M.build("QQQ", 100, [expiry], client=fake, now=now)
    assert levels["flip"] is None and "open_interest" in levels["flip_why"]
    assert 95 < levels["activity_flip"] < 105
    detail = levels["activity_flip_detail"]
    assert detail["status"] == "OK" and detail["dealer_gamma_flip"] is False
    assert detail["metric"] == "gamma_volume"
    assert heat["activity_flip"]["level"] == levels["activity_flip"]


def test_wall_side_reprices_when_live_spot_crosses_cached_strike():
    levels = {
        "spot": 100, "call_wall": 105, "put_wall": 95,
        "call_profile": [{"strike": 100, "gamma_volume": 500},
                         {"strike": 105, "gamma_volume": 100}],
        "put_profile": [{"strike": 95, "gamma_volume": 100},
                        {"strike": 105, "gamma_volume": 500}],
    }
    assert not M.reprice_levels(levels, 101)
    assert levels["call_wall"] == 105 and levels["put_wall"] == 95
    assert M.reprice_levels(levels, 106)
    assert levels["call_wall"] is None and levels["put_wall"] == 105


def test_lse_reversal_triad_never_fakes_bid_ask_order_flow():
    now = dt.datetime(2026, 8, 11, 14, 0, tzinfo=dt.timezone.utc).timestamp()
    current = {"spot": 99.5, "activity_score": 40,
               "source_session_dates": {"2026-08-14": "2026-08-11"},
               "raw": {"delta_volume_net": 100, "delta_volume_gross": 200}}
    bars = [[int(now) - 120, 99, 101, 98.5, 99.5, 1000]]
    triad = A.reversal_triad(current, None, bars,
                             {"spot": 99.5, "call_wall": 100, "put_wall": 95,
                              "magnet": 100}, now)
    assert triad["label"] == "DATA"
    assert triad["value_context"]["state"] == "CONFIRMED"
    assert triad["value_context"]["direction"] == "BEARISH"
    assert triad["available"] == 0
    assert all(not component["available"] for component in triad["components"].values())
    assert triad["architect_options_context"]["counts_toward_triad"] is False


def test_london_wall_and_magnet_colors_stay_unchanged():
    html = open(os.path.join(REPO, "charts", "live.html"), encoding="utf-8").read()
    assert 'rgba(38,166,154,0.72)' in html   # Call Wall: verde-azulado
    assert 'rgba(239,83,80,0.72)' in html    # Put Wall: rojo
    assert 'rgba(255,179,0,0.72)' in html    # Magnet: dorado
    assert 'rgba(255,140,60,0.86)' in html   # Activity flip: naranja, aditivo


def test_weekly_activity_rejects_linearized_level_outside_observed_strikes():
    expiry = "2026-08-14"
    rows = {expiry: [
        row(99, "call", .0001, 1000, delta=.95),
        row(101, "put", .0001, 1, delta=-.05),
    ]}
    now = dt.datetime(2026, 8, 11, 14, 0, tzinfo=dt.timezone.utc).timestamp()
    out = M._weekly_activity_structure(rows, 100, now, now, now + 300)
    assert out["status"] == "DATA"
    assert out["level"] is None
    assert out["raw_level"] < 99
    assert "outside observed weekly Friday strike range" in out["why"]
    assert out["top_profit_level"] in (99, 101)


def test_weekly_neutral_uses_the_underlying_recorded_with_each_greek():
    expiry = "2026-08-14"
    rows = {expiry: [
        row(95, "call", .02, 100, delta=.10, underlying_price=98),
        row(105, "put", .01, 100, delta=-.05, underlying_price=102),
    ]}
    out = M._weekly_activity_structure(rows, 150, 1, 1, 301)
    # Sref=(200*98 + 100*102)/300=99.3333; net delta=500; gamma=300.
    assert out["gamma_weighted_reference_spot"] == 99.3333
    assert out["level"] == 97.6667
    assert out["raw_level"] != 150 - 500 / 300


def test_new_london_proxies_are_optional_chart_indicators_with_disclosure():
    html = open(os.path.join(REPO, "charts", "live.html"), encoding="utf-8").read()
    assert 'dealer_net_daily:false' in html and 'dealer_net_weekly:false' in html
    assert 'mm_top_profit_daily:false' in html and 'mm_top_profit_weekly:false' in html
    assert 'indPanel_dailyWeeklyProxies_v1' in html
    assert 'LSE DN·D VOL' in html and 'LSE DN·W VOL' in html
    assert 'LSE MM$·D VOL' in html and 'LSE MM$·W VOL' in html
    assert 'No es Net Dealer ni inventario market-maker' in html
    assert 'No es PML propietario ni max pain por OI' in html


def test_milk_proxy_forward_archive_preserves_source_and_disclosure(tmp_path):
    now = dt.datetime(2026, 8, 12, 14, 0, tzinfo=dt.timezone.utc).timestamp()
    levels = {"asof": now, "spot": 724.0, "chain_ts": now - 10,
              "dealer_activity_daily": {"level": 719, "expiry": "2026-08-12"},
              "dealer_activity_weekly": {"level": 718, "expiry": "2026-08-14"},
              "mm_top_profit_daily": {"level": 721, "expiry": "2026-08-12"},
              "mm_top_profit_weekly": {"level": 720, "expiry": "2026-08-14"}}
    path = M.append_proxy_history(str(tmp_path), "qqq", levels)
    got = __import__("json").loads(open(path, encoding="utf-8").readline())
    assert got["src"] == "lse" and got["option_source_ts"] == now - 10
    assert got["proprietary_replication"] is False
    assert got["validation"] == "UNPROVEN_FORWARD_OOS_AUDIT_ONLY"
    assert got["dealer_activity_daily"]["expiry"] == "2026-08-12"
    assert got["dealer_activity_weekly"]["expiry"] == "2026-08-14"


def test_omm_is_frozen_and_dmm_appears_after_0945(tmp_path):
    state = tmp_path / "mm.json"
    pre = dt.datetime(2026, 8, 11, 13, 40, tzinfo=dt.timezone.utc).timestamp()
    snap_pre = M._mm_snapshot(
        "QQQ", 101, {100: 10, 105: 20}, {95: 30, 100: 5},
        {100: 40, 105: 10}, {95: 20, 100: 30}, pre, "2026-08-11", pre)
    omm = M._mm_fractal_state("QQQ", snap_pre, pre, int(pre + 300), str(state))
    assert omm["active_lane"] == "OMM" and omm["omm_pivot"] is not None
    frozen = omm["omm_pivot"]

    post = dt.datetime(2026, 8, 11, 14, 0, tzinfo=dt.timezone.utc).timestamp()
    snap_post = M._mm_snapshot(
        "QQQ", 103, {100: 4, 105: 50}, {95: 4, 100: 10},
        {100: 10, 105: 90}, {95: 5, 100: 20}, post, "2026-08-11", post)
    dmm = M._mm_fractal_state("QQQ", snap_post, post, int(post + 300), str(state))
    assert dmm["active_lane"] == "DMM"
    assert dmm["omm_pivot"] == frozen
    assert dmm["dmm_magnet"] is not None
    assert dmm["validation"] == "UNPROVEN_LSE_PROXY_CONTEXT_ONLY"


def test_mm_widget_is_lse_only_and_discloses_proxy():
    html = open(os.path.join(REPO, "charts", "live.html"), encoding="utf-8").read()
    js = open(os.path.join(REPO, "charts", "mm_fractal_widget.js"), encoding="utf-8").read()
    assert 'id="wgt-mmfractal"' in html and "mm_fractal_widget.js?v=23-lse-only" in html
    assert 'd.src!=="lse"' in js
    assert "no fórmula propietaria" in js
    assert "next_refresh_ts" in js
