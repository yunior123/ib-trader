#!/usr/bin/env python3
"""rt_last — el PRINT en tiempo real, con un solo dueño por fichero.

`data/rt_last_<SYM>.txt` = "EPOCH PRICE SIZE FUENTE" (una linea). Lo escriben varios demonios
de streaming (Finnhub hoy; Intrinio en cuanto el vendor encienda su cluster), asi que la regla
es: **solo pisa quien trae un tick MAS NUEVO**. Sin esto, dos WebSockets vivos se sobrescriben
en bucle y el ultimo en llegar gana aunque su tick sea mas viejo — un precio rancio disfrazado
de vivo, que es justo lo que la casa prohibe.

EPOCH es siempre el reloj de BOLSA del tick, jamas la hora de llegada.
"""
import os
import time

# Un tick que LLEGA con 900 s ya no es un PRINT, es historia. Sin esta guarda, el tick de
# Intrinio (15 min impuestos, medido 2026-08-03) ganaba el fichero canonico en cuanto Finnhub
# callaba un rato, y `rt_last_SPY` pasaba a 904 s de antiguedad con pinta de vivo.
MAX_AGE_S = float(os.environ.get("RT_LAST_MAX_AGE_S", "120"))


def path(sym: str) -> str:
    return os.path.join("data", f"rt_last_{sym.upper()}.txt")


def read(sym: str):
    """(epoch, price, size, fuente) o None. None y no ceros: un 0 seria un precio."""
    try:
        with open(path(sym)) as f:
            p = f.read().split()
        return (float(p[0]), float(p[1]), float(p[2]), p[3] if len(p) > 3 else "?")
    except (OSError, ValueError, IndexError):
        return None


def write_if_newer(sym, epoch, price, size, fuente, max_age_s=None):
    # sin anotaciones `float | None`: el venv de la flota es 3.9 y ahi es TypeError al importar
    """Escribe solo si el tick es (a) fresco de verdad y (b) mas nuevo que el que ya hay."""
    if price is None or price <= 0 or not epoch:
        return False
    tope = MAX_AGE_S if max_age_s is None else max_age_s
    if tope > 0 and (time.time() - epoch) > tope:
        return False        # nace viejo: no entra en el print canonico
    prev = read(sym)
    if prev is not None and epoch <= prev[0]:
        return False
    dst = path(sym)
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"{epoch:.3f} {price:.4f} {size:.0f} {fuente}\n")
    os.replace(tmp, dst)
    return True
