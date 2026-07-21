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
import json, os, subprocess, sys, time
from datetime import date, timedelta
HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "Documents/GitHub/ib-trader")
os.chdir(REPO); sys.path.insert(0, REPO)
from ib_insync import IB, Stock, Option

FLEET = ["NVDA","AMD","MU","INTC","TSM","SMH","QQQ","SPY","AAPL","MSFT","META","AMZN","TSLA","AVGO","GOOGL","NOK","TXN","QCOM","NFLX","GLD","XLK"]
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

def in_session():
    lt = time.localtime()
    return lt.tm_wday < 5 and (930 <= lt.tm_hour * 100 + lt.tm_min < 1600)

STATE_F = "data/opt_whale_state.json"   # sobrevive reinicios: sin re-sirenas
state = {}   # sym -> 'puts'|'calls'|'mid'
try:
    st_raw = json.load(open(STATE_F))
    if st_raw.get("day") == date.today().isoformat():
        state = st_raw.get("state", {})
except Exception:
    pass
while True:
    try:
        if not in_session():
            time.sleep(120); continue
        ib = IB(); ib.connect("127.0.0.1", 7496, clientId=82, readonly=True, timeout=15)
        exp = next_friday()
        print(f"whale watch: {len(FLEET)} syms, expiry {exp}", file=sys.stderr)
        stks = {s: Stock(s, "SMART", "USD") for s in FLEET}
        ib.qualifyContracts(*stks.values())
        def fetch_chain(s):
            # SMART puede traer VARIAS tradingClass (cazado 2026-07-20: AMZN
            # devuelve 'AMZN' y '2AMZN' ajustada post-split; tomar la primera
            # dejaba a AMZN con 0 strikes ATM = ticker ciego TODO el dia).
            # Elegir la clase == simbolo QUE tenga la expiry; fallback a
            # cualquiera con la expiry.
            try:
                ch = ib.reqSecDefOptParams(s, "", "STK", stks[s].conId)
                cands = [c for c in ch if c.exchange == "SMART" and c.tradingClass == s and exp in c.expirations]
                if not cands:
                    cands = [c for c in ch if c.exchange == "SMART" and exp in c.expirations]
                return sorted(cands[0].strikes) if cands else []
            except Exception:
                return []
        chains = {s: fetch_chain(s) for s in FLEET}
        # la cadena SMART mezcla strikes de TODAS las expiries -> muchos no
        # existen en la semanal (cazado 2026-07-20: spam Error 200 QQQ 679/712.5).
        # Cache: calificar cada strike UNA vez; los que fallan van a la lista negra.
        qcache = {s: {} for s in FLEET}   # (strike, right) -> Option calificada
        badk = {s: set() for s in FLEET}  # strikes sin contrato en esta expiry
        zeros = {s: 0 for s in FLEET}     # scans seguidos con volumen 0 (ciego)
        while ib.isConnected():
            lines = []
            for s in FLEET:
                try:
                    tk = ib.reqMktData(stks[s], "", False, False); ib.sleep(1.2)
                    spot = tk.last if tk.last == tk.last and tk.last else tk.close
                    ib.cancelMktData(stks[s])
                    if not chains[s]: chains[s] = fetch_chain(s)   # reintento: no dejar ticker muerto toda la sesion
                    if not spot or not chains[s]:
                        zeros[s] += 1
                        if zeros[s] == 2:
                            loud("🕳 TICKER CIEGO", f"{s}: sin spot o sin cadena — ballenas de {s} SIN cobertura, revisar", "ProAlarm")
                        continue
                    ks = [k for k in chains[s] if abs(k-spot)/spot <= 0.03 and k not in badk[s]]
                    # tope 12 strikes mas cercanos al ATM: QQQ a $700 con strikes
                    # de $1 daba 40 strikes = 80 lineas de golpe -> tope de lineas
                    # de TWS (con la flota entera conectada) y Error 354 en los
                    # simbolos siguientes (AAPL/META ciegos, cazado 2026-07-20).
                    ks = sorted(ks, key=lambda k: abs(k - spot))[:12]
                    new = [Option(s, exp, k, r, "SMART", tradingClass=s)
                           for k in ks for r in "CP" if (k, r) not in qcache[s]]
                    if new:
                        ok = ib.qualifyContracts(*new)
                        for c in ok:
                            qcache[s][(c.strike, c.right)] = c
                        # blacklistear SOLO con respuesta definitiva: si qualify
                        # devolvio 0 de todo (fallo transitorio, farm calentando)
                        # NO vetar — cazado 2026-07-20: AAPL entero vetado en el
                        # scan 1 y ciego el resto de la sesion.
                        if ok:
                            for k in ks:
                                if (k, "C") not in qcache[s] and (k, "P") not in qcache[s]:
                                    badk[s].add(k)
                    q = [qcache[s][(k, r)] for k in ks for r in "CP" if (k, r) in qcache[s]]
                    def measure(wait):
                        tks = [ib.reqMktData(c, "", False, False) for c in q]
                        ib.sleep(wait)
                        vc = vp = 0
                        for t in tks:
                            v = t.volume if t.volume == t.volume else 0
                            if t.contract.right == "C": vc += v
                            else: vp += v
                            ib.cancelMktData(t.contract)
                        return vc, vp
                    vc, vp = measure(2.5)
                    if vc + vp == 0 and q:
                        vc, vp = measure(4.0)   # farm lenta (post-login): un reintento antes de declarar 0
                    tag = ""
                    if vc + vp == 0:
                        # FALLBACK 1-linea (cazado 2026-07-20): el tope de ~100
                        # lineas de market data es COMPARTIDO con toda la flota
                        # -> los scans por-strike pierden la loteria al azar
                        # (Error 354, tickers ciegos rotando). Tick 100/101 en el
                        # SUBYACENTE da call/put volume de la clase entera con
                        # una sola linea — P/C estandar, inmune al tope.
                        tku = ib.reqMktData(stks[s], "100,101", False, False); ib.sleep(2.5)
                        cvol = tku.callVolume if tku.callVolume == tku.callVolume else 0
                        pvol = tku.putVolume if tku.putVolume == tku.putVolume else 0
                        ib.cancelMktData(stks[s])
                        if cvol or pvol:
                            vc, vp, tag = cvol, pvol, " (clase)"
                    pc = vp / max(vc, 1); tot = vc + vp
                    lines.append(f"{s} volC {vc:,.0f} volP {vp:,.0f} P/C {pc:.2f}{tag}")
                    if tot == 0:
                        zeros[s] += 1
                        if zeros[s] == 2:
                            badk[s].clear()   # autocura: reintentar strikes vetados
                            loud("🕳 TICKER CIEGO", f"{s}: 2 scans sin volumen de opciones — ballenas de {s} SIN cobertura, revisar", "ProAlarm")
                    else:
                        zeros[s] = 0
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
            json.dump({"day": date.today().isoformat(), "state": state}, open(STATE_F, "w"))
            lt = time.localtime()
            if lt.tm_hour >= 16: print("cierre 16:00 — whale watch fin de sesion", file=sys.stderr); ib.disconnect(); sys.exit(0)
            ib.sleep(300)
        raise ConnectionError("TWS fuera")
    except SystemExit: raise
    except Exception as e:
        print(f"whale watch caido: {e} — retry 30s", file=sys.stderr); time.sleep(30)
