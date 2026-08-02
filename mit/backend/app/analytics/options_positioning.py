from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
import math

import numpy as np

from backend.app.analytics.math_utils import black_scholes_greeks, linear_zero_crossing
from backend.app.domain import DealerPositioning, MagnetLevel, OptionContract

CONTRACT_MULTIPLIER = 100
MATRIX_BAND = 0.12  # heatmap: strikes dentro de +/-12% del spot (donde vive la gamma)


def _greeks(contract: OptionContract, spot: float) -> tuple[float, float]:
    if contract.delta is not None and contract.gamma is not None:
        return contract.delta, contract.gamma
    mid_iv = contract.implied_volatility or 0.35
    days = max((contract.expiration - date.today()).days, 1)
    delta, gamma, _, _ = black_scholes_greeks(
        spot,
        contract.strike,
        days / 365,
        mid_iv,
        is_call=contract.option_type == "call",
    )
    return delta, gamma


def analyze_dealer_positioning(
    symbol: str, spot: float, chain: list[OptionContract]
) -> DealerPositioning:
    if not chain:
        return DealerPositioning(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            spot=spot,
            net_gex=0,
            net_dex=0,
            gamma_regime="UNKNOWN",
            caveats=["No option chain returned by selected provider."],
        )

    gex_by_strike: dict[float, float] = defaultdict(float)
    call_oi: dict[float, float] = defaultdict(float)
    put_oi: dict[float, float] = defaultdict(float)
    net_gex = 0.0
    net_dex = 0.0

    for contract in chain:
        delta, gamma = _greeks(contract, spot)
        # Scenario proxy: calls positive, puts negative. Actual dealer inventory direction is
        # not observable from open interest alone; vendor dealer-positioning fields are better.
        sign = 1 if contract.option_type == "call" else -1
        gex = sign * gamma * contract.open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01
        dex = delta * contract.open_interest * CONTRACT_MULTIPLIER * spot
        gex_by_strike[contract.strike] += gex
        net_gex += gex
        net_dex += dex
        if contract.option_type == "call":
            call_oi[contract.strike] += contract.open_interest
        else:
            put_oi[contract.strike] += contract.open_interest

    call_wall = max(call_oi, key=call_oi.get) if call_oi else None
    put_wall = max(put_oi, key=put_oi.get) if put_oi else None
    max_pain = _max_pain(chain)
    expected_move = _expected_move(spot, chain)
    gamma_flip = _gamma_flip(spot, chain)

    total_abs = sum(abs(value) for value in gex_by_strike.values()) or 1
    magnets: list[MagnetLevel] = []
    for label, price, kind in (
        ("Call wall", call_wall, "resistance"),
        ("Put wall", put_wall, "support"),
        ("Gamma flip", gamma_flip, "regime"),
        ("Max pain", max_pain, "pin"),
    ):
        if price is None:
            continue
        local = abs(gex_by_strike.get(float(price), 0)) / total_abs
        proximity = 1 / (1 + abs(price / spot - 1) * 25)
        magnets.append(
            MagnetLevel(label=label, price=float(price), strength=round(local + proximity, 4), kind=kind)
        )
    magnets.sort(key=lambda item: item.strength, reverse=True)

    return DealerPositioning(
        symbol=symbol.upper(),
        timestamp=datetime.now(UTC),
        spot=spot,
        net_gex=net_gex,
        net_dex=net_dex,
        gamma_regime="POSITIVE / DAMPENING" if net_gex >= 0 else "NEGATIVE / AMPLIFYING",
        gamma_flip=gamma_flip,
        call_wall=call_wall,
        put_wall=put_wall,
        max_pain=max_pain,
        expected_move=expected_move,
        magnets=magnets[:8],
        gex_by_strike={f"{strike:g}": value for strike, value in sorted(gex_by_strike.items())},
        caveats=[
            "Open-interest signs are a dealer-positioning scenario proxy, not observed dealer inventory.",
            "Gamma flip is repriced with a flat-IV Black-Scholes approximation when vendor scenario data is unavailable.",
        ],
    )


def _cell_greeks(contract: OptionContract, spot: float) -> tuple[float, float]:
    """Return (gamma, vega) using provider values, BS fallback when a greek is missing."""
    gamma = contract.gamma
    vega = contract.vega
    if gamma is not None and vega is not None:
        return gamma, vega
    mid_iv = contract.implied_volatility or 0.35
    days = max((contract.expiration - date.today()).days, 1)
    _, bs_gamma, bs_vega, _ = black_scholes_greeks(
        spot, contract.strike, days / 365, mid_iv, is_call=contract.option_type == "call"
    )
    return (gamma if gamma is not None else bs_gamma, vega if vega is not None else bs_vega)


def compute_option_matrix(
    symbol: str, spot: float, chain: list[OptionContract], *, metric: str = "gex"
) -> dict:
    """Per-(strike,expiration) GEX or VEX matrix. House sign: call +, put - (matches analyze_dealer_positioning).

    Fail-loud: a strike×expiry with no contracts is omitted from `cells` (renders blank);
    a real measured 0 stays as 0. Never fabricates a value for absent data."""
    if metric not in {"gex", "vex"}:
        raise ValueError(f"Unknown metric: {metric}")
    # Banda ±MATRIX_BAND del spot: centra el mapa donde vive la gamma (como SpotGamma/opt_chain);
    # fuera de la banda es ruido ~0 que sepulta el color cerca del dinero.
    lo, hi = (spot * (1 - MATRIX_BAND), spot * (1 + MATRIX_BAND)) if spot > 0 else (0.0, 1e12)
    cells: dict[str, float] = {}
    expirations: set[date] = set()
    strikes: set[float] = set()
    for contract in chain:
        if not (lo <= contract.strike <= hi):
            continue
        # Fail-loud: SOLO griegas MEDIDAS. Si falta la que toca, se OMITE (celda en blanco);
        # jamas reconstruir con IV plana (eso convierte "no se" en un numero inventado).
        greek = contract.gamma if metric == "gex" else contract.vega
        if greek is None:
            continue
        sign = 1 if contract.option_type == "call" else -1
        oi = contract.open_interest
        if metric == "gex":
            value = sign * greek * oi * CONTRACT_MULTIPLIER * spot * spot * 0.01
        else:  # vex: vega notional per 1-vol move
            value = sign * greek * oi * CONTRACT_MULTIPLIER
        key = f"{contract.strike:g}|{contract.expiration.isoformat()}"
        cells[key] = cells.get(key, 0.0) + value
        expirations.add(contract.expiration)
        strikes.add(contract.strike)

    max_cell = None
    if cells:
        top_key = max(cells, key=lambda k: abs(cells[k]))
        top_strike, top_expiry = top_key.split("|")
        max_cell = {"strike": float(top_strike), "expiration": top_expiry, "value": cells[top_key]}

    return {
        "symbol": symbol.upper(),
        "metric": metric,
        "spot": spot,
        "expirations": [d.isoformat() for d in sorted(expirations)],
        "strikes": [float(f"{s:g}") for s in sorted(strikes, reverse=True)],
        "cells": cells,
        "max_cell": max_cell,
        "caveats": [
            "Open-interest signs are a dealer-positioning scenario proxy, not observed dealer inventory.",
            "Only MEASURED greeks: strikes without provider gamma/vega are omitted (blank), never reconstructed.",
            f"Strikes banded to +/-{int(MATRIX_BAND*100)}% of spot.",
        ],
    }


def compute_trace_matrix(
    symbol: str, spot: float, chain: list[OptionContract], *, metric: str = "gex"
) -> dict:
    """SpotGamma-TRACE-style per-strike metric (GEX or Net OI). House sign: call +, put -.

    The metric varies slowly intraday, so the frontend paints one current value per strike
    across the whole time axis (no history archive in v1). Fail-loud: GEX omits strikes with
    no MEASURED gamma (never reconstructs); empty chain yields empty by_strike."""
    if metric not in {"gex", "netoi"}:
        raise ValueError(f"Unknown metric: {metric}")
    lo, hi = (spot * (1 - MATRIX_BAND), spot * (1 + MATRIX_BAND)) if spot > 0 else (0.0, 1e12)
    by_strike: dict[float, float] = defaultdict(float)
    for contract in chain:
        if not (lo <= contract.strike <= hi):
            continue
        sign = 1 if contract.option_type == "call" else -1
        if metric == "gex":
            if contract.gamma is None:  # fail-loud: measured greeks only, no IV reconstruction
                continue
            value = sign * contract.gamma * contract.open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01
        else:  # netoi: net open interest, calls +, puts -
            value = sign * contract.open_interest
        by_strike[contract.strike] += value

    dealer = analyze_dealer_positioning(symbol, spot, chain)
    strikes = sorted(by_strike.keys(), reverse=True)
    return {
        "symbol": symbol.upper(),
        "metric": metric,
        "spot": spot,
        "strikes": [float(f"{s:g}") for s in strikes],
        "by_strike": {f"{s:g}": by_strike[s] for s in strikes},
        "levels": {
            "call_wall": dealer.call_wall,
            "put_wall": dealer.put_wall,
            "gamma_flip": dealer.gamma_flip,
            "max_pain": dealer.max_pain,
        },
        "caveats": [
            "Per-strike metric is the current snapshot painted across the whole time axis (no intraday history in v1).",
            "Open-interest signs are a dealer-positioning scenario proxy, not observed dealer inventory.",
            (
                "GEX uses MEASURED greeks only; strikes without provider gamma are omitted."
                if metric == "gex"
                else "Net OI = sum(open interest) per strike, calls +, puts -."
            ),
            f"Strikes banded to +/-{int(MATRIX_BAND * 100)}% of spot.",
        ],
    }


def _max_pain(chain: list[OptionContract]) -> float | None:
    strikes = sorted({contract.strike for contract in chain})
    if not strikes:
        return None
    pain: dict[float, float] = {}
    for settlement in strikes:
        total = 0.0
        for contract in chain:
            intrinsic = (
                max(0, settlement - contract.strike)
                if contract.option_type == "call"
                else max(0, contract.strike - settlement)
            )
            total += intrinsic * contract.open_interest * CONTRACT_MULTIPLIER
        pain[settlement] = total
    return min(pain, key=pain.get)


def _expected_move(spot: float, chain: list[OptionContract]) -> float | None:
    expiries = sorted({contract.expiration for contract in chain if contract.expiration >= date.today()})
    if not expiries:
        return None
    expiry = expiries[0]
    near = sorted(
        (c for c in chain if c.expiration == expiry), key=lambda c: abs(c.strike - spot)
    )
    calls = [c for c in near if c.option_type == "call"]
    puts = [c for c in near if c.option_type == "put"]
    if not calls or not puts:
        return None
    call, put = calls[0], puts[0]
    call_mid = (call.bid + call.ask) / 2 if call.ask else call.last
    put_mid = (put.bid + put.ask) / 2 if put.ask else put.last
    return call_mid + put_mid


def _gamma_flip(spot: float, chain: list[OptionContract]) -> float | None:
    lower, upper = spot * 0.72, spot * 1.28
    grid = np.linspace(lower, upper, 81)
    points: list[tuple[float, float]] = []
    for scenario_spot in grid:
        total = 0.0
        for contract in chain:
            days = max((contract.expiration - date.today()).days, 1)
            _, gamma, _, _ = black_scholes_greeks(
                scenario_spot,
                contract.strike,
                days / 365,
                contract.implied_volatility or 0.35,
                is_call=contract.option_type == "call",
            )
            sign = 1 if contract.option_type == "call" else -1
            total += sign * gamma * contract.open_interest * CONTRACT_MULTIPLIER * scenario_spot**2 * 0.01
        points.append((float(scenario_spot), total))
    return linear_zero_crossing(points, spot)
