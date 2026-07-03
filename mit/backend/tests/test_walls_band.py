"""Los muros son niveles que se DIBUJAN y se operan: no pueden caer a -50% del spot.

Bug medido 2026-08-02 (SPY spot 744,27): `max(put_oi)` sobre la cadena ENTERA daba put_wall=360
(OI 26.722 de un tail hedge lejano) y se pintaba como "soporte". Definicion del vendor de
referencia (support.spotgamma.com): muro = strike de GAMMA NETA maxima, call ARRIBA del precio y
put ABAJO.
"""
from __future__ import annotations

from datetime import UTC, datetime

from backend.app.analytics.options_positioning import WALL_BAND, analyze_dealer_positioning
from backend.app.domain import OptionContract


def _c(strike, tipo, oi, gamma=None):
    return OptionContract(
        symbol="SPY", strike=strike, expiration=datetime(2026, 8, 21, tzinfo=UTC),
        option_type=tipo, open_interest=oi, gamma=gamma, delta=0.5, iv=0.2,
        bid=1.0, ask=1.1, volume=10,
    )


SPOT = 744.27


def test_el_tail_hedge_lejano_NO_es_el_put_wall():
    """El caso exacto que fallaba: 360 con OI enorme frente al 733 cercano."""
    chain = [
        _c(360.0, "put", 26722, gamma=0.0001),   # LEAP a -52%: OI el mas alto de la cadena
        _c(733.0, "put", 5000, gamma=0.02),
        _c(749.0, "call", 6000, gamma=0.02),
    ]
    d = analyze_dealer_positioning("SPY", SPOT, chain)
    assert d.put_wall == 733.0, f"put_wall={d.put_wall}: volvio a coger el strike de fuera de banda"
    assert d.call_wall == 749.0


def test_call_wall_solo_por_ENCIMA_y_put_wall_solo_por_DEBAJO():
    chain = [
        _c(700.0, "call", 99999, gamma=0.05),    # call por DEBAJO del spot: no es resistencia
        _c(760.0, "call", 100, gamma=0.001),
        _c(790.0, "put", 99999, gamma=0.05),     # put por ENCIMA del spot: no es soporte
        _c(720.0, "put", 100, gamma=0.001),
    ]
    d = analyze_dealer_positioning("SPY", SPOT, chain)
    assert d.call_wall == 760.0
    assert d.put_wall == 720.0


def test_gamma_gana_a_open_interest():
    """OI acumula historia; la gamma dice donde el dealer tiene que cubrir HOY."""
    chain = [
        _c(735.0, "put", 50000, gamma=0.001),    # mucho OI, poca gamma
        _c(740.0, "put", 1000, gamma=0.09),      # poco OI, MUCHA gamma  <- el muro
        _c(750.0, "call", 10, gamma=0.05),
    ]
    d = analyze_dealer_positioning("SPY", SPOT, chain)
    assert d.put_wall == 740.0
    assert any("source=gamma" in c for c in d.caveats)


def test_sin_gamma_medida_cae_a_oi_y_lo_DECLARA():
    """Sin griegas no se inventa: se usa OI y se dice en el caveat."""
    chain = [_c(735.0, "put", 5000), _c(750.0, "call", 6000)]
    d = analyze_dealer_positioning("SPY", SPOT, chain)
    assert (d.call_wall, d.put_wall) == (750.0, 735.0)
    assert any("source=oi" in c for c in d.caveats)


def test_sin_ningun_strike_en_banda_devuelve_None_no_un_strike_absurdo():
    """Ningun muro es mejor que un muro falso: None, jamas el strike lejano."""
    chain = [_c(100.0, "put", 9999, gamma=0.05), _c(2000.0, "call", 9999, gamma=0.05)]
    d = analyze_dealer_positioning("SPY", SPOT, chain)
    assert d.call_wall is None and d.put_wall is None


def test_la_banda_del_muro_coincide_con_la_del_mapa():
    """Si divergen, se dibujaria una linea de nivel fuera de la ventana visible."""
    from backend.app.analytics.options_positioning import MATRIX_BAND

    assert WALL_BAND == MATRIX_BAND
