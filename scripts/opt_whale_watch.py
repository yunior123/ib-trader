#!/usr/bin/env python3
"""opt_whale_watch.py — vigia de BALLENAS de opciones de la flota (2026-07-20,
orden "activa alarm fleet for whale puts and calls"). SEÑAL-SOLAMENTE.

Cada 5 min: volumen de opciones del dia ±3% ATM (expiry semanal AUTO = proximo
viernes) para la flota liquida. Alerta voz+banner cuando el flujo se dispara:
  - P/C >= 2.0 con volumen real  -> BALLENA DE PUTS (piso/hedge o bajista)
  - P/C <= 0.35 con volumen real -> BALLENA DE CALLS (ley #13: pico de calls
    = techo local probable / iman — esperar pullback, no perseguir)
Anti-spam: alerta solo al CRUZAR umbral (histeresis 1.5/0.5) por simbolo.
Escribe data/opt_flow.txt. clientId 82. Jamas ordena. Reemplaza al opt_sentinel
del 16-jul (fosil: exit-advisor de un call vencido; archivado en git)."""
import os, subprocess, sys, time
from datetime import date, timedelta
HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "Documents/GitHub/ib-trader")
os.chdir(REPO); sys.path.insert(0, REPO)
from ib_insync import IB, Stock, Option

FLEET = ["NVDA","AMD","MU","INTC","TSM","SMH","QQQ","AAPL","MSFT","META","AMZN","TSLA","AVGO","GOOGL"]
VMIN = 3000          # volumen total minimo para que el ratio signifique algo
PC_PUTS, PC_CALLS = 2.0, 0.35
EXIT_PUTS, EXIT_CALLS = 1.5, 0.5   # histeresis

def next_friday():
    d = date.today()
    return (d + timedelta(days=(4 - d.weekday()) % 7)).strftime("%Y%m%d")

def loud(title, msg, sound="ProAlert"):
    subprocess.Popen(["/usr/bin/osascript","-e",
        f'display notification "{msg}" with title "{title}" sound name "{sound}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/bin/bash","scripts/speak.sh","SIGNAL",msg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt=time.localtime()
    d=f"{HOME}/Desktop/trading-signals"; os.makedirs(d,exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt","a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")

state = {}   # sym -> 'puts'|'calls'|'mid'
while True:
    try:
        ib = IB(); ib.connect("127.0.0.1", 7496, clientId=82, readonly=True, timeout=15)
        exp = next_friday()
        print(f"whale watch: {len(FLEET)} syms, expiry {exp}", file=sys.stderr)
        stks = {s: Stock(s, "SMART", "USD") for s in FLEET}
        ib.qualifyContracts(*stks.values())
        chains = {}
        for s in FLEET:
            try:
                ch = ib.reqSecDefOptParams(s, "", "STK", stks[s].conId)
                chains[s] = sorted(next(c for c in ch if c.exchange == "SMART").strikes)
            except Exception:
                chains[s] = []
        while ib.isConnected():
            lines = []
            for s in FLEET:
                try:
                    tk = ib.reqMktData(stks[s], "", False, False); ib.sleep(1.2)
                    spot = tk.last if tk.last == tk.last and tk.last else tk.close
                    ib.cancelMktData(stks[s])
                    if not spot or not chains[s]: continue
                    ks = [k for k in chains[s] if abs(k-spot)/spot <= 0.03]
                    cons = [Option(s, exp, k, r, "SMART", tradingClass=s) for k in ks for r in "CP"]
                    q = ib.qualifyContracts(*cons)
                    tks = [ib.reqMktData(c, "", False, False) for c in q]
                    ib.sleep(2.5)
                    vc = vp = 0
                    for t in tks:
                        v = t.volume if t.volume == t.volume else 0
                        if t.contract.right == "C": vc += v
                        else: vp += v
                        ib.cancelMktData(t.contract)
                    pc = vp / max(vc, 1); tot = vc + vp
                    lines.append(f"{s} volC {vc:,.0f} volP {vp:,.0f} P/C {pc:.2f}")
                    prev = state.get(s, "mid")
                    cur = prev
                    if tot >= VMIN:
                        if pc >= PC_PUTS: cur = "puts"
                        elif pc <= PC_CALLS: cur = "calls"
                        elif prev == "puts" and pc < EXIT_PUTS: cur = "mid"
                        elif prev == "calls" and pc > EXIT_CALLS: cur = "mid"
                    if cur != prev:
                        state[s] = cur
                        if cur == "puts":
                            loud("🐋 BALLENA PUTS", f"{s}: flujo puts {pc:.1f} a 1 ({vp:,.0f} puts vs {vc:,.0f} calls) — piso o tesis bajista", "ProAlarm")
                        elif cur == "calls":
                            loud("🐋 BALLENA CALLS", f"{s}: flujo calls masivo, P C {pc:.2f} ({vc:,.0f} calls) — iman y techo local, ley 13: no perseguir, esperar pullback", "ProAlarm")
                except Exception as e:
                    print(f"{s}: {e}", file=sys.stderr)
            with open("data/opt_flow.txt", "w") as f:
                f.write(time.strftime("%H:%M:%S") + f" {exp} ±3% ATM volumen dia\n" + "\n".join(lines) + "\n")
            lt = time.localtime()
            if lt.tm_hour >= 16: print("cierre 16:00 — whale watch fin de sesion", file=sys.stderr); ib.disconnect(); sys.exit(0)
            ib.sleep(300)
        raise ConnectionError("TWS fuera")
    except SystemExit: raise
    except Exception as e:
        print(f"whale watch caido: {e} — retry 30s", file=sys.stderr); time.sleep(30)
