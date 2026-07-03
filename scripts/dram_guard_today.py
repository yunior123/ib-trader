#!/usr/bin/env python3
"""dram_guard_today.py — guardian de DRAM y sus componentes (2026-07-22,
orden Yunior: "vigila DRAM... monitorea los tickers que la forman").

Cada 45s: momentum 5m de DRAM y componentes de memoria (MU SNDK WDC STX SKHY
LRCX + brujula SMH) desde data/bars_*_ibkr.txt. Canta (speak.sh + banner) SOLO
en CAMBIOS de estado (histeresis anti crying-wolf):
  - CONFLUENCIA VERDE: >=4 componentes suben 5m y DRAM rezagada -> candidato call
  - CONFLUENCIA ROJA:  >=4 caen -> veto call / atencion put
  - DRAM MOVIDA: |5m| >= 0.8% -> cantar direccion y niveles
Muere solo a las 16:00. Los niveles exactos (55.75/56.40/54.95/MU 940/SMH 550.5)
los canta price_alarm — esto es el CONTEXTO. SEÑAL-SOLAMENTE.
"""
import os, subprocess, time

_OSA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osa_gate")  # portero: respeta data/notify_off

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
COMPS = ["mu", "sndk", "wdc", "stx", "skhy", "lrcx"]

def say(title, msg, voice_msg=None):
    """voice_msg: version corta (Yunior 2026-07-28 "voces muy largas, resume")."""
    corto = voice_msg or msg
    subprocess.Popen(["/bin/bash", "scripts/speak.sh", "SIGNAL", corto],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen([_OSA, "-e",
                      f'display notification "{corto}" with title "{title}" sound name "ProAlert"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import notify_short; notify_short.push(title, corto)
    lt = time.localtime()
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | 🛡 DRAM GUARD | {msg}\n")

def chg5m(sym):
    """% de cambio de los ultimos 5 cierres 1m; None si data vieja."""
    try:
        lines = open(f"data/bars_{sym}_ibkr.txt").readlines()[-6:]
        rows = [l.split() for l in lines]
        if len(rows) < 6 or time.time() - float(rows[-1][0]) > 180:
            return None
        a, b = float(rows[0][4]), float(rows[-1][4])
        return (b / a - 1) * 100
    except Exception:
        return None

state = "ARRANQUE"
last_move_ts = 0
say("🛡 DRAM GUARD", "Guardian de DRAM arriba: componentes de memoria vigilados hasta las 4")
while True:
    lt = time.localtime()
    if lt.tm_hour >= 16:
        say("🛡 DRAM GUARD", "Cierre: guardian de DRAM fuera. Resumen en el log del Desktop")
        break
    d = chg5m("dram")
    comps = {s: chg5m(s) for s in COMPS}
    vivos = {s: c for s, c in comps.items() if c is not None}
    if d is not None and len(vivos) >= 4:
        up = sum(1 for c in vivos.values() if c > 0.10)
        dn = sum(1 for c in vivos.values() if c < -0.10)
        nuevo = "VERDE" if up >= 4 else "ROJA" if dn >= 4 else "MIXTA"
        # anti-parloteo (12:17): cantar SOLO en el giro VERDE<->ROJA real
        # (pasar por MIXTA no re-arma el canto del mismo color).
        if nuevo in ("VERDE", "ROJA") and nuevo != state:
            lider = max(vivos, key=lambda s: abs(vivos[s]))
            if nuevo == "VERDE":
                say("🟢 MEMORIA CONFLUENCIA", f"{up} de {len(vivos)} componentes suben, lider {lider.upper()} "
                    f"{vivos[lider]:+.1f}. DRAM {d:+.1f} — viento a favor del sector",
                    voice_msg="Memoria subiendo. DRAM a favor.")
            else:
                say("🔴 MEMORIA CONFLUENCIA", f"{dn} de {len(vivos)} componentes caen, lider {lider.upper()} "
                    f"{vivos[lider]:+.1f}. Viento en contra — proteger largos del sector",
                    voice_msg="Memoria bajando. Cuidado con DRAM.")
            state = nuevo
        if abs(d) >= 0.8 and time.time() - last_move_ts > 300:
            say("⚡ DRAM MOVIDA", f"DRAM {d:+.1f} por ciento en 5 minutos. "
                f"{'Hacia el techo 58' if d > 0 else 'Hacia el piso 55 — no cuchillos sin retest'}",
                voice_msg=f"DRAM se movió {'para arriba' if d > 0 else 'para abajo'}.")
            last_move_ts = time.time()
    time.sleep(45)
