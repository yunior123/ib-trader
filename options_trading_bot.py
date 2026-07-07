#!/usr/bin/env python3
"""
options_trading_bot.py - Options (calls & puts) counterpart of day_trading_bot.py
=================================================================================
Same validated underlying signals (confirmed capitulation -> CALL; confirmed
euphoria/blow-off -> PUT), executed with options and institutional discipline:

  * NEVER 0DTE. Hard floor: 3+ days to expiration (default minimum 5).
  * Liquidity gates before any order: max bid/ask spread %, min open interest,
    non-zero volume. Orders are ALWAYS limits at mid — never market orders.
  * Position sizing: a fraction of cash per trade (options can go to zero;
    all-in is not risk management, it's roulette).
  * Profit-only SELLS: GTC limit at premium+target; trail on premium peak and
    DTE-escape exits only execute at >= floor = max(entry+floor_pct, break-even
    incl. fees). The bot never SELLS at a loss.
  * HONEST WARNING (theta): unlike stock, a held option decays and can expire
    worthless. If price never reaches the floor, expiry settles at intrinsic
    value and CAN realize a loss. That is an expiration event, not a sell —
    no rule can prevent it. Sizing (risk_fraction) is the real protection.

Backtest mode prices the synthetic ATM option with Black-Scholes on top of the
real underlying 1m/5m bars (realized-vol IV proxy) — the standard way to
prototype option strategies without paid intraday chain data. Live mode uses
the real IBKR option chain (reqSecDefOptParams) with the same rules.
"""

import argparse
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from day_trading_bot import (
    IB_AVAILABLE, IB, Stock, MarketOrder, LimitOrder, util,
    TORONTO, _bar_et, _in_rth,
    add_indicators, load_ohlcv_csv,
    in_trading_window, seconds_until_window_opens, wait_for_tws,
    log_account_context, get_account_value,
    DEFAULT_CONFIG as STOCK_CONFIG,
)

try:  # Option contract class (ib_async / ib_insync)
    from ib_async import Option
except ImportError:
    try:
        from ib_insync import Option
    except ImportError:
        Option = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("options_bot")

HARD_MIN_DTE = 3  # user rule: never 0DTE, never < 3 days to expiration

OPT_CONFIG = {
    # --- Underlying signal engine (same values validated on the stock bot) ---
    "bb_period": STOCK_CONFIG["bb_period"],
    "bb_std": STOCK_CONFIG["bb_std"],                # 3.0: only true panic/euphoria
    "rsi_period": STOCK_CONFIG["rsi_period"],
    "rsi_oversold": STOCK_CONFIG["rsi_oversold"],    # 25: capitulation -> CALL setup
    "rsi_overbought": 75.0,                          # euphoria -> PUT setup
    "volume_ma_period": STOCK_CONFIG["volume_ma_period"],
    "volume_mult": STOCK_CONFIG["volume_mult"],
    "atr_period": STOCK_CONFIG["atr_period"],
    "reclaim_lookback": STOCK_CONFIG["reclaim_lookback"],
    "reclaim_window_bars": STOCK_CONFIG["reclaim_window_bars"],
    "rth_only": True,
    "entry_cutoff": (15, 30),
    # --- Direction ---
    "direction": "both",          # "calls" | "puts" | "both"
    # --- Contract selection (Goldman rules: liquidity first, never 0DTE) ---
    "min_dte": 5,                 # prefer >= 5 days; hard floor 3 enforced
    "dte_exit": 2,                # try to be out when DTE <= 2 (only at >= floor)
    "target_delta": 0.60,         # slightly ITM: more intrinsic, less theta bleed
    "max_spread_pct": 10.0,       # reject chains with bid/ask spread > 10% of mid
    "min_open_interest": 100,
    # --- Premium exits (profit-only sells) ---
    "target_pct": 25.0,           # resting GTC limit at premium * 1.25
    "floor_pct": 3.0,             # never sell below premium+3% (nor break-even+fees)
    "trail_giveback_pct": 25.0,   # exit if premium retraces 25% off its peak (>= floor)
    # --- Risk (the real never-lose-big mechanism for options) ---
    "risk_fraction": 0.50,        # max fraction of cash per position
    "allow_single_contract": True,  # small accounts: allow 1 contract if affordable
    "commission_per_contract": 1.0,  # IBKR ~$0.65/contract, min $1/order — use $1
    "multiplier": 100,
    # --- Synthetic pricing (backtest only) ---
    "risk_free_rate": 0.04,
    "iv_premium": 1.10,           # implied vol trades above realized: RV * 1.10
    "iv_floor": 0.20,
    "iv_cap": 2.00,
}


# ===================== BLACK-SCHOLES (backtest pricing) =====================
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """Black-Scholes European price. T in years. right: 'C' or 'P'."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, S - K) if right == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if right == "C":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def realized_vol(closes: pd.Series, bars_per_day: int = 390) -> float:
    """Annualized realized vol from 1m closes (last ~5 sessions)."""
    rets = np.log(closes / closes.shift()).dropna().tail(bars_per_day * 5)
    if len(rets) < 30:
        return 0.5
    return float(rets.std() * math.sqrt(252 * bars_per_day))


def next_expiry(ts: datetime, min_dte: int) -> datetime:
    """Next Friday 16:00 ET that is at least min_dte days out (never < HARD_MIN_DTE)."""
    min_dte = max(min_dte, HARD_MIN_DTE)
    d = ts.astimezone(TORONTO)
    for ahead in range(1, 40):
        cand = d + timedelta(days=ahead)
        if cand.weekday() == 4 and (cand.date() - d.date()).days >= min_dte:
            return cand.replace(hour=16, minute=0, second=0, microsecond=0)
    return d + timedelta(days=max(min_dte, 7))


# ===================== POSITION =====================
@dataclass
class OptionPosition:
    right: str                 # 'C' or 'P'
    strike: float
    expiry: datetime
    entry_premium: float       # per share
    contracts: int
    entry_time: datetime
    entry_bar: int
    floor_premium: float       # never sell below this
    target_premium: float      # resting GTC limit
    peak_premium: float = 0.0
    pending_exit: bool = False


@dataclass
class OptPortfolio:
    cash: float
    starting_cash: float
    positions: List[OptionPosition] = field(default_factory=list)
    realized_pnl: float = 0.0
    commissions: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    expiry_losses: int = 0     # positions that expired below break-even (theta risk)
    expiry_loss_usd: float = 0.0


# ===================== BOT =====================
class OptionsBot:
    """Confirmed-reversal entries on the underlying; options execution."""

    def __init__(self, cfg: dict, capital: float):
        self.cfg = cfg
        self.p = OptPortfolio(cash=capital, starting_cash=capital)
        self._bar = 0
        self._pending: Optional[str] = None   # 'C'/'P' armed for next bar open
        self._dip_bar = None; self._dip_high = 0.0; self._dip_rsi = 50.0
        self._top_bar = None; self._top_low = 0.0; self._top_rsi = 50.0

    # ---- underlying signals (mirror of the validated stock engine) ----
    def _capitulation(self, row) -> bool:
        c = self.cfg
        if pd.isna(row["bb_lower"]) or pd.isna(row["vol_ma"]):
            return False
        return bool(
            row["close"] <= row["bb_lower"]
            and row["rsi"] <= c["rsi_oversold"]
            and row["vol_ma"] > 0
            and row["volume"] >= row["vol_ma"] * c["volume_mult"]
        )

    def _euphoria(self, row) -> bool:
        c = self.cfg
        if pd.isna(row["bb_upper"]) or pd.isna(row["vol_ma"]):
            return False
        return bool(
            row["close"] >= row["bb_upper"]
            and row["rsi"] >= c["rsi_overbought"]
            and row["vol_ma"] > 0
            and row["volume"] >= row["vol_ma"] * c["volume_mult"]
        )

    def _arm_entries(self, row, ts):
        c = self.cfg
        if self.p.positions or self._pending:
            return
        session_ok = (not c["rth_only"]) or (_in_rth(ts) and _bar_et(ts) < tuple(c["entry_cutoff"]))
        if not session_ok:
            return
        want_calls = c["direction"] in ("calls", "both")
        want_puts = c["direction"] in ("puts", "both")

        # CALL: capitulation armed -> green confirmation above panic high, RSI up
        if want_calls:
            if self._capitulation(row):
                self._dip_bar = self._bar
                self._dip_high = float(row["high"]); self._dip_rsi = float(row["rsi"])
            elif (
                self._dip_bar is not None
                and self._bar - self._dip_bar <= c["reclaim_window_bars"]
                and float(row["close"]) > self._dip_high
                and float(row["close"]) > float(row["open"])
                and float(row["rsi"]) > self._dip_rsi
            ):
                self._pending = "C"; self._dip_bar = None
                return
        # PUT: euphoria armed -> red confirmation below blow-off low, RSI down
        if want_puts:
            if self._euphoria(row):
                self._top_bar = self._bar
                self._top_low = float(row["low"]); self._top_rsi = float(row["rsi"])
            elif (
                self._top_bar is not None
                and self._bar - self._top_bar <= c["reclaim_window_bars"]
                and float(row["close"]) < self._top_low
                and float(row["close"]) < float(row["open"])
                and float(row["rsi"]) < self._top_rsi
            ):
                self._pending = "P"; self._top_bar = None

    # ---- synthetic option lifecycle (backtest) ----
    def _price(self, pos: OptionPosition, S: float, ts, sigma: float) -> float:
        T = max(0.0, (pos.expiry - ts.astimezone(TORONTO)).total_seconds() / (365.0 * 86400))
        return bs_price(S, pos.strike, T, self.cfg["risk_free_rate"], sigma, pos.right)

    def step(self, row, ts, sigma: float):
        c = self.cfg
        p = self.p
        self._bar += 1
        mult = c["multiplier"]
        comm = c["commission_per_contract"]

        # 1) fill pending entry at this bar's open (limit-at-mid modeled as open px)
        if self._pending and (not c["rth_only"] or _in_rth(ts)):
            right = self._pending
            S = float(row["open"])
            expiry = next_expiry(ts, c["min_dte"])
            strike = round(S)  # ATM (delta ~0.5-0.6 with the IV premium)
            T = max(1e-6, (expiry - ts.astimezone(TORONTO)).total_seconds() / (365.0 * 86400))
            prem = bs_price(S, strike, T, c["risk_free_rate"], sigma, right)
            if prem > 0.05:
                budget = p.cash * c["risk_fraction"]
                cost_1 = prem * mult + comm
                n = int(budget / cost_1)
                if n < 1 and c["allow_single_contract"] and p.cash >= cost_1:
                    n = 1
                if n >= 1:
                    cost = n * prem * mult + comm
                    be = prem + (2 * comm) / (n * mult)      # break-even premium incl fees
                    floor = max(prem * (1 + c["floor_pct"] / 100), be * 1.001)
                    target = max(prem * (1 + c["target_pct"] / 100), floor)
                    p.positions.append(OptionPosition(
                        right=right, strike=strike, expiry=expiry, entry_premium=prem,
                        contracts=n, entry_time=ts, entry_bar=self._bar,
                        floor_premium=floor, target_premium=target, peak_premium=prem,
                    ))
                    p.cash -= cost
                    p.commissions += comm
                    p.buy_count += 1
                    dte = (expiry.date() - ts.astimezone(TORONTO).date()).days
                    log.info(
                        f"[{ts}] BUY {n}x {right} K={strike} DTE={dte} @ {prem:.2f} "
                        f"(target {target:.2f}, floor {floor:.2f})"
                    )
            self._pending = None

        # 2) manage open positions
        still = []
        for pos in p.positions:
            S_open, S_high, S_low, S_close = (float(row[k]) for k in ("open", "high", "low", "close"))
            prem_open = self._price(pos, S_open, ts, sigma)
            # best premium this bar: favorable underlying extreme for the right
            S_best = S_high if pos.right == "C" else S_low
            prem_best = self._price(pos, S_best, ts, sigma)
            prem_close = self._price(pos, S_close, ts, sigma)
            pos.peak_premium = max(pos.peak_premium, prem_best)
            sold = False

            def sell(prem_fill, tag):
                proceeds = pos.contracts * prem_fill * mult - comm
                pnl = pos.contracts * (prem_fill - pos.entry_premium) * mult - 2 * comm
                p.cash += proceeds
                p.commissions += comm
                p.realized_pnl += pnl
                p.sell_count += 1
                log.info(f"[{ts}] SELL ({tag}) {pos.contracts}x {pos.right} @ {prem_fill:.2f} (net {pnl:+.2f})")

            # expiry settlement (forced; the one place a loss can be realized)
            if ts.astimezone(TORONTO) >= pos.expiry:
                intrinsic = max(0.0, (S_close - pos.strike) if pos.right == "C" else (pos.strike - S_close))
                pnl = pos.contracts * (intrinsic - pos.entry_premium) * mult - comm
                p.cash += pos.contracts * intrinsic * mult
                p.realized_pnl += pnl
                p.sell_count += 1
                if pnl < 0:
                    p.expiry_losses += 1
                    p.expiry_loss_usd += pnl
                    log.warning(f"[{ts}] EXPIRY LOSS {pos.contracts}x {pos.right} K={pos.strike}: {pnl:+.2f} (theta risk)")
                continue

            # pending exit (trail/DTE) fills at open, floor-enforced
            if pos.pending_exit:
                pos.pending_exit = False
                if pos.entry_bar != self._bar and prem_open >= pos.floor_premium:
                    sell(prem_open, "flat")
                    sold = True
            # resting GTC limit at target touched intrabar
            if not sold and pos.entry_bar != self._bar and prem_best >= pos.target_premium:
                fill = max(pos.target_premium, prem_open)
                sell(fill, "target")
                sold = True
            if not sold:
                dte = (pos.expiry.date() - ts.astimezone(TORONTO).date()).days
                trail_ok = prem_close >= pos.floor_premium
                trail_broken = (
                    pos.peak_premium > pos.entry_premium
                    and prem_close <= pos.peak_premium * (1 - c["trail_giveback_pct"] / 100)
                )
                dte_escape = dte <= max(c["dte_exit"], 0) and trail_ok
                if pos.entry_bar != self._bar and trail_ok and (trail_broken or dte_escape):
                    pos.pending_exit = True
                still.append(pos)
        p.positions = still

        # 3) arm next entry from this completed bar
        self._arm_entries(row, ts)

    def summary(self, S_last: float, ts_last, sigma: float):
        p = self.p
        mtm = sum(pos.contracts * self._price(pos, S_last, ts_last, sigma) * self.cfg["multiplier"]
                  for pos in p.positions)
        return {
            "open_positions": len(p.positions),
            "cash": p.cash,
            "realized_pnl": p.realized_pnl,
            "mtm_open": mtm,
            "total_equity": p.cash + mtm,
            "buys": p.buy_count,
            "sells": p.sell_count,
            "commissions": p.commissions,
            "expiry_losses": p.expiry_losses,
            "expiry_loss_usd": p.expiry_loss_usd,
        }


# ===================== BACKTEST =====================
def run_backtest(df: pd.DataFrame, cfg: dict, capital: float):
    data = add_indicators(df, cfg)
    bot = OptionsBot(cfg, capital)
    sigma_series = {}
    closes = data["close"]
    # rolling sigma once per session (cheap + stable)
    dates = pd.Series([ts.date() for ts in data.index], index=data.index)
    for d in dates.unique():
        upto = closes[dates <= d]
        sigma_series[d] = min(max(realized_vol(upto) * cfg["iv_premium"], cfg["iv_floor"]), cfg["iv_cap"])
    for ts, row in data.iterrows():
        bot.step(row, ts, sigma_series[ts.date()])
    last_ts = data.index[-1]
    s = bot.summary(float(data.iloc[-1]["close"]), last_ts, sigma_series[last_ts.date()])
    sessions = len(dates.unique())
    log.info("=== OPTIONS BACKTEST SUMMARY ===")
    log.info(f"Sessions: {sessions} | trades: {s['buys']}B/{s['sells']}S | fees ${s['commissions']:.2f}")
    log.info(f"Realized PnL: ${s['realized_pnl']:+.2f} | open MTM: ${s['mtm_open']:.2f} | open pos: {s['open_positions']}")
    if s["expiry_losses"]:
        log.warning(f"EXPIRY LOSSES: {s['expiry_losses']} (${s['expiry_loss_usd']:+.2f}) — theta risk realized")
    log.info(f"Total equity: ${s['total_equity']:.2f} ({(s['total_equity']/capital-1)*100:+.2f}%)")
    return s


# ===================== LIVE (IBKR real option chain) =====================
def pick_contract(ib, und_contract, spot: float, right: str, cfg: dict):
    """Institutional contract selection: DTE >= min (never < 3), ATM strike,
    liquidity gates (spread, OI). Returns (Option, mid) or (None, reason)."""
    chains = ib.reqSecDefOptParams(und_contract.symbol, "", und_contract.secType, und_contract.conId)
    chain = next((c for c in chains if c.exchange == "SMART"), None)
    if chain is None:
        return None, "no SMART chain"
    today = datetime.now(TORONTO).date()
    min_dte = max(cfg["min_dte"], HARD_MIN_DTE)
    expiries = sorted(
        e for e in chain.expirations
        if (datetime.strptime(e, "%Y%m%d").date() - today).days >= min_dte
    )
    if not expiries:
        return None, f"no expiry with DTE >= {min_dte}"
    expiry = expiries[0]
    strike = min(chain.strikes, key=lambda k: abs(k - spot))
    opt = Option(und_contract.symbol, expiry, strike, right, "SMART",
                 tradingClass=chain.tradingClass, currency="USD")
    ib.qualifyContracts(opt)
    tick = ib.reqMktData(opt, "100,101", False, False)  # OI + option volume
    ib.sleep(3)
    bid = tick.bid if tick.bid and tick.bid > 0 else 0.0
    ask = tick.ask if tick.ask and tick.ask > 0 else 0.0
    ib.cancelMktData(opt)
    if bid <= 0 or ask <= 0:
        return None, "no quotes (market data subscription?)"
    mid = (bid + ask) / 2
    spread_pct = (ask - bid) / mid * 100
    if spread_pct > cfg["max_spread_pct"]:
        return None, f"spread {spread_pct:.1f}% > {cfg['max_spread_pct']}%"
    oi = max(tick.callOpenInterest or 0, tick.putOpenInterest or 0)
    if oi and oi < cfg["min_open_interest"]:
        return None, f"open interest {oi} < {cfg['min_open_interest']}"
    return opt, mid


def run_live(args, cfg: dict):
    if not IB_AVAILABLE or Option is None:
        log.error("ib_insync/ib_async required for live mode.")
        return
    if args.live:
        log.warning("!!! REAL MONEY OPTIONS - Type YES to confirm !!!")
        if input("> ").strip().upper() != "YES":
            return
    if args.wait_tws:
        wait_for_tws(args.host, args.port)
    ib = IB()
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=15,
               readonly=not args.live, account=args.account if args.live else "")
    log_account_context(ib, dry_run=not args.live)
    und = Stock(args.symbol.upper(), "SMART", "USD")
    ib.qualifyContracts(und)
    bot = OptionsBot(cfg, get_account_value(ib))
    log.info("Options bot connected. Cash: $%.2f", bot.p.cash)
    last_bar = None
    try:
        while True:
            if args.schedule and not in_trading_window():
                import time as _t
                w = seconds_until_window_opens()
                log.info("Outside Sun 20:00->Fri 20:00 Toronto window; sleeping %.0f min", w / 60)
                _t.sleep(w)
                continue
            if not ib.isConnected():
                if args.wait_tws:
                    wait_for_tws(args.host, args.port)
                ib.connect(args.host, args.port, clientId=args.client_id, timeout=15,
                           readonly=not args.live, account=args.account if args.live else "")
                ib.qualifyContracts(und)
            bars = ib.reqHistoricalData(und, "", "5 D", args.bar_size, "TRADES", True, 1)
            if not bars:
                ib.sleep(30); continue
            df = util.df(bars)
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            data = add_indicators(df, cfg)
            if data.index[-1] != last_bar and len(data) >= 2:
                row = data.iloc[-2]; sig_ts = data.index[-2]
                sigma = min(max(realized_vol(data["close"]) * cfg["iv_premium"],
                                cfg["iv_floor"]), cfg["iv_cap"])
                # entry signal armed by the sim engine
                bot.step(row, sig_ts.to_pydatetime() if hasattr(sig_ts, "to_pydatetime") else sig_ts, sigma)
                if args.live and bot._pending and not ib.positions():
                    spot = float(row["close"])
                    opt, mid = pick_contract(ib, und, spot, bot._pending, cfg)
                    if opt is None:
                        log.info("Skip entry: %s", mid)
                    else:
                        budget = get_account_value(ib) * cfg["risk_fraction"]
                        n = int(budget / (mid * cfg["multiplier"] + cfg["commission_per_contract"]))
                        n = max(n, 1 if cfg["allow_single_contract"] else 0)
                        if n >= 1:
                            ib.placeOrder(opt, LimitOrder("BUY", n, round(mid, 2)))
                            log.info("BUY %dx %s %s K=%s @ limit %.2f (mid)", n,
                                     opt.symbol, opt.lastTradeDateOrContractMonth, opt.strike, mid)
                            # profit-only exit lives at the broker
                            tgt = round(mid * (1 + cfg["target_pct"] / 100), 2)
                            ib.placeOrder(opt, LimitOrder("SELL", n, tgt, tif="GTC"))
                            log.info("GTC SELL limit @ %.2f (profit-only)", tgt)
                last_bar = data.index[-1]
                if args.once:
                    log.info("One-shot options check complete.")
                    break
            ib.sleep(25)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        ib.disconnect()


# ===================== CLI =====================
def build_parser():
    p = argparse.ArgumentParser(description="Options dip/euphoria bot (calls & puts, never 0DTE)")
    p.add_argument("--mode", choices=["backtest", "trade"], default="backtest")
    p.add_argument("--symbol", default="DRAM")
    p.add_argument("--data-file", help="Underlying OHLCV CSV for backtest")
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--direction", choices=["calls", "puts", "both"], default="both")
    p.add_argument("--min-dte", type=int, default=OPT_CONFIG["min_dte"],
                   help=f"Min days to expiration (hard floor {HARD_MIN_DTE}; 0DTE forbidden)")
    p.add_argument("--dte-exit", type=int, default=OPT_CONFIG["dte_exit"])
    p.add_argument("--target-pct", type=float, default=OPT_CONFIG["target_pct"])
    p.add_argument("--floor-pct", type=float, default=OPT_CONFIG["floor_pct"])
    p.add_argument("--trail-giveback-pct", type=float, default=OPT_CONFIG["trail_giveback_pct"])
    p.add_argument("--risk-fraction", type=float, default=OPT_CONFIG["risk_fraction"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=8)
    p.add_argument("--account", default="U26942420")
    p.add_argument("--bar-size", default="5 mins")
    p.add_argument("--live", action="store_true")
    p.add_argument("--once", action="store_true")
    p.add_argument("--schedule", action="store_true")
    p.add_argument("--wait-tws", action="store_true")
    return p


def main():
    args = build_parser().parse_args()
    cfg = OPT_CONFIG.copy()
    cfg.update({
        "direction": args.direction,
        "min_dte": max(args.min_dte, HARD_MIN_DTE),
        "dte_exit": args.dte_exit,
        "target_pct": args.target_pct,
        "floor_pct": args.floor_pct,
        "trail_giveback_pct": args.trail_giveback_pct,
        "risk_fraction": args.risk_fraction,
    })
    if args.min_dte < HARD_MIN_DTE:
        log.warning("min_dte %d < %d clamped: 0DTE/short-dated is forbidden.", args.min_dte, HARD_MIN_DTE)
    if args.mode == "backtest":
        if not args.data_file:
            raise SystemExit("--data-file required for backtest (underlying OHLCV CSV)")
        run_backtest(load_ohlcv_csv(args.data_file), cfg, args.capital)
    else:
        run_live(args, cfg)


if __name__ == "__main__":
    main()
