from __future__ import annotations

from backend.app.domain import BookAnalytics, OrderBook


def analyze_order_book(book: OrderBook) -> BookAnalytics:
    bids = book.bids
    asks = book.asks
    if not bids or not asks:
        return BookAnalytics(symbol=book.symbol, timestamp=book.timestamp)
    best_bid, best_ask = bids[0], asks[0]
    spread = max(0.0, best_ask.price - best_bid.price)
    top_total = best_bid.size + best_ask.size
    microprice = (
        (best_ask.price * best_bid.size + best_bid.price * best_ask.size) / top_total
        if top_total > 0
        else (best_bid.price + best_ask.price) / 2
    )
    bid_size = sum(level.size for level in bids)
    ask_size = sum(level.size for level in asks)
    total = bid_size + ask_size
    imbalance = (bid_size - ask_size) / total if total else 0
    bid_wall = max(bids, key=lambda level: level.size)
    ask_wall = max(asks, key=lambda level: level.size)
    return BookAnalytics(
        symbol=book.symbol,
        timestamp=book.timestamp,
        spread=spread,
        microprice=microprice,
        imbalance=imbalance,
        bid_wall=bid_wall.price,
        ask_wall=ask_wall.price,
        bid_wall_size=bid_wall.size,
        ask_wall_size=ask_wall.size,
    )
