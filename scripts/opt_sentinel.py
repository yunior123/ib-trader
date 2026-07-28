#!/usr/bin/env python3
"""opt_sentinel.py — centinela de opciones (creado 2026-07-16 9:20 pre-open).
SEÑAL-SOLAMENTE (ley #0). Dos misiones:

1. EXIT ADVISOR del INTC 104C 17-jul de Yunior: vigila NBBO INTC + premium del
   call en vivo y GRITA (sirena+voz+Desktop) cuando toca vender segun las
   reglas acordadas: pop que se estanca / target 102.5+ / ruptura <100 /
   time-stop 10:15. Cada regla dispara UNA vez.

2. FLUJO PUT/CALL de la flota: cada 5 min lee volumen de opciones del dia
   (puts vs calls ±3% ATM, 17-jul) via OPRA y alerta si el put-flow se
   dispara. Escribe data/opt_flow.txt + espejo Desktop.

Python permitido: ib_insync lo exige (regla #4). ClientId 86. Jamas ordena.
"""
import datetime as dt
import os
import subprocess
import sys
import time

from ib_insync import IB, Option, Stock

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear: el repo se movio a ~/ib-trader (TCC/launchd, 2026-07-25)
os.chdir(REPO)
MIRROR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
SIREN = os.path.join(REPO, "sounds/fire_alarm.wav")

# FLOTA COMPLETA (orden Yunior 2026-07-16: "las alarmas de opciones para toda
# la flota, not just semis"). Umbral de volumen por liquidez del libro.
FLEET_OPT = ["INTC", "MU", "TSM", "SMH", "QQQ", "NVDA", "AMD",
             "TSLA", "AAPL", "GOOGL", "QCOM", "ASML", "TXN", "NOK",
             "DRAM", "SKHY", "SPCX"]
FLOW_MIN = {"ASML": 300, "GOOGL": 300, "TXN": 500, "NOK": 500,
            "DRAM": 800, "SKHY": 800, "SPCX": 800, "QCOM": 500}  # resto: 2000
EXP = "20260717"

# GUARD FRESCURA (2026-07-28): este centinela es la foto del plan 2026-07-16.
# Con EXP vencido canto "VENDE YA" de posiciones muertas y "FLUJO OPCIONES volC 0
# volP 0" fabricado 174 veces el 2026-07-27. Dato viejo NO se canta: fuera, a gritos.
# opt_whale_watch.py lo reemplaza (mismo data/opt_flow.txt, expiries rodantes).
if dt.date.today() > dt.datetime.strptime(EXP, "%Y%m%d").date():
    sys.stderr.write(f"{dt.datetime.now():%F %T} opt_sentinel RETIRADO: EXP {EXP} "
                     "vencido — plan 2026-07-16, no se canta con datos viejos. "
                     "Vive opt_whale_watch.py\n")
    sys.exit(78)  # EX_CONFIG: el keepalive lo ve y NO relanza

def now():
    return dt.datetime.now()

def mirror_line(msg):
    line = f"{now():%H:%M:%S} | {msg}"
    print(line, flush=True)
    with open(os.path.join(MIRROR, f"{now():%Y-%m-%d}.txt"), "a") as f:
        f.write(line + "\n")

def shout(msg, voice_msg, urgent=False):
    mirror_line(("🚨 " if urgent else "🔔 ") + msg)
    # banner Mac (orden 2026-07-16 "notifications in mac too, real quick") —
    # mismo camino 1.5ms que fleet_notify.h: osascript directo, no bloquea
    try:
        safe = msg.replace('"', "'")[:180]
        subprocess.Popen(["/usr/bin/osascript", "-e",
                          f'display notification "{safe}" with title "OPCIONES {"URGENTE" if urgent else ""}" sound name "Sosumi"'])
    except Exception:
        pass
    def _audio():
        try:
            n = 3 if urgent else 1
            for _ in range(n):
                if os.path.exists(SIREN):
                    subprocess.run(["afplay", SIREN], timeout=15)
            subprocess.run(["say", "-v", "Paulina", voice_msg], timeout=30)
        except Exception:
            pass
    import threading
    threading.Thread(target=_audio, daemon=True).start()

def read_nbbo(sym):
    try:
        with open(f"data/nbbo_{sym.lower()}.txt") as f:
            ts, bid, ask = f.read().split()[:3]
        if time.time() - int(ts) > 30:
            return None
        return (float(bid) + float(ask)) / 2
    except Exception:
        return None

from ib_mode import get_port  # fuente unica: data/ib_mode.txt (paper/live), no 4002 a ciegas
ib = IB()
ib.connect("127.0.0.1", get_port(), clientId=85, timeout=15)
ib.RequestTimeout = 15   # causa raiz 2026-07-28 (opt_whale_watch.py): sin esto, qualifyContracts cuelga para siempre si TWS no responde
mirror_line("opt_sentinel ARRANCADO (exit-advisor INTC 104C + flujo put/call flota)")

# --- suscripcion streaming al 104C ---
call104 = Option("INTC", EXP, 104.0, "C", "SMART", currency="USD", tradingClass="INTC")
ib.qualifyContracts(call104)
t104 = ib.reqMktData(call104, "", False, False)

# --- contratos ATM de flota para flujo (se refrescan cada ciclo con el spot) ---
stks = {s: Stock(s, "SMART", "USD") for s in FLEET_OPT}
ib.qualifyContracts(*stks.values())
chains = {}
for s in FLEET_OPT:
    try:
        ch = ib.reqSecDefOptParams(s, "", "STK", stks[s].conId)
        chains[s] = sorted(next(c for c in ch if c.exchange == "SMART").strikes)
    except Exception:
        chains[s] = []

fired = set()          # reglas ya disparadas
flow_pc = {}           # sym -> P/C de VOLUMEN del dia (monitor cada 5 min)
hi_after_open = 0.0    # high watermark post-9:30
hi_time = None
or_high = or_low = None
last_flow = 0.0
open_t = now().replace(hour=9, minute=30, second=0, microsecond=0)

COST_104C = 256.0  # lo pagado por el contrato (Yunior 2026-07-16)

def call_premium():
    b, a = t104.bid, t104.ask
    if b == b and b > 0:
        val = b * 100  # venta al bid
        pnl = val - COST_104C
        return (f"bid {b:.2f}/ask {a:.2f} | valor {val:.0f} USD | "
                f"P&L {pnl:+.0f} USD ({pnl / COST_104C * 100:+.0f}%)")
    return "premium n/d"

def call_pnl_voice():
    b = t104.bid
    if b == b and b > 0:
        pnl = b * 100 - COST_104C
        return f" {'Mas' if pnl >= 0 else 'Menos'} {abs(pnl):.0f}."
    return ""

def rule(key, cond, msg, voice, urgent=False):
    if key not in fired and cond:
        fired.add(key)
        shout(f"INTC 104C: {msg} | {call_premium()}", voice + call_pnl_voice(), urgent)

while True:
    t = now()
    # ===== MOTOR DE ENTRADA DE PUTS (Yunior vendio el 104C 09:3x) =====
    # Regla: rebote-fallido = romper el MINIMO del opening range (9:30-9:45)
    # despues de las 9:45, confirmado 2 lecturas. Una señal por ticker.
    # sym: (target_put, target_call) — muros de OI del scan 2026-07-16
    SIG_MAP = {
        "MU": (850, 900), "TSM": (400, 419), "SMH": (565, 585),
        "INTC": (95, 103.5), "QQQ": (705, 717), "AMD": (500, 525),
        "NVDA": (201, 215), "DRAM": (51, 57), "TSLA": (385, 400),
    }
    if not hasattr(rule, "orx"):
        rule.orx = {}    # sym -> (lo, hi)
        rule.below = {}
        rule.above = {}
    or_end = open_t + dt.timedelta(minutes=15)
    for sym, (tgt_put, tgt_call) in SIG_MAP.items():
        px = read_nbbo(sym)
        if not px or t < open_t:
            continue
        if t <= or_end:
            lo, hi = rule.orx.get(sym, (px, px))
            rule.orx[sym] = (min(lo, px), max(hi, px))
            continue
        if sym not in rule.orx:
            continue
        or_lo, or_hi = rule.orx[sym]
        rule.below[sym] = rule.below.get(sym, 0) + 1 if px < or_lo * 0.9985 else 0
        rule.above[sym] = rule.above.get(sym, 0) + 1 if px > or_hi * 1.0015 else 0
        strike = round(px)
        # filtro de flujo del dia (si el monitor ya midio): puts confirman put, calls confirman call
        pc = flow_pc.get(sym)
        flow_note = f" | flujo P/C hoy {pc:.2f}" if pc else ""
        # NVDA solo con QQQ alineado (cascada real, no ruido)
        qpx = read_nbbo("QQQ")
        qlo, qhi = rule.orx.get("QQQ", (0, 0))
        nvda_dn_ok = sym != "NVDA" or bool(qpx and qlo and qpx < qlo)
        nvda_up_ok = sym != "NVDA" or bool(qpx and qhi and qpx > qhi)
        rule(f"put_{sym}", rule.below.get(sym, 0) >= 2 and nvda_dn_ok
             and (pc is None or pc >= 0.8),
             f"COMPRAR PUT {sym} ~{strike} (rompio minimo del open {or_lo:.2f}, px {px:.2f})"
             f" | target {tgt_put} | stop: recupera {or_lo:.2f}{flow_note}",
             f"Comprar put de {sym} ahora. Rompio el minimo de la apertura.", True)
        rule(f"call_{sym}", rule.above.get(sym, 0) >= 2 and nvda_up_ok
             and (pc is None or pc <= 1.3),
             f"COMPRAR CALL {sym} ~{strike} (rompio maximo del open {or_hi:.2f}, px {px:.2f})"
             f" | target {tgt_call} | stop: recupera {or_hi:.2f}{flow_note}",
             f"Comprar call de {sym} ahora. Rompio el maximo de la apertura.", True)
    # ===== EXIT ADVISOR del INTC 101C de Yunior (comprado 10:09; NVDA/QQQ puts
    # ya vendidos — sus reglas quedan inertes al no re-disparar) =====
    ipx = read_nbbo("INTC")
    if ipx:
        if not hasattr(rule, "intc_hi"):
            rule.intc_hi, rule.intc_hit = 0.0, None
        if ipx > rule.intc_hi:
            rule.intc_hi, rule.intc_hit = ipx, t
        rule("ic_stop", ipx < 99.98,
             f"INTC 101C: STOP — perdio 100 (px {ipx:.2f}). VENDE YA",
             "Stop del call de Intel. Vender ya.", True)
        rule("ic_examen", ipx >= 101.68,
             f"INTC 101C: EXAMEN 101.70 (px {ipx:.2f}) — si SMH sigue verde AGUANTA a 102.5-103.5; si rechaza, vende el pullback",
             "Intel llego al maximo de la apertura. Decision.", True)
        rule("ic_venta", ipx >= 102.48,
             f"INTC 101C: ZONA DE VENTA 102.5 (px {ipx:.2f}) — cobra",
             "Vender el call de Intel. Zona de venta.", True)
        rule("ic_target", ipx >= 103.45,
             f"INTC 101C: MAXIMO DE AYER 103.5 (px {ipx:.2f}) — VENDE TODO, no negocies",
             "Vender todo el call de Intel ahora.", True)
        rule("ic_stall", rule.intc_hit is not None and rule.intc_hi >= 100.9
             and (t - rule.intc_hit).total_seconds() >= 600 and ipx < rule.intc_hi - 0.3
             and ipx < 101,
             f"INTC 101C: ESTANCADO — 10 min sin nuevo maximo bajo 101 (high {rule.intc_hi:.2f}, px {ipx:.2f}). Aprieta stop a 100.30 o vende",
             "El call de Intel se estanco. Apretar stop o vender.")
        rule("ic_eod", t.hour == 15 and t.minute >= 30,
             f"INTC 101C: 15:30 — cierra HOY (px {ipx:.2f}); 1 DTE jamas overnight",
             "Cierre del dia. Vender el call de Intel.", True)
    # ===== EXIT ADVISOR del NVDA PUT de Yunior (vendido ~10:07 — inerte) =====
    npx = read_nbbo("NVDA")
    qpx2 = read_nbbo("QQQ")
    if npx:
        rule("nv_tp1", npx <= 205.3,
             f"NVDA PUT: TOMA GANANCIA — llego al muro 205 (px {npx:.2f}). "
             f"Vende (o mitad si QQQ<709 sigue cayendo: debajo de 205 hay aire hasta 202)",
             "Toma ganancia del put de Nvidia. Llego a doscientos cinco.", True)
        rule("nv_tp2", npx <= 202.3,
             f"NVDA PUT: VENDE TODO — bolson de aire alcanzado (px {npx:.2f}), target 202 cumplido",
             "Vender todo el put de Nvidia. Objetivo doscientos dos cumplido.", True)
        rule("nv_stop", npx >= 209.6,
             f"NVDA PUT: STOP — recupero 209.6 (px {npx:.2f}), la ruptura fallo. Vende ya",
             "Stop del put de Nvidia. Vender ya.", True)
        rule("nv_eod", t.hour == 15 and t.minute >= 30,
             f"NVDA PUT: 15:30 — cierra la posicion HOY (px {npx:.2f}); jamas overnight con 1 DTE",
             "Cierre del dia. Vender el put de Nvidia ahora.", True)
    # ===== EXIT ADVISOR del QQQ PUT de Yunior (comprado 09:45, flujo P/C 1.44) =====
    if qpx2:
        rule("qq_tp1", qpx2 <= 705.3,
             f"QQQ PUT: TOMA GANANCIA — target 705 alcanzado (px {qpx2:.2f}). "
             f"Vende (o mitad si SMH/NVDA siguen cayendo: siguiente escalon 703)",
             "Toma ganancia del put de Q Q Q. Llego a setecientos cinco.", True)
        rule("qq_tp2", qpx2 <= 703.2,
             f"QQQ PUT: VENDE TODO — 703 cumplido (px {qpx2:.2f})",
             "Vender todo el put de Q Q Q. Objetivo cumplido.", True)
        rule("qq_stop", qpx2 >= 711.1,
             f"QQQ PUT: STOP — recupero 711 (px {qpx2:.2f}), la ruptura de 709 fallo. Vende ya",
             "Stop del put de Q Q Q. Vender ya.", True)
        rule("qq_eod", t.hour == 15 and t.minute >= 30,
             f"QQQ PUT: 15:30 — cierra HOY (px {qpx2:.2f}); jamas overnight",
             "Cierre del dia. Vender el put de Q Q Q.", True)
    # panorama a las 9:45: rebote fuerte o debil
    rule("or_report", t >= or_end + dt.timedelta(seconds=30),
         "OPENING RANGE cerrado (9:45): " + ", ".join(
             f"{s} {v[0]:.1f}-{v[1]:.1f}" for s, v in sorted(rule.orx.items())),
         "Rango de apertura cerrado. Vigilando rupturas para puts.")

    # --- flujo put/call cada 5 min (post-open) ---
    if t >= open_t and time.time() - last_flow >= 300:
        last_flow = time.time()
        lines = []
        for s in FLEET_OPT:
            spot = read_nbbo(s)
            if not spot or not chains[s]:
                continue
            # centrar en el spot (sin sort tomaba los 8 strikes MAS BAJOS de la
            # banda -> P/C absurdos tipo 198; visto 10:17)
            ks = sorted([k for k in chains[s] if abs(k - spot) / spot <= 0.03],
                        key=lambda k: abs(k - spot))[:8]
            cons = []
            for k in ks:
                for r in ("C", "P"):
                    cons.append(Option(s, EXP, k, r, "SMART", currency="USD", tradingClass=s))
            try:
                cons = [c for c in ib.qualifyContracts(*cons) if c.conId]
                if not cons:
                    # cadena que no cualifica = NO SE, jamas "volumen 0"
                    lines.append(f"{s} SIN-DATO (cadena {EXP} no cualifica)")
                    flow_pc.pop(s, None)
                    continue
                tks = [ib.reqMktData(c, "", False, False) for c in cons]
                ib.sleep(4)
                vc = vp = 0
                for tk in tks:
                    v = tk.volume if tk.volume == tk.volume else 0
                    if tk.contract.right == "C":
                        vc += v
                    else:
                        vp += v
                    ib.cancelMktData(tk.contract)
                if vc + vp == 0:
                    # 0/0 no es P/C 0.00: es ausencia de dato
                    lines.append(f"{s} SIN-DATO (vol 0 en {len(cons)} contratos)")
                    flow_pc.pop(s, None)
                    continue
                pc = vp / max(vc, 1)
                flow_pc[s] = pc
                lines.append(f"{s} volC {vc:,.0f} volP {vp:,.0f} P/C {pc:.2f}")
                vmin = FLOW_MIN.get(s, 2000)
                if vp + vc > vmin and pc >= 2.5:
                    shout(f"{s}: FLUJO DE PUTS fuerte hoy — volP {vp:,.0f} vs volC {vc:,.0f} (P/C {pc:.1f})",
                          f"Flujo de puts fuerte en {s}.")
                if vp + vc > vmin and pc <= 0.4:
                    shout(f"{s}: FLUJO DE CALLS fuerte hoy — volC {vc:,.0f} vs volP {vp:,.0f} (P/C {pc:.1f})",
                          f"Flujo de calls fuerte en {s}.")
            except Exception as e:
                lines.append(f"{s} error {str(e)[:40]}")
        with open("data/opt_flow.txt", "w") as f:
            f.write(f"{t:%H:%M:%S} 17-jul ±3% ATM (volumen del dia)\n" + "\n".join(lines) + "\n")
        if lines:
            mirror_line("FLUJO OPCIONES: " + " | ".join(lines))
    ib.sleep(2)
