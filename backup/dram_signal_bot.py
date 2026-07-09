#!/usr/bin/env python3
"""
dram_signal_bot.py - DRAM specialist: sounds the alarm when it's time to BUY
or SELL, with its own distinct sounds (different from the fleet's).
=============================================================================
Engine: the SAME validated logic that made +34.9% on real data —
  BUY  = confirmed capitulation reversal (BB 3-sigma + RSI<=25 + volume spike,
         then a green confirmation bar) -> plays sounds/dram_buy.wav
  SELL = adaptive exit fires on the virtual position (target +4% touched,
         trail 3xATR broken, or 15:45 EOD flatten)   -> plays sounds/dram_sell.wav

Data: REAL Yahoo 1m bars (prepost included), polled every 30s, stored via the
price bridge already running. Signals evaluated on completed bars only.
Every alert is logged to trades.db (bot=dram_signal). Runs 24/5 in a loop
that survives errors; RTH gating comes from the engine config itself.

Run:  nohup venv/bin/python dram_signal_bot.py >> dram_signals.log 2>&1 &
Test: venv/bin/python dram_signal_bot.py --replay data/dram_1m_30d.csv
"""

import argparse
import subprocess
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from day_trading_bot import (  # noqa: E402
    DEFAULT_CONFIG, DipAccumulatorBot, TradeLog,
    add_indicators, load_ohlcv_csv,
)

SYMBOL = "DRAM"
POLL_SECONDS = 30
SOUND_BUY = "sounds/dram_buy.wav"
SOUND_SELL = "sounds/dram_sell.wav"


def sound(path):
    try:
        subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass


class DramSignaler:
    """Feeds bars to the validated engine; alerts on virtual buys/sells."""

    def __init__(self, db=None, quiet=False):
        cfg = DEFAULT_CONFIG.copy()          # confirmed entry + adaptive exit
        self.bot = DipAccumulatorBot(cfg, 1000.0)  # virtual $1k book for signals
        self.db = db
        self.quiet = quiet
        self._buys = 0
        self._sells = 0

    def on_bar(self, ts, row):
        self.bot.step(row, ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts)
        p = self.bot.portfolio
        if p.buy_count > self._buys:
            self._buys = p.buy_count
            px = p.lots[-1].entry_price if p.lots else float(row["close"])
            msg = f"[{ts}] *** DRAM: COMPRAR *** @ ~{px:.2f} (capitulacion confirmada)"
            print(msg, flush=True)
            if not self.quiet:
                sound(SOUND_BUY)
            if self.db:
                self.db.trade(ts, SYMBOL, "SIGNAL-BUY", 1, px, reason="confirmed reversal")
        if p.sell_count > self._sells:
            self._sells = p.sell_count
            px = float(row["close"])
            msg = f"[{ts}] *** DRAM: VENDER *** @ ~{px:.2f} (exit adaptativo: target/trail/EOD)"
            print(msg, flush=True)
            if not self.quiet:
                sound(SOUND_SELL)
            if self.db:
                self.db.trade(ts, SYMBOL, "SIGNAL-SELL", 1, px, reason="adaptive exit")


def replay(path):
    """Backtest the alert stream on saved real data (no sounds)."""
    df = add_indicators(load_ohlcv_csv(path), DEFAULT_CONFIG.copy())
    sig = DramSignaler(quiet=True)
    for ts, row in df.iterrows():
        sig.on_bar(ts, row)
    print(f"replay {path}: {sig._buys} señales de COMPRA, {sig._sells} de VENTA")


def live():
    import yfinance as yf
    db = TradeLog(bot="dram_signal", mode="live")
    sig = DramSignaler(db=db)
    print(f"DRAM signal bot vivo | poll {POLL_SECONDS}s | buy={SOUND_BUY} sell={SOUND_SELL}",
          flush=True)
    seen_last = None
    while True:
        try:
            df = yf.Ticker(SYMBOL).history(period="2d", interval="1m", prepost=True)
            if not df.empty and len(df) >= 30:
                df = df.reset_index()
                df.columns = [str(c).lower() for c in df.columns]
                df = df.rename(columns={"datetime": "date"}).set_index("date")
                df = add_indicators(df[["open", "high", "low", "close", "volume"]],
                                    DEFAULT_CONFIG.copy())
                # process only NEW completed bars (exclude the forming one)
                completed = df.iloc[:-1]
                new = completed if seen_last is None else completed[completed.index > seen_last]
                for ts, row in new.iterrows():
                    sig.on_bar(ts, row)
                if len(completed):
                    seen_last = completed.index[-1]
        except Exception as e:
            print(f"error: {str(e)[:80]}", flush=True)
        time.sleep(POLL_SECONDS)


def main():
    ap = argparse.ArgumentParser(description="DRAM buy/sell sound signaler")
    ap.add_argument("--replay", help="CSV real para verificar señales (sin sonido)")
    args = ap.parse_args()
    if args.replay:
        replay(args.replay)
    else:
        live()


if __name__ == "__main__":
    main()
