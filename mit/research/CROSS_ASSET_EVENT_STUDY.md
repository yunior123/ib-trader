# Separate vs combined: SPY + TSLA event study

## Decision

Keep **Bento reversal** and **Trinity continuation** as separate engines, but connect them through a state machine.

- Bento identifies an opening overextension and arms a possible fade.
- Trinity describes whether trend continuation is still active.
- A flat AND/OR merge is the wrong design because the engines often predict opposite regimes.
- For an opening reversal, wait until the combined 5-of-6 reversal confirmation fires.
- For continuation away from a Bento opening extreme, use Trinity independently.

In practical UI terms, show both engines separately and let the combined layer display one of:

1. `CONTINUATION ACTIVE — DO NOT FADE`
2. `REVERSAL ARMED — NOT CONFIRMED`
3. `REVERSAL CONFIRMED`
4. `NEUTRAL / CONFLICT`

## Data

### SPY

- 17,706 five-minute bars
- 227 complete regular sessions
- 2025-04-15 through 2026-03-20

### TSLA

- 97,812 five-minute bars
- 1,254 complete regular sessions
- 2018-07-27 through 2023-09-08
- Historical prices normalized for Tesla's 2020 5-for-1 and 2022 3-for-1 splits

### TSLA one-minute validation

- Signals generated on the five-minute series
- Outcomes resolved on the matching one-minute series
- 93,210 one-minute bars
- 239 complete sessions
- 2022-08-30 through 2023-09-08
- The one-minute and five-minute source closes match exactly at five-minute boundaries

## Why “it works most of the time” can be true but misleading

On volatile stocks, asking only whether the predicted side is touched sometime in the next 30 minutes produces high hit rates because both directions are often touched.

For TSLA in the one-minute validation:

| Model | Favorable 25 bp touched | Opposite 25 bp touched | Both touched | Favorable side first |
|---|---:|---:|---:|---:|
| Bento reversal | 80.6% | 83.3% | 63.9% | 55.6% |
| Trinity continuation | 82.4% | 87.1% | 69.4% | 43.9% |
| Combined reversal 5/6 | 88.5% | 76.9% | 65.4% | **68.0%** |

So a screenshot can correctly say that a favorable move happened frequently while still failing to show whether the predicted side happened first. First-touch is the more useful timing test.

## Key results

### SPY five-minute event study

| Model | Signals | 10 bp predicted side first in 30m | 10% prior daily ATR side first | Directional 30m close |
|---|---:|---:|---:|---:|
| Bento reversal | 27 | 68.2% of 22 resolved | 60.9% of 23 | 55.6% |
| Trinity continuation | 120 | 56.2% of 105 | 59.3% of 108 | 58.3% |
| Combined reversal 5/6 | 19 | **81.3% of 16** | **86.7% of 15** | **68.4%** |

The combined confirmation materially improved reversal timing on SPY, but preserved only 70.4% of Bento setups and arrived a median 65 minutes later.

### TSLA full five-minute history

| Model | Signals | 50 bp side first in 30m | 100 bp side first in 30m | 10% prior daily ATR side first |
|---|---:|---:|---:|---:|
| Bento reversal | 203 | 45.1% of 184 | 45.0% of 129 | 47.6% of 189 |
| Trinity continuation | 473 | 47.3% of 425 | 51.4% of 323 | 48.4% of 434 |
| Combined reversal 5/6 | 149 | 52.9% of 119 | 57.9% of 57 | 48.1% of 129 |

Across the full TSLA history, none of the reconstructions showed a stable, universal edge. The combined model helped at larger reversal thresholds, but not enough to call it robust.

### TSLA one-minute path validation, 2022-08-30 to 2023-09-08

| Model | Signals | 25 bp side first in 30m | 50 bp side first in 30m | Directional 30m close |
|---|---:|---:|---:|---:|
| Bento reversal | 36 | 55.6% of 36 | 57.1% of 35 | 41.7% |
| Trinity continuation | 85 | 43.9% of 82 | 41.7% of 84 | 44.7% |
| Combined reversal 5/6 | 26 | **68.0% of 25** | **56.5% of 23** | **53.8%** |

The combined reversal confirmation was the best TSLA timing tool in this recent one-minute subset, but 25 resolved cases are not enough to claim a permanent edge. Its behavior also varied substantially by year.

## Final architecture

- **Use Bento separately** to create the opening reversal candidate.
- **Use Trinity separately** for continuation outside the opening-fade context.
- **Use the combined 5-of-6 model only to time the actual reversal**, after Trinity's trend state has weakened or broken.
- Do not use the Bento–Trinity router at the opening extreme; it was unstable across SPY and TSLA.

## MSTR status

A public dataset listing describes approximately 29,513 regular-session five-minute MSTR bars from 2023-12-11 through 2025-06-09, originally sourced from Alpaca. The original hosted dataset is no longer directly downloadable from the discovered listing, so it was not used. A clean MSTR export from IBKR, Alpaca, TradingView, or a verified historical-data vendor can be passed through the included engine without changing the signal logic.

## Files

- `decision_table.csv`: compact SPY/TSLA comparison
- `cross_asset_summary.csv`: all fixed and volatility-normalized metrics
- `TSLA/m1_validation_summary.csv`: one-minute path validation
- `TSLA/yearly_stability.csv`: year-by-year stability
- `cross_asset_event_study.py`: reproducible engine
- Three Pine v6 indicator files
