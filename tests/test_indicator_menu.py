from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "charts" / "live.html").read_text()


def test_vwap_is_an_optional_indicator_and_defaults_off():
    assert "vwap:false" in HTML
    assert '{ k:"vwap",        n:"VWAP"' in HTML
    assert 'setVis([S.vwap], indOn("vwap"));' in HTML


def test_vwap_series_is_populated_by_history_and_incremental_frames():
    assert "S.vwap.setData(ind.vwap);" in HTML
    assert "upd(S.vwap, ind.vwap);" in HTML


def test_rsi_and_divergence_are_independent_optional_indicators():
    assert "rsi:false" in HTML and "rsi_divergence:false" in HTML
    assert '{ k:"rsi",         n:"RSI (14)"' in HTML
    assert '{ k:"rsi_divergence", n:"RSI Divergence (5−14)"' in HTML
    assert 'setVis([rsiLine, rsi70, rsi30], indOn("rsi"));' in HTML
    assert 'setVis([rsiDivLine, rsiDivZero], indOn("rsi_divergence"));' in HTML
    assert 'if (k === "rsi_divergence" && !rsiDivLine)' in HTML


def test_rsi_pane_only_appears_when_selected():
    assert 'if (k === "rsi" && !rsiLine)' in HTML
    assert 'if (indOn(k)) ensureOptionalPane(k); else removeOptionalPane(k);' in HTML
    assert "chart.removeSeries(s)" in HTML
    assert "rsiLine.setData(ind.rsi || []);" in HTML
    assert "upd(rsiLine, ind.rsi);" in HTML
    assert "rsiDivLine.setData(ind.rsiDivergence || []);" in HTML
    assert "upd(rsiDivLine, ind.rsiDivergence);" in HTML


def test_no_empty_optional_panes_are_created_at_boot():
    assert "let volS = null" in HTML
    assert "function syncOptionalPanes()" in HTML
    assert 'setHeight(indOn("volume") ? 80 : 0)' not in HTML


def test_orderflow_footprint_is_optional_and_fail_loud():
    assert "footprint:false" in HTML
    assert '{ k:"footprint",   n:"Order Flow · Bid × Ask"' in HTML
    assert 'OrderFlowPanel.setVisible(indOn("footprint"))' in HTML
    assert 'msg.type === "footprint"' in HTML


def test_milk_volume_proxies_are_independent_optional_overlays_default_off():
    for key in ("dealer_net_daily", "dealer_net_weekly",
                "mm_top_profit_daily", "mm_top_profit_weekly"):
        assert f"{key}:false" in HTML
        assert f'indOn("{key}")' in HTML
    assert '{ k:"dealer_net_daily", n:"Dealer-neutral · Día (VOL proxy)"' in HTML
    assert '{ k:"dealer_net_weekly", n:"Dealer-neutral · Semana (VOL proxy)"' in HTML
    assert '{ k:"mm_top_profit_daily", n:"MM payout-min · Día (VOL proxy)"' in HTML
    assert '{ k:"mm_top_profit_weekly", n:"MM payout-min · Semana (VOL proxy)"' in HTML
    assert '["h-dnd-wrap", "dealer_net_daily"]' in HTML
    assert '["h-dnw-wrap", "dealer_net_weekly"]' in HTML
    assert '["h-mmd-wrap", "mm_top_profit_daily"]' in HTML
    assert '["h-mmw-wrap", "mm_top_profit_weekly"]' in HTML
    assert "if (curLevels) drawLevels(curLevels);" in HTML


def test_six_window_realtime_launch_preserves_each_perp_symbol():
    panel = (Path(__file__).resolve().parents[1] / "charts" / "orderflow_panel.js").read_text()
    assert 'toLowerCase() === "auto"' in HTML
    assert "switchPerp(historySym)" in HTML
    assert 'qp.toLowerCase() !== "auto"' in HTML
    assert 'OrderFlowPanel.setFeed("perp")' in HTML
    assert "setFeed" in panel and 'msg.tape_source || "equity"' in panel
