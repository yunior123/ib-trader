# TrendSpider — Source-Code & Community Archaeology Report

## 0. Headline finding (read this first)

**TrendSpider's "proprietary" automated-TA engine is publicly documented — by TrendSpider itself.** Their JavaScript custom-indicator API exposes the *actual internal engine functions* (`find_trends`, `find_head_and_shoulders`, `find_double_peak_formation`, `find_channel`, `find_wedge`, `find_triangle`, `find_broadening`, `find_cup_and_handle`, `fractal_high/low`, `vwap`, `twap`) **with their internal variable names, defaults and scoring language**. Nobody on GitHub has reverse-engineered them because there is nothing to reverse — the spec is in `charts.trendspider.com/scripting/docs/api.md` (175 KB of markdown, downloaded).

Three structural facts that collapse the whole reverse-engineering problem:

1. **The trend-strength scoring language is [math.js](https://mathjs.org)** — the "custom formula" function list in their KB is verbatim the math.js function catalog, and `find_trends`'s docs link to mathjs syntax. So a faithful clone = mathjs expression evaluator + their variable set.
2. **Base points are Williams Fractals.** Their own `find_trends` example uses `fractal_low(low, 5)`; the auto-anchoring docs say "Window=5 → Williams Fractal points"; the UI parameter "HH/LL Numbers" *is* the fractal window (default 10 on daily).
3. **ATR(14) is the universal scale unit** — gap detection ("ATR for Islands", default 3×ATR(14)), relevance filtering, "long bar" definition (1.5×ATR(14)), pattern tolerances. `find_trends` even says: *"trends engine uses ATR heavily, so it needs it in many places"* (default `atrLength = 14`).
4. Standard indicators are **TA-Lib** — TrendSpider's own GitHub org publishes `node_talib` ("A technical analysis library for node.js"). Their internal name for Raindrop charts is **`rainfall`** (`current.chart_type` ∈ `line, bars, candles, hollowcandles, rainfall, heikinashi`).

---

## 1. Table of every open-source / public replication found

| Metric / feature | Repo or URL | Language | Quality | Data it needs |
|---|---|---|---|---|
| **The engine spec itself** (all of the below) | https://charts.trendspider.com/scripting/docs/api.md (+ `_sidebar.md`, `additional_series.md`) | JS API docs (markdown) | **Authoritative** — TrendSpider's own | n/a |
| Trend-line scoring variable set + formula language | https://help.trendspider.com/kb/automated-technical-analysis/custom-trend-line-formulas | mathjs expressions | **Authoritative** | n/a |
| Automated trendline detection (closest OSS equivalent) | https://github.com/neurotrader888/TechnicalAnalysisAutomation → `trendline_automation.py` (⭐570) | Python | **Faithful in spirit, different method** (single best-fit line per window, slope optimized by numerical descent — not pairwise-scored) | OHLC only |
| Horizontal S/R Heatmap (best OSS match found) | same repo → `mp_support_resist.py` | Python | **Faithful** — Gaussian KDE of log-close, bandwidth = `atr×3.0`, recency-weighted, peaks by prominence. Matches TrendSpider's "3×ATR" + recency + clustering description | OHLC (close + ATR) |
| Head & Shoulders (zigzag-based, same construction TrendSpider uses) | same repo → `head_shoulders.py`, `directional_change.py`, `rolling_window.py` | Python | Faithful | OHLC |
| Harmonic patterns / PIP pattern mining / flags & pennants | same repo → `harmonic_patterns.py`, `pip_pattern_miner.py`, `flags_pennants.py`, `perceptually_important.py` | Python | Good | OHLC |
| Automated trendlines + Elliott waves, explicitly branded "free TrendSpider clone" | https://github.com/jinhae8971/trendline-detector | Python (scipy/numpy/pandas) | **Rough** — `find_peaks` + ATR filter + C(n,2) pair enumeration + 4-component weighted score; caps at top-20 lines vs TrendSpider's 2000/top-1% | OHLCV daily |
| Companion "free TrendSpider clone" repos | https://github.com/jinhae8971/backtest-lab (Backtrader strategy lab), https://github.com/jinhae8971/chart-analyzer (chart image + vision analysis) | Python | Toy/rough | OHLCV |
| **Native TrendSpider-language (JS) open-source indicators** — real working examples of their API | https://github.com/trendoscope-algorithms/trendspider (⭐10): `zigzag/iZigzag.js`, `HarmonicPatterns/HarmonicPatterns.js`, `iSupertrend/`, `iRsi/` | TrendSpider JS | **Faithful** (MPL-2.0, by Trendoscope) | OHLCV |
| TrendSpider JS custom indicators (ports) | https://github.com/bondjames12/trend-spider-indicators (⭐4): B-XTrender, Market Bias, SMA-RSI, Fair Value Bands | TrendSpider JS (GPL-3.0) | Rough (author flags forward-looking bugs on weekly variants) | OHLCV |
| More TrendSpider JS in the wild | https://github.com/drgoose23/trendspider_scripts (`hurst_exponent.js`, `returns_dist.js`, `rsi_divergences.js`, `trendstrength_candles.js`); https://github.com/maikokuppe/trendspider-indicators (`supplyDemand.js`, 16 KB); https://github.com/MikeI-Code/Trendspider-BOS (`bos_liquidity_sweep.js`); https://github.com/donoage/moe-bot-trendspider-data (`trendspider_support_resistance_script.js`) | TrendSpider JS | Mixed | OHLCV |
| **Raindrop chart** — closest public replication | "Waindrops [Makit0]" https://www.tradingview.com/script/dJr8hv4v-Waindrops-Makit0/ | Pine Script (open source) | **Faithful** — splits period in half, independent VWAP per half, per-half vertical volume histogram from tick/lower-TF data, green/red/blue by right-vs-left VWAP, configurable neutral tick-delta threshold | Intraday only (1m–720m); price+time+volume; fails on volumeless indices |
| Raindrop chart (modern variant) | "Raindrop Candles (Zeiierman)" https://www.tradingview.com/script/UTH5wdpT-Raindrop-Candles-Zeiierman/ | Pine Script (open source) | Faithful — mini volume profile per bar from lower-TF (minute/second) intrabar series, left/right centroids | Lower-TF intrabar series |
| Raindrop dashboard | "RainDrop Panel" https://www.tradingview.com/script/lw7DKpOG/ | Pine Script | Toy (table readout) | OHLCV |
| Raindrop official spec + white paper | https://help.trendspider.com/kb/raindrop-charts-tm/how-raindrops-are-rendered (11 render steps), https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-pattern (**exact pattern thresholds**), white paper PDF https://trendspider.com/whitepapers/raindrops_280519.pdf | — | **Authoritative** (white paper is a 32-page *image-only* scan, no formulas — I extracted all 32 JPEGs; it's a visual explainer, not math) | — |
| Auto-trendline Pine replications | "Auto Trend Lines v1.0" https://www.tradingview.com/script/X9KGemzG-Auto-Trend-Lines-v1-0/ ; "Trendline Detector – 3 Timeframes" https://www.tradingview.com/script/SB0Y7c9Y-Trendline-Detector-3-Timeframes/ (ranks by touch count, ties → more recent + steeper) ; "Trend Line – HarryBot" https://gist.github.com/immusen/c4c60952bb3b8da4079cde81ca080dfb (full source, fetched: fractal anchors, min-angle selection, ATR-free gap/`chg` relevance filter, auto-delete when `gap > 2`) | Pine v5 | Rough → decent | OHLC |
| TrendSpider→broker signal plumbing (not a metric, but the integration spec) | https://github.com/TradersPost/docs/blob/main/learn/signal-sources/trend-spider.md ; https://github.com/mbelarj/ts-webhook-proxy | Markdown / TS | n/a | webhooks |
| Competitor's public reverse-engineering inventory of TrendSpider | https://github.com/vincenzo5/Edge → `docs/roadmaps/trendspider-competitive-roadmap.md` | Markdown | Inventory only, no math | n/a |
| TrendSpider's own OSS (reveals their stack) | https://github.com/TrendSpider → `node_talib` (C, LGPL-3.0) | C/JS | — | — |
| Empirical falsification of volume-profile-style S/R (relevant to Raindrop/heatmap edge) | https://github.com/pedrobraiti/volume-profile-trading (README 404 at time of fetch; repo exists) | Python | Unknown | 17–33 yr OHLCV |

**Dead ends worth recording so you don't repeat them:** TrendSpider's own GitHub org has *zero* algorithm code (only forks: stripe-php, swarmprom, console-feed, rabbot, alpinejs-countdown). There is no `TrendSpider` PyPI/npm clone. GitHub code search for `raindrop left_vwap`, `trendspider gamma`, etc. returns nothing. The Raindrop white paper has **no text layer** (all DCTDecode images) and contains **no formulas**.

---

## 2. Reproducible algorithm specs

### 2.1 Automated Trendline Detection + Strength Scoring ★ most valuable

**Inputs:** OHLC bars for the chart timeframe. `atrLength = 14`. `hhllWindow` (UI: "HH/LL Numbers", per-timeframe; default **10** on daily). `drawingInput ∈ {wick(H/L), body(O/C)}`. `analysisType ∈ {Original, Enhanced}` (Enhanced = smaller inter-candle distance → more, tighter lines). `gapATRMult = 3.0`. `strongestPct` (UI "Most Relevant" = **top 1%**; API default `0.1` = top 10%). Hard cap **2000 lines**.

**Step-by-step:**

```
1. ATR = ATR(14) over the series.

2. BASE POINTS (pivots)
   highPivots = fractal_high(high, hhllWindow)     # Williams fractal, sparse series
   lowPivots  = fractal_low(low,  hhllWindow)
   # fractal_high(series, length, peakIndex): length odd unless peakIndex given;
   # peakIndex defaults to (length-1)/2. peakIndex ≠ centre → asymmetric pivots.
   # On Raindrop charts substitute leftVWAP/rightVWAP for O/C when drawingInput = body.
   # Base points may be weighted: array of {index, weight} → feeds linePointsWeight.

3. ISLAND SEGMENTATION (critical, most clones miss it)
   Detect price gaps where |open[i] - close[i-1]| > gapATRMult * ATR[i]  (default 3×).
   TrendSpider NEVER draws a trendline across a gap. Split the series into "islands"
   at gaps; only pair base points that live in the same island.

4. CANDIDATE GENERATION
   For each same-type pair (p1, p2), p1.index < p2.index, same island:
     slope = (p2.price - p1.price) / (p2.index - p1.index)
     intercept = p1.price - slope * p1.index
     line(i) = slope*i + intercept, extended right to the last bar.
   Cost is O(n²) in pivots — this is why they cap at 2000 output lines.
   Optional discardTrendCallback(p1, p2) → true to reject (their API exposes this hook).

5. HIT ACCOUNTING — compute per candidate line (exact internal variable set):
   tolerance band around the line is ATR-scaled.
   hits.number (n)                 # count of highs/lows touching the line
   hits.percent (pc)               # touches as fraction
   hits.violations (v)             # bars that actually CROSS the line
   hits.bounceUp (bu)              # line touched by bar's HIGH but NOT by adjacent bar's high
   hits.bounceDown (bd)            # line touched by bar's LOW  but NOT by adjacent bar's low
   hits.bounceUpStrict (bus), hits.bounceDownStrict (bds)
   hits.bounceUpCandles (buc), hits.bounceDownCandles (bdc)
   hits.bounceUpStrictCandles (busc), hits.bounceDownStrictCandles (bdsc)
   hits.peaksUp (pu)               # bounceUp where |high[i]-high[i±1]| > 1.5*ATR(14)  ("long bar")
   hits.peaksDown (pd)             # ditto on lows.  Every peak is also a bounce.
   hits.candlesAbove (ca), hits.candlesBelow (cb)
   hits.maxConfirmatioinDistance (mcd)   # [sic — typo is in their API]
   length (l)                      # bars covered by the line
   seriesLength                    # total bars
   slopePecent                     # [sic]
   priceDeviation.p25th / p50th / p75th   # quantiles of |line - (H+L)/2| deviation %, 0..1
   linePointsBase, linePointsWeight, trendsAccumulated
   points                          # highest highs / lowest lows at window size
   points2x                        # same at window*2 (every points2x is also a point)

6. STRENGTH = mathjs.evaluate(formula, scope=above)
   Verified real TrendSpider formula (from their own find_trends example, support lines):
       'hits.candlesAbove / (hits.candlesBelow + 1)'
   Practical faithful reconstruction of "Most Relevant" behaviour:
       strength = (2*pu + bu + 0.5*n) / (1 + v) * log(1 + l) / (1 + priceDeviation.p50th)
   (their production default is not published; the variable set is, so calibrate the
    formula by matching your line set against TrendSpider screenshots)

7. RELEVANCE FILTER
   Discard lines whose current projected price is not within an ATR factor of recent
   price action ("Lines" setting). Sort by strength desc; keep top `strongestPct`;
   cap 2000.

8. BREAKOUT DETECTION
   A breakout requires ONE FULL CANDLE CLOSE through the line on that timeframe
   (5-min chart → a 5-min candle must close on the far side). Green marker = break up,
   red = break down. No wick-only breaks.

9. MTFA
   Run the whole pipeline on the secondary timeframe, then project those lines onto the
   primary chart (dashed vs solid). Do NOT recompute pivots on the primary bars.
```

**Edge cases:** volumeless symbols (fine for trendlines, fatal for Raindrop-drawn ones); `hhllWindow` must be odd if `peakIndex` unspecified; charts with zero fractal points return all-null (handle empty pivot set); log-price fitting is recommended (neurotrader takes `np.log` of data "to resolve price scaling issues") — TrendSpider does *not* appear to, which is why `slopePecent` exists as a scale-free alternative.

**Validation:** (a) reproduce `hits.*` counters against a hand-audited 200-bar window; (b) render your top-1% set next to a TrendSpider screenshot on the same symbol/TF/settings and measure line-set Jaccard overlap; (c) unit-test that no line spans a >3×ATR gap; (d) sweep `hhllWindow` 5→10→20 and confirm monotone decrease in line count (their documented behaviour).

---

### 2.2 Horizontal Support/Resistance Heatmap

TrendSpider's own words: *"Heatmaps approximate key support and resistance zones by summing all of the detected trend lines and applying an advanced heatmap generation algorithm."* Modes: **Horizontal**, **Depth**, **Trends**. Horizontal is *"calculated from an overlaid grid that calculates cells that have clusters of candles with a sequential number of highs on green candles and lows on red candles,"* then projects past confluence forward. Brighter red = more S/R.

**Spec A — faithful to their description (trend-line summation):**
```
1. Run 2.1 in "All (Unfiltered)" mode → thousands of lines.
2. Build a price grid: rows = price cells (cell height ≈ 0.25×ATR), cols = time bins.
3. For every line, for every bar it covers, accumulate weight into cell(price_of_line, t)
   weight = line.strength  (or 1 for unweighted "Depth" mode).
4. Horizontal mode = collapse the time axis at the right edge: score(priceCell) =
   Σ weights of all lines projecting into that cell now, plus candle-cluster term:
   + count of green-candle highs and red-candle lows falling in that cell (sequential runs
     weighted higher).
5. Normalize to [0,1] → alpha of red. Render as horizontal bands.
```

**Spec B — drop-in OSS equivalent (`mp_support_resist.py`, quality: faithful, and it is a *better* starting point):**
```python
# core computation, quoted verbatim
weights = first_w + np.arange(len(price)) * w_step          # recency ramp, first_w→1.0
kernal = scipy.stats.gaussian_kde(price, bw_method=atr*atr_mult, weights=weights)
price_range = np.arange(min_v, max_v, (max_v-min_v)/200)
pdf = kernal(price_range)                                   # "market profile"
peaks, props = scipy.signal.find_peaks(pdf, prominence=np.max(pdf)*prom_thresh)
levels = [np.exp(price_range[p]) for p in peaks]            # log-space → price
```
Defaults `atr_mult=3.0` (identical to TrendSpider's 3×ATR constant), `prom_thresh=0.1–0.25`, `lookback=365`, prices in **log space**, ATR computed on log H/L/C. Signal generator included: `sr_penetration_signal` = +1 on close crossing above a level, −1 below.

**Validation:** count of levels should fall as `prom_thresh` rises; levels must be stable under ±1 bar of new data (no flicker); compare level prices to TrendSpider heatmap band centres within 0.25×ATR.

---

### 2.3 Raindrop Chart (internal name: `rainfall`)

**Inputs:** the chart period P (10 min ≤ P ≤ 1 month for pattern detection; any intraday for rendering), plus **sub-period data**: 1-minute bars minimum, tick data preferred. Requires volume.

**Step-by-step (TrendSpider's 11 documented steps, formalized):**
```
For each period P = [t0, t1), midpoint tm = t0 + P/2:
  L = trades/bars in [t0, tm)          # first half
  R = trades/bars in [tm, t1)          # second half

  leftVWAP  = Σ(price_i * vol_i for i in L) / Σ(vol_i for i in L)
  rightVWAP = Σ(price_i * vol_i for i in R) / Σ(vol_i for i in R)
      # price_i = the sub-bar's typical price (hlc3/ohlc4) or trade print price
  high = max(high_i over L∪R);  low = min(low_i over L∪R)
  massCenter = Σ(price_i*vol_i over L∪R) / Σ(vol_i over L∪R)     # full-period VWAP

  # Body shape (this is what makes it a "raindrop"):
  VaP_L = histogram of Σvol by price bucket over L    # bucket = N ticks ("Ticks per bar", default 2)
  VaP_R = histogram of Σvol by price bucket over R
  Rotate each histogram 90° (price on y), repaint as an AREA chart,
  mirror L to the left of the period centre-line and R to the right, merge.
  Draw vertical line from low→high; horizontal dash at leftVWAP (left side) and
  rightVWAP (right side); dot/marker at massCenter.

  # Colour (sentiment):
  if   rightVWAP > leftVWAP + eps : GREEN  (bullish)
  elif rightVWAP < leftVWAP - eps : RED    (bearish)
  else                            : BLUE   (neutral)   # eps = "neutral tick delta", default 0
```

**Indicator plumbing (this is the real alpha of the feature):** on a Raindrop chart TrendSpider replaces the OHLC inputs everywhere downstream:
- `open  ≡ leftVWAP`
- `close ≡ rightVWAP`
- `high`, `low` unchanged
- `oc2 ≡ (leftVWAP + rightVWAP)/2`

So **every** indicator becomes volume-weighted for free. Documented example: SMA on Raindrop = 288.01 vs SMA on candles = 287.57 on the same symbol/period. Trendlines drawn with `drawingInput = Body (O/C)` on a Raindrop chart therefore become **volume-weighted trendlines** — pivots are VWAP extremes, not price extremes. This is the single cheapest high-value thing to steal: you don't need their charts, just recompute your indicators on `(high, low, leftVWAP, rightVWAP)`.

**Edge cases:** zero volume in a half-period → that side's VWAP undefined (Makit0's Pine version simply cannot run on volumeless indices); illiquid symbols make the histogram degenerate; period must be ≥ 2× the sub-bar resolution or the halves collapse; DST/session boundaries — use session-aware halving, not naive wall-clock; gaps are irrelevant (no open/close continuity).

**Validation:** on a 60-min raindrop, `massCenter` must equal the volume-weighted mean of `leftVWAP` and `rightVWAP` weighted by each half's volume; `Σ VaP_L + Σ VaP_R` must equal period volume exactly; colour must flip exactly at `rightVWAP == leftVWAP`.

---

### 2.4 Raindrop Patterns — exact published thresholds ★ free quantitative alpha

TrendSpider publishes the literal detection rules (timeframes 10 min – 1 month). "Body" = the low→high range of the drop.

```
Raindrop/Balloon      : leftVWAP > low + 0.60*(high-low)
                        AND rightVWAP > low + 0.60*(high-low)
                        AND ≥80% of the period's volume sits above 0.60 of the body
                        → volume stacked at the top of the range

Raindrop/Blue Doji    : leftVWAP == rightVWAP   (within the neutral epsilon)
                        → indecision / tight trading. ALSO used as an auto-anchor
                          point for Anchored VWAP ("Most Recent Blue Doji Raindrop").

Raindrop/Flip         : |leftVWAP - rightVWAP| ≥ 0.50*(high-low)
                        sign gives Flip Upside (green) / Flip Downside (red)

Raindrop/Double Flip  : >33% of the body lies between leftVWAP and rightVWAP, and:
   Bearish : a GREEN flip followed by a RED flip whose rightVWAP < the green flip's LOW
   Bullish : a RED flip followed by a GREEN flip whose rightVWAP > the red flip's HIGH
```
Internal naming in the white paper is `Rainfall/Flip Downside`, `Rainfall/Double Flip Downside`, etc. Raindrops are also stated to be backward-compatible with the ~100 classic candlestick patterns (Hammer, Harami, Engulfing…) since left/right VWAP substitute for open/close.

---

### 2.5 Auto-Anchored VWAP / Anchored Volume-by-Price

**Anchored indicators offered:** Anchored VWAP, Anchored Volume-By-Price, Anchored OBV, Accumulation/Distribution.

**Anchor selection (the proprietary bit) — full published rule set:**
```
Highest Volume Candle  (uses Window)
Highest High           (uses Window)
Lowest Low             (uses Window)
Blue Raindrop          → most recent Raindrop/Blue Doji  (needs 2.3/2.4)
Recent Gap             → anchors to points from their "Gap Snake" indicator
Day / Week / Month / Quarter / Year to date

WINDOW SEMANTICS (verbatim): "The amount of candles a candle must dominate over in
order to count as an appropriate anchor point." Window=5 → Williams Fractal points.
Window=20 → candle A qualifies only if no candle in the 10 to its left or 10 to its
right dominates it.  ⇒ Window is a SYMMETRIC ±Window/2 dominance test.

Continuous Mode = re-anchor at EVERY qualifying point (required for honest
backtesting — non-continuous anchors to the most recent fit only and is curve-fit).
```
Then `AVWAP(t) = Σ(price*vol from anchor→t) / Σ(vol from anchor→t)`, `price` = configurable source. Their `vwap(from_index, to_index)` signature confirms index-anchored cumulative VWAP with an optional price series and volume series: `vwap(hlc3, volume, close.length - 10)`.

**Bands:** three types — `Percentage`, `Std. deviation` (volatility bands), and **`VbP Ribbon`** (band width proportional to volume traded at that price — thicker where more volume). The VbP Ribbon is the one nobody replicates: it is `bandwidth(p) ∝ volumeAtPrice(p)` from the anchored volume profile.

**Validation:** in continuous mode, AVWAP must reset exactly on anchor bars; a "highest high, window=5" anchor set must equal `fractal_high(high, 5)` non-null indices.

---

### 2.6 Chart-pattern detectors — full parameterization

All are zigzag-based (MetaTrader-style `depth / deviation / backstep`) and OHLC-only.

```
find_head_and_shoulders(depth=11, deviation=0.01, backstep=2, inverse=false, headHeight=0)
  → { patternLine[], neckLine[],
      indexes: {start, leftShoulder, leftTrough, head, rightTrough, rightShoulder, end} }
  headHeight = minimum head height as a MULTIPLE OF THE LEFT LEG RANGE.

find_double_peak_formation(type='top'|'bottom', timeSpan='short term'|'long term', params)
  → { patternLine[], supportLine[],
      indexes:{patternStart, firstPeak, valleyFloor, secondPeak, patternLastIndex},
      firstPeakLabel, secondPeakLabel,      # "Adam" or "Eve" classification
      inForce }                             # still valid / not yet invalidated
  params (all override the timeSpan preset):
    maxDistance, minDistance                       # candles between the two peaks
    priceMaxDifferenceATR                          # peak-to-peak diff, in ATR multiples
    priceMaxDifferencePercentage                   # …or in %
    minStartValleyFloorDifference                  # ×latest ATR
    minValleyFloorPeakDifference                   # ×latest ATR
    maxHalvesRatio                                 # max (end - valleyFloor)/(valleyFloor - start)
    relevantAreaThreshold                          # outside valleyFloor↔peaks band ⇒ irrelevant
    zigzagDepth, zigzagDeviation, zigzagBackstep

find_channel(timeSpan='short', channelType)         # ascending/descending/horizontal
find_triangle(timeSpan='short', type='ascending'|'descending'|'all')
find_wedge(timeSpan, wedgeType, broadening)         # rising/falling
find_broadening(timeSpan, broadeningType, rightAngled)   # symmetrical/asymmetrical/right-angled
find_cup_and_handle(options)
```
That "Adam/Eve" peak-shape taxonomy (sharp V vs rounded U) is a genuinely proprietary classification worth copying: Adam = narrow spike peak, Eve = wide rounded peak; Adam&Eve / Eve&Adam combinations have different documented reliabilities in the pattern literature.

**Reference implementation to steal:** `neurotrader888/TechnicalAnalysisAutomation/head_shoulders.py` + `directional_change.py` (zigzag via directional-change with a σ threshold — equivalent to `deviation`).

---

### 2.7 Automated Fibonacci Retracement

```
Inputs: OHLC; drawingInput (Body O/C ⇒ body-to-body fibs, Wick H/L ⇒ wick-to-wick);
        analysisType (Original ⇒ larger inter-candle distance ⇒ measures a BIGGER swing;
                      Enhanced ⇒ smaller distance ⇒ smaller swing).
Algorithm: reuse the SAME base-point engine as 2.1 (that's why the fib inherits the
trendline drawing-input and analysis-type settings), select the "most meaningful"
high/low pair per timeframe = the highest-strength trend swing, then place standard
retracement levels between them. MTFA: secondary-TF fibs render dashed on the primary.
Alerts anchored to a specific fib level are FROZEN in price when the timeframe changes.
"Truth in Analysis" line = a vertical dotted line stamping the wall-clock time the
analysis was last computed (their anti-hindsight audit trail — worth copying).
```
Locked (non-configurable) properties: `Ext.Right`, `Lock Figure`, `Visible On` — i.e. auto-fibs always extend right and are position-locked.

---

### 2.8 Seasonality engine (their genuinely unique dataset)

```
request.seasonality(ticker, granularity, dataPoint) → { dataByCategory, sinceDate, dateFormat, categories }
  granularity ∈ {monthly, day_of_week, week_of_year, time_of_day}
  dataPoint   ∈ {change, rvol, rsi, mfi, ma20, ma50, ma100}
     change = last close vs previous close, %
     rvol   = relative volume, indicator timeframe follows `granularity`
     rsi / mfi = seasonality OF THE INDICATOR, not of price
     ma20/50/100 = seasonality of "distance from close to SMA(N)"
```
Returns **raw data points only** — `[{timestamp, value}]` bucketed by season; the *"in X% of cases this ticker was up in month Y"* summary is left to the caller. So the spec is trivial: bucket a long history by calendar key, compute the chosen statistic per bucket, then report hit-rate + mean + dispersion. The non-obvious, copyable idea is **seasonality of indicators (RVOL/RSI/MFI/MA-distance), not just of returns** — e.g. "SMH's RSI is seasonally depressed in week 38" is a far more actionable prior than "SMH is up 60% of Septembers", and it directly serves your `setup_type × régimen` calibration buckets.

---

### 2.9 Bonus: Options Map & Unusual Options (relevant to your GEX/whale stack)

**Options Map** = a strikes × expirations heatmap. Cell metrics: `Ask, Ask-Bid Spread, Bid, Delta, Delta×OI, Gamma, Gamma×OI, IV, Last, OI Change, OI, Price Change%, Put−Call IV, Put−Call OI, Put−Call Volume, P/C Ratio OI, P/C Ratio Volume, Theta, Theta×OI, Vega, Vega×OI, Volume Today, Volume/OI`. Colour normalization: `Entire Grid | By Strike (row) | By Expiration (column)`. Totals row per expiration + totals column per strike (suppressed for non-aggregatable metrics). **Greeks and IV are Black-Scholes** (stated explicitly). Note: `Gamma × OI` totals-by-strike *is* a GEX-by-strike wall map — same object as your `gex_core`, minus the dealer sign convention. TrendSpider does **not** publish a gamma-flip / vol-trigger / vanna / charm metric — they stop at the raw greek×OI surface, so your existing gamma stack is already ahead of them here.

**Unusual Options** records (delayed ≤5 min, last 300 per ticker):
```json
{"timestamp":…, "costBasis":31200, "dealType":"TRADE", "assetPrice":171.465,
 "strike":200, "type":"CALL", "oi":5156, "moneyStatus":"OTM",
 "expDate":…, "daysToExp":414, "size":30, "oiPercent":0.58,
 "tags":["trade","bearish","stock","at_bid","call","otm"]}
```
Filterable on `timestamp, expDate, daysToExp, strike, type, costBasis, oi, tags`. The `at_bid` / `bearish` tags = **signed trade classification** (Lee-Ready style bid/ask side assignment) plus `size` and `costBasis` — i.e. exactly the whale-flow primitive your `opt_whale_watch` uses. `oiPercent = size/oi` is their "unusualness" ratio.

Also available and cheap to consume: `request.dark_pool()`, `request.short_volume()` (FINRA Reg SHO), `request.retail_trading()`, `request.market_breadth()` (8 data types × 120+ universes), `request.relative_performance(ticker, 'yearly'|'quarterly'|'techrank', 'spx500'|'russell2000'|'same_sector'|'same_mktcap'|'same_sector_mktcap')`, `request.congress_trading()`, `request.wallstreetbets()`, `options.compute_greeks()`, `options.compute_option_price()`.

---

## 3. Published empirical evidence (with numbers)

**On TrendSpider's own metrics — the honest answer is: essentially none, and their own white paper shows a negative.**

| Evidence | Numbers |
|---|---|
| **TrendSpider's own Raindrop white paper**, "Price Behavior Explorer" page | Entry = `30-min Rainfall/Double Flip Downside (Evolved)` AND `close > BB(20,2,2,oc2) mid`. Result: **66 positions over 10 months of MCD data (2816 candles), mean trade return −0.16%**, mean-change curve drifting negative vs the plotted "Random Control". Published by TrendSpider itself. There is no positive-hit-rate study for any Raindrop pattern anywhere. |
| Independent Raindrop backtests | **None found.** No academic paper, no quant blog with numbers, no r/algotrading thread with a reproducible test. |
| **Support/resistance predictive power — Osler (2000), FRBNY Econ. Policy Review 6(2):53-68** | Bounce rate off *published* S/R levels **60.8%** vs **56.2%** off arbitrary levels (**+4.6pp**). By currency: +4.2pp mark, +5.6pp yen, +4.0pp pound. Statistically significant in **9 of 16** firm-currency pairs. Predictive power persists **≥5 business days** after publication. Round numbers: 96% of published levels end in 0 or 5, 20% in 00; round-number effect worth ~+3.4pp in simulation vs +4.6pp observed. **Read: the real edge over a coin flip is ~4-5 percentage points, and part of it is just round numbers.** |
| **ML with engineered S/R features — MDPI *Mathematics* 10(20):3888 (2022)** | Adding automated support/resistance features raised model **profitability by 65%** across 8 currency pairs vs the same models without them. |
| **Chart patterns — Lo, Mamaysky & Wang (2000), J. Finance 55:1705-1765** | Kernel-regression automated pattern detection on US stocks 1962-1996: H&S, double bottoms etc. **do carry incremental information** (statistically), strongest in small caps. Their own caveat: *patterns optimal for detecting statistical anomalies need not be profitable, and vice versa.* |
| **Head & shoulders — Osler (1998)** | H&S has **no predictive power in US equities**; H&S traders are classifiable as **noise traders generating unprofitable order flow**. Profitable for USD/DEM and USD/JPY but not 4 other currencies. Follow-up: Savin, Weller & Zvingelis, *J. Financial Econometrics* 5(2):243 — "Predictive Power of H&S Price Patterns in the US Stock Market" — finds some predictive power for S&P500/Russell2000 with a properly automated detector. |
| **Automated trendline slopes** | `neurotrader888`'s public work (570★) fits support/resistance slopes and *plots* them as features; the repo ships no profitability claim. Treat trendline slope as a **regime feature**, not a signal. |
| Your CLAUDE.md-relevant cross-check | Independent trendline/pattern follow-through rates in your own `pattern_detect.py` (~<50%) are **consistent** with this literature. TrendSpider's marketing claim of "mathematical precision → more accurate than eyeballing" has **no published test behind it**. |

**Verdict for the house:** the *engine* is worth cloning (it's a fast, well-specified, ATR-normalized level generator); the *patterns* are not signals. Use auto-trendlines/heatmaps exactly the way your doctrine already uses OI walls: as printed levels with measured bounce probabilities, expecting a real edge in the **+4 to +5 percentage point** range over random levels — not 70%.

---

## 4. DATA REQUIREMENTS

| Metric | Required feed | Granularity / frequency | Notes |
|---|---|---|---|
| Automated trendline detection + scoring | **OHLC only** (chart timeframe) | Bar close on the chart TF; recompute on each new bar | No volume, no tape, no options. ATR(14) derived. Cheapest high-value item — you can build this today from IBKR/yfinance bars. |
| Breakout detection | OHLC of the same TF | Bar close only (full candle close required) | Explicitly *not* tick — no wick breaks. |
| Horizontal / Depth / Trends S/R Heatmap | OHLC (+ candle colour ⇒ needs open) | Chart TF; rolling lookback (365 bars in the OSS analogue) | KDE over log-close, bandwidth 3×ATR. |
| Auto Fibonacci | OHLC | Chart TF | Shares the trendline base-point engine. |
| Chart patterns (H&S, double top/bottom, channels, triangles, wedges, broadening, cup&handle) | OHLC | Chart TF | ZigZag(depth, deviation, backstep) + ATR-multiple tolerances. |
| **Raindrop chart (left/right VWAP + body)** | **Intraday sub-period data with volume**: 1-minute bars *minimum*, **tick prints preferred**. Per-print: price + size + timestamp. | Must be ≥ ~2 sub-bars per half-period. Rendering TF 1 min → 12 h (Makit0); patterns 10 min → 1 month | **Hard requirement.** No exchange-tag or side classification needed. **Fails entirely on volumeless indices** (use ETF proxies: SPY/QQQ not SPX/NDX). |
| Raindrop patterns (Balloon / Blue Doji / Flip / Double Flip) | Same as Raindrop + the per-half volume-at-price histogram (Balloon needs the 80%-of-volume-above-60%-of-body test) | Per period, TF ≥ 10 min | Volume-at-price bucket size = N ticks (default 2). |
| Volume-weighted indicators (any indicator on Raindrop inputs) | Raindrop series `(high, low, leftVWAP, rightVWAP)` | Per period | Zero extra data beyond the Raindrop feed. |
| Anchored VWAP / VbP / OBV / A-D | OHLCV with volume; anchor detection needs the same OHLCV (+ Raindrop feed if anchoring to Blue Doji) | Chart TF; cumulative from anchor | Continuous mode mandatory for honest backtests. |
| Gap Snake / island segmentation | OHLC (needs open vs prior close) | Chart TF | Gap if `|open − prevClose| > 3×ATR(14)`. |
| Seasonality (change / rvol / rsi / mfi / ma20-50-100) | Long history: daily for monthly/DoW/WoY; **intraday bars for `time_of_day`** | Multi-year (their samples run to ~20 yr); recompute daily | Raw per-season points; you compute the summary. |
| Relative performance / TechRank | Full cross-section of the universe (SPX500 / R2000 / sector / mktcap peers) | Daily | Requires a universe snapshot, not a single ticker. |
| Market breadth (A/D etc.) | Constituent-level daily data for 120+ universes | Daily | Your `index_breadth.py` already does the weighted version. |
| Options Map (Delta/Gamma/Vega/Theta ×OI, IV, Volume/OI, P/C ratios) | **Full option-chain snapshot**: all strikes × all expirations, bid/ask/last/volume/OI. Greeks computed locally via Black-Scholes | Snapshot; intraday refresh (their OI Change implies ≥daily OI deltas). **OPRA entitlement; single device at a time** | Options-on-futures NOT covered; CBOE index options ($SPX) ARE. Same feed your IBKR `opt_chain_<sym>.txt` cache provides. |
| Unusual Options / whale flow | **Intraday option TRADE tape with size + cost basis + OI + side classification** (`at_bid`/`at_ask` ⇒ signed) + moneyness | Per print, ≤5 min delayed, last 300 per ticker | This is the only feed here needing signed trade classification. Equivalent to your existing whale watcher's input. |
| Dark pool volume | FINRA ATS aggregate | **Weekly granularity, delayed 3–5 weeks** | Effectively useless for timing; regime context only. Their DWM volume already includes dark-pool prints. |
| Short volume | FINRA Reg SHO | Daily, US equity only | |
| Retail trading activity / WSB mentions / Congress trading / Insider / Analyst ratings / Earnings / Dividends / Splits / FRED / Crypto F&G | Vendor alt-data endpoints | Daily→event-driven | All available via their `request.*` API if you ever hold a subscription. |

---

## 5. Artifacts on disk (all absolute paths)

Working directory: `/private/tmp/claude-502/-Users-yuniorrodriguezosorio/76ae049f-f97e-4afe-8984-bd226d4c93ba/scratchpad/ts/`

- `api.md` — **175 KB: TrendSpider's complete JS API reference.** The single most valuable file. `find_trends` at line 4645, `find_double_peak_formation` 4511, `find_head_and_shoulders` 4596, `fractal_high/low` 813/851, `vwap` 889, `twap` 4947, `compute_band` 4298, `request.seasonality` 3855, `request.unusual_options` 3567, `options.compute_greeks` 4035.
- `addser.md` — data-access doc (`request.history`, `land_points_onto_series`, alt-data catalog).
- `formulas.html` — custom trend-line scoring formula KB page (mathjs catalog + all 13 primary variables).
- `nt_trendline.py`, `nt_mp.py` — neurotrader888's trendline optimizer and KDE market-profile S/R (the two best OSS drop-ins).
- `src_swings_detector.py`, `src_trendlines_fitter.py`, `src_trendlines_scorer.py`, `src_elliott_rules.py`, `src_elliott_fibonacci.py`, `README.md` — the "free TrendSpider clone" Python engine.
- `izigzag.js` — Trendoscope's zigzag written in TrendSpider's own JS dialect (working API example, MPL-2.0).
- `raindrops.pdf` + `wp_01.jpg … wp_32.jpg` — the Raindrop white paper and all 32 extracted page images (image-only scan; `wp_03.jpg` = the definitional page, `wp_29.jpg` = the −0.16% / 66-position backtest).
- `x.py` — the KB text-extraction helper used throughout (reusable for any help.trendspider.com page).

**Recommended build order for maximum value per hour:** (1) §2.3 Raindrop `(high, low, leftVWAP, rightVWAP)` series from your existing 1-min IBKR bars → instantly volume-weights every indicator in the fleet, zero new data; (2) §2.1 trendline engine with mathjs-equivalent scoring, feeding your printed-level discipline; (3) §2.2 KDE heatmap as a second, independent opinion on your OI walls; (4) §2.8 indicator-seasonality to enrich the `setup_type × régimen` calibration buckets. Skip Raindrop *patterns* as triggers — their own white paper reports a losing expectancy.

Sources: [TrendSpider JS API](https://charts.trendspider.com/scripting/docs/api.md) · [Custom trend line formulas](https://help.trendspider.com/kb/automated-technical-analysis/custom-trend-line-formulas) · [Automated trendline detection](https://help.trendspider.com/kb/automated-technical-analysis/automated-trendline-detection) · [Trendline analysis settings](https://help.trendspider.com/kb/automated-technical-analysis/trend-analysis-settings) · [Breakout detection](https://help.trendspider.com/kb/automated-technical-analysis/breakout-detection) · [Horizontal S/R heatmaps](https://help.trendspider.com/kb/automated-technical-analysis/horizontal-support-and-resistance-heatmaps) · [Automated Fibonacci](https://help.trendspider.com/kb/automated-technical-analysis/automated-fibonacci-retracements) · [MTFA](https://help.trendspider.com/kb/automated-technical-analysis/multi-timeframe-analysis) · [How Raindrops are rendered](https://help.trendspider.com/kb/raindrop-charts-tm/how-raindrops-are-rendered) · [Raindrop chart patterns](https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-pattern) · [Raindrop volume weighting](https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-volume-weighting-effects-on-indicators-and-auto-trendlines) · [Raindrop white paper PDF](https://trendspider.com/whitepapers/raindrops_280519.pdf) · [Anchored indicators 101](https://help.trendspider.com/kb/indicators/anchored-indicators-101) · [Options Map](https://help.trendspider.com/kb/options-data/options-map) · [Dark pool data](https://help.trendspider.com/kb/other-data-types/dark-pool-data) · [neurotrader888/TechnicalAnalysisAutomation](https://github.com/neurotrader888/TechnicalAnalysisAutomation) · [jinhae8971/trendline-detector](https://github.com/jinhae8971/trendline-detector) · [trendoscope-algorithms/trendspider](https://github.com/trendoscope-algorithms/trendspider) · [bondjames12/trend-spider-indicators](https://github.com/bondjames12/trend-spider-indicators) · [drgoose23/trendspider_scripts](https://github.com/drgoose23/trendspider_scripts) · [maikokuppe/trendspider-indicators](https://github.com/maikokuppe/trendspider-indicators) · [MikeI-Code/Trendspider-BOS](https://github.com/MikeI-Code/Trendspider-BOS) · [donoage/moe-bot-trendspider-data](https://github.com/donoage/moe-bot-trendspider-data) · [TrendSpider GitHub org](https://github.com/TrendSpider) · [vincenzo5/Edge roadmap](https://github.com/vincenzo5/Edge) · [Waindrops [Makit0] Pine](https://www.tradingview.com/script/dJr8hv4v-Waindrops-Makit0/) · [Raindrop Candles (Zeiierman)](https://www.tradingview.com/script/UTH5wdpT-Raindrop-Candles-Zeiierman/) · [RainDrop Panel](https://www.tradingview.com/script/lw7DKpOG/) · [Auto Trend Lines v1.0](https://www.tradingview.com/script/X9KGemzG-Auto-Trend-Lines-v1-0/) · [Trendline Detector 3TF](https://www.tradingview.com/script/SB0Y7c9Y-Trendline-Detector-3-Timeframes/) · [HarryBot trendline gist](https://gist.github.com/immusen/c4c60952bb3b8da4079cde81ca080dfb) · [Osler 2000, Support for Resistance](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=888805) · [MDPI Mathematics 10(20):3888](https://www.mdpi.com/2227-7390/10/20/3888) · [Lo, Mamaysky & Wang 2000](https://www.nber.org/papers/w7613) · [Savin, Weller & Zvingelis, JFEC 5(2)](https://academic.oup.com/jfec/article-abstract/5/2/243/785044)