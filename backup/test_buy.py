#!/usr/bin/env python3
"""Test buy 1 share of CUPR."""
import config as cfg
from ib_client import connect, get_account_value
from execution import make_contract, place_order

cfg.DRY_RUN = False  # Set to True to test without real orders

def main():
    ib = connect(cfg)
    nav = get_account_value(ib)
    print(f"Net Liquidation: ${nav:,.2f}")

    contract = make_contract("CUPR", cfg.EXCHANGE, cfg.CURRENCY)
    ib.qualifyContracts(contract)
    print(f"Contract: {contract}")

    # Place buy order for 1 share
    place_order(ib, contract, "BUY", 1, cfg.DRY_RUN)
    print(f"Order placed (DRY_RUN={cfg.DRY_RUN})")

    ib.disconnect()

if __name__ == "__main__":
    main()