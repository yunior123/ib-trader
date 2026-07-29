#!/usr/bin/env python3
"""opt_whale_watch.py — vigia de BALLENAS de opciones de la flota (2026-07-20,
orden "activa alarm fleet for whale puts and calls"). SEÑAL-SOLAMENTE.

Cada 5 min: volumen de opciones del dia ±3% ATM para la flota (data/fleet.txt).
Expiry REAL por simbolo: la mas cercana >= hoy segun reqSecDefOptParams, cache
diaria en data/opt_whale_chains.json; la parrilla se reconstruye si el spot se
aleja >1.5% del centro usado. Alerta voz+banner cuando el flujo se dispara:
  - P/C >= 2.0 con volumen real  -> BALLENA DE PUTS (piso/hedge o bajista)
  - P/C <= 0.35 con volumen real -> BALLENA DE CALLS (ley #13: pico de calls
    = techo local probable / iman — esperar pullback, no perseguir)
Anti-spam: alerta solo al CRUZAR umbral (histeresis 1.5/0.5) por simbolo.
Escribe data/opt_flow.txt. clientId 82. Jamas ordena.

v2 (2026-07-26): overlay de premium NETO firmado via Unusual Whales
`net-prem-ticks` en `uw_premium.py`: banner SIN VOZ, solo historial.
v3 (2026-07-28): expiry por simbolo desde secdef (el 27-jul next_friday=20260731
no existia en varios nombres y tras el -8% la parrilla ATM cayo en strikes
inexistentes -> "Unknown contract" masivo y CERO ballenas todo el selloff).
Sin cadena valida = "BALLENAS CIEGAS <sym>" en voz, jamas silencio ni ceros.
`--selftest`: cualifica la parrilla de los 30 y sale (verificacion overnight).

v4 (2026-07-28 tarde): mensajes "Alerta ballena..."/"Alerta premium..." distintos por detector
(antes compartian texto y confundian); strike dominante + cruce con muro medido
(data/gex_snapshot.json) en el mensaje; 2 lecturas consecutivas antes de sonar una entrada nueva
a puts/calls (señal marginal != decisiva, evita cruces de un solo tick como EWY 28-jul); filtro
por ticker opcional data/whale_alert_filter.txt (CALLS|PUTS|BOTH); carril rapido opcional
data/whale_priority.txt (max 5, reqMktData mas frecuente — HIRO confirmo en vivo que tick-by-tick
real-time no existe para opciones, docs/HIRO-2026-07-25.md). Todo ajustable desde el panel de
chart_bridge sin reiniciar el proceso."""
import json, os, subprocess, sys, threading, time
from datetime import date
HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear: el repo se movio a ~/ib-trader (TCC/launchd, 2026-07-25)
os.chdir(REPO); sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
from ib_mode import get_port  # fuente unica: scripts/ib_mode.py (CLAUDE.md #7)
from ib_insync import IB, Stock, Option
import em_envelope   # tabla de festivos real (misma fuente que fleet_healthcheck.sessions_since)
import uw_premium
import notify_short


def load_fleet():
    syms = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    if not syms:
        raise RuntimeError("data/fleet.txt vacio — sin flota no hay vigia")
    return syms

FLEET = load_fleet()   # fuente unica del universo (CLAUDE.md #7); antes lista hardcodeada de 25
VMIN = 3000          # volumen total minimo para que el ratio signifique algo
PC_PUTS, PC_CALLS = 2.0, 0.35
EXIT_PUTS, EXIT_CALLS = 1.5, 0.5   # histeresis

# bug cazado 2026-07-28: umbral P/C UNICO -> SPY (P/C real 0.47-1.69 todo el dia) no puede
# tocar 2.0/0.35 JAMAS: el capitan del mercado era mudo estructural. Umbral propio (percentil
# de su historia, whale_flow_hist) SOLO en el lado inalcanzable para ese ticker; el resto de
# la flota conserva el estatico probado (lema 2026-07-28: sin ruido nuevo sin medir).
PC_HIST_F = "data/whale_flow_hist.jsonl"
PC_HIST_MIN_N = 100

def pc_thresholds():
    import collections
    per = collections.defaultdict(list)
    try:
        with open(os.path.join(REPO, PC_HIST_F)) as f:
            for l in f:
                try: d = json.loads(l)
                except Exception: continue
                pc = d.get("pc")
                if pc is not None and d.get("vc", 0) + d.get("vp", 0) >= VMIN:
                    per[d.get("sym")].append(pc)
    except FileNotFoundError:
        return {}
    out = {}
    for s, xs in per.items():
        if len(xs) < PC_HIST_MIN_N: continue
        xs.sort()
        q = lambda p: xs[min(len(xs)-1, int(p*len(xs)))]
        th = {"puts": PC_PUTS, "calls": PC_CALLS, "xputs": EXIT_PUTS, "xcalls": EXIT_CALLS, "n": len(xs)}
        if xs[-1] < PC_PUTS:    # jamas alcanzo el umbral puts en toda su historia -> cola p97 propia
            th["puts"], th["xputs"] = q(0.97), q(0.85)
        if xs[0] > PC_CALLS:    # jamas alcanzo el umbral calls -> cola p03 propia
            th["calls"], th["xcalls"] = q(0.03), q(0.15)
        if th["puts"] != PC_PUTS or th["calls"] != PC_CALLS:
            out[s] = th
    return out

PCTH = pc_thresholds()
if PCTH:
    print("umbral P/C propio (lado inalcanzable): " + "  ".join(
        f"{s}:puts>={t['puts']:.2f}/calls<={t['calls']:.2f}(n={t['n']})" for s, t in sorted(PCTH.items())), file=sys.stderr)
STATE_STALE_S = 3600   # sin lectura con tot>=VMIN en esta ventana, puts/calls decae a mid solo (bug cazado 2026-07-28: se congelaba para siempre)
UW_POLL_S = 900   # 15min: conservador con el cupo del trial, 25 syms x 78 rondas/dia seria abuso
# top-10 Nasdaq (pesos QQQ, playbook data/qqq_weights.txt) presentes en la flota;
# COST no esta en fleet.txt (fuente unica CLAUDE.md #5) -> sin cobertura, no se inventa.
NASDAQ10 = [s for s in ("NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "AVGO", "META", "TSLA", "NFLX") if s in FLEET]
UW_PREM_BULL, UW_PREM_BEAR = 2_000_000, -2_000_000   # umbral SIN CALIBRAR (doctrina: etiquetado, no medido)
UW_PREM_EXIT = 1_000_000                             # histeresis, mismo patron que PC_PUTS/PC_CALLS
UW_MAX_AGE_S = 600   # feed mas viejo que esto no es "large trade AHORA": se ignora, no se alarma con dato muerto
UW_CAPTAINS = [s for s in ("SPY", "QQQ", "SMH") if s in FLEET]   # capitanes (regla 12): solo alarman con umbral MEDIDO propio
UW_PREM_MIN_N = 30   # bajo esto no hay percentil honesto (measured-probability)


def uw_prem_thresholds():
    """p97 de |premium neto| propio por simbolo (n>=30) — QQQ p50 ya es ~$3.6M, el $2M fijo seria crying-wolf en ETFs."""
    per = {}
    try:
        with open(os.path.join(REPO, "data", "uw_premium_flow_hist.jsonl")) as f:
            for ln in f:
                try: d = json.loads(ln)
                except json.JSONDecodeError: continue
                sp = d.get("signed_premium")
                if sp is not None:
                    per.setdefault(d.get("sym"), []).append(abs(float(sp)))
    except FileNotFoundError:
        return {}
    out = {}
    for s, xs in per.items():
        if len(xs) < UW_PREM_MIN_N: continue
        xs.sort()
        p97 = xs[min(len(xs)-1, int(0.97 * len(xs)))]
        out[s] = {"bull": p97, "bear": -p97, "exit": p97 / 2.0, "n": len(xs)}   # exit al 50%, mismo ratio 2M/1M
    return out

UW_PTH = uw_prem_thresholds()
if UW_PTH:
    print("umbral UW premium propio (p97): " + "  ".join(
        f"{s}:${t['bull']/1e6:.1f}M(n={t['n']})" for s, t in sorted(UW_PTH.items())), file=sys.stderr)
RECENTER_PCT = 0.015   # spot >1.5% del centro usado -> parrilla nueva (selloff 27-jul)
CHAIN_F = "data/opt_whale_chains.json"   # cache diaria secdef: no re-pedir cada arranque

def load_symlist(name):
    """Patron canonical_fleet() (fleet_healthcheck.py:366): fichero inexistente o vacio -> None,
    nunca lista vacia silenciosa (regla #7 NADA HARDCODEADO)."""
    p = os.path.join(REPO, "data", name)
    if not os.path.exists(p):
        return None
    syms = open(p).read().split()
    return syms or None

def load_ticker_filter():
    """data/whale_alert_filter.txt: 'TICKER CALLS|PUTS|BOTH' por linea, ajustable desde el panel
    de chart_bridge. Ausente/vacio -> {} (sin filtro, BOTH para todos, comportamiento de hoy)."""
    p = os.path.join(REPO, "data", "whale_alert_filter.txt")
    if not os.path.exists(p):
        return {}
    out = {}
    for line in open(p):
        parts = line.split()
        if len(parts) >= 2 and parts[1].upper() in ("CALLS", "PUTS", "BOTH"):
            out[parts[0].upper()] = parts[1].upper()
    return out

# carril rapido (Yunior 2026-07-28 "seleccionar hasta 5 tickers para detectar terremoto rapido"):
# data/whale_priority.txt, ajustable desde el panel de chart_bridge. Ausente/vacio -> el carril
# rapido simplemente no corre (nunca se adivina una lista por defecto — regla #3).
PRIORITY_F = "whale_priority.txt"
PRIORITY_MAX = 5   # acoplado al cupo de 5 lineas tick-by-tick medido en ibkr_bar_bridge.py:55,
                    # aunque este carril use reqMktData, no tick-by-tick (HIRO probo en vivo
                    # 2026-07-28 que tick-by-tick real-time NO existe para opciones, error 10189
                    # en 20/20 contratos — docs/HIRO-2026-07-25.md)
PRIORITY_CYCLE_S = 45   # re-escaneo de los prioritarios mientras dura el resto del ciclo de 5min

GEX_SNAPSHOT_F = os.path.join(REPO, "data", "gex_snapshot.json")
GEX_MAX_AGE_S = 3600   # muro de un snapshot mas viejo que esto no se cita (freshness gate)

def wall_near(sym, strike, right):
    """Si data/gex_snapshot.json tiene un muro FRESCO y MEDIDO para sym que coincide con strike,
    devuelve su precio; si no, None. Nunca fabrica coincidencia (regla #3)."""
    if strike is None:
        return None
    try:
        snap = json.load(open(GEX_SNAPSHOT_F)).get(sym)
    except Exception:
        return None
    if not snap or time.time() - snap.get("ts", 0) > GEX_MAX_AGE_S:
        return None
    wall = snap.get("call_wall") if right == "C" else snap.get("put_wall")
    if wall is None:
        return None
    spot = snap.get("spot") or 0
    tol = max(spot * 0.01, 0.5)   # 1% del spot o $0.5, lo que sea mayor
    return wall if abs(wall - strike) <= tol else None

def dominant_strike(per, right):
    """per: lista (strike, right, volumen) del ultimo measure() por-strikes. Strike con mas
    volumen del lado que disparo. None si measure uso el fallback de clase (sin detalle por-strike)."""
    cands = [(v, k) for (k, r, v) in per if r == right and v > 0]
    return max(cands)[1] if cands else None

def loud(title, msg, sound="ProAlert", voice_msg=None):
    """voice_msg: version corta (Yunior 2026-07-28 "voces muy largas, resume" / "notificaciones
    cortas y precisas, en ntfy, macos, all over"). Banner macOS usa la version corta tambien;
    `msg` completo se queda SOLO en el log (lo leen signals_db/regen_signals/etc)."""
    corto = voice_msg or msg
    subprocess.Popen(["/usr/bin/osascript","-e",
        f'display notification "{corto}" with title "{title}" sound name "{sound}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["/bin/bash","scripts/speak.sh","DANGER",corto],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt=time.localtime()
    d=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals"); os.makedirs(d,exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt","a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")
    notify_short.push(title, corto)

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

def fetch_chain(ib, stks, s):
    """Expiries/strikes REALES via secdef; expiry mas cercana >= hoy POR SIMBOLO.
    Devuelve {"exp","tc","strikes"} o None (None = ciego, jamas {} fabricado)."""
    today = date.today().strftime("%Y%m%d")
    try:
        ch = ib.reqSecDefOptParams(s, "", "STK", stks[s].conId)
    except Exception as e:
        print(f"{s}: secdef fallo: {e}", file=sys.stderr)
        return None
    # SMART puede traer VARIAS tradingClass (cazado 2026-07-20: AMZN devuelve
    # 'AMZN' y '2AMZN' post-split); preferir la clase == simbolo.
    pool = [c for c in ch if c.exchange == "SMART" and c.tradingClass == s] \
        or [c for c in ch if c.exchange == "SMART"]
    exps = sorted({e for c in pool for e in c.expirations if e >= today})
    if not exps:
        return None
    exp = exps[0]
    have = [c for c in pool if exp in c.expirations]
    tc = next((c.tradingClass for c in have if c.tradingClass == s), have[0].tradingClass)
    # bug cazado en caza de bugs 2026-07-28: strikes se unia de TODAS las tradingClass de `have`
    # (ej. AMZN '2AMZN' post-split) pero los contratos se califican con un unico `tc` -> strikes
    # ajenos a esa clase entraban a la parrilla, fallaban qualify y se blacklisteaban una y otra
    # vez en cada RECENTER (badk[s].clear() los reintenta). Filtrar por tc antes de unir strikes.
    have_tc = [c for c in have if c.tradingClass == tc]
    strikes = sorted({k for c in (have_tc or have) for k in c.strikes})
    return {"exp": exp, "tc": tc, "strikes": strikes} if strikes else None

def load_chain_cache():
    try:
        raw = json.load(open(CHAIN_F))
        if raw.get("day") == date.today().isoformat():
            return raw.get("chains", {})
    except Exception:
        pass
    return {}

def save_chain_cache(chains):
    try:
        tmp = CHAIN_F + ".tmp"
        json.dump({"day": date.today().isoformat(), "chains": chains}, open(tmp, "w"))
        os.replace(tmp, CHAIN_F)   # escritura atomica (regla de frontera Python)
    except Exception:
        pass

def save_state(state):
    """Bug cazado 2026-07-28: STATE_F se escribia con json.dump directo (sin tmp+rename, a
    diferencia de save_chain_cache). Un os._exit(1) del watchdog a mitad de escritura dejaba
    opt_whale_state.json truncado -> el load con except:pass del arranque resetea state={},
    perdiendo toda la histeresis puts/calls/mid del dia."""
    try:
        tmp = STATE_F + ".tmp"
        json.dump({"day": date.today().isoformat(), "state": state}, open(tmp, "w"))
        os.replace(tmp, STATE_F)
    except Exception:
        pass

def get_spot(ib, stk, waits=(1.2,)):
    for w in waits:
        tk = ib.reqMktData(stk, "", False, False); ib.sleep(w)
        v = tk.last if tk.last == tk.last and tk.last else tk.close
        ib.cancelMktData(stk)
        if v == v and v:   # ANTI-NaN (2026-07-22): NaN es truthy y rompia todo aguas abajo
            return v
    return None

def selftest():
    """Cualifica la parrilla ATM de toda la flota y sale. Overnight las opciones
    no tickean: el exito es 'contratos cualificados', no volumen. clientId 83."""
    ib = IB(); ib.connect("127.0.0.1", get_port(), clientId=83, readonly=True, timeout=15)
    stks = {s: Stock(s, "SMART", "USD") for s in FLEET}
    ib.qualifyContracts(*stks.values())
    bad = []
    for s in FLEET:
        info = fetch_chain(ib, stks, s)
        if not info:
            print(f"SELFTEST {s}: SIN CADENA (secdef vacio)"); bad.append(s); continue
        spot = get_spot(ib, stks[s], waits=(1.2, 3.0))
        if not spot:
            print(f"SELFTEST {s}: exp {info['exp']} strikes {len(info['strikes'])} SIN SPOT"); bad.append(s); continue
        ks = sorted([k for k in info["strikes"] if abs(k-spot)/spot <= 0.03], key=lambda k: abs(k-spot))[:12]
        opts = [Option(s, info["exp"], k, r, "SMART", tradingClass=info["tc"]) for k in ks for r in "CP"]
        ok = ib.qualifyContracts(*opts) if opts else []
        print(f"SELFTEST {s}: spot {spot:g} exp {info['exp']} tc {info['tc']} atm {len(ks)} -> {len(ok)}/{len(opts)} cualificados")
        if not ok: bad.append(s)
    ib.disconnect()
    print(f"SELFTEST OK: {len(FLEET)}/{len(FLEET)} con parrilla cualificada" if not bad
          else f"SELFTEST FALLA ({len(bad)}): {' '.join(bad)}")
    sys.exit(1 if bad else 0)

STATE_F = "data/opt_whale_state.json"   # sobrevive reinicios: sin re-sirenas
state = {}   # sym -> 'puts'|'calls'|'mid'
try:
    st_raw = json.load(open(STATE_F))
    if st_raw.get("day") == date.today().isoformat():
        state = st_raw.get("state", {})
except Exception:
    pass

if "--selftest" in sys.argv:
    selftest()

UW_TOK = uw_premium.token()   # vacio -> overlay se salta entero, degradacion limpia
uw_last = {}   # sym -> epoch del ultimo poll UW (persiste entre reconexiones IB)
if not UW_TOK:
    print("whale watch: sin UW_TOKEN, overlay de premium neto DESACTIVADO", file=sys.stderr)

# Salir tras N fallos SEGUIDOS -> el keepalive re-exec y recarga codigo/puerto fresco. Sin esto,
# el retry interno de 30s corre para siempre: un proceso vivo 15h siguio pegado al 4002 del
# viernes cuando el gateway del lunes estaba en 4001, y NINGUNA ballena disparo en todo el dia
# (get_port() actual da 4001, pero el import viejo del proceso solo conocia 4002).
FAIL_EXIT = int(os.environ.get("WHALE_FAIL_EXIT", "5"))

# VIGIA de cuelgue (2026-07-28, Yunior: se colgo 3 veces en 15 min cerca de GLD/"Unknown
# contract", proceso vivo pero CERO avance -- probable reqMktData/qualifyContracts sin
# respuesta de TWS bajo el tope de lineas compartido). Hilo aparte: si el hilo principal
# se bloquea en una llamada sincrona de ib_insync, este hilo sigue corriendo y mata el
# proceso igual -- os._exit() no espera a nadie. El keepalive externo ya relanza en ~60s.
WATCHDOG_S = int(os.environ.get("WHALE_WATCHDOG_S", "300"))
_progress = {"t": time.time()}

def _watchdog():
    while True:
        time.sleep(30)
        stuck = time.time() - _progress["t"]
        if stuck > WATCHDOG_S:
            print(f"whale watch: SIN AVANCE {stuck:.0f}s (>{WATCHDOG_S}s) -- "
                  "colgado, salgo para que el keepalive relance", file=sys.stderr)
            os._exit(1)

threading.Thread(target=_watchdog, daemon=True).start()

fails = 0
while True:
    try:
        if not in_session():
            _progress["t"] = time.time()   # sin esto el watchdog mataba el proceso SANO cada 5min toda la noche (boot-loop, cazado 2026-07-29)
            time.sleep(120); continue
        ib = IB(); ib.connect("127.0.0.1", get_port(), clientId=82, readonly=True, timeout=15)
        # CAUSA RAIZ confirmada 2026-07-28 (caza de bugs) de los cuelgues cerca de GLD del mismo
        # dia: ib_insync.IB.RequestTimeout es 0 por defecto -> qualifyContracts/reqSecDefOptParams
        # esperan para siempre si TWS no responde un reqId (util.run() solo mete wait_for si
        # timeout es verdadero). Sin esto, solo el watchdog externo de 300s lo notaba, nunca la
        # causa. Con esto, la llamada synchrona levanta a los 15s y el except de scan_symbol la
        # cuenta como fallo real (ver zeros[s] mas abajo) en vez de colgar el proceso entero.
        ib.RequestTimeout = 15
        fails = 0
        stks = {s: Stock(s, "SMART", "USD") for s in FLEET}
        ib.qualifyContracts(*stks.values())
        chains = load_chain_cache()
        for s in FLEET:
            if not chains.get(s):
                chains[s] = fetch_chain(ib, stks, s)
        save_chain_cache(chains)
        muertos = [s for s in FLEET if not chains.get(s)]
        print(f"whale watch: {len(FLEET)} syms, cadena valida {len(FLEET)-len(muertos)}/{len(FLEET)}"
              + (f" — SIN cadena: {' '.join(muertos)}" if muertos else ""), file=sys.stderr)
        # la cadena secdef mezcla strikes de VARIAS expiries de la clase -> algunos no
        # existen en la elegida. Cache: calificar cada strike UNA vez; los que fallan
        # van a la lista negra.
        qcache = {s: {} for s in FLEET}   # (strike, right) -> Option calificada
        badk = {s: set() for s in FLEET}  # strikes sin contrato en esta expiry
        zeros = {s: 0 for s in FLEET}     # scans seguidos ciego/sin volumen
        center = {}                       # sym -> spot con el que se construyo la parrilla
        pending = {}                      # sym -> lado armado por la lectura anterior, sin confirmar aun
        filt_map = {}                     # sym -> CALLS|PUTS|BOTH, recargado cada pasada completa

        def scan_symbol(s, lines):
            _progress["t"] = time.time()   # vigia: llegar aqui prueba que el simbolo previo no colgo
            try:
                spot = get_spot(ib, stks[s])
                if not chains.get(s): chains[s] = fetch_chain(ib, stks, s)   # reintento: no dejar ticker muerto toda la sesion
                if not spot or not chains.get(s):
                    zeros[s] += 1
                    falta = "spot" if chains.get(s) else "cadena de opciones"
                    lines.append(f"{s} CIEGO sin {falta}")
                    # bug cazado 2026-07-28: "== 2" solo sonaba UNA vez; un simbolo ciego el
                    # resto de la sesion (GLD-style) se quedaba mudo tras el primer aviso,
                    # violando la doctrina "jamas silencio" de la cabecera del fichero. Re-avisa
                    # cada ~30min (6 scans de 5min) mientras siga ciego.
                    if zeros[s] == 2 or (zeros[s] > 2 and zeros[s] % 6 == 0):
                        loud("🕳 BALLENAS CIEGAS", f"BALLENAS CIEGAS {s}: sin {falta} — flujo de {s} SIN cobertura, revisar", "ProAlarm")
                    return
                exp, tc = chains[s]["exp"], chains[s]["tc"]
                c0 = center.get(s)
                if c0 is None:
                    center[s] = spot
                elif abs(spot - c0) / c0 > RECENTER_PCT:
                    # selloff 27-jul: el spot se fue de la parrilla y todo era Unknown
                    nc = fetch_chain(ib, stks, s)
                    if nc: chains[s] = nc; exp, tc = nc["exp"], nc["tc"]
                    qcache[s].clear(); badk[s].clear(); center[s] = spot
                    print(f"{s}: spot {spot:g} a {abs(spot-c0)/c0:.1%} del centro {c0:g} — parrilla reconstruida", file=sys.stderr)
                ks = [k for k in chains[s]["strikes"] if abs(k-spot)/spot <= 0.03 and k not in badk[s]]
                # tope 12 strikes mas cercanos al ATM: QQQ a $700 con strikes
                # de $1 daba 40 strikes = 80 lineas de golpe -> tope de lineas
                # de TWS (con la flota entera conectada) y Error 354 en los
                # simbolos siguientes (AAPL/META ciegos, cazado 2026-07-20).
                ks = sorted(ks, key=lambda k: abs(k - spot))[:12]
                new = [Option(s, exp, k, r, "SMART", tradingClass=tc)
                       for k in ks for r in "CP" if (k, r) not in qcache[s]]
                if new:
                    ok = ib.qualifyContracts(*new)   # los unknown se descartan aqui, jamas matan el scan
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
                    per = []   # (strike, right, volumen): identifica el strike dominante
                    for t in tks:
                        v = t.volume if t.volume == t.volume else 0
                        per.append((t.contract.strike, t.contract.right, v))
                        if t.contract.right == "C": vc += v
                        else: vp += v
                        ib.cancelMktData(t.contract)
                    return vc, vp, per
                vc, vp, per = measure(2.5)
                if vc + vp == 0 and q:
                    vc, vp, per = measure(4.0)   # farm lenta (post-login): un reintento antes de declarar 0
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
                        vc, vp, tag, per = cvol, pvol, " (clase)", []   # sin detalle por-strike: fuente de clase entera
                tot = vc + vp
                if tot == 0:
                    # sin volumen medido: NO se fabrica P/C 0.00 (regla #3)
                    zeros[s] += 1
                    lines.append(f"{s} exp {exp} contratos {len(q)} SIN VOLUMEN MEDIDO")
                    if zeros[s] == 2:
                        badk[s].clear()   # autocura: reintentar strikes vetados
                    if zeros[s] == 2 or (zeros[s] > 2 and zeros[s] % 6 == 0):   # re-avisa, no solo una vez
                        loud("🕳 BALLENAS CIEGAS", f"BALLENAS CIEGAS {s}: {zeros[s]} scans sin volumen de opciones — flujo de {s} SIN cobertura, revisar", "ProAlarm")
                    return
                zeros[s] = 0
                pc = vp / max(vc, 1)
                pc_txt = "inf" if vc == 0 else f"{pc:.2f}"   # vc=0 -> pc numerico gigante sin sentido; solo cosmetico, la decision de umbral abajo no cambia
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
                                         f" age {rec['feed_age_s']}s")
                            # alarma top-10 Nasdaq (Yunior 2026-07-28: "large bullish/bearish
                            # options trade in top 10 nasdaq"), INDEPENDIENTE del gate P/C:
                            # dispara solo por MAGNITUD de premium neto firmado. Detector DISTINTO
                            # al de ratio put/call de abajo — mensaje propio ("Alerta premium"),
                            # jamas "alto volumen de calls/puts" que colisionaba con BALLENA y
                            # confundia (Yunior 2026-07-28: "el mensaje es el mismo... y confunde").
                            # capitanes (SPY/QQQ/SMH) SOLO con umbral p97 propio medido (n>=30);
                            # single names sin historia siguen con el $2M etiquetado de siempre
                            _t = UW_PTH.get(s)
                            _armed = _t is not None or s in NASDAQ10
                            _bull = _t["bull"] if _t else UW_PREM_BULL
                            _bear = _t["bear"] if _t else UW_PREM_BEAR
                            _exit = _t["exit"] if _t else UW_PREM_EXIT
                            if s in (NASDAQ10 + UW_CAPTAINS) and _armed and rec["feed_age_s"] is not None and rec["feed_age_s"] <= UW_MAX_AGE_S:
                                sp = uw_prem["signed_premium"]
                                pkey = f"{s}_uwprem"
                                pprev = state.get(pkey, "mid")
                                pcur = pprev
                                if sp >= _bull: pcur = "bull"
                                elif sp <= _bear: pcur = "bear"
                                elif pprev == "bull" and sp < _exit: pcur = "mid"
                                elif pprev == "bear" and sp > -_exit: pcur = "mid"
                                if pcur != pprev:
                                    state[pkey] = pcur
                                    if pcur in ("bull", "bear"):
                                        jappend("data/whale_alerts.jsonl",
                                                {"ts": int(time.time()), "side": pcur.upper(),
                                                 "prev": "UW_PREMIUM", "sym": s,
                                                 "signed_premium": round(sp, 0),
                                                 "call": round(uw_prem["net_call_premium"], 0),
                                                 "put": round(uw_prem["net_put_premium"], 0)})
                                        emoji = "🟢📈" if pcur == "bull" else "🔴📉"
                                        tag2 = "ALCISTA" if pcur == "bull" else "BAJISTA"
                                        # cual lado domina el premium (calls o puts), no solo el neto firmado:
                                        lado_op = "calls" if abs(uw_prem["net_call_premium"]) >= abs(uw_prem["net_put_premium"]) else "puts"
                                        mm = abs(sp) / 1e6
                                        loud(f"{emoji} ALERTA PREMIUM {tag2} {s}",
                                             f"Alerta premium: barrida de opciones {tag2.lower()} en {s} — neto "
                                             f"${sp:,.0f} (call ${uw_prem['net_call_premium']:,.0f} "
                                             f"put ${uw_prem['net_put_premium']:,.0f}), umbral SIN CALIBRAR",
                                             "ProAlert",
                                             voice_msg=f"Barrida {tag2.lower()} en {s}: {mm:.1f} millones "
                                                       f"netos comprados en {lado_op} en quince minutos.")
                    except Exception as e:
                        print(f"{s}: UW premium fallo ({e})", file=sys.stderr)
                lines.append(f"{s} volC {vc:,.0f} volP {vp:,.0f} P/C {pc_txt}{tag} exp {exp}{uw_suffix}")
                jappend("data/whale_flow_hist.jsonl",
                        {"ts": int(time.time()), "sym": s, "vc": int(vc), "vp": int(vp),
                         "pc": round(pc, 3), "spot": round(float(spot), 4),
                         "src": "clase" if tag else "strikes", "exp": exp})
                prev = state.get(s, "mid")
                th = PCTH.get(s)   # percentil propio del ticker; sin historia suficiente -> estatico
                t_puts = th["puts"] if th else PC_PUTS
                t_calls = th["calls"] if th else PC_CALLS
                t_xputs = th["xputs"] if th else EXIT_PUTS
                t_xcalls = th["xcalls"] if th else EXIT_CALLS
                if tot >= VMIN:
                    state[f"{s}_freshts"] = time.time()   # ultima lectura CON volumen suficiente para significar algo
                    if pc >= t_puts: cur_raw = "puts"
                    elif pc <= t_calls: cur_raw = "calls"
                    elif prev == "puts" and pc < t_xputs: cur_raw = "mid"
                    elif prev == "calls" and pc > t_xcalls: cur_raw = "mid"
                    else: cur_raw = prev
                else:
                    # bug cazado 2026-07-28: con tot<VMIN el ratio no es fiable para ENTRAR ni
                    # SALIR de puts/calls, asi que se conservaba prev indefinidamente — si el
                    # flujo se seca del todo tras una ballena real, el estado se congelaba en
                    # "puts"/"calls" para siempre (opt_flow.txt/voz seguian anunciando una
                    # ballena horas despues de que el volumen real desaparecio). Decaimiento por
                    # antiguedad: sin una lectura CON volumen suficiente en STATE_STALE_S, la
                    # señal expira a mid en silencio (no es un CRUCE, no exige voz ni confirmacion).
                    stale = time.time() - state.get(f"{s}_freshts", 0) > STATE_STALE_S
                    cur_raw = "mid" if (prev in ("puts", "calls") and stale) else prev
                # SEÑAL MARGINAL != DECISIVA (~/CLAUDE.md #3): una NUEVA entrada a puts/calls exige
                # 2 lecturas consecutivas del mismo lado antes de sonar (doctrina PRINT-O-NADA).
                # EWY 2026-07-28 disparo con pc=2.006 (+0.3% sobre el umbral) y revirtio 7min
                # despues sin una 2a lectura que confirmara — exactamente el caso que esto corta.
                if cur_raw in ("puts", "calls") and cur_raw != prev:
                    if pending.get(s) == cur_raw:
                        cur = cur_raw
                        del pending[s]
                    else:
                        pending[s] = cur_raw
                        cur = prev
                else:
                    pending.pop(s, None)
                    cur = cur_raw
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
                        # ley 13 (espada-ballena): PUTS = piso, se refuerza -> rebote mas
                        # probable; CALLS = techo, se refuerza -> retroceso mas probable.
                        explica = "rebote probable" if cur == "puts" else "bajada probable"
                        loud("🐋📈 ALERTA BALLENA CRECE", f"Sigue entrando volumen de {cur} en {s}, {explica}.", "ProAlarm",
                             voice_msg=f"Alerta ballena, sigue entrando {cur} en {s}, {explica}.")
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
                    if cur in ("puts", "calls"):
                        # filtro por ticker (data/whale_alert_filter.txt, ajustable desde el
                        # panel de chart_bridge): silencia el lado no deseado; el estado ya
                        # quedo actualizado arriba, la histeresis sigue coherente aunque no suene.
                        lado_txt = "PUTS" if cur == "puts" else "CALLS"
                        if filt_map.get(s, "BOTH") in ("BOTH", lado_txt):
                            right = "P" if cur == "puts" else "C"
                            strike = dominant_strike(per, right) if not tag else None
                            wall = wall_near(s, strike, right) if strike is not None else None
                            nivel = f", strike {strike:g}" if strike is not None else ""
                            if wall is not None:
                                nivel += f" — cerca del muro de {lado_txt.lower()} medido en ${wall:g}"
                            detalle = f"alto volumen de {cur} en {s}{nivel}"
                            loud(f"🐋 ALERTA BALLENA {lado_txt}", f"Alerta ballena: {detalle}", "ProAlarm",
                                 voice_msg=f"Alerta ballena, {detalle}.")
            except Exception as e:
                # bug cazado 2026-07-28: este except lo cubria TODO (qualify/measure/get_spot)
                # sin tocar zeros[s] ni lines[] -> un simbolo que empieza a fallar (timeout tras
                # el fix de RequestTimeout de arriba, o cualquier otra excepcion) desaparecia de
                # opt_flow.txt para siempre sin que BALLENAS CIEGAS pudiera dispararse jamas.
                zeros[s] += 1
                lines.append(f"{s} ERROR: {e}")
                if zeros[s] == 2:
                    loud("🕳 BALLENAS CIEGAS", f"BALLENAS CIEGAS {s}: excepcion repetida ({e}) — flujo de {s} SIN cobertura, revisar", "ProAlarm")
                print(f"{s}: {e}", file=sys.stderr)

        while ib.isConnected():
            lines = []
            filt_map = load_ticker_filter()   # recarga por si el panel de config lo cambio
            for s in FLEET:
                scan_symbol(s, lines)
            with open("data/opt_flow.txt", "w") as f:
                f.write(time.strftime("%H:%M:%S") + " ±3% ATM volumen dia (expiry por simbolo)\n" + "\n".join(lines) + "\n")
            save_state(state)
            save_chain_cache(chains)
            lt = time.localtime()
            if lt.tm_hour >= 16: print("cierre 16:00 — whale watch fin de sesion", file=sys.stderr); ib.disconnect(); sys.exit(0)
            # carril rapido (Yunior 2026-07-28 "seleccionar hasta 5 tickers para detectar
            # terremoto rapido"): mientras dura el resto del ciclo de 5min, los simbolos de
            # data/whale_priority.txt (max 5, ajustable desde el panel) se re-escanean cada
            # PRIORITY_CYCLE_S en vez de esperar la vuelta completa de los 30 — mismo reqMktData
            # ya usado arriba, mismo cupo de lineas ya respetado, SIN tick-by-tick (HIRO probo en
            # vivo que no existe en tiempo real para opciones — docs/HIRO-2026-07-25.md).
            priority = [s for s in (load_symlist(PRIORITY_F) or []) if s in FLEET][:PRIORITY_MAX]
            elapsed = 0
            while priority and elapsed < 300 and ib.isConnected():
                # bug cazado 2026-07-28: WATCHDOG_S(300) == este sleep de 300s total y _progress
                # solo se tocaba al INICIO de scan_symbol -> el tiempo del ultimo simbolo del
                # ciclo se SUMABA a este sleep antes de volver a tocar _progress, autodisparando
                # el watchdog sobre un proceso sano casi cada ciclo sin carril prioritario. Tocar
                # aqui, justo antes de un sleep INTENCIONAL, separa "colgado" de "esperando adrede".
                _progress["t"] = time.time()
                ib.sleep(PRIORITY_CYCLE_S)
                elapsed += PRIORITY_CYCLE_S
                fast_lines = []
                for s in priority:
                    scan_symbol(s, fast_lines)
                save_state(state)
            if not priority:
                _progress["t"] = time.time()
                ib.sleep(300)
        raise ConnectionError("TWS fuera")
    except SystemExit: raise
    except Exception as e:
        fails += 1
        if fails >= FAIL_EXIT:
            print(f"whale watch: {fails} fallos seguidos ({e}) — SALGO para que el keepalive "
                  f"recargue codigo/puerto fresco", file=sys.stderr)
            sys.exit(1)
        print(f"whale watch caido: {e} — retry 30s ({fails}/{FAIL_EXIT})", file=sys.stderr)
        time.sleep(30)
