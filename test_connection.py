#!/usr/bin/env python3
"""Test IBKR connection and fetch data for a symbol."""
import logging
import config as cfg
from ib_client import connect, get_history, get_account_value

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def test_connection():
    print(f"Connecting to {cfg.IB_HOST}:{cfg.IB_PORT} (clientId={cfg.IB_CLIENT_ID})...")
    ib = connect(cfg)
    print("✓ Connected!")

    # Test account value
    nav = get_account_value(ib)
    print(f"✓ Net Liquidation: ${nav:,.2f}")

    # Test historical data for a symbol
    symbol = "2134"
    print(f"\nFetching history for {symbol}...")
    df = get_history(ib, symbol, cfg)
    print(f"✓ Got {len(df)} bars")
    print(df.tail(3))

    ib.disconnect()
    print("\n✓ Disconnected")


if __name__ == "__main__":
    test_connection()