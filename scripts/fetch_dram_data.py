#!/usr/bin/env python3
"""Fetch real DRAM OHLCV data from Yahoo Finance and save CSVs for local backtests.

Outputs (in data/):
  dram_15m.csv    - 15-min bars, ~60 days (matches the live bot's bar size)
  dram_daily.csv  - daily bars, up to 2 years (DRAM listed 2026-04-02)

Uses yfinance, which handles Yahoo's cookie/crumb auth and browser
impersonation. Raw urllib/requests calls to the chart API get HTTP 429.

Usage:
  venv/bin/python scripts/fetch_dram_data.py [SYMBOL]
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "DRAM"


def save(df: pd.DataFrame, name: str) -> None:
    """Normalize a yfinance history frame to the bot's OHLCV CSV format."""
    df = df.reset_index()
    df.columns = [
        str(c[0]).lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns
    ]
    tscol = "datetime" if "datetime" in df.columns else "date"
    out = df.rename(columns={tscol: "date"})[
        ["date", "open", "high", "low", "close", "volume"]
    ].dropna()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    out.to_csv(path, index=False)
    print(
        f"saved {path} | bars={len(out)} "
        f"from={out['date'].iloc[0]} to={out['date'].iloc[-1]} "
        f"last_close={out['close'].iloc[-1]:.2f}"
    )


def main() -> None:
    ticker = yf.Ticker(SYMBOL)
    prefix = SYMBOL.lower()

    print(f"Fetching {SYMBOL} 15m bars (60d)...")
    df_15m = ticker.history(period="60d", interval="15m", prepost=False)
    if df_15m.empty:
        raise RuntimeError(f"No 15m data returned for {SYMBOL}")
    save(df_15m, f"{prefix}_15m.csv")

    print(f"Fetching {SYMBOL} daily bars (2y)...")
    df_daily = ticker.history(period="2y", interval="1d")
    if df_daily.empty:
        raise RuntimeError(f"No daily data returned for {SYMBOL}")
    save(df_daily, f"{prefix}_daily.csv")


if __name__ == "__main__":
    main()
