#!/usr/bin/env python3
"""opt_chain_cache.py — cache de cadenas de opciones para el lector C++ opt_quick.

SEÑAL-SOLAMENTE / SOLO LECTURA (ley #0 Yunior 2026-07-16): `IB.connect(...,
readonly=True)`, `reqMarketDataType(1)` (realtime, jamas delayed), cero
ordenes de ningun tipo. Python permitido: ib_insync lo exige (regla #4).
ClientId 48 (rango 40-49; 83-99 ocupados por daemons).

Cada ~3 min durante 9:00-16:15 ET (reloj del Mac = ET) vuelca a
`data/opt_chain_<sym>.txt` la cadena ±15% ATM del vencimiento mas cercano +
el siguiente semanal, para los 17 de la flota + 4 miembros QQQ (MSFT/AVGO/
AMZN/META: ola ATM ±8%, ola lejana ±15%) que alimentan el P/C de
`./qqq_xray`. Escritura atomica (tmp+rename).

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
import re
import shutil
import sys
import time

try:
    from ib_insync import IB, Option, Stock
except ImportError:
    from ib_async import IB, Option, Stock

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # NUNCA hardcodear: el repo se movio a ~/ib-trader (TCC/launchd, 2026-07-25)
os.chdir(REPO)

# los 17 de la flota con opciones US (orden Yunior 2026-07-16 noche)
# + 4 miembros QQQ para el P/C de qqq_xray (2026-07-16 noche, 17->21): banda
#   recortada en los nuevos para mantener el ciclo <180s.
FLEET = ["SMH", "TSM", "QQQ", "NVDA", "MU", "ASML", "INTC", "DRAM", "SKHY",
         "SPCX", "AMD", "TXN", "TSLA", "NOK", "AAPL", "GOOGL", "QCOM",
         "MSFT", "AVGO", "AMZN", "META", "LRCX", "SNDK", "WDC", "STX", "SPY"]
CUSTOM_TICKERS = "data/options_alert_tickers.txt"


def symbols_to_cache():
    """Flota canónica + tickers pedidos al motor C++.

    El fichero custom solo amplía el adaptador de datos; no mete esos símbolos en fleet.txt ni
    en MANADA. Se relee cada ciclo para que `options_alert_engine XYZ CALL` funcione sin restart.
    """
    out = list(FLEET)
    try:
        with open(CUSTOM_TICKERS) as f:
            for raw in f.read().split():
                sym = raw.strip().upper()
                if re.fullmatch(r"[A-Z0-9](?:[A-Z0-9.-]{0,10}[A-Z0-9])?", sym) and sym not in out:
                    out.append(sym)
    except OSError:
        pass
    return out

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ib_mode import get_port                # fuente única: data/ib_mode.txt (paper/live)
PORT, CLIENT_ID = get_port(), 48           # 7497 paper / 7496 live; env IBKR_PORT gana
# banda ampliada 2026-07-26: MEDIDO contra las 35 cadenas completas (chain_full_<sym>.json)
# que ±6%/±4% truncaban ANTES del cap de MAX_STRIKES en 15/26 simbolos (NOK 2, QCOM 8,
# SKHY 9, NVDA/AMZN 10...) -- el request TWS no crece (sigue capado en MAX_STRIKES/
# NARROW_MAX_STRIKES, solo cambia CUALES strikes entran), asi que ampliar es gratis en
# lineas/ciclo. A ±15%/±8% los 26 llegan al cap salvo NOK (estructuralmente fino: ni
# el 60% de Polygon converge, ver poly_chain_archive.py band_trace).
PCT_BAND = 0.15          # ±15% del spot
NARROW = {"MSFT", "AVGO", "AMZN", "META"}
NARROW_BAND, NARROW_MAX_STRIKES, NARROW_SLEEP = 0.08, 12, 4
# los 4 NARROW no tenian ola lejana: su ancho efectivo se quedaba en ±2,5-5% (META 0.0247,
# MSFT 0.0296, AVGO 0.0354, AMZN 0.0507) < BAND_FLOOR 0.10, asi que chart_levels DESCARTABA
# siempre su cadena TWS (griegas 100%, 3 min) y caia a Polygon (15 min). La ola 2 se toma
# sobre la banda ANCHA: medido sobre las cadenas del 2026-07-31 da half-span 0.145-0.149.
# +40 lineas y +FAR_SLEEP por narrow (48->88 lineas, 4 syms = +160/ciclo, ~+16-25 s). El ciclo
# YA iba a 388-391 s con 26 syms (logs/opt_chain_cache.log 2026-07-31), no a CYCLE_S: si crece
# mas, bajar ESTO antes que tocar las olas de los no-narrow.
NARROW_FAR_MAX_STRIKES = 10
FAR_SLEEP = 4            # s de espera de la ola lejana (OI/vol pesan mas que griegas finas)
MAX_STRIKES = 20         # cap por vencimiento (2 exps x 20 strikes x 2 rights = 80 lineas TWS max)
MAX_LINES_PER_EXP = 2 * (MAX_STRIKES + MAX_STRIKES)          # no-narrow: near+far, 2 rights
NARROW_MAX_LINES_PER_EXP = 2 * (NARROW_MAX_STRIKES + NARROW_FAR_MAX_STRIKES)
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


def _sample_with_edges(pool, cap):
    """Muestreo lineal que SIEMPRE incluye LOS DOS BORDES. `pool[::stride]` arrancaba en el
    minimo y el ultimo paso no llegaba al maximo: QQQ 0DTE daba strike_span_pct 0.0979 contra
    BAND_FLOOR 0.10 y chart_levels descartaba la cadena IBKR por 0.21pp."""
    if not pool or cap <= 0:
        return []
    if len(pool) <= cap:
        return list(pool)
    if cap == 1:
        return [pool[-1]]
    idx = sorted({round(i * (len(pool) - 1) / (cap - 1)) for i in range(cap)})
    return [pool[i] for i in idx]


def line_budget(narrow, n_exps):
    """Lineas de market data que puede pedir UN simbolo por ciclo (near+far, 2 rights, n_exps).
    TWS da 100 concurrentes por defecto (maxTickerLimit): pasarse = TWS rechaza y la cadena sale
    coja. https://interactivebrokers.github.io/tws-api/market_data.html"""
    cap = NARROW_MAX_LINES_PER_EXP if narrow else MAX_LINES_PER_EXP
    return cap * max(1, int(n_exps))


def select_strikes(strikes_all, spot, band, max_ks, narrow,
                   far_band=None, far_max_ks=None):
    """(near, far) para UN vencimiento. Funcion pura: testeable sin TWS.

    near = los `max_ks` mas cercanos al ATM dentro de `band`.
    far  = el resto de la banda LEJANA muestreado con los dos bordes incluidos. Para los
    NARROW la banda lejana es la ancha (PCT_BAND) aunque la ola 1 sea estrecha.
    """
    if not strikes_all or not spot or spot <= 0:
        return [], []
    if far_band is None:
        far_band = PCT_BAND if narrow else band
    if far_max_ks is None:
        far_max_ks = NARROW_FAR_MAX_STRIKES if narrow else max_ks
    far_band = max(far_band, band)
    near_pool = sorted((k for k in set(strikes_all) if abs(k - spot) / spot <= band),
                       key=lambda k: (abs(k - spot), k))
    near = sorted(near_pool[:max_ks])
    far_pool = sorted({k for k in strikes_all
                       if abs(k - spot) / spot <= far_band} - set(near))
    return near, _sample_with_edges(far_pool, far_max_ks)


def header_lines(sym, spot, exps, rows, band, band_atm, max_ks, far_max_ks, narrow,
                 epoch=None, stamp=None):
    """Las 3 lineas '#' del fichero de cadena. Funcion pura: testeable sin TWS.

    CABECERA HONESTA (feature #5 chain-honesty, 2026-07-25): banda, tope de strikes y cuantas
    filas traen griegas/cotizaciones de verdad, para que un consumidor distinga "±6% con
    griegas" de "±4% con 0 de 80". Contrato en docs/CHAIN-HEADER.md, APPEND-ONLY.
    La linea 1 NO se toca: scripts/opt_quick.cpp la parsea posicionalmente y busca
    "epoch "/"spot "/"exps " por substring; las otras dos no contienen esos tokens.
    `band` es la banda EXTERIOR pedida porque gex_core.from_ibkr_cache la usa de FILTRO:
    declarar la del ATM tiraria la ola lejana de los narrow. `band_atm` = la densa.
    """
    epoch = time.time() if epoch is None else epoch
    stamp = stamp or f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}"
    n = len(rows)
    g_ok = sum(1 for r in rows if float(r.split()[7]) > 0)
    q_ok = sum(1 for r in rows if float(r.split()[3]) > 0 and float(r.split()[4]) > 0)
    ks = [float(r.split()[0]) for r in rows]
    # semiancho REAL escrito: es lo que chart_levels compara contra BAND_FLOOR (0.10)
    span_pct = ((max(ks) - min(ks)) / 2 / spot) if (ks and spot) else -1.0
    return [
        f"# opt_chain {sym} | epoch {int(epoch)} | {stamp} | spot {spot:.2f} | "
        f"exps {' '.join(exps)}",
        f"# fuente ibkr_tws | band {band:.4f} | max_strikes {max_ks} | "
        f"narrow {1 if narrow else 0} | vencimientos {len(exps)} | rows {n} | "
        f"greeks_ok_pct {(g_ok / n) if n else 0:.4f} | "
        f"bidask_ok_pct {(q_ok / n) if n else 0:.4f} | "
        f"band_atm {band_atm:.4f} | far_max_strikes {far_max_ks} | "
        f"span_pct {span_pct:.4f}",
        "# strike right exp bid ask vol oi iv delta gamma",
    ]


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
                self.ib.RequestTimeout = 15   # causa raiz 2026-07-28 (opt_whale_watch.py): sin esto, qualifyContracts cuelga para siempre si TWS no responde
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
        # 2 OLAS (2026-07-28): MAX_STRIKES pegados al ATM daban ±1.4% efectivo en SPY —
        # el lunes el put wall de MU estaba a -14% y el cache no lo veia. Ola 1 = ATM denso
        # (como siempre); ola 2 = resto de la banda muestreado a <=max_ks strikes (caza muros
        # lejanos). Olas secuenciales para no pasar el limite de lineas de market data de TWS.
        far_band = PCT_BAND if narrow else band
        far_cap = NARROW_FAR_MAX_STRIKES if narrow else max_ks
        near, far = select_strikes(strikes_all, spot, band, max_ks, narrow,
                                   far_band=far_band, far_max_ks=far_cap)
        cons, far_cons = [], []
        for exp in exps:
            for k in near:
                for r in ("C", "P"):
                    cons.append(Option(sym, exp, k, r, "SMART",
                                       currency="USD", tradingClass=sym))
            for k in far:
                for r in ("C", "P"):
                    far_cons.append(Option(sym, exp, k, r, "SMART",
                                           currency="USD", tradingClass=sym))
        if not cons and not far_cons:
            log(f"{sym}: 0 strikes en ±{far_band*100:.0f}% — skip")
            return 0
        budget = line_budget(narrow, len(exps))
        if len(cons) + len(far_cons) > budget:
            # fail-loud antes de pedir: TWS corta por encima de su maxTickerLimit y la cadena
            # saldria coja sin decirlo. Solo puede saltar si alguien sube los caps.
            log(f"{sym}: {len(cons) + len(far_cons)} lineas > presupuesto {budget} "
                f"({len(exps)} vencimientos) — skip")
            return 0
        rows = []
        for wave, wsleep in ((cons, NARROW_SLEEP if narrow else SLEEP_TICKS),
                             (far_cons, FAR_SLEEP)):
            if not wave:
                continue
            wave = [c for c in self.ib.qualifyContracts(*wave) if c and c.conId]
            tks = [self.ib.reqMktData(c, "100,101,106", False, False) for c in wave]
            self.ib.sleep(wsleep)
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
        head = header_lines(sym, spot, exps, rows, far_band, band, max_ks, far_cap,
                            narrow, epoch=time.time(), stamp=f"{now:%Y-%m-%d %H:%M:%S}")
        with open(tmp, "w") as f:
            f.write("\n".join(head) + "\n")
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
        log(f"opt_chain_cache ARRANCADO ({len(symbols_to_cache())} syms, ±{PCT_BAND*100:.0f}% ATM, "
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
            for sym in symbols_to_cache():
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
