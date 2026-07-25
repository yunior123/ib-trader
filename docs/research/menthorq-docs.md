# MenthorQ — Technical Dossier (Deep Research)

Research date: 2026-07-25. Everything below is sourced from MenthorQ's own guide wiki (~500+ guides), quantitative-model pages, Academy lessons, integration docs, Discord bot documentation, and third-party integration writeups (TrendSpider, Quantower, ATAS, optionstradingiq, gex-levels.com). Confidence is flagged per item. **MenthorQ explicitly states multiple times that the exact formulas are proprietary** — the honest finding is that the *taxonomy and level schema are fully documented*, while the *transforms* are disclosed only at the level of "which inputs, which qualitative operation."

---

## PART 0 — Architecture: how the product actually works

This matters more than any single metric, because it constrains what MenthorQ can possibly be computing.

**Pipeline:** full options chain per asset (all strikes, all expirations, including 0DTE) → per-strike gamma and delta exposure → aggregation into Net GEX / Net DEX curves → level extraction (argmax / inflection / top-N ranking) → clipping to the 1D Expected Move envelope → publish as a flat list of named price levels.

**The output is a flat text blob of `name → price` pairs.** This is the single most important structural fact. MenthorQ does not push a live stream to charting platforms; it pushes a *snapshot list of ~20 named price levels per ticker*. Confirmed by:
- TradingView has no ingestion API, so MenthorQ **pushes a new version of the Pine script itself** each time levels update; users may need to remove/re-add the indicator to fully refresh ([tradingview guide](https://menthorq.com/guide/tradingview/)).
- Sierra Chart integration is a **DLL** reading either (a) the API with an API key, or (b) a plain text file that must be named exactly **`SierraChart Q-Levels.txt`** in the Sierra Chart Data folder ([sierra-chart-integration](https://menthorq.com/guide/sierra-chart-integration/)). Default API refresh interval: **120 minutes**, user-configurable in minutes.
- Quantower: DLL/script in `C:\Quantower\Settings\Scripts\Indicators`, API key + **Machine ID activation** ([quantower-integration](https://menthorq.com/guide/quantower-integration/)).
- QUIN's "Request Levels" tool generates **"TradingView code"** the user copy-pastes into the *Custom Levels* indicator ([request-levels-via-quin](https://menthorq.com/guide/request-levels-via-quin/)).

**Update cadence** (from [asset coverage guide](https://menthorq.com/guide/menthorq-asset-coverage/), [tradingview guide](https://menthorq.com/guide/tradingview/), [ATAS marketplace](https://marketplace.atas.net/product/menthor-q-market-data-services)):

| Model | Cadence |
|---|---|
| Gamma Levels EOD — stocks/ETFs/indices | 18:00 ET (TradingView indicator pushes 18:30 and 23:00 ET) |
| Gamma Levels EOD — crypto | 20:00 ET |
| Gamma Levels EOD — futures, forex | 23:00 ET |
| Gamma Levels **Intraday** — stocks/ETFs/indices | every **5 minutes, 09:35–16:00 ET**, plus an 08:00 ET pre-market snapshot |
| Gamma Levels **Intraday** — futures | every 5 min, 22:30–17:00 ET, **paused 18:00–22:00 ET** for data processing |
| Aggregate claim | "updated more than **14 times per day**" |
| Blind Spots Levels | Mon–Fri ~23:00 ET (EOD only) |

**Coverage:** 1,400+ assets. Assets are bucketed **Tier 1 / Tier 2 / Tier 3**, and the TradingView "Auto Updated Levels" indicator ships pre-calculated levels for Tiers 1–3 only. Futures: ES, NQ, RTY, YM, CL, NG, GC, SI, PL, HG, ZB, ZN, ZT, ZF, MBT, 6A, 6B, 6C, 6E, 6J, 6S, ZS, ZC, ZW. Forex: AUD, CHF, GBP, EUR, JPY, CAD, XAU. Crypto: BTC/ETH/SOL/XRP/BNB against USDT/USD/USDC (~13–20 pairs), sourced from **Deribit, Binance, OKX** (~95% of global crypto options volume).

**Critical constraint MenthorQ admits:** Gamma Levels **Intraday is not available for futures** — the documented workaround is to compute levels on SPY/SPX/QQQ and use *Levels Conversion* to project them onto ES/NQ. So intraday futures levels are **derived from equity-index option chains, not from futures options**, unless you use the EOD futures-options model.

---

## PART 1 — NUMBERED CATALOGUE

### A. Gamma exposure core

**1. Net Gamma Exposure (Net GEX)**
*What:* Signed aggregate dealer gamma across the option chain, per strike and in total.
*Inputs:* Full option chain — per-strike gamma, open interest, (for intraday: volume), spot, contract multiplier, all expirations including 0DTE.
*Computation:* MenthorQ states only that it "aggregates gamma exposure from both call and put options across strikes and expirations" producing "a net value that reflects whether call gamma or put gamma dominates," with green bars = net call gamma, red bars = net put gamma. Dealer convention is the standard street one: customers are net long calls / long puts, so **dealers are short options; negative Net GEX = dealers short gamma**. The guide confirms: "investors buy puts for downside protection, dealers who sell those puts must hedge dynamically," leaving dealers short put gamma.
*Decision rule:* Positive Net GEX → dealers "sell into rallies and buy into declines" → mean-reverting, range-bound, fade extremes. Negative Net GEX → hedging is "pro-cyclical" → momentum, breakouts, trend-follow.
*Confidence:* **HIGH** on taxonomy/interpretation, **LOW** on exact formula (never published).
*Sources:* [what-is-net-gex](https://menthorq.com/guide/what-is-net-gex/), [key-gamma-levels](https://menthorq.com/guide/key-gamma-levels/), [net-gamma-exposure model](https://menthorq.com/quantitative-model/net-gamma-exposure/)

**2. Total GEX (as distinct from Net GEX)**
*What:* Absolute (unsigned) gamma magnitude across the chain.
*Computation:* "the absolute amount of gamma exposure across the option chain, regardless of whether that exposure is positive or negative" — i.e. Σ|GEX_k| vs Σ GEX_k.
*Decision rule (this is the genuinely useful non-obvious one):* **High Total GEX + negative Net GEX = bifurcated market** — unstable at the regime level but with "large pockets of gamma that influence price action" at specific strikes. Translation: trade the *levels* but do not trade the *regime*; expect violent moves that still respect individual strikes. This is the cleanest published rule on the whole site.
*Confidence:* **HIGH** (conceptual), formula trivially reconstructible.
*Source:* [how-to-interpret-net-gex-versus-total-gex](https://menthorq.com/guide/how-to-interpret-net-gex-versus-total-gex/)

**3. Net GEX Multi-Expiration**
*What:* Three separate Net GEX curves — **0DTE, WDTE (weekly), monthly** — plus (for futures) a split across four key expiration dates.
*Decision rule:* Divergence between the 0DTE curve and the monthly curve identifies whether today's structure is a same-day artifact (fades by the close) or a structural wall (persists). Used for OPEX trading.
*Confidence:* HIGH (documented product), Discord command `/netgex_multiexpiry`.
*Sources:* [the-net-gex-multi-expirations](https://menthorq.com/guide/the-net-gex-multi-expirations/), [discord-ai-bot-commands](https://menthorq.com/guide/discord-ai-bot-commands/)

**4. Net Delta Exposure (Net DEX)**
*What:* Aggregate dealer delta across the chain.
*Inputs:* per-strike delta × OI × multiplier, summed.
*Computation:* Not published. Sign convention IS published and is **inverted from the naive reading** — worth noting: "**Positive DEX** → market makers *sell* the underlying to reach delta neutrality → **negative liquidity event**. **Negative DEX** → market makers *buy* → **positive liquidity event**." Simultaneously "positive DEX = bullish sentiment positioning." So DEX is a *sentiment* read whose *flow* implication is the opposite sign. Any port must not conflate the two.
*Decision rule:* DEX direction is a confirmation filter on GEX-level trades — Academy lessons list "Net Delta Exposure direction" as a required confluence input for ES setups.
*Confidence:* HIGH on sign convention, LOW on formula.
*Sources:* [net-delta-exposure](https://menthorq.com/quantitative-model/net-delta-exposure/), [gamma-levels-on-es](https://menthorq.com/guide/gamma-levels-on-es/)

**5. Historical GEX / DEX (`/histgex`)**
*What:* SPX time series in three panes — historical spot, historical GEX with an SMA overlay, historical DEX with an SMA overlay.
*Decision rule:* GEX/DEX vs their own moving average = regime persistence check. Implies MenthorQ stores a daily GEX/DEX scalar per ticker — the raw material for calibration.
*Confidence:* HIGH (documented command).
*Source:* [discord-ai-bot-commands](https://menthorq.com/guide/discord-ai-bot-commands/)

**6. Positive GEX Top-10 strikes (`/posgex`)**
*What:* Table of the 10 strikes with the **most positive GEX and DEX**.
*Decision rule:* "identifying sticky strikes and spread placement opportunities" — i.e. where to sell premium / place short strikes of condors and credit spreads.
*Confidence:* HIGH.

**7. Negative GEX Top-10 strikes (`/neggex`)**
*What:* The 10 strikes with the most negative GEX and DEX.
*Decision rule:* "confirmation and strike selection" — acceleration zones; where breaks run. The mirror of #6: do **not** sell premium here.
*Confidence:* HIGH.

### B. The published levels taxonomy (the part that ports expose)

**8. Call Resistance**
*What:* The single strike with the heaviest net **call** gamma.
*Inputs:* per-strike net call gamma exposure across the chain.
*Computation:* `argmax_k (net call GEX at strike k)` — described as "the widest bars in the Net GEX chart" and "the price level with the most net gamma when it comes to calls."
*Decision rule:* Dealer hedging caps rallies — dealers sell futures/underlying into strength as price rises toward it, "creating a self-limiting loop." First touch → **fade**, sell at the level with a tight stop just above. Break above it, especially through negative-gamma clusters → dealers must buy → momentum continuation.
*Confidence:* **HIGH.**
*Sources:* [key-levels-and-key-terms](https://menthorq.com/guide/key-levels-and-key-terms/), [TrendSpider blog](https://trendspider.com/blog/menthorq-levels-indicators/), [gamma-levels-for-futures-trading](https://menthorq.com/guide/gamma-levels-for-futures-trading/)

**9. Put Support**
*What:* The single strike with the heaviest net **put** gamma. `argmax_k (net put GEX at strike k)`.
*Decision rule:* Dealers short those puts hedge by **buying** futures into weakness → floor. Break below flips the mechanism: "dealer delta exposure changes more rapidly… dealers must continue selling into weakness," plus a reflexive roll-down loop (traders roll puts lower → dealers sell new puts → hedge by selling futures). **The published confirmation trigger is the failed retest**: if price cannot reclaim broken Put Support, "old support has now become resistance" and trend continuation is confirmed.
*Confidence:* **HIGH.**
*Sources:* [understanding-trading-below-the-put-support](https://menthorq.com/guide/understanding-trading-below-the-put-support-what-does-that-mean-for-traders/), [key-levels-and-key-terms](https://menthorq.com/guide/key-levels-and-key-terms/)

**10. High Vol Level (HVL) — the gamma flip**
*What:* The regime boundary between positive and negative dealer gamma. Note the naming ambiguity you asked about: MenthorQ calls it **"High Volatility Level"**, *not* "Highest Volume Level." It is a **gamma flip**, not a volume construct.
*Inputs:* the cumulative Net GEX curve as a function of spot.
*Computation (the most precise disclosure on the site):* "It's derived from the **inflection point in the slope of the gamma exposure curve**" / "the point at which the **slope of the cumulative GEX curve changes**" / "the price where the cumulative gamma curve **reverses slope**." Reconstruction: build cumulative net dealer gamma as a function of hypothetical spot S, `Γ_net(S)`, and solve for the S where it crosses zero (equivalently where the slope of cumulative GEX inverts). Net dealer gamma is **positive above HVL, negative below**.
*Decision rule:* Above HVL → mean-reverting, chop, fade extremes, sell premium. Below HVL → momentum, clean breakouts, trend-follow, buy premium. **Convincing break of HVL is itself a tradeable event** — "market makers hedge, creating volatility spikes… strong excursion opportunities," target the next GEX level (typically GEX 3/4/5).
*Confidence:* **HIGH** on definition and rule; **MEDIUM** on reconstruction (the exact curve construction — whether they reprice gamma at each candidate spot or just use the static OI-weighted profile — is not stated).
*Sources:* [high-vol-level](https://menthorq.com/guide/high-vol-level/), [TrendSpider](https://trendspider.com/blog/menthorq-levels-indicators/), [gamma-levels-on-es](https://menthorq.com/guide/gamma-levels-on-es/)

**11. GEX 1 … GEX 10 (secondary ranked levels)**
*What:* Ten ranked secondary strikes. **This definition is the single most valuable extraction in this dossier** and the two published versions differ slightly:
- MenthorQ's own wording: "Levels with the **highest Net GEX and DEX** that are **within the 1D Exp Range**"; and "GEX Level 0 is the level with the highest Net GEX and DEX within the 1D Exp Move Max and Min."
- TrendSpider's wording: "the ten strikes with the highest overall gamma concentration, ranked 1 (highest) to 10 (lowest), **recalculated each session inside the 1-Day Expected Move range**."

*Inputs:* per-strike Net GEX **and** Net DEX; the 1D Expected Move Min/Max envelope (see #13) as a hard filter.
*Computation (reconstruction):* (a) compute per-strike Net GEX and Net DEX; (b) **discard every strike outside [1D Min, 1D Max]**; (c) score each surviving strike by a joint GEX+DEX magnitude; (d) rank descending; (e) emit top 10 as GEX 1..10. Note the off-by-one: some docs say GEX 0..10 (11 levels), the TradingView UI groups them as **"GEX 1–5"** and **"GEX 6–10"** (two separate toggles / alert groups), so the shipped schema is 10 levels.
*Decision rule:* "GEX Levels act as support and resistance throughout the day." Primary tactic is **GEX-to-GEX scalping**: "break of one GEX level often runs to the next," tradeable when the gap is ≥10 points (ES/NQ). Also used as profit targets after an HVL break.
*Confidence:* **HIGH** on schema and the 1D-range clipping; **MEDIUM** on how GEX and DEX are jointly scored (weights unpublished).
*Sources:* [key-levels-and-key-terms](https://menthorq.com/guide/key-levels-and-key-terms/), [TrendSpider](https://trendspider.com/blog/menthorq-levels-indicators/), [tradingview-scanner](https://menthorq.com/guide/tradingview-scanner/)

**12. 1D Expected Move Max / 1D Min**
*What:* The statistically expected high and low for the next session — "a daily price fence."
*Inputs:* Implied volatility (stated), plus, per a third-party review, "gamma and several other factors." Roadmap mentions adding **IV↔OI correlation and bid-ask spreads** as future inputs — which implies the current version is *IV-based with adjustments*, not a pure straddle price.
*Computation:* Not published. Almost certainly a 1-day IV scaling with a proprietary adjustment: `S × σ_1d × √(1/252) × k`, with asymmetric k up/down (the published hit rates are asymmetric: 87.62% vs 85.02%, so the bands are not symmetric or the distribution isn't).
*Decision rule:* Price fence for the day. Reaching 1D Max **above** Call Resistance "signals exhaustion rather than breakout." Hard filter for GEX-level ranking (#11). Used to size iron condors.
***PUBLISHED HIT RATES — the only auditable statistics MenthorQ publishes:*** SPX, **2019-11-01 → 2023-08-30**:
- **87.62%** of next-day closes stayed **above 1D Exp Min**
- **85.02%** of next-day closes stayed **below 1D Exp Max**
- **72.63%** of next-day closes stayed **inside** the range (the iron-condor case)
Single-stock results (AAPL, TSLA, NVDA) described as "consistent with SPX" but percentages withheld.
*Confidence:* **HIGH** on the statistics and decision rule; **LOW** on formula.
*Sources:* [backtesting-results-1d-move](https://menthorq.com/guide/backtesting-results-1d-move/), [1d-move-indicator](https://menthorq.com/quantitative-model/1d-move-indicator/), [optionstradingiq review](https://optionstradingiq.com/menthor-q-review/)

**13. Call Resistance 0DTE / Put Support 0DTE / HVL 0DTE**
*What:* Identical constructions as #8/#9/#10 but computed **only on the same-day-expiring chain**.
*Decision rule:* HVL 0DTE "flags intraday momentum shifts." These are the intraday-relevant lines; the all-expiry versions are the structural ones. Divergence between 0DTE and all-expiry HVL = the regime is fragile intraday but stable structurally.
*Confidence:* HIGH (schema + alert toggles documented).
*Sources:* [TrendSpider](https://trendspider.com/blog/menthorq-levels-indicators/), [tradingview-scanner](https://menthorq.com/guide/tradingview-scanner/)

**14. Gamma Wall 0DTE**
*What:* "Cluster of today's largest gamma strikes that can pin price until expiry." Distinct from Call Resistance 0DTE — it's a **cluster**, not a single argmax.
*Computation:* Not published. Reconstruction: contiguous run of adjacent 0DTE strikes whose combined GEX exceeds a threshold share of total 0DTE GEX; report the OI-weighted centroid.
*Decision rule:* Pin expectation → prohibits directional 0DTE premium buying at that price; favors premium selling / butterflies centered on it. It is an explicit alert type in the TradingView scanner.
*Confidence:* MEDIUM.

**15. Blind Spots Levels (BL 1 … BL 10)** — *the genuinely proprietary one*
*What:* Hidden reaction zones with **no visible price structure**, "calculated from gamma shifts in **correlated markets**."
*Inputs (all three published explicitly):*
1. **Options positioning** — "net buying and selling pressure" to locate large players.
2. **Momentum divergence** — divergence between price and momentum indicators flagging vulnerability to sharp moves.
3. **Cross-asset correlation** — how moves in one asset propagate. Named pairings: **SPX futures ↔ SPY, QQQ**; **NQ futures ↔ AAPL, MSFT, NVDA**; **BTC futures ↔ high-beta equities**; plus commodities, currencies, rates, and sector flows.
*Computation (this IS published, unusually clearly):* "The Blind Spots Model finds zones where **price levels from multiple correlated assets overlap**, creating clusters of potential market reaction points. These zones are ranked from **BL 1 to BL 10 based on the number of overlaps.**" **BL 1 = the strongest cluster, highest number of overlapping price levels. BL 10 = fewer overlaps.** With an explicit caveat: "**The ranking is a measure of overlap density, not a measure of certainty or importance.**"
*Reconstruction:* For target asset X, take the gamma-level sets of each correlated asset C_i, map each level into X's price space via the conversion ratio (#16), then cluster all mapped levels within a tolerance band; rank clusters by member count; emit top 10.
*Decision rule:* Explains why continuation "abruptly stalls" after a major gamma level breaks — dealers hit unexpected gamma there and must hedge, absorbing momentum. Published rules: (a) treat BLs as **targets** — take partials / tighten stops; (b) enter when price approaches a BL aligned with your bias; (c) **never open a trade directly into an opposing Blind Spot**; (d) require confluence with Q-Score or Gamma Levels.
*Availability:* ETFs, indices, futures, forex, crypto, and Mag-7 stocks. **EOD only, ~23:00 ET.** Available on TradingView, NinjaTrader, MetaTrader 5, Sierra Chart, Quantower.
*Confidence:* **HIGH** on the mechanism and ranking rule (verbatim). **MEDIUM** on the clustering tolerance and how momentum/positioning modulate the pure overlap count.
*Sources:* [blind-spots-levels guide](https://menthorq.com/guide/blind-spots-levels/), [blind-spot-levels model](https://menthorq.com/quantitative-model/blind-spot-levels/), [gamma-levels-on-forex](https://menthorq.com/guide/gamma-levels-on-forex/), [why-most-futures-traders-miss-dealer-flow](https://menthorq.com/guide/why-most-futures-traders-miss-dealer-flow/)

**16. Gamma Scalping levels / Gamma Scalping Intraday**
*What:* A **separate level model** — explicitly "more gamma levels within a **smaller range**, tailored for Futures Traders."
*Computation:* Not published. Structurally it must be the same GEX ranking as #11 but with a **narrower envelope than the 1D Expected Move** (likely a fraction of it, or an intraday-realized-range envelope), yielding denser levels.
*Decision rule:* Tighter scalping grid for ES/NQ; the four selectable models in every integration are `Gamma Levels | Gamma Levels Intraday | Gamma Scalping | Gamma Scalping Intraday`.
*Confidence:* **MEDIUM** (existence and purpose HIGH; construction inferred).
*Sources:* [sierra-chart-integration](https://menthorq.com/guide/sierra-chart-integration/), [quantower-integration](https://menthorq.com/guide/quantower-integration/)

**17. Levels Conversion (spread & ratio)** — fully published math
*What:* Projects one asset's option-derived levels onto another instrument (SPX→ES, QQQ/NDX→NQ, GLD→GC, DIA→YM).
*Computation (verbatim):*
- **Spread method:** `offset = Futures Price − Index Price` (ES 5000, SPX 4975 → +25); add offset to every level.
- **Ratio method:** `ratio = Futures Price ÷ Index Price` (ES 5000 / SPX 4975 = 1.005); multiply every level. Cross-instrument example: QQQ $500 → NQ 21,000 gives ratio 42, so QQQ 515 → **21,630**.
- Sierra Chart's auto mode computes `Base price ÷ Chart price` (QQQ 455 ÷ NQ 21,000 → 46.15385 — note this is the *inverse* orientation, so the sign/direction of the ratio is integration-specific).
*Modes:* Disabled / Manual (type the ratio) / Auto (from previous close, or a specific time, or real-time price).
*Known weakness MenthorQ admits:* auto mode uses prior-day closes and therefore "may lag intraday basis shifts" — i.e. dividend/rate/roll basis drift silently mis-locates every level. **This is where a competing implementation can beat them:** use live basis, not prior close.
*Confidence:* **HIGH** (verbatim formulas).
*Source:* [levels-conversion](https://menthorq.com/guide/levels-conversion/)

**18. Swing Trading Model — Upper Band / Lower Band / Risk Trigger**
*What:* ML-forecast swing levels over **5-day and 20-day** horizons. Three outputs: **Upper Band** (predicted max), **Lower Band** (predicted min), **Risk Trigger** (volatility/risk line).
*Inputs:* implied volatility + options data + historical price. Model class: "advanced machine learning algorithms" — unspecified.
*Decision rule:* Entry/exit envelope for swings; Risk Trigger is the invalidation line. Available on indices, stocks, ETFs, crypto. Shipped as "Swing Trading Levels" indicator on TradingView/Sierra Chart/Quantower.
*Published backtests exist but numbers are behind the guides:* dated monthly posts — Aug 2025, Feb 2025, October, "during Earnings," "during Reciprocal Tariffs," plus "Trading Like a Quant – Baseline Strategy + Alpha Factors." No hit rates surfaced on public pages.
*Confidence:* HIGH on outputs, **LOW** on model.
*Sources:* [swing-trading-model](https://menthorq.com/quantitative-model/swing-trading-model/), [swing-levels-backtesting category](https://menthorq.com/guide-category/quant-strategies/swing-levels-backtesting/)

### C. Q-Score family (the proprietary confidence/probability layer)

There is **no per-level probability score**. What you asked about — "proprietary probability/confidence scores per level" — does **not exist** in MenthorQ's product. The confidence layer is asset-level, not level-level: it's the Q-Score. This is an important negative finding.

**19. Q-Score (composite)**
*What:* Four sub-scores, each on its own scale, displayed side by side. **MenthorQ never publishes a weighted composite formula** — the guides present the four scores as a dashboard, not a single number.
*Sub-scores:* Momentum (0–5), Seasonality (−5…+5), Volatility (0–5), Options (0–5).
*Confidence:* HIGH on components/scales; **the aggregation formula and weights are explicitly undisclosed.**
*Source:* [the-menthor-q-score](https://menthorq.com/guide/the-menthor-q-score/)

**20. Momentum Q-Score (0–5)**
*Inputs:* "price changes across **multiple timeframes**, **trend smoothers**, **volatility adjustments**, and **relative performance metrics**"; combines short/medium/long-term; **adjusted for sector and asset-class differences**; damped so single-day spikes don't distort.
*Scale:* 0 = strong negative momentum, 3 = neutral, 5 = strong positive.
*Verbatim admission:* "While the exact formula is proprietary…"
*Confidence:* HIGH on inputs/scale, LOW on transform.
*Source:* [what-is-the-momentum-q-score](https://menthorq.com/guide/what-is-the-momentum-q-score/)

**21. Seasonality Q-Score (−5…+5)**
*Inputs:* **20 years** of closing prices; the **same forward 5-trading-day calendar window** in each of those years.
*Computation:* aggregate the 20 same-window observations, adjust for "statistical significance," normalize to −5…+5. **Not stated:** whether the statistic is mean return, median return, or hit rate.
*Best reconstruction:* a t-like standardization — `score = clip(5 × mean(r_window) / (std(r_window)/√20), −5, +5)` — which naturally implements the "statistical significance" adjustment they mention.
*Confidence:* MEDIUM-HIGH on spec (lookback and window are explicit), MEDIUM on statistic.
*Source:* [what-is-the-seasonality-q-score](https://menthorq.com/guide/what-is-the-seasonality-q-score/)

**22. Volatility Q-Score (0–5)**
*Inputs:* both historical and implied volatility. Updates daily. **Explicitly cross-asset comparable** — "similar scores represent equivalent volatility regimes regardless of asset class," which mathematically requires a **percentile / rank normalization within the asset's own history**, not an absolute vol level.
*Scale:* 0 = low-vol environment, 5 = high-vol environment.
*Confidence:* HIGH on scale, **MEDIUM** on the percentile inference (strongly implied by the comparability claim, not stated).
*Source:* [what-is-the-volatility-q-score](https://menthorq.com/guide/what-is-the-volatility-q-score/)

**23. Option Q-Score (0–5)**
*Inputs (verbatim list — the most specific factor list on the site):* "**Call vs. put volume, Changes in open interest at key strikes, Skew and slope of implied volatility, Relative strength of short-dated vs long-dated activity, Dealer gamma and delta positioning.**"
*Scale:* 0 = strong bearish sentiment, 3 = neutral, 5 = strong bullish. Explicitly a **directional** gauge, not a volatility gauge. High scores = concentrated call buying + favorable risk reversals; low = hedging demand / downside speculation.
*Confidence:* HIGH on inputs, LOW on weights.
*Source:* [what-is-the-option-q-score](https://menthorq.com/guide/what-is-the-option-q-score/)

### D. Volatility surface family

**24. Volatility Risk Premium (VRP)**
*What:* "evaluates today's implied volatility against **its own historical volatility and historical range**" → cheap / expensive / fair.
*Note the two-part construction:* IV vs HV (a spread) **and** IV vs its own historical range (a percentile). Lookback, weighting, and thresholds all undisclosed.
*Confidence:* MEDIUM on structure, LOW on parameters.
*Source:* [volatility-risk-premium](https://menthorq.com/quantitative-model/volatility-risk-premium/)

**25. IV Rank** — percentile of current IV within its own history; surfaced in `/liq_snapshot` and used as a QUIN screener filter ("IV Rank above 70%"). Standard construction. Confidence HIGH (existence), formula assumed standard.

**26. Volatility Smile** — IV by strike for a single expiry. Standard. Used to read where risk is being priced.

**27. Skew (`/skew`)**
*Definition finally pinned down here, and it's concrete:* the SPX skew chart plots spot price, **put/call OI ratio**, and **risk reversal = IV(25-delta OTM put) − IV(25-delta OTM call)**.
*Variants:* 0DTE Skew, 1-Month Skew, 3-Month Skew.
*Confidence:* **HIGH** on the 25-delta risk-reversal definition (from the Discord command doc — the model page itself hides it).
*Sources:* [discord-ai-bot-commands](https://menthorq.com/guide/discord-ai-bot-commands/), [skew model](https://menthorq.com/quantitative-model/skew-2/)

**28. Term Structure (`/term`)** — IV vs maturity, in **ATM** and **OTM** variants. Tenors, ATM interpolation method, and contango/backwardation thresholds undisclosed. Confidence: HIGH existence, LOW parameters.

**29. 3D Volatility Surface** — IV across strike × expiry. Visualization, no decision rule published.

**30. IV × OI / "sticky strikes" (`/ivoi`)**
*Computation:* "aggregates Implied Volatility and Open Interest **by strike**"; "**spikes** help identify strike levels that have **both** high Open Interest **and** high Volatility."
*Decision rule:* Coincident IV and OI spikes at the same strike = sticky strike = pin candidate. Explicitly positioned as **confirmation only**, "in conjunction with the Menthor Q Key Levels and Net Gamma Exposure." No absolute thresholds — relative spike detection.
*Confidence:* MEDIUM-HIGH.
*Source:* [implied-volatility-per-open-interest](https://menthorq.com/quantitative-model/implied-volatility-per-open-interest/)

### E. Flow / liquidity / microstructure

**31. Volume & Open Interest by strike (`/voloi`, `/voloi_0dte`)** — two-panel chart: **volume by strike (left), OI by strike (right)**, calls green / puts red, with a **put/call ratio heatmap**. Rules published are the classic ones (rising OI + rising price = bullish continuation; declining OI = reversal risk; volume confirms). Confidence HIGH on schema.

**32. Bid/Ask spread by strike (`/bidask`)** — liquidity gate. Narrow = liquid. This is a real tradeable filter and directly relevant to premium-buying vetoes.

**33. Option Matrix (`/matrix`)**
*What:* The daily consolidated dashboard, per ticker.
*Fields:* GEX and DEX across the chain; **0DTE, tomorrow, and out to ~1 month**; **changes** in gamma, delta, and open interest; key levels at each expiration. 5 days of history available via Discord.
*Decision rule:* Morning positioning brief; the **change** columns are the sentiment-shift detector.
*Confidence:* HIGH.
*Source:* [option-matrix](https://menthorq.com/quantitative-model/option-matrix/)

**34. Liquidity Summary / Gamma Condition (`/liq_snapshot`)**
*Fields:* **Implied Vol vs Historical Vol**, **IV Rank**, **1D Expected Move %**, and a **"Gamma Condition"** categorical regime label.
*Decision rule:* "Gamma Condition" is the one-word regime classifier (positive/negative/neutral gamma), exposed as a **column in the TradingView Scanner**. This is the cheapest single field to consume programmatically.
*Confidence:* HIGH.

**35. Intraday Gamma Change** — "measures increases/decreases in gamma **at specific strikes**" through the day, to reveal liquidity dynamics and detect **gamma flips** as they form. This is the closest thing MenthorQ has to a real-time flow alarm.

**36. Intraday Volume** — call and put volumes and **most-traded strikes** intraday; "liquidity hotspots and sentiment shifts to identify turning points."

### F. Positioning / systematic-flow models

**37. CTA Models (`/cta_table`, `/cta_index`, `/cta_currency`, `/cta_commodity`, plus per-asset: `/cta_spx`, `/cta_nasdaq`, `/cta_wti`, `/cta_brent`, `/cta_gold`, `/cta_natgas`, `/cta_treasury2Y`, `/cta_treasury10Y`, `/cta_copper`, `/cta_silver`)**
*What:* Estimated systematic-fund positioning plus **CTA trigger price levels** ("price levels that shape CTA trends").
*Computation:* "proprietary factors **similar to those used by investment banks**" — undisclosed. Industry standard (and the defensible approximation) is a blend of short/medium/long trend signals (e.g. 20/60/120-day breakouts or MA crossovers) mapped to a −100%…+100% notional exposure, with buy/sell/reversal trigger prices being the prices at which each signal flips.
*Decision rule:* Documented usage is **confluence**: "integrating CTAs with Key Levels and the 1D Expected Move" — i.e. a CTA reversal trigger that coincides with a GEX level is a higher-conviction level.
*Confidence:* HIGH on product surface, **LOW** on math.
*Source:* [ctas-models](https://menthorq.com/quantitative-model/ctas-models/)

**38. Volatility Control Fund Model (`/vol_control`)**
*Computation (the one concrete disclosure):* "**Compare 1-month realized volatility to 3-month volatility** to determine when these funds are going long or short on equities."
*Reconstruction:* `signal = RV_21d − RV_63d` (or the ratio). Vol-target funds delever when short-horizon RV > long-horizon RV. Rising RV_21/RV_63 → mechanical equity selling.
*Decision rule:* Anticipate mechanical supply/demand from vol-target funds; they "go long volatility and short equities during strong increases in realized volatility."
*Confidence:* **MEDIUM-HIGH** — the 1M vs 3M RV comparison is stated verbatim; the exposure mapping is not.
*Source:* [volatility-control-models](https://menthorq.com/quantitative-model/volatility-control-models/)

**39. Long-Short Volatility Barometer / LSVB (`/vol_barometer`)**
*Inputs:* **dollar volume traded** in long-vol and short-vol ETFs, plus open interest and Greeks.
*Decision rule (verbatim):* "**Rising LSVB** = increased shorting of volatility → bearish on volatility, **bullish S&P 500**. **Declining LSVB** = more people buying volatility → **bearish S&P 500**." Also used as a divergence detector vs actual price.
*Confidence:* MEDIUM-HIGH on direction, LOW on formula (ETF list and weights unpublished).
*Source:* [long-short-volatility-models](https://menthorq.com/quantitative-model/long-short-volatility-models/)

### G. Momentum / breadth models (fully transparent — these are NOT proprietary)

Unusually, MenthorQ publishes these completely. Source: [momentum-models](https://menthorq.com/quantitative-model/momentum-models/)

**40. Market Breadth (`/market_breadth`)** — % of S&P 500 constituents above their **200-day MA**. High = broad bullish; low = underlying weakness. Confidence **HIGH**, fully reconstructible.

**41. Trend Bias Indicator (`/trend_bias`)** — fast MA vs slow MA crossover state rendered as an **oscillator**; green = probable bullish, red = bearish. Windows unspecified. Confidence HIGH-ish.

**42. Supertrend (`/super_trend`)** — standard ATR × multiplier trailing stop; also reported as a **breadth count** ("S&P 500 stocks in Super Trend Buy Signal mode"). Multiplier/period unspecified but this is a standard public indicator. Confidence HIGH.

**43. RSI & Bollinger breadth (`/rsi_bollinger`)** — four panes: index price; count of stocks with **5-day RSI > 70**; count with **14-day RSI > 70**; count **above the upper Bollinger Band**. Overbought breadth → reversal risk or trend strength. Confidence **HIGH**, fully reconstructible.

**44. Moving-Average breadth (`/ma_indicator`)** — four panes counting stocks above their **5D, 20D, 50D SMA**. Confidence **HIGH**.

**45. MACD (`/macd_indicator`)** — 12/26 EMA difference with 9-day signal EMA; crossovers trigger. Confidence **HIGH**.

### H. Screening / interface / delivery

**46. Options Screeners** — three families: (a) quantitative-factor screening on options data, (b) **Key Levels screening** (i.e. screen for assets by proximity/position relative to their own gamma levels), (c) momentum screening blending TA with options data. Daily output list. Field list not public.

**47. QUIN (natural-language quant engine)** — NL → "structured market conditions, quantitative constraints, **ranked opportunity sets**." Documented example prompts reveal the actual queryable field space: *"top 25 Stocks with **IV Rank above 70%**, **Positive GEX**, and **Market Cap over $20B**"*; *"Technology Stocks with **high Momentum Score, low Implied Volatility**"*; *"biggest **Momentum Score increases vs yesterday** where IV Rank is still below 50%."* Also hosts **Request Levels**, which emits the TradingView paste-blob for: Gamma Levels EOD, Gamma Levels Intraday, Blind Spots, Swing Levels.
*Source:* [quin-the-quant-engine](https://menthorq.com/landing/quin-the-quant-engine/), [request-levels-via-quin](https://menthorq.com/guide/request-levels-via-quin/)

**48. TradingView Scanner (multi-ticker + alerts)**
*Capacity:* **40 tickers = 20 preloaded (daily EOD refresh) + 20 user-uploaded custom**.
*Columns (toggleable):* price, IV, **Gamma Condition**, and the four Q-Scores (Option, Volatility, Momentum, Seasonality).
*Confidence:* HIGH.
*Source:* [tradingview-scanner](https://menthorq.com/guide/tradingview-scanner/)

**49. The three TradingView indicators** — `MenthorQ Levels | End of Day` (pushes 18:30 and 23:00 ET), `MenthorQ Levels | Intraday` (multiple daily), `Custom Levels` (manual paste). Plus separate Blind Spots Levels, Swing Trading Levels, and Momentum indicators. The levels table renders in **tri-column format: Key Level name | Value | Distance to Spot**.

**50. Crypto Gamma Models** — same taxonomy (Net GEX, gamma levels, Net DEX, smile, skew, term structure, option matrix) applied to Deribit/Binance/OKX chains, with **"gamma flip zones"** as the headline signal. Documented external critique worth heeding: crypto **spot and perpetual volume dwarfs the options chain**, so GEX levels fail when perp flow dominates.

**51. Forex Key Levels** — gamma levels + Blind Spots on AUD, EUR, CHF, GBP, CAD, JPY, XAU, built from "options positioning in **Forex futures**" (i.e. CME FX options, not OTC — inferred from the 6E/6J/6A futures coverage list). EOD 23:00 ET.

---

## PART 2 — MATH GAPS: what is genuinely secret, and defensible approximations

Ranked by how much the secrecy actually matters.

**GAP 1 — The GEX kernel itself (per-strike gamma exposure).** Never published in any form; no formula, no worked example, anywhere on the site (I checked `what-is-net-gex`, `key-gamma-levels`, `free-gamma-exposure-chart`, `guide-to-gamma-exposure-gex-and-market-behavior`, plus all third-party writeups).
*Defensible approximation:* `GEX_k = Γ_k(BS) × OI_k × M × S² × 0.01 × sign_k`, with `sign_k = +1` for calls and `−1` for puts under the standard "dealers short customer options" convention (MenthorQ's own text supports the short-put-gamma assumption). Compute Γ from Black-Scholes using the strike's own IV (not ATM IV) — this matters at the wings and is the likeliest source of divergence between vendors. `S²×0.01` gives dollar-gamma per 1% move; MenthorQ may use per-1-point instead, which only rescales and does not move any level. **Level locations are invariant to the scaling constant** — so for reproducing *levels* (not magnitudes) you only need the relative per-strike weights.
*Known divergence evidence:* users report MenthorQ's gamma "doesn't match trusted sites such as unusualwhales" — consistent with a different sign convention, a different IV source per strike, or the inclusion/exclusion of certain expiries.

**GAP 2 — Whether the GEX curve is static or repriced.** HVL is defined as the inflection/zero-crossing of the **cumulative** GEX curve "as a function of price." Two implementations give materially different HVLs: (a) *static* — sum today's per-strike GEX and find where cumulative signed gamma crosses zero (cheap, what most vendors do); (b) *repriced* — for a grid of hypothetical spots S, re-run Black-Scholes gamma for every contract at S and re-sum, then find the S where net gamma = 0 (expensive, and gives a smoother, usually higher HVL). The phrase "**inflection point in the slope**" hints at (b), because a static cumulative sum has no meaningful inflection — only a zero crossing.
*Approximation:* implement (b) on a grid of ±3% around spot in 0.1% steps, holding IV and OI fixed; take the zero crossing of `Σ_k Γ_k(S) × OI_k × sign_k`. Falls back to (a) gracefully.

**GAP 3 — The GEX 1–10 joint GEX+DEX ranking score.** MenthorQ says the ranking uses "highest Net GEX **and** DEX," which is two quantities in different units. Weights unpublished.
*Approximation:* rank by `score_k = z(|GEX_k|) + λ·z(|DEX_k|)` with λ≈0.5 (gamma-dominant, matching the branding "GEX levels" not "GEXDEX levels"), z-scored within the 1D range. Sensitivity test λ ∈ {0, 0.5, 1}; if your top-5 set is stable across λ, the ambiguity doesn't matter.

**GAP 4 — The 1D Expected Move formula.** The published hit rates are **asymmetric** (87.62% above min vs 85.02% below max), which is diagnostic: a symmetric band on a left-skewed equity index return distribution would produce the *opposite* asymmetry. So MenthorQ is almost certainly applying an **asymmetric widening/calibration**, or using put-side and call-side IV separately.
*Approximation:* `Max = S·exp(+k_u·σ_call,1d·√(1/252))`, `Min = S·exp(−k_d·σ_put,1d·√(1/252))`, and **solve k_u, k_d empirically** to reproduce 85.0% / 87.6% coverage on your own SPX history. That's the right move: don't guess their formula, match their published coverage. Rough starting point: a straight 1σ IV band gives ~68% two-sided; their 72.63% two-sided coverage implies roughly **1.05–1.15σ**, with k_d slightly larger than k_u.

**GAP 5 — Blind Spots cluster tolerance and the weighting of the three inputs.** The *overlap-count ranking* is published; the *tolerance band* that defines an "overlap," the correlated-asset universe per target, and how momentum divergence and options positioning modulate the raw count are all secret.
*Approximation:* tolerance = 0.10 × ATR(14) of the target instrument (scale-free, works on ES and on EURUSD); universe = top-8 assets by 60-day return correlation to the target from within their published coverage list; map levels via the ratio method; rank clusters by member count, tie-break by mean correlation weight. Then apply their published caveat honestly: **overlap density ≠ probability.**

**GAP 6 — Gamma Scalping envelope.** Certain to be a narrower band than the 1D range; the band width is unpublished. *Approximation:* use 0.4–0.5 × the 1D range, or the trailing 5-day median intraday range, and emit 10 levels inside it.

**GAP 7 — Q-Score transforms.** All four are explicitly proprietary. The *input lists* are published in detail, especially for Option Q-Score. *Approximation:* build each sub-score as an equal-weighted average of z-scored inputs from the published lists, then map to the published scale via a rolling percentile (this automatically delivers the "comparable across assets" property they claim for Volatility Q-Score). Do **not** attempt a composite Q-Score — MenthorQ itself doesn't publish one, so there is nothing to match.

**GAP 8 — CTA trigger levels.** Fully secret ("similar to those used by investment banks"). *Approximation:* the standard bank replication — normalized blend of 2-week/1-month/3-month/6-month/12-month trend signals mapped to exposure ∈ [−1, +1]; the "trigger prices" are the prices at which each horizon's signal flips sign. Reproducible to within a few tenths of a percent of the published bank models.

**GAP 9 — No per-level probability exists.** Worth stating plainly because it was in the brief: MenthorQ publishes **no hit-rate, confidence, or probability score attached to individual levels**. The only per-level ordinal is the GEX 1–10 / BL 1–10 rank, and for Blind Spots they explicitly disclaim that the rank is *not* a measure of certainty. The competitor gex-levels.com states flatly: "Methodologies differ across all three vendors and **none of us publishes auditable accuracy statistics**." The 1D Move backtest (#12) is the single exception. **This is the clearest competitive opening in the entire product:** an empirically calibrated per-level hit rate, bucketed by regime and time-of-day, is something no vendor in this space ships.

**GAP 10 — The exact paste-format schema.** Not published anywhere public (it's generated inside the logged-in dashboard / Discord `/levels_tw`). Recoverable in one step with any free account: run `/levels_tw SPX` in Discord and read the string. Field names are known from the rendered table: `Call Resistance, Put Support, HVL, 1D Min, 1D Max, GEX 1…GEX 10, Call Resistance 0DTE, Put Support 0DTE, HVL 0DTE, Gamma Wall 0DTE` (+ `BL 1…BL 10` for Blind Spots, `Upper Band / Lower Band / Risk Trigger` for Swing).

---

## PART 3 — ALERT / SIGNAL TAXONOMY

MenthorQ's push surface has three distinct channels. There is **no webhook / streaming alert API** — alerts are either TradingView-native or Discord-bot pull.

### 3.1 Chart alerts (TradingView, via the MenthorQ Scanner)

Only **two trigger primitives** exist:
- **Break Out** — price crosses the level **from below to above**
- **Break Down** — price crosses the level **from above to below**

Selectable level sets for alerting:
1. Call Resistance
2. Put Support
3. High Volatility Level (HVL)
4. Daily Min / Daily Max (1D Expected Move bounds)
5. Call Resistance 0DTE
6. Put Support 0DTE
7. HVL 0DTE
8. Gamma Wall 0DTE
9. **GEX 1–5** (as a group)
10. **GEX 6–10** (as a group)

Delivery: TradingView popup / sound / email / mobile push. Wiring requires "Any alert() function call" as the condition.
**Documented operational weakness:** *"Users must recreate alerts daily to reflect updated level data, as alerts reference settings at creation time."* Every alert is stale the morning after. Any serious consumer must automate re-arming.
*Source:* [tradingview-scanner](https://menthorq.com/guide/tradingview-scanner/)

### 3.2 Regime alerts
Configurable notifications "when levels are **approached**" and when **regime shifts occur (positive → negative GEX)** — i.e. an HVL-crossing / gamma-flip alert distinct from the price-cross primitives above. Also surfaced passively as the **Gamma Condition** column in the scanner and in `/liq_snapshot`.

### 3.3 Discord bot — the full pull-based signal surface
Complete command list ([discord-ai-bot-commands](https://menthorq.com/guide/discord-ai-bot-commands/)):

| Group | Commands |
|---|---|
| Core levels | `/mainchart` (spot + Call Resistance + Put Support + HVL + forward GEX/DEX), `/key_levels` (the key-levels table), `/liq_snapshot` (IV vs HV, IV Rank, 1D Move %, Gamma Condition) |
| GEX | `/netgex` (5 days history), `/netgex_multiexpiry` (0DTE / WDTE / monthly), `/posgex` (top-10 +GEX/DEX strikes), `/neggex` (top-10 −GEX/DEX strikes), `/histgex` (SPX spot + GEX w/ SMA + DEX w/ SMA) |
| Matrix | `/matrix` (Option Matrix, 5 days history) |
| Flow / liquidity | `/voloi`, `/voloi_0dte`, `/ivoi`, `/bidask` |
| Volatility | `/term`, `/skew` (SPX: spot + P/C OI ratio + 25Δ risk reversal) |
| TradingView export | `/levels_tw <ticker>`, `/tw_list <up to 5 tickers>`, `/tw_toptk` (SPX, QQQ, VIX, IWM, TLT) |
| CTA | `/cta_table`, `/cta_index`, `/cta_currency`, `/cta_commodity`, `/cta_spx`, `/cta_nasdaq`, `/cta_wti`, `/cta_brent`, `/cta_gold`, `/cta_natgas`, `/cta_treasury2Y`, `/cta_treasury10Y`, `/cta_copper`, `/cta_silver` |
| Vol models | `/vol_control`, `/vol_barometer` |
| Momentum | `/market_breadth`, `/trend_bias`, `/super_trend`, `/rsi_bollinger`, `/ma_indicator`, `/macd_indicator` |
| Meta | `/help` |

### 3.4 Non-triggered pushes
- **Daily Newsletter** — morning research note from "Menthor Q Research," emailed.
- **Discord research channels** — daily morning notes, dedicated SPX / QQQ / VIX data feeds, premium rooms. Discord is described by a third-party reviewer as "MenthorQ's **main repository of information**."
- **Live Trading Sessions** — 9/week (Pro tier), 24h/week with pro traders, weekly mentorship, monthly strategy session.

---

## PART 4 — PUBLISHED TRADING RULES WITH ACTUAL NUMBERS

The Academy lesson [futures-trading-and-key-levels](https://menthorq.com/academy/trading-with-menthorq/lessons/futures-trading-and-key-levels/) is the only place MenthorQ publishes concrete probabilities and point values. Extracting them verbatim because they're the operational core:

**Put Support break (long-side):**
- Buy stop **above** the level when it breaks convincingly; confluence requirement: **VIX breaking below key resistance**.
- Stated: "**70% chance the initial balance low will be broken**" when the high forms first.
- Stated: "**80%+ chance of reaching 5-point target**."
- Management: take **2/3 at first target (~5 points or the next logical GEX level)**, move stop to breakeven, let **1/3** run to the next GEX level.

**Call Resistance reversal (short-side):**
- Sell **at** the level, tight stop just above. First-touch reversals only.
- Size from risk: **$400 risk ≈ 20 points**.
- **Pin risk to budget: ~20–27 points.**
- **Fractal rotation size: 4.3 points on ES, 22–23 points on NQ** — i.e. noise amplitude; stops inside this are guaranteed to be taken.

**HVL break:** trade convincing breaks; MM hedging creates volatility spikes; target GEX 3 / 4 / 5.

**GEX-to-GEX scalp:** break of one GEX level "often runs to the next"; only worth taking when the inter-level gap is **≥10 points**. Noted correlation between GEX levels and **VWAP ±1σ** — the only VWAP reference found anywhere in MenthorQ's material (there is **no VWAP-anchored level product**; that item in the brief does not exist).

**Explicit NO-TRADE conditions (published):**
- When levels **stack** — Put Support + HVL together, or Call Resistance + HVL together → "excessive chop," wait for a clean break of the whole congestion zone.
- When **VIX is pinning** around its own support/resistance at the open.
- Do **not** trade *between* congested areas; require price convincingly above/below the zone, secondary-timeframe confirmation, and VIX alignment (inverse to ES/NQ).
- Blind Spots: **never open a trade directly into an opposing Blind Spot.**

---

## PART 5 — COMMERCIAL / ACCESS FACTS

- **Pricing (July 2026, from [/pricing](https://menthorq.com/pricing/)):** Premium **$129/mo** (first month $39, coupon FIRST39); Pro **$349/mo** (first month $174.50, coupon FIRST50). Annualized per third party: $1,548 / $4,188. 7-day money-back. An older review lists Premium at $69/mo and a $399 one-time Academy — so **pricing roughly doubled**.
- **Free tier** exists: SPX/QQQ/VIX levels, the TradingView indicator, daily newsletter, Discord community. **The free tier is sufficient to reverse-engineer the paste-format schema and to sanity-check SPX levels against your own GEX build.**
- **Integrations (11):** TradingView, NinjaTrader, TrendSpider, ATAS, Quantower, Bookmap, Sierra Chart, MotiveWave, EdgeClear, Tickblaze, MetaTrader 5. Sierra Chart / Quantower / ATAS require Premium or Pro.
- **No public developer API documentation exists.** The "API" is an authenticated key consumed only by their own compiled platform plugins. No published endpoints, no OpenAPI spec, no rate limits, no JSON schema. There is **no open-source or community port** — every integration is a closed DLL or a MenthorQ-pushed Pine script. The only inspectable artifact is the plaintext paste-blob.

---

## PART 6 — CRITIQUES WORTH INTERNALIZING

From [Trustpilot](https://www.trustpilot.com/review/menthorq.com), Reddit-adjacent discussion, and [gex-levels.com](https://gex-levels.com/blog/menthorq-alternatives):
1. **Gamma values don't reconcile** with other vendors (unusualwhales named). Sign convention / IV-per-strike / expiry inclusion are the likely culprits.
2. **Crypto GEX is structurally weak** — spot and perp volume >> options chain, so dealer-hedging levels get overwhelmed. Applies with less force to single-name equities with thin chains.
3. **Intraday staleness for futures** — no native intraday futures gamma model; must convert from SPY/QQQ, and auto-conversion uses **prior-day closes**, so basis drift silently offsets every level.
4. **Breadth as friction** — "traders typically use only 2–3 models despite paying for the full suite." 51 catalogued features, ~10 load-bearing ones.
5. **No auditable accuracy statistics**, vendor's own competitor included. Only the 1D Move backtest is falsifiable.
6. **Alerts self-expire daily** — a documented operational defect, not a rumor.

---

## Sources

[menthorq.com](https://menthorq.com/) · [/guides/](https://menthorq.com/guides/) · [/quantitative-models/](https://menthorq.com/quantitative-models/) · [/pricing/](https://menthorq.com/pricing/) · [/features/](https://menthorq.com/features/) · [key-levels-and-key-terms](https://menthorq.com/guide/key-levels-and-key-terms/) · [high-vol-level](https://menthorq.com/guide/high-vol-level/) · [key-gamma-levels](https://menthorq.com/guide/key-gamma-levels/) · [blind-spots-levels](https://menthorq.com/guide/blind-spots-levels/) · [blind-spot-levels model](https://menthorq.com/quantitative-model/blind-spot-levels/) · [levels-conversion](https://menthorq.com/guide/levels-conversion/) · [what-is-net-gex](https://menthorq.com/guide/what-is-net-gex/) · [net-gex-vs-total-gex](https://menthorq.com/guide/how-to-interpret-net-gex-versus-total-gex/) · [trade-net-gex-levels](https://menthorq.com/guide/trade-net-gex-levels/) · [net-delta-exposure](https://menthorq.com/quantitative-model/net-delta-exposure/) · [1d-move-indicator](https://menthorq.com/quantitative-model/1d-move-indicator/) · [backtesting-results-1d-move](https://menthorq.com/guide/backtesting-results-1d-move/) · [the-menthor-q-score](https://menthorq.com/guide/the-menthor-q-score/) · [momentum-q-score](https://menthorq.com/guide/what-is-the-momentum-q-score/) · [seasonality-q-score](https://menthorq.com/guide/what-is-the-seasonality-q-score/) · [volatility-q-score](https://menthorq.com/guide/what-is-the-volatility-q-score/) · [option-q-score](https://menthorq.com/guide/what-is-the-option-q-score/) · [volatility-risk-premium](https://menthorq.com/quantitative-model/volatility-risk-premium/) · [swing-trading-model](https://menthorq.com/quantitative-model/swing-trading-model/) · [skew](https://menthorq.com/quantitative-model/skew-2/) · [term-structure](https://menthorq.com/quantitative-model/term-structure/) · [iv-per-oi](https://menthorq.com/quantitative-model/implied-volatility-per-open-interest/) · [option-matrix](https://menthorq.com/quantitative-model/option-matrix/) · [intraday-gamma-models](https://menthorq.com/quantitative-model/intraday-gamma-models/) · [momentum-models](https://menthorq.com/quantitative-model/momentum-models/) · [ctas-models](https://menthorq.com/quantitative-model/ctas-models/) · [volatility-control-models](https://menthorq.com/quantitative-model/volatility-control-models/) · [long-short-volatility-models](https://menthorq.com/quantitative-model/long-short-volatility-models/) · [volume-and-open-interest](https://menthorq.com/quantitative-model/volume-and-open-interest/) · [crypto-gamma-models](https://menthorq.com/quantitative-model/crypto-gamma-models/) · [key-levels-on-forex](https://menthorq.com/quantitative-model/key-levels-on-forex/) · [gamma-levels-on-futures](https://menthorq.com/quantitative-model/gamma-levels-on-futures/) · [gamma-levels stocks](https://menthorq.com/quantitative-model/gamma-levels/) · [options-screeners](https://menthorq.com/quantitative-model/options-screeners/) · [discord-ai-bot-commands](https://menthorq.com/guide/discord-ai-bot-commands/) · [tradingview](https://menthorq.com/guide/tradingview/) · [tradingview-scanner](https://menthorq.com/guide/tradingview-scanner/) · [sierra-chart-integration](https://menthorq.com/guide/sierra-chart-integration/) · [quantower-integration](https://menthorq.com/guide/quantower-integration/) · [menthorq-asset-coverage](https://menthorq.com/guide/menthorq-asset-coverage/) · [gamma-levels-futures-options](https://menthorq.com/guide/gamma-levels-futures-options/) · [gamma-levels-for-futures-trading](https://menthorq.com/guide/gamma-levels-for-futures-trading/) · [gamma-levels-on-es](https://menthorq.com/guide/gamma-levels-on-es/) · [why-most-futures-traders-miss-dealer-flow](https://menthorq.com/guide/why-most-futures-traders-miss-dealer-flow/) · [trading-below-put-support](https://menthorq.com/guide/understanding-trading-below-the-put-support-what-does-that-mean-for-traders/) · [how-to-trade-0dte-levels](https://menthorq.com/guide/how-to-trade-0dte-levels/) · [0dte-gamma-levels](https://menthorq.com/guide/0dte-gamma-levels/) · [request-levels-via-quin](https://menthorq.com/guide/request-levels-via-quin/) · [quin-the-quant-engine](https://menthorq.com/landing/quin-the-quant-engine/) · [Academy: futures trading and key levels](https://menthorq.com/academy/trading-with-menthorq/lessons/futures-trading-and-key-levels/) · [TrendSpider blog](https://trendspider.com/blog/menthorq-levels-indicators/) · [Quantower blog](https://www.quantower.com/blog/gamma-exposure-futures-trading-how-options-data-drives-price-action) · [ATAS marketplace](https://marketplace.atas.net/product/menthor-q-market-data-services) · [optionstradingiq review](https://optionstradingiq.com/menthor-q-review/) · [gex-levels comparison](https://gex-levels.com/blog/menthorq-vs-gex-levels) · [gex-levels alternatives](https://gex-levels.com/blog/menthorq-alternatives) · [Trustpilot](https://www.trustpilot.com/review/menthorq.com)