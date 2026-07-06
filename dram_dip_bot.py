#!/usr/bin/env python3
"""
dram_dip_bot.py - DRAM-specific dip accumulation bot for NYSE/NASDAQ via IBKR SMART routing
==========================================================================================
Trades DRAM (NASDAQ) using Bollinger + RSI + Volume dip strategy.
Never sells at a loss. Dynamic sizing with compounding from real account cash.
"""

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

# Try to import ib_insync for live mode; allow import to fail for dry-run testing
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
    "min_profit_pct": 2.0,
    "trail_giveback_pct": None,
    "capital_per_lot": 100.0,
    "max_lots": 1,
    "max_capital_pct": 100.0,
    "buy_cooldown_bars": 0,
    "thesis_floor": None,
    "commission_per_order": 1.0,   # IBKR fixed US: $0.005/share, min $1.00/order
    "fractional_shares": False,    # whole shares like the live account
}


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


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = df.copy()
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = compute_bollinger(
        df["close"], cfg["bb_period"], cfg["bb_std"]
    )
    df["rsi"] = compute_rsi(df["close"], cfg["rsi_period"])
    df["vol_ma"] = df["volume"].rolling(cfg["volume_ma_period"]).mean()
    return df


# ===================== DATA CLASSES =====================
@dataclass
class Lot:
    entry_price: float
    qty: float
    entry_time: datetime
    peak_price: float = 0.0
    limit_price: float = 0.0   # GTC sell-limit; fills only at this price or better
    entry_bar: int = -1        # bar index of the fill (no same-bar exits)


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
        self._pending_buy = False  # signal armed on bar close, filled next bar open

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
            if price > 0 and available > comm:
                if c.get("fractional_shares", False):
                    qty = (available - comm) / price
                else:
                    qty = float(int((available - comm) / price))
                cost = qty * price + comm
                if qty > 0 and cost <= p.cash + 1e-9:
                    lot = Lot(
                        entry_price=price, qty=qty, entry_time=ts, peak_price=price,
                        limit_price=exit_limit_price(price, qty, c), entry_bar=self._bar_index,
                    )
                    p.lots.append(lot)
                    p.cash -= cost
                    p.commissions += comm
                    p.buy_count += 1
                    p.last_buy_bar_index = self._bar_index
                    log.info(f"[{ts}] BUY {qty:g} @ {price:.2f} (GTC sell-limit {lot.limit_price:.2f})")

        # --- 2) Exits ---
        still_open = []
        for lot in p.lots:
            lot.peak_price = max(lot.peak_price, float(row["high"]))
            filled = False
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

        # --- 4) Arm entry for next bar's open ---
        if not thesis_broken and self._can_buy_more() and self._buy_signal(row):
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

    last_bar_time = None
    try:
        while True:
            current_cash = get_account_value(ib, account=account)
            current_shares, avg_cost = get_position(ib, TICKER_SYMBOL, account=account)

            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="5 D",
                barSizeSetting="15 mins",
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

                    # Entry: market buy only if cash truly covers whole shares + fee
                    if (
                        bot._buy_signal(row)
                        and current_shares == 0
                        and len(bot.portfolio.lots) < cfg["max_lots"]
                        and (cfg["thesis_floor"] is None or price > cfg["thesis_floor"])
                    ):
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

                    # Exit: maintain a GTC LIMIT SELL at avg_cost + target (never
                    # below break-even incl. fees). The order lives at IBKR, so it
                    # can never fill at a loss and survives bot restarts/crashes.
                    if current_shares > 0 and avg_cost > 0:
                        has_open_sell = any(
                            t.contract.symbol == TICKER_SYMBOL
                            and t.order.action == "SELL"
                            and t.orderStatus.status in ("PreSubmitted", "Submitted")
                            for t in ib.openTrades()
                        )
                        if not has_open_sell:
                            lp = round(exit_limit_price(avg_cost, current_shares, cfg), 2)
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
    p.add_argument("--min-profit-pct", type=float, default=2.0)
    p.add_argument("--thesis-floor", type=float, default=None)
    p.add_argument("--ceiling", type=float, default=None)
    p.add_argument("--bb-period", type=int, default=20)
    p.add_argument("--bb-std", type=float, default=DEFAULT_CONFIG["bb_std"])
    p.add_argument("--rsi-oversold", type=float, default=DEFAULT_CONFIG["rsi_oversold"])
    p.add_argument("--volume-mult", type=float, default=DEFAULT_CONFIG["volume_mult"])
    p.add_argument("--commission", type=float, default=1.0, help="Commission per order (USD)")
    p.add_argument("--duration", default="30 D", help="Backtest history duration")
    p.add_argument("--bar-size", default="15 mins", help="Backtest bar size")
    p.add_argument("--data-file", help="Backtest from a local OHLCV CSV instead of IBKR")
    p.add_argument("--save-data", help="Save fetched IBKR OHLCV data to CSV before backtesting")
    p.add_argument("--once", action="store_true", help="Process one completed bar then exit")
    return p


def main():
    args = build_arg_parser().parse_args()

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
