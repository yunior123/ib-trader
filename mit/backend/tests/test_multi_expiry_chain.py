"""_multi_expiry_chain: un vencimiento que falla NO puede desaparecer en silencio.

Medido el 2026-08-02 con SPY al MISMO spot 744.27: una corrida daba call_wall 775 / flip 729.98
con 4 vencimientos y la siguiente call_wall 700 / flip 647.68 con 3. Un muro que parpadea entre
refrescos es peor que no tener muro.
"""
from __future__ import annotations

import asyncio
from datetime import date

import pytest

from backend.app.config import Settings
from backend.app.engine.event_bus import EventBus
from backend.app.engine.orchestrator import MarketIntelligenceEngine


class _Opt:
    """Provider de opciones falso: falla en los vencimientos indicados, y opcionalmente deja de
    fallar en el reintento (para simular un error transitorio)."""

    name = "falso"

    def __init__(self, exps, fallan, sanan_al_reintentar=False):
        self.exps = exps
        self.fallan = set(fallan)
        self.sanan = sanan_al_reintentar
        self.llamadas = []

    async def get_expirations(self, symbol):
        return list(self.exps)

    async def get_option_chain(self, symbol, expiration=None):
        d = expiration.date() if expiration else None
        self.llamadas.append(d)
        if d in self.fallan:
            if self.sanan and self.llamadas.count(d) > 1:
                return [f"{d}-ok"]
            raise RuntimeError(f"boom {d}")
        return [f"{d}-ok"]


def _engine(opt):
    class _P:
        options = opt
        market = depth = flow = fallback = None
    return MarketIntelligenceEngine(Settings(), _P(), EventBus())


EXPS = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 21)]


def test_reintenta_el_vencimiento_transitorio_y_recupera_la_cobertura():
    opt = _Opt(EXPS, fallan={EXPS[1]}, sanan_al_reintentar=True)
    chain = asyncio.run(_engine(opt)._multi_expiry_chain("SPY"))
    assert len(chain) == 4, "tras el reintento el mapa debe volver a cubrir los 4 vencimientos"
    assert opt.llamadas.count(EXPS[1]) == 2


def test_cobertura_bajo_la_mitad_LEVANTA_en_vez_de_servir_mapa_parcial():
    """3 de 4 caidos: el mapa ya no describe el mismo libro -> se declara, no se disimula."""
    opt = _Opt(EXPS, fallan=set(EXPS[:3]))
    with pytest.raises(RuntimeError):
        asyncio.run(_engine(opt)._multi_expiry_chain("SPY"))


def test_todos_caidos_levanta():
    opt = _Opt(EXPS, fallan=set(EXPS))
    with pytest.raises(RuntimeError):
        asyncio.run(_engine(opt)._multi_expiry_chain("SPY"))


def test_un_fallo_persistente_sobre_cuatro_grita_pero_devuelve(caplog):
    """Con cobertura >= mitad se sirve, pero queda ERROR en el log diciendo que los muros de este
    refresco NO son comparables con los del anterior."""
    import logging

    opt = _Opt(EXPS, fallan={EXPS[3]})
    with caplog.at_level(logging.ERROR, logger="mit.orchestrator"):
        chain = asyncio.run(_engine(opt)._multi_expiry_chain("SPY"))
    assert len(chain) == 3
    assert any("NO comparables" in r.getMessage() for r in caplog.records)


def test_sin_vencimientos_cae_a_la_cadena_simple():
    opt = _Opt([], fallan=set())
    assert asyncio.run(_engine(opt)._multi_expiry_chain("SPY")) == ["None-ok"]
