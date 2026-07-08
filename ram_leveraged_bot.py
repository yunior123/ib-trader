#!/usr/bin/env python3
"""
ram_leveraged_bot.py - Memory-sector long/short bot via leveraged ETFs
======================================================================
Watches the WHOLE DRAM/memory complex and profits BOTH directions without
ever shorting (TFSA-compatible):

  SIGNALS (constituents):  DRAM, MU (Micron), 005930.KS (Samsung),
                           000660.KS (SK Hynix)
  BULLISH execution:       buy the bull leveraged ETF (RAM)
  BEARISH execution:       buy the BEAR leveraged ETF (SOXS, 3x inverse semis)

Pattern: dual-agent SOXL/SOXS-style rotation (QuantConnect ETF rotation /
Composer RSI strategies) fused with our validated confirmed-reversal engine:
  * sector capitulation + reversal-up confirmation + quorum  -> BULL entry
  * sector euphoria     + reversal-down confirmation + quorum -> BEAR entry
  * quorum: >= 2 constituents corroborating the direction (breadth filter)
  * Korea trades overnight (Toronto): an overnight Samsung/SK Hynix panic
    ARMS the setup and the ETF trade executes at the US open — the 24/5
    window finally has something to do at 9:30.
  * one position at a time (bull XOR bear); adaptive profit-only exit on the
    ETF's own tape (target -> trail -> time-stop -> EOD flatten; hard floor
    = max(entry+1%, break-even+fees): NEVER sells below it)
  * catalysts: --catalysts fetches earnings dates + news for the complex
    (yfinance) and seeds known events (SK Hynix US ADR listing 2026-07-10).
    With --blackout, no NEW entries on binary-event days (exits stay live).

CAVEAT: SOXS is broad semiconductors (3x inverse SOX index), not pure
memory — it is the closest liquid inverse proxy; a pure memory bear ETF
does not exist. RAM's tape is thin (~8k 1m bars/30d): expect wider fills.
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

from day_trading_bot import (
    order_commission, play_sound,
    IB_AVAILABLE, IB, Stock, MarketOrder, LimitOrder, util,
    TORONTO, _bar_et, _in_rth,
    DipAccumulatorBot, Lot, DEFAULT_CONFIG,
    add_indicators, load_ohlcv_csv, floor_price,
    in_trading_window, seconds_until_window_opens, wait_for_tws,
    log_account_context, get_account_value, get_position,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ram_bot")

CONSTITUENTS = ["DRAM", "MU", "005930.KS", "000660.KS"]  # the memory complex
BULL_ETF = "RAM"
BEAR_ETF = "SOXS"

SECTOR_CONFIG = DEFAULT_CONFIG.copy()
SECTOR_CONFIG.update({
    "quorum": 2,                # constituents that must corroborate the direction
    "support_rsi_bull": 45.0,   # a constituent supports BULL if its RSI <= this
    "support_rsi_bear": 55.0,   # a constituent supports BEAR if its RSI >= this
    "staleness_hours": 12.0,    # how long a constituent's last state stays valid
    "rsi_overbought": 75.0,     # euphoria threshold (bear setups)
    "catalyst_blackout": False, # True: no NEW entries on catalyst days
    # Korea read-through: Samsung+Hynix trade while the US sleeps. If BOTH
    # closed their session strongly in the same direction, arm the matching
    # ETF for the next US open (the "tonight Korea -> tomorrow US" thesis).
    "readthrough_pct": 2.0,     # both .KS names beyond +/- this % -> arm BULL/BEAR
    # Burst mode: capture brief-but-strong intraday moves without waiting for
    # session close or full reversal patterns. Any constituent moving hard in
    # a short window arms the matching ETF immediately.
    "burst_enabled": False,  # probado 2x en 30d: -16.8% y -39.1% vs +34.5% sin el (persigue tops)
    "burst_pct": 3.0,           # % move within the window that triggers
    "burst_minutes": 20,        # lookback window for the move
    "burst_quorum": 2,          # constituents that must burst the SAME direction
    # 24/5 execution: entries 4:00-19:30 ET (pre/post via outsideRth limits) and
    # the IBKR Overnight session (IBEOS, 20:00-03:50 ET) for true night trading.
    "extended_hours": True,
    # VWAP regime filter: BULL only at/below session VWAP (buy value, not chase),
    # BEAR only at/above VWAP. Standard practice in day-trading repos.
    "vwap_filter": True,
    "db_log": True,             # every transaction -> trades.db (bot_trades table)
    "alloc_pct": 50.0,          # igual % de la cuenta por ticker/lado (fraccional)
    "fractional_shares": True,  # compras fraccionales por defecto
})

SEOUL_OFFSET = 9  # hours vs UTC (KRX session date grouping)

KNOWN_CATALYSTS = [
    # seeded manually; --catalysts refreshes/expands from yfinance
    {"date": "2026-07-10", "symbol": "000660.KS",
     "event": "SK Hynix US ADR listing (announced; binary liquidity/attention event)"},
]


# ===================== PER-CONSTITUENT SIGNAL TRACKER =====================
@dataclass
class SigState:
    rsi: float = 50.0
    ts: Optional[datetime] = None
    dip_bar_high: Optional[float] = None   # armed capitulation awaiting up-confirm
    dip_rsi: float = 50.0
    dip_ts: Optional[datetime] = None
    top_bar_low: Optional[float] = None    # armed euphoria awaiting down-confirm
    top_rsi: float = 50.0
    top_ts: Optional[datetime] = None


class Tracker:
    """Confirmed-reversal detection on one constituent's own bar stream."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.s = SigState()

    def _capitulation(self, row):
        c = self.cfg
        if pd.isna(row["bb_lower"]) or pd.isna(row["vol_ma"]):
            return False
        return bool(row["close"] <= row["bb_lower"] and row["rsi"] <= c["rsi_oversold"]
                    and row["vol_ma"] > 0 and row["volume"] >= row["vol_ma"] * c["volume_mult"])

    def _euphoria(self, row):
        c = self.cfg
        if pd.isna(row["bb_upper"]) or pd.isna(row["vol_ma"]):
            return False
        return bool(row["close"] >= row["bb_upper"] and row["rsi"] >= c["rsi_overbought"]
                    and row["vol_ma"] > 0 and row["volume"] >= row["vol_ma"] * c["volume_mult"])

    def update(self, row, ts) -> Optional[str]:
        """Returns 'BULL' / 'BEAR' when this constituent CONFIRMS a reversal."""
        s = self.s
        s.rsi = float(row["rsi"]) if not pd.isna(row["rsi"]) else s.rsi
        s.ts = ts
        window = self.cfg.get("reclaim_window_bars", 60)
        out = None
        if self._capitulation(row):
            s.dip_bar_high = float(row["high"]); s.dip_rsi = float(row["rsi"]); s.dip_ts = ts
        elif (s.dip_bar_high is not None and s.dip_ts is not None
              and (ts - s.dip_ts).total_seconds() <= window * 300  # ~window bars of slack
              and float(row["close"]) > s.dip_bar_high
              and float(row["close"]) > float(row["open"])
              and float(row["rsi"]) > s.dip_rsi):
            out = "BULL"; s.dip_bar_high = None
        if self._euphoria(row):
            s.top_bar_low = float(row["low"]); s.top_rsi = float(row["rsi"]); s.top_ts = ts
        elif (s.top_bar_low is not None and s.top_ts is not None
              and (ts - s.top_ts).total_seconds() <= window * 300
              and float(row["close"]) < s.top_bar_low
              and float(row["close"]) < float(row["open"])
              and float(row["rsi"]) < s.top_rsi):
            out = out or "BEAR"; s.top_bar_low = None
        return out


# ===================== SECTOR BOT =====================
class MemorySectorBot:
    """Quorum-gated sector signals; single position on bull OR bear ETF."""

    def __init__(self, cfg: dict, capital: float, catalysts=None):
        self.cfg = cfg
        self.trackers = {sym: Tracker(cfg) for sym in CONSTITUENTS}
        self.exec_bot = {}  # side -> DipAccumulatorBot-like lot mgmt via LeveragedPairBot logic
        self.pending_side: Optional[str] = None
        self.pending_ts: Optional[datetime] = None
        self.position_side: Optional[str] = None
        self.bot = DipAccumulatorBot(cfg, capital)   # reuse portfolio/exits engine
        self.bot._pending_buy = False
        self.catalyst_days = set()
        for c in (catalysts or []):
            try:
                self.catalyst_days.add(date.fromisoformat(c["date"]))
            except Exception:
                pass
        # Korea read-through session tracking
        self._ks_session = {}   # sym -> {"date": d, "open": px, "close": px}
        self._ks_closed = {}    # sym -> (session_date, pct_change)
        self._rt_consumed = set()
        # Burst mode: recent closes per constituent for fast-move detection
        self._recent = {sym: [] for sym in CONSTITUENTS}  # [(ts, close)]
        self._last_burst_ts = None
        self.db = None  # set by run_live/run_backtest when db_log enabled

    def _quorum(self, side: str, now) -> int:
        c = self.cfg
        n = 0
        for sym, tr in self.trackers.items():
            s = tr.s
            if s.ts is None or (now - s.ts).total_seconds() > c["staleness_hours"] * 3600:
                continue
            if side == "BULL" and s.rsi <= c["support_rsi_bull"]:
                n += 1
            elif side == "BEAR" and s.rsi >= c["support_rsi_bear"]:
                n += 1
        return n

    def _korea_readthrough(self, sym, row, ts):
        """Track KRX sessions; when BOTH Korean names close the same session
        beyond +/-readthrough_pct, arm the matching ETF for the next US open."""
        from datetime import timedelta as _td
        c = self.cfg
        kdate = (ts + _td(hours=SEOUL_OFFSET)).date()
        st = self._ks_session.get(sym)
        if st is None or st["date"] != kdate:
            if st is not None and st["open"] > 0:  # previous session just closed
                chg = (st["close"] / st["open"] - 1) * 100
                self._ks_closed[sym] = (st["date"], chg)
            self._ks_session[sym] = {"date": kdate, "open": float(row["open"]), "close": float(row["close"])}
        else:
            st["close"] = float(row["close"])
        # both names closed the SAME session in the same strong direction?
        a, b = self._ks_closed.get("005930.KS"), self._ks_closed.get("000660.KS")
        if a and b and a[0] == b[0] and a[0] not in self._rt_consumed:
            rt = c.get("readthrough_pct", 2.0)
            side = None
            if a[1] >= rt and b[1] >= rt:
                side = "BULL"
            elif a[1] <= -rt and b[1] <= -rt:
                side = "BEAR"
            if side and self.position_side is None and self.pending_side is None:
                self._rt_consumed.add(a[0])
                self.pending_side = side
                self.pending_ts = ts
                log.info(f"[{ts}] KOREA READ-THROUGH {side}: Samsung {a[1]:+.1f}% / Hynix {b[1]:+.1f}% "
                         f"(sesion {a[0]}) -> armado para el open de US")
                play_sound("momentum")
            elif side:
                self._rt_consumed.add(a[0])

    def _burst_check(self, sym, row, ts):
        """Brief-but-strong move on any constituent -> arm the matching ETF now."""
        from datetime import timedelta as _td
        c = self.cfg
        if not c.get("burst_enabled", False):
            return
        buf = self._recent[sym]
        buf.append((ts, float(row["close"])))
        cutoff = ts - _td(minutes=c.get("burst_minutes", 20))
        while buf and buf[0][0] < cutoff:
            buf.pop(0)
        if len(buf) < 3 or self.position_side is not None or self.pending_side is not None:
            return
        move = (buf[-1][1] / buf[0][1] - 1) * 100
        side = "BULL" if move >= c["burst_pct"] else ("BEAR" if move <= -c["burst_pct"] else None)
        if side:
            if not hasattr(self, "_sym_burst"):
                self._sym_burst = {}
            self._sym_burst[sym] = (side, ts, move)
            # quorum: N constituents bursting the SAME direction within the window
            agree = [
                (s, m) for s, (sd, t2, m) in self._sym_burst.items()
                if sd == side and (ts - t2).total_seconds() <= c.get("burst_minutes", 20) * 60
            ]
            if len(agree) < c.get("burst_quorum", 2):
                return
            if self.cfg.get("catalyst_blackout") and ts.astimezone(TORONTO).date() in self.catalyst_days:
                return
            if self._last_burst_ts and (ts - self._last_burst_ts).total_seconds() < 1800:
                return
            self._last_burst_ts = ts
            self.pending_side = side
            self.pending_ts = ts
            names = ", ".join(f"{s} {m:+.1f}%" for s, m in agree)
            log.info(f"[{ts}] BURST {side} quorum {len(agree)}: {names} -> armado")

    def on_signal_bar(self, sym: str, row, ts):
        if sym.endswith(".KS"):
            self._korea_readthrough(sym, row, ts)
        self._burst_check(sym, row, ts)
        confirm = self.trackers[sym].update(row, ts)
        if confirm is None or self.position_side is not None or self.pending_side is not None:
            return
        if self.cfg.get("catalyst_blackout") and ts.astimezone(TORONTO).date() in self.catalyst_days:
            log.info(f"[{ts}] {confirm} confirm from {sym} suppressed: catalyst blackout day")
            return
        if self.cfg.get("vwap_filter", False) and "vwap" in row and not pd.isna(row["vwap"]):
            px, vw = float(row["close"]), float(row["vwap"])
            if confirm == "BULL" and px > vw * 1.005:
                return  # no chases above fair value
            if confirm == "BEAR" and px < vw * 0.995:
                return
        q = self._quorum(confirm, ts)
        if q >= self.cfg["quorum"]:
            self.pending_side = confirm
            self.pending_ts = ts
            log.info(f"[{ts}] SECTOR {confirm} armed by {sym} (quorum {q}/{len(CONSTITUENTS)})")
            play_sound("momentum")

    def on_etf_bar(self, side: str, row, ts):
        """Called for each bar of BOTH ETFs; acts only on the relevant one."""
        c = self.cfg
        b = self.bot
        p = b.portfolio
        comm = c.get("commission_per_order", 0.0)

        # entry: pending side matches this ETF, bar strictly after arming,
        # inside the tradeable session (RTH, or 4:00-19:30 ET when extended)
        if c.get("extended_hours", False):
            hm = _bar_et(ts)
            session_ok = (4, 0) <= hm < (19, 30)
        else:
            session_ok = _in_rth(ts) and _bar_et(ts) < tuple(c.get("entry_cutoff", (15, 30)))
        if (self.pending_side == side and self.position_side is None
                and self.pending_ts is not None and ts > self.pending_ts
                and session_ok):
            price = float(row["open"])
            available = p.cash * c.get("alloc_pct", 100.0) / 100.0
            comm = order_commission(available, c)
            if price > 0 and available > comm:
                if c.get("fractional_shares", True):
                    qty = round((available - comm) / price, 4)
                else:
                    qty = float(int((available - comm) / price))
                cost = qty * price + comm
                if qty > 0 and cost <= p.cash + 1e-9:
                    b._bar_index += 1
                    lot = Lot(entry_price=price, qty=qty, entry_time=ts, peak_price=price,
                              limit_price=floor_price(price, qty, c), entry_bar=b._bar_index)
                    p.lots.append(lot)
                    p.cash -= cost
                    p.commissions += comm
                    p.buy_count += 1
                    self.position_side = side
                    log.info(f"[{ts}] BUY {side} ETF {qty:g} @ {price:.2f} (floor {lot.limit_price:.2f})")
                    play_sound("enter")
                    if getattr(self, "db", None):
                        self.db.trade(ts, side, "BUY", qty, price, comm, reason="entry")
            self.pending_side = None
            self.pending_ts = None

        # exits: only on the ETF we hold
        if self.position_side != side or not p.lots:
            return
        b._bar_index += 1
        still = []
        for lot in p.lots:
            filled = False
            floor_px = lot.limit_price
            bars_held = b._bar_index - lot.entry_bar
            target_px = lot.entry_price * (1 + c.get("profit_target_pct", 4.0) / 100)
            limit_now = max(target_px if bars_held < c.get("time_stop_bars", 390) else floor_px, floor_px)
            if lot.pending_exit:
                lot.pending_exit = False
                open_px = float(row["open"])
                if lot.entry_bar != b._bar_index and open_px >= floor_px:
                    p.cash += lot.qty * open_px - comm
                    p.commissions += comm
                    pnl = lot.qty * (open_px - lot.entry_price) - 2 * comm
                    p.realized_pnl += pnl
                    p.sell_count += 1
                    filled = True
                    log.info(f"[{ts}] SELL {side} (flat) @ {open_px:.2f} (net {pnl:+.2f})")
                    play_sound("exit")
                    if getattr(self, "db", None):
                        self.db.trade(ts, side, "SELL", lot.qty, open_px, comm, pnl, "flat")
            if not filled and lot.entry_bar != b._bar_index and float(row["high"]) >= limit_now:
                open_px = float(row["open"])
                fill = open_px if open_px > limit_now else limit_now
                p.cash += lot.qty * fill - comm
                p.commissions += comm
                pnl = lot.qty * (fill - lot.entry_price) - 2 * comm
                p.realized_pnl += pnl
                p.sell_count += 1
                filled = True
                log.info(f"[{ts}] SELL {side} (limit) @ {fill:.2f} (net {pnl:+.2f})")
                play_sound("exit")
                if getattr(self, "db", None):
                    self.db.trade(ts, side, "SELL", lot.qty, fill, comm, pnl, "limit")
            if not filled:
                lot.peak_price = max(lot.peak_price, float(row["high"]))
                close_px = float(row["close"])
                atr = float(row["atr"]) if not pd.isna(row["atr"]) else 0.0
                if lot.entry_bar != b._bar_index and close_px > floor_px:
                    trail_broken = atr > 0 and close_px < lot.peak_price - c.get("trail_atr_mult", 3.0) * atr
                    eod = c.get("eod_flatten", True) and _bar_et(ts) >= (15, 45) and _in_rth(ts)
                    if trail_broken or eod:
                        lot.pending_exit = True
                still.append(lot)
        p.lots = still
        if not p.lots:
            self.position_side = None

    def summary(self, last_prices: dict):
        p = self.bot.portfolio
        last = last_prices.get(self.position_side, 0.0) if self.position_side else 0.0
        unreal = sum((last - l.entry_price) * l.qty for l in p.lots)
        return {
            "cash": p.cash, "realized_pnl": p.realized_pnl, "unrealized": unreal,
            "total_equity": p.cash + sum(l.qty * last for l in p.lots),
            "buys": p.buy_count, "sells": p.sell_count, "commissions": p.commissions,
            "open_side": self.position_side, "open_lots": len(p.lots),
        }


# ===================== CATALYSTS =====================
def fetch_catalysts(save_path="data/catalysts_dram.json"):
    """Earnings dates + latest headlines for the memory complex (yfinance)."""
    import warnings; warnings.filterwarnings("ignore")
    import yfinance as yf
    out = list(KNOWN_CATALYSTS)
    for sym in CONSTITUENTS:
        try:
            t = yf.Ticker(sym)
            try:
                cal = t.calendar
                if cal is not None and hasattr(cal, "get") and cal.get("Earnings Date"):
                    for d in cal["Earnings Date"][:2]:
                        out.append({"date": str(d), "symbol": sym, "event": "earnings"})
            except Exception:
                pass
            try:
                for n in (t.news or [])[:5]:
                    content = n.get("content", n)
                    title = content.get("title", "")
                    when = content.get("pubDate", "") or content.get("providerPublishTime", "")
                    if title:
                        out.append({"date": str(when)[:10], "symbol": sym, "event": f"news: {title[:90]}"})
            except Exception:
                pass
        except Exception as e:
            log.warning("catalyst fetch failed for %s: %s", sym, e)
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(save_path, "w"), indent=1, default=str)
    log.info("Saved %d catalyst entries -> %s", len(out), save_path)
    for c in out:
        print(f"  {c['date']:<12} {c['symbol']:<10} {c['event']}")
    return out


# ===================== BACKTEST =====================
def run_backtest(cfg, capital, files_sig: dict, files_etf: dict, catalysts=None):
    """files_sig: {symbol: csv}; files_etf: {'BULL': csv, 'BEAR': csv}"""
    sig_frames = {s: add_indicators(load_ohlcv_csv(f), cfg) for s, f in files_sig.items()}
    etf_frames = {side: add_indicators(load_ohlcv_csv(f), cfg) for side, f in files_etf.items()}
    events = []
    for sym, df in sig_frames.items():
        for ts, row in df.iterrows():
            events.append((ts.to_pydatetime(), 0, "sig", sym, row))
    for side, df in etf_frames.items():
        for ts, row in df.iterrows():
            events.append((ts.to_pydatetime(), 1, "etf", side, row))
    events.sort(key=lambda e: (e[0], e[1]))
    bot = MemorySectorBot(cfg, capital, catalysts)
    if cfg.get("db_log"):
        from day_trading_bot import TradeLog
        bot.db = TradeLog(bot="ram_sector", mode="backtest")
    for ts, _, kind, key, row in events:
        if kind == "sig":
            bot.on_signal_bar(key, row, ts)
        else:
            bot.on_etf_bar(key, row, ts)
    last_prices = {side: float(df.iloc[-1]["close"]) for side, df in etf_frames.items()}
    s = bot.summary(last_prices)
    log.info("=== MEMORY SECTOR BOT BACKTEST ===")
    log.info(f"Trades: {s['buys']}B/{s['sells']}S | fees ${s['commissions']:.2f} | open: {s['open_side'] or 'ninguna'} ({s['open_lots']} lots)")
    log.info(f"Realized: ${s['realized_pnl']:+.2f} | unrealized: ${s['unrealized']:+.2f}")
    log.info(f"Total equity: ${s['total_equity']:.2f} ({(s['total_equity'] / capital - 1) * 100:+.2f}%)")
    return s


# ===================== LIVE =====================
def run_live(args, cfg, catalysts=None):
    """US legs (DRAM/MU + ETFs) via IBKR; Korean legs refreshed via yfinance
    (IBKR retail has no KRX data). Korean bars arm setups; ETF trades at RTH."""
    if not IB_AVAILABLE:
        log.error("ib_insync/ib_async required.")
        return
    import warnings; warnings.filterwarnings("ignore")
    import yfinance as yf
    if args.live:
        log.warning("!!! REAL MONEY (leveraged sector ETFs) - Type YES !!!")
        if input("> ").strip().upper() != "YES":
            return
    if args.wait_tws:
        wait_for_tws(args.host, args.port)
    ib = IB()
    account = args.account if args.live else ""
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=15,
               readonly=not args.live, account=account)
    log_account_context(ib, dry_run=not args.live)
    us_syms = {"DRAM": Stock("DRAM", "SMART", "USD"), "MU": Stock("MU", "SMART", "USD")}
    etfs = {"BULL": Stock(args.bull, "SMART", "USD"), "BEAR": Stock(args.bear, "SMART", "USD")}
    for ctr in list(us_syms.values()) + list(etfs.values()):
        ib.qualifyContracts(ctr)
    # IBKR Overnight session (IBEOS): separate routing for the 20:00-03:50 ET band
    night_etfs = {}
    for side, sym in (("BULL", args.bull), ("BEAR", args.bear)):
        try:
            nc = Stock(sym, "OVERNIGHT", "USD")
            ib.qualifyContracts(nc)
            night_etfs[side] = nc
        except Exception:
            log.warning("%s no disponible en sesion OVERNIGHT (IBEOS)", sym)

    def _band(now_hm):
        if (9, 30) <= now_hm < (16, 0):
            return "rth"
        if (4, 0) <= now_hm < (9, 30) or (16, 0) <= now_hm < (20, 0):
            return "ext"
        return "overnight"
    bot = MemorySectorBot(cfg, get_account_value(ib, account=account), catalysts)
    if cfg.get("db_log"):
        from day_trading_bot import TradeLog
        bot.db = TradeLog(bot="ram_sector", mode="live" if args.live else "paper")
    log.info("Sector bot live: bull=%s bear=%s cash=$%.2f | extended_hours=%s db_log=%s",
             args.bull, args.bear, bot.bot.portfolio.cash,
             cfg.get("extended_hours"), cfg.get("db_log"))
    seen = set()
    try:
        while True:
            if args.schedule and not in_trading_window():
                import time as _t
                _t.sleep(seconds_until_window_opens())
                continue
            # 1) Korean constituents via yfinance (overnight arming)
            for ksym in ("005930.KS", "000660.KS"):
                try:
                    kdf = yf.Ticker(ksym).history(period="2d", interval="5m")
                    if not kdf.empty:
                        kdf = kdf.reset_index()
                        kdf.columns = [str(c).lower() for c in kdf.columns]
                        kdf = kdf.rename(columns={"datetime": "date"}).set_index("date")
                        kdf = add_indicators(kdf.rename(columns=str.lower), cfg)
                        ts = kdf.index[-2]
                        key = (ksym, str(ts))
                        if key not in seen and len(kdf) >= 2:
                            seen.add(key)
                            bot.on_signal_bar(ksym, kdf.iloc[-2], ts.to_pydatetime())
                except Exception as e:
                    log.debug("KS fetch fail %s: %s", ksym, e)
            # 2) US constituents + ETFs via IBKR
            for sym, ctr in us_syms.items():
                bars = ib.reqHistoricalData(ctr, "", "2 D", args.bar_size, "TRADES", True, 1)
                if bars:
                    df = util.df(bars); df["date"] = pd.to_datetime(df["date"]); df.set_index("date", inplace=True)
                    df = add_indicators(df, cfg)
                    if len(df) >= 2:
                        ts = df.index[-2]; key = (sym, str(ts))
                        if key not in seen:
                            seen.add(key)
                            bot.on_signal_bar(sym, df.iloc[-2], ts.to_pydatetime())
            for side, ctr in etfs.items():
                bars = ib.reqHistoricalData(ctr, "", "2 D", args.bar_size, "TRADES", True, 1)
                if bars:
                    df = util.df(bars); df["date"] = pd.to_datetime(df["date"]); df.set_index("date", inplace=True)
                    df = add_indicators(df, cfg)
                    if len(df) >= 2:
                        ts = df.index[-2]; key = (side, str(ts))
                        if key not in seen:
                            seen.add(key)
                            # live order mirroring: pending -> real market buy; GTC exits
                            if args.live and bot.pending_side == side and bot.position_side is None:
                                from datetime import datetime as _dt
                                price = float(df.iloc[-2]["close"])
                                cash = get_account_value(ib, account=account)
                                available = cash * cfg.get("alloc_pct", 50.0) / 100.0 \
                                    - order_commission(cash, cfg)
                                qty = float(int(available // price))
                                if qty < 1 and cfg.get("fractional_shares", False):
                                    # IBKR fractional: needs the permission enabled and
                                    # min $1 order value; not available in IBEOS overnight
                                    fq = round(max(0.0, available) / price, 4)
                                    if fq * price >= 1.0:
                                        qty = fq
                                if qty > 0:
                                    band = _band(_bar_et(_dt.now(TORONTO)))
                                    if band == "overnight" and qty != int(qty):
                                        log.info("Fractional no disponible en sesion OVERNIGHT; espero sesion 4:00 ET")
                                        continue
                                    lp = round(price * 1.003, 2)  # marketable limit: capped slippage
                                    if band == "overnight" and side in night_etfs:
                                        order = LimitOrder("BUY", qty, lp, tif="DAY")
                                        target_ctr = night_etfs[side]
                                    else:
                                        order = LimitOrder("BUY", qty, lp, tif="DAY",
                                                           outsideRth=(band != "rth"))
                                        target_ctr = ctr
                                    trade = ib.placeOrder(target_ctr, order)
                                    ib.sleep(3)
                                    st = trade.orderStatus
                                    log.info("BUY %s x%d limit %.2f [%s] status=%s filled=%s avg=%s",
                                             ctr.symbol, qty, lp, band, st.status, st.filled, st.avgFillPrice)
                                    if bot.db:
                                        bot.db.trade(_dt.utcnow(), ctr.symbol, "BUY",
                                                     st.filled or qty, st.avgFillPrice or lp,
                                                     cfg.get("commission_per_order", 1.0),
                                                     reason=f"live-{band}-{st.status}")
                            shares, avg = get_position(ib, ctr.symbol, account=account)
                            if args.live and shares > 0 and avg > 0:
                                has_sell = any(t.contract.symbol == ctr.symbol and t.order.action == "SELL"
                                               and t.orderStatus.status in ("PreSubmitted", "Submitted")
                                               for t in ib.openTrades())
                                if not has_sell:
                                    from datetime import datetime as _dt
                                    lp = round(max(avg * (1 + cfg.get("profit_target_pct", 4.0) / 100),
                                                   floor_price(avg, shares, cfg)), 2)
                                    # GTC + outsideRth: the profit-only exit works pre/post too
                                    ib.placeOrder(ctr, LimitOrder("SELL", shares if shares != int(shares) else int(shares), lp,
                                                                  tif="GTC", outsideRth=True))
                                    log.info("GTC SELL %s %s @ %.2f (outsideRth)", shares, ctr.symbol, lp)
                                    if bot.db:
                                        bot.db.trade(_dt.utcnow(), ctr.symbol, "SELL-ORDER",
                                                     shares, lp, reason="gtc-exit-placed")
                            bot.on_etf_bar(side, df.iloc[-2], ts.to_pydatetime())
            if bot.db:
                from datetime import datetime as _dt
                pos_sym = (args.bull if bot.position_side == "BULL"
                           else args.bear if bot.position_side == "BEAR" else "")
                bot.db.snapshot(_dt.utcnow(), get_account_value(ib, account=account),
                                pos_sym, sum(l.qty for l in bot.bot.portfolio.lots))
            if args.once:
                log.info("One-shot sector check complete.")
                break
            ib.sleep(30)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        ib.disconnect()


# ===================== CLI =====================
def build_parser():
    p = argparse.ArgumentParser(description="Memory-sector long/short bot (bull ETF vs bear ETF)")
    p.add_argument("--mode", choices=["backtest", "trade", "catalysts"], default="backtest")
    p.add_argument("--bull", default=BULL_ETF)
    p.add_argument("--bear", default=BEAR_ETF)
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--quorum", type=int, default=SECTOR_CONFIG["quorum"])
    p.add_argument("--blackout", action="store_true", help="No new entries on catalyst days")
    p.add_argument("--fractional", action="store_true", default=True,
                   help="Fractional-share orders (default ON; needs IBKR fractional permission)")
    p.add_argument("--alloc-pct", type=float, default=50.0,
                   help="Igual %% de la cuenta por ticker/lado (default 50)")
    p.add_argument("--profit-target-pct", type=float, default=SECTOR_CONFIG["profit_target_pct"])
    p.add_argument("--floor-pct", type=float, default=SECTOR_CONFIG["floor_pct"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=10)
    p.add_argument("--account", default="U26942420")
    p.add_argument("--bar-size", default="5 mins")
    p.add_argument("--live", action="store_true")
    p.add_argument("--once", action="store_true")
    p.add_argument("--schedule", action="store_true")
    p.add_argument("--wait-tws", action="store_true")
    return p


def main():
    args = build_parser().parse_args()
    cfg = SECTOR_CONFIG.copy()
    cfg.update({"quorum": args.quorum, "catalyst_blackout": args.blackout,
                "fractional_shares": args.fractional, "alloc_pct": args.alloc_pct,
                "profit_target_pct": args.profit_target_pct, "floor_pct": args.floor_pct})
    cat_path = Path("data/catalysts_dram.json")
    catalysts = json.load(open(cat_path)) if cat_path.exists() else KNOWN_CATALYSTS
    if args.mode == "catalysts":
        fetch_catalysts()
        return
    if args.mode == "backtest":
        files_sig = {s: f"data/{s.lower().replace('.', '_')}_1m_30d.csv" for s in CONSTITUENTS}
        files_etf = {"BULL": f"data/{args.bull.lower()}_1m_30d.csv",
                     "BEAR": f"data/{args.bear.lower()}_1m_30d.csv"}
        missing = [f for f in list(files_sig.values()) + list(files_etf.values()) if not Path(f).exists()]
        if missing:
            raise SystemExit(f"Missing data files: {missing}")
        run_backtest(cfg, args.capital, files_sig, files_etf, catalysts)
    else:
        run_live(args, cfg, catalysts)


if __name__ == "__main__":
    main()
