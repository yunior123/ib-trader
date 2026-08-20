import importlib.util
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("perp_ws", REPO / "scripts" / "perp_ws_bridge.py")
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
SOURCE = (REPO / "scripts" / "perp_ws_bridge.py").read_text()
CHART_SOURCE = (REPO / "scripts" / "chart_bridge.py").read_text()
HTML = (REPO / "charts" / "live.html").read_text()


def test_ws_snapshot_contract_and_freshness():
    now = time.time()
    got = P.snapshot_stats({
        "NVDA": {"px": 224.8, "bid": 224.79, "ask": 224.81,
                 "vol24h_usd": 1_900_000, "oi_usd": 11_900_000,
                 "src": "okx-ws", "feed_ts": now - 0.5},
    }, now=now)
    row = got["NVDA"]
    assert row["transport"] == "websocket"
    assert row["src"] == "okx-ws"
    assert row["feed_age_s"] == 0.5
    assert row["spread_pct"] == 0.0089


def test_incomplete_or_crossed_books_are_not_published():
    assert P.snapshot_stats({"X": {"px": 1, "bid": 2, "ask": 1,
                                    "src": "okx-ws", "feed_ts": time.time()}}) == {}
    assert P.snapshot_stats({"X": {"px": 1, "src": "okx-ws",
                                    "feed_ts": time.time()}}) == {}


def test_volume_and_open_interest_use_websocket_channels():
    assert '("trades", "bbo-tbt", "tickers", "open-interest")' in SOURCE
    assert '"tickers.%sUSDT" % s' in SOURCE


def test_bridge_accepts_hot_dynamic_subscription_requests():
    assert 'REQUESTS = "data/perp_requests.txt"' in SOURCE
    assert "async def _okx_dynamic_subscriber" in SOURCE
    assert "async def _bybit_dynamic_subscriber" in SOURCE
    assert "pedidos_dinamicos() - resolved_requests" in SOURCE


def test_perpetual_chart_uses_tape_and_bbo_not_equity_bars():
    assert "def load_perp_tape_bars" in CHART_SOURCE
    assert 'f"nbbo_{st.perp_base.lower()}usdt.txt"' in CHART_SOURCE
    assert 'ctl.get("cmd") == "perp"' in CHART_SOURCE
    assert "st._perp_raw = load_perp_tape_bars(base)" in CHART_SOURCE
    assert "async def perp_levels_poll" in CHART_SOURCE
    assert 'lv["underlying_sym"] = base.upper()' in CHART_SOURCE


def test_ui_can_open_perpetual_by_badge_or_usdt_search():
    assert "function switchPerp(sym)" in HTML
    assert 'data-perp="${s}"' in HTML
    assert 'ws.send(JSON.stringify({ cmd: "perp", sym: base }))' in HTML
    assert 'new URLSearchParams(location.search).get("perp")' in HTML
    assert 'modepill.textContent = "● PERP 24/7"' in HTML


def test_perpetual_mode_follows_every_supported_ticker_dynamically():
    assert 'let chartSymbolMode = new URLSearchParams(location.search).get("perp")' in HTML
    assert 'chartSymbolMode === "perp")' in HTML
    assert 'history.replaceState(null, "", here)' in HTML
    assert 'switchSymbol(curSym.slice(0, -4), true)' in HTML
    assert 's + "USDT" === curSym' in HTML


def test_any_usdt_text_is_resolved_by_backend_not_a_static_ui_map():
    assert 'if (s.endsWith("USDT"))' in HTML
    assert 'PERP[s.slice(0, -4)]' not in HTML
