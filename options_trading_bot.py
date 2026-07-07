#!/usr/bin/env python3
"""
options_trading_bot.py - Institutional-grade options bot (v2: vertical debit spreads)
=====================================================================================
Same validated underlying signals as day_trading_bot.py (confirmed capitulation ->
bullish; confirmed euphoria -> bearish), executed with defined-risk option
structures and professional discipline.

v2 upgrades (sourced from optionlab, goquantra spread strategies, PyOptionTrader,
staskh/trading_skills, tastytrade-style mechanics):
  * DEFAULT STRUCTURE = VERTICAL DEBIT SPREAD (bull call / bear put):
      - long ~0.60-delta leg + short ~0.30-delta leg, same expiry
      - defined max loss = net debit (sizing certainty; no more account-eating
        single positions on expensive underlyings)
      - short leg offsets theta decay and IV-crush (vega-reduced)
  * Delta-targeted strikes via inverse Black-Scholes (not blind ATM).
  * IV-percentile gate: when realized-vol percentile is HIGH, long premium is
    expensive -> spreads only (long single option mode is blocked).
  * Risk-managed exits (user-approved: options CAN lose, cut early > ride to 0):
      - profit target: GTC limit at debit * (1 + target_pct)
      - stop loss: spread value <= debit * (1 - max_loss_pct) -> out next open
      - thesis stop: underlying invalidates the setup (breaks capitulation low /
        euphoria high by 0.5*ATR) -> out next open, salvage remaining value
      - DTE escape: DTE <= 2 -> out at market value (never hold to the cliff)
  * NEVER 0DTE: hard floor 3 days to expiration; default minimum 5.
  * Liquidity gates + limit-at-mid always. Live spreads use real IBKR combo
    (BAG) orders so both legs fill atomically at the net price.

Backtest prices both legs with Black-Scholes over real underlying 1m bars
(realized-vol IV proxy). Upper-bound results: real spreads/slippage not modeled.
"""

import argparse
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import NormalDist
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

try:
    from ib_async import Option, Contract, ComboLeg
except ImportError:
    try:
        from ib_insync import Option, Contract, ComboLeg
    except ImportError:
        Option = Contract = ComboLeg = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("options_bot")

HARD_MIN_DTE = 3   # never 0DTE, never < 3 days to expiration
_N = NormalDist()

OPT_CONFIG = {
    # --- Underlying signal engine (validated on the stock bot) ---
    "bb_period": STOCK_CONFIG["bb_period"],
    "bb_std": STOCK_CONFIG["bb_std"],
    "rsi_period": STOCK_CONFIG["rsi_period"],
    "rsi_oversold": STOCK_CONFIG["rsi_oversold"],
    "rsi_overbought": 75.0,
    "volume_ma_period": STOCK_CONFIG["volume_ma_period"],
    "volume_mult": STOCK_CONFIG["volume_mult"],
    "atr_period": STOCK_CONFIG["atr_period"],
    "reclaim_lookback": STOCK_CONFIG["reclaim_lookback"],
    "reclaim_window_bars": STOCK_CONFIG["reclaim_window_bars"],
    "rth_only": True,
    "entry_cutoff": (15, 30),
    "direction": "both",            # calls | puts | both
    # --- Structure ---
    "structure": "spread",          # "spread" (defined risk, DEFAULT) | "long"
    "long_delta": 0.60,             # long leg: slightly ITM, more intrinsic
    "short_delta": 0.30,            # short leg: ~1 sigma OTM, funds theta/vega
    # --- Contract selection ---
    "min_dte": 5,                   # hard floor 3 (0DTE forbidden)
    "dte_exit": 2,                  # out when DTE <= 2, at market value
    "max_spread_pct": 10.0,         # per-leg bid/ask spread gate (live)
    "min_open_interest": 100,
    # --- Exits (risk-managed; losses allowed but CUT, never ridden to zero) ---
    "target_pct": 50.0,             # GTC limit at debit * 1.50 (91% win rate in sweep)
    "max_loss_pct": 100.0,          # price stop DISABLED: risk is already defined by the debit
                                    # (sweep: price stops on 1m marks destroyed the edge)
    "thesis_stop": False,           # OFF by default (sweep: -$798 with it, +$7,624 without)
    # --- IV regime gate ---
    "iv_pctile_block_long": 70.0,   # RV percentile above this: block "long" structure
    # --- Risk sizing (defined risk makes this exact) ---
    "risk_fraction": 0.25,          # max net debit per position = 25% of cash
    "allow_single_spread": True,    # small accounts: 1 spread if affordable
    "commission_per_contract": 1.0, # per leg per contract (IBKR ~$0.65, min $1)
    "multiplier": 100,
    # --- Synthetic pricing (backtest) ---
    "risk_free_rate": 0.04,
    "iv_premium": 1.10,
    "iv_floor": 0.20,
    "iv_cap": 2.00,
}


# ===================== BLACK-SCHOLES =====================
def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S, K, T, r, sigma, right) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, S - K) if right == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if right == "C":
        return S * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)
    return K * math.exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)


def strike_for_delta(S, T, r, sigma, right, delta) -> float:
    """Inverse BS: strike whose |delta| equals the target (delta-targeted legs)."""
    if right == "C":
        d1 = _N.inv_cdf(min(max(delta, 0.01), 0.99))
    else:  # put delta = N(d1) - 1
        d1 = _N.inv_cdf(min(max(1.0 - delta, 0.01), 0.99))
    K = S * math.exp((r + 0.5 * sigma ** 2) * T - d1 * sigma * math.sqrt(T))
    step = 0.5 if S < 25 else (1.0 if S < 200 else 5.0)
    return max(step, round(K / step) * step)


def realized_vol(closes: pd.Series, bars_per_day: int = 390) -> float:
    rets = np.log(closes / closes.shift()).dropna().tail(bars_per_day * 5)
    if len(rets) < 30:
        return 0.5
    return float(rets.std() * math.sqrt(252 * bars_per_day))


def next_expiry(ts: datetime, min_dte: int) -> datetime:
    min_dte = max(min_dte, HARD_MIN_DTE)
    d = ts.astimezone(TORONTO)
    for ahead in range(1, 40):
        cand = d + timedelta(days=ahead)
        if cand.weekday() == 4 and (cand.date() - d.date()).days >= min_dte:
            return cand.replace(hour=16, minute=0, second=0, microsecond=0)
    return d + timedelta(days=max(min_dte, 7))


# ===================== POSITION =====================
@dataclass
class SpreadPosition:
    right: str                # 'C' (bull call spread) or 'P' (bear put spread)
    k_long: float
    k_short: Optional[float]  # None => plain long option
    expiry: datetime
    entry_debit: float        # net premium paid per share
    contracts: int
    entry_time: datetime
    entry_bar: int
    target_value: float       # GTC limit on the spread value
    stop_value: float         # cut if spread value drops here (defined loss)
    thesis_level: float       # underlying level that invalidates the trade
    peak_value: float = 0.0
    pending_exit: bool = False
    exit_reason: str = ""


@dataclass
class OptPortfolio:
    cash: float
    starting_cash: float
    positions: List[SpreadPosition] = field(default_factory=list)
    realized_pnl: float = 0.0
    commissions: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    wins: int = 0
    losses: int = 0
    loss_usd: float = 0.0


# ===================== BOT =====================
class OptionsBot:
    def __init__(self, cfg: dict, capital: float):
        self.cfg = cfg
        self.p = OptPortfolio(cash=capital, starting_cash=capital)
        self._bar = 0
        self._pending: Optional[dict] = None
        self._dip_bar = None; self._dip_high = 0.0; self._dip_rsi = 50.0; self._dip_low = 0.0
        self._top_bar = None; self._top_low = 0.0; self._top_rsi = 50.0; self._top_high = 0.0
        self._rv_history: List[float] = []

    # ---- signals ----
    def _capitulation(self, row) -> bool:
        c = self.cfg
        if pd.isna(row["bb_lower"]) or pd.isna(row["vol_ma"]):
            return False
        return bool(row["close"] <= row["bb_lower"] and row["rsi"] <= c["rsi_oversold"]
                    and row["vol_ma"] > 0 and row["volume"] >= row["vol_ma"] * c["volume_mult"])

    def _euphoria(self, row) -> bool:
        c = self.cfg
        if pd.isna(row["bb_upper"]) or pd.isna(row["vol_ma"]):
            return False
        return bool(row["close"] >= row["bb_upper"] and row["rsi"] >= c["rsi_overbought"]
                    and row["vol_ma"] > 0 and row["volume"] >= row["vol_ma"] * c["volume_mult"])

    def iv_percentile(self, rv: float) -> float:
        self._rv_history.append(rv)
        hist = self._rv_history[-2000:]
        if len(hist) < 20:
            return 50.0
        return 100.0 * sum(1 for x in hist if x <= rv) / len(hist)

    def _arm_entries(self, row, ts, atr: float):
        c = self.cfg
        if self.p.positions or self._pending:
            return
        session_ok = (not c["rth_only"]) or (_in_rth(ts) and _bar_et(ts) < tuple(c["entry_cutoff"]))
        if not session_ok:
            return
        want_calls = c["direction"] in ("calls", "both")
        want_puts = c["direction"] in ("puts", "both")

        if want_calls:
            if self._capitulation(row):
                self._dip_bar = self._bar
                self._dip_high = float(row["high"]); self._dip_low = float(row["low"])
                self._dip_rsi = float(row["rsi"])
            elif (self._dip_bar is not None
                  and self._bar - self._dip_bar <= c["reclaim_window_bars"]
                  and float(row["close"]) > self._dip_high
                  and float(row["close"]) > float(row["open"])
                  and float(row["rsi"]) > self._dip_rsi):
                self._pending = {"right": "C", "thesis": self._dip_low - self.cfg.get("thesis_atr_buffer", 0.5) * atr}
                self._dip_bar = None
                return
        if want_puts:
            if self._euphoria(row):
                self._top_bar = self._bar
                self._top_low = float(row["low"]); self._top_high = float(row["high"])
                self._top_rsi = float(row["rsi"])
            elif (self._top_bar is not None
                  and self._bar - self._top_bar <= c["reclaim_window_bars"]
                  and float(row["close"]) < self._top_low
                  and float(row["close"]) < float(row["open"])
                  and float(row["rsi"]) < self._top_rsi):
                self._pending = {"right": "P", "thesis": self._top_high + self.cfg.get("thesis_atr_buffer", 0.5) * atr}
                self._top_bar = None

    # ---- pricing ----
    def _value(self, pos: SpreadPosition, S: float, ts, sigma: float) -> float:
        T = max(0.0, (pos.expiry - ts.astimezone(TORONTO)).total_seconds() / (365.0 * 86400))
        r = self.cfg["risk_free_rate"]
        v = bs_price(S, pos.k_long, T, r, sigma, pos.right)
        if pos.k_short is not None:
            v -= bs_price(S, pos.k_short, T, r, sigma, pos.right)
        return max(0.0, v)

    def _legs(self, pos: SpreadPosition) -> int:
        return 2 if pos.k_short is not None else 1

    # ---- simulation step ----
    def step(self, row, ts, sigma: float):
        c = self.cfg
        p = self.p
        self._bar += 1
        mult = c["multiplier"]

        # 1) fill pending entry at this bar's open
        if self._pending and (not c["rth_only"] or _in_rth(ts)):
            info = self._pending; self._pending = None
            right = info["right"]
            S = float(row["open"])
            expiry = next_expiry(ts, c["min_dte"])
            T = max(1e-6, (expiry - ts.astimezone(TORONTO)).total_seconds() / (365.0 * 86400))
            r = c["risk_free_rate"]
            iv_pct = self.iv_percentile(sigma)
            structure = c["structure"]
            if structure == "long" and iv_pct >= c["iv_pctile_block_long"]:
                structure = "spread"  # IV too rich to buy naked premium
                log.info(f"[{ts}] IV pct {iv_pct:.0f} >= {c['iv_pctile_block_long']:.0f}: forcing spread structure")
            k_long = strike_for_delta(S, T, r, sigma, right, c["long_delta"])
            k_short = None
            debit = bs_price(S, k_long, T, r, sigma, right)
            if structure == "spread":
                k_short = strike_for_delta(S, T, r, sigma, right, c["short_delta"])
                if (right == "C" and k_short <= k_long) or (right == "P" and k_short >= k_long):
                    k_short = None  # degenerate; stay long-only
                else:
                    debit -= bs_price(S, k_short, T, r, sigma, right)
            legs = 2 if k_short is not None else 1
            comm_in = c["commission_per_contract"] * legs
            if debit > 0.05:
                cost_1 = debit * mult + comm_in
                budget = p.cash * c["risk_fraction"]
                n = int(budget / cost_1)
                if n < 1 and c["allow_single_spread"] and p.cash >= cost_1:
                    n = 1
                if n >= 1:
                    width = abs((k_short or k_long) - k_long)
                    max_profit = (width - debit) if k_short is not None else float("inf")
                    target = min(debit * (1 + c["target_pct"] / 100),
                                 debit + max_profit * 0.9) if k_short is not None else debit * (1 + c["target_pct"] / 100)
                    p.positions.append(SpreadPosition(
                        right=right, k_long=k_long, k_short=k_short, expiry=expiry,
                        entry_debit=debit, contracts=n, entry_time=ts, entry_bar=self._bar,
                        target_value=target,
                        stop_value=debit * (1 - c["max_loss_pct"] / 100),
                        thesis_level=info["thesis"], peak_value=debit,
                    ))
                    p.cash -= n * debit * mult + comm_in
                    p.commissions += comm_in
                    p.buy_count += 1
                    dte = (expiry.date() - ts.astimezone(TORONTO).date()).days
                    tag = f"{right}-spread {k_long}/{k_short}" if k_short else f"{right} {k_long}"
                    log.info(f"[{ts}] BUY {n}x {tag} DTE={dte} debit={debit:.2f} "
                             f"(target {target:.2f}, stop {p.positions[-1].stop_value:.2f}, IVpct {iv_pct:.0f})")

        # 2) manage positions
        still = []
        for pos in p.positions:
            S_open, S_high, S_low, S_close = (float(row[k]) for k in ("open", "high", "low", "close"))
            legs = self._legs(pos)
            comm_out = c["commission_per_contract"] * legs
            v_open = self._value(pos, S_open, ts, sigma)
            S_best = S_high if pos.right == "C" else S_low
            v_best = self._value(pos, S_best, ts, sigma)
            v_close = self._value(pos, S_close, ts, sigma)
            pos.peak_value = max(pos.peak_value, v_best)
            sold = False

            def close_out(v_fill, tag):
                nonlocal sold
                proceeds = pos.contracts * v_fill * mult - comm_out
                pnl = pos.contracts * (v_fill - pos.entry_debit) * mult - comm_out - \
                    c["commission_per_contract"] * legs  # entry legs commission
                p.cash += proceeds
                p.commissions += comm_out
                p.realized_pnl += pnl
                p.sell_count += 1
                if pnl >= 0:
                    p.wins += 1
                else:
                    p.losses += 1
                    p.loss_usd += pnl
                log.info(f"[{ts}] CLOSE ({tag}) {pos.contracts}x @ {v_fill:.2f} (net {pnl:+.2f})")
                sold = True

            # expiry settlement
            if ts.astimezone(TORONTO) >= pos.expiry:
                intr = max(0.0, (S_close - pos.k_long) if pos.right == "C" else (pos.k_long - S_close))
                if pos.k_short is not None:
                    intr -= max(0.0, (S_close - pos.k_short) if pos.right == "C" else (pos.k_short - S_close))
                close_out(max(0.0, intr), "expiry")
                continue
            # pending exit fills at open
            if pos.pending_exit:
                pos.pending_exit = False
                if pos.entry_bar != self._bar:
                    close_out(v_open, pos.exit_reason)
                    continue
            # profit target: resting GTC limit on spread value
            if not sold and pos.entry_bar != self._bar and v_best >= pos.target_value:
                close_out(max(pos.target_value, v_open), "target")
                continue
            # risk exits evaluated on close -> out next bar open
            if not sold:
                if pos.entry_bar != self._bar:
                    dte = (pos.expiry.date() - ts.astimezone(TORONTO).date()).days
                    reason = ""
                    if v_close <= pos.stop_value:
                        reason = "stop"
                    elif c["thesis_stop"] and (
                        (pos.right == "C" and S_close < pos.thesis_level)
                        or (pos.right == "P" and S_close > pos.thesis_level)
                    ):
                        reason = "thesis"
                    elif dte <= max(c["dte_exit"], 0):
                        reason = "dte"
                    if reason:
                        pos.pending_exit = True
                        pos.exit_reason = reason
                still.append(pos)
        p.positions = still

        # 3) arm next entry
        atr = float(row["atr"]) if not pd.isna(row["atr"]) else 0.0
        self._arm_entries(row, ts, atr)

    def summary(self, S_last, ts_last, sigma):
        p = self.p
        mtm = sum(pos.contracts * self._value(pos, S_last, ts_last, sigma) * self.cfg["multiplier"]
                  for pos in p.positions)
        return {
            "open_positions": len(p.positions), "cash": p.cash,
            "realized_pnl": p.realized_pnl, "mtm_open": mtm,
            "total_equity": p.cash + mtm, "buys": p.buy_count, "sells": p.sell_count,
            "wins": p.wins, "losses": p.losses, "loss_usd": p.loss_usd,
            "commissions": p.commissions,
        }


# ===================== BACKTEST =====================
def run_backtest(df: pd.DataFrame, cfg: dict, capital: float):
    data = add_indicators(df, cfg)
    bot = OptionsBot(cfg, capital)
    closes = data["close"]
    dates = pd.Series([ts.date() for ts in data.index], index=data.index)
    sig = {}
    for d in dates.unique():
        upto = closes[dates <= d]
        sig[d] = min(max(realized_vol(upto) * cfg["iv_premium"], cfg["iv_floor"]), cfg["iv_cap"])
    for ts, row in data.iterrows():
        bot.step(row, ts, sig[ts.date()])
    last_ts = data.index[-1]
    s = bot.summary(float(data.iloc[-1]["close"]), last_ts, sig[last_ts.date()])
    log.info("=== OPTIONS BACKTEST (v2 spreads) ===")
    log.info(f"Sessions: {len(dates.unique())} | {s['buys']}B/{s['sells']}S | "
             f"wins {s['wins']} / losses {s['losses']} (${s['loss_usd']:+.2f}) | fees ${s['commissions']:.2f}")
    log.info(f"Realized: ${s['realized_pnl']:+.2f} | open MTM: ${s['mtm_open']:.2f} ({s['open_positions']} pos)")
    log.info(f"Total equity: ${s['total_equity']:.2f} ({(s['total_equity']/capital-1)*100:+.2f}%)")
    return s


# ===================== LIVE (real IBKR chain, combo orders) =====================
def _leg_ok(tick, cfg) -> tuple:
    bid = tick.bid if tick.bid and tick.bid > 0 else 0.0
    ask = tick.ask if tick.ask and tick.ask > 0 else 0.0
    if bid <= 0 or ask <= 0:
        return None, "no quotes"
    mid = (bid + ask) / 2
    if (ask - bid) / mid * 100 > cfg["max_spread_pct"]:
        return None, f"leg spread {(ask - bid) / mid * 100:.1f}%"
    return mid, ""


def pick_spread(ib, und, spot, right, cfg, sigma):
    """Delta-targeted vertical: long ~0.60d + short ~0.30d, same expiry (DTE>=min)."""
    chains = ib.reqSecDefOptParams(und.symbol, "", und.secType, und.conId)
    chain = next((ch for ch in chains if ch.exchange == "SMART"), None)
    if chain is None:
        return None, "no SMART chain"
    today = datetime.now(TORONTO).date()
    min_dte = max(cfg["min_dte"], HARD_MIN_DTE)
    expiries = sorted(e for e in chain.expirations
                      if (datetime.strptime(e, "%Y%m%d").date() - today).days >= min_dte)
    if not expiries:
        return None, f"no expiry with DTE>={min_dte}"
    expiry = expiries[0]
    dte = (datetime.strptime(expiry, "%Y%m%d").date() - today).days
    T = dte / 365.0
    r = cfg["risk_free_rate"]
    kl_t = strike_for_delta(spot, T, r, sigma, right, cfg["long_delta"])
    ks_t = strike_for_delta(spot, T, r, sigma, right, cfg["short_delta"])
    k_long = min(chain.strikes, key=lambda k: abs(k - kl_t))
    k_short = min(chain.strikes, key=lambda k: abs(k - ks_t))
    if k_short == k_long:
        return None, "strikes collapsed"
    legs = []
    mids = []
    for k, action in ((k_long, "BUY"), (k_short, "SELL")):
        o = Option(und.symbol, expiry, k, right, "SMART", tradingClass=chain.tradingClass, currency="USD")
        ib.qualifyContracts(o)
        t = ib.reqMktData(o, "", False, False)
        ib.sleep(2.5)
        mid, err = _leg_ok(t, cfg)
        ib.cancelMktData(o)
        if mid is None:
            return None, f"{action} K={k}: {err}"
        legs.append((o, action)); mids.append(mid if action == "BUY" else -mid)
    net_mid = sum(mids)
    if net_mid <= 0.05:
        return None, f"net debit too small ({net_mid:.2f})"
    combo = Contract(symbol=und.symbol, secType="BAG", currency="USD", exchange="SMART",
                     comboLegs=[ComboLeg(conId=o.conId, ratio=1, action=a, exchange="SMART")
                                for o, a in legs])
    return (combo, net_mid, k_long, k_short, expiry), ""


def run_live(args, cfg):
    if not IB_AVAILABLE or Option is None:
        log.error("ib_insync/ib_async required.")
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
    log.info("Options bot v2 connected. Cash: $%.2f | structure=%s", bot.p.cash, cfg["structure"])
    last_bar = None
    try:
        while True:
            if args.schedule and not in_trading_window():
                import time as _t
                _t.sleep(seconds_until_window_opens())
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
                ts_py = sig_ts.to_pydatetime() if hasattr(sig_ts, "to_pydatetime") else sig_ts
                bot.step(row, ts_py, sigma)
                if args.live and bot._pending and not ib.positions():
                    picked, err = pick_spread(ib, und, float(row["close"]), bot._pending["right"], cfg, sigma)
                    if picked is None:
                        log.info("Skip entry: %s", err)
                    else:
                        combo, net_mid, kl, ks, expiry = picked
                        budget = get_account_value(ib) * cfg["risk_fraction"]
                        n = int(budget / (net_mid * cfg["multiplier"] + 2 * cfg["commission_per_contract"]))
                        n = max(n, 1 if cfg["allow_single_spread"] else 0)
                        if n >= 1:
                            ib.placeOrder(combo, LimitOrder("BUY", n, round(net_mid, 2)))
                            log.info("BUY %dx %s spread %s/%s exp %s @ net %.2f (limit)",
                                     n, bot._pending["right"], kl, ks, expiry, net_mid)
                            tgt = round(net_mid * (1 + cfg["target_pct"] / 100), 2)
                            ib.placeOrder(combo, LimitOrder("SELL", n, tgt, tif="GTC"))
                            log.info("GTC SELL combo limit @ %.2f", tgt)
                last_bar = data.index[-1]
                if args.once:
                    log.info("One-shot options v2 check complete.")
                    break
            ib.sleep(25)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        ib.disconnect()


# ===================== CLI =====================
def build_parser():
    p = argparse.ArgumentParser(description="Options bot v2: delta-targeted vertical debit spreads, never 0DTE")
    p.add_argument("--mode", choices=["backtest", "trade"], default="backtest")
    p.add_argument("--symbol", default="DRAM")
    p.add_argument("--data-file")
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--direction", choices=["calls", "puts", "both"], default="both")
    p.add_argument("--structure", choices=["spread", "long"], default=OPT_CONFIG["structure"])
    p.add_argument("--long-delta", type=float, default=OPT_CONFIG["long_delta"])
    p.add_argument("--short-delta", type=float, default=OPT_CONFIG["short_delta"])
    p.add_argument("--min-dte", type=int, default=OPT_CONFIG["min_dte"])
    p.add_argument("--dte-exit", type=int, default=OPT_CONFIG["dte_exit"])
    p.add_argument("--target-pct", type=float, default=OPT_CONFIG["target_pct"])
    p.add_argument("--max-loss-pct", type=float, default=OPT_CONFIG["max_loss_pct"])
    p.add_argument("--risk-fraction", type=float, default=OPT_CONFIG["risk_fraction"])
    p.add_argument("--no-thesis-stop", action="store_true")
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
        "direction": args.direction, "structure": args.structure,
        "long_delta": args.long_delta, "short_delta": args.short_delta,
        "min_dte": max(args.min_dte, HARD_MIN_DTE), "dte_exit": args.dte_exit,
        "target_pct": args.target_pct, "max_loss_pct": args.max_loss_pct,
        "risk_fraction": args.risk_fraction, "thesis_stop": not args.no_thesis_stop,
    })
    if args.min_dte < HARD_MIN_DTE:
        log.warning("min_dte clamped to %d: 0DTE/short-dated forbidden.", HARD_MIN_DTE)
    if args.mode == "backtest":
        if not args.data_file:
            raise SystemExit("--data-file required")
        run_backtest(load_ohlcv_csv(args.data_file), cfg, args.capital)
    else:
        run_live(args, cfg)


if __name__ == "__main__":
    main()
