"""X rechaza con 403 cualquier post con 2+ cashtags (docs/ERRORES.md, 2026-07-21 x2).

El sanitizador tiene que dejar EXACTAMENTE uno. Los casos de abajo salen de posts
reales de la flota (x_plan_poster / x_postmortem / x_whale_bot).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from x_post_common import count_cashtags, sanitize_cashtags  # noqa: E402


def _one_or_zero(text):
    """Invariante duro: tras sanear, X nunca ve mas de un cashtag."""
    return count_cashtags(sanitize_cashtags(text)) <= 1


# --- el contador ve lo mismo que X --------------------------------------------
def test_count_pure_cashtag():
    assert count_cashtags("$NVDA rompe") == 1


def test_count_money_glued_to_letters_counts():
    # el caso cazado en vivo: `$4.7B` cuenta, y por eso el post se fue en 403
    assert count_cashtags("flujo de $4.7B") == 1


def test_count_pure_digits_does_not_count():
    assert count_cashtags("premium $200 max") == 0


def test_count_two_is_two():
    assert count_cashtags("$NVDA y $SPY") == 2


# --- el sanitizador -----------------------------------------------------------
def test_keeps_first_drops_second():
    out = sanitize_cashtags("$NVDA lidera, $SPY sigue")
    assert out == "$NVDA lidera, SPY sigue"
    assert count_cashtags(out) == 1


def test_money_glued_loses_dollar_keeps_meaning():
    out = sanitize_cashtags("$QQQ con flujo de $4.7B hoy")
    assert out == "$QQQ con flujo de 4.7B USD hoy"
    assert count_cashtags(out) == 1


def test_money_alone_still_sanitized_when_no_cashtag():
    # sin cashtag puro delante, el importe con letras sigue perdiendo el $
    out = sanitize_cashtags("tide de $53M en la sesion")
    assert out == "tide de 53M USD en la sesion"
    assert count_cashtags(out) == 0


def test_pure_digits_untouched():
    out = sanitize_cashtags("$SPY techo, premium $200, stop $198")
    assert out == "$SPY techo, premium $200, stop $198"
    assert count_cashtags(out) == 1


def test_three_cashtags_leave_one():
    out = sanitize_cashtags("$MU $SKHY $DRAM manada de memoria")
    assert out == "$MU SKHY DRAM manada de memoria"
    assert count_cashtags(out) == 1


def test_trailing_punctuation_preserved():
    out = sanitize_cashtags("lideres: $SMH, $MU.")
    assert out == "lideres: $SMH, MU."
    assert count_cashtags(out) == 1


def test_idempotent():
    once = sanitize_cashtags("$NVDA $SPY $4.7B")
    assert sanitize_cashtags(once) == once


def test_no_cashtag_is_noop():
    assert sanitize_cashtags("sin tickers aqui") == "sin tickers aqui"


def test_invariant_on_real_shaped_posts():
    posts = [
        "$QQQ 🔴 741 muro | 🎯 738 | 📍 736 | 🟢 733 | 🛑 730 — flujo $4.7B calls. No es consejo financiero.",
        "Postmortem: $NVDA +2.1%, $AMD +1.4%, $MU -0.8%. Premium quemado $1.2M.",
        "Manada memoria: $MU $SKHY $DRAM $SNDK $WDC $STX — 6/6 arriba, tide $53M.",
        "Premium $200 max, spread <5%, OI>500. Sin cashtags.",
        "$SPY",
        "$4.7B",
    ]
    for p in posts:
        assert _one_or_zero(p), p


def test_post_text_applies_sanitizer(monkeypatch):
    """La guarda tiene que estar en el camino real de publicacion, no solo suelta."""
    import x_post_common as xc

    captured = []
    monkeypatch.setattr(xc, "budget_refusal", lambda: None)
    out = xc.post_text("$NVDA y $SPY", "test", lambda m: captured.append(m), dry_run=True)
    assert out is True
    # "$NVDA y $SPY" (12) -> "$NVDA y SPY" (11): el $ del segundo cayo en post_text
    assert any("(11 chars)" in c for c in captured), captured
