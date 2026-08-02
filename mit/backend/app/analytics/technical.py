from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from backend.app.domain import Bar, Direction, SignalSnapshot


def _frame(bars: list[Bar]) -> pd.DataFrame:
    frame = pd.DataFrame([bar.model_dump() for bar in bars])
    if frame.empty:
        return frame
    frame = frame.set_index(pd.to_datetime(frame.pop("timestamp"), utc=True)).sort_index()
    return frame


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _dmi(frame: pd.DataFrame, length: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = frame.high.diff()
    down = -frame.low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    previous = frame.close.shift(1)
    tr = pd.concat(
        [(frame.high - frame.low), (frame.high - previous).abs(), (frame.low - previous).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    plus = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr.replace(0, np.nan)
    minus = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus - minus).abs() / (plus + minus).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return plus.fillna(0), minus.fillna(0), adx.fillna(0)


def _enrich(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["rsi"] = _rsi(result.close)
    result["bb_basis"] = result.close.rolling(20).mean()
    result["bb_sd"] = result.close.rolling(20).std(ddof=0)
    result["bb_upper"] = result.bb_basis + 2 * result.bb_sd
    result["bb_lower"] = result.bb_basis - 2 * result.bb_sd
    result["rsi_basis"] = result.rsi.rolling(20).mean()
    result["rsi_sd"] = result.rsi.rolling(20).std(ddof=0)
    result["rsi_upper"] = result.rsi_basis + 2 * result.rsi_sd
    result["rsi_lower"] = result.rsi_basis - 2 * result.rsi_sd
    result["ribbon_high"] = result.high.rolling(20).mean()
    result["ribbon_mid"] = ((result.high + result.low + result.close) / 3).rolling(20).mean()
    result["ribbon_low"] = result.low.rolling(20).mean()
    result["ema5"] = result.close.ewm(span=5, adjust=False).mean()
    previous = result.close.shift(1)
    tr = pd.concat(
        [(result.high - result.low), (result.high - previous).abs(), (result.low - previous).abs()], axis=1
    ).max(axis=1)
    result["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    result["plus_di"], result["minus_di"], result["adx"] = _dmi(result)
    return result


def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        frame.resample(rule, label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


def _latest_value(frame: pd.DataFrame, key: str) -> float:
    value = frame[key].iloc[-1]
    return float(value) if pd.notna(value) else 0.0


def analyze_signals(symbol: str, bars: list[Bar]) -> SignalSnapshot:
    base = _frame(bars)
    now = bars[-1].timestamp if bars else datetime.now(UTC)
    if len(base) < 260:
        return SignalSnapshot(
            symbol=symbol,
            timestamp=now,
            bento_state="INSUFFICIENT DATA",
            trinity_state="INSUFFICIENT DATA",
            router_state="NEUTRAL",
        )

    five = _enrich(base)
    fifteen = _enrich(_resample(base, "15min"))
    thirty = _enrich(_resample(base, "30min"))
    hourly = _enrich(_resample(base, "1h"))
    four_hour = _enrich(_resample(base, "4h"))
    daily = _enrich(_resample(base, "1D"))

    # Bento: opening stretch detector. During the session it remains armed while the
    # current 15m/30m conditions agree; it is independent from Trinity.
    def extreme(frame: pd.DataFrame) -> int:
        row = frame.iloc[-1]
        if row.close > row.bb_upper and row.rsi >= 70:
            return -1
        if row.close < row.bb_lower and row.rsi <= 30:
            return 1
        return 0

    ext15, ext30 = extreme(fifteen), extreme(thirty)
    bento_direction = Direction.NEUTRAL
    bento_state = "NO OPENING EXTREME"
    bento_score = 0.0
    if ext15 == ext30 != 0:
        bento_direction = Direction.UP if ext15 == 1 else Direction.DOWN
        bento_state = "REVERSAL ARMED"
        bento_score = 1.0
    elif ext15 != 0 or ext30 != 0:
        direction = ext15 or ext30
        bento_direction = Direction.UP if direction == 1 else Direction.DOWN
        bento_state = "PARTIAL EXTREME — WAIT FOR MTF CONFIRMATION"
        bento_score = 0.5

    # Trinity: independent continuation detector. Direction is based on 5-timeframe EMA5
    # alignment; ribbon, RSI-BB, DMI/ADX and ATR energy score the quality.
    frames = [five, fifteen, hourly, four_hour, daily]
    above = sum(_latest_value(frame, "close") > _latest_value(frame, "ema5") for frame in frames)
    below = sum(_latest_value(frame, "close") < _latest_value(frame, "ema5") for frame in frames)
    row = five.iloc[-1]
    daily_atr = _latest_value(daily, "atr")
    energy = float(row.atr / daily_atr) if daily_atr > 0 else 0

    long_facts = [
        above == 5,
        row.close > row.ribbon_high,
        row.rsi > max(50, row.rsi_basis),
        row.plus_di > row.minus_di,
        row.adx >= 20,
        energy >= 0.14,
    ]
    short_facts = [
        below == 5,
        row.close < row.ribbon_low,
        row.rsi < min(50, row.rsi_basis),
        row.minus_di > row.plus_di,
        row.adx >= 20,
        energy >= 0.14,
    ]
    long_score = sum(long_facts) / len(long_facts)
    short_score = sum(short_facts) / len(short_facts)
    if long_score >= 5 / 6:
        trinity_direction = Direction.UP
        trinity_state = "CONTINUATION ACTIVE"
        trinity_score = long_score
    elif short_score >= 5 / 6:
        trinity_direction = Direction.DOWN
        trinity_state = "CONTINUATION ACTIVE"
        trinity_score = short_score
    else:
        trinity_direction = Direction.UP if long_score > short_score else Direction.DOWN if short_score > long_score else Direction.NEUTRAL
        trinity_state = "CONTINUATION WEAK / MIXED"
        trinity_score = max(long_score, short_score)

    # Combined router: it does not erase either independent indicator. It decides when a
    # Bento fade is confirmed and when Trinity should veto a premature fade.
    reasons: list[str] = []
    reversal_score = 0
    router_direction = Direction.NEUTRAL
    router_state = "NEUTRAL / CONFLICT"

    if bento_direction != Direction.NEUTRAL:
        predicted_up = bento_direction == Direction.UP
        reentered_band = row.close > row.bb_lower if predicted_up else row.close < row.bb_upper
        entered_ribbon = row.close > row.ribbon_low if predicted_up else row.close < row.ribbon_high
        rsi_turn = row.rsi > five.rsi.iloc[-2] if predicted_up else row.rsi < five.rsi.iloc[-2]
        dmi_flip = row.plus_di > row.minus_di if predicted_up else row.minus_di > row.plus_di
        mtf_break = above < 5 if predicted_up else below < 5
        candle_turn = row.close > row.open if predicted_up else row.close < row.open
        facts = [reentered_band, entered_ribbon, rsi_turn, dmi_flip, mtf_break, candle_turn]
        labels = ["price re-entered Bollinger", "price entered ribbon", "RSI turned", "DMI flipped", "MTF trend broke", "reversal candle"]
        reversal_score = sum(facts)
        reasons.extend(label for label, passed in zip(labels, facts) if passed)

        continuation_opposes = (
            trinity_state == "CONTINUATION ACTIVE" and trinity_direction != bento_direction
        )
        if continuation_opposes and reversal_score < 5:
            router_state = "CONTINUATION ACTIVE — DO NOT FADE"
            router_direction = trinity_direction
            reasons.append("Trinity continuation veto")
        elif reversal_score >= 5:
            router_state = "REVERSAL CONFIRMED"
            router_direction = bento_direction
        else:
            router_state = "REVERSAL ARMED — WAIT"
            router_direction = bento_direction
    elif trinity_state == "CONTINUATION ACTIVE":
        router_state = "CONTINUATION ACTIVE"
        router_direction = trinity_direction
        reasons.append("5-timeframe EMA5, ribbon, RSI, DMI/ADX and energy aligned")

    return SignalSnapshot(
        symbol=symbol.upper(),
        timestamp=now,
        bento_state=bento_state,
        bento_direction=bento_direction,
        bento_score=bento_score,
        trinity_state=trinity_state,
        trinity_direction=trinity_direction,
        trinity_score=round(trinity_score, 3),
        router_state=router_state,
        router_direction=router_direction,
        reversal_score=reversal_score,
        reasons=reasons,
    )
