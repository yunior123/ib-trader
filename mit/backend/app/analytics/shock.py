from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from backend.app.config import Settings
from backend.app.domain import Bar, Direction, Severity, ShockState, WeeklyDay, WeeklyRow


def _daily_frame(bars: list[Bar]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    frame = pd.DataFrame([bar.model_dump() for bar in bars])
    frame.index = pd.to_datetime(frame.pop("timestamp"), utc=True)
    daily = (
        frame.resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    daily["return_pct"] = daily.close.pct_change() * 100
    return daily


def analyze_shock(symbol: str, bars: list[Bar], settings: Settings) -> ShockState:
    daily = _daily_frame(bars)
    now = bars[-1].timestamp if bars else datetime.now(UTC)
    if len(daily) < 5:
        return ShockState(
            symbol=symbol.upper(),
            timestamp=now,
            change_pct=0,
            note="Insufficient daily history for shock calibration.",
        )

    returns = daily.return_pct.dropna()
    current = float(returns.iloc[-1])
    history = returns.iloc[:-1].tail(settings.reversion_lookback_days)
    mean = float(history.mean()) if len(history) else 0
    std = float(history.std(ddof=0)) if len(history) else 0
    zscore = (current - mean) / std if std > 0 else None
    absolute = abs(current)

    severity = Severity.INFO
    label = "normal"
    if absolute >= settings.extreme_shock_pct:
        severity, label = Severity.CRITICAL, "extreme 15% shock"
    elif absolute >= settings.shock_pct:
        severity, label = Severity.WARNING, "10% shock"
    elif zscore is not None and abs(zscore) >= settings.shock_zscore:
        severity, label = Severity.WATCH, f"{settings.shock_zscore:g}σ statistical shock"

    probability, sample = _historical_reversion_probability(
        daily,
        threshold=min(settings.shock_pct, max(absolute, 0.01)),
        horizon=settings.reversal_horizon_days,
    )
    direction = Direction.UP if current > 0 else Direction.DOWN if current < 0 else Direction.NEUTRAL
    note = (
        "Reversion probability is empirical: a subsequent close moved opposite the shock within "
        f"{settings.reversal_horizon_days} sessions. It is an alert condition, not a prediction guarantee."
    )
    return ShockState(
        symbol=symbol.upper(),
        timestamp=now,
        change_pct=current,
        zscore=zscore,
        severity=severity,
        direction=direction,
        label=label,
        historical_reversion_probability=probability,
        sample_size=sample,
        horizon_days=settings.reversal_horizon_days,
        note=note,
    )


def _historical_reversion_probability(
    daily: pd.DataFrame, *, threshold: float, horizon: int
) -> tuple[float | None, int]:
    returns = daily.return_pct.to_numpy(dtype=float)
    closes = daily.close.to_numpy(dtype=float)
    outcomes: list[bool] = []
    for i in range(1, len(daily) - horizon):
        shock = returns[i]
        if not np.isfinite(shock) or abs(shock) < threshold:
            continue
        future = closes[i + 1 : i + horizon + 1] / closes[i] - 1
        opposite = np.any(future < 0) if shock > 0 else np.any(future > 0)
        outcomes.append(bool(opposite))
    if not outcomes:
        return None, 0
    return float(np.mean(outcomes)), len(outcomes)


def build_weekly_rows(bars_by_symbol: dict[str, list[Bar]], settings: Settings) -> list[WeeklyRow]:
    rows: list[WeeklyRow] = []
    for symbol, bars in bars_by_symbol.items():
        daily = _daily_frame(bars)
        if daily.empty:
            continue
        latest = daily.index[-1]
        monday = (latest - pd.Timedelta(days=latest.weekday())).date()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        days: list[WeeklyDay] = []
        for offset, name in enumerate(day_names):
            target = monday + pd.Timedelta(days=offset)
            matches = daily[daily.index.date == target]
            if matches.empty:
                days.append(WeeklyDay(day=name, date=target, status="pending"))
                continue
            row = matches.iloc[-1]
            change = float(row.return_pct) if pd.notna(row.return_pct) else 0.0
            shock = abs(change) >= settings.shock_pct
            direction = Direction.UP if change > 0 else Direction.DOWN if change < 0 else Direction.NEUTRAL
            days.append(
                WeeklyDay(
                    day=name,
                    date=target,
                    close=float(row.close),
                    change_pct=change,
                    shock=shock,
                    direction=direction,
                    status="shock" if shock else "closed",
                )
            )
        rows.append(WeeklyRow(symbol=symbol.upper(), days=days))
    return rows
