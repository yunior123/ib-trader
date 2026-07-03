def shares_from_risk(account_value: float, atr_value: float, risk_pct: float, atr_mult: float = 2.0) -> int:
    """Volatility-adjusted position size: risk a fixed % of account equity per
    trade, with the stop distance set to atr_mult * ATR. Wider ATR -> smaller
    size; tighter ATR -> larger size."""
    if atr_value <= 0:
        return 0
    risk_dollars = account_value * risk_pct
    stop_distance = atr_value * atr_mult
    return max(int(risk_dollars / stop_distance), 0)


def cap_to_max_position(qty: int, price: float, account_value: float, max_pct: float) -> int:
    """Hard ceiling so a single volatile name can't dominate the book."""
    if price <= 0:
        return 0
    max_dollars = account_value * max_pct
    max_shares = int(max_dollars / price)
    return max(min(qty, max_shares), 0)
