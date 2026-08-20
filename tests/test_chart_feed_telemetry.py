import importlib.util
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chart_bridge_feed", REPO / "scripts" / "chart_bridge.py")
CB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CB)
HTML = (REPO / "charts" / "live.html").read_text()
HEATMAP = (REPO / "charts" / "gex_heatmap_widget.js").read_text()


def test_fresh_websocket_tick_is_declared_realtime():
    st = CB.State("spy")
    st.bars = [[int(time.time()) - 60, 1, 2, 1, 2, 100]]
    st._rt_source = "finnhub"
    st._rt_tick_epoch = time.time() - 0.25
    meta = CB.chart_feed_meta(st)
    assert meta["realtime"] is True
    assert meta["provider"] == "finnhub"
    assert meta["upstream"] == "websocket"
    assert meta["ui_transport"] == "websocket"
    assert meta["age_s"] < 1


def test_stale_tick_is_not_presented_as_realtime(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "market_source.txt").write_text("intrinio\n")
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    st = CB.State("spy")
    st.bars = [[int(time.time()) - 1000, 1, 2, 1, 2, 100]]
    st._rt_source = "finnhub"
    st._rt_tick_epoch = time.time() - 100
    meta = CB.chart_feed_meta(st)
    assert meta["realtime"] is False
    assert meta["provider"] == "intrinio"
    assert meta["upstream"] == "rest->file"
    assert meta["tier"] == "delayed_15m"


def test_fresh_perpetual_bbo_is_declared_24x7_websocket():
    st = CB.State("qqqusdt")
    st.perp_base = "QQQ"
    st._perp_raw = [[int(time.time()) - 5, 724, 725, 723, 724.5, 1]]
    st.bars = st._perp_raw
    st._rt_source = "okx-ws"
    st._rt_tick_epoch = time.time() - 0.1
    meta = CB.chart_feed_meta(st)
    assert meta["realtime"] is True
    assert meta["provider"] == "okx-ws"
    assert meta["tier"] == "realtime_24x7"
    assert meta["upstream"] == "websocket"


def test_chart_and_heatmap_show_loading_latency_provider_and_transport():
    assert 'id="chartload"' in HTML and 'id="chartfeed"' in HTML
    assert "beginChartLoad(`cargando ${u}`)" in HTML
    assert "fetch ${Math.round(lastChartFetchMs)}ms" in HTML
    assert "upstream ${f.upstream" in HTML and "UI WS" in HTML
    assert "REST snapshot" in HEATMAP
    assert "fetch ${Math.round(fetchMs)}ms" in HEATMAP
    assert "class=\"ghspin\"" in HEATMAP


def test_provider_checkbox_panel_filters_chart_heatmap_and_perps():
    assert 'id="providerbtn"' in HTML and 'id="providerpanel"' in HTML
    assert 'localStorage.getItem("providerDisplay_v1")' in HTML
    for provider in ("ibkr", "finnhub", "intrinio", "uw", "polygon", "okx", "bybit", "lse"):
        assert f'k:"{provider}"' in HTML
    assert "providerEnabled(lastChartFeed.provider)" in HTML
    assert "providerEnabled(rawPerp.src)" in HTML
    assert "window.providerEnabled(d.src)" in HEATMAP


def test_any_catalogued_market_ticker_can_be_resolved(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    (data / "lse_catalog.json").write_text(__import__("json").dumps([
        {"dataset": "stocks", "symbol": "IBM", "name": "IBM"},
        {"dataset": "crypto", "symbol": "BTC/USD", "name": "Bitcoin"},
        {"dataset": "options", "symbol": "IBM", "name": "IBM options"},
    ]))
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    assert CB.lse_catalog_entry("ibm")["dataset"] == "stocks"
    assert CB.lse_catalog_entry("btc/usd")["dataset"] == "crypto"
    assert CB.lse_catalog_entry("DOES-NOT-EXIST") is None


def test_lse_catalog_search_supports_more_than_six_tickers(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    rows = [{"dataset": "stocks", "symbol": f"TEST{i}", "name": f"Test company {i}",
             "live": 1} for i in range(12)]
    rows += [{"dataset": "options", "symbol": "TEST0", "name": "options duplicate"}]
    (data / "lse_catalog.json").write_text(__import__("json").dumps(rows))
    monkeypatch.setattr(CB, "REPO", str(tmp_path))
    got = CB.lse_catalog_search("TEST", limit=30)
    assert len(got) == 12
    assert len({r["symbol"] for r in got}) == 12
    assert all(r["dataset"] == "stocks" for r in got)


def test_london_only_watchlist_does_not_offer_other_providers(monkeypatch):
    monkeypatch.setitem(CB.STATE_CFG, "lse_only", True)
    monkeypatch.setattr(CB, "load_fleet", lambda: ["QQQ"])
    monkeypatch.setattr(CB, "load_user_watchlist", lambda: [])
    monkeypatch.setattr(CB, "lse_catalog_entry", lambda s: {"dataset": "etf"})
    payload = CB.watchlist_payload()
    assert payload["src"] == "lse"
    assert payload["perp"] == {} and payload["korea"] == []


def test_dynamic_equity_has_explicit_rest_then_websocket_paths():
    src = (REPO / "scripts" / "chart_bridge.py").read_text()
    assert "async def prepare_dynamic_equity" in src
    assert "def load_lse_dynamic_bars" in src
    assert "async def lse_dynamic_ws_feed" in src
    assert 'st._rt_source = "lse-ws-bbo-mid"' in src
    assert '"action": "subscribe_options"' in src
    assert 'msg.get("type") == "options_subscribed"' in src
    assert "apply_option_tick" in src
    assert "_lse_rebuild_from_ws" in src


def test_lse_websocket_uses_current_tls_host_and_current_auth_frame():
    src = (REPO / "scripts" / "chart_bridge.py").read_text()
    client = (REPO / "scripts" / "lse_client.py").read_text()
    assert 'WS_URL = "wss://data-ws.londonstrategicedge.com"' in client
    assert 'msg.get("type") == "auth" and msg.get("status") == "ok"' in src
    assert 'WS_URL = "wss://ws.londonstrategicedge.com"' not in client


def test_lse_heatmap_poll_tracks_websocket_refits_with_rest_greek_disclosure():
    assert "const POLL_MS = 1000" in HEATMAP
    assert "WS prints · REST Greeks" in HEATMAP


def test_quiet_lse_subscription_is_connected_but_not_fake_realtime(monkeypatch):
    monkeypatch.setitem(CB.STATE_CFG, "lse_only", True)
    st = CB.State("qqq")
    st.bars = [[int(time.time()) - 3600, 1, 2, 1, 2, 100]]
    st._dynamic_provider = "lse"
    st._lse_ws_status = "SUBSCRIBED"
    st._lse_ws_connected_at = time.time() - 60
    st._lse_ws_subscribed_at = time.time() - 59
    meta = CB.chart_feed_meta(st)
    assert meta["lse_ws"]["connected"] is True
    assert meta["lse_ws"]["status"] == "SUBSCRIBED"
    assert meta["realtime"] is False
    assert meta["tier"] == "subscribed/no-fresh-tick"
    assert meta["upstream"] == "websocket+rest"


def test_chart_renders_lse_transport_separately_from_price_freshness():
    assert 'LSE WS ✓ ${ws.status || "CONNECTED"} · PRICE STALE' in HTML
    assert 'msg.type === "feed_status"' in HTML
    assert "#chartfeed.connected" in HTML
    assert 'modepill.textContent = "● LSE LIVE"' in HTML
