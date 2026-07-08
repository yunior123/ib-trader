#!/usr/bin/env python3
"""
day_trading_leveraged_bot.py - Signal on the base ticker, trade its leveraged ETF
=================================================================================
Uses the validated day_trading_bot engine (confirmed capitulation entry +
adaptive profit-only exit) but SPLITS the roles:

  * SIGNALS  computed on the BASE ticker's bars (DRAM, TSLA, NVDA, ...)
  * TRADES   executed on the LEVERAGED ETF (RAM, TSLL, NVDL, ...) at its prices

Pairs (base -> leveraged):
  DRAM->RAM  SPCX->SPCH  TSLA->TSLL  AAPL->AAPU  NVDA->NVDL
  TSM->TSMU  TXN->TXNU   AMD->AMDD   INTC->INTW  ASML->ASMU

Why this design: leveraged ETFs amplify the rebound the signal predicts
(2x the move on the same entry timing), but they carry daily-reset decay —
holding bags in them bleeds value even sideways. The adaptive exit's EOD
flatten and profit floor matter MORE here, not less. Floors/targets are set
on the ETF's own prices, so the never-sell-below-floor guarantee is intact.
"""

import argparse
import logging

import pandas as pd

from day_trading_bot import (
    IB_AVAILABLE, IB, Stock, MarketOrder, LimitOrder, util,
    TORONTO, _bar_et, _in_rth,
    DipAccumulatorBot, Lot, DEFAULT_CONFIG,
    add_indicators, load_ohlcv_csv, exit_limit_price, floor_price,
    in_trading_window, seconds_until_window_opens, wait_for_tws, tws_port_open,
    log_account_context, get_account_value, get_position,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("leveraged_bot")

# base ticker (signal source) -> leveraged ETF (traded instrument)
PAIRS = {
    "DRAM": "RAM",
    "SPCX": "SPCH",
    "TSLA": "TSLL",
    "AAPL": "AAPU",
    "NVDA": "NVDL",
    "TSM": "TSMU",
    "TXN": "TXNU",
    "AMD": "AMDD",
    "INTC": "INTW",
    "ASML": "ASMU",
}


class LeveragedPairBot(DipAccumulatorBot):
    """Signals from the base row; entries/exits priced on the leveraged ETF row.

    The exec row must carry the ETF's own OHLCV and ATR (for the trail);
    the signal row carries the base ticker's indicators (BB/RSI/volume).
    """

    def step_pair(self, sig_row, exe_row, ts):
        c = self.cfg
        p = self.portfolio
        self._bar_index += 1
        comm = c.get("commission_per_order", 0.0)

        # --- 1) Fill last bar's signal at the ETF's open (RTH only) ---
        if self._pending_buy:
            self._pending_buy = False
            if not c.get("rth_only", False) or _in_rth(ts):
                price = float(exe_row["open"])
                available = self._buy_capital()
                if price > 0 and available > comm:
                    qty = float(int((available - comm) / price))
                    cost = qty * price + comm
                    if qty > 0 and cost <= p.cash + 1e-9:
                        lot = Lot(
                            entry_price=price, qty=qty, entry_time=ts, peak_price=price,
                            limit_price=floor_price(price, qty, c), entry_bar=self._bar_index,
                        )
                        p.lots.append(lot)
                        p.cash -= cost
                        p.commissions += comm
                        p.buy_count += 1
                        p.last_buy_bar_index = self._bar_index
                        log.info(f"[{ts}] BUY LETF {qty:g} @ {price:.2f} (floor {lot.limit_price:.2f})")

        # --- 2) Adaptive exits on the ETF's prices ---
        still = []
        for lot in p.lots:
            filled = False
            floor_px = lot.limit_price
            bars_held = self._bar_index - lot.entry_bar
            target_px = lot.entry_price * (1 + c.get("profit_target_pct", 4.0) / 100)
            limit_now = target_px if bars_held < c.get("time_stop_bars", 390) else floor_px
            limit_now = max(limit_now, floor_px)

            if lot.pending_exit:
                lot.pending_exit = False
                open_px = float(exe_row["open"])
                if lot.entry_bar != self._bar_index and open_px >= floor_px:
                    p.cash += lot.qty * open_px - comm
                    p.commissions += comm
                    pnl = lot.qty * (open_px - lot.entry_price) - 2 * comm
                    p.realized_pnl += pnl
                    p.sell_count += 1
                    filled = True
                    log.info(f"[{ts}] SELL LETF (flat) {lot.qty:g} @ {open_px:.2f} (net {pnl:+.2f})")
            if not filled and lot.entry_bar != self._bar_index and float(exe_row["high"]) >= limit_now:
                open_px = float(exe_row["open"])
                fill = open_px if open_px > limit_now else limit_now
                p.cash += lot.qty * fill - comm
                p.commissions += comm
                pnl = lot.qty * (fill - lot.entry_price) - 2 * comm
                p.realized_pnl += pnl
                p.sell_count += 1
                filled = True
                log.info(f"[{ts}] SELL LETF (limit) {lot.qty:g} @ {fill:.2f} (net {pnl:+.2f})")
            if not filled:
                lot.peak_price = max(lot.peak_price, float(exe_row["high"]))
                close_px = float(exe_row["close"])
                atr = float(exe_row["atr"]) if not pd.isna(exe_row["atr"]) else 0.0
                if lot.entry_bar != self._bar_index and close_px > floor_px:
                    trail_broken = (
                        atr > 0 and close_px < lot.peak_price - c.get("trail_atr_mult", 3.0) * atr
                    )
                    eod = c.get("eod_flatten", True) and _bar_et(ts) >= (15, 45) and _in_rth(ts)
                    if trail_broken or eod:
                        lot.pending_exit = True
                still.append(lot)
        p.lots = still

        # --- 3) Arm entry from the BASE ticker's completed bar ---
        session_ok = True
        if c.get("rth_only", False):
            session_ok = _in_rth(ts) and _bar_et(ts) < tuple(c.get("entry_cutoff", (15, 30)))
        if self._can_buy_more() and session_ok:
            mode = c.get("entry_mode", "confirmed")
            if mode == "confirmed":
                if self._buy_signal(sig_row):
                    self._dip_armed_bar = self._bar_index
                    self._dip_high = float(sig_row["high"])
                    self._dip_rsi = float(sig_row["rsi"])
                elif (
                    self._dip_armed_bar is not None
                    and self._bar_index - self._dip_armed_bar <= c.get("reclaim_window_bars", 60)
                    and float(sig_row["close"]) > self._dip_high
                    and float(sig_row["close"]) > float(sig_row["open"])
                    and float(sig_row["rsi"]) > self._dip_rsi
                ):
                    self._pending_buy = True
                    self._dip_armed_bar = None
            elif mode == "dip" and self._buy_signal(sig_row):
                self._pending_buy = True


# ===================== BACKTEST =====================
def align_frames(base_df: pd.DataFrame, letf_df: pd.DataFrame, cfg: dict):
    """Inner-join on timestamps; base gets signal indicators, LETF gets ATR."""
    base = add_indicators(base_df, cfg)
    letf = add_indicators(letf_df, cfg)  # only its atr/ohlcv are used
    idx = base.index.intersection(letf.index)
    return base.loc[idx], letf.loc[idx]


def run_pair_backtest(base_df, letf_df, cfg, capital):
    base, letf = align_frames(base_df, letf_df, cfg)
    if len(base) < 100:
        raise RuntimeError(f"only {len(base)} aligned bars — not enough overlap")
    bot = LeveragedPairBot(cfg, capital)
    for ts, sig_row in base.iterrows():
        bot.step_pair(sig_row, letf.loc[ts], ts.to_pydatetime())
    last = float(letf.iloc[-1]["close"])
    s = bot.summary(last)
    sessions = len(pd.Series(base.index.date).unique())
    log.info("=== LEVERAGED PAIR BACKTEST ===")
    log.info(f"Aligned bars: {len(base)} | sessions: {sessions} | trades {s['buys']}B/{s['sells']}S | fees ${s['commissions']:.2f}")
    log.info(f"Realized: ${s['realized_pnl']:+.2f} | unrealized: ${s['unrealized_pnl']:+.2f} | open lots: {s['open_lots']}")
    log.info(f"Total equity: ${s['total_equity']:.2f} ({(s['total_equity'] / capital - 1) * 100:+.2f}%)")
    return s


# ===================== LIVE =====================
def run_live(args, cfg):
    if not IB_AVAILABLE:
        log.error("ib_insync/ib_async required for live mode.")
        return
    base_sym = args.base.upper()
    letf_sym = args.letf.upper()
    if args.live:
        log.warning("!!! REAL MONEY (leveraged ETF %s) - Type YES to confirm !!!", letf_sym)
        if input("> ").strip().upper() != "YES":
            return
    if args.wait_tws:
        wait_for_tws(args.host, args.port)
    ib = IB()
    account = args.account if args.live else ""
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=15,
               readonly=not args.live, account=account)
    log_account_context(ib, dry_run=not args.live)
    base_c = Stock(base_sym, "SMART", "USD")
    letf_c = Stock(letf_sym, "SMART", "USD")
    ib.qualifyContracts(base_c, letf_c)
    bot = LeveragedPairBot(cfg, get_account_value(ib, account=account))
    log.info("Leveraged bot: signals=%s trade=%s | cash $%.2f", base_sym, letf_sym, bot.portfolio.cash)

    # restart recovery on the LETF position
    shares, avg = get_position(ib, letf_sym, account=account)
    if shares > 0 and avg > 0 and not bot.portfolio.lots:
        from datetime import datetime as _dt
        bot.portfolio.lots.append(Lot(entry_price=avg, qty=shares, entry_time=_dt.utcnow(),
                                      peak_price=avg, limit_price=floor_price(avg, shares, cfg)))
        log.info("Recovered LETF position: %s @ %.2f", shares, avg)

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
                           readonly=not args.live, account=account)
                ib.qualifyContracts(base_c, letf_c)
            b_bars = ib.reqHistoricalData(base_c, "", "5 D", args.bar_size, "TRADES", True, 1)
            l_bars = ib.reqHistoricalData(letf_c, "", "5 D", args.bar_size, "TRADES", True, 1)
            if not b_bars or not l_bars:
                ib.sleep(30); continue
            bdf = util.df(b_bars); bdf["date"] = pd.to_datetime(bdf["date"]); bdf.set_index("date", inplace=True)
            ldf = util.df(l_bars); ldf["date"] = pd.to_datetime(ldf["date"]); ldf.set_index("date", inplace=True)
            base, letf = align_frames(bdf, ldf, cfg)
            if len(base) >= 2 and base.index[-1] != last_bar:
                sig_row = base.iloc[-2]; exe_row = letf.iloc[-2]; sig_ts = base.index[-2]
                current_cash = get_account_value(ib, account=account)
                shares, avg = get_position(ib, letf_sym, account=account)
                if args.live:
                    comm = cfg.get("commission_per_order", 0.0)
                    price = float(exe_row["close"])
                    if bot._pending_buy and shares == 0:
                        available = (current_cash * 0.98 if cfg.get("use_all_cash", True)
                                     else min(cfg["capital_per_lot"], current_cash * 0.95)) - comm
                        qty = int(available // price)
                        if qty >= 1:
                            ib.placeOrder(letf_c, MarketOrder("BUY", qty))
                            log.info("BUY REAL %d %s @ ~$%.2f", qty, letf_sym, price)
                    if shares > 0 and avg > 0:
                        has_sell = any(t.contract.symbol == letf_sym and t.order.action == "SELL"
                                       and t.orderStatus.status in ("PreSubmitted", "Submitted")
                                       for t in ib.openTrades())
                        if not has_sell:
                            lp = round(max(avg * (1 + cfg.get("profit_target_pct", 4.0) / 100),
                                           floor_price(avg, shares, cfg)), 2)
                            ib.placeOrder(letf_c, LimitOrder("SELL", int(shares), lp, tif="GTC"))
                            log.info("GTC SELL %d %s @ %.2f (profit-only)", int(shares), letf_sym, lp)
                bot.step_pair(sig_row, exe_row, sig_ts.to_pydatetime())
                last_bar = base.index[-1]
                if args.once:
                    log.info("One-shot leveraged check complete.")
                    break
            ib.sleep(25)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        ib.disconnect()


# ===================== CLI =====================
def build_parser():
    p = argparse.ArgumentParser(description="Leveraged-ETF day bot: signal on base, trade the 2x wrapper")
    p.add_argument("--mode", choices=["backtest", "trade"], default="backtest")
    p.add_argument("--base", default="NVDA", help="Signal ticker (e.g. NVDA)")
    p.add_argument("--letf", default=None, help="Leveraged ETF to trade (default: PAIRS[base])")
    p.add_argument("--base-file", help="Backtest: base ticker OHLCV CSV")
    p.add_argument("--letf-file", help="Backtest: leveraged ETF OHLCV CSV")
    p.add_argument("--capital", type=float, default=500.0)
    p.add_argument("--profit-target-pct", type=float, default=DEFAULT_CONFIG["profit_target_pct"])
    p.add_argument("--floor-pct", type=float, default=DEFAULT_CONFIG["floor_pct"])
    p.add_argument("--trail-atr-mult", type=float, default=DEFAULT_CONFIG["trail_atr_mult"])
    p.add_argument("--entry-mode", choices=["confirmed", "dip"], default="confirmed")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=9)
    p.add_argument("--account", default="U26942420")
    p.add_argument("--bar-size", default="5 mins")
    p.add_argument("--live", action="store_true")
    p.add_argument("--once", action="store_true")
    p.add_argument("--schedule", action="store_true")
    p.add_argument("--wait-tws", action="store_true")
    return p


def main():
    args = build_parser().parse_args()
    if args.letf is None:
        args.letf = PAIRS.get(args.base.upper())
        if args.letf is None:
            raise SystemExit(f"No leveraged pair known for {args.base}; pass --letf explicitly")
    cfg = DEFAULT_CONFIG.copy()
    cfg.update({
        "entry_mode": args.entry_mode,
        "exit_mode": "adaptive",
        "profit_target_pct": args.profit_target_pct,
        "floor_pct": args.floor_pct,
        "trail_atr_mult": args.trail_atr_mult,
    })
    if args.mode == "backtest":
        if not (args.base_file and args.letf_file):
            raise SystemExit("--base-file and --letf-file required for backtest")
        run_pair_backtest(load_ohlcv_csv(args.base_file), load_ohlcv_csv(args.letf_file),
                          cfg, args.capital)
    else:
        run_live(args, cfg)


if __name__ == "__main__":
    main()
