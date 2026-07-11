---
name: trendline-trading
description: Trendline and channel trading — objective swing-point detection, trendline construction/validation rules, break-and-retest entries, false-break filters, and channel trading, wired to the ib-trader fleet's 1m/5m/15m bars and existing Supertrend/Donchian/CUSUM layers. Use when the user asks about trendlines, trend channels, trendline breaks, retests, higher-lows/lower-highs structure, or drawing support/resistance lines.
---

# Trendline Trading

Trendlines are only tradeable if constructed by mechanical rules — otherwise
they're hindsight art. These rules are deterministic and backtestable.

## Construction (mechanical)

**Swing points** (on the working timeframe, use 5m/15m for intraday):
- Swing high = bar high greater than the 2 highs before AND after (fractal-5).
- Swing low mirrored. Ignore swings whose range < 0.5×ATR(14) (noise).

**Valid trendline**:
- Uptrend line: connect 2 successive HIGHER swing lows; a 3rd touch
  (within 0.15×ATR of the line) VALIDATES it. Downtrend line mirrored on lower highs.
- Slope sanity: reject lines steeper than 45° equivalent (price change per bar
  > 0.5×ATR) — parabolic lines break by design.
- Age: lines with 3+ touches spanning ≥60 bars are institutional-grade;
  2-touch lines are provisional (half size or watch-only).

**Channels**: clone the validated line through the opposite extreme swing.
Price living in the upper half = strength; repeated failures to reach the
upper rail = fade warning.

## Signals

**Break**: 1m/5m CLOSE beyond the line by ≥0.25×ATR (wicks don't count) with
vol ≥ volMA(20). This matches the fleet's confirm-bar philosophy — no
anticipation, close-basis only.

**Retest entry** (higher quality than the break itself): after the break, price
returns to the line within 20 bars and rejects (close back in break direction).
Entry on rejection close; stop 0.5×ATR beyond the line; target = channel width
projected, min 2R.

**False-break filter**: if the break bar's CUSUM contribution is < the fleet's
per-ticker QUAKE_MIN/4, treat as noise probe — most trendline breaks without a
volatility signature revert. Cross-check `st_trend` (Supertrend 5m in every
bot's log) — a trendline break AGAINST the active Supertrend direction needs a
flip confirmation before it's trusted.

**Trend structure degradation** (exit/reversal early warning): sequence check —
uptrend intact while swing lows keep rising; first lower swing low = line
under threat regardless of whether the line itself is touched.

## Fleet integration

- Bars: `data/bars_<sym>.txt` (Alpaca IEX) / `data/bars_<sym>_ibkr.txt` (SIP,
  full volume — prefer for volume gates when present).
- The bots already run Supertrend(10,3) 5m + Donchian-390 + CUSUM; trendlines
  complement them as PRICE-STRUCTURE context — e.g., a terremoto CUSUM banner
  landing exactly at a 3-touch weekly trendline is a materially stronger signal
  than either alone.
- Any rule promoted to a bot must pass the standing gate: replay 90d via
  `--stdin`, WR≥70 + positive OOS walk-forward (scripts/fleet_wfo.py pattern).
