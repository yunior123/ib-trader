# Market outlook — Thursday 2026-07-30

As of **2026-07-29 20:54:49 EDT**. Research and signal context only; no orders were placed,
simulated, staged, or transmitted.

## Executive read

- The base case for SPY tomorrow is **fragile/risk-off, not a one-way crash**. The close of the
  signed UW tape was bearish, SPY's 30-minute signed premium was -$10.2M, UW market tide was
  -$150.3M, the Jul-30 book is negative gamma, and ES/NQ were -1.03%/-0.75% at the cutoff.
- A mechanical bounce is credible because SPY/QQQ also printed large **bid-side puts** (aggressive
  put sales), SPY recovered to 732.16 after hours, and 722-730 contains heavy put inventory.
- Therefore the clean decision is conditional: **below 728/730 favors 723 then 720/716; above
  735 favors 739/741; 740/741 is the first major upside wall, not an automatic breakout.**
- The probabilities in the tree are a **declared judgmental synthesis**, not a measured forecast.
  The current compass cell has only n=19 effective observations and no predictive edge.

## Live UW whale read

`signed premium = net_call_premium - net_put_premium`. Positive means call buying and/or put
selling dominated; negative means call selling and/or put buying dominated. It identifies
aggressor premium, **not opening versus closing**, and multi-leg activity can still distort a
single alert.

| Symbol | Full day signed | Last 30 buckets | Read at close |
|---|---:|---:|---|
| SPY | +$66.0M | **-$10.2M** | Full-day put selling, bearish closing reversal |
| QQQ | +$1.2M | **-$7.2M** | Nearly balanced day, bearish close |
| MU | **-$44.0M** | **-$18.6M** | Strong bearish aggressor tape |
| NVDA | **-$60.8M** | **-$20.5M** | Strong bearish aggressor tape |
| AAPL | -$1.2M | **-$13.8M** | Earnings hedge/risk-off close |
| SMH | +$5.6M | +$0.2M | Put selling/absorption; neutral close |
| AMD | +$28.5M | +$0.1M | Put selling dominated; price disagreed |
| GOOGL | +$8.4M | -$1.3M | Bullish day, soft close |
| MSFT | +$35.8M | -$3.7M | Bullish day; earnings superseded tape |
| AMZN | **-$44.5M** | -$6.1M | Bearish into Thursday earnings |
| META | +$26.0M | -$0.6M | Bullish day; earnings gap superseded tape |

Notable signed alerts:

- **SPY:** 770P Jul-31 $1.78M bid-side, 675P Sep-30 $1.05M bid-side, and two 695P
  Aug-21 alerts totaling $1.28M bid-side: aggressive put sales, bullish/vol-selling evidence.
  A 711C Jul-30 alert was $886K ask-side: call buying.
- **QQQ:** the 680P Sep-18 cluster was mostly bid-side put selling, although one alert was
  ask-side. This conflicts with the bearish final 30-minute aggregate.
- **MU:** 750P Sep-2027 $2.30M ask-side and 720P Mar-2027 $853K ask-side were bearish put buys.
  The $4.92M 740C Sep-18 alert was predominantly mid-side and is **not directionally usable**.
- **NVDA:** 220C Jan-2027 $5.22M bid-side was aggressive call selling (bearish). The $2.72M
  192.5C Aug-07 alert was mid-side and directionally unknown.
- **AAPL:** 357.5P Jul-31 $2.21M ask-side was an earnings hedge/bearish; 330C Aug-21 $1.93M
  ask-side was bullish. Event flow is mixed.
- **SMH:** 525P Aug-21 $783K and 520P Aug-28 $583K were ask-side put buys, bearish despite the
  positive full-day aggregate.
- **AMD:** the largest 460P/450P alerts were bid-side put sales. This is bullish absorption, but
  the falling equity print did not confirm it.

UW's global market tide at 16:10 ET was net calls -$167.3M and net puts -$17.0M, or
**-$150.3M signed**. That is a stronger bearish breadth input than isolated bullish put sales.

## SPY book for Thursday

The full Polygon snapshot was taken 16:20:05 ET with IBKR spot 727.90. It covers a converged
18% band through Aug-21, has 95%+ usable greeks, but **no entitled after-hours bid/ask**.

- Jul-30 volume: 747,185 calls / 841,259 puts, P/C **1.13**.
- Jul-30 OI: 100,198 calls / 130,590 puts, P/C **1.30**.
- Approximate Jul-30 net GEX: **-$1.20B per 1%**; negative gamma means moves can accelerate.
- Put wall: **730**. Call wall: **740**. Highest OI put cluster: **720**.
- ATM 728 closing straddle: **$7.44**, about **1.02%**. UW term structure independently reports
  a $6.54 / 0.90% implied move.
- Max pain: **741**, but it is descriptive inventory, not a price target after a large selloff.
- Classic price pivots from Wednesday: 722.73 / 716.01 support and 739.43 / 749.41 resistance.
- After-hours 15m Bollinger: 726.28–734.51, midpoint 730.39; SPY was 732.16.
- VIX context was 20.66, but `vix_live=0`; it is context only and cannot confirm a branch.

## SPY TREE PRINT

As-of: **2026-07-29 20:54:49 EDT**

```text
SPY reference: 732.16 AH | Wed close 729.46 | Jul-30 EM roughly 723-737
|
+-- Open below 728 ........................................ 40%
|   |
|   +-- Reject 728/730; continuation to 723/720 .......... 65%
|   |   +-- 720 holds and rebounds toward 728 ............ 60%
|   |   `-- 720 fails; 716 then 710/700 opens ............ 40%
|   |
|   `-- Reclaim 730 on two prints; squeeze to 735/740 .... 35%
|
+-- Open inside 728-735 ................................... 43%
|   |
|   +-- Reclaim/hold 735; test 739-741 .................... 40%
|   +-- Lose 728; rotate to 723/720 ....................... 45%
|   `-- Remain pinned 728-735 .............................. 15%
|
`-- Open above 735 ........................................ 17%
    |
    +-- Hold 735; break 740/741 toward 745/749 ............ 45%
    `-- Reject 740/741; return to 735 then 730 ............ 55%
```

Every sibling split sums to 100%. Approximate terminal mass: bearish paths 54.7%, bullish paths
38.9%, pinned/range 6.4%. These are **doctrine/judgment**, not calibrated probabilities.

Branch invalidations:

- Bear thesis invalidated intraday by two 5-minute closes above 735 followed by a successful
  retest; stronger invalidation above 741.
- Bull thesis invalidated by loss of 728 with two fresh IBKR prints; below 720 the negative-gamma
  continuation branch becomes dominant.
- A touch alone is not confirmation. The trigger must come from fresh IBKR prints; Polygon/UW
  structure does not execute or confirm levels.

Measured-versus-doctrine audit:

- `compass_calib.json`: `CONTINUACION|f0|NEG` n_eff=19, WR30=36.8%, Wilson low=19.2%;
  below the n>=30 gate, so the live compass correctly reports `prob:null`.
- The only trusted calibration cell is `reclaim_wall|POSITIVO` n=27, 24/27, but it does not match
  tomorrow's negative-gamma starting state and is not used to claim a forecast.
- X recent-search returned 99 English SPY posts (keyword tally 33 positive / 9 negative / 57
  neutral), but the highest-engagement results were promotional/bot-like. **X sentiment is
  unusable and receives zero weight.**

## Ten upside candidates for Thursday

Ranking means upside *potential if the trigger prints*, not unconditional buys.

| Rank | Symbol | Spot/ref | P/E | Options-liquidity evidence | Trigger / support | Confidence |
|---:|---|---:|---:|---|---|---|
| 1 | MSFT | 418.99 AH | 23.26 | 200K front vol, 216K OI; UW +$35.8M day | Hold 415 then clear 425 / support 410-400 | Medium-high, earnings |
| 2 | LRCX | 273.00 AH | 47.63 | 27.8K vol, 36.3K OI | Clear 274 then 280 / support 265-252 | Medium, earnings gap |
| 3 | GOOGL | 336.21 | 16.92 | 114K vol, 166K OI; P/C vol 0.43 | Clear 342.5 / support 331.6-330 | Medium |
| 4 | CRM | 188.38 close | 21.81 | Finviz optionable; 14.8M avg shares; UW +$6.75M | Clear 190.2 / support 182 | Medium |
| 5 | NFLX | 73.04 AH | 23.20 | 88.8K vol, 219K OI; P/C vol 0.43 | Clear 73.75 / support 71.75 | Medium |
| 6 | WMT | 114.22 close | 40.24 | Optionable; 22.5M avg shares; UW +$0.23M | Clear 114.7 / support 112.5 | Low-medium |
| 7 | XOM | 156.75 close | 26.45 | Optionable; 16.9M avg shares | Clear 159.1 / support 155.8 | Low-medium |
| 8 | AMZN | 229.63 AH | 27.09 | 98.1K vol, 218K OI | Clear 232.8 / support 226; earnings after close | Low, binary event |
| 9 | AAPL | 339.56 AH | 40.91 | 233K vol, 278K OI | Clear 344.6-345 / support 337.3; earnings after close | Low, mixed tape |
| 10 | STX | 764.43 close | 55.09 | Full chain available; 9.3M shares today | Clear 815 / support 747 | Low, high beta |

The upside list is intentionally weaker below rank 5. Broad tape is risk-off; AMZN/AAPL are
event candidates, not clean directional forecasts.

## Ten downside candidates for Thursday

| Rank | Symbol | Spot/ref | P/E | Options-liquidity evidence | Trigger / support | Confidence |
|---:|---|---:|---:|---|---|
| 1 | META | 545.00 AH | 21.29 | 137K front vol, 107K OI | Below 540 opens 525/500 / resistance 560 | High, earnings gap |
| 2 | ARM | 224.89 AH | 265.70 | Optionable; 10.2M avg shares; UW -$8.34M | Lose 222 / resistance 230-244 | High, earnings gap |
| 3 | QCOM | 150.00 AH | 16.93 | 35.7K vol, 36.7K OI; P/C vol 1.71 | Lose 150 then 145 / resistance 155-160 | High |
| 4 | MU | 729.86 AH | 16.73 | 182K vol, 162K OI; UW -$44.0M | Lose 720 then 700 / resistance 740-750 | High |
| 5 | SMH | 508.00 AH | ETF | 185K vol, 473K OI; P/C vol 2.35 | Lose 503/500 then 485 / resistance 520 | High |
| 6 | NVDA | 191.18 AH | 29.10 | 715K vol, 832K OI; UW -$60.8M | Lose 189.9 then 185/180 / resistance 195 | Medium-high |
| 7 | TSM | 377.18 AH | 27.04 | 45.0K vol, 128K OI; UW -$30.7M | Lose 372.7 then 365 / resistance 385-391 | Medium-high |
| 8 | AMD | 431.10 AH | 140.98 | 121K vol, 131K OI | Lose 424/420 then 410 / resistance 440-450 | Medium; UW diverges bullish |
| 9 | C | 127.13 close | 13.72 | Optionable; 12.7M avg shares | Lose 126.8 then 125/120 / resistance 132 | Medium |
| 10 | JPM | 344.71 close | 14.77 | Optionable; 9.4M avg shares | Lose 343.8 then 340/335 / resistance 350-357 | Medium |

## Source/freshness legend

- **IBKR bars/spot:** realtime entitlement, last SPY bar 20:53 ET; trigger-grade.
- **UW net-prem-ticks / flow-alerts:** live HTTP reads made 20:49-20:51 ET; latest equity buckets
  mostly 19:59-20:15 UTC. Aggressor side is measured; opening/closing is unknown.
- **UW market tide:** latest row 16:10 ET; signed aggregate -$150.3M.
- **Polygon full chain:** 16:20:05 ET snapshot; structural only. OI is previous-close inventory,
  bid/ask unavailable after hours, and it cannot trigger a trade.
- **Finviz Elite:** one live export at approximately 20:52 ET for 48 optionable/liquid symbols. Fundamentals and
  closes are context; after-hours fields were used where shown.
- **Overnight feed:** 20:53 ET: ES -1.03%, NQ -0.75%, KOSPI -1.19%, SK Hynix -5.77%.
- **VIX:** 20.66 at 20:42 ET with `vix_live=0`; context only.
- **X API:** one paid recent-search at 20:49 ET; spam contamination made it zero-weight.

## Exact read-only endpoints and commands

Endpoints:

```text
GET https://api.unusualwhales.com/api/stock/{SYM}/net-prem-ticks
GET https://api.unusualwhales.com/api/stock/{SYM}/flow-alerts?limit=100
GET https://api.unusualwhales.com/api/market/market-tide
GET https://api.unusualwhales.com/api/market/oi-change
GET https://api.unusualwhales.com/api/stock/SPY/greek-exposure/strike
GET https://api.unusualwhales.com/api/stock/SPY/spot-exposures/strike
GET https://api.unusualwhales.com/api/stock/SPY/max-pain
GET https://api.unusualwhales.com/api/stock/SPY/volatility/term-structure
GET https://elite.finviz.com/export/screener
GET https://api.twitter.com/2/tweets/search/recent
```

Local source checks:

```sh
tail -1 data/bars_spy_ibkr.txt
cat data/overnight_ctx.json
cat data/vix.json
cat data/compass_SPY.json
cat data/history/2026-07-29/chain_full_spy.json
cat data/compass_calib.json
cat data/timeofday_factors.json
```

Authentication values came from `config/feeds.env` and `config/x.env` and were never printed.
