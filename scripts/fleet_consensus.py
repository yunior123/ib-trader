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
MAX_BAR_AGE = float(os.environ.get("FLEET_CONS_MAX_BAR_AGE", "180"))   # s; barras mas viejas no votan
MIN_COVER = float(os.environ.get("FLEET_CONS_MIN_COVER", "0.90"))      # cobertura minima de la flota
WIN_OPEN = int(os.environ.get("FLEET_CONS_WIN_OPEN", str(9 * 60 + 25)))    # 09:25
WIN_CLOSE = int(os.environ.get("FLEET_CONS_WIN_CLOSE", str(16 * 60 + 5)))  # 16:05
SIGDIR = os.path.join(REPO, "data", "trading-signals")


def _pb(c, n=20):
    # None, no 0.5: un %B de 0.5 dice "en el centro de la banda, nada que ver" cuando la
    # verdad es "no se". Indistinguible de una medicion real (fix 2026-07-25).
    if len(c) < n:
        return None
    w = c[-n:]; m = st.mean(w); sd = st.pstdev(w); up = m + 2 * sd; lo = m - 2 * sd
    return (c[-1] - lo) / (up - lo) if up > lo else 0.5


def snapshot():
    """Devuelve (up, dn, n, caps_dir, mom_up, mom_dn, skipped) del estado de la flota.

    `skipped` = {sym: motivo} de los que NO votaron. Es la pieza clave: antes se hacía
    `continue` en silencio y el símbolo desaparecía del DENOMINADOR, no solo del numerador.
    """
    up = dn = 0; caps = {}; mom_up = mom_dn = 0; skipped = {}
    now = time.time()
    for s in FLEET:
        try:
            p = f"data/bars_{s.lower()}_ibkr.txt"
            # FRESCURA (fix 2026-07-25): sin esto el daemon emitia veredictos con barras de
            # 11 horas. El disparo de las 00:00:45 fue un artefacto de rollover de fecha
            # (chart_levels rueda de expiry), no un movimiento de mercado.
            age = now - os.path.getmtime(p)
            if age > MAX_BAR_AGE:
                skipped[s] = f"barras rancias ({age/60:.0f}min)"
                continue
            r = [l.split() for l in open(p) if l.strip()]
            c1 = [float(x[4]) for x in r]
            if len(c1) < 7:
                skipped[s] = "menos de 7 barras"
                continue
            spot = c1[-1]
            lv = chart_levels.gen(s, spot=spot, write=False)
            if not lv or not lv.get("flip"):
                skipped[s] = "sin flip en el mapa GEX"
                continue
            mom = 100 * (c1[-1] - c1[-6]) / c1[-6]
            side = 1 if spot >= lv["flip"] else -1
            if side > 0:
                up += 1; mom_up += 1 if mom > 0.03 else 0
            else:
                dn += 1; mom_dn += 1 if mom < -0.03 else 0
            if s in CAPS:
                caps[s] = "UP" if side > 0 else "DN"
        except Exception as e:
            skipped[s] = f"{type(e).__name__}: {e}"
            continue
    return up, dn, up + dn, caps, mom_up, mom_dn, skipped


def consensus_dir(up, dn, n, caps, skipped=None):
    """Devuelve ('UP'|'DN'|None, motivo). Capitanes unánimes + flota >= PCT del mismo lado,
    y COBERTURA suficiente.

    FIX 2026-07-25 — la alarma disparó 3 veces hoy sobre un denominador fabricado:
    4 símbolos (NFLX/GLD/XLK/EWY) fallaban en silencio, así que n=26 en vez de 30 y
    21/26 = 80.8% >= 78% DISPARABA, cuando 21/30 = 70% NO debía. El porcentaje se calcula
    ahora sobre la FLOTA COMPLETA y por debajo de MIN_COVER no hay veredicto direccional:
    una cobertura mala es un problema de FEED, no una dirección del mercado.
    """
    need = int(len(FLEET) * MIN_COVER)
    if n < need:
        return None, (f"cobertura insuficiente {n}/{len(FLEET)} (min {need}) — "
                      f"esto es FEED, no direccion")
    if len(caps) < 3:
        return None, f"faltan capitanes ({len(caps)}/3)"
    cap_set = set(caps.values())
    if len(cap_set) != 1:
        return None, "capitanes divididos"
    cdir = cap_set.pop()
    aligned = up if cdir == "UP" else dn
    pct = 100 * aligned / len(FLEET)          # <- FLOTA COMPLETA, no los que parsearon
    if pct >= PCT:
        return cdir, f"{aligned}/{len(FLEET)} = {pct:.0f}%"
    return None, f"{aligned}/{len(FLEET)} = {pct:.0f}% < {PCT:.0f}%"


def fire(cdir, up, dn, n, mom_up, mom_dn, skipped=None):
    veh = "CALLS" if cdir == "UP" else "PUTS"
    aligned = up if cdir == "UP" else dn
    mom = mom_up if cdir == "UP" else mom_dn
    arrow = "📈" if cdir == "UP" else "📉"
    nf = len(FLEET)
    faltan = f" ({len(skipped)} sin voto)" if skipped else ""
    msg = (f"🐘 MANADA {'ALCISTA' if cdir=='UP' else 'BAJISTA'} {arrow}: {aligned}/{nf}{faltan} de la flota "
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
                          f'display notification "{aligned}/{nf} alineados -> {veh}" with title "🐘 MANADA {cdir}" sound name "Hero"'],
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
    print(f"[consensus] DISPARADA {cdir}: {aligned}/{nf} (n={n}, sin voto {len(skipped or {})})")


def main():
    once = "--once" in sys.argv
    last = None      # último consenso disparado ("UP"/"DN"/None)
    pending = None; pend_cnt = 0
    print(f"[consensus] monitor MANADA — umbral {PCT}% + capitanes unánimes")
    while True:
        up, dn, n, caps, mu, md, skipped = snapshot()
        cdir, why = consensus_dir(up, dn, n, caps, skipped)
        dom = 100 * max(up, dn) / len(FLEET)
        print(f"  {time.strftime('%H:%M:%S')} flota {up}↑/{dn}↓ de {len(FLEET)} "
              f"({dom:.0f}% dom, n={n}) caps={caps} -> consenso={cdir or 'no'} [{why}]")
        if skipped:
            print(f"    NO VOTARON ({len(skipped)}): " +
                  ", ".join(f"{k}={v}" for k, v in list(skipped.items())[:6]))
        # ventana horaria: fuera de sesion no hay veredicto direccional (rollover, feeds caidos)
        nowm = time.localtime().tm_hour * 60 + time.localtime().tm_min
        if not (WIN_OPEN <= nowm <= WIN_CLOSE):
            if cdir:
                print(f"    fuera de ventana {WIN_OPEN//60}:{WIN_OPEN%60:02d}-"
                      f"{WIN_CLOSE//60}:{WIN_CLOSE%60:02d}: no se dispara")
            cdir = None
        # histéresis: persistir 2 ciclos antes de disparar; solo en transición
        if cdir and cdir != last:
            if pending == cdir:
                pend_cnt += 1
            else:
                pending = cdir; pend_cnt = 1
            if pend_cnt >= 2:
                fire(cdir, up, dn, n, mu, md, skipped); last = cdir; pending = None; pend_cnt = 0
        elif not cdir:
            last = None; pending = None; pend_cnt = 0   # consenso roto -> re-armar
        if once:
            if not cdir:
                print("  -> sin consenso ahora (flota dividida o capitanes discordes)")
            break
        time.sleep(45)


if __name__ == "__main__":
    main()
