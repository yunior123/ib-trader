#!/usr/bin/env python3
"""optgate.py — gate de spread de OPCIONES para las alarmas (2026-07-22,
orden Yunior: "dram bid/ask difference is too high, verify always before
sounding any alarm — we could loss a lot of money").

⚠ LA VERDAD VIVE EN C++: scripts/gate_core.hpp + scripts/gate.cpp -> binario ./gate
   (orden Yunior 2026-07-25: "python solo para test, la computacion en C++").
   Este archivo YA NO CALCULA NADA: es una envoltura fina que llama a ./gate --json y
   traduce su veredicto a los mismos strings de siempre. Si tocas la regla del 5%, del OI
   o del presupuesto, se toca en gate_core.hpp y punto.

QUE ARREGLA ESTA REESCRITURA (auditoria 2026-07-25) — los numeros medidos:
  · FALLA ABIERTA de frescura. La linea `if not spot or (epoch and time.time()-epoch > MAX_AGE_S)`
    saltaba el chequeo de edad entero cuando `epoch` era FALSY. Con `epoch 0` en la cabecera
    (cadena de 1970) esto respondia literalmente "OPCIONES OK (spread 2%)" sobre quotes
    fosiles — el desastre DRAM documentado (spread real 8-20%, -15% al entrar).
    Ahora: sin epoch valido y sin cadena FRESCA no hay numero, y por tanto no hay "OK".
  · DOS matematicas del mismo 5%: aqui era (ask-bid)/ASK y en order_ticket.py (ask-bid)/MID.
    Medido con bid 1.425 / ask 1.50: /ask = 5.0% -> "OPCIONES OK" mientras /mid = 5.1% -> NO-GO.
    Canonico: /MID (el estandar, y el conservador). El mismo numero en todo el sistema.

Regla (CLAUDE.md #4): spread <= 5% del premium o NO se paga.
Uso desde cualquier vigia (API intacta):
    from optgate import opt_vehicle
    veredicto = opt_vehicle("DRAM")   # str listo para pegar al mensaje

Devuelve p.ej.:
  "OPCIONES OK (spread 1%)"                        -> ok=True
  "OPCIONES VETADAS spread 15% — usar ACCIONES o ETF apalancado"
  "OPCIONES s/d (sin cadena fresca) — default acciones"
Lee data/opt_chain_<sym>.txt (cache IBKR, primer OTM liquido <= $3.5) a traves de ./gate.
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(REPO, "gate")          # binario canonico (./scripts/build_gate.sh)
MAX_SPREAD_PCT = 5.0                       # informativo: el gate real esta en gate_core.hpp
MAX_AGE_S = 900
_warned = set()


def _warn(msg):
    """Fail-LOUD una vez por motivo: un gate que no puede opinar tiene que decirlo."""
    if msg not in _warned:
        _warned.add(msg)
        print(f"[optgate] {msg}", file=sys.stderr, flush=True)


def gate_json(sym, *args, timeout=10):
    """Veredicto CRUDO del binario (dict) o None si no se puede obtener. Cero calculo aqui."""
    if not os.path.exists(GATE):
        _warn(f"falta el binario {GATE} — corre ./scripts/build_gate.sh; SIN VEREDICTO")
        return None
    try:
        p = subprocess.run([GATE, "--json", "--no-write", sym.upper(), *args],
                           capture_output=True, text=True, timeout=timeout, cwd=REPO)
        out = (p.stdout or "").strip()
        if not out:
            _warn(f"{sym}: ./gate no devolvio nada ({(p.stderr or '').strip()[:80]})")
            return None
        return json.loads(out.splitlines()[-1])
    except Exception as e:                                   # noqa: BLE001 - degradar limpio
        _warn(f"{sym}: ./gate fallo ({str(e)[:80]})")
        return None


def _survey(sym):
    """(spread_pct, spread_ok) medidos POR EL BINARIO, o (None, False) si no hay veredicto.

    (None, False) cuando: no hay cadena, no hay epoch (frescura no verificable), la cadena
    esta VIEJA, o el contrato no cotiza (bid/ask -1.00 fuera de RTH). "No hay dato" jamas
    se devuelve como un numero bonito: eso era exactamente el fail-open.

    El booleano NO se recalcula en Python. Comparar aqui `pct <= 5.0` volveria a partir la
    frontera: el gate mide 5.000000000000004 para un 5.0% exacto y lo acepta con tolerancia
    EPS; un `<=` suelto en Python lo vetaria. Un solo juez.
    """
    g = gate_json(sym)
    if not g or not (g.get("freshness") or {}).get("fresh"):
        return None, False
    q = g.get("quote") or {}
    pct = q.get("spread_pct")
    if not isinstance(pct, (int, float)):
        return None, False
    return float(pct), bool(q.get("spread_ok"))


def opt_spread_pct(sym):
    """spread% (/mid) del primer OTM liquido, o None si NO hay veredicto posible."""
    return _survey(sym)[0]


def opt_gate(sym, *args):
    """Veredicto completo del gate (GO/CAUTION/NO-GO + motivos) para quien quiera todo."""
    return gate_json(sym, *args)


def opt_vehicle(sym):
    pct, ok = _survey(sym)
    if pct is None:
        return "OPCIONES s/d (sin cadena fresca) — default ACCIONES"
    if ok:
        return f"OPCIONES OK (spread {pct:.0f}%)"
    return f"OPCIONES VETADAS spread {pct:.0f}% — usar ACCIONES o ETF apalancado"


def opt_ok(sym):
    """True solo si SABEMOS que el spread es pagable. Ignorancia -> False."""
    return _survey(sym)[1]


def opt_veto(sym):
    """True solo si SABEMOS que el spread es malo (tres estados, no dos).

    Ni `not opt_ok()` ni `pct > 5` valen: el primero confunde "no hay cadena" con "spread
    malo" (silenciaria la flota un lunes antes del primer refresco) y el segundo vuelve a
    poner un umbral en Python. Ante ignorancia devuelve False: la señal grita.
    """
    pct, ok = _survey(sym)
    return pct is not None and not ok


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["DRAM", "QQQ", "MU", "SKHY"]):
        print(s.upper(), "->", opt_vehicle(s))
