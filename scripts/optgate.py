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

Regla (CLAUDE.md #4): spread <= 5% del premium O peaje <= 0.60% (medido 2026-08-05: el
peaje = (ask-bid)/(|delta|*spot) rescata contratos caros con delta alta donde el % miente;
supervivientes reales 0.23-0.31%, vetados 0.76-2.70%). mid < $0.20 = veto directo: con tick
de 1c el spread% minimo es 0.01/mid > 5% (0/821 pasaron).
Uso desde cualquier vigia (API intacta):
    from optgate import opt_vehicle
    veredicto = opt_vehicle("DRAM")   # str listo para pegar al mensaje

Devuelve p.ej.:
  "OPCIONES OK (spread 1%)"                        -> ok=True
  "OPCIONES OK (spread 7%, peaje 0.31%)"           -> ok=True (rescatado por peaje)
  "OPCIONES VETADAS spread 15% — usar ACCIONES o ETF apalancado"
  "OPCIONES s/d (sin cadena fresca) — default acciones"
Lee data/opt_chain_<sym>.txt (cache IBKR, primer OTM liquido <= $3.5) a traves de ./gate.
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# bin/ primero, raiz de respaldo: la mudanza a bin/ dejo esta ruta apuntando al sitio viejo.
GATE = next((_p for _p in (os.path.join(REPO, "bin", "gate"), os.path.join(REPO, "gate"))
        if os.access(_p, os.X_OK)), os.path.join(REPO, "bin", "gate"))          # binario canonico (./scripts/build_gate.sh)
MAX_SPREAD_PCT = 5.0                       # informativo: el gate real esta en gate_core.hpp
MAX_PEAJE_PCT = 0.60                       # medido 2026-08-05 sobre 2.782 contratos
MIN_MID = 0.20                             # suelo del tick: 0.01/mid > 5% siempre por debajo
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


def _peaje(g):
    """peaje% = (ask-bid)/(|delta|*spot)*100: lo que debe moverse el SUBYACENTE para pagar
    la horquilla. None si falta delta valida o spot (jamas se inventa). delta -1 = n/d."""
    q = (g or {}).get("quote") or {}
    c = (g or {}).get("contract") or {}
    bid, ask = q.get("bid"), q.get("ask")
    d, spot = c.get("delta"), (g or {}).get("spot")
    if any(not isinstance(v, (int, float)) for v in (bid, ask, d, spot)):
        return None
    if ask <= bid or spot <= 0 or not (0.0 < abs(d) < 1.0):
        return None
    return (ask - bid) / (abs(d) * spot) * 100.0


def _survey(sym):
    """dict {spread_pct, spread_ok, peaje_pct, ok, veto_motivo} del BINARIO, o None.

    None cuando: no hay cadena, no hay epoch (frescura no verificable), la cadena esta
    VIEJA, o el contrato no cotiza (bid/ask -1.00 fuera de RTH). "No hay dato" jamas se
    devuelve como un numero bonito: eso era exactamente el fail-open.

    spread_ok NO se recalcula en Python (el gate acepta la frontera 5.0% con EPS; un `<=`
    suelto aqui la vetaria — un solo juez). Lo que SI añade Python (2026-08-06, medido):
    veto directo mid<0.20 (suelo del tick) y rescate por peaje<=0.60% cuando hay delta.
    """
    g = gate_json(sym)
    if not g or not (g.get("freshness") or {}).get("fresh"):
        return None
    q = g.get("quote") or {}
    pct = q.get("spread_pct")
    if not isinstance(pct, (int, float)):
        return None
    mid = q.get("mid")
    if isinstance(mid, (int, float)) and mid < MIN_MID:
        return {"spread_pct": float(pct), "spread_ok": False, "peaje_pct": None,
                "ok": False, "veto_motivo": "suelo del tick: mid<0.20 no puede pasar 5%"}
    peaje = _peaje(g)
    sok = bool(q.get("spread_ok"))
    return {"spread_pct": float(pct), "spread_ok": sok, "peaje_pct": peaje,
            "ok": sok or (peaje is not None and peaje <= MAX_PEAJE_PCT),
            "veto_motivo": None}


def opt_spread_pct(sym):
    """spread% (/mid) del primer OTM liquido, o None si NO hay veredicto posible."""
    s = _survey(sym)
    return s["spread_pct"] if s else None


def opt_peaje_pct(sym):
    """peaje% del primer OTM liquido, o None si no hay veredicto o falta delta."""
    s = _survey(sym)
    return s["peaje_pct"] if s else None


def opt_gate(sym, *args):
    """Veredicto completo del gate (GO/CAUTION/NO-GO + motivos) para quien quiera todo."""
    g = gate_json(sym, *args)
    if isinstance(g, dict):
        g["peaje_pct"] = _peaje(g)     # aditivo: no toca lo que emite el binario
    return g


def opt_vehicle(sym):
    s = _survey(sym)
    if s is None:
        return "OPCIONES s/d (sin cadena fresca) — default ACCIONES"
    pct, pj = s["spread_pct"], s["peaje_pct"]
    if s["veto_motivo"]:
        return f"OPCIONES VETADAS {s['veto_motivo']} — usar ACCIONES o ETF apalancado"
    if s["ok"]:
        if s["spread_ok"]:
            return f"OPCIONES OK (spread {pct:.0f}%)"
        return f"OPCIONES OK (spread {pct:.0f}%, peaje {pj:.2f}%)"
    if pj is not None:
        return (f"OPCIONES VETADAS spread {pct:.0f}% peaje {pj:.2f}% — "
                "usar ACCIONES o ETF apalancado")
    return f"OPCIONES VETADAS spread {pct:.0f}% — usar ACCIONES o ETF apalancado"


def opt_ok(sym):
    """True solo si SABEMOS que la horquilla es pagable (spread<=5% O peaje<=0.60%)."""
    s = _survey(sym)
    return bool(s and s["ok"])


def opt_veto(sym):
    """True solo si SABEMOS que el spread es malo (tres estados, no dos).

    Ni `not opt_ok()` ni `pct > 5` valen: el primero confunde "no hay cadena" con "spread
    malo" (silenciaria la flota un lunes antes del primer refresco) y el segundo vuelve a
    poner un umbral en Python. Ante ignorancia devuelve False: la señal grita.
    """
    s = _survey(sym)
    return s is not None and not s["ok"]


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["DRAM", "QQQ", "MU", "SKHY"]):
        print(s.upper(), "->", opt_vehicle(s))
