"""
IB Trader - main loop.

READ BEFORE RUNNING:
  1. Starts in DRY_RUN mode (config.py). No live orders are sent while
     DRY_RUN=True - every decision is only logged and written to trades.db.
  2. Before ever setting DRY_RUN=False, test for an extended period against
     a PAPER TRADING account (TWS port 7497 or IB Gateway port 4002), never
     straight to a live account.
  3. This is a rules-based heuristic system, not a guarantee of profit.
     Trend-following rules can lose money in choppy or reversing markets.
  4. Whoever runs this against a live account is responsible for monitoring
     it. Nothing here should be mistaken for financial advice.
"""
import logging

import config as cfg
from logger import setup_logging
from ib_client import connect, get_history, get_account_value
from indicators import add_indicators
from strategy import entry_signal, exit_signal, rebuy_signal
from risk import shares_from_risk, cap_to_max_position
from execution import make_contract, place_order
from portfolio import PortfolioState
from database import TradeDB

log = logging.getLogger("ib-trader.main")


def process_symbol(ib, symbol, state: PortfolioState, db: TradeDB):
    df = add_indicators(get_history(ib, symbol, cfg), cfg)
    row = df.iloc[-1]
    sym_state = state.get(symbol)
    account_value = get_account_value(ib)
    contract = make_contract(symbol, cfg.EXCHANGE, cfg.CURRENCY)

    total_shares = sym_state.core_shares + sym_state.trading_shares

    # --- No position yet: look for a fresh entry ---
    if total_shares == 0:
        sig = entry_signal(df, cfg)
        if sig:
            qty = shares_from_risk(account_value, row.atr, cfg.ACCOUNT_RISK_PER_TRADE, cfg.ATR_TRAIL_MULT)
            qty = cap_to_max_position(qty, row.close, account_value, cfg.MAX_POSITION_PCT_OF_NAV)
            if qty > 0:
                core_qty = int(qty * cfg.CORE_FRACTION)
                trading_qty = qty - core_qty
                place_order(ib, contract, "BUY", qty, cfg.DRY_RUN)
                db.log_trade(symbol, "BUY", qty, sig.reason, cfg.DRY_RUN)
                sym_state.core_shares = core_qty
                sym_state.trading_shares = trading_qty
                sym_state.avg_cost = row.close
                sym_state.ladder_progress = 0
                state.save()
        else:
            log.info("%s: no entry signal (uptrend=%s rsi=%.1f)", symbol, row.ema_med > row.ema_slow, row.rsi)
        return

    # --- Already holding: look for laddered profit-taking / safety exit ---
    sig = exit_signal(df, sym_state.avg_cost, sym_state.ladder_progress, cfg)
    if sig and sym_state.trading_shares > 0:
        sell_qty = int(sym_state.trading_shares * sig.fraction)
        if sell_qty > 0:
            place_order(ib, contract, "SELL", sell_qty, cfg.DRY_RUN)
            db.log_trade(symbol, "SELL", sell_qty, sig.reason, cfg.DRY_RUN)
            sym_state.trading_shares -= sell_qty
            sym_state.ladder_progress += 1
            state.save()
        return

    # --- Otherwise look for a buyback opportunity to redeploy realized cash ---
    sig = rebuy_signal(df, cfg)
    if sig:
        qty = shares_from_risk(account_value, row.atr, cfg.ACCOUNT_RISK_PER_TRADE, cfg.ATR_TRAIL_MULT)
        qty = cap_to_max_position(qty, row.close, account_value, cfg.MAX_POSITION_PCT_OF_NAV)
        if qty > 0:
            place_order(ib, contract, "BUY", qty, cfg.DRY_RUN)
            db.log_trade(symbol, "BUY", qty, sig.reason, cfg.DRY_RUN)
            sym_state.trading_shares += qty
            sym_state.ladder_progress = max(sym_state.ladder_progress - 1, 0)
            state.save()


def main():
    setup_logging()
    log.info("Starting IB trader | DRY_RUN=%s | symbols=%s", cfg.DRY_RUN, cfg.SYMBOLS)

    ib = connect(cfg)
    state = PortfolioState()
    db = TradeDB()

    try:
        while True:
            for symbol in cfg.SYMBOLS:
                try:
                    process_symbol(ib, symbol, state, db)
                except Exception:
                    log.exception("Error processing %s", symbol)
            ib.sleep(cfg.POLL_SECONDS)
    except KeyboardInterrupt:
        log.info("Shutting down (KeyboardInterrupt)")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
