#!/usr/bin/env python3
"""session_dirs.py — filtro unico de carpetas data/history/<fecha> que SON sesion de mercado.

Por que: `poly_chain_archive.py` corre por launchd a las 08:45 y 16:20 TODOS los dias, tambien
sabado y domingo. La foto del domingo es la del VIERNES con otro nombre (medido 2026-08-02:
data/history/2026-08-02/chain_full_spy.json trae spot 744,27 con spot_age_s=159.611 = 44,3 h).
Todo consumidor que tome "la ultima sesion" por NOMBRE DE CARPETA se come ese duplicado:
skew.py:50 hacia `dates[0]` y su drr_1d salia domingo-viernes = 0 FABRICADO.
La tabla de festivos es la UNICA de la casa (em_envelope), no se duplica aqui.
"""
import datetime as dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _em():
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import em_envelope  # tabla unica de festivos; LEVANTA si se agota (jamas asume "sin festivos")
    return em_envelope


def is_session_dir(name):
    """True/False si `name` es YYYY-MM-DD; None si el nombre no es una fecha (no es carpeta de dia)."""
    try:
        d = dt.date.fromisoformat(name)
    except ValueError:
        return None
    return _em().is_market_day(d)


def session_dirs(hist, reverse=True):
    """Subcarpetas de `hist` que son sesion de mercado, ordenadas por fecha."""
    if not os.path.isdir(hist):
        return []
    out = [n for n in os.listdir(hist)
           if os.path.isdir(os.path.join(hist, n)) and is_session_dir(n) is True]
    return sorted(out, reverse=reverse)
