#!/usr/bin/env python3
"""TWS -> stdout price bridge for momentum_bot (C++).
Streams "SYMBOL PRICE EPOCH" lines for the favorite tickers using the live
TWS connection (read-only). The C++ detector consumes this via popen."""

import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

from day_trading_bot import IB, Stock, IB_AVAILABLE  # noqa: E402

FAVORITES = ["TSM", "AMD", "DRAM", "ASML", "SPCX", "TSLA", "NVDA", "NOK",
             "AAPL", "INTC", "TXN", "MU", "GOOGL", "QCOM", "SMH", "SPY", "QQQ"]
HOST, PORT, CLIENT_ID = "127.0.0.1", 7496, 21


def main():
    if not IB_AVAILABLE:
        print("ib_insync missing", file=sys.stderr)
        return 1
    ib = IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15, readonly=True)
    contracts = [Stock(s, "SMART", "USD") for s in FAVORITES]
    ib.qualifyContracts(*contracts)
    tickers = {c.symbol: ib.reqMktData(c, "", False, False) for c in contracts}
    print("bridge connected: %d tickers" % len(tickers), file=sys.stderr)
    try:
        while True:
            ib.sleep(5)
            now = time.time()
            for sym, t in tickers.items():
                px = t.last or t.close or (t.bid + t.ask) / 2 if (t.bid and t.ask) else (t.last or t.close)
                if px and px > 0:
                    sys.stdout.write(f"{sym} {px:.4f} {now:.0f}\n")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        ib.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
