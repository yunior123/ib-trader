#!/usr/bin/env python3
"""position_close_reminder.py — aviso hablado de posiciones de OPCIONES que expiran HOY.

Hueco medido (auditoria 2026-07-28): el retirado opt_sentinel daba el "cierra HOY, jamas
overnight" y nadie lo heredo. Este lo da leyendo POSICIONES REALES de IBKR (readonly,
clientId 46), no un plan congelado. SENAL-SOLAMENTE: cero ordenes. Habla al detectar
(1 vez), a las 14:00 y a las 15:30; marcas persistidas por dia (tmp+rename).
Fuera de RTH o sin posiciones que expiren hoy: silencio. Conexion caida -> exit 75 (retry).
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import ib_mode

MARKS = os.path.join(REPO, "data", f"pos_close_marks_{dt.date.today():%Y%m%d}.json")
SLOTS = ("detect", "1400", "1530")


def say(msg):
    subprocess.Popen(["/bin/bash", "scripts/speak.sh", "SIGNAL", msg])
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      f'display notification "{msg}" with title "⏰ EXPIRA HOY"'],
                     stderr=subprocess.DEVNULL)
    p = os.path.join(REPO, "data", "trading-signals", f"{dt.date.today():%Y-%m-%d}.txt")
    with open(p, "a") as f:
        f.write(f"{dt.datetime.now():%H:%M:%S} | ⏰ EXPIRA HOY | {msg}\n")
    import notify_short; notify_short.push("⏰ EXPIRA HOY", msg)


def load_marks():
    try:
        return json.load(open(MARKS))
    except Exception:
        return {}


def save_marks(m):
    tmp = MARKS + ".tmp"
    json.dump(m, open(tmp, "w"))
    os.rename(tmp, MARKS)


def rth_now():
    n = dt.datetime.now()
    mins = n.hour * 60 + n.minute
    return n.weekday() < 5 and 570 <= mins < 960


def expiring_today(ib):
    hoy = f"{dt.date.today():%Y%m%d}"
    out = []
    for p in ib.positions():
        c = p.contract
        if c.secType == "OPT" and p.position != 0 and \
                c.lastTradeDateOrContractMonth == hoy:
            out.append(f"{c.symbol} {c.strike:g}{c.right}")
    return out


def main():
    if not rth_now():
        return 0
    try:
        from ib_async import IB
    except ImportError:
        from ib_insync import IB
    ib = IB()
    try:
        ib.connect("127.0.0.1", ib_mode.get_port(), clientId=46, readonly=True, timeout=15)
    except Exception as e:
        sys.stderr.write(f"position_close_reminder: sin TWS ({e})\n")
        return 75
    try:
        while rth_now():
            pos = expiring_today(ib)
            if pos:
                marks = load_marks()
                n = dt.datetime.now()
                hhmm = n.hour * 100 + n.minute
                slot = "detect" if "detect" not in marks else \
                       ("1400" if hhmm >= 1400 and "1400" not in marks else
                        ("1530" if hhmm >= 1530 and "1530" not in marks else None))
                if slot:
                    say(f"Tu opción de {', '.join(pos)} vence hoy. Véndela antes de las 3:50.")
                    marks[slot] = f"{n:%H:%M}"
                    save_marks(marks)
            ib.sleep(120)
    finally:
        ib.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
