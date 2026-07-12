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
(precedente: topgainer exec_trade.py); no esta en el camino de latencia de
ticks — las señales son eventos de bar de 1m.

Edge cases cubiertos: replay de log tras restart (offsets persistidos, arranque
en EOF), inode rotado, señales duplicadas (cooldown + posicion abierta), shares
enteras (API fraccional bloqueada), presupuesto vivo por slot, cap de abiertas,
bolsas no bloquean slots (el cash manda), fills parciales, stop imposible ->
cierre inmediato, reconcile de posiciones/ordenes huerfanas al arrancar y cada
10 min, TWS caido -> reconexion + fallback, precio sin subscripcion IBKR ->
cadena Alpaca quote/trade fresco o NO se opera (jamas precio viejo/delayed).
"""
import json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime

ROOT = "/Users/yuniorrodriguezosorio/Documents/GitHub/ib-trader"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from ib_insync import IB, Stock, LimitOrder, StopOrder, MarketOrder  # noqa

# ---------------- config (env-overridable) ----------------
def envf(k, d): v = os.getenv(k); return float(v) if v else d
MIN_EQUITY   = envf("ETF_MIN_EQUITY", 450.0)    # USD; debajo = no operar
MAX_OPEN     = int(envf("ETF_MAX_OPEN", 4))     # posiciones activas (bolsas no cuentan)
BAG_MAX      = int(envf("ETF_BAG_MAX", 6))      # bolsas max simultaneas
BAG_MIN_GAIN = envf("ETF_BAG_MIN_GAIN", 1.0)    # % sobre entry para vender bull (cubre 2x0.5% fee cap)
BEAR_STOP    = envf("ETF_BEAR_STOP", 5.0)       # % stop servidor en el bear ETF
COOLDOWN_S   = envf("ETF_COOLDOWN_S", 900)      # anti re-entrada por ETF
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

MAP = json.load(open("data/leveraged_map.json"))          # base -> {bull, bear}
BULL_OF = {b: m["bull"] for b, m in MAP.items()}
BEAR_OF = {b: m["bear"] for b, m in MAP.items() if m.get("bear")}
ALL_ETFS = set(BULL_OF.values()) | set(BEAR_OF.values())
BEAR_ETFS = set(BEAR_OF.values())
BASES = list(MAP.keys())

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
    tmp = STATE_FILE + ".tmp"
    json.dump(STATE, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE_FILE)

def armed():
    return os.path.exists(ARMED_FILE)

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
            tk = ib.reqMktData(c, "", True, False)   # snapshot ($0.01, capped)
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
        self.ib = IB(); self.last_try = 0
    def connected(self):
        if self.ib.isConnected(): return True
        if time.time() - self.last_try < 30: return False
        self.last_try = time.time()
        try:
            self.ib.connect(HOST, PORT, clientId=CID, timeout=15, account=ACCOUNT)
            self.ib.reqMarketDataType(1)             # REALTIME only, jamas delayed
            log(f"IBKR conectado (cuenta {ACCOUNT})")
            return True
        except Exception as e:
            log(f"IBKR sin conexion: {e}"); return False
    def netliq_usd(self):
        try:
            vals = {(v.tag, v.currency): float(v.value)
                    for v in self.ib.accountValues(ACCOUNT)
                    if v.tag in ("NetLiquidation", "ExchangeRate", "AvailableFunds")}
            nl_base = vals.get(("NetLiquidation", "CAD")) or vals.get(("NetLiquidation", "USD"))
            if ("NetLiquidation", "USD") in vals: return vals[("NetLiquidation", "USD")]
            fx = FX_FALLBACK
            return (nl_base or 0) / fx
        except Exception as e:
            log(f"netliq error: {e}"); return 0
    def avail_usd(self):
        try:
            for v in self.ib.accountValues(ACCOUNT):
                if v.tag == "AvailableFunds":
                    x = float(v.value)
                    return x if v.currency == "USD" else x / FX_FALLBACK
        except Exception: pass
        return 0
    def qualify(self, sym):
        c = Stock(sym, "SMART", "USD"); self.ib.qualifyContracts(c); return c
    def buy_limit(self, sym, qty, px):
        tr = self.ib.placeOrder(self.qualify(sym),
                                LimitOrder("BUY", qty, round(px, 2), tif="DAY",
                                           account=ACCOUNT, outsideRth=False))
        return self._wait_fill(tr, 300)
    def sell_limit_day(self, sym, qty, px):
        tr = self.ib.placeOrder(self.qualify(sym),
                                LimitOrder("SELL", qty, round(px, 2), tif="DAY", account=ACCOUNT))
        return self._wait_fill(tr, 120)
    def sell_market(self, sym, qty):
        tr = self.ib.placeOrder(self.qualify(sym), MarketOrder("SELL", qty, account=ACCOUNT))
        return self._wait_fill(tr, 120)
    def place_gtc_sell(self, sym, qty, px):       # bolsa bull: recuperacion
        tr = self.ib.placeOrder(self.qualify(sym),
                                LimitOrder("SELL", qty, round(px, 2), tif="GTC", account=ACCOUNT))
        return tr.order.orderId
    def place_gtc_stop(self, sym, qty, px):       # bear: stop servidor-side
        tr = self.ib.placeOrder(self.qualify(sym),
                                StopOrder("SELL", qty, round(px, 2), tif="GTC", account=ACCOUNT))
        return tr.order.orderId
    def cancel(self, order_id):
        for tr in self.ib.openTrades():
            if tr.order.orderId == order_id:
                self.ib.cancelOrder(tr.order)
    def _wait_fill(self, tr, timeout):
        end = time.time() + timeout
        while time.time() < end and not tr.isDone():
            self.ib.sleep(1)
        filled = tr.filled()
        avg = tr.orderStatus.avgFillPrice or 0
        if not tr.isDone():
            self.ib.cancelOrder(tr.order); self.ib.sleep(2)
            filled = tr.filled(); avg = tr.orderStatus.avgFillPrice or 0
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
# titulo "SYM: BUY NOW" / "SELL NOW" / "SELL-STOP" / "BUY PUT" / "SELL PUT" / "PUT-STOP"
RX_TITLE = re.compile(r"^([A-Z]+): (BUY NOW|SELL NOW|SELL-STOP|BUY PUT|SELL PUT|PUT-STOP)$")
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
            with open(path) as f:
                f.seek(rec["off"])
                chunk = f.read()
                rec["off"] = f.tell()
            for line in chunk.splitlines():
                parts = [p.strip() for p in line.split(" | ", 2)]
                if len(parts) != 3 or parts[1].startswith("WARMUP"): continue
                m = RX_TITLE.match(parts[1])
                if not m: continue      # terremoto/tendencia/etc: no se opera
                pm = RX_PRICE.search(parts[2])
                out.append((m.group(1), m.group(2), float(pm.group(1)) if pm else 0, parts[2]))
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
    return (venue, "ok")

def rth_now():
    lt = time.localtime()
    return lt.tm_wday < 5 and (570 <= lt.tm_hour * 60 + lt.tm_min < 959)

def do_buy(ibkr, base, side, etf, sig_msg):
    venue, why = preflight(ibkr, etf, True)
    if venue is None:
        log(f"SKIP BUY {etf} ({base} {side}): {why}"); return
    if not rth_now():
        log(f"SKIP BUY {etf}: fuera de RTH"); return
    px = ref_price(ibkr.ib if isinstance(venue, Ibkr) else None, etf)
    if not px:
        banner(f"{etf}: SIN PRECIO", "ni IBKR ni Alpaca fresco — trade abortado (jamas precio viejo)")
        return
    bid, ask = px
    paper = isinstance(venue, AlpacaPaper)
    equity = MIN_EQUITY if paper else ibkr.netliq_usd()
    slot = max(50.0, equity / MAX_OPEN)
    avail = equity if paper else ibkr.avail_usd()
    budget = min(slot, max(0, avail - 5))            # buffer fees/FX
    qty = int(budget // ask)
    if qty < 1:
        banner(f"{etf}: SIN PRESUPUESTO", f"slot {slot:.0f} ask {ask:.2f} avail {avail:.0f} — 0 shares")
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
    pos = {"base": base, "side": side, "qty": filled, "entry": avg,
           "t": time.time(), "venue": "alpaca_paper" if paper else "ibkr",
           "bag": False, "bag_oid": None, "stop_oid": None}
    if side == "bear":
        stop_px = avg * (1 - BEAR_STOP / 100)
        try:
            pos["stop_oid"] = (venue.order(etf, "sell", filled, "stop", stop=stop_px, tif="gtc")
                               if paper else venue.place_gtc_stop(etf, filled, stop_px))
        except Exception as e:
            log(f"{etf}: STOP FALLO ({e}) — cerrando bear YA (regla: bear jamas sin stop)")
            venue.order(etf, "sell", filled, "market") if paper else venue.sell_market(etf, filled)
            banner(f"{etf}: BEAR ABORTADO", "no se pudo colocar stop — posicion cerrada")
            return
    STATE["positions"][etf] = pos
    STATE["cooldown"][etf] = time.time()
    STATE["history"].append({**pos, "event": "buy", "at": time.time()})
    save_state()
    banner(f"{etf}: {'BEAR' if side=='bear' else 'BULL'} COMPRADO",
           f"{filled} @ {avg:.2f} ({base} señal) " + (f"stop {avg*(1-BEAR_STOP/100):.2f}" if side == "bear" else ""))

def do_sell(ibkr, base, kind):
    """kind: bull_exit (SELL NOW/SELL-STOP) | bear_exit (SELL PUT/PUT-STOP)"""
    want = "bull" if kind == "bull_exit" else "bear"
    etf = BULL_OF.get(base) if want == "bull" else BEAR_OF.get(base)
    pos = STATE["positions"].get(etf or "")
    if not pos or pos["side"] != want or pos.get("bag"):
        return                                        # nada que hacer (o ya es bolsa con GTC)
    venue, why = preflight(ibkr, etf, False)
    if venue is None:
        log(f"SKIP SELL {etf}: {why}"); return
    paper = isinstance(venue, AlpacaPaper)
    px = ref_price(None if paper else ibkr.ib, etf)
    bid = px[0] if px else 0
    if want == "bull":
        floor = pos["entry"] * (1 + BAG_MIN_GAIN / 100)
        if bid >= floor:
            if paper:
                venue.order(etf, "sell", pos["qty"], "limit", px=max(floor, bid * 0.999))
                filled, avg = pos["qty"], max(floor, bid * 0.999)
            else:
                # limit >= floor SIEMPRE: la regla "solo vender mas arriba" es dura
                filled, avg = venue.sell_limit_day(etf, pos["qty"], max(floor, bid * 0.999))
            if filled >= pos["qty"]:
                pnl = (avg - pos["entry"]) / pos["entry"] * 100
                banner(f"{etf}: VENDIDO +{pnl:.1f}%", f"{filled} @ {avg:.2f} (entry {pos['entry']:.2f})")
                STATE["history"].append({**pos, "event": "sell", "exit": avg, "at": time.time()})
                del STATE["positions"][etf]; save_state(); return
            if filled > 0:      # fill parcial: lo vendido se contabiliza, el resto va a bolsa
                STATE["history"].append({**pos, "event": "sell_partial", "qty": filled,
                                         "exit": avg, "at": time.time()})
                pos["qty"] -= filled
        # no se vende por debajo: BOLSA + GTC de recuperacion (regla Yunior)
        try:
            oid = (venue.order(etf, "sell", pos["qty"], "limit", px=floor, tif="gtc")
                   if paper else venue.place_gtc_sell(etf, pos["qty"], floor))
            pos["bag"] = True; pos["bag_oid"] = oid; save_state()
            banner(f"{etf}: BOLSA", f"señal de venta bajo entry ({bid:.2f} < {floor:.2f}) — "
                                    f"aguantamos con GTC {floor:.2f} (sobrevive reinicios)")
        except Exception as e:
            log(f"{etf}: GTC bolsa fallo: {e} — reintenta reconcile")
    else:
        if pos.get("stop_oid") and not paper:
            try: venue.cancel(pos["stop_oid"])
            except Exception: pass
        filled, avg = ((pos["qty"], bid) if paper else venue.sell_limit_day(etf, pos["qty"], bid * 0.997 if bid else pos["entry"]))
        if paper: venue.order(etf, "sell", pos["qty"], "market")
        if not paper and filled < pos["qty"]:
            filled, avg = venue.sell_market(etf, pos["qty"] - filled)   # bear no se queda colgado
        pnl = (avg - pos["entry"]) / pos["entry"] * 100 if avg else 0
        banner(f"{etf}: BEAR CERRADO {pnl:+.1f}%", f"@ {avg:.2f} (entry {pos['entry']:.2f})")
        STATE["history"].append({**pos, "event": "sell", "exit": avg, "at": time.time()})
        del STATE["positions"][etf]; save_state()

def reconcile(ibkr):
    """Adopta posiciones/ordenes reales; re-coloca GTC de bolsas y stops de bears."""
    if not ibkr.connected(): return
    try:
        ibkr.ib.reqAllOpenOrders()      # GTC/stops de sesiones previas tambien
        ibkr.ib.sleep(1.5)
        real = {p.contract.symbol: p for p in ibkr.ib.positions(ACCOUNT)
                if p.contract.symbol in ALL_ETFS and p.position > 0}
        open_ids = {tr.order.orderId for tr in ibkr.ib.openTrades()}
        for sym, p in real.items():
            pos = STATE["positions"].get(sym)
            if not pos:
                side = "bear" if sym in BEAR_ETFS else "bull"
                pos = {"base": next((b for b, m in MAP.items() if sym in (m["bull"], m.get("bear"))), "?"),
                       "side": side, "qty": int(p.position), "entry": float(p.avgCost),
                       "t": time.time(), "venue": "ibkr", "bag": side == "bull",
                       "bag_oid": None, "stop_oid": None}
                STATE["positions"][sym] = pos
                log(f"reconcile: adoptada {sym} {pos['qty']}@{pos['entry']:.2f} ({side})")
            if pos["side"] == "bear" and pos.get("stop_oid") not in open_ids:
                pos["stop_oid"] = ibkr.place_gtc_stop(sym, pos["qty"], pos["entry"] * (1 - BEAR_STOP / 100))
                log(f"reconcile: stop re-colocado {sym}")
            if pos["side"] == "bull" and pos.get("bag") and pos.get("bag_oid") not in open_ids:
                pos["bag_oid"] = ibkr.place_gtc_sell(sym, pos["qty"], pos["entry"] * (1 + BAG_MIN_GAIN / 100))
                log(f"reconcile: GTC bolsa re-colocada {sym}")
        for sym in list(STATE["positions"]):
            pos = STATE["positions"][sym]
            if pos["venue"] == "ibkr" and sym not in real:
                # el broker dice que ya no existe (GTC/stop se lleno estando muertos)
                banner(f"{sym}: cerrada en broker", "GTC/stop se ejecuto — posicion retirada del estado")
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
        ("2026-01-01 10:01:00 | NVDA TERREMOTO ALZA | CUSUM subiendo", None),
        ("2026-01-01 10:02:00 | TSLA: BUY PUT | COMPRAR PUT TSLA @ 404.00", ("TSLA", "BUY PUT")),
        ("2026-01-01 10:03:00 | TSLA: PUT-STOP | VENDER PUT TSLA @ 410.00", ("TSLA", "PUT-STOP")),
    ]
    ok = True
    for raw, want in lines:
        parts = [p.strip() for p in raw.split(" | ", 2)]
        got = None
        if len(parts) == 3 and not parts[1].startswith("WARMUP"):
            m = RX_TITLE.match(parts[1])
            if m: got = (m.group(1), m.group(2))
        if got != want: ok = False; print(f"FAIL parse: {raw} -> {got} != {want}")
    for b in BASES:
        assert BULL_OF[b], b
    assert BEAR_OF.get("TSLA") == "TSLS" and "INTC" not in BEAR_OF
    print("selftest:", "OK" if ok else "FAIL")
    return 0 if ok else 1

# ---------------- main ----------------
if "--selftest" in sys.argv:
    sys.exit(selftest())

log(f"fleet_executor arrancando: {len(BULL_OF)} bulls, {len(BEAR_OF)} bears, "
    f"armed={armed()}, min_equity={MIN_EQUITY} USD, cuenta {ACCOUNT}")
ibkr = Ibkr()
reconcile(ibkr)
last_reconcile = time.time()
while True:
    try:
        for base, action, sig_px, msg in new_log_lines():
            if base not in MAP: continue
            log(f"señal {base} {action} @ {sig_px} :: {msg[:80]}")
            if action == "BUY NOW":
                do_buy(ibkr, base, "bull", BULL_OF[base], msg)
            elif action in ("SELL NOW", "SELL-STOP"):
                do_sell(ibkr, base, "bull_exit")
            elif action == "BUY PUT":
                etf = BEAR_OF.get(base)
                if not BEARS_ON:
                    log(f"{base}: BEARS OFF (backtest 37% WR — gate WR-70); ETF_BEARS=1 activa")
                elif etf: do_buy(ibkr, base, "bear", etf, msg)
                else: log(f"{base}: sin bear ETF listado — put queda señal-solo")
            elif action in ("SELL PUT", "PUT-STOP"):
                do_sell(ibkr, base, "bear_exit")
        if time.time() - last_reconcile > 600:
            reconcile(ibkr); last_reconcile = time.time()
        save_state()
        time.sleep(2)
    except KeyboardInterrupt:
        break
    except Exception as e:
        log(f"loop error: {e}")
        time.sleep(5)
