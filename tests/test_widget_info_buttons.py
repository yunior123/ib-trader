import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "charts" / "live.html").read_text(encoding="utf-8")


def test_every_professional_widget_has_one_info_button_and_popover():
    widgets = {"gex", "prem", "flow", "liqmap", "tech", "ivreg", "rviv", "hmap", "book", "gdecay",
               "dark", "gexexp"}   # dark/gexexp: widgets UW 2026-08-03
    buttons = set(re.findall(r'class="wginfo"[^>]+data-widget="([^"]+)"', HTML))
    popovers = set(re.findall(r'class="popover-box"[^>]+data-widget="([^"]+)"', HTML))
    assert buttons == widgets
    assert popovers == widgets


def test_info_popovers_have_single_accessible_initializer():
    assert HTML.count("// ===== Widget info popovers =====") == 1
    assert 'btn.setAttribute("aria-controls", popoverId)' in HTML
    assert 'btn.setAttribute("aria-expanded", "true")' in HTML
    assert 'popover.setAttribute("role", "dialog")' in HTML
    assert 'if (e.key === "Escape") closeAllPopovers();' in HTML
