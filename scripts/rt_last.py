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


def write_if_newer(sym: str, epoch: float, price: float, size: float, fuente: str) -> bool:
    """Escribe solo si este tick es mas nuevo que el que ya hay. True si escribio."""
    if price is None or price <= 0 or not epoch:
        return False
    prev = read(sym)
    if prev is not None and epoch <= prev[0]:
        return False
    dst = path(sym)
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"{epoch:.3f} {price:.4f} {size:.0f} {fuente}\n")
    os.replace(tmp, dst)
    return True
