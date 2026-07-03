import logging

from ib_insync import IB, Stock, MarketOrder, LimitOrder

log = logging.getLogger("ib-trader.execution")


def make_contract(symbol: str, exchange: str, currency: str) -> Stock:
    return Stock(symbol, exchange, currency)


def place_order(
    ib: IB,
    contract,
    side: str,
    quantity: int,
    dry_run: bool,
    order_type: str = "MARKET",
    limit_price: float = None,
):
    if quantity <= 0:
        log.info("Skipping zero-quantity order for %s", contract.symbol)
        return None

    if dry_run:
        log.info("[DRY RUN] Would %s %d %s (%s)", side, quantity, contract.symbol, order_type)
        return {"dry_run": True, "side": side, "quantity": quantity, "symbol": contract.symbol}

    if order_type == "LIMIT" and limit_price:
        order = LimitOrder(side, quantity, limit_price)
    else:
        order = MarketOrder(side, quantity)

    trade = ib.placeOrder(contract, order)
    log.info("Submitted LIVE order: %s %d %s", side, quantity, contract.symbol)
    return trade
