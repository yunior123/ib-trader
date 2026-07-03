#!/usr/bin/env python3
"""today_alarm5.py — alarmas de ENTRADA que expiran HOY (Yunior 2026-07-28: "arma alarmas
que expiren hoy para comprar nvda, aapl, mu, dram, skhy, calls or puts").

Vigia SOLO estos 5 simbolos (lista fija de Yunior, no data/fleet.txt). Corre `./level_react
--sym <SYM>` (primitivo C++, doctrina print-o-nada: BOUNCE/RETEST_REJECT + printed = los
UNICOS eventos operables, jamas TOUCH) cada POLL_S, siembra el baseline sin cantar en el
primer scan (patron opt_whale_watch), y ante un evento operable NUEVO arma la ficha con
order_ticket.build() + el gate de spread canonico optgate.opt_vehicle() (CLAUDE.md #4) y
canta por voz.

Lado: dist_atr>0 al cierre del evento -> CALL (cerro por ENCIMA del nivel); dist_atr<0 ->
PUT (cerro por DEBAJO). SIEMPRE side=buy (Yunior pidio "comprar").

Expira solo: el loop revisa gex_core.in_rth() cada vuelta y sale del todo en cuanto el
mercado cierra hoy — sin keepalive, sin relanzamiento, mañana no existe. SEÑAL-SOLAMENTE.
"""
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gex_core
import optgate
import order_ticket

_OSA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osa_gate")  # portero: respeta data/notify_off

SYMS = ["NVDA", "AAPL", "MU", "DRAM", "SKHY"]
POLL_S = 25
# bin/ primero, raiz de respaldo: la mudanza a bin/ dejo esta ruta apuntando al sitio viejo.
LEVEL_REACT = next((_p for _p in (os.path.join(REPO, "bin", "level_react"), os.path.join(REPO, "level_react"))
               if os.access(_p, os.X_OK)), os.path.join(REPO, "bin", "level_react"))
FIRED_LOG = os.path.join(REPO, "data", "today_alarm5_fired.jsonl")


def loud(title, msg, sound="ProAlert", voice_msg=None):
    """voice_msg: version corta para la voz (Yunior 2026-07-28 "sencillo, que un niño
    pequeño pueda entender"); el banner/log se quedan con la ficha completa."""
    corto = voice_msg or msg
    subprocess.Popen([_OSA, "-e",
        f'display notification "{corto}" with title "{title}" sound name "{sound}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/bin/bash", "scripts/speak.sh", "SIGNAL", corto],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import notify_short; notify_short.push(title, corto)
    lt = time.localtime()
    d = os.path.join(REPO, "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")


def jappend(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def tradeable_events(sym):
    try:
        out = subprocess.run([LEVEL_REACT, "--sym", sym], capture_output=True,
                              timeout=15, text=True).stdout
        d = json.loads(out)
    except Exception as e:
        print(f"{sym}: level_react fallo ({e})", file=sys.stderr)
        return []
    return [e for e in d.get("events", []) if e.get("tradeable")]


def veto_suffix(sym):
    try:
        c = json.load(open(f"data/compass_{sym.lower()}.json"))
        if c.get("vetoes"):
            return " | " + "; ".join(c["vetoes"][:1])
    except Exception:
        pass
    return ""


VOICE_COOLDOWN_S = 1800.0
_voz_cooldown = {}


def _instancia_unica():
    """Candado: manana a las 09:31 el cron de launchd y un arranque manual doblarian la voz
    (medido hoy: multiples 'armado' en el log y 4 pushes en el mismo segundo)."""
    import fcntl
    fd = os.open(os.path.join(REPO, "data", ".today_alarm5.lock"),
                 os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("today_alarm5: ya hay una instancia viva — me voy", file=sys.stderr)
        sys.exit(0)
    return fd            # se mantiene abierto: el lock vive lo que el proceso


def main():
    _lock = _instancia_unica()  # noqa: F841
    if gex_core.in_rth() is not True:
        print("today_alarm5: mercado cerrado ahora mismo, nada que armar hoy", file=sys.stderr)
        return
    last_seen = {}
    for s in SYMS:
        ev = tradeable_events(s)
        last_seen[s] = max((e["ts"] for e in ev), default=0)
    print(f"today_alarm5: armado {SYMS}, baseline sembrado, expira al cierre de hoy",
          file=sys.stderr)
    while gex_core.in_rth():
        for s in SYMS:
            for e in tradeable_events(s):
                if e["ts"] <= last_seen[s]:
                    continue
                last_seen[s] = max(last_seen[s], e["ts"])
                kind = "call" if e["dist_atr"] > 0 else "put"
                t = order_ticket.build(s, e["level_px"], "buy", kind)
                gate = optgate.opt_vehicle(s)
                msg = (f"{s} {e['event']} en {e['level_type']} {e['level_px']:g} — "
                       f"{t['ticket']} | {gate}{veto_suffix(s)}")
                icon = "🟢" if t["verdict"] == "GO" else "🟡" if t["verdict"] == "CAUTION" else "🔴"
                # SOLO GO interrumpe (Yunior 2026-08-04: "con cuidado call de nvda is bad, it
                # repeats 3 times plus its a bad signal"). Un CAUTION por "sale muy caro" no es
                # accionable: se REGISTRA (FIRED_LOG + trading-signals) y calla. Y cooldown por
                # (sym,kind): 4 niveles cruzando en el MISMO poll eran 4 voces identicas.
                ck = (s, kind)
                en_cooldown = time.time() - _voz_cooldown.get(ck, 0) < VOICE_COOLDOWN_S
                if t["verdict"] != "GO" or en_cooldown:
                    motivo = "cooldown" if en_cooldown else t["verdict"]
                    print(f"{s} {kind}: registrado sin voz ({motivo}) — {msg[:80]}")
                    jappend(FIRED_LOG, {"ts": int(time.time()), "sym": s, "event": e,
                                        "ticket": t, "gate": gate, "silenciada": motivo})
                    continue
                _voz_cooldown[ck] = time.time()
                if t["verdict"] == "GO":
                    voz = f"Compra {kind} de {s}."
                else:
                    # razon corta y precisa (Yunior 2026-07-28: "no compres call de micron.
                    # esta loco eso, no se entiende, se preciso") -- el porque, no solo el veto.
                    if not t.get("fresh", True):
                        razon = "datos viejos"
                    elif not t.get("spread_ok", True):
                        razon = "el spread está muy ancho"
                    elif not t.get("oi_ok", True):
                        razon = "poca liquidez"
                    elif not t.get("budget_ok", True):
                        razon = "sale muy caro"
                    else:
                        razon = "sin ventaja ahora"
                    if t["verdict"] == "CAUTION":
                        voz = f"Con cuidado, {kind} de {s}: {razon}."
                    else:
                        voz = f"No compres {kind} de {s}: {razon}."
                loud(f"{icon} {s} {kind.upper()} {e['event']}", msg, voice_msg=voz)
                jappend(FIRED_LOG, {"ts": int(time.time()), "sym": s, "event": e,
                                     "ticket": t, "gate": gate})
        time.sleep(POLL_S)
    print("today_alarm5: mercado cerro, alarmas de hoy EXPIRADAS, saliendo", file=sys.stderr)


if __name__ == "__main__":
    main()
