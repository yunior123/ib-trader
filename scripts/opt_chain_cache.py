#!/usr/bin/env python3
"""opt_chain_cache.py — cache de cadenas de opciones para el lector C++ opt_quick.

SEÑAL-SOLAMENTE / SOLO LECTURA (ley #0 Yunior 2026-07-16): `IB.connect(...,
readonly=True)`, `reqMarketDataType(1)` (realtime, jamas delayed), cero
ordenes de ningun tipo. Python permitido: ib_insync lo exige (regla #4).
ClientId 48 (rango 40-49; 83-99 ocupados por daemons).

Cada ~3 min durante 9:00-16:15 ET (reloj del Mac = ET) vuelca a
`data/opt_chain_<sym>.txt` la cadena ±6% ATM del vencimiento mas cercano +
el siguiente semanal, para los 17 de la flota + 4 miembros QQQ (MSFT/AVGO/
AMZN/META, banda ±4%) que alimentan el P/C de `./qqq_xray`. Escritura
atomica (tmp+rename).

FORMATO (contrato con scripts/opt_quick.cpp — NO desviarse):
  # opt_chain NVDA | epoch 1784298180 | 2026-07-17 10:03:00 | spot 208.35 | exps 20260717 20260724
  # strike right exp bid ask vol oi iv delta gamma    (n/d = -1)
  207.50 C 20260717 1.23 1.27 15234 8211 0.4310 0.5512 0.0410

Uso:  ./venv/bin/python scripts/opt_chain_cache.py          # daemon (keepalive)
      ./venv/bin/python scripts/opt_chain_cache.py --once   # 1 ciclo, ignora ventana (test manual)
"""
import datetime as dt
import math
import os
import shutil
import sys
import time

try:
    from ib_insync import IB, Option, Stock
except ImportError:
    from ib_async import IB, Option, Stock

HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "Documents/GitHub/ib-trader")
os.chdir(REPO)

# los 17 de la flota con opciones US (orden Yunior 2026-07-16 noche)
# + 4 miembros QQQ para el P/C de qqq_xray (2026-07-16 noche, 17->21): banda
#   recortada a ±4% en los nuevos para mantener el ciclo <180s.
FLEET = ["SMH", "TSM", "QQQ", "NVDA", "MU", "ASML", "INTC", "DRAM", "SKHY",
         "SPCX", "AMD", "TXN", "TSLA", "NOK", "AAPL", "GOOGL", "QCOM",
         "MSFT", "AVGO", "AMZN", "META", "LRCX", "SNDK", "WDC", "STX", "SPY"]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ib_mode import get_port                # fuente única: data/ib_mode.txt (paper/live)
PORT, CLIENT_ID = get_port(), 48           # 7497 paper / 7496 live; env IBKR_PORT gana
PCT_BAND = 0.06          # ±6% del spot
# los 4 miembros QQQ van recortados (±4%, 12 strikes, 4s de ticks) para que el
# ciclo de 21 syms siga <180s (medido 2026-07-16: ~157s con 17 syms a pleno)
NARROW = {"MSFT", "AVGO", "AMZN", "META"}
NARROW_BAND, NARROW_MAX_STRIKES, NARROW_SLEEP = 0.04, 12, 4
MAX_STRIKES = 20         # cap por vencimiento (2 exps x 20 strikes x 2 rights = 80 lineas TWS max)
CYCLE_S = 180            # cada 3 min
SLEEP_TICKS = 5          # s de espera para que lleguen ticks/greeks por simbolo
ONCE = "--once" in sys.argv


def log(msg):
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def in_window(t):
    if ONCE:
        return True
    if t.weekday() >= 5:
        return False
    hm = t.hour * 60 + t.minute
    return 9 * 60 <= hm <= 16 * 60 + 15          # 9:00-16:15 ET


def nz(v, d=-1.0):
    try:
        f = float(v)
        return f if f == f and not math.isinf(f) else d
    except (TypeError, ValueError):
        return d


def read_nbbo(sym):
    try:
        with open(f"data/nbbo_{sym.lower()}.txt") as f:
            ts, bid, ask = f.read().split()[:3]
        if time.time() - int(float(ts)) > 30:
            return None
        return (float(bid) + float(ask)) / 2
    except Exception:
        return None


class ChainCache:
    def __init__(self):
        self.ib = IB()
        self.stks = {}
        self.chains = {}         # sym -> (day, strikes[], expirations[])

    def connect(self):
        while not self.ib.isConnected():
            try:
                self.ib.connect("127.0.0.1", PORT, clientId=CLIENT_ID,
                                timeout=15, readonly=True)
                self.ib.reqMarketDataType(1)              # realtime SIEMPRE (ley #6)
                log(f"conectado TWS {PORT} clientId {CLIENT_ID} (readonly)")
            except Exception as e:
                log(f"TWS no disponible ({str(e)[:60]}) — reintento 60s")
                self.ib.disconnect()
                time.sleep(60)

    def chain_of(self, sym):
        today = dt.date.today().strftime("%Y%m%d")
        cached = self.chains.get(sym)
        if cached and cached[0] == today:
            return cached[1], cached[2]
        if sym not in self.stks:
            stk = Stock(sym, "SMART", "USD")
            self.ib.qualifyContracts(stk)
            self.stks[sym] = stk
        params = self.ib.reqSecDefOptParams(sym, "", "STK", self.stks[sym].conId)
        ch = next((c for c in params
                   if c.exchange == "SMART" and c.tradingClass == sym),
                  next((c for c in params if c.exchange == "SMART"), None))
        if not ch:
            raise RuntimeError("sin cadena SMART")
        exps = sorted(e for e in ch.expirations if e >= today)[:2]
        strikes = sorted(ch.strikes)
        self.chains[sym] = (today, strikes, exps)
        return strikes, exps

    def spot_of(self, sym):
        px = read_nbbo(sym)
        if px:
            return px
        tks = self.ib.reqTickers(self.stks[sym])
        if tks:
            t = tks[0]
            for v in (t.marketPrice(), t.last, t.close):
                if nz(v) > 0:
                    return float(v)
        return None

    def dump_sym(self, sym):
        strikes_all, exps = self.chain_of(sym)
        spot = self.spot_of(sym)
        if not spot or not exps:
            log(f"{sym}: sin spot/vencimientos — skip")
            return 0
        narrow = sym in NARROW
        band = NARROW_BAND if narrow else PCT_BAND
        max_ks = NARROW_MAX_STRIKES if narrow else MAX_STRIKES
        cons = []
        for exp in exps:
            ks = sorted((k for k in strikes_all
                         if abs(k - spot) / spot <= band),
                        key=lambda k: abs(k - spot))[:max_ks]
            for k in ks:
                for r in ("C", "P"):
                    cons.append(Option(sym, exp, k, r, "SMART",
                                       currency="USD", tradingClass=sym))
        if not cons:
            log(f"{sym}: 0 strikes en ±{band*100:.0f}% — skip")
            return 0
        cons = [c for c in self.ib.qualifyContracts(*cons) if c.conId]
        tks = [self.ib.reqMktData(c, "100,101,106", False, False) for c in cons]
        self.ib.sleep(NARROW_SLEEP if narrow else SLEEP_TICKS)
        rows = []
        for tk in tks:
            c = tk.contract
            oi = tk.callOpenInterest if c.right == "C" else tk.putOpenInterest
            g = tk.modelGreeks
            rows.append(f"{c.strike:.2f} {c.right} {c.lastTradeDateOrContractMonth} "
                        f"{nz(tk.bid):.2f} {nz(tk.ask):.2f} "
                        f"{nz(tk.volume, 0):.0f} {nz(oi, 0):.0f} "
                        f"{nz(g.impliedVol if g else None):.4f} "
                        f"{nz(g.delta if g else None):.4f} "
                        f"{nz(g.gamma if g else None):.4f}")
            self.ib.cancelMktData(c)
        now = dt.datetime.now()
        path = f"data/opt_chain_{sym.lower()}.txt"
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(f"# opt_chain {sym} | epoch {int(time.time())} | "
                    f"{now:%Y-%m-%d %H:%M:%S} | spot {spot:.2f} | "
                    f"exps {' '.join(exps)}\n")
            f.write("# strike right exp bid ask vol oi iv delta gamma\n")
            f.write("\n".join(rows) + "\n")
        os.replace(tmp, path)
        try:
            # historia para backtesting (orden Yunior 2026-07-22; densificado 5min 07-23):
            # 1 foto/5min/simbolo en data/history/YYYY-MM-DD/ (opt_chain_<sym>_HHMM.txt,
            # MM redondeado a 5) — suficiente para backtestear evolucion GEX/muros intradia.
            # Degradacion limpia (si falla, no rompe el cache).
            hdir = f"data/history/{now:%Y-%m-%d}"
            _bucket = (now.minute // 5) * 5
            hpath = f"{hdir}/opt_chain_{sym.lower()}_{now:%H}{_bucket:02d}.txt"
            if not os.path.exists(hpath):
                os.makedirs(hdir, exist_ok=True)
                shutil.copy2(path, hpath)
        except Exception:
            pass
        return len(rows)

    def run(self):
        log(f"opt_chain_cache ARRANCADO ({len(FLEET)} syms, ±{PCT_BAND*100:.0f}% ATM, "
            f"2 vencimientos, ciclo {CYCLE_S}s, ventana 9:00-16:15 ET)")
        while True:
            t = dt.datetime.now()
            if not in_window(t):
                if self.ib.isConnected():
                    self.ib.disconnect()
                    log("fuera de ventana — desconectado")
                time.sleep(60)
                continue
            self.connect()
            t0 = time.time()
            total = 0
            for sym in FLEET:
                try:
                    total += self.dump_sym(sym)
                except Exception as e:
                    log(f"{sym}: error {str(e)[:80]}")
                    if not self.ib.isConnected():
                        break
            log(f"ciclo completo: {total} contratos cacheados en {time.time()-t0:.0f}s")
            if ONCE:
                self.ib.disconnect()
                return
            wait = CYCLE_S - (time.time() - t0)
            if wait > 0:
                self.ib.sleep(wait)


if __name__ == "__main__":
    ChainCache().run()
