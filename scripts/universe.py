#!/usr/bin/env python3
"""universe.py — fuente unica de las DOS listas de simbolos (doctrina docs/UNIVERSOS.md).

`fleet()`          -> data/fleet.txt (30): vota, habla, dispara. La leen 36 ficheros, uno
                      es el denominador de MANADA (fleet_consensus). Exige barras 1m.
`gamma_universe()`  -> data/universe_gamma.txt (35 = fleet + SPX/XSP/NDX/DIA/IWM): el
                      universo del MAPA. Solo exige cadena de opciones. No vota, no habla,
                      no dispara.

Las dos LEVANTAN si el fichero falta o esta vacio: una lista vacia silenciosa escondio media
flota en fleet_consensus el 2026-07-25 (21/26 = 80.8% disparo DANGER cuando 21/30 = 70% no
debia). Nunca confundir las dos listas — es la forma mas facil de repetir ese bug.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_list(fname, motivo):
    p = os.path.join(REPO, "data", fname)
    syms = []
    with open(p) as f:
        for ln in f:                      # una sola linea separada por espacios,
            ln = ln.strip()               # pero se admite tambien uno por linea
            if not ln or ln.startswith("#"):
                continue
            syms.extend(t.upper() for t in ln.split())
    if not syms:
        raise RuntimeError(f"{p} vacia o ausente: {motivo}")
    return syms


def fleet():
    """La flota de SEÑALES (30). Vota, habla, dispara."""
    return _read_list("fleet.txt", "sin flota canonica no hay señal que votar")


def gamma_universe():
    """El universo del MAPA gamma (35). Mapa solamente: no vota, no habla, no dispara."""
    return _read_list("universe_gamma.txt", "sin universo gamma no hay mapa que construir")
