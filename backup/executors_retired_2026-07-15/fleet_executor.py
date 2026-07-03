#!/usr/bin/env python3
"""fleet_executor.py — leveraged-ETF execution layer over the C++ signal fleet.

ORDEN YUNIOR 2026-07-11 (literal, esto es ley):
  - No se opera el ticker: BUY del subyacente -> comprar ETF BULL apalancado;
    señal de BAJADA (BUY PUT) -> comprar ETF BEAR/inverso.
  - BULL: "we buy and sell higher only, if not we keep the bag" -> un bull
    SOLO se vende por encima del entry (+BAG_MIN_GAIN% que cubre comisiones);
    si la señal de venta llega por debajo, se AGUANTA LA BOLSA y se deja una
    limit GTC de recuperacion en el broker (sobrevive reinicios y muertes).
  - BEAR: "we dont hold the bag for the bearish" -> STOP GTC servidor-side
    a -BEAR_STOP_PCT% del fill, SIEMPRE; ademas sale con la señal del bot.
  - IBKR = primario (TFSA U26942420, unica cuenta permitida). Alpaca = fallback
    y es cuenta PAPER (clave PK) -> si se usa, banner LOUD "PAPER, NO REAL".
  - Se activa solo cuando la cuenta este fondeada: preflight NetLiq >= MIN_EQUITY
    USD. Kill switch: rm data/etf_armed (sin el archivo = dry-run, solo log).

Mapa verificado en vivo 2026-07-11 (Alpaca 14k assets + IBKR qualify):
data/leveraged_map.json. Sin bear ETF listado (INTC/ASML/TXN/NOK/DRAM/CPER):
el lado put queda señal-solo.

Diseño: tail de los 16 *_operations.log (formato "FECHA | TITULO | MSG",
WARMUP filtrado). Los motores C++ validados NO se tocan. Python/ib_insync
porque la conexion al broker con fills/stops/reconcile no tiene gemelo C++
(precedente: screener exec_trade.py); no esta en el camino de latencia de
ticks — las señales son eventos de bar de 1m.

Edge cases cubiertos: replay de log tras restart (offsets persistidos, arranque
en EOF), inode rotado, señales duplicadas (cooldown + posicion abierta), shares
enteras (API fraccional bloqueada), presupuesto vivo por slot, cap de abiertas,
bolsas no bloquean slots (el cash manda), fills parciales, stop imposible ->
cierre inmediato, reconcile de posiciones/ordenes huerfanas al arrancar y cada
10 min, TWS caido -> reconexion + fallback, precio sin subscripcion IBKR ->
cadena Alpaca quote/trade fresco o NO se opera (jamas precio viejo/delayed).
"""
import json, math, os, re, sqlite3, subprocess, sys, time, urllib.request
from datetime import datetime

ROOT = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from ib_insync import IB, Stock, LimitOrder, StopOrder, MarketOrder  # noqa

# ---------------- config (env-overridable) ----------------
def envf(k, d): v = os.getenv(k); return float(v) if v else d
MIN_EQUITY   = envf("ETF_MIN_EQUITY", 500.0)    # USD; orden 2026-07-11: opera con >500 en activos
MAX_OPEN     = int(envf("ETF_MAX_OPEN", 4))     # posiciones activas (bolsas no cuentan)
BAG_MAX      = int(envf("ETF_BAG_MAX", 6))      # bolsas max simultaneas
BAG_MIN_GAIN = envf("ETF_BAG_MIN_GAIN", 1.0)    # % minimo sobre entry (el floor real suma fees, abajo)
BEAR_STOP    = envf("ETF_BEAR_STOP", 5.0)       # % stop servidor en el bear ETF (señal regular)
COOLDOWN_S   = envf("ETF_COOLDOWN_S", 900)      # anti re-entrada por ETF
CASH_RESERVE = envf("ETF_CASH_RESERVE", 25.0)   # USD que JAMAS se gastan (colchon anti-negativo)
FEE_MIN_USD  = envf("ETF_FEE_MIN_USD", 1.0)     # peor caso comision IBKR por lado (micro-orden)
# STOP CATASTROFICO en bulls (orden 2026-07-11 "stop loss should be on price
# as well... we are handling a lot of money in the future"): la bolsa sigue
# viva para caidas normales (backtest: bolsas ~-20% recuperan 86%), pero un
# colapso del nombre se corta a -25% del ETF (~-12% subyacente en 2x) con STP
# GTC SERVIDOR-side. Convive con la GTC de recuperacion en un grupo OCA del
# broker: una se llena -> la otra se cancela SOLA (imposible oversell, funciona
# con el Mac muerto). ETF_BULL_STOP=0 lo desactiva.
BULL_STOP    = envf("ETF_BULL_STOP", 25.0)
# BEARS por TERREMOTO (orden 2026-07-11 "only use leveraged inversed when sure
# and real fast when earthquake"): el CUSUM banner-grade (precision 88-99% por
# ticker) es el gatillo, NO la señal PUT regular (esa fallo el backtest, WR37).
# Stop apretado, time-stop, salida por quake inverso y EOD 15:50 SIEMPRE
# (inverso apalancado jamas pasa la noche).
QUAKE_BEARS  = envf("ETF_QUAKE_BEARS", 1) > 0
# stop del quake-bear NORMALIZADO por leverage (auditoria pro 2026-07-11: un
# -3% plano era 1% de QQQ en SQQQ (chop-out) vs 3% de TSLA en TSLS — el mismo
# error del stop plano que mato a los bears regulares). Riesgo subyacente
# constante: stop_etf = lev * QUAKE_USTOP, acotado [1.5%, 4.5%].
QUAKE_USTOP  = envf("ETF_QUAKE_UNDERLYING_STOP", 1.5)   # % del SUBYACENTE
QUAKE_HOLD   = envf("ETF_QUAKE_HOLD_MIN", 45)    # min max en un quake-bear
MAX_BEARS    = int(envf("ETF_MAX_BEARS", 2))     # bears simultaneos max
# ===== CIRCUIT BREAKERS (auditoria pro 2026-07-11: "el peor caso era el caso
# por defecto" — 4 semis apalancados comprados en el mismo panico sin freno).
# (a) HALT diario: perdida realizada del dia >= DAY_LOSS_PCT% del NetLiq =>
#     no mas COMPRAS hasta la proxima sesion (las salidas siguen vivas)
# (b) cap por sector: max BUCKET_MAX bulls activos por bucket (tech/commod);
#     ademas >=2 bolsas en el bucket bloquean nuevas compras ahi (no promediar
#     un regimen muriendo)
# (c) cap de apalancamiento bruto: sum(lev*notional) <= GROSS_CAP x NetLiq
DAY_LOSS_PCT = envf("ETF_DAY_LOSS_PCT", 5.0)
BUCKET_MAX   = int(envf("ETF_BUCKET_MAX", 2))
GROSS_CAP    = envf("ETF_GROSS_CAP", 1.5)
# BEARS OFF por defecto: el backtest 90d de la traduccion (data/leveraged_bt_90d.txt)
# dio WR 37% / -84% — el stop plano -5% en el ETF es 2-5x mas ancho que los stops
# afinados de los bots y las fees se comen el edge corto. Orden permanente #7
# (WR>=70 o la estrategia queda OFF) manda. ETF_BEARS=1 en el keepalive activa.
BEARS_ON     = envf("ETF_BEARS", 0) > 0
FX_FALLBACK  = envf("ETF_USDCAD_FALLBACK", 1.45)
ACCOUNT      = os.getenv("ETF_ACCOUNT", "U26942420")   # TFSA: la UNICA permitida
ARMED_FILE   = "data/etf_armed"
STATE_FILE   = "data/etf_positions.json"
LOG_FILE     = "fleet_executor.log"
HOST, PORT, CID = "127.0.0.1", 7496, 90

MAP = json.load(open("data/leveraged_map.json"))          # base -> {bull, bear, lev_*, bucket}
BULL_OF = {b: m["bull"] for b, m in MAP.items()}
BEAR_OF = {b: m["bear"] for b, m in MAP.items() if m.get("bear")}
ALL_ETFS = set(BULL_OF.values()) | set(BEAR_OF.values())
BEAR_ETFS = set(BEAR_OF.values())
BASES = list(MAP.keys())
LEV = {}                                                   # etf -> leverage
BUCKET_OF = {}                                             # etf -> sector bucket
for b, m in MAP.items():
    LEV[m["bull"]] = m.get("lev_bull", 2); BUCKET_OF[m["bull"]] = m.get("bucket", "tech")
    if m.get("bear"):
        LEV[m["bear"]] = m.get("lev_bear", 1); BUCKET_OF[m["bear"]] = m.get("bucket", "tech")

def quake_stop_pct(etf):
    return min(4.5, max(1.5, LEV.get(etf, 1) * QUAKE_USTOP))

def bull_stop_pct(etf):
    # -25% calibrado para 2x; se escala por leverage real (TQQQ 3x -> mas aire)
    return min(35.0, max(15.0, BULL_STOP * LEV.get(etf, 2) / 2.0)) if BULL_STOP > 0 else 0

AL = {}
for line in open("alpaca.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1); AL[k] = v.strip().strip('"')
AL_H = {"APCA-API-KEY-ID": AL["ALPACA_KEY"], "APCA-API-SECRET-KEY": AL["ALPACA_SECRET"],
        "Content-Type": "application/json"}

def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    with open(LOG_FILE, "a") as f: f.write(line + "\n")

def banner(title, msg):
    log(f"BANNER {title} | {msg}")
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg[:200]}" with title "{title[:60]}" sound name "Glass"'],
                       timeout=10, capture_output=True)
    except Exception:
        pass

# ---------------- estado persistido ----------------
def load_state():
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"positions": {}, "offsets": {}, "cooldown": {}, "history": []}
STATE = load_state()
def save_state():
    if len(STATE.get("history", [])) > 4000:            # el CSV es el historial
        STATE["history"] = STATE["history"][-4000:]     # completo; esto es cache
    tmp = STATE_FILE + ".tmp"
    json.dump(STATE, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE_FILE)

def armed():
    return os.path.exists(ARMED_FILE)

def cent_ceil(px):
    """Redondeo SIEMPRE hacia arriba al centavo en limits de VENTA — round()
    normal podia caer 1c bajo el profit_floor y violar 'never sell on loss'
    (adversarial review 2026-07-11)."""
    return math.ceil(px * 100 - 1e-9) / 100

def profit_floor(entry, qty):
    """Precio minimo de venta que GARANTIZA ganancia neta de comisiones
    (orden: 'consider broker fees to sell in profit all the time, never sell
    on loss'). Modelo de fees corregido en auditoria pro 2026-07-11: IBKR
    cobra $0.005/sh con minimo (~$0.35 tiered, verificado en vivo: micro-
    ordenes pagan centavos) y CAP de 0.5% del notional — el modelo anterior
    ($1 plano/lado) DOBLABA el floor en posiciones chicas y retenia bolsas
    mas tiempo del necesario."""
    notional = max(entry * max(qty, 1), 1e-9)
    fee_side = min(max(0.005 * max(qty, 1), FEE_MIN_USD * 0.35), 0.005 * notional)
    fee_pct = 2 * fee_side / notional * 100
    return cent_ceil(entry * (1 + max(BAG_MIN_GAIN, fee_pct + 0.2) / 100))

LEDGER = "data/etf_ledger.csv"
DB_FILE = "trades.db"
_DB = [None]

def db():
    """SQLite local (orden 2026-07-11 'register all operations and trades in
    database locally'): etf_operations + etf_signals en trades.db, WAL para
    lectores concurrentes. La DB JAMAS bloquea trading (todo en try/except;
    el CSV sigue siendo el respaldo plano)."""
    if _DB[0] is None:
        c = sqlite3.connect(DB_FILE, timeout=5)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE IF NOT EXISTS etf_operations(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, event TEXT NOT NULL,
            etf TEXT, base TEXT, side TEXT, qty INTEGER, px REAL, fee_usd REAL,
            pnl_pct TEXT, pnl_usd REAL DEFAULT 0, note TEXT)""")
        try: c.execute("ALTER TABLE etf_operations ADD COLUMN pnl_usd REAL DEFAULT 0")
        except Exception: pass
        c.execute("""CREATE TABLE IF NOT EXISTS etf_signals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, base TEXT NOT NULL,
            action TEXT NOT NULL, sig_px REAL, msg TEXT)""")
        c.commit()
        try:   # migracion unica: CSV existente -> DB si la tabla nace vacia
            if not c.execute("SELECT 1 FROM etf_operations LIMIT 1").fetchone() \
               and os.path.exists(LEDGER):
                import csv as _csv
                rows = [(r["ts"], r["event"], r["etf"], r["base"], r["side"],
                         r["qty"], r["px"], r["fee_usd"], r["pnl_pct"], r["note"])
                        for r in _csv.DictReader(open(LEDGER))]
                c.executemany("INSERT INTO etf_operations(ts,event,etf,base,side,"
                              "qty,px,fee_usd,pnl_pct,note) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
                c.commit()
                log(f"db: {len(rows)} filas migradas del CSV")
        except Exception as e:
            log(f"db migracion: {e}")
        _DB[0] = c
    return _DB[0]

def db_signal(base, action, sig_px, msg):
    try:
        db().execute("INSERT INTO etf_signals(ts,base,action,sig_px,msg) VALUES(?,?,?,?,?)",
                     (f"{datetime.now():%Y-%m-%d %H:%M:%S}", base, action, sig_px, msg[:300]))
        db().commit()
    except Exception as e:
        log(f"db señal error: {e}")

def ledger(event, etf, base, side, qty, px, fee=0.0, pnl="", note="", pnl_usd=0.0):
    """Historial COMPLETO append-only: CSV + trades.db (orden: 'records should
    be kept by operations, full history'). pnl_usd alimenta el HALT diario."""
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a") as f:
        if new:
            f.write("ts,event,etf,base,side,qty,px,fee_usd,pnl_pct,pnl_usd,note\n")
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S},{event},{etf},{base},{side},"
                f"{qty},{px:.4f},{fee:.2f},{pnl},{pnl_usd:.2f},{note}\n")
    try:
        db().execute("INSERT INTO etf_operations(ts,event,etf,base,side,qty,px,"
                     "fee_usd,pnl_pct,pnl_usd,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (f"{datetime.now():%Y-%m-%d %H:%M:%S}", event, etf, base, side,
                      qty, px, fee, pnl, pnl_usd, note))
        db().commit()
    except Exception as e:
        log(f"db ledger error: {e}")

def day_realized_usd():
    """PnL realizado HOY (ventas + cierres server-side) — alimenta el circuit
    breaker diario. DB caida => 0 con log (no bloquea, pero se grita)."""
    try:
        row = db().execute(
            "SELECT COALESCE(SUM(pnl_usd),0) FROM etf_operations "
            "WHERE ts >= ? AND event IN ('sell','sell_partial','closed_serverside','closed_external')",
            (f"{datetime.now():%Y-%m-%d} 00:00:00",)).fetchone()
        return float(row[0])
    except Exception as e:
        log(f"day_realized error: {e}"); return 0.0

# ---------------- precio confiable (jamas delayed) ----------------
def alpaca_price(sym):
    """(price, age_s) del quote IEX; fallback ultimo trade. None si viejo."""
    try:
        r = urllib.request.Request(
            f"https://data.alpaca.markets/v2/stocks/{sym}/quotes/latest?feed=iex", headers=AL_H)
        q = json.loads(urllib.request.urlopen(r, timeout=5).read())["quote"]
        bid, ask = q.get("bp") or 0, q.get("ap") or 0
        ts = datetime.fromisoformat(q["t"].split(".")[0].rstrip("Z") + "+00:00").timestamp()
        if bid > 0 and ask > bid and time.time() - ts < 60:
            return (bid, ask)
    except Exception:
        pass
    try:
        r = urllib.request.Request(
            f"https://data.alpaca.markets/v2/stocks/{sym}/trades/latest?feed=iex", headers=AL_H)
        t = json.loads(urllib.request.urlopen(r, timeout=5).read())["trade"]
        ts = datetime.fromisoformat(t["t"].split(".")[0].rstrip("Z") + "+00:00").timestamp()
        if t["p"] > 0 and time.time() - ts < 300:
            return (t["p"] * 0.999, t["p"] * 1.001)
    except Exception:
        pass
    return None

def ref_price(ib, sym):
    """IBKR snapshot si hay permisos; si no, Alpaca fresco; si no, None."""
    if ib and ib.isConnected():
        try:
            c = Stock(sym, "SMART", "USD"); ib.qualifyContracts(c)
            tk = ib.reqMktData(c, "", True, False)   # snapshot normal: gratis
            # con subscripcion propia; sin ella -> err 354, ticks NaN y caemos
            # a Alpaca (el "$0.01" es del REGULATORY snapshot, que NO usamos)
            ib.sleep(2.5)
            if tk.bid and tk.ask and tk.bid > 0 and tk.ask > tk.bid:
                return (tk.bid, tk.ask)
            if tk.last and tk.last > 0:
                return (tk.last * 0.999, tk.last * 1.001)
        except Exception:
            pass
    return alpaca_price(sym)

# ---------------- venue IBKR ----------------
class Ibkr:
    def __init__(self):
        self.ib = IB(); self.last_try = 0; self.connect_time = 0
    def connected(self):
        if self.ib.isConnected(): return True
        if time.time() - self.last_try < 30: return False
        self.last_try = time.time()
        try:
            self.ib.connect(HOST, PORT, clientId=CID, timeout=15, account=ACCOUNT)
            self.ib.reqMarketDataType(1)             # REALTIME only, jamas delayed
            self.connect_time = time.time()
            log(f"IBKR conectado (cuenta {ACCOUNT})")
            return True
        except Exception as e:
            log(f"IBKR sin conexion: {e}"); return False
    def fx_rate(self):
        """USDCAD del broker si esta (ExchangeRate tag); si no, fallback
        conservador 1.45 (subestima el poder de compra = lado seguro)."""
        try:
            for v in self.ib.accountValues(ACCOUNT):
                if v.tag == "ExchangeRate" and v.currency == "USD":
                    r = float(v.value)
                    if 0.4 < r < 1.0:      # USD->CAD viene como CAD/USD invertido
                        return 1.0 / r
                    if 1.0 < r < 2.0:
                        return r
        except Exception:
            pass
        return FX_FALLBACK
    def netliq_usd(self):
        try:
            vals = {(v.tag, v.currency): float(v.value)
                    for v in self.ib.accountValues(ACCOUNT)
                    if v.tag in ("NetLiquidation", "ExchangeRate", "AvailableFunds")}
            nl_base = vals.get(("NetLiquidation", "CAD")) or vals.get(("NetLiquidation", "USD"))
            if ("NetLiquidation", "USD") in vals: return vals[("NetLiquidation", "USD")]
            fx = max(self.fx_rate(), FX_FALLBACK)    # el mas conservador gana
            return (nl_base or 0) / fx
        except Exception as e:
            log(f"netliq error: {e}"); return 0
    def avail_usd(self):
        """min(AvailableFunds, SettledCash) — cuenta CASH: comprar con proceeds
        sin liquidar y revender = free-riding (auditoria pro 2026-07-11)."""
        try:
            vals = {}
            for v in self.ib.accountValues(ACCOUNT):
                if v.tag in ("AvailableFunds", "SettledCash"):
                    x = float(v.value)
                    vals[v.tag] = x if v.currency == "USD" else x / FX_FALLBACK
            if not vals: return 0
            return min(vals.values())
        except Exception: pass
        return 0
    def qualify(self, sym):
        c = Stock(sym, "SMART", "USD"); self.ib.qualifyContracts(c); return c
    def buy_limit(self, sym, qty, px):
        tr = self.ib.placeOrder(self.qualify(sym),
                                LimitOrder("BUY", qty, round(px, 2), tif="DAY",
                                           account=ACCOUNT, outsideRth=False))
        # 90s (era 300): un limit marketable llena en segundos; esperar 5min
        # bloqueaba el loop entero y podia perder la ventana EOD de los bears
        return self._wait_fill(tr, 90)
    def sell_limit_day(self, sym, qty, px):
        tr = self.ib.placeOrder(self.qualify(sym),
                                LimitOrder("SELL", qty, cent_ceil(px), tif="DAY", account=ACCOUNT))
        return self._wait_fill(tr, 120)
    def sell_market(self, sym, qty):
        tr = self.ib.placeOrder(self.qualify(sym), MarketOrder("SELL", qty, account=ACCOUNT))
        return self._wait_fill(tr, 120)
    def _place_checked(self, sym, o):
        """Coloca y VERIFICA aceptacion (adversarial review: un stop rechazado
        en silencio dejaba un bear sin proteccion). Rechazo -> excepcion."""
        tr = self.ib.placeOrder(self.qualify(sym), o)
        self.ib.sleep(1.5)
        if tr.orderStatus.status in ("Cancelled", "Inactive", "ApiCancelled"):
            raise RuntimeError(f"orden rechazada: {tr.orderStatus.status} {tr.log[-1].message if tr.log else ''}")
        return tr.order.orderId
    def place_gtc_sell(self, sym, qty, px, oca=None):   # bolsa bull: recuperacion
        o = LimitOrder("SELL", qty, cent_ceil(px), tif="GTC", account=ACCOUNT)
        if oca: o.ocaGroup, o.ocaType = oca, 1          # una se llena -> la otra muere
        return self._place_checked(sym, o)
    def place_gtc_stop(self, sym, qty, px, oca=None):   # stop servidor-side
        o = StopOrder("SELL", qty, round(px, 2), tif="GTC", account=ACCOUNT)
        o.triggerMethod = 3      # double-last: un print suelto en ETF fino no dispara
        if oca: o.ocaGroup, o.ocaType = oca, 1
        return self._place_checked(sym, o)
    def cancel_confirmed(self, order_id, sym=None, timeout=10):
        """Cancela y ESPERA confirmacion (adversarial review: el cancel async
        + venta manual inmediata podia dejar DOS sells vivos = short). Refresca
        reqAllOpenOrders (ordenes de sesiones previas invisibles a openTrades)
        y verifica simbolo antes de cancelar (orderIds se reusan tras reiniciar
        TWS). True = confirmado muerto; False = NO vender manualmente."""
        try:
            self.ib.reqAllOpenOrders(); self.ib.sleep(1)
            target = None
            for tr in self.ib.openTrades():
                if tr.order.orderId == order_id and \
                   (sym is None or tr.contract.symbol == sym):
                    target = tr; break
            if target is None:
                return True                      # ya no existe: muerto
            self.ib.cancelOrder(target.order)
            end = time.time() + timeout
            while time.time() < end:
                self.ib.sleep(0.5)
                if target.orderStatus.status in ("Cancelled", "ApiCancelled", "Inactive", "Filled"):
                    # Filled = el stop gano la carrera: la posicion ya salio
                    return target.orderStatus.status != "Filled"
            return False
        except Exception as e:
            log(f"cancel_confirmed error {sym} #{order_id}: {e}")
            return False
    def cancel(self, order_id):
        for tr in self.ib.openTrades():
            if tr.order.orderId == order_id:
                self.ib.cancelOrder(tr.order)
    def broker_qty(self, sym):
        """Cantidad REAL en el broker (cuenta = fuente de verdad; el humano
        tambien opera esta cuenta a mano). None si no se pudo consultar."""
        try:
            for p in self.ib.positions(ACCOUNT):
                if p.contract.symbol == sym:
                    return int(p.position)
            return 0
        except Exception:
            return None
    def _wait_fill(self, tr, timeout):
        end = time.time() + timeout
        while time.time() < end and not tr.isDone():
            self.ib.sleep(1)
        filled = tr.filled()
        avg = tr.orderStatus.avgFillPrice or 0
        if not tr.isDone():
            self.ib.cancelOrder(tr.order); self.ib.sleep(2)
            filled = tr.filled(); avg = tr.orderStatus.avgFillPrice or 0
        try:
            end2 = time.time() + 4        # commissionReport llega DESPUES del
            while time.time() < end2:     # fill (mensaje aparte, docs ib_insync)
                if filled and any(f.commissionReport and f.commissionReport.execId
                                  for f in tr.fills):
                    break
                self.ib.sleep(0.5)
            self.last_fee = sum(f.commissionReport.commission
                                for f in tr.fills
                                if f.commissionReport and f.commissionReport.execId)
        except Exception:
            self.last_fee = 0.0
        return (int(filled), float(avg))

# ---------------- venue Alpaca (PAPER — fallback, NO dinero real) ----------------
class AlpacaPaper:
    BASE = "https://paper-api.alpaca.markets"
    def _post(self, path, body):
        r = urllib.request.Request(self.BASE + path, data=json.dumps(body).encode(),
                                   headers=AL_H, method="POST")
        return json.loads(urllib.request.urlopen(r, timeout=15).read())
    def order(self, sym, side, qty, typ, px=None, tif="day", stop=None):
        b = {"symbol": sym, "side": side, "qty": str(qty), "type": typ, "time_in_force": tif}
        if px: b["limit_price"] = str(round(px, 2))
        if stop: b["stop_price"] = str(round(stop, 2))
        o = self._post("/v2/orders", b)
        return o.get("id")

# ---------------- parser de señales ----------------
# titulo "SYM: BUY NOW" / "SELL NOW" / "SELL-STOP" / "BUY PUT" / "BUY CALL" / "PUT-STOP"
# (BUY CALL reemplaza SELL PUT 2026-07-13 — mismo cierre de posicion bajista,
# "SELL PUT" queda reconocido por compat con logs viejos)
RX_TITLE = re.compile(r"^([A-Z]+): (BUY NOW|SELL NOW|SELL-STOP|BUY PUT|BUY CALL|SELL PUT|PUT-STOP)$")
# terremoto banner-grade: "SYM TERREMOTO ALZA|CAIDA" — gatillo de los quake-bears
RX_QUAKE = re.compile(r"^([A-Z]+) TERREMOTO (ALZA|CAIDA)$")
RX_PRICE = re.compile(r"@ ([\d.]+)")

def new_log_lines():
    out = []
    for base in BASES:
        path = f"{base.lower()}_operations.log"
        try: st = os.stat(path)
        except FileNotFoundError: continue
        rec = STATE["offsets"].get(path)
        if rec is None or rec.get("ino") != st.st_ino or st.st_size < rec.get("off", 0):
            STATE["offsets"][path] = {"ino": st.st_ino, "off": st.st_size}   # EOF: JAMAS replay
            continue
        if st.st_size > rec["off"]:
            with open(path, "rb") as f:
                f.seek(rec["off"])
                raw = f.read()
            # solo consumir hasta el ULTIMO \n: una linea a medio escribir por
            # el bot C++ se dejaria para el proximo ciclo (adversarial review:
            # avanzar el offset sobre una linea parcial PERDIA esa señal)
            nl = raw.rfind(b"\n")
            if nl < 0: continue
            rec["off"] += nl + 1
            chunk = raw[:nl + 1].decode("utf-8", "replace")
            for line in chunk.splitlines():
                parts = [p.strip() for p in line.split(" | ", 2)]
                if len(parts) != 3 or parts[1].startswith("WARMUP"): continue
                m = RX_TITLE.match(parts[1])
                if m:
                    pm = RX_PRICE.search(parts[2])
                    out.append((m.group(1), m.group(2), float(pm.group(1)) if pm else 0, parts[2]))
                    continue
                q = RX_QUAKE.match(parts[1])
                if q:
                    out.append((q.group(1), "QUAKE " + q.group(2), 0, parts[2]))
    return out

# ---------------- motor de reglas ----------------
def open_active():   # posiciones no-bolsa
    return [p for p in STATE["positions"].values() if not p.get("bag")]
def bags():
    return [p for p in STATE["positions"].values() if p.get("bag")]

def preflight(ibkr, etf, is_buy):
    if not armed():
        return (None, "DRY-RUN (data/etf_armed ausente)")
    live = ibkr.connected()
    venue = ibkr if live else AlpacaPaper()
    if is_buy:
        nl = 0
        if live:
            nl = ibkr.netliq_usd()
            if nl < MIN_EQUITY:
                return (None, f"equity {nl:.0f} USD < {MIN_EQUITY:.0f} — esperar fondeo")
        if etf in STATE["positions"]:
            return (None, f"{etf}: posicion/bolsa ya abierta, no re-entrada")
        if time.time() - STATE["cooldown"].get(etf, 0) < COOLDOWN_S:
            return (None, f"{etf}: cooldown activo")
        if len(open_active()) >= MAX_OPEN:
            return (None, f"cap {MAX_OPEN} posiciones activas alcanzado")
        if len(bags()) >= BAG_MAX:
            return (None, f"cap {BAG_MAX} bolsas alcanzado")
        # ---- CIRCUIT BREAKERS (auditoria pro 2026-07-11) ----
        if live and DAY_LOSS_PCT > 0:
            dr = day_realized_usd()
            if dr <= -(DAY_LOSS_PCT / 100.0) * max(nl, MIN_EQUITY):
                return (None, f"HALT DIARIO: perdida realizada hoy {dr:+.0f} USD "
                              f">= {DAY_LOSS_PCT}% del equity — sin compras hasta mañana")
        bkt = BUCKET_OF.get(etf, "tech")
        actives_bkt = [p for e, p in STATE["positions"].items()
                       if not p.get("bag") and BUCKET_OF.get(e) == bkt]
        if len(actives_bkt) >= BUCKET_MAX:
            return (None, f"cap sector '{bkt}': ya {len(actives_bkt)} activas "
                          f"(no 4 semis apalancados en el mismo panico)")
        bags_bkt = [p for e, p in STATE["positions"].items()
                    if p.get("bag") and BUCKET_OF.get(e) == bkt]
        if len(bags_bkt) >= 2:
            return (None, f"sector '{bkt}' con {len(bags_bkt)} bolsas abiertas — "
                          f"no se promedia un regimen muriendo")
    return (venue, "ok")

def rth_now():
    lt = time.localtime()
    return lt.tm_wday < 5 and (570 <= lt.tm_hour * 60 + lt.tm_min < 959)

BATCH_SPENT = [0.0]   # USD gastados en el ciclo actual (reset en el loop)

def do_buy(ibkr, base, side, etf, sig_msg, stop_pct=None, kind="signal"):
    venue, why = preflight(ibkr, etf, True)
    if venue is None:
        log(f"SKIP BUY {etf} ({base} {side}): {why}"); return
    if not rth_now():
        log(f"SKIP BUY {etf}: fuera de RTH"); return
    paper = isinstance(venue, AlpacaPaper)
    if not paper:
        # cuenta = fuente de verdad: si el humano ya compro este ETF a mano,
        # NO se duplica (reconcile lo adopta en el proximo pase)
        rq = venue.broker_qty(etf)
        if rq and rq > 0:
            banner(f"{etf}: ya en cuenta (manual)", "no se duplica — reconcile la adopta")
            return
    px = ref_price(ibkr.ib if isinstance(venue, Ibkr) else None, etf)
    if not px:
        banner(f"{etf}: SIN PRECIO", "ni IBKR ni Alpaca fresco — trade abortado (jamas precio viejo)")
        return
    bid, ask = px
    # BALANCE FRESCO inmediatamente antes de ordenar (orden 2026-07-11: "always
    # check current balance before buying, avoid negative balance") + reserva
    # intocable. Multiples señales en rafaga: el executor es secuencial y cada
    # compra espera su fill, asi que el AvailableFunds del broker ya refleja la
    # compra anterior antes de calcular la siguiente.
    equity = MIN_EQUITY if paper else ibkr.netliq_usd()
    slot = max(50.0, equity / MAX_OPEN)
    avail = equity if paper else ibkr.avail_usd()
    # rafaga de señales: AvailableFunds del broker actualiza con latencia —
    # lo gastado en ESTE ciclo se descuenta a mano (adversarial review)
    budget = min(slot, max(0.0, avail - CASH_RESERVE - BATCH_SPENT[0]))
    qty = int(budget // ask)
    if qty < 1:
        today = f"{datetime.now():%Y-%m-%d}"
        if STATE.setdefault("nobudget", {}).get(etf) != today:
            STATE["nobudget"][etf] = today
            banner(f"{etf}: SIN PRESUPUESTO", f"slot {slot:.0f} ask {ask:.2f} avail {avail:.0f} — 0 shares")
        else:
            log(f"{etf}: sin presupuesto (repetido hoy, sin banner)")
        return
    # cap de apalancamiento BRUTO: sum(lev x notional) <= GROSS_CAP x NetLiq
    if not paper:
        gross = sum(LEV.get(e, 2) * p["qty"] * p["entry"] for e, p in STATE["positions"].items())
        if gross + LEV.get(etf, 2) * qty * ask > GROSS_CAP * max(equity, 1):
            log(f"SKIP BUY {etf}: gross leverage {gross:.0f}+{LEV.get(etf,2)*qty*ask:.0f} "
                f"> {GROSS_CAP}x{equity:.0f} — cap de exposicion bruta")
            return
    limit = ask * 1.001
    if paper:
        oid = venue.order(etf, "buy", qty, "limit", px=limit)
        filled, avg = qty, limit                      # paper: asumimos fill al limit
        banner(f"{etf}: PAPER BUY (fallback)", f"IBKR CAIDO — orden en Alpaca PAPER, NO ES REAL. {qty}x{limit:.2f}")
    else:
        filled, avg = venue.buy_limit(etf, qty, limit)
    if filled < 1:
        banner(f"{etf}: BUY sin fill", f"limit {limit:.2f} no lleno en 5min — cancelado"); return
    sp = stop_pct if stop_pct is not None else BEAR_STOP
    pos = {"base": base, "side": side, "qty": filled, "entry": avg,
           "t": time.time(), "venue": "alpaca_paper" if paper else "ibkr",
           "bag": False, "bag_oid": None, "stop_oid": None, "kind": kind,
           "deadline": time.time() + QUAKE_HOLD * 60 if kind == "quake" else None}
    if side == "bear":
        stop_px = avg * (1 - sp / 100)
        try:
            pos["stop_oid"] = (venue.order(etf, "sell", filled, "stop", stop=stop_px, tif="gtc")
                               if paper else venue.place_gtc_stop(etf, filled, stop_px))
        except Exception as e:
            log(f"{etf}: STOP FALLO ({e}) — cerrando bear YA (regla: bear jamas sin stop)")
            venue.order(etf, "sell", filled, "market") if paper else venue.sell_market(etf, filled)
            banner(f"{etf}: BEAR ABORTADO", "no se pudo colocar stop — posicion cerrada")
            return
    elif BULL_STOP > 0:
        # stop CATASTROFICO del bull en el broker (orden 2026-07-11 "stop loss
        # on price as well"), escalado por leverage real del ETF (TQQQ 3x
        # respira mas). La bolsa vive para caidas normales, el colapso se
        # corta. Si falla no se aborta el bull (reconcile reintenta en 5min).
        stop_px = avg * (1 - bull_stop_pct(etf) / 100)
        try:
            oca = f"B{etf}{int(time.time())}"
            if paper:
                pos["stop_oid"] = venue.order(etf, "sell", filled, "stop", stop=stop_px, tif="gtc")
            else:
                pos["stop_oid"] = venue.place_gtc_stop(etf, filled, stop_px, oca=oca)
                pos["oca"] = oca
        except Exception as e:
            log(f"{etf}: stop catastrofico fallo ({e}) — reconcile reintentara")
    BATCH_SPENT[0] += filled * avg
    STATE["positions"][etf] = pos
    STATE["cooldown"][etf] = time.time()
    STATE["history"].append({**pos, "event": "buy", "at": time.time()})
    save_state()
    ledger("buy", etf, base, side, filled, avg, getattr(venue, "last_fee", 0.0),
           note=kind + (" PAPER" if paper else ""))
    banner(f"{etf}: {'BEAR' if side=='bear' else 'BULL'} COMPRADO",
           f"{filled} @ {avg:.2f} ({base} {kind}) " + (f"stop {avg*(1-sp/100):.2f}" if side == "bear" else ""))

def do_sell(ibkr, base, kind):
    """kind: bull_exit (SELL NOW/SELL-STOP) | bear_exit (BUY CALL/SELL PUT/PUT-STOP)"""
    want = "bull" if kind == "bull_exit" else "bear"
    etf = BULL_OF.get(base) if want == "bull" else BEAR_OF.get(base)
    pos = STATE["positions"].get(etf or "")
    if not pos or pos["side"] != want or pos.get("bag"):
        return                                        # nada que hacer (o ya es bolsa con GTC)
    if not rth_now():
        # verificado contra docs IBKR (agente 2026-07-11): un MKT/DAY fuera de
        # horario queda en cola y llena en el OPEN siguiente = comer el gap en
        # un inverso apalancado. Fuera de RTH mandan las ordenes del broker
        # (stop GTC); esta salida se reintenta al abrir.
        log(f"SKIP SELL {etf}: fuera de RTH — el stop GTC protege; reintento en el open")
        return
    venue, why = preflight(ibkr, etf, False)
    if venue is None:
        log(f"SKIP SELL {etf}: {why}"); return
    # la venta se enruta al venue DUEÑO de la posicion (fix review 2026-07-11):
    # una posicion IBKR con TWS caido JAMAS se "vende" en paper — se espera
    # (los stops/GTC del broker siguen protegiendo) y se reintenta luego
    if pos["venue"] == "ibkr" and isinstance(venue, AlpacaPaper):
        log(f"SKIP SELL {etf}: TWS caido y la posicion es IBKR — broker protege, reintento")
        return
    if pos["venue"] == "alpaca_paper" and not isinstance(venue, AlpacaPaper):
        venue = AlpacaPaper()
    paper = isinstance(venue, AlpacaPaper)
    if not paper:
        # cuenta = fuente de verdad: el humano pudo vender/ajustar a mano
        rq = venue.broker_qty(etf)
        if rq == 0:
            banner(f"{etf}: ya cerrada en broker", "vendida manualmente o GTC/stop lleno — estado limpiado")
            ledger("closed_external", etf, base, pos["side"], pos["qty"], 0)
            STATE["history"].append({**pos, "event": "closed_external", "at": time.time()})
            del STATE["positions"][etf]; save_state(); return
        if rq is not None and rq < pos["qty"]:
            log(f"{etf}: broker tiene {rq} < estado {pos['qty']} — se vende lo real")
            pos["qty"] = rq
    px = ref_price(None if paper else ibkr.ib, etf)
    bid = px[0] if px else 0
    if want == "bull":
        floor = profit_floor(pos["entry"], pos["qty"])   # garantiza ganancia NETA de fees
        if bid >= floor:
            # el stop catastrofico se cancela CON CONFIRMACION antes de vender:
            # cancel async + venta inmediata = dos sells vivos = short posible
            if not paper and pos.get("stop_oid"):
                if not venue.cancel_confirmed(pos["stop_oid"], etf):
                    log(f"{etf}: cancel del stop NO confirmado — venta pospuesta "
                        f"(la proteccion del broker sigue viva, cero riesgo de oversell)")
                    return
                pos["stop_oid"] = None; save_state()
            if paper:
                venue.order(etf, "sell", pos["qty"], "limit", px=max(floor, bid * 0.999))
                filled, avg = pos["qty"], max(floor, bid * 0.999)
            else:
                # limit >= floor SIEMPRE: la regla "solo vender mas arriba" es dura
                filled, avg = venue.sell_limit_day(etf, pos["qty"], max(floor, bid * 0.999))
            if filled >= pos["qty"]:
                pnl = (avg - pos["entry"]) / pos["entry"] * 100
                banner(f"{etf}: VENDIDO +{pnl:.1f}%", f"{filled} @ {avg:.2f} (entry {pos['entry']:.2f})")
                ledger("sell", etf, base, "bull", filled, avg,
                       getattr(venue, "last_fee", 0.0), f"{pnl:+.2f}",
                       pnl_usd=(avg - pos["entry"]) * filled)
                STATE["history"].append({**pos, "event": "sell", "exit": avg, "at": time.time()})
                del STATE["positions"][etf]; save_state(); return
            if filled > 0:      # fill parcial: lo vendido se contabiliza, el resto va a bolsa
                STATE["history"].append({**pos, "event": "sell_partial", "qty": filled,
                                         "exit": avg, "at": time.time()})
                ledger("sell_partial", etf, base, "bull", filled, avg,
                       getattr(venue, "last_fee", 0.0),
                       f"{(avg - pos['entry']) / pos['entry'] * 100:+.2f}",
                       pnl_usd=(avg - pos["entry"]) * filled)
                pos["qty"] -= filled
        # no se vende por debajo: BOLSA = par OCA en el broker — GTC de
        # recuperacion en floor + stop catastrofico; una llena, la otra muere
        # sola (imposible oversell, sobrevive reinicios y muerte del Mac)
        try:
            if paper:
                pos["bag_oid"] = venue.order(etf, "sell", pos["qty"], "limit", px=floor, tif="gtc")
            else:
                if pos.get("stop_oid"):          # stop suelto del buy: fuera CON
                    if not venue.cancel_confirmed(pos["stop_oid"], etf):   # confirmacion
                        log(f"{etf}: cancel del stop viejo NO confirmado — bolsa pospuesta")
                        return
                    pos["stop_oid"] = None
                oca = f"B{etf}{int(time.time())}"
                new_gtc = venue.place_gtc_sell(etf, pos["qty"], floor, oca=oca)
                if BULL_STOP > 0:
                    try:
                        pos["stop_oid"] = venue.place_gtc_stop(
                            etf, pos["qty"], pos["entry"] * (1 - bull_stop_pct(etf) / 100), oca=oca)
                    except Exception as e2:
                        # segunda pata fallo: rollback de la primera — jamas
                        # dejar media proteccion fuera de un OCA coherente
                        venue.cancel_confirmed(new_gtc, etf)
                        raise RuntimeError(f"pata stop del OCA fallo: {e2}")
                pos["bag_oid"] = new_gtc
                pos["oca"] = oca
            pos["bag"] = True; save_state()
            ledger("bag", etf, base, "bull", pos["qty"], floor, note="GTC recuperacion")
            banner(f"{etf}: BOLSA", f"señal de venta bajo entry ({bid:.2f} < {floor:.2f}) — "
                                    f"aguantamos con GTC {floor:.2f} (sobrevive reinicios)")
        except Exception as e:
            log(f"{etf}: GTC bolsa fallo: {e} — reintenta reconcile")
    else:
        if pos.get("stop_oid") and not paper:
            if not venue.cancel_confirmed(pos["stop_oid"], etf):
                log(f"{etf}: cancel del stop bear NO confirmado — salida pospuesta "
                    f"(el stop sigue protegiendo); reintento en el proximo ciclo")
                return
            pos["stop_oid"] = None; save_state()
        filled, avg = ((pos["qty"], bid) if paper else venue.sell_limit_day(etf, pos["qty"], bid * 0.997 if bid else pos["entry"]))
        if paper: venue.order(etf, "sell", pos["qty"], "market")
        if not paper and filled < pos["qty"]:
            filled, avg = venue.sell_market(etf, pos["qty"] - filled)   # bear no se queda colgado
        pnl = (avg - pos["entry"]) / pos["entry"] * 100 if avg else 0
        banner(f"{etf}: BEAR CERRADO {pnl:+.1f}%", f"@ {avg:.2f} (entry {pos['entry']:.2f})")
        ledger("sell", etf, base, "bear", pos["qty"], avg,
               getattr(venue, "last_fee", 0.0), f"{pnl:+.2f}", note=pos.get("kind", ""),
               pnl_usd=(avg - pos["entry"]) * pos["qty"] if avg else 0.0)
        STATE["history"].append({**pos, "event": "sell", "exit": avg, "at": time.time()})
        del STATE["positions"][etf]; save_state()

def reconcile(ibkr):
    """Adopta posiciones/ordenes reales; re-coloca GTC de bolsas y stops de bears."""
    if not ibkr.connected(): return
    try:
        ibkr.ib.reqAllOpenOrders()      # GTC/stops de sesiones previas tambien
        ibkr.ib.sleep(1.5)
        allpos = ibkr.ib.positions(ACCOUNT)
        real = {p.contract.symbol: p for p in allpos
                if p.contract.symbol in ALL_ETFS and p.position > 0}
        # SHORT en nuestros ETFs = algo salio muy mal (o el humano shortea a
        # proposito): alarma, no se toca (cuenta = verdad, puede ser suyo)
        for p in allpos:
            if p.contract.symbol in ALL_ETFS and p.position < 0:
                banner(f"{p.contract.symbol}: SHORT DETECTADO",
                       f"{p.position} shares — el bot NO gestiona shorts, revisar YA")
        open_ids = {(tr.contract.symbol, tr.order.orderId) for tr in ibkr.ib.openTrades()}
        for sym, p in real.items():
            pos = STATE["positions"].get(sym)
            if pos and pos["entry"] > 0 and \
               abs(float(p.avgCost) - pos["entry"]) / pos["entry"] > 0.20:
                # corporate action (reverse split) o adopcion desfasada: el
                # avgCost del broker manda; floor/stops se recalculan del real
                log(f"reconcile: {sym} entry {pos['entry']:.2f} -> avgCost "
                    f"{float(p.avgCost):.2f} (re-baseline, proteccion recreada)")
                pos["entry"] = float(p.avgCost)
                pos["stop_oid"] = pos["bag_oid"] = None
            if pos and int(p.position) < pos["qty"]:
                # el humano vendio parte a mano: la proteccion debe cubrir lo REAL
                log(f"reconcile: {sym} broker {int(p.position)} < estado {pos['qty']} — qty ajustada")
                pos["qty"] = int(p.position)
                pos["stop_oid"] = pos["bag_oid"] = None   # fuerza recreacion del par abajo
            if not pos:
                side = "bear" if sym in BEAR_ETFS else "bull"
                pos = {"base": next((b for b, m in MAP.items() if sym in (m["bull"], m.get("bear"))), "?"),
                       "side": side, "qty": int(p.position), "entry": float(p.avgCost),
                       "t": time.time(), "venue": "ibkr", "bag": side == "bull",
                       "bag_oid": None, "stop_oid": None}
                STATE["positions"][sym] = pos
                log(f"reconcile: adoptada {sym} {pos['qty']}@{pos['entry']:.2f} ({side})")
            if pos["side"] == "bear" and (sym, pos.get("stop_oid")) not in open_ids:
                sp = quake_stop_pct(sym) if pos.get("kind") == "quake" else BEAR_STOP
                pos["stop_oid"] = ibkr.place_gtc_stop(sym, pos["qty"], pos["entry"] * (1 - sp / 100))
                log(f"reconcile: stop bear re-colocado {sym} (-{sp:.1f}%)")
            if pos["side"] == "bull" and pos.get("venue", "ibkr") == "ibkr":
                # proteccion bull = stop catastrofico (+ GTC recuperacion si es
                # bolsa) SIEMPRE presentes; si falta cualquiera se recrea el par
                # completo en un OCA fresco (mezclar ordenes de grupos viejos
                # dejaria huecos de oversell)
                need_stop = BULL_STOP > 0 and (sym, pos.get("stop_oid")) not in open_ids
                need_bag = pos.get("bag") and (sym, pos.get("bag_oid")) not in open_ids
                if need_stop or need_bag:
                    for oid in (pos.get("stop_oid"), pos.get("bag_oid")):
                        if oid and (sym, oid) in open_ids:
                            ibkr.cancel(oid)
                    oca = f"B{sym}{int(time.time())}"
                    if BULL_STOP > 0:
                        pos["stop_oid"] = ibkr.place_gtc_stop(
                            sym, pos["qty"], pos["entry"] * (1 - bull_stop_pct(sym) / 100), oca=oca)
                    if pos.get("bag"):
                        pos["bag_oid"] = ibkr.place_gtc_sell(
                            sym, pos["qty"], profit_floor(pos["entry"], pos["qty"]), oca=oca)
                    pos["oca"] = oca
                    log(f"reconcile: proteccion bull re-colocada {sym} "
                        f"(stop -{BULL_STOP}%{' + GTC bolsa' if pos.get('bag') else ''})")
        # PODA solo con la conexion ya sincronizada (adversarial review: un
        # positions() vacio recien conectado borraba posiciones reales del
        # estado y duplicaba stops al re-adoptar)
        if time.time() - ibkr.connect_time > 15:
            for sym in list(STATE["positions"]):
                pos = STATE["positions"][sym]
                if pos["venue"] == "ibkr" and sym not in real:
                    # el broker dice que ya no existe (GTC/stop se lleno estando
                    # muertos): precio real de la ejecucion de hoy si existe
                    exit_px = 0.0
                    try:
                        for f in ibkr.ib.reqExecutions():
                            if f.contract.symbol == sym and f.execution.side == "SLD":
                                exit_px = float(f.execution.avgPrice or f.execution.price)
                    except Exception:
                        pass
                    pnl_usd = (exit_px - pos["entry"]) * pos["qty"] if exit_px else 0.0
                    banner(f"{sym}: cerrada en broker",
                           f"GTC/stop se ejecuto ({exit_px:.2f}) — retirada del estado")
                    ledger("closed_serverside", sym, pos.get("base", "?"), pos["side"],
                           pos["qty"], exit_px, pnl_usd=pnl_usd,
                           note="fill estando executor caido" if exit_px else "precio no hallado")
                    STATE["history"].append({**pos, "event": "closed_serverside", "at": time.time()})
                    del STATE["positions"][sym]
        save_state()
    except Exception as e:
        log(f"reconcile error: {e}")

# ---------------- selftest (sin broker) ----------------
def selftest():
    lines = [
        ("2026-01-01 10:00:00 | WARMUP NVDA: BUY NOW | COMPRAR NVDA @ 100.00", None),
        ("2026-01-01 10:00:00 | NVDA: BUY NOW | COMPRAR NVDA @ 100.00 (shares o CALL)", ("NVDA", "BUY NOW")),
        ("2026-01-01 10:01:00 | NVDA TERREMOTO ALZA | CUSUM subiendo", ("NVDA", "QUAKE ALZA")),
        ("2026-01-01 10:02:00 | TSLA: BUY PUT | COMPRAR PUT TSLA @ 404.00", ("TSLA", "BUY PUT")),
        ("2026-01-01 10:03:00 | TSLA: PUT-STOP | VENDER PUT TSLA @ 410.00", ("TSLA", "PUT-STOP")),
        ("2026-01-01 10:03:30 | TSLA: BUY CALL | COMPRAR CALL TSLA @ 411.00", ("TSLA", "BUY CALL")),
        ("2026-01-01 10:04:00 | GLD TERREMOTO CAIDA | CUSUM: cayendo fuerte -1.2%", ("GLD", "QUAKE CAIDA")),
        ("2026-01-01 10:05:00 | GLD TERREMOTO ALZA | CUSUM: subiendo fuerte +1.2%", ("GLD", "QUAKE ALZA")),
        ("2026-01-01 10:06:00 | WARMUP GLD TERREMOTO CAIDA | CUSUM: cayendo", None),
    ]
    ok = True
    for raw, want in lines:
        parts = [p.strip() for p in raw.split(" | ", 2)]
        got = None
        if len(parts) == 3 and not parts[1].startswith("WARMUP"):
            m = RX_TITLE.match(parts[1])
            if m: got = (m.group(1), m.group(2))
            else:
                q = RX_QUAKE.match(parts[1])
                if q: got = (q.group(1), "QUAKE " + q.group(2))
        if got != want: ok = False; print(f"FAIL parse: {raw} -> {got} != {want}")
    for b in BASES:
        assert BULL_OF[b], b
    assert BEAR_OF.get("TSLA") == "TSLS" and "INTC" not in BEAR_OF
    # floor gana neto de fees SIN doblarlas: 3 shares @ $33 (~$100) — fee/lado
    # = max(0.35 tiered, 0.005*3sh)=0.35, cap 0.5% -> ~0.9% total -> floor 1.0-1.3%
    f = profit_floor(33.0, 3)
    assert 33.0 * 1.009 <= f <= 33.0 * 1.014, f"floor {f} fuera de rango fee-real"
    # notional grande converge al minimo BAG_MIN_GAIN
    f2 = profit_floor(80.0, 100)
    assert abs(f2 - cent_ceil(80.0 * (1 + BAG_MIN_GAIN / 100))) < 0.011
    # stops normalizados por leverage
    assert quake_stop_pct("SQQQ") == 4.5 and quake_stop_pct("TSLS") == 1.5
    assert bull_stop_pct("TQQQ") == 35.0 and bull_stop_pct("TSLL") == 25.0
    # buckets y breakers cargados
    assert BUCKET_OF["TQQQ"] == "tech" and BUCKET_OF["UGL"] == "commod"
    assert DAY_LOSS_PCT > 0 and GROSS_CAP > 0
    print("selftest:", "OK" if ok else "FAIL")
    return 0 if ok else 1

# ---------------- main ----------------
if "--selftest" in sys.argv:
    sys.exit(selftest())

log(f"fleet_executor arrancando: {len(BULL_OF)} bulls, {len(BEAR_OF)} bears, "
    f"armed={armed()}, min_equity={MIN_EQUITY} USD, cuenta {ACCOUNT}, "
    f"breakers: dia -{DAY_LOSS_PCT}% / sector {BUCKET_MAX} / bruto {GROSS_CAP}x")
try:
    db()   # tablas listas desde el arranque (registro de TODA operacion/señal)
except Exception as e:
    log(f"db init error: {e}")
ibkr = Ibkr()
reconcile(ibkr)
last_reconcile = time.time()
while True:
    try:
        BATCH_SPENT[0] = 0.0
        for base, action, sig_px, msg in new_log_lines():
            if base not in MAP: continue
            log(f"señal {base} {action} @ {sig_px} :: {msg[:80]}")
            db_signal(base, action, sig_px, msg)
            if action == "BUY NOW":
                do_buy(ibkr, base, "bull", BULL_OF[base], msg)
            elif action in ("SELL NOW", "SELL-STOP"):
                do_sell(ibkr, base, "bull_exit")
            elif action == "BUY PUT":
                etf = BEAR_OF.get(base)
                if not BEARS_ON:
                    log(f"{base}: BEARS regulares OFF (backtest 37% WR — gate WR-70); ETF_BEARS=1 activa")
                elif etf: do_buy(ibkr, base, "bear", etf, msg)
                else: log(f"{base}: sin bear ETF listado — put queda señal-solo")
            elif action in ("BUY CALL", "SELL PUT", "PUT-STOP"):
                do_sell(ibkr, base, "bear_exit")
            elif action == "QUAKE CAIDA":
                # BEAR por TERREMOTO: "only when sure and real fast when earthquake"
                etf = BEAR_OF.get(base)
                nbears = len([p for p in STATE["positions"].values()
                              if p["side"] == "bear" and not p.get("bag")])
                if not QUAKE_BEARS: log(f"{base}: quake-bears OFF (ETF_QUAKE_BEARS=0)")
                elif not etf: log(f"{base}: quake CAIDA sin bear ETF — señal-solo")
                elif BULL_OF.get(base) in STATE["positions"]:
                    log(f"{base}: bull/bolsa abierta — sin quake-bear (conflicto)")
                elif nbears >= MAX_BEARS:
                    log(f"{base}: cap {MAX_BEARS} bears alcanzado — quake ignorado")
                elif time.localtime().tm_hour * 60 + time.localtime().tm_min >= 920:
                    log(f"{base}: quake despues de 15:20 — sin entrada (EOD 15:50 lo sacaria ya)")
                else:
                    do_buy(ibkr, base, "bear", etf, msg,
                           stop_pct=quake_stop_pct(etf), kind="quake")
            elif action == "QUAKE ALZA":
                etf = BEAR_OF.get(base)
                if etf and STATE["positions"].get(etf, {}).get("kind") == "quake":
                    log(f"{base}: quake INVERSO — cerrando quake-bear ya")
                    do_sell(ibkr, base, "bear_exit")
        # exits programados de bears: time-stop del quake + EOD 15:50 SIEMPRE
        # (inverso apalancado JAMAS pasa la noche — decay + gap)
        lt = time.localtime(); mins = lt.tm_hour * 60 + lt.tm_min
        for sym in list(STATE["positions"]):
            p = STATE["positions"].get(sym)
            if not p or p["side"] != "bear" or p.get("bag"): continue
            timed_out = p.get("deadline") and time.time() > p["deadline"]
            eod = lt.tm_wday < 5 and mins >= 950 and mins < 960
            # red de seguridad (review 2026-07-11): si el executor estuvo caido
            # en la ventana EOD, un bear sin deadline quedaria vivo para siempre
            # — edad maxima 8h lo saca en la proxima sesion si o si
            stale = time.time() - p.get("t", 0) > 8 * 3600
            if timed_out or eod or stale:
                why = "time-stop" if timed_out else ("EOD 15:50" if eod else "edad>8h")
                log(f"{sym}: exit programado bear ({why})")
                do_sell(ibkr, p["base"], "bear_exit")
        if time.time() - last_reconcile > 300:
            reconcile(ibkr); last_reconcile = time.time()
        save_state()
        time.sleep(0.5)
    except KeyboardInterrupt:
        break
    except Exception as e:
        log(f"loop error: {e}")
        time.sleep(5)
