#!/usr/bin/env python3
"""fleet_consensus.py — alarma de MANADA: dispara cuando TODA la flota se pone de acuerdo
en una dirección (orden Yunior 2026-07-24: "comprar puts/calls cuando todos se pongan de
acuerdo en ir en una direccion").

Condición CRUZADA (no de un precio) -> monitor propio. Voto por símbolo = lado del flip
(estructural) confirmado por momentum. CONSENSO cuando:
  (a) los 3 CAPITANES (SPY/QQQ/SMH) coinciden en dirección  Y
  (b) >= UMBRAL % de la flota está del mismo lado.
Al dispararse: voz DANGER + señal (data/trading-signals -> BD + teléfono) + vehículo
(calls si arriba / puts si abajo) + nota de gate de opciones (spread). Histéresis: solo
en la TRANSICIÓN a consenso, y persiste 2 ciclos (anti-flicker). SEÑAL-SOLAMENTE.

Uso: python3 scripts/fleet_consensus.py --once | --daemon
Umbral: env FLEET_CONS_PCT (default 78).
"""
import os, sys, time, subprocess, statistics as st, datetime as dt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
import chart_levels

FLEET = open("data/fleet.txt").read().split()
CAPS = ["SPY", "QQQ", "SMH"]
PCT = float(os.environ.get("FLEET_CONS_PCT", "78"))
SIGDIR = os.path.join(REPO, "data", "trading-signals")


def _pb(c, n=20):
    if len(c) < n:
        return 0.5
    w = c[-n:]; m = st.mean(w); sd = st.pstdev(w); up = m + 2 * sd; lo = m - 2 * sd
    return (c[-1] - lo) / (up - lo) if up > lo else 0.5


def snapshot():
    """Devuelve (up, dn, n, caps_dir, mom_up, mom_dn) del estado actual de la flota."""
    up = dn = 0; caps = {}; mom_up = mom_dn = 0
    for s in FLEET:
        try:
            r = [l.split() for l in open(f"data/bars_{s.lower()}_ibkr.txt") if l.strip()]
            c1 = [float(x[4]) for x in r]
            if len(c1) < 7:
                continue
            spot = c1[-1]
            lv = chart_levels.gen(s, spot=spot, write=False)
            if not lv or not lv.get("flip"):
                continue
            mom = 100 * (c1[-1] - c1[-6]) / c1[-6]
            side = 1 if spot >= lv["flip"] else -1
            if side > 0:
                up += 1; mom_up += 1 if mom > 0.03 else 0
            else:
                dn += 1; mom_dn += 1 if mom < -0.03 else 0
            if s in CAPS:
                caps[s] = "UP" if side > 0 else "DN"
        except Exception:
            continue
    return up, dn, up + dn, caps, mom_up, mom_dn


def consensus_dir(up, dn, n, caps):
    """Devuelve 'UP'/'DN'/None. Requiere capitanes unánimes + flota >= PCT del mismo lado."""
    if n == 0 or len(caps) < 3:
        return None
    cap_set = set(caps.values())
    if len(cap_set) != 1:
        return None                      # capitanes divididos -> sin consenso
    cdir = cap_set.pop()
    pct = 100 * (up if cdir == "UP" else dn) / n
    if pct >= PCT:
        return cdir
    return None


def fire(cdir, up, dn, n, mom_up, mom_dn):
    veh = "CALLS" if cdir == "UP" else "PUTS"
    aligned = up if cdir == "UP" else dn
    mom = mom_up if cdir == "UP" else mom_dn
    arrow = "📈" if cdir == "UP" else "📉"
    msg = (f"🐘 MANADA {'ALCISTA' if cdir=='UP' else 'BAJISTA'} {arrow}: {aligned}/{n} de la flota "
           f"alineados {'ARRIBA' if cdir=='UP' else 'ABAJO'} del flip + los 3 capitanes de acuerdo "
           f"({mom} con momentum). Sesgo direccional FUERTE -> comprar {veh}. "
           f"VERIFICA spread <=5% y print antes de entrar (optgate). No es consejo financiero.")
    # voz DANGER
    try:
        subprocess.Popen(["/bin/bash", "scripts/speak.sh", "DANGER",
                          f"Manada {'alcista' if cdir=='UP' else 'bajista'}: la flota se puso de acuerdo. Comprar {veh.lower()}."],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    # notificación Mac
    try:
        subprocess.Popen(["/usr/bin/osascript", "-e",
                          f'display notification "{aligned}/{n} alineados -> {veh}" with title "🐘 MANADA {cdir}" sound name "Hero"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    # señal al archivo (BD + teléfono via notify_relay)
    try:
        os.makedirs(SIGDIR, exist_ok=True)
        ts = time.strftime("%H:%M:%S")
        with open(f"{SIGDIR}/{dt.date.today():%Y-%m-%d}.txt", "a") as f:
            f.write(f"{ts} | 🐘 MANADA {'ALCISTA' if cdir=='UP' else 'BAJISTA'} | {msg}\n")
    except Exception:
        pass
    print(f"[consensus] DISPARADA {cdir}: {aligned}/{n}")


def main():
    once = "--once" in sys.argv
    last = None      # último consenso disparado ("UP"/"DN"/None)
    pending = None; pend_cnt = 0
    print(f"[consensus] monitor MANADA — umbral {PCT}% + capitanes unánimes")
    while True:
        up, dn, n, caps, mu, md = snapshot()
        cdir = consensus_dir(up, dn, n, caps)
        dom = 100 * max(up, dn) / n if n else 0
        print(f"  {time.strftime('%H:%M:%S')} flota {up}↑/{dn}↓ ({dom:.0f}% dom) caps={caps} -> consenso={cdir or 'no'}")
        # histéresis: persistir 2 ciclos antes de disparar; solo en transición
        if cdir and cdir != last:
            if pending == cdir:
                pend_cnt += 1
            else:
                pending = cdir; pend_cnt = 1
            if pend_cnt >= 2:
                fire(cdir, up, dn, n, mu, md); last = cdir; pending = None; pend_cnt = 0
        elif not cdir:
            last = None; pending = None; pend_cnt = 0   # consenso roto -> re-armar
        if once:
            if not cdir:
                print("  -> sin consenso ahora (flota dividida o capitanes discordes)")
            break
        time.sleep(45)


if __name__ == "__main__":
    main()
