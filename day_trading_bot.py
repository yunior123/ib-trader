#!/usr/bin/env python3
"""
dram_dip_bot.py - DRAM-specific dip accumulation bot for NYSE/NASDAQ via IBKR SMART routing
==========================================================================================
Trades DRAM (NASDAQ) using Bollinger + RSI + Volume dip strategy.
Never sells at a loss. Dynamic sizing with compounding from real account cash.
"""

import argparse
import logging
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple
from zoneinfo import ZoneInfo

TORONTO = ZoneInfo("America/Toronto")

import numpy as np
import pandas as pd

# IBKR API: prefer ib_async (maintained successor), fall back to ib_insync.
# Both expose the identical IB/Stock/Order/util API surface.
try:
    from ib_async import IB, Stock, MarketOrder, LimitOrder, util
    IB_AVAILABLE = True
except ImportError:
    try:
        from ib_insync import IB, Stock, MarketOrder, LimitOrder, util
        IB_AVAILABLE = True
    except ImportError:
        IB_AVAILABLE = False
        IB = None
        Stock = None
        MarketOrder = None
        LimitOrder = None
        util = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("dram_dip_bot")

# ===================== DRAM CONFIGURATION =====================
TICKER_SYMBOL = "DRAM"
TICKER_EXCHANGE = "SMART"      # IBKR SMART routing for best price across NYSE/NASDAQ/BATS/EDGX
TICKER_CURRENCY = "USD"
LIVE_CASH_ACCOUNT = "U26642820"
LIVE_TFSA_ACCOUNT = "U26942420"

# Backward-compatible aliases for older snippets/log parsers.
DRAM_SYMBOL = TICKER_SYMBOL
DRAM_EXCHANGE = TICKER_EXCHANGE
DRAM_CURRENCY = TICKER_CURRENCY

# Default strategy parameters (can be overridden via CLI)
# Single-lot dip-cycle mode (validated 2026-07-06 on 14d of real 1m data):
# buy panic dips, sell via GTC limit at entry+target (never below break-even
# incl. commissions), hold the bag until it recovers. Realized PnL can never
# be negative by construction.
DEFAULT_CONFIG = {
    "bb_period": 20,
    "bb_std": 3.0,          # only true panic breaks the 3-sigma band
    "rsi_period": 14,
    "rsi_oversold": 25.0,   # deep capitulation only (35 buys the first shallow dip = top)
    "volume_ma_period": 20,
    "volume_mult": 1.2,
    "ceiling_price": None,
    "min_profit_pct": 5.0,   # exit floor: never sell below entry+5% (nor break-even+fees)
    "trail_giveback_pct": None,
    "capital_per_lot": 100.0,
    "max_lots": 1,
    "max_capital_pct": 100.0,
    "buy_cooldown_bars": 0,
    "thesis_floor": None,
    "commission_per_order": 1.0,   # IBKR fixed US: $0.005/share, min $1.00/order
    "fractional_shares": False,    # whole shares like the live account
    "use_all_cash": True,          # redeploy the FULL balance every cycle (compounding)
    # --- Breakout modes (Dual Thrust / BOS entry + Chandelier/ATR exit) ---
    "entry_mode": "confirmed",     # "dip" = buy the capitulation bar; "reclaim" = wait for
                                   #   a close above the prior N-bar high after the dip (BOS);
                                   #   "momentum" = Donchian breakout (buy strength);
                                   #   "both" = dip OR momentum, whichever fires first
    "reclaim_lookback": 10,        # N-bar high that defines the reclaim breakout
    "reclaim_window_bars": 60,     # dip signal stays armed this many bars awaiting reclaim
    "momo_lookback": 20,           # Donchian: close > prior N-bar high = momentum breakout
    "momo_rsi_min": 60.0,          # momentum entries need RSI strength (not oversold)
    "exit_mode": "adaptive",       # "fixed" = GTC limit at entry+target;
                                   # "breakout" = ATR Chandelier trail, floor at entry+target;
                                   # "adaptive" = target limit + trail + time-stop to floor +
                                   #   EOD flatten. Floor = max(entry+floor_pct, break-even).
    "atr_period": 14,
    "trail_atr_mult": 3.0,         # exit when price retraces this many ATRs off the peak
    # --- Adaptive exit (sell fast, worst case floor, cash > bag) ---
    "profit_target_pct": 4.0,      # initial resting limit (captures explosive moves)
    "floor_pct": 1.0,              # hard floor above entry; NEVER sell below this (nor break-even)
    "time_stop_bars": 390,         # ~1 trading day on 1m bars; EOD flatten is the real deadline
    "eod_flatten": True,           # at 15:45 ET, exit at >= floor rather than hold overnight
    # --- Session discipline ---
    "rth_only": True,              # entries only 9:30-16:00 ET (no thin pre/post market)
    "entry_cutoff": (15, 30),      # no NEW buys after 15:30 ET (no time left to exit)
}


def _bar_et(ts) -> tuple:
    """(hour, minute) of a bar timestamp in America/Toronto."""
    return (ts.astimezone(TORONTO).hour, ts.astimezone(TORONTO).minute)


def _in_rth(ts) -> bool:
    hm = _bar_et(ts)
    return (9, 30) <= hm < (16, 0)


def floor_price(entry: float, qty: float, cfg: dict) -> float:
    """Adaptive-exit hard floor: entry + floor_pct, never below break-even incl. fees."""
    floor = entry * (1 + cfg.get("floor_pct", 1.0) / 100)
    comm = cfg.get("commission_per_order", 0.0)
    if qty > 0 and comm > 0:
        floor = max(floor, (entry + (2 * comm) / qty) * 1.001)
    return floor


def exit_limit_price(entry: float, qty: float, cfg: dict) -> float:
    """Sell-limit price: entry+target, but never below break-even incl. both
    commissions. Guarantees every realized cycle is net-positive."""
    target = entry * (1 + cfg["min_profit_pct"] / 100)
    comm = cfg.get("commission_per_order", 0.0)
    if qty > 0 and comm > 0:
        breakeven = entry + (2 * comm) / qty
        target = max(target, breakeven * 1.001)
    return target

# ===================== INDICATORS =====================
def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    return mid, mid + num_std * std, mid - num_std * std


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = df.copy()
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = compute_bollinger(
        df["close"], cfg["bb_period"], cfg["bb_std"]
    )
    df["rsi"] = compute_rsi(df["close"], cfg["rsi_period"])
    df["vol_ma"] = df["volume"].rolling(cfg["volume_ma_period"]).mean()
    df["atr"] = compute_atr(df, cfg.get("atr_period", 14))
    # Prior N-bar high: a close above it = bullish break of structure (reclaim)
    df["reclaim_high"] = df["high"].shift(1).rolling(cfg.get("reclaim_lookback", 10)).max()
    # Donchian upper (prior N bars): a close above it = momentum breakout (Turtle-style)
    df["momo_high"] = df["high"].shift(1).rolling(cfg.get("momo_lookback", 20)).max()
    return df


# ===================== DATA CLASSES =====================
@dataclass
class Lot:
    entry_price: float
    qty: float
    entry_time: datetime
    peak_price: float = 0.0
    limit_price: float = 0.0   # fixed mode: GTC sell-limit; breakout mode: break-even floor
    entry_bar: int = -1        # bar index of the fill (no same-bar exits)
    pending_exit: bool = False # breakout mode: trail broken, exit at next bar open (floor-checked)


@dataclass
class Portfolio:
    cash: float
    starting_cash: float
    lots: List[Lot] = field(default_factory=list)
    realized_pnl: float = 0.0
    last_buy_bar_index: int = -9999
    thesis_broken_alerted: bool = False
    commissions: float = 0.0
    buy_count: int = 0
    sell_count: int = 0

    def deployed_capital(self) -> float:
        return sum(l.entry_price * l.qty for l in self.lots)

    def total_equity(self, current_price: float) -> float:
        mark_to_market = sum(l.qty * current_price for l in self.lots)
        return self.cash + mark_to_market


# ===================== BOT CORE =====================
class DipAccumulatorBot:
    def __init__(self, cfg: dict, capital: float):
        self.cfg = cfg
        self.portfolio = Portfolio(cash=capital, starting_cash=capital)
        self._bar_index = 0
        self._pending_buy = False    # signal armed on bar close, filled next bar open
        self._dip_armed_bar = None   # reclaim/confirmed: bar index of last capitulation signal
        self._dip_high = 0.0         # confirmed mode: panic bar's high (confirmation threshold)
        self._dip_rsi = 50.0         # confirmed mode: panic bar's RSI (must turn up)

    def _buy_signal(self, row) -> bool:
        c = self.cfg
        if c["ceiling_price"] is not None and row["close"] >= c["ceiling_price"]:
            return False
        if pd.isna(row["bb_lower"]) or pd.isna(row["rsi"]) or pd.isna(row["vol_ma"]):
            return False
        near_lower_band = row["close"] <= row["bb_lower"]
        oversold = row["rsi"] <= c["rsi_oversold"]
        volume_confirmed = (
            row["vol_ma"] > 0 and row["volume"] >= row["vol_ma"] * c["volume_mult"]
        )
        return bool(near_lower_band and oversold and volume_confirmed)

    def _momentum_signal(self, row) -> bool:
        """Donchian/Turtle breakout: close above the prior N-bar high with RSI
        strength and volume confirmation — buy strength, not fear."""
        c = self.cfg
        if c["ceiling_price"] is not None and row["close"] >= c["ceiling_price"]:
            return False
        if pd.isna(row["momo_high"]) or pd.isna(row["rsi"]) or pd.isna(row["vol_ma"]):
            return False
        broke_out = float(row["close"]) > float(row["momo_high"])
        strong = float(row["rsi"]) >= c.get("momo_rsi_min", 60.0)
        volume_confirmed = (
            row["vol_ma"] > 0 and row["volume"] >= row["vol_ma"] * c["volume_mult"]
        )
        return bool(broke_out and strong and volume_confirmed)

    def _check_thesis_floor(self, row, ts) -> bool:
        c = self.cfg
        p = self.portfolio
        if c["thesis_floor"] is not None and row["close"] <= c["thesis_floor"]:
            if not p.thesis_broken_alerted:
                log.warning(
                    f"[{ts}] PRICE BROKE THESIS FLOOR ({c['thesis_floor']})! "
                    "New buys stopped. Manual decision required."
                )
                p.thesis_broken_alerted = True
            return True
        return False

    def _buy_capital(self) -> float:
        c = self.cfg
        p = self.portfolio
        if len(p.lots) >= c["max_lots"]:
            return 0.0
        if self._bar_index - p.last_buy_bar_index < c["buy_cooldown_bars"]:
            return 0.0
        if c.get("use_all_cash", False):
            # Full-compounding mode: every cycle redeploys the whole balance.
            return p.cash
        max_deployable = p.starting_cash * (c["max_capital_pct"] / 100)
        remaining_deployable = max_deployable - p.deployed_capital()
        return max(0.0, min(c["capital_per_lot"], remaining_deployable, p.cash))

    def _can_buy_more(self) -> bool:
        return self._buy_capital() > 0

    def step(self, row, ts: datetime):
        """Process one COMPLETED bar. Chronology inside the bar:
        1. fill last bar's armed entry at this bar's OPEN (no look-ahead)
        2. check GTC sell-limits against this bar's HIGH (intrabar fill)
        3. thesis-floor check on close (blocks new buys, never forces a sale)
        4. evaluate entry signal on this bar's close -> arm for next bar
        """
        c = self.cfg
        p = self.portfolio
        self._bar_index += 1
        comm = c.get("commission_per_order", 0.0)

        # --- 1) Fill pending entry at this bar's open ---
        if self._pending_buy:
            self._pending_buy = False
            price = float(row["open"])
            available = self._buy_capital()
            # RTH discipline: never fill outside 9:30-16:00 ET (cash > thin fills)
            if c.get("rth_only", False) and not _in_rth(ts):
                price = 0.0
            if price > 0 and available > comm:
                if c.get("fractional_shares", False):
                    qty = (available - comm) / price
                else:
                    qty = float(int((available - comm) / price))
                cost = qty * price + comm
                if qty > 0 and cost <= p.cash + 1e-9:
                    if c.get("exit_mode") == "adaptive":
                        lp = floor_price(price, qty, c)   # hard floor (entry+1% / break-even)
                    else:
                        lp = exit_limit_price(price, qty, c)
                    lot = Lot(
                        entry_price=price, qty=qty, entry_time=ts, peak_price=price,
                        limit_price=lp, entry_bar=self._bar_index,
                    )
                    p.lots.append(lot)
                    p.cash -= cost
                    p.commissions += comm
                    p.buy_count += 1
                    p.last_buy_bar_index = self._bar_index
                    log.info(f"[{ts}] BUY {qty:g} @ {price:.2f} (GTC sell-limit {lot.limit_price:.2f})")

        # --- 2) Exits ---
        still_open = []
        exit_mode = c.get("exit_mode", "fixed")
        for lot in p.lots:
            filled = False
            if exit_mode == "adaptive" and c["trail_giveback_pct"] is None:
                # Sell fast, never below floor, prefer cash over bags:
                #   stage 1: resting limit at entry+target (catches explosive moves)
                #   stage 2: after time_stop_bars, limit decays to the floor (out fast)
                #   trail:   3xATR retrace off peak -> out at next open if >= floor
                #   EOD:     15:45 ET flatten at >= floor rather than hold overnight
                floor_px = lot.limit_price
                bars_held = self._bar_index - lot.entry_bar
                target_px = lot.entry_price * (1 + c.get("profit_target_pct", 4.0) / 100)
                limit_now = target_px if bars_held < c.get("time_stop_bars", 120) else floor_px
                limit_now = max(limit_now, floor_px)

                # 2a) pending exit (trail/EOD) fills at this bar's open, floor-checked
                if lot.pending_exit:
                    lot.pending_exit = False
                    open_px = float(row["open"])
                    if lot.entry_bar != self._bar_index and open_px >= floor_px:
                        p.cash += lot.qty * open_px - comm
                        p.commissions += comm
                        pnl = lot.qty * (open_px - lot.entry_price) - 2 * comm
                        p.realized_pnl += pnl
                        p.sell_count += 1
                        filled = True
                        log.info(f"[{ts}] SELL (flat) {lot.qty:g} @ {open_px:.2f} (net {pnl:+.2f})")
                # 2b) resting limit touched intrabar
                if not filled and lot.entry_bar != self._bar_index and float(row["high"]) >= limit_now:
                    open_px = float(row["open"])
                    fill = open_px if open_px > limit_now else limit_now
                    p.cash += lot.qty * fill - comm
                    p.commissions += comm
                    pnl = lot.qty * (fill - lot.entry_price) - 2 * comm
                    p.realized_pnl += pnl
                    p.sell_count += 1
                    filled = True
                    log.info(f"[{ts}] SELL (limit) {lot.qty:g} @ {fill:.2f} (net {pnl:+.2f})")
                if not filled:
                    lot.peak_price = max(lot.peak_price, float(row["high"]))
                    close_px = float(row["close"])
                    atr = float(row["atr"]) if not pd.isna(row["atr"]) else 0.0
                    if lot.entry_bar != self._bar_index and close_px > floor_px:
                        trail_broken = (
                            atr > 0 and close_px < lot.peak_price - c.get("trail_atr_mult", 3.0) * atr
                        )
                        eod = c.get("eod_flatten", False) and _bar_et(ts) >= (15, 45) and _in_rth(ts)
                        if trail_broken or eod:
                            lot.pending_exit = True
                    still_open.append(lot)
                continue
            if exit_mode == "breakout" and c["trail_giveback_pct"] is None:
                floor_px = lot.limit_price  # break-even + fees; never sell below this
                # 2a) pending trailing exit fills at THIS bar's open, floor enforced
                if lot.pending_exit:
                    lot.pending_exit = False
                    open_px = float(row["open"])
                    if lot.entry_bar != self._bar_index and open_px >= floor_px:
                        p.cash += lot.qty * open_px - comm
                        p.commissions += comm
                        pnl = lot.qty * (open_px - lot.entry_price) - 2 * comm
                        p.realized_pnl += pnl
                        p.sell_count += 1
                        filled = True
                        log.info(f"[{ts}] SELL (trail) {lot.qty:g} @ {open_px:.2f} (net {pnl:+.2f})")
                if not filled:
                    # 2b) update peak, then arm Chandelier exit on close:
                    #     price retraced trail_atr_mult ATRs off the peak AND is
                    #     still above the break-even floor -> exit next bar open.
                    lot.peak_price = max(lot.peak_price, float(row["high"]))
                    atr = float(row["atr"]) if not pd.isna(row["atr"]) else 0.0
                    if lot.entry_bar != self._bar_index and atr > 0:
                        trail = lot.peak_price - c.get("trail_atr_mult", 2.0) * atr
                        close_px = float(row["close"])
                        if close_px < trail and close_px > floor_px:
                            lot.pending_exit = True
                    still_open.append(lot)
                continue
            lot.peak_price = max(lot.peak_price, float(row["high"]))
            if c["trail_giveback_pct"] is None:
                # GTC limit: fills any bar whose high reaches it, at limit or better.
                # Never fills below limit => realized PnL is net-positive by construction.
                if lot.entry_bar != self._bar_index and float(row["high"]) >= lot.limit_price:
                    open_px = float(row["open"])
                    fill = open_px if open_px > lot.limit_price else lot.limit_price
                    p.cash += lot.qty * fill - comm
                    p.commissions += comm
                    pnl = lot.qty * (fill - lot.entry_price) - 2 * comm
                    p.realized_pnl += pnl
                    p.sell_count += 1
                    filled = True
                    log.info(f"[{ts}] SELL {lot.qty:g} @ {fill:.2f} (net {pnl:+.2f})")
            else:
                # Legacy close-based trailing exit (still never below profit target)
                gain_pct = (row["close"] - lot.entry_price) / lot.entry_price * 100
                giveback = (lot.peak_price - row["close"]) / lot.peak_price * 100
                if gain_pct >= c["min_profit_pct"] and giveback >= c["trail_giveback_pct"]:
                    p.cash += lot.qty * row["close"] - comm
                    p.commissions += comm
                    p.realized_pnl += lot.qty * (row["close"] - lot.entry_price) - 2 * comm
                    p.sell_count += 1
                    filled = True
            if not filled:
                still_open.append(lot)
        p.lots = still_open

        # --- 3) Thesis floor (blocks new buys only) ---
        thesis_broken = self._check_thesis_floor(row, ts)

        # --- 4) Arm entry for next bar's open (RTH + cutoff discipline) ---
        session_ok = True
        if c.get("rth_only", False):
            session_ok = _in_rth(ts) and _bar_et(ts) < tuple(c.get("entry_cutoff", (15, 30)))
        if not thesis_broken and self._can_buy_more() and session_ok:
            mode = c.get("entry_mode", "dip")
            if mode == "confirmed":
                # Capitulation arms the setup; buy ONLY when the next bar confirms
                # the reversal: green close above the panic bar's high with RSI
                # turning up (hammer + confirmation). Cash until proof.
                if self._buy_signal(row):
                    self._dip_armed_bar = self._bar_index
                    self._dip_high = float(row["high"])
                    self._dip_rsi = float(row["rsi"])
                elif (
                    self._dip_armed_bar is not None
                    and self._bar_index - self._dip_armed_bar <= c.get("reclaim_window_bars", 60)
                    and float(row["close"]) > self._dip_high
                    and float(row["close"]) > float(row["open"])
                    and float(row["rsi"]) > self._dip_rsi
                ):
                    self._pending_buy = True
                    self._dip_armed_bar = None
            if mode in ("momentum", "both") and self._momentum_signal(row):
                self._pending_buy = True
            if mode == "both" and self._buy_signal(row):
                self._pending_buy = True
            if mode == "reclaim":
                # Two-stage: capitulation arms the dip; a close above the prior
                # N-bar high (bullish break of structure) confirms the rebound.
                if self._buy_signal(row):
                    self._dip_armed_bar = self._bar_index
                if (
                    self._dip_armed_bar is not None
                    and self._bar_index > self._dip_armed_bar
                    and self._bar_index - self._dip_armed_bar <= c.get("reclaim_window_bars", 60)
                    and not pd.isna(row["reclaim_high"])
                    and float(row["close"]) > float(row["reclaim_high"])
                ):
                    self._pending_buy = True
                    self._dip_armed_bar = None
            elif mode == "dip" and self._buy_signal(row):
                self._pending_buy = True

    def summary(self, last_price: float):
        p = self.portfolio
        unrealized = sum((last_price - l.entry_price) * l.qty for l in p.lots)
        return {
            "open_lots": len(p.lots),
            "cash": p.cash,
            "realized_pnl": p.realized_pnl,
            "unrealized_pnl": unrealized,
            "total_equity": p.total_equity(last_price),
            "buys": p.buy_count,
            "sells": p.sell_count,
            "commissions": p.commissions,
        }


# ===================== SCHEDULE / TWS AVAILABILITY =====================
def in_trading_window(now=None) -> bool:
    """24/5 window: Sunday 20:00 Toronto -> Friday 20:00 Toronto."""
    now = now or datetime.now(TORONTO)
    wd, hm = now.weekday(), (now.hour, now.minute)  # Mon=0..Sun=6
    if wd <= 3:                      # Mon-Thu: always inside
        return True
    if wd == 4:                      # Friday: until 20:00
        return hm < (20, 0)
    if wd == 6:                      # Sunday: from 20:00
        return hm >= (20, 0)
    return False                     # Saturday


def seconds_until_window_opens(now=None) -> float:
    now = now or datetime.now(TORONTO)
    probe = now
    while not in_trading_window(probe):
        probe = (probe + timedelta(minutes=15)).replace(second=0, microsecond=0)
    return max(60.0, (probe - now).total_seconds())


def tws_port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """Cheap socket probe: is TWS/IB Gateway listening?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_tws(host: str, port: int, retry_seconds: int = 60) -> None:
    """Block until the TWS/Gateway API port accepts connections."""
    while not tws_port_open(host, port):
        log.warning(
            "TWS/IB Gateway not reachable at %s:%s - retrying in %ss "
            "(start TWS and enable API in Global Configuration > API > Settings)",
            host, port, retry_seconds,
        )
        time.sleep(retry_seconds)


# ===================== IBKR HELPERS (LIVE MODE) =====================
def get_account_value(ib, tag="TotalCashValue", account: str = "") -> float:
    try:
        summary = ib.accountSummary()
        for item in summary:
            if item.tag == tag and (not account or item.account == account):
                return float(item.value)
        return 0.0
    except Exception:
        return 0.0


def get_position(ib, symbol: str, account: str = "") -> Tuple[float, float]:
    try:
        for pos in ib.positions():
            if pos.contract.symbol == symbol and (not account or pos.account == account):
                return float(pos.position), float(pos.avgCost)
        return 0.0, 0.0
    except Exception:
        return 0.0, 0.0


def log_account_context(ib, dry_run: bool):
    try:
        accounts = ib.managedAccounts()
    except Exception:
        accounts = []
    if accounts:
        log.info("Managed accounts visible: %s", ", ".join(accounts))
    if dry_run and accounts and not any(account.startswith("DU") for account in accounts):
        log.warning(
            "No DU* paper account detected. Continuing read-only/dry-run only; "
            "do not use --live unless this is intentional."
        )


# ===================== BACKTEST (DRY RUN) =====================
def run_backtest(df: pd.DataFrame, cfg: dict, starting_cash: float):
    df = add_indicators(df, cfg)
    bot = DipAccumulatorBot(cfg, starting_cash)

    for ts, row in df.iterrows():
        bot.step(row, ts.to_pydatetime())

    last_price = df.iloc[-1]["close"]
    s = bot.summary(last_price)
    sessions = len(pd.Series(df.index.date).unique())
    log.info("=== BACKTEST SUMMARY ===")
    log.info(f"Final price: ${last_price:.2f} | sessions: {sessions}")
    log.info(f"Trades: {s['buys']} buys / {s['sells']} sells ({(s['buys'] + s['sells']) / max(sessions, 1):.1f}/day) | commissions: ${s['commissions']:.2f}")
    log.info(f"Open lots: {s['open_lots']}")
    log.info(f"Cash: ${s['cash']:.2f}")
    log.info(f"Realized PnL (net of fees): ${s['realized_pnl']:.2f}")
    log.info(f"Unrealized PnL: ${s['unrealized_pnl']:.2f}")
    log.info(f"Total equity: ${s['total_equity']:.2f}")
    log.info(f"Return: {(s['total_equity'] / starting_cash - 1) * 100:.2f}%")
    return s


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"{path} is missing required columns: {sorted(missing)}")
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df.set_index("date", inplace=True)
    return df


# ===================== LIVE / PAPER TRADING =====================
def run_live_or_paper(args, cfg: dict):
    if not IB_AVAILABLE:
        log.error("ib_insync not installed. Run: pip install ib_insync")
        return

    if args.live:
        if args.account != LIVE_TFSA_ACCOUNT:
            raise RuntimeError(
                f"Live trading is restricted to TFSA account {LIVE_TFSA_ACCOUNT}; "
                f"refusing account {args.account}."
            )
        log.warning("!!! REAL MONEY MODE - Type YES to confirm !!!")
        if input("> ").strip().upper() != "YES":
            log.info("Cancelled.")
            return

    # Wait for TWS instead of dying: lets launchd start the bot at boot and
    # have it sit patiently until TWS/Gateway is up (or come back after a restart).
    if args.wait_tws:
        wait_for_tws(args.host, args.port)

    ib = IB()
    account = args.account if args.live else ""
    try:
        ib.connect(
            args.host,
            args.port,
            clientId=args.client_id,
            timeout=15,
            readonly=not args.live,
            account=account,
        )
    except ConnectionRefusedError:
        log.error(
            "Could not connect to IBKR at %s:%s. For paper trading, enable API "
            "access in TWS paper and use port 7497, or IB Gateway paper port 4002.",
            args.host,
            args.port,
        )
        return
    log_account_context(ib, dry_run=not args.live)
    contract = Stock(TICKER_SYMBOL, TICKER_EXCHANGE, TICKER_CURRENCY)
    ib.qualifyContracts(contract)

    current_cash = get_account_value(ib, account=account)
    bot = DipAccumulatorBot(cfg, current_cash)
    log.info(f"Connected. Starting cash: ${current_cash:,.2f}")

    # Restart recovery: if IBKR already holds shares, seed a synthetic lot so
    # the breakout trail has a peak/floor to work from (otherwise a restarted
    # bot would never exit an existing position in breakout mode).
    boot_shares, boot_avg = get_position(ib, TICKER_SYMBOL, account=account)
    if boot_shares > 0 and boot_avg > 0 and not bot.portfolio.lots:
        bot.portfolio.lots.append(
            Lot(entry_price=boot_avg, qty=boot_shares,
                entry_time=datetime.utcnow(), peak_price=boot_avg,
                limit_price=exit_limit_price(boot_avg, boot_shares, cfg))
        )
        log.info("Recovered existing position: %s shares @ $%.2f", boot_shares, boot_avg)

    last_bar_time = None
    try:
        while True:
            # 24/5 schedule: Sunday 20:00 Toronto -> Friday 20:00 Toronto.
            if args.schedule and not in_trading_window():
                wait = seconds_until_window_opens()
                log.info(
                    "Outside Sun 20:00 -> Fri 20:00 Toronto window; sleeping %.0f min "
                    "until it reopens.", wait / 60,
                )
                time.sleep(wait)
                continue

            # Reconnect guard: TWS restarts / network blips must not kill the bot.
            if not ib.isConnected():
                log.warning("Lost IBKR connection; waiting for TWS...")
                if args.wait_tws:
                    wait_for_tws(args.host, args.port)
                else:
                    ib.sleep(30)
                try:
                    ib.connect(
                        args.host, args.port, clientId=args.client_id,
                        timeout=15, readonly=not args.live, account=account,
                    )
                    ib.qualifyContracts(contract)
                    log.info("Reconnected to IBKR.")
                except Exception as exc:
                    log.error("Reconnect failed: %s", exc)
                    continue

            current_cash = get_account_value(ib, account=account)
            current_shares, avg_cost = get_position(ib, TICKER_SYMBOL, account=account)

            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="5 D",
                barSizeSetting=args.bar_size,  # live candle: --bar-size ("5 mins", "15 mins", ...)
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
            if not bars:
                ib.sleep(30)
                continue

            df = util.df(bars)
            if df is None or df.empty:
                ib.sleep(30)
                continue

            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            df = add_indicators(df, cfg)

            latest_ts = df.index[-1]
            if latest_ts != last_bar_time and len(df) >= 2:
                # The newest bar may still be forming: act on the last COMPLETED bar.
                row = df.iloc[-2]
                signal_ts = df.index[-2]
                price = row["close"]

                log.info(
                    f"[{signal_ts}] Cash: ${current_cash:,.2f} | "
                    f"Pos: {current_shares} @ ${avg_cost:.2f} | Price: ${price:.2f}"
                )

                if args.live:
                    comm = cfg.get("commission_per_order", 0.0)

                    # Entry: bot.step() on the previous bar armed _pending_buy
                    # (handles both dip and reclaim/BOS modes identically to sim)
                    if (
                        bot._pending_buy
                        and current_shares == 0
                        and len(bot.portfolio.lots) < cfg["max_lots"]
                        and (cfg["thesis_floor"] is None or price > cfg["thesis_floor"])
                    ):
                        # All-cash mode: deploy ~98% of cash (2% buffer covers fee +
                        # market movement between signal bar and market-order fill;
                        # TFSA is a cash account, an over-budget order gets rejected).
                        if cfg.get("use_all_cash", False):
                            available = current_cash * 0.98 - comm
                        else:
                            available = min(cfg["capital_per_lot"], current_cash * 0.95) - comm
                        qty = int(available // price)
                        if qty >= 1:
                            ib.placeOrder(contract, MarketOrder("BUY", qty))
                            log.info(f"BUY REAL {qty} {TICKER_SYMBOL} @ ~${price:.2f}")
                            bot.portfolio.lots.append(
                                Lot(entry_price=price, qty=qty,
                                    entry_time=signal_ts.to_pydatetime(),
                                    limit_price=exit_limit_price(price, qty, cfg))
                            )
                            bot.portfolio.last_buy_bar_index = bot._bar_index
                        else:
                            log.info(
                                "Skip buy: cash $%.2f cannot cover 1 share @ $%.2f + $%.2f fee",
                                current_cash, price, comm,
                            )

                    # Exit: profit-only, floor = break-even incl. fees at IBKR
                    if current_shares > 0 and avg_cost > 0:
                        has_open_sell = any(
                            t.contract.symbol == TICKER_SYMBOL
                            and t.order.action == "SELL"
                            and t.orderStatus.status in ("PreSubmitted", "Submitted")
                            for t in ib.openTrades()
                        )
                        floor_px = exit_limit_price(avg_cost, current_shares, cfg)
                        if cfg.get("exit_mode", "fixed") == "breakout":
                            # Chandelier trail off the peak; sell with a marketable
                            # LIMIT capped at >= floor so a fill below break-even
                            # is impossible even on slippage/gaps.
                            lots = bot.portfolio.lots
                            atr = float(row["atr"]) if not pd.isna(row["atr"]) else 0.0
                            if not has_open_sell and lots and atr > 0:
                                trail = lots[0].peak_price - cfg.get("trail_atr_mult", 2.0) * atr
                                if price < trail and price > floor_px:
                                    lp = round(max(floor_px, price * 0.995), 2)
                                    ib.placeOrder(
                                        contract,
                                        LimitOrder("SELL", int(current_shares), lp, tif="GTC"),
                                    )
                                    log.info(
                                        "Trail broken: GTC LIMIT SELL %d @ >=$%.2f (floor $%.2f)",
                                        int(current_shares), lp, floor_px,
                                    )
                        elif not has_open_sell:
                            # Fixed mode: resting GTC limit at entry+target, lives at
                            # the broker, survives bot restarts/crashes.
                            lp = round(floor_px, 2)
                            ib.placeOrder(
                                contract,
                                LimitOrder("SELL", int(current_shares), lp, tif="GTC"),
                            )
                            log.info(
                                "Placed GTC LIMIT SELL %d @ $%.2f (profit-only exit)",
                                int(current_shares), lp,
                            )

                bot.step(row, signal_ts.to_pydatetime())
                last_bar_time = latest_ts
                if args.once:
                    log.info("One-shot paper/dry-run check complete.")
                    break

            ib.sleep(25)

    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
    finally:
        ib.disconnect()


# ===================== CLI =====================
def build_arg_parser():
    p = argparse.ArgumentParser(description="DRAM Dip Accumulator Bot (SMART routing)")
    p.add_argument("--mode", choices=["backtest", "trade"], default="trade")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7497)
    p.add_argument("--client-id", type=int, default=7)
    p.add_argument("--account", default=LIVE_TFSA_ACCOUNT, help="Live account; live mode is TFSA-only")
    p.add_argument("--live", action="store_true", help="Send real orders (default: paper/dry-run)")
    p.add_argument("--capital", type=float, default=100.0, help="Starting capital for backtest")
    p.add_argument("--capital-per-lot", type=float, default=100.0)
    p.add_argument("--max-lots", type=int, default=1)
    p.add_argument("--min-profit-pct", type=float, default=DEFAULT_CONFIG["min_profit_pct"])
    p.add_argument("--thesis-floor", type=float, default=None)
    p.add_argument("--ceiling", type=float, default=None)
    p.add_argument("--bb-period", type=int, default=20)
    p.add_argument("--bb-std", type=float, default=DEFAULT_CONFIG["bb_std"])
    p.add_argument("--rsi-oversold", type=float, default=DEFAULT_CONFIG["rsi_oversold"])
    p.add_argument("--volume-mult", type=float, default=DEFAULT_CONFIG["volume_mult"])
    p.add_argument("--commission", type=float, default=1.0, help="Commission per order (USD)")
    p.add_argument("--entry-mode", choices=["dip", "reclaim", "confirmed", "momentum", "both"],
                   default=DEFAULT_CONFIG["entry_mode"],
                   help="dip = buy fear; reclaim = dip + BOS confirm; momentum = Donchian "
                        "breakout (buy strength); both = dip OR momentum")
    p.add_argument("--momo-lookback", type=int, default=DEFAULT_CONFIG["momo_lookback"])
    p.add_argument("--momo-rsi-min", type=float, default=DEFAULT_CONFIG["momo_rsi_min"])
    p.add_argument("--exit-mode", choices=["fixed", "breakout"], default=DEFAULT_CONFIG["exit_mode"],
                   help="fixed = GTC limit at entry+target; breakout = ATR trail, break-even floor")
    p.add_argument("--trail-atr-mult", type=float, default=DEFAULT_CONFIG["trail_atr_mult"])
    p.add_argument("--duration", default="30 D", help="Backtest history duration")
    p.add_argument("--bar-size", default="5 mins",
                   help='Candle for live trading AND IBKR backtest fetch ("1 min", "5 mins", "15 mins")')
    p.add_argument("--data-file", help="Backtest from a local OHLCV CSV instead of IBKR")
    p.add_argument("--save-data", help="Save fetched IBKR OHLCV data to CSV before backtesting")
    p.add_argument("--once", action="store_true", help="Process one completed bar then exit")
    p.add_argument("--schedule", action="store_true",
                   help="Only trade Sun 20:00 -> Fri 20:00 Toronto; sleep outside the window")
    p.add_argument("--wait-tws", action="store_true",
                   help="If TWS/Gateway is not up, wait and retry instead of exiting")
    p.add_argument("--symbol", default=TICKER_SYMBOL, help="Ticker symbol (default: DRAM)")
    p.add_argument("--exchange", default=TICKER_EXCHANGE, help="Exchange (default: SMART)")
    p.add_argument("--currency", default=TICKER_CURRENCY, help="Currency (default: USD)")
    return p


def main():
    global TICKER_SYMBOL, TICKER_EXCHANGE, TICKER_CURRENCY
    args = build_arg_parser().parse_args()
    TICKER_SYMBOL = args.symbol.upper()
    TICKER_EXCHANGE = args.exchange
    TICKER_CURRENCY = args.currency

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(
        {
            "ceiling_price": args.ceiling,
            "min_profit_pct": args.min_profit_pct,
            "capital_per_lot": args.capital_per_lot,
            "max_lots": args.max_lots,
            "thesis_floor": args.thesis_floor,
            "rsi_oversold": args.rsi_oversold,
            "volume_mult": args.volume_mult,
            "bb_period": args.bb_period,
            "bb_std": args.bb_std,
            "commission_per_order": args.commission,
            "entry_mode": args.entry_mode,
            "momo_lookback": args.momo_lookback,
            "momo_rsi_min": args.momo_rsi_min,
            "exit_mode": args.exit_mode,
            "trail_atr_mult": args.trail_atr_mult,
        }
    )

    if args.mode == "backtest":
        if args.data_file:
            run_backtest(load_ohlcv_csv(args.data_file), cfg, args.capital)
            return
        if not IB_AVAILABLE:
            log.error("ib_insync required for backtest data fetch. Run: pip install ib_insync")
            return
        ib = IB()
        try:
            try:
                ib.connect(args.host, args.port, clientId=args.client_id, readonly=True)
            except ConnectionRefusedError:
                log.error(
                    "Could not connect to IBKR at %s:%s for backtest data. "
                    "Use TWS paper port 7497 or IB Gateway paper port 4002.",
                    args.host,
                    args.port,
                )
                return
            log_account_context(ib, dry_run=True)
            contract = Stock(TICKER_SYMBOL, TICKER_EXCHANGE, TICKER_CURRENCY)
            ib.qualifyContracts(contract)
            bars = ib.reqHistoricalData(
                contract,
                "",
                args.duration,
                args.bar_size,
                "TRADES",
                True,
                1,
            )
            df = util.df(bars)
        finally:
            if ib.isConnected():
                ib.disconnect()
        if df is None or df.empty:
            raise RuntimeError(f"No historical data returned for {TICKER_SYMBOL}")
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["date"] = pd.to_datetime(df["date"])
        if args.save_data:
            Path(args.save_data).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.save_data, index=False)
            log.info("Saved fetched OHLCV data to %s", args.save_data)
        df.set_index("date", inplace=True)
        run_backtest(df, cfg, args.capital)
    else:
        run_live_or_paper(args, cfg)


if __name__ == "__main__":
    main()
