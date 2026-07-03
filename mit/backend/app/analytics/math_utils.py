from __future__ import annotations

import math
from statistics import NormalDist


def black_scholes_greeks(
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    *,
    is_call: bool,
    rate: float = 0.045,
) -> tuple[float, float, float, float]:
    """Return delta, gamma, vega and theta per share.

    This is a transparent fallback when the selected option-chain provider does not include
    greeks. It is not a volatility-surface model.
    """
    t = max(years, 1 / 365 / 24)
    sigma = max(volatility, 0.01)
    s = max(spot, 1e-9)
    k = max(strike, 1e-9)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (rate + sigma * sigma / 2) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    normal = NormalDist()
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    delta = normal.cdf(d1) if is_call else normal.cdf(d1) - 1
    gamma = pdf / (s * sigma * sqrt_t)
    vega = s * pdf * sqrt_t
    call_theta = -(s * pdf * sigma) / (2 * sqrt_t) - rate * k * math.exp(-rate * t) * normal.cdf(d2)
    if is_call:
        theta = call_theta / 365
    else:
        theta = (
            -(s * pdf * sigma) / (2 * sqrt_t)
            + rate * k * math.exp(-rate * t) * normal.cdf(-d2)
        ) / 365
    return delta, gamma, vega, theta


def linear_zero_crossing(points: list[tuple[float, float]], reference: float) -> float | None:
    points = sorted(points)
    candidates: list[float] = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if y1 == 0:
            candidates.append(x1)
        elif y1 * y2 < 0:
            candidates.append(x1 + (0 - y1) * (x2 - x1) / (y2 - y1))
    return min(candidates, key=lambda x: abs(x - reference)) if candidates else None
