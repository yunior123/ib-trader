from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "charts" / "live.html").read_text(encoding="utf-8")
HEATMAP = (ROOT / "charts" / "gex_heatmap_widget.js").read_text(encoding="utf-8")
FRACTAL = (ROOT / "charts" / "mm_fractal_widget.js").read_text(encoding="utf-8")


def test_widget_panel_has_persistent_master_visibility_switch():
    assert 'const wgFresh = () => ({ visible: true' in HTML
    assert 'WG.visible = WG.visible === false' in HTML
    assert 'localStorage.setItem(WG_KEY, JSON.stringify(WG))' in HTML
    assert '"--dockw", dockW + "px"' in HTML


def test_hidden_panel_preserves_individual_widget_choices():
    assert 'const on = wgShowing(id)' in HTML
    assert 'WG.open[id] = !WG.open[id]' in HTML
    assert 'if (WG.open[id]) { WG.visible = true;' in HTML


def test_expensive_london_widgets_suspend_browser_refresh_when_hidden():
    assert '!window.cockpitWidgetOpen("gexheat")' in HEATMAP
    assert '!window.cockpitWidgetOpen("mmfractal")' in FRACTAL


def test_builtin_widgets_respect_master_panel_visibility():
    for widget in ("tech", "flow", "liqmap", "gex", "ivreg", "rviv", "hmap", "book", "gdecay"):
        assert f'wgShowing("{widget}")' in HTML
    assert 'if (wgShowing("tech"))' in HTML
