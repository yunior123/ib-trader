#!/usr/bin/env python3
"""spx_print_watch.py — vigia de UN dia (Yunior 2026-08-04 11:5x: "monta alerta para put o
call, nowww"). Niveles de la lectura VolSignals: SPX 7715.5 arriba (estanteria rota -> CALL
acelerando) / 7690 abajo (suelo roto -> PUT). SPX no tiene tick local: se vigila via SPY
(ratio medido 10.09 al armar). PRINT-O-NADA: 2 lecturas consecutivas. Un disparo por lado."""
import os, subprocess, sys, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import notify_short

RATIO = 10.09
UP, DN = 7715.5 / RATIO, 7690.0 / RATIO          # SPY ~764.67 / ~762.14
F = os.path.join(REPO, "data", "rt_last_SPY.txt")

def spot():
    try:
        p = open(F).read().split()
        ts, px = float(p[0]), float(p[1])
        return px if time.time() - ts < 120 else None
    except (OSError, ValueError, IndexError):
        return None

def grita(titulo, corto):
    subprocess.Popen(["/bin/bash", os.path.join(REPO, "scripts", "speak.sh"), "SIGNAL", corto],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      'display notification "%s" with title "%s" sound name "ProChord"' % (corto, titulo)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    notify_short.push(titulo, corto)

print("armado: CALL si SPY imprime >=%.2f (SPX 7715.5) | PUT si <=%.2f (SPX 7690). 2 lecturas." % (UP, DN))
arriba = abajo = 0
disparo_up = disparo_dn = False
while not (disparo_up and disparo_dn):
    lt = time.localtime()
    if lt.tm_hour * 100 + lt.tm_min >= 1601:
        print("cierre: vigia expirado"); break
    px = spot()
    if px is not None:
        arriba = arriba + 1 if px >= UP else 0
        abajo = abajo + 1 if px <= DN else 0
        if arriba >= 2 and not disparo_up:
            disparo_up = True
            grita("🟢 SPX PRINT 7715 — CALL", "Ese es el print. Compra call de XSP: SPX rompio 7715 con dos lecturas.")
        if abajo >= 2 and not disparo_dn:
            disparo_dn = True
            grita("🔴 SPX PRINT 7690 — PUT", "Suelo roto. Compra put de XSP: SPX perdio 7690 con dos lecturas.")
    time.sleep(2)
