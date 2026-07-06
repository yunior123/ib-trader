#!/usr/bin/env python3
"""Local DRAM backtest sweeps against saved OHLCV data."""

from itertools import product
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dram_dip_bot import DEFAULT_CONFIG, DipAccumulatorBot, add_indicators, load_ohlcv_csv, log


def simulate(df: pd.DataFrame, cfg: dict, capital: float = 70.0) -> dict:
    data = add_indicators(df, cfg)
    bot = DipAccumulatorBot(cfg, capital)
    buys = 0
    sells = 0
    max_open_lot_dd_pct = 0.0
    equity_curve = []
    prev_lots = 0
    prev_realized = 0.0

    for ts, row in data.iterrows():
        bot.step(row, ts.to_pydatetime())
        if len(bot.portfolio.lots) > prev_lots:
            buys += len(bot.portfolio.lots) - prev_lots
        if bot.portfolio.realized_pnl > prev_realized:
            sells += 1
        prev_lots = len(bot.portfolio.lots)
        prev_realized = bot.portfolio.realized_pnl

        for lot in bot.portfolio.lots:
            drawdown = (row.close - lot.entry_price) / lot.entry_price * 100
            max_open_lot_dd_pct = min(max_open_lot_dd_pct, drawdown)
        equity_curve.append(bot.portfolio.total_equity(row.close))

    summary = bot.summary(data.iloc[-1].close)
    peak = capital
    max_equity_dd_pct = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        max_equity_dd_pct = min(max_equity_dd_pct, (equity / peak - 1) * 100)

    return {
        "equity": float(summary["total_equity"]),
        "return_pct": float((summary["total_equity"] / capital - 1) * 100),
        "realized": float(summary["realized_pnl"]),
        "unrealized": float(summary["unrealized_pnl"]),
        "open_lots": int(summary["open_lots"]),
        "buys": buys,
        "sells": sells,
        "max_open_lot_dd_pct": max_open_lot_dd_pct,
        "max_equity_dd_pct": max_equity_dd_pct,
    }


def append_price_path(df: pd.DataFrame, closes: list[float]) -> pd.DataFrame:
    rows = []
    start = df.index[-1]
    for i, close in enumerate(closes, start=1):
        rows.append(
            {
                "date": start + pd.Timedelta(days=i),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": int(df["volume"].tail(20).mean()),
            }
        )
    extra = pd.DataFrame(rows).set_index("date")
    return pd.concat([df, extra])


def main():
    log.setLevel("ERROR")
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/dram_15m.csv")
    df = load_ohlcv_csv(str(data_path))

    print(f"data={data_path} bars={len(df)} from={df.index.min().date()} to={df.index.max().date()}")
    print(f"buy_hold_return_pct={(df.close.iloc[-1] / df.close.iloc[0] - 1) * 100:.2f}")
    print(f"worst_daily_pct={df.close.pct_change().min() * 100:.2f}")
    print(f"max_close_drawdown_pct={(df.close / df.close.cummax() - 1).min() * 100:.2f}")

    default_metrics = simulate(df, DEFAULT_CONFIG.copy())
    print("default", default_metrics)

    results = []
    for bb_std, rsi, vol_mult, profit, cooldown in product(
        [1.0, 1.25, 1.5, 2.0],
        [35, 45, 55, 65],
        [0.8, 1.0, 1.2],
        [1.0, 2.0, 3.0],
        [1, 3, 5],
    ):
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(
            {
                "bb_std": bb_std,
                "rsi_oversold": rsi,
                "volume_mult": vol_mult,
                "min_profit_pct": profit,
                "buy_cooldown_bars": cooldown,
            }
        )
        metrics = simulate(df, cfg)
        if metrics["buys"]:
            results.append((metrics["return_pct"], bb_std, rsi, vol_mult, profit, cooldown, metrics))

    results.sort(reverse=True, key=lambda item: item[0])
    print(f"configs_with_trades={len(results)}")
    for _, bb_std, rsi, vol_mult, profit, cooldown, metrics in results[:10]:
        print(
            "sweep",
            {
                "bb_std": bb_std,
                "rsi": rsi,
                "volume_mult": vol_mult,
                "profit": profit,
                "cooldown": cooldown,
                **metrics,
            },
        )

    stress_cfg = DEFAULT_CONFIG.copy()
    stress_cfg.update({"bb_std": 1.0, "rsi_oversold": 55, "volume_mult": 0.8})
    for label, closes in {
        "rebound_5pct": [df.close.iloc[-1] * 1.05],
        "drop_10pct": [df.close.iloc[-1] * 0.90],
        "drop_25pct": [df.close.iloc[-1] * 0.75],
        "drop_40pct": [df.close.iloc[-1] * 0.60],
    }.items():
        print(f"stress_{label}", simulate(append_price_path(df, closes), stress_cfg))


if __name__ == "__main__":
    main()
