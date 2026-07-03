"""
Decision engine.

Entry (trend + pullback):
    - 50 EMA > 200 EMA               (medium-term trend up)
    - price > 200 EMA                (long-term trend up)
    - RSI < RSI_OVERSOLD             (pullback)
    - price at/below the fast EMA    (pullback confirmation)

Exit (laddered profit-taking on the TRADING slice only):
    - as unrealized gain from avg trading cost crosses each rung in
      PROFIT_LADDER, sell that fraction of the trading shares
    - CORE shares are never touched by this logic
    - RSI > RSI_OVERBOUGHT or price far above the fast EMA triggers a full
      trading-slice exit as a safety valve

Buyback:
    - after a pullback from a recent local high while still in an uptrend,
      redeploy into the trading slice
"""
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    action: str            # "BUY" or "SELL"
    reason: str
    fraction: float = 0.0  # for SELL: fraction of trading_shares to sell


def is_uptrend(row: pd.Series) -> bool:
    return bool(row.ema_med > row.ema_slow and row.close > row.ema_slow)


def is_pullback(row: pd.Series, cfg) -> bool:
    return bool(row.rsi < cfg.RSI_OVERSOLD and row.close <= row.ema_fast)


def is_overextended(row: pd.Series, cfg) -> bool:
    stretch = row.close > row.ema_fast + cfg.ATR_TRAIL_MULT * row.atr
    return bool(row.rsi > cfg.RSI_OVERBOUGHT or stretch)


def entry_signal(df: pd.DataFrame, cfg) -> Optional[Signal]:
    row = df.iloc[-1]
    if is_uptrend(row) and is_pullback(row, cfg):
        return Signal("BUY", "uptrend + oversold pullback at fast EMA")
    return None


def exit_signal(df: pd.DataFrame, avg_cost: float, ladder_progress: int, cfg) -> Optional[Signal]:
    row = df.iloc[-1]
    if avg_cost <= 0:
        return None

    gain = (row.close - avg_cost) / avg_cost

    if is_overextended(row, cfg):
        return Signal("SELL", "overbought / overextended safety exit", fraction=1.0)

    if ladder_progress < len(cfg.PROFIT_LADDER):
        trigger_gain, fraction = cfg.PROFIT_LADDER[ladder_progress]
        if gain >= trigger_gain:
            return Signal(
                "SELL",
                f"profit ladder rung {ladder_progress + 1} at +{trigger_gain:.0%}",
                fraction=fraction,
            )

    return None


def rebuy_signal(df: pd.DataFrame, cfg, pullback_pct: float = 0.05) -> Optional[Signal]:
    row = df.iloc[-1]
    recent_high = df["close"].tail(20).max()
    drawdown = (recent_high - row.close) / recent_high
    if is_uptrend(row) and drawdown >= pullback_pct:
        return Signal("BUY", f"buyback after {drawdown:.0%} pullback from recent high")
    return None
