# TrendSpider — Technical Dossier on Proprietary Features & Underlying Math

Research date: 2026-07-25. Primary sources: `help.trendspider.com` knowledge base (the real documentation), the 2019 Raindrop white paper (PDF, decoded from `https://trendspider.com/whitepapers/raindrops_280519.pdf`), TrendSpider blog/learning-center, store indicator pages, pricing matrix. Confidence tags: **HIGH** = stated in vendor docs; **MEDIUM** = third-party/blog explanation or partial doc; **LOW** = inferred/reconstructed by me.

---

## PART 1 — CATALOGUE OF FEATURES / METRICS / ENGINES

### A. Automated Technical Analysis engine (the original moat)

**1. Automated Trendline Detection**
- *What*: Server/client-side enumeration of **all** geometrically possible trendlines on a chart, then filtering + scoring down to the "Most Relevant" ~1%.
- *Inputs*: full OHLC series for the chart timeframe; `Base Points` (min candle separation between two connection points, set **per timeframe** — e.g. "10 candles apart" on Daily); `Drawing Input` = Wick (H/L) or Body (O/C); `Analysis Type` = Original / Standard / Enhanced (trend sensitivity); `Islands` = Respect / Ignore gaps; ATR(14) factors per resolution; on Raindrop charts, left/right VWAP can replace H/L.
- *Algorithm (reconstructed from docs)*:
 1. Detect candidate pivots ("reaction highs and lows") via a window/dominance rule; `points` = "highest highs or lowest lows calculated at the given window size", plus `points2x` at 2× window.
 2. Enumerate lines through pairs of pivots subject to `BasePoints` minimum horizontal separation (higher base points ⇒ fewer lines).
 3. Hard filter: dismiss any line whose distance from the **last price** exceeds `ATR_length × ATR_factor` — docs say "each number is a factor of the **14-period ATR** for a specific resolution". Larger factor ⇒ more lines survive.
 4. If Islands = Respect, forbid lines spanning a detected gap.
 5. Score every survivor with the sorting formula (see #2); keep top 1% ("Most Relevant"), or looser ("More Lines"), or all (cap ≈ **2,000 lines**).
- *Decision rule*: surviving lines are treated as live S/R; you then hang Dynamic Alerts on them (break/touch/bounce).
- *Confidence*: HIGH for parameters and pipeline, MEDIUM for pivot detection specifics.
- *Sources*: https://help.trendspider.com/kb/automated-technical-analysis/automated-trendline-detection , https://help.trendspider.com/kb/automated-technical-analysis/trendline-customization-and-filtering , https://help.trendspider.com/kb/automated-technical-analysis/customization-and-tuning , https://help.trendspider.com/kb/advanced-customization-settings/trend-analysis-settings

**2. Custom Trend-Line Scoring / Sorting Formula engine ← the single most valuable disclosed math**
- *What*: A user-editable expression language that ranks candidate trendlines. TrendSpider exposes the exact **variables** its own ranking uses.
- *Variables (verbatim definitions from docs)*:
 - `length` — number of bars covered by the line
 - `seriesLength` — total bars in the series
 - `priceDev25 / priceDev50 / priceDev75` — 25th/50th/75th quantile of **deviation percentage between the trend line and (H+L)/2**, range 0→1
 - `hits` — number of highs or lows touching the line
 - `points` — highest highs / lowest lows at the given window size; `points2x` — same at window × 2
 - `bounceUp` / `bounceDown` — a touch where the *adjacent* bar does **not** touch (i.e. a clean rejection), up/down side
 - `peaksUp` / `peaksDown` — a touch by a **long bar**, defined as bar range difference **> 1.5 × ATR(14)**
 - `violations` — number of bars that actually cross the line
- *Functions available*: add/subtract/multiply/divide/mod/pow/abs/sign; sqrt/square/cube/cbrt/nthRoot/exp/expm1; ceil/floor/fix; gcd/lcm; log/log2/log10/log1p; **mean, median, mode, std, variance, mad, min, max, sum, prod, quantileSeq**; full trig/hyperbolic set; dotMultiply/dotDivide/dotPow (i.e. it's a math.js-style evaluator).
- *Where*: `…` button → Advanced → **Trends** tab → Add → field "new type".
- *Decision rule*: highest-scoring 1% render as actionable S/R.
- *My defensible approximation of the default score* (LOW confidence, but consistent with every documented statement — "count how many times each trendline had a bounce or a breakthrough"):
 `score ≈ [ (hits + w_b·(bounceUp+bounceDown) + w_p·(peaksUp+peaksDown)) / (1 + violations) ] · (length/seriesLength)^α · 1/(1+priceDev50)` with `w_b ≈ 1`, `w_p ≈ 2`, `α ∈ [0.25, 1]`. Note `priceDev*` in the denominator is what makes a line "tight" rather than merely long.
- *Confidence*: HIGH on variables/functions/UI path; LOW on the default expression itself (never published).
- *Source*: https://help.trendspider.com/kb/advanced-customization-settings/custom-trend-line-formulas

**3. Gap / "Islands" detection**
- *What*: Detects price gaps, forbids trendlines crossing them, paints them as colored bars along the chart bottom.
- *Inputs*: ATR window (default 14) + minimum ATR multiple.
- *Computation*: gap is flagged when the discontinuity between consecutive periods ≥ **k × ATR(14)**, documented default **k = 3**. Smaller k ⇒ more gaps.
- *Decision rule*: gaps are S/R magnets; trendlines don't span them (when "Respect"); gaps also feed anchoring ("Recent Gap") and the Gap Proximity scan condition.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/automated-technical-analysis/customization-and-tuning , https://help.trendspider.com/kb/automated-technical-analysis/types-of-automated-analysis

**4. Gap Detector indicator / 5. Gap Proximity indicator**
- *Gap Detector*: parameter `Gap Factor` (inverse sensitivity — larger ⇒ fewer gaps; commonly cited default 0.5). Cannot be used in visual scripting — hence Gap Proximity exists as the scriptable sibling.
- *Gap Proximity*: inputs `Gap Factor`, `Band Type` ∈ {ATR, Standard Deviation, Constant, Percentage}, `Band Length`, `Band Mult`. Output = distance of current price to the nearest historical gap, expressed in band units. Decision rule: "price is inside/near an unfilled gap" → scannable condition for gap-fill trades.
- *Confidence*: HIGH on parameters, LOW on exact formula (undisclosed). Best approximation: `proximity = (price − gapEdge) / (Band(BandLength) × BandMult)`.
- *Sources*: https://help.trendspider.com/kb/indicators/gap-detector , https://help.trendspider.com/kb/indicators/gap-proximity

**6. Automated Fibonacci Retracements ("dynamic fibs")**
- *What*: Auto-selects the swing anchor pair per timeframe and draws fib levels; recalculates with the analysis refresh.
- *Inputs*: Drawing Input (Wick-to-Wick vs Body-to-Body); Analysis Type (Original = larger swing distance, Enhanced = smaller/granular); user-checkable level set.
- *Computation*: same pivot machinery as trendlines picks "the most meaningful Fibonacci connection points on each timeframe"; levels = standard retracement ratios applied between chosen high/low. Level list is user-toggled (defaults not published).
- *Decision rule*: confluence of auto-fib level + auto-trendline + heatmap hot cell = high-probability reaction zone.
- *Confidence*: HIGH for mechanism, LOW for the anchor-selection objective function and default level set.
- *Source*: https://help.trendspider.com/kb/automated-technical-analysis/automated-fibonacci-retracements

**7. Horizontal Support/Resistance Heatmap**
- *What*: Density map of horizontal S/R.
- *Computation (verbatim)*: "an overlaid grid that calculates cells that have **clusters of candles with a sequential number of highs on green candles and lows on red candles**"; an "advanced heatmap generation algorithm" sums detected trend lines and projects the zones. Brighter red = more confluence; unshaded = path of least resistance.
- *Decision rule*: trade toward unshaded corridors, expect reaction at bright cells.
- *Confidence*: MEDIUM (rule stated but thresholds and normalization not published).
- *Source*: https://help.trendspider.com/kb/automated-technical-analysis/horizontal-support-and-resistance-heatmaps

**8. Depth Heatmap / 9. Trends (price-confluence) Heatmap**
- *Computation (HIGH)*: a **fixed 40 × 60 cell grid** overlays the region between Truth-in-Analysis lines; the "heat" of a cell = **number of detected trendlines crossing that cell** (equivalently number of line-points in the cell). **Depth** additionally applies a gradient bleed to neighbouring cells (smoothing); **Trends** shows raw counts with no bleed.
- *Constraints*: requires manual refresh; **does not work on logarithmic scale**.
- *Decision rule*: cell brightness ⇒ expected friction; use as a probabilistic S/R field rather than discrete lines.
- *Sources*: https://help.trendspider.com/kb/automated-technical-analysis/heatmaps-399dc166f3dc428e , https://help.trendspider.com/kb/automated-technical-analysis/heatmaps

**10. Truth-in-Analysis Timestamp (anti-repaint device)**
- *What*: A vertical dotted line marking the instant the automated analysis (trendlines, auto-fibs, heatmaps) was computed; it **freezes** them so they cannot silently repaint as bars arrive.
- *Mechanics*: "Refresh & Lock" recomputes and re-locks at now. Yellow/blue line = locked; red = unlocked/live. If locked analysis scrolls out of range the chart auto-reverts to live mode.
- *Decision rule*: any signal must be judged against the analysis as of its lock time — this is TrendSpider's explicit stance against look-ahead/repaint bias in discretionary chart work.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/automated-technical-analysis/truth-in-analysis-timestamp

**11. Multi-Timeframe Analysis (MTFA) on one chart**
- *What*: Projects a **secondary** timeframe's objects onto the primary chart: auto-trendlines, manual drawings, upper/lower indicators, auto-fibs, candlestick patterns.
- *Mechanics*: primary = solid lines, secondary = **dashed**. Timeframes 1-minute → Monthly; up to 5 favourite MTF slots in the timeframe menu. In cross-timeframe comparisons elsewhere in the platform (alerts/scanner) TrendSpider explicitly "uses the **last calculated data point on the larger time frame**" — i.e. step-hold of the HTF value, no interpolation.
- *Decision rule*: trade the LTF entry only in the direction sanctioned by the dashed (HTF) structure.
- *Confidence*: HIGH for rendering rules; MEDIUM for the alignment rule (documented in the alerts KB, applied by analogy to chart MTFA).
- *Sources*: https://help.trendspider.com/kb/automated-technical-analysis/multi-timeframe-analysis , https://help.trendspider.com/kb/alerts/multi-factor-alerts-overview , https://help.trendspider.com/kb/charting/chart-timeframe-menu-and-favorite-timeframes

---

### B. Raindrop Charts® — full construction math (white paper decoded)

**12. Raindrop Chart construction**
- *What*: A "human-friendly Volume Profile chart" invented by **Ruslan Lagutin (CTO), Oct 2018**, published as a white paper 2019-05-28. Each bar has **four data points — Left Mean, Right Mean, High, Low — and a body**; there is **no open and no close** (deliberately: "open/close prices are actually random and arbitrary numbers, formed more by the passage of time than anything meaningful in the data").
- *Inputs*: the bar period (e.g. 60m) and **the most granular data available — 1-minute candles or tick data**.
- *Exact construction (verbatim 11-step algorithm from white paper + KB)*:
 1. Choose period P and take the first period window (e.g. Mon 08 Oct 09:30–10:30 EST).
 2. Take the **second half** of P; build a **Volume-at-Price histogram** from the granular sub-data.
 3. Rotate the histogram 90° (respecting price-axis direction).
 4. Re-paint it as an **area chart** → this is the **right** half of the drop.
 5. Repeat 2–4 on the **first half** of P → **left** half.
 6. Join left+right into one Raindrop. *Width at any price level ∝ volume transacted at that price; both sides use the same scale so they are directly comparable.*
 7. Plot the **mass-center** point = the volume-weighted price of the whole period.
 8. Draw a vertical line for High/Low of P.
 9. Draw **dashed lines** on left and right = the **VWAP of that half-period**:
 `LeftMean = Σ(p·v) / Σv over first half`, `RightMean = Σ(p·v) / Σv over second half`.
 10. Colour: `Left > Right → RED`; `Right > Left → GREEN`; `Left == Right → BLUE`.
 11. Repeat for remaining periods.
- *Decision rule*: green = sentiment migrated up within the bar (bullish), red = down, blue = true balance/indecision (rare; flagged as a potential S/R zone and used as an auto-anchor). Bar *shape* (where the mass sits, left vs right thickness) is the actual signal, not the colour alone.
- *Author's own caveat*: raindrops likely lose utility at **higher timeframes (≥45m)** because sentiment can flip more than once inside the bar — "more research needed".
- *Confidence*: HIGH (primary source, verbatim).
- *Sources*: https://trendspider.com/whitepapers/raindrops_280519.pdf , https://help.trendspider.com/kb/raindrop-charts-tm/how-raindrops-are-rendered , https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-charts

**13. Raindrop-native indicator & trendline math (volume-weighted everything)**
- *What*: Because there is no O/C, every indicator on a raindrop chart is recomputed from `{High, Low, RightVWAP, LeftVWAP, or the average of the two means = "central calculated point"}`. "TrendSpider always calculates indicators from the exact chart type that is displayed under them."
- *Effect (documented example)*: SMA on raindrops = **288.01** vs **287.57** on candles for the same symbol/period — i.e. a real, measurable volume-weighting shift.
- *Trendlines*: can be drawn from left/right VWAP or the central point instead of H/L ⇒ **volume-weighted trendlines**.
- *Decision rule*: using central/left/right mean converts any classic indicator into a volume-weighted version; treat crossovers as VWAP-of-sentiment crossovers, not price crossovers.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-volume-weighting-effects-on-indicators-and-auto-trendlines , white paper pp.6–7

**14. Raindrop pattern taxonomy (with the only published numeric thresholds)**
| Pattern | Definition (verbatim/near-verbatim) | Reading |
|---|---|---|
| **Flip** | "Left price stands apart from Right by **at least 50% of a drop's body**" | Upside flip = bullish, downside = bearish |
| **Double Flip** | "Upside flip followed by downside flip, **flip depth 33%** (instead of 50% for single Flip)"; >33% of body between L and R | Momentum reversal sequence; bearish version = declining lows across flips |
| **Blue Doji** | Left VWAP == Right VWAP exactly | True consensus/indecision; candidate S/R zone; used as auto-anchor |
| **Raindrop/Balloon** | Left and Right VWAP both **above 60% of the body**, and **≥80% of the candle's volume resides above 60% of the body** | Concentrated buying in upper range = bullish |
| **Baguette** (white paper #5) | Thick, even, long drop; L and R means close; volume ~uniform at all prices, no peak | Wide range with no consensus; rare |
| **Long tail drop** (#4) | Wide range but volume concentrated in a tight sub-range; mean sits inside the dense histogram | Tail is noise; the dense zone is the real level |
- *Backtest status*: the white paper's Appendix B contains only illustrative examples (AAPL,30 / KO,30 / MCD,30) — **no win-rate statistics were ever published**. Section "Research" explicitly asks the community to backtest Flip, Double Flip, Doji, Baguette.
- *Confidence*: HIGH for definitions; the reliability numbers simply do not exist publicly.
- *Sources*: https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-pattern , white paper pp.4–5, 12–13

---

### C. Anchored & volume tooling

**15. Anchored Indicators engine (AVWAP and friends)**
- *Indicators*: **Anchored VWAP, Anchored Volume-by-Price, Anchored OBV, Accumulation/Distribution Line** (all cumulative, so the anchor matters).
- *Auto-anchor point types*: Year/Quarter/Month/Week/Day-to-date; **Highest High**, **Lowest Low** (each with a `window` parameter = "the amount of candles a candle must dominate over"); **Highest Volume Candle**; **Recent Gap**; **Blue Raindrop** (most recent raindrop-doji).
- *Modes*: **Non-continuous** (default) anchors to the most recent qualifying point only; **Continuous** re-anchors at *every* qualifying point (required for backtesting). Continuous is **disallowed for Highest High / Lowest Low / Highest Volume** because their window is forward-looking — an explicit look-ahead-bias guard.
- *Computation*: `AVWAP_t = Σ_{i=anchor..t}(p_i·v_i) / Σ_{i=anchor..t} v_i`, reset at each new anchor in continuous mode.
- *Decision rule*: price above AVWAP-from-event = buyers from that event are in profit ⇒ trend intact; the anchor library is the point (gap-anchored, volume-spike-anchored, blue-doji-anchored).
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/indicators/anchored-indicators-101

**16. Volume by Price (VbP) / Volume Profile**
- *Inputs*: `Columns` = number of price sections the range is split into (bin count); anchor option (YTD, recent gap, highest volume, month start…); Bull/Bear colours.
- *Outputs*: **POC** = price level with most activity; **Value Area = 70% of traded volume**, with **VAH/VAL** boundaries; **ΔVolume** = green-candle minus red-candle volume per bin; **Pyramid Mode** (manual VbP) splits bullish volume left / bearish right.
- *Decision rule*: POC = magnet; VA edges = rotation boundaries; low-volume voids = fast-travel zones.
- *Note*: **no TPO / Time-Price-Opportunity** implementation is documented. **Renko and Point & Figure are NOT supported chart types** (chart types = Line, Bars, Candles, Hollow Candles, **Raindrop**, Heikin Ashi).
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/indicators/volume-by-price , https://help.trendspider.com/kb/charting/chart-settings-and-customization

---

### D. Pattern recognition

**17. Automated Candlestick Pattern Recognition**
- Single- and multi-candle formations detected on any timeframe and auto-labelled; works on candles, Heikin Ashi **and Raindrops** ("raindrops are backwards-compatible with most Japanese candlestick formations"). In scripting the operator is **`Evolved`** = "triggers when the last candle of a given pattern finalizes".
- *Confidence*: HIGH for behaviour; the per-pattern geometric tolerances are not published (LOW).
- *Sources*: https://help.trendspider.com/kb/automated-technical-analysis/types-of-automated-analysis , https://help.trendspider.com/kb/alerts/create-a-new-multi-factor-alert-from-scratch

**18. Automated Chart Pattern Recognition (13 patterns) + actionability filter**
- *Patterns*: Ascending / Descending / Symmetrical Triangle; Double Top; Double Bottom; Horizontal / Ascending / Descending Channel; Head & Shoulders; Inverse H&S; Rising Wedge; Falling Wedge; Cup & Handle.
- *Per-pattern settings*: `Time Span` (Short/Long Term) on all; Double Top/Bottom add `Type` = All | **Confirmed** (neckline broken), `Max peak distance (ATR)`, `Max peak distance (%)`, `Retracement`; Cup & Handle adds `Inverted`, `Bands`; H&S adds the ZigZag set (see #19).
- *Discard/actionability rules (the real differentiator, verbatim-ish)*: patterns are removed when in "very early stages", "no longer respected by price action", or already "played out"; **triangles** are dropped when the **apex is too far in the future or too deep in the past**; **channels/wedges** are dropped once price leaves and travels too far; **Double Top/Bottom** kept only if fully formed and never invalidated, or still developing; **H&S** discarded when a new pattern emerges or "price never goes below neck line after shoulder 2"; **Cup & Handle** discarded when the handle extends too far. Nothing is drawn purely historically.
- *Decision rule*: pattern presence = context; the scannable trigger is the **breakout/breakdown + retest** condition pair that ships pre-built.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/automated-technical-analysis/automated-chart-pattern-recognition

**19. Head & Shoulders detector (explicit ZigZag parameterization)**
- *Inputs / meaning*: `Depth` = "number of candles without a second maximum or minimum deviation of the previous pivot" (larger ⇒ wider-spaced pivots ⇒ older patterns found); `Deviation` = required vertical distance from the previous pivot (higher ⇒ deeper troughs); `Back Step` = bars required before the pattern may change direction; `Head Height` = allowed % distance between head and left shoulder (default "Any", plus 4 presets); `Bands` = tolerance envelope around shoulder/head/neckline levels measured in **ATR, Standard Deviation, Constant, or Percentage**; `Retracement` = auto-fib on a chosen leg (Left Leg, Left Trough-Shoulder, Left Trough-Head, Right Trough-Head, Right Trough-Shoulder, Right Leg).
- *Construction*: neckline = line through the two trough lows between shoulders and head.
- *Decision rule*: pre-built scan conditions for **H&S breakdown / retest** and **inverse H&S breakout / retest**.
- *Confidence*: HIGH (this is effectively a documented ZigZag(Depth, Deviation, BackStep) pivot engine + geometric constraints, i.e. reimplementable).
- *Sources*: https://help.trendspider.com/kb/automated-technical-analysis/automated-chart-pattern-recognition , https://trendspider.com/blog/next-level-intelligence-automated-head-and-shoulders-pattern-recognition/

**20. Divergence detection (RSI Divergences)**
- Ships via the store/community rather than as core auto-analysis: connects price peaks/troughs to oscillator peaks/troughs, labels **Regular Bullish / Hidden Bearish** etc., green/red, plus an RSI Divergence **scanner**. Pivot detection is the same class of ZigZag problem; thresholds are per-script.
- *Confidence*: MEDIUM (store pages + blog), LOW on formulas.
- *Sources*: https://trendspider.com/trading-tools-store/indicators/689ab4-rsi-divergences-tsbuild25/ , https://trendspider.com/blog/a-practical-guide-to-screening-for-and-trading-bullish-divergences/

**21. Market Wave Trend & Signals (wave/trend-phase detection, store indicator)**
- *Mechanism as described*: volatility-adjusted averaging builds a "Wave" baseline + an adaptive channel that expands/contracts with volatility (functionally a Keltner/SuperTrend-family construct). A decisive close beyond the band = trend-phase change. A **signal-grading engine** separates standard signals (triangles) from **"Power" signals** (bold arrows) requiring secondary confirmation from **volume flow + relative strength**; a `Momentum Filter` suppresses signals below internal volume/oscillation thresholds. TP1/TP2/MaxProfit computed from volatility at trend onset.
- *Params*: `Wave Length`, `Sensitivity Factor`, momentum filter toggle.
- *Confidence*: MEDIUM on mechanism, LOW on formula. Defensible approximation: `Wave = EMA/ALMA(price, WaveLength)`, bands `= Wave ± SensitivityFactor × ATR(WaveLength)`, Power = band break AND volume z-score > 0 AND RP/relative-strength > benchmark.
- *Source*: https://trendspider.com/trading-tools-store/indicators/698789-market-wave-trend-signals/

---

### E. Alerts, scripting, scanning

**22. Dynamic Price Alerts (the flagship invention: alerts that ride a line)**
- *Attach to*: auto or manual **trendlines**, **indicators**, and drawings (right-click → "Create Alert At This Line/Drawing"). The trigger price is re-evaluated from the object's current value, so it slides as the trendline/indicator moves.
- *Trigger conditions (verbatim semantics)*:
 - **Break Through** — price crosses to the opposite side of the **buffer zone**; requires the candle to "open and close, or close and open, on either side of the buffer area"; a two-candle variant fires when a candle opens on the opposite side to the previous candle's side.
 - **Touch** — price touches or trades **into** the buffer but does not break through (consolidation detector).
 - **Bounce** — a Touch followed by **no** break-through on the **next** candle (needs 2 completed candles).
- *Parameters*: `Sensitivity` = buffer width around the line (e.g. $1.00; docs note sensitivity 0 is practically untriggerable since price would need to print the exact cent); `Confirmation Candle` = which timeframe's close validates (e.g. a Daily trendline can confirm on 30m…Daily; Weekly/Monthly → 4h/Session/Daily); expiry = duration + max number of fires; optional JSON note payload for webhooks.
- *Critical mechanic*: **all alerts fire only after a complete candlestick closes on the confirmation timeframe. "Instant alerts are not available." Minimum alert timeframe = 5 minutes.** So this is a bar-close hysteresis system, not tick-based.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/alerts/dynamic-price-alerts-overview , https://help.trendspider.com/kb/alerts/trigger-conditions , https://help.trendspider.com/kb/alerts/create-new-dynamic-price-alert , https://help.trendspider.com/kb/alerts/alerts-faq-markdown-html

**23. Multi-Factor Alerts (chained/nested conditions across timeframes)**
- *Structure*: three logical trees — **"Any of the following" (OR)**, **"All of the following" (AND)**, **"None of the following" (NOT)** — nestable, each condition carrying its own timeframe and its own symbol.
- *Evaluation cadence*: the alert is checked **when the smallest involved timeframe closes** (15m smallest ⇒ checked on 15m closes). Cross-timeframe comparisons use **the last calculated data point on the larger timeframe** — which the docs admit causes apparent misfires when the HTF datapoint updates immediately after the fire.
- *Extended-hours data excluded unless explicitly enabled.*
- *Decision rule*: this is the platform's equivalent of a compiled signal predicate; the same script object is reusable as scan / backtest / bot / checklist.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/alerts/multi-factor-alerts-overview , https://help.trendspider.com/kb/alerts/create-a-new-multi-factor-alert-from-scratch

**24. Visual Scripting system (write once, run everywhere)**
- *Subjects*: indicators (200–300+), price O/H/L/C, candlestick patterns, chart patterns, and "special indicators" — `Range` (Donchian equivalent), `Candle Range`, `Date/Time` (military time ⇒ trading-window gating), `Change %`.
- *Operators*: >, <, =, **Crossed up through**, **Crossed down through**, Increased, **Is within range of (±%)**, **Evolved** (candlestick finalization), **Exists in watch list**.
- *Offsets*: **condition offset** ("RSI 1 candle ago") and **block offset** ("happened within X candles" — conditions need not be simultaneous, which is how sequence logic is expressed).
- *Multi-symbol*: a logical block can be assigned an explicit symbol ⇒ "buy SPY when gold drops" (not available in scanners).
- *Shorthand*: K/M/B numeric suffixes.
- *Reuse targets*: Strategy Tester entry/exit, Market Scanner, Multi-Factor Alerts, Smart Checklist, Bots, AI-strategy features.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/scripts/scripts-scripts-everywhere-scan-backtest-create-alerts

**25. Smart Checklist**
- A saved script evaluated **automatically on every chart load** for the currently displayed symbol; renders one green/red light per condition plus a master light that turns green only when **all** conditions pass. Same scripting substrate as scanner/backtest.
- *Decision rule*: mechanized pre-trade gate — no discretionary "close enough".
- *Confidence*: HIGH/MEDIUM.
- *Sources*: https://help.trendspider.com/kb/right-sidebar/smart-checklist-widget , https://trendspider.com/blog/software-update-smart-checklist-feature-added/

**26. Market Scanner**
- *Condition categories (13)*: Price, Indicators, Candlestick Patterns, **Chart Patterns**, **AI Model**, Fundamentals, Relative Performance, Analyst Estimates, **News Content**, Earnings, Dividends, Splits, Watch Lists. 70+ built-in scans.
- *Chart type selectable for the scan*: candlestick, Heikin Ashi, **Raindrop**.
- *MTF*: **up to 3 timeframes per scan**.
- *`Current Candle` flag*: when ON the scan treats the **live, unfinished** candle's last price as if it were the close ("in force"); when OFF it uses the last **closed** candle. (This is the explicit look-ahead/premature-signal trade-off knob.)
- *Scheduling*: **1 scheduled scan per day, 7 days/week**, emailed; result colouring **red = dropped out, blue = new match, grey = still matching** (a built-in state diff).
- *Min scanning timeframe by plan*: 2h (Standard) → 5m (Premium) → 1m (Enhanced/Advanced).
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/scanner/market-scanner , https://help.trendspider.com/kb/scanner/multiple-timeframes-and-the-current-candle , https://trendspider.com/pricing/

**27. Smart Watch Lists (auto-maintained universes)**
- 700+ dynamic lists: sector/industry, US stocks by market cap, **trading halts**, retail-trading-activity, **r/wallstreetbets** (see #40). Usable as scanner universes and as `Exists in watch list` conditions.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/smart-watch-lists/automated-watch-lists-for-retail-trading-activity

---

### F. Backtesting, automation, ML

**28. Strategy Tester (no-code multi-condition backtester)**
- *Execution model (the single most important mechanic)*: **conditions are checked at the candle CLOSE; if true, the trade executes at the OPEN of the following candle.** Backtesting "assumes perfect execution and zero slippage… orders fill at a specific, predefined price every time".
- *Config*: timeframe (1m→Yearly, floor by plan), depth in candles (2K/10K/20K/30K by plan) or explicit date range, chart type as price source (incl. Heikin Ashi / Raindrop), Ext Hours toggle, direction Long **or** Short, `Trade Cost` (% per trade, stands in for commissions+fees).
- *Entries*: script, or an explicit **Signal List** of timestamps (Unix / ISO-8601 / human-readable) — this is how external signals get backtested.
- *Exits*: script; **Take Profit**, **Stop Loss**, **Trailing Stop** — each expressible as **percentage**, **fixed price units**, or **× ATR(7) of the prior candle**; **Entry Invalidated**; **time-based (# candles passed)**; exit Signal List.
- *Trailing stop rule (verbatim)*: "the trail stop is recalculated for each period but if the new value is less than the current value, it will be discarded" — i.e. monotone ratchet: `stop_t = max(stop_{t-1}, f(price_t))`.
- *Hard constraints*: no scaling in, no multiple consecutive entries, **any exit closes 100%**; stops/TPs are only evaluated **at candle close** (no intrabar fills) — which systematically understates gap-through losses and overstates survival of wick-hunts.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/strategy-tester/understanding-strategy-tester-from-trendspider , https://help.trendspider.com/kb/strategy-tester/accessing-and-using-the-strategy-tester , https://help.trendspider.com/kb/strategy-tester/strategy-tester-faq-markdown-html

**29. Price Behavior Explorer + Random Control (their answer to "is this luck?")**
- *Metrics reported*: Mean Change %, Median Change %, **2nd / 98th percentile** (outlier band), Min/Max Change %, Number of Positions, and **Random Control (Mean)** = the average change of randomly-timed positions over the same sample.
- *Decision rule*: a strategy's mean change must exceed the **random control**; otherwise the edge is timing-free. This is a lightweight in-product Monte-Carlo null hypothesis.
- *Performance chart*: strategy cumulative vs **asset buy-and-hold** baseline, positions-over-time, cumulative drawdown. Position analysis: win rate, average gain/loss, return distribution.
- *Confidence*: HIGH for the metric list; **no formulas published for Sharpe/profit factor/expectancy — those metrics are essentially absent.**
- *Source*: https://help.trendspider.com/kb/strategy-tester/read-and-analyzing-test-results

**30. Strategy Variance Explorer / Group Strategy Tester (robustness, not walk-forward)**
- *Varies*: strategies × symbols (watchlist or scanner output) × timeframes × depth. **Up to 53 combinations** standard (up to 500 on request; older docs say 30–52).
- *Variant table metrics*: **R/R, Win %, Positions, Avg. Return, Return St. Dev, Drawdown, Exposure**, rendered as a green-to-transparent heatmap per column.
- *Decision rule*: high dispersion across variants ⇒ curve-fit/fragile; consistency across symbols and timeframes ⇒ candidate edge. Symbols-per-variance-test capped by plan (50/150/250/510).
- *Important*: this is **variance/robustness testing, not anchored walk-forward optimization** — there is no documented rolling in-sample/out-of-sample optimizer. "Forward testing" in marketing = running the strategy forward live/paper as a bot.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/strategy-tester/strategy-variance-explorer , https://trendspider.com/blog/a-revolutionary-approach-to-strategy-optimization-the-strategy-variance-tester/ , https://trendspider.com/pricing/

**31. Strategy Bots / Trade Automation**
- *Model*: **one bot = one strategy × one symbol × one timeframe.** Creating a bot **clones and locks** the strategy version (audit integrity).
- *Latency*: conditions evaluated "as soon as the corresponding candle closes, **in 40 to 60 seconds**". Stops/TPs/trailing also only fire at candle close (documented limitation).
- *Execution path*: **webhooks**, not native brokerage — user-defined URL + custom JSON body for entry and exit; prebuilt targets: SignalStack, TradersPost, Alertatron, Alert2Trade, Zapier, Make, Workato, IFTTT, Discord, Slack, Elastic. Retry logic up to **5 attempts / 3-second intervals**, then fallback = "Notify and assume manual entry/exit" or "Notify and stop bot".
- *Safety*: internal consistency checks on **every** evaluation to detect **signal movement / historical data adjustment (repaint)** — bot auto-stops on anomaly. Corner case where one candle produces both entry and exit is **muted**. Stopping a bot **does not flatten** the position. Extended-hours flag is forcibly disabled for bots.
- *Journaling*: control notifications (Critical-Only or **Verbose**) via SMS/email, status window with **last 5 signals**, and entry/exit arrows painted on the chart.
- *Limits*: 5 / 10 / 50 / 100 bots by plan; 5 free automated trades/month via SignalStack.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/trading-bots/trading-bots , https://trendspider.com/pricing/

**32. ML Quant Lab ("AI Strategies")**
- *Label construction (HIGH, and unusually well specified)*: **binary classification of "will price hit my Take-Profit before my Stop-Loss within the next X candles"**. Two label modes: **Conservative** (TP hit and SL never touched inside the horizon) and **Aggressive** (TP hit; SL allowed *after* TP). No regression targets.
- *Models*: **Naive Bayes** (complexity 1/4, assumes independent features), **Logistic Regression** (2/4), **K-Nearest Neighbors** (3/4), **Random Forest** (4/4, exposes number of trees + max tree complexity; flagged as overfit-prone).
- *Features*: any platform indicator/series; LLM-assisted feature engineering and model "cross-breeding" are advertised.
- *Output*: model **confidence** (for RF, the ensemble vote share) → thresholded into an entry signal, which becomes a scannable condition (`AI Model`) and a backtestable/bot-able script.
- *Gap*: **no documented train/validation/test split or purged CV** — the methodological weak point.
- *Confidence*: HIGH on labels/models, LOW on validation internals.
- *Sources*: https://help.trendspider.com/kb/ai-strategies/creating-an-ai-strategy-2-what-you-want-to-predict , https://help.trendspider.com/kb/ai-strategies/creating-an-ai-strategy-3-type-of-the-model , https://help.trendspider.com/kb/ai-strategies/what-is-an-ai-strategy

**33. Custom Indicators — JavaScript Scripting API**
- Language: **JavaScript**, executed **once per chart load**. Documented API surface: OHLCV access, dozens of helper functions to **compute indicators, detect trendlines, find chart patterns/formations**, math utilities; drawing of lines, **signals**, histograms, candle colouring, and arbitrary **HTML/table/chart overlays**; ability to upload custom time series and to **fetch third-party APIs via HTTP GET**. Debug via browser devtools + logging. AI code assist (Ctrl-K, "Claude 4.5") and indicator conversion (e.g. from Pine).
- Custom indicators are first-class in charts, strategies, bots, alerts, scanners and AI strategies.
- Reference: `https://charts.trendspider.com/scripting/docs/` (SPA — not server-rendered, so function signatures could not be extracted by fetch).
- *Confidence*: HIGH that the API exists with those capability classes; LOW on exact signatures.
- *Sources*: https://help.trendspider.com/kb/indicators/custom-indicators-js-scripting , https://trendspider.com/developers/

---

### G. Data-derived analytics

**34. Seasonality engine**
- *Aggregation units*: **Monthly, Week-of-Year, Day-of-Week, Hour-of-Day**. Week numbering = **Gregorian week** ("numbering always starts from the 1st day of the year; the first and last week need not have 7 days").
- *Metrics per bucket*: **% of periods that closed higher than they opened** (green columns = the "win rate"); **Mean Change %** = Σ(change%)/n; **P25/P75 band** rendered as a pale-blue cloud ("where most of the changes/volatility took place").
- *Controls*: start-date picker (commonly ~20-year default), and an **exclude-periods** filter accepting years or specific months (e.g. `2008`, `Mar 2020`, comma-separated) to strip regime outliers.
- *Decision rule*: only take seasonal tilts where win% and mean change agree and the P25/P75 cloud isn't dominated by a couple of outlier years.
- *Confidence*: HIGH for units/metrics/exclusions; MEDIUM for the default lookback; colour thresholds unpublished.
- *Sources*: https://help.trendspider.com/kb/right-sidebar/seasonality , https://trendspider.com/blog/software-update-new-asset-seasonality-data-types/

**35. Market Breadth engine (17 series × 120+ universes, chartable as symbols)**
- *Series and formulas*:
 - **Advance/Decline Ratio** = (# up) / (# down) in the list
 - **Advance/Decline Line** = cumulative (# up − # down)
 - **McClellan Oscillator = EMA(AD_LINE, 19) − EMA(AD_LINE, 39)** ← explicitly published
 - **% of symbols above Daily SMA(5, 10, 20, 50, 70, 100, 200)** — 7 series
 - **% making new highs / new lows over 14, 21, 63 days** — 6 series
 - **52-week High/Low difference** (net new highs − new lows)
- *Symbology*: `$MA50SP500` = % above SMA(50) in S&P 500; `$ADDJ30` = A/D ratio in Dow 30. Available for major indexes, **9 US sectors and 152 industries** ⇒ sector-level internals are chartable and scriptable.
- *Decision rule*: divergence between index price and its own breadth series = distribution; sector-level %>SMA50 = rotation map.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/indicators/market-breadth-data

**36. Relative Performance (RP) — fully published formulas**
- *Definition*: "RP is always a number from 0 to 100… equal to the **percentage of stocks in a given universe which have their performance worse than the current ticker's performance**" (percentile rank, universe default **SPX500**; non-constituents ranked as hypothetical members).
- *Data point used*: **HLC/3**.
- *Modes*:
 - **Last Quarter** = rolling 3-month price change %.
 - **Yearly (4-quarter weighted)**: `PERFORMANCE = Perf1Q·0.4 + Perf2Q·0.2 + Perf3Q·0.2 + Perf4Q·0.2`, where PerfNQ = change from N×3 months ago to now.
 - **TechRank** (no price change at all): `PERFORMANCE = slowEMADistance·0.30 + slowROC·0.30 + fastEMADistance·0.15 + fastROC·0.15 + ppoSlope·0.05 + fastRSI·0.05`, with slowEMA = **200**, fastEMA = **50**, slowROC = **125**, fastROC = **20**, RSI = **14**, PPO = **(12, 26, 9)**.
- *Decision rule*: **RP > 80 = leader (green), RP < 20 = laggard (red)**; scannable and chartable. This is TrendSpider's clone of IBD Relative Strength Rating / StockCharts TechRank.
- *Confidence*: HIGH (formulas verbatim).
- *Sources*: https://help.trendspider.com/kb/other-data-types/relative-performance , https://trendspider.com/blog/instantly-identify-leaders-and-laggards-with-relative-performance/

**37. Relative Strength (Dorsey & Mansfield variants)**
- Present as named indicators with a `Benchmark` input; the classic definitions apply — Dorsey RS = `100 × (price / benchmark)` (raw ratio, often smoothed); Mansfield RS = `((RS_t / SMA(RS, n)) − 1) × 100` (zero-centered). TrendSpider does not publish its parameterization.
- *Confidence*: LOW (names HIGH, formulas inferred from the standard literature).
- *Sources*: https://help.trendspider.com/kb/indicators/relative-strength , https://trendspider.com/blog/new-indicators-added-dorsey-and-mansfield-relative-strength/

**38. Fundamentals indicator (200+ metrics on the price timeline)**
- Income statement / balance sheet / cash flow items plus ratios (P/E, EV/EBITDA incl. **ttm** variants, ROA, turnover, current/quick, growth), plus **user-defined custom formulas**.
- *Rendering math*: a **ladder/step line** (value held constant between reports) with a dot at each report — **green dot if the metric beat the previous quarter, red if worse; grey dot = year-ago comparison; clouds = YoY change**. Quarters bucketed as "consecutive 3 months".
- Scannable, checklist-able, and usable in Stock Market Maps. Restatement handling undocumented.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/indicators/fundamentals

**39. FRED macro integration**
- ~**5,000** of FRED's ~730,000 series ("99% of series with meaningful popularity"). Frequency mismatch resolved by an **`Aggregate` parameter** (Last, Sum, Average, …) producing one datapoint per chart candle. Transformations: absolute level, **As Change %** (period-over-period), and a `Level At` reference line (default 0). **NBER recession bands** shaded automatically.
- *Decision rule*: macro overlay for regime gating (e.g. only long when a series' Change% > 0).
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/indicators/fred-data

**40. Wall Street Bets mentions (VADER sentiment pipeline)**
- Source: **Quiver Quantitative**. Pipeline: fetch all tickers mentioned on r/wallstreetbets for a window → score sentiment with **VADER**, take the **median sentiment across all days** in the window → bucket into lists (any mention / median < 0 / median > 0) → **noise filter: drop symbols with < 5 mentions (1-day lists) or < 15 (longer windows)** → rank by mention count → **cap top 50 per list**, published across 1-day/7-day/14-day windows as auto watch lists.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/other-data-types/wall-street-bets-mentions-data

**41. Dark Pool volume**
- Off-exchange share of total volume, expressed as **% of total volume**, plotted as a coloured area. **Weekly datapoints only, with a 3–5 week publication lag.** Note: daily/weekly/monthly consolidated volume already includes dark-pool prints, so this is a decomposition, not an addition.
- *Decision rule*: structurally high off-exchange % (50–70%+) changes how you read volume confirmation; **the lag makes it unusable as a timing signal**.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/other-data-types/dark-pool-data

**42. Options Chain**
- Data via **OPRA** (subscription; single-device restriction). **Implied volatility and Greeks are computed with the Black-Scholes model.** Refresh ≈ **every 10 seconds** (snapshot, not streaming). Up to 7 selectable columns from: Bid, Ask, Ask-Bid Spread, Delta, Gamma, Theta, Vega, IV, Volume Today, Open Interest, OI Change, Price Change %, and composite Greek×OI products (**Delta × OI, Gamma × OI**). Proprietary display widgets: **Progress Bar Metric** (scaled bars across strikes) and **Navigation Bar Metric** (vertical all-strike chart, green calls / red puts). Options on futures unavailable; CBOE index options ($SPX) supported.
- *Decision rule*: Gamma×OI / Delta×OI by strike is the wall/pin proxy available here.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/options-data/options-chain

**43. Options Map (strike × expiry heatmap)**
- Grid where each cell = one contract; **22+ selectable metrics** (OI, Volume, Delta, Gamma, Theta, Vega, IV, spreads…), calls or puts, strike range ±$10/20/30/50/100, strike increment $1/$5/$10, expiry filter (none/weekly/monthly/quarterly).
- **Normalization scope is the key knob**: colour-grade **relative to the Entire Grid**, **By Strike** (row-relative), or **By Expiration** (column-relative) — plus "Ignore Stale". Totals row/column surface the largest aggregate strike and expiry. CSV export; right-click to hide outliers / flag / add to watchlist.
- *Decision rule*: by-expiration normalization finds the dominant strike for a given date (wall); by-strike normalization finds which expiry owns a level. **Max Pain is not computed.**
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/options-data/options-map

**44. Unusual Options Flow (block & sweep detector)**
- *Published criteria*: trade is a **block or a sweep**, executed **at the ask or at the bid**, **premium paid > $20,000**, and the trade constitutes "a relatively meaningful material portion of the **open interest** in the contract". Widget updates **once per minute**; also exposed as a public per-symbol page.
- *Decision rule*: at-ask sweeps = aggressive buyer; at-bid = aggressive seller; size relative to OI is the significance filter.
- *Confidence*: HIGH on criteria, MEDIUM on the exact OI-ratio cutoff (industry convention ≈ vol/OI ≥ 1.25 with vol > 500, OI > 100 — that specific triple is a general/Barchart-style convention, not confirmed as TrendSpider's).
- *Sources*: https://trendspider.com/learning-center/unusual-options-activity/ , https://help.trendspider.com/kb/right-sidebar/unusual-options-widget

**45. "What's Happening Now" data flows (9 streams with published cadence)**
| Stream | Cadence / source |
|---|---|
| News | **once per minute**, all supported tickers |
| Unusual Options | **once per minute** |
| Corporate (institutional) transactions | **every 30 minutes**, from **13F** filings |
| Insider trading | daily, SEC-reported insider transactions |
| Government/Congress trades | congressional filings (**45-day** disclosure requirement) |
| Analyst estimates | daily |
| Earnings / Dividends / Splits | daily, past + upcoming |
- Plus Trading Halts and Trending/52-week-high-low/gapper feeds surfaced as smart watch lists and free scanners.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/researching-opportunities/data-flow

**46. Stock Market Maps (tile + bubble heatmaps)**
- Two constructions: **Tile Map** (grid, size = sizing metric) and **Bubble Map** (2-axis scatter with size/colour). Inputs: symbol list (700+ prebuilt or custom), **sizing metric**, **colour metric**; ~**57 metrics** across performance, fundamentals, financial health.
- *Colour math*: metric-direction-aware ("bigger is better" for revenue, "smaller is better" for P/E); **blue = 45th–55th percentile (median band)**, green = favourable, red = unfavourable, grey = ambiguous (e.g. negative P/E). So this is a **percentile-ranked** heatmap, not a raw-value one.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/researching-opportunities/stock-market-maps

**47. Segments & KPIs**
- Reported-segment financials for ~**1,500 largest US companies**: revenue by segment, revenue by geography, segment EBIT, segment capex, and company-specific KPIs (subscribers, store count, backlog), one column per fiscal period (quarterly or annual), each with a **Change% YoY** row (green/red). Any metric can be plotted above price as bar/line/scatter, stackable as parts-of-a-whole, with trend/median/average overlays.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/researching-opportunities/segments-and-kpis

**48. Composite Symbols (custom spreads/ratios) — with an explicitly documented OHLC rule**
- Syntax: expression prefixed with `=`, e.g. `=SPY/QQQ`, `=1/^EURUSD`, `=AAPL.CHG / SPY.CHG`; operators `+ - / * ( ) % ^`; **max 9 unique symbols**; whitespace-sensitive; crypto requires exchange prefix (`BINANCE:^ETHBTC`).
- Per-symbol accessors: `.O .H .L .C .V .CHG .ACHG .SIZE`.
- **OHLC of a composite**: `Open` = operation applied to each leg's open; `Close` = operation applied to each leg's close; `High` = **max of (open, high, low, close) computed from the calculated high**; `Low` = **min of the same set** — i.e. highs/lows are re-derived because a ratio can invert extremes.
- Limits: **no volume**, no real-time streaming (manual refresh), session treated as **24/7 UTC**.
- *Decision rule*: proper way to chart RS pairs (e.g. `=SMH/SPY`) and cross-market spreads with auto-trendlines/heatmaps applied on top.
- *Confidence*: HIGH.
- *Source*: https://help.trendspider.com/kb/data-feeds/composite-symbols

**49. Sidekick AI (research agent)**
- Model picker: Gemini 3.1, Sonnet 4.6, GPT 5.4 on all plans; GPT 5.5 and Opus 4.8 on Plus/Max. Tooling: price data across asset classes, financial statements, **10-K/20-F filings and earnings-call transcripts**, sentiment, options flow, insider + congressional trades, seasonality, and **live broker holdings via SignalStack (read-only)**. Can **see the rendered chart including your annotations/indicators/drawings**. Has a **rule/heuristic-based backtest critic** ("built from TrendSpider's expertise") that explains why a strategy is weak. Deep Research mode exists.
- *Documented limits*: ≤ 15–20 tickers per analysis (soft limit 20 alerts per message), cannot give trading advice, **cannot judge trendline quality**, cannot execute trades. 25 messages/month on every plan.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/sidekick-ai/trendspider-sidekick , https://trendspider.com/pricing/

**50. Chart-type / workspace infrastructure worth noting for a builder**
- Chart types: Line, Bars, Candles, Hollow Candles, **Raindrop**, Heikin Ashi. Linear/log scale (heatmaps disabled on log). Fractional or decimal futures display. Exchange vs local time zone. Extended-hours toggle below weekly for stocks/ETFs/OTC. Session-break verticals.
- **Multi-Symbol View: up to 48 charts (max 8 × 6)**, mixed asset classes, bulk-apply settings and bulk-refresh of automated analysis; 5–20 open workspaces by plan.
- Custom data upload (own time series) is supported and chartable/scriptable.
- *Confidence*: HIGH.
- *Sources*: https://help.trendspider.com/kb/charting/chart-settings-and-customization , https://help.trendspider.com/kb/workspaces/multi-symbol-view , https://help.trendspider.com/kb/data-feeds/uploading-custom-data-to-trendspider

---

## PART 2 — MATH GAPS (what is genuinely secret) + defensible approximations

1. **The default trendline scoring expression.** Variables are fully published (`hits, violations, bounceUp/Down, peaksUp/Down, points, points2x, length, seriesLength, priceDev25/50/75`), the default weighting is not, nor is the "top 1%" threshold's tie-breaking.
 *Approximation*: `score = ((hits + (bounceUp+bounceDown) + 2·(peaksUp+peaksDown)) / (1+violations)) · (length/seriesLength)^0.5 / (1+priceDev50)`; select top 1% by score after the ATR distance filter. Calibrate the exponent and `w_p` by matching rendered line counts on a known chart.

2. **Pivot ("Base Points") defaults per timeframe.** Only one concrete number leaked: **Daily ≈ 10 candles apart**. The full per-resolution table (1m…Monthly) and the per-resolution **ATR(14) distance factors** are not published.
 *Approximation*: use a monotone map, e.g. base points ≈ {1m: 20, 5m: 15, 15m: 12, 1h: 10, D: 10, W: 8, M: 6}, and line-dismissal distance `≤ 2–3 × ATR(14)` per resolution (consistent with the gap default of 3×ATR14). Tune by counting rendered lines.

3. **"Analysis Type" (Original / Standard / Enhanced) internals.** Described only qualitatively as trend-sensitivity. *Approximation*: a multiplier on the pivot window / minimum swing amplitude — Original ≈ 1.5×, Standard ≈ 1.0×, Enhanced ≈ 0.6× of the base window.

4. **Auto-Fibonacci anchor objective.** "Most meaningful connection points" is undefined; default level set unpublished. *Approximation*: pick the swing pair maximizing `|H−L| × (recency weight)` subject to both endpoints being confirmed pivots at the active window, then plot 0.236 / 0.382 / 0.5 / 0.618 / 0.786 (+ extensions 1.272/1.618).

5. **Heatmap normalization and colour mapping.** Grid is known (**40×60**, bounded by Truth-in-Analysis lines) and the count rule is known (trendlines crossing a cell), but the count→colour transfer function and the Depth gradient kernel are not. *Approximation*: `heat = count / max(count)`, then Depth = 2-D Gaussian blur (σ ≈ 1–1.5 cells) of that field; render `alpha = heat^0.7`.

6. **Horizontal S/R heatmap "sequential number of highs on green candles and lows on red candles."** The required run length is not published. *Approximation*: bin price into 60 rows; per bin count `Σ[high∈bin ∧ close>open] + Σ[low∈bin ∧ close<open]`, require ≥3 to register, then normalize as above.

7. **Candlestick pattern tolerances.** Body/wick ratio thresholds for each of the recognized formations are undisclosed. *Approximation*: TA-Lib's definitions — TrendSpider's behaviour is consistent with a TA-Lib-class recognizer plus the `Evolved` (pattern-finalized) event semantics.

8. **Chart-pattern "actionability" filter thresholds.** The *rules* are stated (apex too far/deep, no longer respected, handle overextended, price never returned below neckline) but not the numbers. *Approximation*: apex within `[−0.25·L, +0.5·L]` bars of now where L = pattern length; invalidate when price is > 1×ATR(14) beyond the boundary for ≥2 closes.

9. **Raindrop histogram binning and rendering smoothing.** The white paper specifies the *steps* but not bin count, bin width, or the area-chart smoothing/kernel; also silent on **edge cases** (single-print half-periods, zero-volume halves, gapped periods) and on whether the "mass center" uses the whole period's VWAP (it says "the same as the volume-weighted price"). *Approximation*: bins at the instrument's tick-derived granularity or ~50 bins across the period's H–L; mass center = full-period VWAP `Σ(p·v)/Σv`; monotone cubic interpolation for the area outline; if one half has no volume, render a degenerate (zero-width) side.

10. **Raindrop pattern reliability statistics.** None ever published — Appendix B is illustrative charts only, and the paper explicitly requests backtesting. Any "reliability %" you see attributed to raindrops is invented. **Treat as unmeasured.**

11. **Backtester metric formulas.** Only names are published (Win %, R/R, Avg Return, Return St.Dev, Drawdown, Exposure, Mean/Median Change %, 2nd/98th percentile, Random Control). No Sharpe, profit factor, expectancy, MAE/MFE. *Approximation / caution*: assume `R/R = avg win / |avg loss|`, `Exposure = bars in market / total bars`, `Drawdown` from the cumulative % curve (per-trade compounding basis unspecified — verify before comparing to any external engine). **The absence of Sharpe/PSR/DSR and of purged walk-forward is a real methodological hole; export trades and compute those yourself.**

12. **Random Control construction.** Sample count, whether entries are matched on holding period/exposure, and whether it's per-symbol are unspecified. *Approximation*: N ≥ 1,000 random entries with the same holding-period distribution; compare mean and use a bootstrap CI rather than the single mean the UI shows.

13. **AI-strategy validation.** No documented train/val/test split, no purging/embargo, no walk-forward. Confidence calibration method unstated. *Assume in-sample optimism unless you replicate with your own CV.*

14. **Dynamic-alert extrapolation.** Docs never state whether a trendline is projected forward for triggering beyond its last anchor point (it visibly is on-chart). *Assume* the line is extended linearly: `level(t) = m·t + b` from its two anchors, and that the alert compares that extrapolated level against the confirmation candle's OHLC with the `sensitivity` buffer.
 *Trigger semantics to replicate*: Touch = `low ≤ level+s ∧ high ≥ level−s ∧ ¬crossed`; BreakThrough = candle open and close on opposite sides of the buffer band; Bounce = Touch at `t` and no BreakThrough at `t+1`.

15. **Gap Detector's `Gap Factor` scale.** Whether 0.5 multiplies ATR(14) or a different band isn't stated. *Approximation*: `gap if |open_t − close_{t−1}| > GapFactor × ATR(14)` — note this default (0.5×ATR) is far looser than the trendline engine's islands default (3×ATR), so the two features disagree by design.

16. **Market Wave Trend & Signals.** Community/store indicator, closed source. See #21 for my approximation.

17. **Relative Strength (Dorsey/Mansfield) parameterization** — periods unpublished; standard defaults (Mansfield SMA(52) on weekly) are the safe assumption.

18. **Latency/infrastructure.** "Instant alerts are not available"; bots evaluate 40–60 s after close; options chain refreshes ~10 s; scanner scheduling is 1/day. **There is no documented tick-level trigger path anywhere in the product** — architecturally relevant if you're comparing against a tick-driven system.

---

## PART 3 — ALERT / SIGNAL TAXONOMY (everything the platform can push)

**Alert objects (2 first-class types)**
1. **Dynamic Price Alert** — attached to a trendline / indicator / drawing. Sub-triggers:
 - 1a. **Break Through** (single-candle: open & close on opposite sides of the buffer; two-candle variant: candle opens on the side opposite the previous candle)
 - 1b. **Touch** (enters buffer, no break)
 - 1c. **Bounce** (Touch at t, no break at t+1)
 - Parameters: `Sensitivity` (buffer), `Confirmation Candle` timeframe, expiry by duration **and** by max fire count, optional JSON note payload.
2. **Multi-Factor Alert** — nested Any/All/None trees over indicators, price, candlestick patterns, chart patterns, AI model output, fundamentals, RP, analyst estimates, news content, earnings/dividends/splits, watch-list membership; per-condition timeframe and per-block symbol; block offsets ("happened within X candles"); evaluated at the **smallest** involved timeframe's close.

**Signals emitted by other subsystems**
3. **Strategy Bot entry signal** (candle close, 40–60 s) → webhook JSON + SMS/email.
4. **Strategy Bot exit signal** — script exit, Take Profit, Stop Loss, Trailing Stop, Entry-Invalidated, Time-based (# candles) — all evaluated at candle close.
5. **Bot control/health notifications** — Verbose or Critical-Only: started/stopped, webhook failure + retry (≤5 × 3 s), fallback ("assume manual entry/exit" / "stop bot"), and **auto-stop on internal consistency failure (signal moved / historical data adjusted = repaint detection)**.
6. **Scheduled Market Scan report** (email, 1/day) with state diff colouring: **blue = newly matching, grey = still matching, red = dropped out**.
7. **Smart Checklist per-condition lights** (on every chart load): per-condition green/red + master all-conditions light. Passive, chart-local.
8. **Chart-painted signals**: automated trendlines/auto-fibs/heatmaps refresh, candlestick and chart-pattern labels, bot entry/exit arrows, custom-script `signal` marks.
9. **Data-flow feeds** that function as alerts in practice: News (1 min), **Unusual Options block/sweep >$20k premium** (1 min), institutional 13F changes (30 min), insider filings, congressional trades, halts, gappers, earnings/dividends/splits calendars, analyst estimate changes.
10. **Smart Watch List membership changes** (halts, WSB positive/negative sentiment lists, retail-activity lists, 52-week extremes).
11. **AI/ML model signal** — binary "TP before SL within X candles" above a confidence threshold; consumable as a scan condition, an alert condition, a backtest entry, or a bot trigger.
12. **Sidekick AI outputs** — chat/deep-research answers, indicator explanations, and rule-based backtest critiques (informational; cannot place orders).

**Delivery channels**: email, **SMS**, and **webhook** (custom URL + custom JSON body; prebuilt: SignalStack, TradersPost, Alertatron, Alert2Trade, Zapier, Make, Workato, IFTTT, Discord, Slack, Elastic), plus in-app alert sounds (not customizable) and chart annotations. Alert expirations are counted in **calendar days**. Extended-hours evaluation is opt-in for alerts and **unavailable for bots**. Max active alerts by plan: **10 / 50 / 100 / 400**; alert history retention **30 / 90 / 180 / 365 days**; bots **5 / 10 / 50 / 100**.

---

### Builder's bottom line (what is actually reusable IP)
- **Fully reconstructible from public docs**: Raindrop construction (exact), raindrop pattern thresholds (50% / 33% / 60%+80% rules), McClellan = EMA19−EMA39 of the A/D line, Relative Performance (all three modes with exact weights), AVWAP anchor taxonomy incl. the look-ahead guard, backtester execution model (close→next open, ATR(7) stops, ratchet trailing rule), bot latency and repaint auto-stop, ML label definition (TP-before-SL, conservative/aggressive), scanner/alert MTF alignment (step-hold of last HTF value), gap = 3×ATR(14), heatmap 40×60 grid = trendline-crossing count.
- **Genuinely secret**: the trendline **scoring weights** and the per-resolution Base-Point/ATR-factor tables (everything else about trendlines is documented, including the variable set — which is why an approximation is credible), the auto-fib anchor objective, candlestick pattern tolerances, and any pattern reliability statistics (which do not exist).

Sources: [Automated Trendline Detection](https://help.trendspider.com/kb/automated-technical-analysis/automated-trendline-detection) · [Custom Trend Line Formulas](https://help.trendspider.com/kb/advanced-customization-settings/custom-trend-line-formulas) · [Trendline Customization & Filtering](https://help.trendspider.com/kb/automated-technical-analysis/trendline-customization-and-filtering) · [Customization & Tuning](https://help.trendspider.com/kb/automated-technical-analysis/customization-and-tuning) · [Trend Analysis Settings](https://help.trendspider.com/kb/advanced-customization-settings/trend-analysis-settings) · [Types of Automated Analysis](https://help.trendspider.com/kb/automated-technical-analysis/types-of-automated-analysis) · [Auto Fibonacci](https://help.trendspider.com/kb/automated-technical-analysis/automated-fibonacci-retracements) · [Depth & Trends Heatmaps](https://help.trendspider.com/kb/automated-technical-analysis/heatmaps-399dc166f3dc428e) · [Horizontal S/R Heatmaps](https://help.trendspider.com/kb/automated-technical-analysis/horizontal-support-and-resistance-heatmaps) · [Truth in Analysis](https://help.trendspider.com/kb/automated-technical-analysis/truth-in-analysis-timestamp) · [MTFA](https://help.trendspider.com/kb/automated-technical-analysis/multi-timeframe-analysis) · [Raindrop white paper PDF](https://trendspider.com/whitepapers/raindrops_280519.pdf) · [How Raindrops Are Rendered](https://help.trendspider.com/kb/raindrop-charts-tm/how-raindrops-are-rendered) · [Raindrop Patterns](https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-pattern) · [Raindrop Volume-Weighting Effects](https://help.trendspider.com/kb/raindrop-charts-tm/raindrop-chart-volume-weighting-effects-on-indicators-and-auto-trendlines) · [Anchored Indicators 101](https://help.trendspider.com/kb/indicators/anchored-indicators-101) · [Volume by Price](https://help.trendspider.com/kb/indicators/volume-by-price) · [Chart Pattern Recognition](https://help.trendspider.com/kb/automated-technical-analysis/automated-chart-pattern-recognition) · [H&S blog](https://trendspider.com/blog/next-level-intelligence-automated-head-and-shoulders-pattern-recognition/) · [Dynamic Price Alerts](https://help.trendspider.com/kb/alerts/dynamic-price-alerts-overview) · [Trigger Conditions](https://help.trendspider.com/kb/alerts/trigger-conditions) · [Alerts FAQ](https://help.trendspider.com/kb/alerts/alerts-faq-markdown-html) · [Multi-Factor Alerts](https://help.trendspider.com/kb/alerts/multi-factor-alerts-overview) · [Visual Scripting](https://help.trendspider.com/kb/scripts/scripts-scripts-everywhere-scan-backtest-create-alerts) · [Smart Checklist](https://help.trendspider.com/kb/right-sidebar/smart-checklist-widget) · [Market Scanner](https://help.trendspider.com/kb/scanner/market-scanner) · [MTF & Current Candle](https://help.trendspider.com/kb/scanner/multiple-timeframes-and-the-current-candle) · [Strategy Tester](https://help.trendspider.com/kb/strategy-tester/understanding-strategy-tester-from-trendspider) · [Strategy Tester config](https://help.trendspider.com/kb/strategy-tester/accessing-and-using-the-strategy-tester) · [Reading Test Results](https://help.trendspider.com/kb/strategy-tester/read-and-analyzing-test-results) · [Variance Explorer](https://help.trendspider.com/kb/strategy-tester/strategy-variance-explorer) · [Trading Bots](https://help.trendspider.com/kb/trading-bots/trading-bots) · [AI model types](https://help.trendspider.com/kb/ai-strategies/creating-an-ai-strategy-3-type-of-the-model) · [AI prediction target](https://help.trendspider.com/kb/ai-strategies/creating-an-ai-strategy-2-what-you-want-to-predict) · [JS Scripting](https://help.trendspider.com/kb/indicators/custom-indicators-js-scripting) · [Seasonality](https://help.trendspider.com/kb/right-sidebar/seasonality) · [Market Breadth](https://help.trendspider.com/kb/indicators/market-breadth-data) · [Relative Performance formulas](https://help.trendspider.com/kb/other-data-types/relative-performance) · [Fundamentals](https://help.trendspider.com/kb/indicators/fundamentals) · [FRED](https://help.trendspider.com/kb/indicators/fred-data) · [WSB mentions](https://help.trendspider.com/kb/other-data-types/wall-street-bets-mentions-data) · [Dark Pool](https://help.trendspider.com/kb/other-data-types/dark-pool-data) · [Options Chain](https://help.trendspider.com/kb/options-data/options-chain) · [Options Map](https://help.trendspider.com/kb/options-data/options-map) · [Unusual Options](https://trendspider.com/learning-center/unusual-options-activity/) · [Data Flow](https://help.trendspider.com/kb/researching-opportunities/data-flow) · [Stock Market Maps](https://help.trendspider.com/kb/researching-opportunities/stock-market-maps) · [Segments & KPIs](https://help.trendspider.com/kb/researching-opportunities/segments-and-kpis) · [Composite Symbols](https://help.trendspider.com/kb/data-feeds/composite-symbols) · [Sidekick](https://help.trendspider.com/kb/sidekick-ai/trendspider-sidekick) · [Multi-Symbol View](https://help.trendspider.com/kb/workspaces/multi-symbol-view) · [Chart Settings](https://help.trendspider.com/kb/charting/chart-settings-and-customization) · [Gap Detector](https://help.trendspider.com/kb/indicators/gap-detector) · [Gap Proximity](https://help.trendspider.com/kb/indicators/gap-proximity) · [Market Wave Trend & Signals](https://trendspider.com/trading-tools-store/indicators/698789-market-wave-trend-signals/) · [Pricing matrix](https://trendspider.com/pricing/)