---
name: liquidity-trading
description: Liquidity-based trading analysis — resting liquidity pools (equal highs/lows), stop hunts / liquidity sweeps, order blocks, fair value gaps, session liquidity windows, and whale-print/NBBO liquidity reads wired to the ib-trader fleet's data files. Use when the user asks about liquidity trading, stop hunts, sweeps, order blocks, FVG, smart-money concepts, where stops cluster, or why price wicked a level and reversed.
---

# Liquidity Trading

Price moves toward liquidity (clustered resting orders), consumes it, then often
reverses. This skill turns that into checkable rules on 1m/5m/15m bars.

## Core concepts → detection rules

**Liquidity pools** — where stops cluster:
- Equal highs/lows: 2+ swing highs (lows) within 0.1×ATR(14) of each other →
  buy-side (sell-side) liquidity rests just above (below).
- Prior day high/low, session high/low, round numbers ($0.50/$1 increments on
  sub-$100 names), Donchian-390 extremes (the fleet already tracks day range).

**Liquidity sweep / stop hunt** (the tradeable event):
- Bar wicks BEYOND the pool by ≥0.25×ATR but CLOSES back inside → swept.
- Confirmation: next bar closes in the reversal direction with vol ≥ volMA(20).
- Failed sweep (close beyond, no reclaim in 3 bars) = genuine breakout, do NOT fade.

**Order block**: last opposite-color 1m/5m bar before an impulsive move
(≥2×ATR range, vol ≥1.5×volMA). Revisits of its 50% level are reaction zones.

**Fair value gap (FVG)**: 3-bar pattern where bar1.high < bar3.low (bullish).
MEASURED 2026-07-30 on poly_bars (1,306,310 FVGs, 13,499 sym-day clusters, 30 syms,
2 years): same-day complete fill = **88.55%** — but a SYMMETRIC level the same distance
in the OPPOSITE direction is touched **87.83%** of the time. **Edge over the null =
+0.72pp** (bullish +0.19pp, bearish +1.28pp), against a house bar of +6pp.
The fill rate is DIFFUSION, not institutional anchoring. Do NOT trade the fill.
The old "~70% gets filled" line was folklore: wrong number AND meaningless.
Script: scratchpad/fvg_null.py. Same precedent as scripts/gaps.py:12-15 (no p_fill published).

**Session windows (ET)**: 9:30–10:00 opening auction sweeps prior-day levels;
10:00–11:30 trend establishment; 15:30–16:00 MOC flows. Overnight (20:00–04:00,
Blue Ocean/IBEOS) is thin — levels made there are weak liquidity, expect RTH retests.

## Fleet data hooks (this repo)

- `data/whale_<sym>.txt` — "EPOCH PRICE USD DIR" prints ≥$50k from the ws daemon.
  A whale print INTO a pool level + sweep wick = institutional participation signal.
- `data/nbbo_<sym>.txt` — "EPOCH BID ASK". Spread widening >2× its session median
  at a level = liquidity vacuum (moves accelerate); tight spread + heavy tape = absorption.
- `data/bars_<sym>.txt` / `bars_<sym>_ibkr.txt` — 1m OHLCV for all detection rules.
  IBKR file carries full SIP volume (trustworthy for vol gates); Alpaca file is
  IEX-sampled (~2-5% of tape) — scale vol thresholds accordingly.

## Trade template (signal-only, matches fleet discipline)

1. Map pools on 15m (levels) + 1m (triggers) before the open.
2. Wait for sweep + reclaim close (never anticipate).
3. Entry: close of confirmation bar. Stop: 0.5×ATR beyond the sweep extreme.
4. Target: opposite pool (minimum 2R or skip). Time-stop 90 min.
5. Skip entirely if NBBO spread >0.3% (fleet SPREAD_MAX convention) or within
   ±2 min of scheduled macro prints (FOMC/CPI/NFP).

Backtest any rule via the fleet harness before trusting it: replay bars through
`--stdin` bots or `scripts/backtest_replay.py` — WR≥70 + positive OOS or it
doesn't ship (standing order).
