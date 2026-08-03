#!/usr/bin/env python3
"""capitulacion_qqq.py — alarma de CAPITULACION para QQQ (Yunior 2026-07-28: "ya se hizo la
acumulacion, la manipulacion esta apunto de terminar, viene la distribucion, monta alerta para
cuando la flota se ponga de acuerdo para la capitulacion").

Dispara SOLO cuando las TRES condiciones coinciden dentro de una ventana de 20 min:
  1. MANADA BAJISTA de fleet_consensus.py (78% de la flota + 3 capitanes de acuerdo,
     data/consensus_signals.jsonl) -- "la flota se pone de acuerdo".
  2. QQQ rompe con PRINT CONFIRMADO (RETEST_REJECT, no BOUNCE -- doctrina print-o-nada:
     BOUNCE es rebote, RETEST_REJECT con cierre por debajo es la ruptura que SIGUE)
     via ./level_react --sym QQQ.
  3. Regimen gamma NEG en QQQ (recalculado en vivo, gex_core) -- los dealers amplifican,
     el break corre en vez de rebotar; sin esto una ruptura confirmada aun podria
     encontrar piso, no es capitulacion.

Sin las tres, NO canta -- una manada sola, o un break solo, no es capitulacion.
SEÑAL-SOLAMENTE. Corre mientras el mercado este abierto (gex_core.in_rth()), sin fecha
de caducidad (esto es una tesis de ciclo, no un intradia)."""
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gex_core
import notify_short

SYM = "QQQ"
MANADA_WINDOW_S = 20 * 60
POLL_S = 30
# bin/ primero, raiz de respaldo: la mudanza a bin/ dejo esta ruta apuntando al sitio viejo.
LEVEL_REACT = next((_p for _p in (os.path.join(REPO, "bin", "level_react"), os.path.join(REPO, "level_react"))
               if os.access(_p, os.X_OK)), os.path.join(REPO, "bin", "level_react"))
CONSENSUS_F = os.path.join(REPO, "data", "consensus_signals.jsonl")


def loud(title, msg, sound="ProAlarm", voice_msg=None):
    corto = voice_msg or msg
    subprocess.Popen(["/usr/bin/osascript", "-e",
        f'display notification "{corto}" with title "{title}" sound name "{sound}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/bin/bash", "scripts/speak.sh", "DANGER", corto],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt = time.localtime()
    d = os.path.join(REPO, "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")
    notify_short.push(title, corto)


def manada_bajista_reciente():
    """Ultima MANADA DOWN dentro de la ventana. None si no hay o esta vieja."""
    if not os.path.exists(CONSENSUS_F):
        return None
    now = time.time()
    best = None
    with open(CONSENSUS_F) as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("dir") == "DOWN" and now - r.get("ts", 0) <= MANADA_WINDOW_S:
                if best is None or r["ts"] > best["ts"]:
                    best = r
    return best


def qqq_tradeable_events():
    try:
        out = subprocess.run([LEVEL_REACT, "--sym", SYM], capture_output=True,
                              timeout=15, text=True).stdout
        d = json.loads(out)
    except Exception as e:
        print(f"capitulacion_qqq: level_react fallo ({e})", file=sys.stderr)
        return []
    return d.get("events", [])


def qqq_regime_neg():
    """Recalculado en vivo (cadena IBKR cacheada, exp mas cercana). None si no se puede medir."""
    path = os.path.join(REPO, "data", f"opt_chain_{SYM.lower()}.txt")
    try:
        rows, spot, exp0 = [], None, None
        with open(path) as f:
            for ln in f:
                if ln.startswith("#"):
                    if "spot" in ln:
                        p = ln.split(); spot = float(p[p.index("spot") + 1])
                    continue
                t = ln.split()
                if len(t) < 10:
                    continue
                strike, right, exp, bid, ask, vol, oi, iv, delta, gamma = t
                if exp0 is None:
                    exp0 = exp
                if exp != exp0:
                    continue
                rows.append({"strike": float(strike), "right": right, "oi": float(oi),
                             "gamma": float(gamma)})
        if not rows or spot is None:
            return None
        g = gex_core.build_gex(rows, spot, scale="house")
        return g.get("regime") == "NEG"
    except Exception as e:
        print(f"capitulacion_qqq: regimen fallo ({e})", file=sys.stderr)
        return None


def main():
    if gex_core.in_rth() is not True:
        print("capitulacion_qqq: mercado cerrado, nada que vigilar ahora", file=sys.stderr)
        return
    last_seen = max((e["ts"] for e in qqq_tradeable_events() if e.get("tradeable")), default=0)
    print("capitulacion_qqq: armado (manada bajista + break confirmado QQQ + regimen NEG)",
          file=sys.stderr)
    while gex_core.in_rth():
        for e in qqq_tradeable_events():
            if not e.get("tradeable") or e["ts"] <= last_seen:
                continue
            last_seen = max(last_seen, e["ts"])
            if e["event"] != "RETEST_REJECT" or e["dist_atr"] >= 0:
                continue   # BOUNCE o cierre arriba = rebote, no es la ruptura que sigue
            manada = manada_bajista_reciente()
            if not manada:
                continue
            neg = qqq_regime_neg()
            if neg is not True:
                continue
            msg = (f"CAPITULACION QQQ: manada bajista ({manada['aligned']}/{manada['n_fleet']}, "
                   f"hace {int(time.time() - manada['ts'])}s) + ruptura confirmada en "
                   f"{e['level_type']} {e['level_px']:g} + regimen NEG — las tres condiciones "
                   f"se cumplieron. No es consejo financiero.")
            loud("💀 CAPITULACION QQQ", msg,
                 voice_msg="Capitulación en QQQ. Manada, ruptura y régimen negativo, las tres.")
        time.sleep(POLL_S)
    print("capitulacion_qqq: mercado cerro, salgo", file=sys.stderr)


if __name__ == "__main__":
    main()
