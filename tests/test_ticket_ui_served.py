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


def test_review_click_never_dies_silent():
    assert "⏳ Preflight en curso…" in HTML
    assert "El bridge no respondió al preflight" in HTML
    assert "Sin conexión al bridge" in HTML
    assert "clearTimeout(preflightTimer)" in HTML
