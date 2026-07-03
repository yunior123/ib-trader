from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "charts" / "live.html").read_text(
    encoding="utf-8"
)


def test_chart_has_a_default_left_gutter():
    assert "--chart-left-gutter: 22px" in HTML
    assert "left: var(--chart-left-gutter)" in HTML


def test_latest_candles_have_visible_right_side_breathing_room():
    assert "const SHOW_BARS = 62" in HTML
    assert "const RIGHT_BREATHING_BARS = 60" in HTML
    assert "to: n + RIGHT_BREATHING_BARS" in HTML


def test_structural_lines_explain_themselves_on_hover():
    assert 'id="leveltip"' in HTML
    assert 'el.addEventListener("mousemove", showLevelTip)' in HTML
    assert "FLIP · Dealer gamma zero-crossing" in HTML
    assert "A-FLIP · Activity zero-crossing" in HTML
    assert "Uses open interest and implied volatility" in HTML
    assert "does not use open interest" in HTML
    assert "CW · Call Wall" in HTML
    assert "PW · Put Wall" in HTML
    assert "MAG · Gamma-volume Magnet" in HTML


def test_compass_is_anchored_in_the_chart_middle_zone():
    compass_css = HTML.split("#dirarrow {", 1)[1].split("}", 1)[0]
    assert "left:55%" in compass_css
    assert "right:auto" in compass_css
    assert "transform:translate(-50%,-50%)" in compass_css
    assert "right:13%" not in compass_css


def test_widgets_are_hidden_by_default_without_losing_saved_selection():
    assert 'const wgFresh = () => ({ visible: false' in HTML
    assert 'const WG_DEFAULT_HIDDEN_KEY = "cockpitWidgets.defaultHidden.v1"' in HTML
    assert "WG.visible = false" in HTML
    assert 'localStorage.setItem(WG_KEY, JSON.stringify(WG))' in HTML
    assert "WG.open[id] = !WG.open[id]" in HTML


def test_candle_timer_is_in_information_bar_not_price_axis():
    infobar = HTML.split('<div id="infobar">', 1)[1].split('<div id="help">', 1)[0]
    chart = HTML.split('<div id="chart">', 1)[1].split('<footer>', 1)[0]
    assert '<span id="countdown"' in infobar
    assert 'id="countdown"' not in chart
    assert 'countdownEl.style.display = "inline-flex"' in HTML
    assert "priceToCoordinate(lastBar.close)" not in HTML
    assert "order:-1; margin-left:4px" in HTML
