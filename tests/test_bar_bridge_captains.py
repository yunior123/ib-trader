#!/usr/bin/env python3
"""test_bar_bridge_captains.py — los CAPITANES nunca se quedan sin cinta firmada.

BUG MEDIDO el 2026-07-25: `data/whale_qqq.txt` y `data/whale_spy.txt` a **0 BYTES** — los dos
capitanes del mercado sin cinta tick-by-tick, junto con aapl/amd/asml/gld/intc/tsm/txn (8 de 14
vacios), mientras los cupos se los habian llevado DRAM/NOK/NVDA/SPCX/TSLA por salir antes en la
lista de argumentos. IBKR capea las suscripciones tick-by-tick por cuenta (err 10190) y el
reparto era best-effort EN EL ORDEN DE LA LISTA.

Por que importa: la REGLA 12 (jerarquia de capitanes) dice que si el capitan que gobierna un
simbolo va EN CONTRA, la señal de ese nombre queda practicamente ANULADA. Con la cinta de
QQQ/SPY vacia, esa regla corria sin su input firmado — el veto mas fuerte del sistema, ciego.

No se puede testear la suscripcion real sin TWS, asi que se testea el ORDEN, que es lo que
decide quien se queda fuera cuando el cap muerde.
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(daemon):
    """Importa el modulo con/sin --daemon en argv (el reorden solo aplica en daemon)."""
    argv = ["ibkr_bar_bridge.py"] + (["--daemon"] if daemon else []) + ["NVDA", "MU", "QQQ", "SPY"]
    old = sys.argv
    sys.argv = argv
    try:
        spec = importlib.util.spec_from_file_location(
            f"bbridge_{'d' if daemon else 's'}", os.path.join(REPO, "scripts", "ibkr_bar_bridge.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except ImportError as e:
        pytest.skip(f"ib_async no disponible en este venv: {e}")
    finally:
        sys.argv = old


def test_captains_first_pure():
    """La funcion de orden: capitanes al frente, el resto conserva su orden relativo."""
    m = _load(daemon=False)
    assert m.captains_first(["NVDA", "MU", "QQQ", "SPY"]) == ["QQQ", "SPY", "NVDA", "MU"]
    # SMH tambien es capitan (semis) y va tras QQQ/SPY, en el orden de CAPTAINS_FIRST
    assert m.captains_first(["DRAM", "SMH", "NOK", "QQQ"]) == ["QQQ", "SMH", "DRAM", "NOK"]
    # el orden relativo de los NO capitanes se preserva exactamente
    assert m.captains_first(["D", "C", "B", "A"]) == ["D", "C", "B", "A"]
    # sin capitanes en la lista, no toca nada
    assert m.captains_first(["MU", "NVDA"]) == ["MU", "NVDA"]
    # idempotente
    once = m.captains_first(["NVDA", "QQQ", "MU", "SPY"])
    assert m.captains_first(once) == once


def test_daemon_reorders_so_captains_get_the_tape():
    """En --daemon los capitanes van primero: el cap de IBKR jamas los deja fuera."""
    m = _load(daemon=True)
    assert m.SYMS[:2] == ["QQQ", "SPY"], f"capitanes no van primeros: {m.SYMS}"
    # STATES respeta el orden de insercion (dict py3.7+), y la suscripcion itera STATES.values()
    assert list(m.STATES.keys())[:2] == ["QQQ", "SPY"]


def test_single_mode_keeps_first_argument():
    """Sin --daemon NO se reordena: run_single() usa SYMS[0] como el simbolo que sondea,
    asi que `ibkr_bar_bridge.py NVDA MU` debe seguir apuntando a NVDA."""
    m = _load(daemon=False)
    assert m.SYMS[0] == "NVDA", f"modo suelto reordenado: {m.SYMS}"


def test_no_symbol_is_lost_in_the_reorder():
    """El reorden es una PERMUTACION: ni pierde ni duplica simbolos."""
    m = _load(daemon=False)
    src = ["NVDA", "MU", "QQQ", "SPY", "SMH", "DRAM", "NOK"]
    out = m.captains_first(src)
    assert sorted(out) == sorted(src)
    assert len(out) == len(set(out))
