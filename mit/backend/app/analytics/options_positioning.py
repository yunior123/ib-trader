from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
import json
import math
import os
from pathlib import Path

import numpy as np

from backend.app.analytics.math_utils import black_scholes_greeks, linear_zero_crossing
from backend.app.domain import DealerPositioning, MagnetLevel, OptionContract

CONTRACT_MULTIPLIER = 100
FLAT_IV_FALLBACK = 0.35  # IV plana de respaldo: se USA pero se DECLARA (ver caveats)
MATRIX_BAND = 0.12  # heatmap: strikes dentro de +/-12% del spot (donde vive la gamma)
TRACE_CUBE_DIR_ENV = "MIT_TRACE_CUBE_DIR"
TRACE_CUBE_MAX_AGE_ENV = "MIT_TRACE_CUBE_MAX_AGE_MIN"  # si se define, SUSTITUYE la regla de sesion
SESSION_START_ENV = "MIT_SESSION_START_HHMM"
DEFAULT_SESSION_START = "0400"  # premercado ET: a esa hora el cubo de ayer ya no describe hoy


def trace_cube_dir() -> Path:
    """data/ del repo ib-trader (donde scripts/trace_cube.py escribe), override por env."""
    override = os.environ.get(TRACE_CUBE_DIR_ENV)
    return Path(override) if override else Path(__file__).resolve().parents[4] / "data"


def current_session_date(now: datetime | None = None) -> date:
    """Sesion de mercado VIGENTE en hora local: hoy si es dia habil y ya empezo el premercado,
    si no el ultimo dia habil. Sin calendario de festivos a proposito: un festivo no deja cubo
    y el panel cae a flat_current (degradacion segura; nunca pinta la sesion de otro dia)."""
    now = now or datetime.now()
    raw = os.environ.get(SESSION_START_ENV) or DEFAULT_SESSION_START
    if len(raw) != 4 or not raw.isdigit():
        raise ValueError(f"{SESSION_START_ENV} debe ser HHMM, no {raw!r}")
    start = int(raw[:2]) * 60 + int(raw[2:])
    day = now.date()
    if day.weekday() < 5 and now.hour * 60 + now.minute >= start:
        return day
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _cube_is_current(meta: dict, now: datetime | None = None) -> bool:
    """Un cubo de otra sesion BORRA las velas vivas del panel (el orquestador recorta las barras
    a la ventana de epochs del cubo) y encima se anuncia 'measured': se rechaza."""
    now = now or datetime.now()
    max_age = os.environ.get(TRACE_CUBE_MAX_AGE_ENV)
    if max_age:
        generated = meta.get("generated_epoch")
        if not isinstance(generated, (int, float)) or isinstance(generated, bool):
            return False
        return (now.timestamp() - float(generated)) <= float(max_age) * 60
    return meta.get("date") == current_session_date(now).isoformat()


def read_trace_cube(symbol: str, *, base_dir: str | Path | None = None) -> dict | None:
    """Cubo strike×tiempo de scripts/trace_cube.py, o None si no existe/no es utilizable.
    None significa 'no hay eje de tiempo medido' y el llamador lo DECLARA (time_axis)."""
    root = Path(base_dir) if base_dir is not None else trace_cube_dir()
    path = root / f"trace_cube_{symbol.lower()}.json"
    if not path.is_file():
        return None
    try:
        cube = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    meta = cube.get("meta") or {}
    if not isinstance(cube.get("cells"), dict) or not meta.get("epochs"):
        return None
    if not _cube_is_current(meta):
        return None
    return cube


def _greeks(contract: OptionContract, spot: float) -> tuple[float, float]:
    if contract.delta is not None and contract.gamma is not None:
        return contract.delta, contract.gamma
    mid_iv = contract.implied_volatility or FLAT_IV_FALLBACK
    days = max((contract.expiration - date.today()).days, 1)
    delta, gamma, _, _ = black_scholes_greeks(
        spot,
        contract.strike,
        days / 365,
        mid_iv,
        is_call=contract.option_type == "call",
    )
    return delta, gamma


WALL_BAND = MATRIX_BAND  # los muros viven en la misma ventana que el mapa: fuera no se dibujan


def _walls(spot, call_gamma, put_gamma, call_oi, put_oi):
    """Call wall ARRIBA del spot, put wall ABAJO, ambos dentro de la banda del mapa, y por GAMMA
    medida cuando la hay (OI solo como respaldo). Devuelve (call_wall, put_wall, fuente).

    Por que: tomabamos `max(call_oi)`/`max(put_oi)` sobre la cadena ENTERA, sin lado ni banda.
    Medido 2026-08-02 con SPY a 744,27: put_wall = 360 (OI 26.722 de un tail hedge lejano) = -51,6%
    del spot, dibujado en el panel como "soporte", frente al 710 real. El vendor de referencia
    (support.spotgamma.com) define el muro por GAMMA NETA y toma "el call wall por ENCIMA del precio
    y el put wall por DEBAJO"; nuestro propio gex_core (la flota) ya lo hace por gamma.
    """
    if spot <= 0:
        return (None, None, "sin_spot")
    lo, hi = spot * (1 - WALL_BAND), spot * (1 + WALL_BAND)

    def pick(fuente, arriba):
        cand = {k: v for k, v in fuente.items()
                if v > 0 and lo <= k <= hi and (k >= spot if arriba else k <= spot)}
        return max(cand, key=cand.get) if cand else None

    cw, pw = pick(call_gamma, True), pick(put_gamma, False)
    if cw is not None or pw is not None:
        # gamma medida en al menos un lado; el que falte cae a OI y se etiqueta como mixto
        src = "gamma"
        if cw is None:
            cw, src = pick(call_oi, True), "mixto_gamma_oi"
        if pw is None:
            pw, src = pick(put_oi, False), "mixto_gamma_oi"
        return (cw, pw, src)
    return (pick(call_oi, True), pick(put_oi, False), "oi")


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

    reconstruidos = 0   # contratos cuya gamma sale de una IV INVENTADA (0.35), no medida
    gex_by_strike: dict[float, float] = defaultdict(float)
    call_oi: dict[float, float] = defaultdict(float)
    put_oi: dict[float, float] = defaultdict(float)
    call_gamma: dict[float, float] = defaultdict(float)
    put_gamma: dict[float, float] = defaultdict(float)
    net_gex = 0.0
    net_dex = 0.0

    for contract in chain:
        if contract.delta is None or contract.gamma is None:
            reconstruidos += 1
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
            if contract.gamma is not None:
                call_gamma[contract.strike] += contract.gamma * contract.open_interest
        else:
            put_oi[contract.strike] += contract.open_interest
            if contract.gamma is not None:
                put_gamma[contract.strike] += contract.gamma * contract.open_interest

    call_wall, put_wall, wall_src = _walls(spot, call_gamma, put_gamma, call_oi, put_oi)
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
            f"Walls: source={wall_src}, call above spot / put below, both within ±{WALL_BAND:.0%} "
            "of spot — a strike outside that window is not a tradable wall.",
            # net_gex, el titular POSITIVE/NEGATIVE y el flip se calculan con estas griegas: si una
            # parte viene de una IV inventada (0.35 plano), hay que decir CUANTA.
            f"Greeks: {len(chain) - reconstruidos}/{len(chain)} measured; "
            f"{reconstruidos} reconstructed with a flat {FLAT_IV_FALLBACK:g} IV "
            f"({reconstruidos / len(chain):.0%} of the chain) — regime and flip inherit that.",
        ],
    )


def _cell_greeks(contract: OptionContract, spot: float) -> tuple[float, float]:
    """Return (gamma, vega) using provider values, BS fallback when a greek is missing."""
    gamma = contract.gamma
    vega = contract.vega
    if gamma is not None and vega is not None:
        return gamma, vega
    mid_iv = contract.implied_volatility or FLAT_IV_FALLBACK
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


def _trace_time_axis(cube: dict, metric: str) -> dict | None:
    """Columnas MEDIDAS del cubo para una metrica. None si el cubo no tiene esa metrica."""
    cells = (cube.get("cells") or {}).get(metric)
    if not isinstance(cells, dict) or not cells:
        return None
    meta = cube["meta"]
    epochs = meta["epochs"]
    labels = meta.get("labels") or [""] * len(epochs)
    spots = meta.get("spots") or [None] * len(epochs)
    greeks = meta.get("greeks_ok_pct") or [None] * len(epochs)
    filled = {int(key.rsplit("|", 1)[1]) for key in cells}
    columns = [
        {
            "epoch": int(epoch),
            "label": labels[i] if i < len(labels) else "",
            "spot": spots[i] if i < len(spots) else None,
            "greeks_ok_pct": greeks[i] if i < len(greeks) else None,
            # columna sin celdas = foto sin griegas medidas: se muestra VACIA, nunca a cero
            "has_data": int(epoch) in filled,
        }
        for i, epoch in enumerate(epochs)
    ]
    return {
        "date": meta.get("date"),
        "source": meta.get("source"),
        "generated_epoch": meta.get("generated_epoch"),
        "strikes": [float(f"{s:g}") for s in meta.get("strikes", [])],
        "columns": columns,
        "cells": cells,
        "intraday_variation": (meta.get("intraday_variation") or {}).get(metric),
    }


def compute_trace_matrix(
    symbol: str, spot: float, chain: list[OptionContract], *, metric: str = "gex",
    cube: dict | None = None,
) -> dict:
    """SpotGamma-TRACE-style per-strike metric (GEX or Net OI). House sign: call +, put -.

    `by_strike` is the CURRENT snapshot. When a measured strike×time cube exists
    (scripts/trace_cube.py) it is served as `trace_time` and `time_axis="measured"`;
    otherwise `time_axis="flat_current"` and the frontend must say so. Fail-loud: GEX omits
    strikes with no MEASURED gamma (never reconstructs); empty chain yields empty by_strike."""
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
    trace_time = _trace_time_axis(cube, metric) if cube else None
    levels = {
        "call_wall": dealer.call_wall,
        "put_wall": dealer.put_wall,
        "gamma_flip": dealer.gamma_flip,
        "max_pain": dealer.max_pain,
    }
    if dealer.expected_move is not None and dealer.expected_move > 0:  # ATM straddle, measured
        levels["implied_move_up"] = spot + dealer.expected_move
        levels["implied_move_dn"] = spot - dealer.expected_move
        levels["implied_move"] = dealer.expected_move

    if trace_time:
        n_data = sum(1 for c in trace_time["columns"] if c["has_data"])
        axis_caveat = (
            f"Time axis MEASURED: {n_data}/{len(trace_time['columns'])} chain snapshots with data "
            f"from {trace_time['date']} ({trace_time['columns'][0]['label']}–"
            f"{trace_time['columns'][-1]['label']}). Columns without measured greeks stay blank."
        )
        var = trace_time.get("intraday_variation")
        if var is not None:
            axis_caveat += f" Measured intraday variation: {var:.0%} of strikes move."
    else:
        axis_caveat = (
            "Time axis NOT measured: the per-strike metric is the current snapshot painted flat "
            "across the session. Run scripts/trace_cube.py <SYM> for a real intraday axis."
        )

    return {
        "symbol": symbol.upper(),
        "metric": metric,
        "spot": spot,
        "strikes": [float(f"{s:g}") for s in strikes],
        "by_strike": {f"{s:g}": by_strike[s] for s in strikes},
        "levels": levels,
        "time_axis": "measured" if trace_time else "flat_current",
        "trace_time": trace_time,
        "caveats": [
            axis_caveat,
            "Open-interest signs are a dealer-positioning scenario proxy, not observed dealer inventory.",
            (
                "GEX uses MEASURED greeks only; strikes without provider gamma are omitted."
                if metric == "gex"
                else "Net OI = sum(open interest) per strike, calls +, puts -. IBKR open interest "
                     "is a T+1 field: it does not move intraday."
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
