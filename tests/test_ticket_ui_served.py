"""Regresión bug NOK 2026-07-29: live.html carga order_ticket_ui.js pero el
bridge no lo servía (404) -> OrderTicketUI undefined -> "Revisar" moría MUDO."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "charts" / "live.html").read_text(encoding="utf-8")
BRIDGE = (ROOT / "scripts" / "chart_bridge.py").read_text(encoding="utf-8")


def test_every_local_script_in_html_has_a_bridge_route():
    scripts = set(re.findall(r'<script[^>]+src="/?([^"]+\.js)"', HTML))
    assert scripts, "live.html sin <script src> locales? sospechoso"
    for js in scripts:
        assert f'@app.get("/{js}")' in BRIDGE, f"el bridge no sirve /{js} (404 = botones muertos)"
        assert (ROOT / "charts" / js).exists(), f"charts/{js} no existe"


def test_order_click_never_dies_silent():
    assert "y enviando" in HTML and "⏳ Cotizando" in HTML
    assert "El bridge no respondió en 12 s" in HTML
    assert "Sin conexión al bridge" in HTML
    assert "clearTimeout(quickTimer)" in HTML
    # un toque = UNA orden: botón deshabilitado en vuelo y restaurado siempre
    assert "if (quickInFlight) return;" in HTML
    assert "orderBtn.disabled = true;" in HTML
    assert "quickBtnIdle()" in HTML


def test_one_tap_no_dialog_no_selector():
    # Orden de Yunior 2026-07-29: COMPRAR/VENDER directo, sin selector FICHA/ARMAR.
    assert "zone-dest" not in HTML
    assert ">COMPRAR<" in HTML
    assert 'quick_order_result" ) onQuickOrder' in HTML.replace('") on', '" ) on')
    assert 'id="zone-sym"' in HTML          # cualquier ticker
