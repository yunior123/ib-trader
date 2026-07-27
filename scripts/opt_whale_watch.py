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
del 16-jul (fosil: exit-advisor de un call vencido; archivado en git).

v2 (2026-07-26): el ratio de VOLUMEN (`pc`) no distingue comprador de
vendedor -> cuenta igual puts comprados (bajista) que puts vendidos
(alcista). Overlay de premium NETO por lado via Unusual Whales
`net-prem-ticks` (agresor YA firmado por UW, ask-side menos bid-side) en
`uw_premium.py`: banner SIN VOZ (sin latencia medida ni n_eff, ~/CLAUDE.md) —
solo lectura, solo historial para calibrar."""
import json, os, subprocess, sys, time
from datetime import date, timedelta
HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear: el repo se movio a ~/ib-trader (TCC/launchd, 2026-07-25)
os.chdir(REPO); sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
from ib_mode import get_port  # fuente unica: scripts/ib_mode.py (CLAUDE.md #7)
from ib_insync import IB, Stock, Option
import em_envelope   # tabla de festivos real (misma fuente que fleet_healthcheck.sessions_since)
import uw_premium

FLEET = ["NVDA","AMD","MU","INTC","TSM","SMH","QQQ","SPY","AAPL","MSFT","META","AMZN","TSLA","AVGO","GOOGL","NOK","TXN","QCOM","NFLX","GLD","XLK","LRCX","SNDK","WDC","STX"]
VMIN = 3000          # volumen total minimo para que el ratio signifique algo
PC_PUTS, PC_CALLS = 2.0, 0.35
EXIT_PUTS, EXIT_CALLS = 1.5, 0.5   # histeresis
UW_POLL_S = 900   # 15min: conservador con el cupo del trial, 25 syms x 78 rondas/dia seria abuso

def next_friday():
    d = date.today()
    return (d + timedelta(days=(4 - d.weekday()) % 7)).strftime("%Y%m%d")

def loud(title, msg, sound="ProAlert"):
    subprocess.Popen(["/usr/bin/osascript","-e",
        f'display notification "{msg}" with title "{title}" sound name "{sound}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/bin/bash","scripts/speak.sh","DANGER",msg],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt=time.localtime()
    d=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals"); os.makedirs(d,exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt","a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")

def in_session():
    """lun-vie 09:30-16:00 Y dia de mercado real (sin festivos hardcodeados a mano:
    reutiliza em_envelope.is_market_day, la misma tabla que fleet_healthcheck)."""
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    import datetime as dt
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))

def jappend(path, obj):
    # historia para backtesting (scalper 2026-07-21): append-only JSONL,
    # degradacion limpia — si falla, la alarma sigue viva igual.
    try:
        with open(path, "a") as f:
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")
    except Exception:
        pass

STATE_F = "data/opt_whale_state.json"   # sobrevive reinicios: sin re-sirenas
state = {}   # sym -> 'puts'|'calls'|'mid'
try:
    st_raw = json.load(open(STATE_F))
    if st_raw.get("day") == date.today().isoformat():
        state = st_raw.get("state", {})
except Exception:
    pass

UW_TOK = uw_premium.token()   # vacio -> overlay se salta entero, degradacion limpia
uw_last = {}   # sym -> epoch del ultimo poll UW (persiste entre reconexiones IB)
if not UW_TOK:
    print("whale watch: sin UW_TOKEN, overlay de premium neto DESACTIVADO", file=sys.stderr)

while True:
    try:
        if not in_session():
            time.sleep(120); continue
        ib = IB(); ib.connect("127.0.0.1", get_port(), clientId=82, readonly=True, timeout=15)
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
                    # ANTI-NaN (2026-07-22 12:22/12:35): farm transitoria -> last
                    # Y close NaN. NaN es truthy => pasaba el filtro, ks=[] (nan
                    # rompe la comparacion), vc+vp=0 y caia al fallback clase con
                    # spot=nan -> 7 sirenas BALLENA CRECE falsas (QQQ 48k->1.48M).
                    if spot != spot: spot = None
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
                    uw_suffix = ""
                    if UW_TOK and time.time() - uw_last.get(s, 0) >= UW_POLL_S:
                        uw_last[s] = time.time()
                        try:
                            uw_rows = uw_premium.fetch_net_prem_ticks(s, UW_TOK)
                            uw_age, uw_ts = uw_premium.latest_feed_age_s(uw_rows)
                            uw_prem = uw_premium.signed_premium(uw_rows, window_min=15)
                            if uw_prem is not None:
                                rec = {"ts": int(time.time()), "sym": s, "src": "unusual_whales_trial",
                                       "feed_ts": uw_ts, "feed_age_s": None if uw_age is None else round(uw_age, 1),
                                       **uw_prem}
                                jappend("data/uw_premium_flow_hist.jsonl", rec)
                                lado = "BULLISH" if uw_prem["signed_premium"] > 0 else "BEARISH"
                                uw_suffix = (f" | UW prem neto ${uw_prem['signed_premium']:,.0f} {lado}"
                                             f" (call ${uw_prem['net_call_premium']:,.0f} put ${uw_prem['net_put_premium']:,.0f})"
                                             f" age {rec['feed_age_s']}s [banner sin voz: latencia sin medir en sesion]")
                        except Exception as e:
                            print(f"{s}: UW premium fallo ({e})", file=sys.stderr)
                    lines.append(f"{s} volC {vc:,.0f} volP {vp:,.0f} P/C {pc:.2f}{tag}{uw_suffix}")
                    jappend("data/whale_flow_hist.jsonl",
                            {"ts": int(time.time()), "sym": s, "vc": int(vc), "vp": int(vp),
                             "pc": round(pc, 3), "spot": round(float(spot), 4),
                             "src": "clase" if tag else "strikes", "exp": exp})
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
                    # ESCALADA (Yunior 12:20): dentro del MISMO estado, si el volumen
                    # dominante se DUPLICA desde el ultimo canto -> re-sirena.
                    # (cazado: NVDA 82k->248k calls sin re-alarma). Aditivo.
                    try:
                        vkey = f"{s}_v"
                        vdom = vc if cur == "calls" else vp if cur == "puts" else 0
                        vlast = state.get(vkey, 0)
                        # tag => este scan uso volumen de CLASE entera: incomparable
                        # con el baseline por-strikes -> jamas cantar ESCALADA ahi
                        # (2026-07-22: NOK 4k strikes vs 122k clase = "DUPLICO" falso).
                        # SEED (post-mortem 2026-07-22 12:22): con vlast=0 (feature
                        # nueva o state sin vkey tras reinicio) "2*max(0,1)=2" hacia
                        # que CUALQUIER volumen>VMIN cantara DUPLICO -> 7 sirenas
                        # falsas en un scan. Primera observacion SIEMBRA el baseline,
                        # jamas canta.
                        if not tag and cur in ("calls", "puts") and vlast <= 0:
                            state[vkey] = vdom
                        elif not tag and cur in ("calls", "puts") and cur == prev and vlast > 0 and vdom >= 2 * vlast and vdom > VMIN:
                            state[vkey] = vdom
                            jappend("data/whale_alerts.jsonl",
                                    {"ts": int(time.time()), "side": cur.upper(), "prev": "ESCALADA",
                                     "sym": s, "pc": round(pc, 3), "vc": int(vc), "vp": int(vp),
                                     "spot": round(float(spot), 4)})
                            loud("🐋📈 BALLENA CRECE", f"{s}: el flujo de {cur} se DUPLICO — {vdom:,.0f} contratos (P C {pc:.2f}). La marea sigue entrando", "ProAlarm")
                        elif cur != prev:
                            # jamas sembrar baseline con volumen de CLASE entera
                            # (AVGO_v=158k clase 12:36 dejo la escalada por-strikes
                            # muda el resto del dia). tag => baseline 0 = re-siembra
                            # limpia en el proximo scan por-strikes.
                            state[vkey] = 0 if tag else vdom
                    except Exception:
                        pass
                    if cur != prev:
                        state[s] = cur
                        jappend("data/whale_alerts.jsonl",
                                {"ts": int(time.time()), "side": cur.upper(), "prev": prev.upper(),
                                 "sym": s, "pc": round(pc, 3), "vc": int(vc), "vp": int(vp),
                                 "spot": round(float(spot), 4)})
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
