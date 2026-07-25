#!/usr/bin/env python3
"""fleet_window.py — UNA sola respuesta a "¿la flota debe estar viva ahora?".

La ventana la fijo Yunior el 2026-07-25: **domingo 20:00 -> viernes 20:00 hora de Toronto.
Fuera de ahi, todo muerto, salvo para testing/backtesting/fixes.**

El CALCULO no vive aqui: vive en `fleet_hours.cpp` (C++23), porque es el que decide si la
flota habla y la ley de la casa es C++ para lo que decide. Este modulo es solo el puente
para los consumidores Python — mueve un codigo de salida, no calcula nada.

POR QUE EXISTE: el 2026-07-25 habia CUATRO ideas distintas del horario conviviendo —
`fleet_healthcheck.market_hours()` (lun-vie 09:30-16:00), `premarket_or_session()`
(lun-vie 04:00-16:00), `levels_5min_archive.in_session()` (09:25-16:10) y ninguna en el
screener. Resultado medido ese sabado: el healthcheck REVIVIA cada 5 min lo que el portero
acababa de apagar, y el screener relanzo el bridge de barras 11 s despues del apagado.
Definiciones divergentes del mismo concepto = el sistema peleandose consigo mismo.

CONTRATO
    live() -> True   la flota debe estar viva
              False  fuera de ventana
              None   NO SE SABE (falta el binario, o fallo) — el llamador debe CALLAR,
                     jamas asumir True. Un falso LIVE hace hablar a los bots con datos
                     muertos; un falso DEAD solo calla. Ante la duda, callar.

`None` es a proposito distinto de `False`: "no lo se" y "no toca" piden avisos distintos.
Prohibido colapsarlos (ley de la casa: nada de devolver un valor plausible ante un fallo).
"""
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BINARIO = os.path.join(REPO, "fleet_hours")


def live(timeout=5):
    """True/False/None segun ./fleet_hours (exit 0 = LIVE, 1 = DEAD). Ver el contrato."""
    if not os.access(BINARIO, os.X_OK):
        return None
    try:
        return subprocess.run([BINARIO], capture_output=True, timeout=timeout).returncode == 0
    except Exception:
        return None


def why(timeout=5):
    """Explicacion humana del portero, o None. Para logs y avisos, nunca para decidir."""
    if not os.access(BINARIO, os.X_OK):
        return None
    try:
        r = subprocess.run([BINARIO, "--why"], capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip().splitlines()[0] if r.stdout else None
    except Exception:
        return None


def guard_or_exit(nombre, permitir_sin_portero=False):
    """Guarda para un job de launchd: sale 0 si no toca correr.

    Sale 0 y no 1 a proposito: "hoy no tocaba" NO es un fallo del job, y launchd graba el
    exit code — un 1 aqui ensuciaria el audit de `fleet_healthcheck` con fallos fantasma.
    """
    v = live()
    if v is True:
        return
    if v is None and permitir_sin_portero:
        print(f"[{nombre}] portero AUSENTE ({BINARIO}) — sigo porque el job lo permite")
        return
    motivo = why() or ("portero AUSENTE: compila con scripts/build_fleet_hours.sh"
                       if v is None else "fuera de ventana")
    print(f"[{nombre}] no corro: {motivo}")
    raise SystemExit(0)


if __name__ == "__main__":
    v = live()
    print({True: "LIVE", False: "DEAD", None: "DESCONOCIDO (portero ausente)"}[v])
    print(why() or "")
    raise SystemExit(0 if v is True else 1)
