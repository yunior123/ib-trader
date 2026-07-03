# SpotGamma — Technical Dossier (proprietary metrics, mechanisms, math)

**Research note on access:** `support.spotgamma.com` blocks normal fetching (HTTP 403), but the underlying **Zendesk Help Center API is fully open and unauthenticated** — 417 articles, full HTML bodies:
`https://support.spotgamma.com/api/v2/help_center/en-us/articles.json?per_page=100&page=N`
`https://support.spotgamma.com/api/v2/help_center/en-us/articles/{id}.json`
`https://support.spotgamma.com/api/v2/help_center/en-us/{sections|categories}.json`
This is the single richest source and is how most HIGH-confidence entries below were obtained. `docs.spotgamma.com` does **not** exist; `spotgamma.com/model-faq/` 301-redirects to the support center. There is **no public API** ([confirmed](https://support.spotgamma.com/hc/en-us/articles/50266085426195)); EquityHub has a CSV export button. The TRACE User Manual PDF (`https://spotgamma.com/wp-content/uploads/2025/07/TRACE-User-Manual-Final-Version.pdf`, 841 KB) is **image-only — zero extractable text**.

**Data foundation** (HIGH — [article 50266146223123](https://support.spotgamma.com/hc/en-us/articles/50266146223123)): OPRA consolidated feed + direct US options exchange feeds + OCC weekly clearing data. All metrics are SpotGamma's own calculations on top of that. Coverage: US equities/ETFs/indices only; **no commodity options** — commodity exposure is proxied via GLD/IAU/SLV/USO/XLE/COPX ([50272004688403](https://support.spotgamma.com/hc/en-us/articles/50272004688403)).

---

## PART 1 — CATALOGUE OF FEATURES / METRICS / INDICATORS

### A. Foundational gamma math

**1. GEX (Gamma Exposure) — dollar notional dealer gamma**
- *What:* $ of stock dealers must transact per 1% move to stay delta-neutral.
- *Inputs:* per-contract gamma (BSM), open interest, contract multiplier (100), spot.
- *Computation (explicitly published):* `GEX = Gamma × OI × Contract Multiplier × Spot²`, summed over every strike & expiry. Sign convention: **calls contribute positive GEX, puts negative**; net of all = **Net GEX**. ([HIGH — support 15214161607827](https://support.spotgamma.com/hc/en-us/articles/15214161607827))
- *Caveat for reconstruction:* as written, `Γ·OI·100·S²` is $ per **100%** move; to get "$ per 1%" you need `×0.01`. SpotGamma's marketing number ("SPX GEX +$5bn = $5bn per 1% move") implies the 0.01 is applied internally. Also `Γ` here is per-$1 (i.e. `∂Δ/∂S`), so `Γ·S` = delta change per 1% and `Γ·S²·0.01` = $ notional per 1%.
- *Decision rule:* Net GEX > 0 → mean-reverting/compressed regime → sell premium (condors, CSPs, covered calls). Net GEX < 0 → amplification regime → long gamma/directional. Near zero → "most dangerous zone for complacent premium sellers."
- *Confidence:* HIGH.

**2. DDOI — Dealer-Directional Open Interest (the positioning assumption engine)**
- *What:* the unobservable split of OI between dealers and customers; everything else rests on it.
- *Published assumptions (this is the single most important reconstruction fact):*
  - **Index products (SPX/SPY/NDX/QQQ/RUT/IWM):** dealers modeled **SHORT puts, LONG calls** (justified by structural collar/call-overwriting flow).
  - **Single stocks (Equity Hub Total OI):** dealers modeled **SHORT both puts and calls**.
  - Free SPX GEX tool restates it: "options liquidity providers are short put options and long calls."
- *Sources:* [DDOI 15246735925395](https://support.spotgamma.com/hc/en-us/articles/15246735925395), [Structural Dealer Positioning 4413981525907](https://support.spotgamma.com/hc/en-us/articles/4413981525907), [free SPX GEX tool](https://spotgamma.com/free-tools/spx-gamma-exposure/).
- *Confidence:* HIGH.

**3. Net Gamma / "Gamma Notional (MM)"**
- `Net Gamma = Σ(call gamma) − Σ(put gamma)`, reported daily in $MM. Positive → lower forward RV; negative → higher forward RV. Explicitly: "low market gamma is not necessarily bearish." ([HIGH — 15413527450899](https://support.spotgamma.com/hc/en-us/articles/15413527450899), [15413312933011](https://support.spotgamma.com/hc/en-us/articles/15413312933011))

**4. Call Gamma / Put Gamma / Call Delta / Put Delta (per-name aggregates)**
- Call Gamma = Σ dealer call gamma over all strikes/expiries; Put Gamma = same for puts (modeled **negative** on indices). Call Delta = Σ dealer call delta; Put Delta = Σ put deltas **added as positive from the dealer perspective because dealers are consistently modeled short puts**. ([HIGH — 15412908066067, 15413629404051, 15412912150675, 15413528709395](https://support.spotgamma.com/hc/en-us/articles/15413528709395))

**5. Net Delta**
- `Net Delta = Total Call Delta − Total Put Delta`. Positive → dealers net long hedge; negative → net short hedge. Rule: large net delta expiring → hedge unwind → reversal risk. ([HIGH — 1500006848702](https://support.spotgamma.com/hc/en-us/articles/1500006848702))

**6. Gamma Profile / Delta Profile (the curve everything is read off)**
- *Computation:* re-price the whole modeled dealer book over a grid of hypothetical spot prices S, sum gamma (or delta) notional at each S → G(S), D(S). Annotated with Put Wall, Call Wall, Zero Gamma, Vol Trigger, Absolute Gamma, combos, large gamma strikes. Steep/vertical slope = high gamma rate-of-change = expected volatility; flat = calm. ([HIGH — 15413307516819](https://support.spotgamma.com/hc/en-us/articles/15413307516819), [15412965195283](https://support.spotgamma.com/hc/en-us/articles/15412965195283))

---

### B. Key levels (the product's core IP)

**7. Call Wall**
- *Definition:* **the strike with the largest net CALL gamma** in the underlying. (Note: the older Equity Hub levels glossary says "strike with largest call open interest" — [14356859960339](https://support.spotgamma.com/hc/en-us/articles/14356859960339) — a genuine internal inconsistency; the 2025-refreshed article defines it by gamma.)
- *Decision rules:* upper bound of expected range; fade strength into it; close above = regime flip, resistance→support, new wall resets higher within days; check for the next concentration above. Confirm with HIRO: negative HIRO delta flow at the Call Wall = structural resistance confirmed; flat/positive HIRO = level vulnerable.
- *Stats (SPX, 2019-05-10 → 2024-05-28):* held (intraday high did not exceed) **83%** of sessions; SPX closed below **88%**; post-breach forward returns −7bps (1d), +5bps (5d).
- *Confidence:* HIGH. [15297391724179](https://support.spotgamma.com/hc/en-us/articles/15297391724179), [31209900542867](https://support.spotgamma.com/hc/en-us/articles/31209900542867)

**8. Put Wall**
- *Definition:* strike with the largest net PUT gamma. Support because dealers short puts must buy as price falls toward the strike.
- *Stats:* held **89%** of sessions; SPX closed above **93%**; post-breach avg forward returns +14bps (1d), +7bps (5d), +39bps (10d).
- *Rule:* lower bound of expected gamma range; sell secured puts at/just below; break below = gamma collapses as puts go deep ITM (delta→−1) → hedging cushion disappears.
- *Confidence:* HIGH. [15297856056979](https://support.spotgamma.com/hc/en-us/articles/15297856056979)

**9. Zero Gamma**
- Spot level where the modeled net dealer gamma profile G(S) crosses zero. **Explicitly NOT support/resistance** — it is a regime marker, "the eye of the storm"; feedback loops do not ignite until price is *materially* away from it. ([HIGH — 15297958613907](https://support.spotgamma.com/hc/en-us/articles/15297958613907))

**10. Gamma Flip**
- The label for the same crossing on any product; "SpotGamma models the point of gamma flips … as the Zero Gamma level." ([HIGH — 15413261162387](https://support.spotgamma.com/hc/en-us/articles/15413261162387))

**11. Volatility Trigger™ (VT)**
- *What:* proprietary level below which bearish feedback loops are modeled to kick in; **"where dealers' last major level of positive gamma support is."** Generally the last major support **above** the Put Wall, and typically sits **several points above Zero Gamma** (earlier warning than the naive zero-crossing).
- *Mechanism:* below VT, MM hedging flips from counter-trend (vol-suppressing) to with-trend (vol-expanding).
- *Stats:* SPX opens above VT → avg 5-day RV **13%**; opens below → **18%**. Closes above VT → σ(1d ret) 0.9%, σ(5d ret) 2.0%; closes below → 1.3% / 2.7%.
- *Rule:* above VT → sell secured puts; below VT → bear put spread, momentum > mean reversion, pinning strategies (flies) degrade.
- *Confidence:* HIGH on definition/stats, **LOW on exact algorithm** (see MATH GAPS). [15297954935699](https://support.spotgamma.com/hc/en-us/articles/15297954935699), [spotgamma.com/volatility-trigger-zero-gamma-trading](https://spotgamma.com/volatility-trigger-zero-gamma-trading/)

**12. Hedge Wall**
- Single-stock analogue of the Vol Trigger: "the point where risk exposure changes significantly for options dealers" and where RV is expected to start increasing. Above it → mean reversion favored; below → momentum. Rising Hedge Wall = bullish, falling = bearish. Explicitly claimed to be "predictive of future volatility behavior with statistical significance."
- *Confidence:* HIGH on role, **LOW on formula**. [15297582984723](https://support.spotgamma.com/hc/en-us/articles/15297582984723)

**13. Key Gamma Strike**
- Strike with the **largest magnitude of combined (call+put) gamma**. Sticky pin / magnet, strongest when SG Gamma Index is positive. Most tactical level in normal vol regimes (more likely to interact with price than the distant Call Wall); Walls dominate in high-vol or longer horizons. ([HIGH — 15297780226451](https://support.spotgamma.com/hc/en-us/articles/15297780226451))

**14. Large Gamma Strike 1..n (index products)**
- Index-side equivalent of Key Gamma Strike, **ranked, 1 = strongest**; multiple per product. Under normal conditions their proximity makes them stronger magnets than the Walls. ([HIGH — 15297803530131](https://support.spotgamma.com/hc/en-us/articles/15297803530131))

**15. Key Delta Strike**
- Strike with the largest total delta. Because OTM strikes carry little delta, a strike must accumulate disproportionate OI to qualify → the level is ITM-option driven. Consequence: on a call-dominated name (AAPL) it can sit **below** the Put Wall; on a put-dominated name (MSFT), **above** the Call Wall. Rule: ITM Key Delta Strike → post-expiration reversal risk as dealer hedges unwind. ([HIGH — 15297677809683](https://support.spotgamma.com/hc/en-us/articles/15297677809683))

**16. Absolute Gamma**
- **Index products only.** The strike with the largest *total* gamma: because puts are modeled negative-gamma and calls positive, the calculation takes **|put gamma| + |call gamma|** so that it measures total magnitude rather than the net. Tends to sit near Zero Gamma. Read as the "stickiest" pin. ([HIGH — 15297255426195](https://support.spotgamma.com/hc/en-us/articles/15297255426195))

**17. High Volatility Point / Low Volatility Point (Synthetic OI only)**
- Two new levels introduced by the Synthetic OI model: **HVP = strike holding the most negative gamma; LVP = strike holding the most positive gamma.** ([HIGH — 39946919887891](https://support.spotgamma.com/hc/en-us/articles/39946919887891))

**18. Combos / Combo Strikes (SPX↔SPY, NDX↔QQQ, RUT↔IWM, DJX↔DIA)**
- *Computation:* aggregate total gamma across the index option chain **and** the ETF chain at price-equivalent strikes, then "back out what the equivalent price is in both SPX and SPY terms" (since 3100 SPX ≠ 310.0 SPY exactly). Ranked **1 (strongest) → 5 (weakest)** by gamma. Then mapped to **ES / NQ / RTY / YM** for futures traders; the SPX→ES basis "changes daily and is automatically adjusted by SpotGamma."
- *Positioning:* SpotGamma explicitly frames combos as **model-free** ("neither depend on models nor assumptions … simply showing gamma hotspots"), unlike the DDOI-dependent levels. Same claim is made for HIRO.
- *Rule:* magnets / speed bumps; strongest when coincident with persistent high-liquidity nodes in the order book (Bookmap dark-red persistent lines); trade credit verticals or spot with stops just beyond.
- *Confidence:* HIGH. [15297504641811](https://support.spotgamma.com/hc/en-us/articles/15297504641811), [spotgamma.com/combo-strike](https://spotgamma.com/combo-strike/), [1500006926242](https://support.spotgamma.com/hc/en-us/articles/1500006926242)

**19. Reference Price**
- SPX / SPX(prev) / SPY / NDX / QQQ price **at the timestamp the model snapshot was taken**. All levels/models are conditioned on it; if spot has since moved far, levels are stale. AM notes are weighted more heavily than PM because **OI is not updated until ~12:00 AM** ET. ([HIGH — 15297897280019](https://support.spotgamma.com/hc/en-us/articles/15297897280019), [1500006915501](https://support.spotgamma.com/hc/en-us/articles/1500006915501))

---

### C. HIRO (the flagship real-time signal)

**20. HIRO — Hedging Impact of Real-time Options**
- *What:* signed, aggregated **delta notional** of every options print, interpreted as the dealer hedging requirement it creates. 400+ US tickers.
- *Inputs:* every OPRA options print (trade price, size, strike, expiry), NBBO context, per-contract delta, spot.
- *Reconstructed algorithm:*
  1. For each print, infer **customer aggressor side** (buy vs sell) — the proprietary part.
  2. `impact_i = sign_i × Δ_i × qty_i × 100 × S` (delta notional), with sign flipped so that **customer call buying and put selling ⇒ positive HIRO; call selling and put buying ⇒ negative HIRO** (this convention is stated explicitly on the product page and in the screener article).
  3. **Filter:** the "All Trades" view "does use SpotGamma proprietary logic to filter out some trades that we consider hedged and therefore do not drive the underlying" (i.e. exclusions for delta-neutral/multileg/cross/tied-to-stock prints).
  4. **Sum over a rolling window** — user-selectable 1m / 5m / 10m / 30m / 1h / 4h / 1d; explicitly described as "the same concept as an SMA applied to a price chart."
  5. **Standardize across underlyings** "so that you can compare the HIRO value across instruments."
- *Views/filters:* Total (single net line) · Put/Call split (puts = dark blue, calls = orange) · **Next Expiry** (green line: 0DTE / next Friday / monthly only) · **Retail-only** (red) · 5-day history via calendar picker.
- *Decision rules:* (a) HIRO **flattening** at the Call Wall = local top; flattening at the Put Wall = local bottom, often sharp reversal. (b) After a Flow Alert, **wait for flows to "shut off," then trade the reversion**. (c) Flow concentrated in Next Expiry ⇒ unstable, reversion-prone; concentrated in longer-dated ⇒ stable ("longer-dated short puts added ⇒ RV measurably decreases"). (d) Advanced play: buy ITM spreads after sharp HIRO moves; sell premium when HIRO reverts at a Wall.
- *Confidence:* HIGH on inputs/outputs/rules; **MEDIUM-LOW on the aggressor-attribution and standardization internals.**
- *Sources:* [4420646443539](https://support.spotgamma.com/hc/en-us/articles/4420646443539), [4421103606803](https://support.spotgamma.com/hc/en-us/articles/4421103606803), [50265906309907 (rolling window)](https://support.spotgamma.com/hc/en-us/articles/50265906309907), [12284071347091 (All Trades filter)](https://support.spotgamma.com/hc/en-us/articles/12284071347091), [12284120712083 (Next Expiry)](https://support.spotgamma.com/hc/en-us/articles/12284120712083), [spotgamma.com/hiro-indicator](https://spotgamma.com/hiro-indicator/), [how-to-use-spotgamma-hiro-indicator](https://spotgamma.com/how-to-use-spotgamma-hiro-indicator/), [28192381417747 (checklist)](https://support.spotgamma.com/hc/en-us/articles/28192381417747)

**21. HIRO Signal gauge / 30-day range card**
- Full gauge width = **30-day range** of that ticker's HIRO; colored inner segment = **5-day range**; dot = today's reading. Dot color: green (positive flow), red (negative), yellow (neutral); dark/open circle = near HOD/LOD of the signal. Interpretation: dot near an extreme ⇒ elevated flow ⇒ **gamma levels are more likely to be respected today**; light flow ⇒ levels less reliable. Pair with the EquityHub Options Impact gauge. ([HIGH — 47874015095827](https://support.spotgamma.com/hc/en-us/articles/47874015095827), [50204551716755](https://support.spotgamma.com/hc/en-us/articles/50204551716755))

**22. HIRO Flow Alerts**
- "Using a proprietary SpotGamma model based on the size of hedging impact … **for all listed US options, SpotGamma calculates a specific 'impact threshold' for the given security, and alerts the user when this threshold has been breached.**" Per-symbol adaptive threshold (implies normalization by the ticker's own historical impact distribution). Available as a chart overlay ("SpotGamma Alerts" indicator), an alert log (All / Watchlist), and a bell that turns red. ([HIGH — 47871269691667](https://support.spotgamma.com/hc/en-us/articles/47871269691667))

**23. HIRO Stock Screener + Trending list**
- Screener: 400+ names with HIRO Signal gauge, price change, sector. Trending tab = "stocks of material interest, as determined by a proprietary SpotGamma algorithm … specific to each security." ([HIGH/LOW split — 47874015095827](https://support.spotgamma.com/hc/en-us/articles/47874015095827), [4421139806483](https://support.spotgamma.com/hc/en-us/articles/4421139806483))

---

### D. TRACE (intraday strike × time heatmaps for SPX)

**24. TRACE / Options Inventory Model**
- *Engine:* "SpotGamma's proprietary **Options Inventory Model** that determines intraday positioning for SPX options," ingesting all US-listed options. **Updates every 1 minute**, plus **5-day forward projections**.
- *Participant lens:* Market Makers (default), **Customers, Pro Customers, Firms, Broker Dealers** — these are the OCC/OCC-style origin classifications, meaning SpotGamma is attributing every print to a participant class.
- *Confidence:* HIGH on structure, LOW on the classifier. [33607907909011](https://support.spotgamma.com/hc/en-us/articles/33607907909011)

**25. TRACE Gamma Heatmap**
- Axes: x = time of day (+5-day forward), y = price/strike; color = selected participant's gamma at that price/time. **Blue = positive MM gamma = lower expected RV; Red = negative MM gamma = higher expected RV; white/black = neutral transition zone (little hedging).** Rules: price moves swiftly through neutral/negative zones, finds S/R in positive zones; pinning most likely in a blue zone with maximum effect at EOD; volatility most likely in red zones, also peaking at EOD. ([HIGH — 33608037264787](https://support.spotgamma.com/hc/en-us/articles/33608037264787))

**26. TRACE Delta Pressure Heatmap**
- "The **net change in options delta positioning** across all prices and time frames." Blue = dealers must **buy** to hedge; red = must **sell**. Contour lines = zone borders, "can guide toward closing levels."
- **Regime-conditional reading (the key rule):** in **positive** MM gamma, overhead red = selling resistance and underneath blue = support (containment, breaking them "takes considerable volume"); in **negative** MM gamma the same zones **invert into accelerants** — overhead blue extends rallies, underneath red extends selloffs.
- ([HIGH — 33608084842643](https://support.spotgamma.com/hc/en-us/articles/33608084842643), [spotgamma.com/options-delta-pressure-explained](https://spotgamma.com/options-delta-pressure-explained/))

**27. TRACE Charm Pressure Heatmap**
- Charm = ∂Δ/∂t. Heatmap of **time-decay-driven** hedging by price × time; heavily driven by 0DTE volume. **Red = options passively gaining value → dealers sell more futures (less support); Blue = options passively losing value → dealers buy more futures (more support).** Empirical claims: spot tends to migrate toward the **boundary where positive and negative MM charm meet at EOD**, and moves strongly *through* blue zones in that process. Charm dampens hedging flow from strong positive-gamma nodes → **pinning at EOD**; watch white/black between red and blue. ([HIGH — 33608198289043](https://support.spotgamma.com/hc/en-us/articles/33608198289043))

**28. TRACE Strike Plot**
- Three lenses by strike, per participant class: **GEX by strike** ("estimated local gamma for each individual strike," $ notional at current price; blue = positive/long gamma, red = negative/short), **OI by strike**, **Net OI by strike** (calls orange, puts blue). **0DTE toggle** isolates same-day positions. Rule: blue MM GEX ⇒ support/resistance; red ⇒ move amplification at that strike. ([HIGH — 33608227551379](https://support.spotgamma.com/hc/en-us/articles/33608227551379), [33608294279955](https://support.spotgamma.com/hc/en-us/articles/33608294279955))

**29. TRACE Stability Gauge**
- "Proprietary, **forward-looking** metric [that] evaluates the likelihood of large movement over the **next 10 minutes**. Higher values → lower likelihood of significant price movement." **Live only 09:30–15:30 ET**, greyed out thereafter. Rule: low reading = imminent gamma flip/vol expansion → tighten stops, exit range trades. Formula: "based on SpotGamma's proprietary analysis" — undisclosed. ([HIGH existence / LOW math — 50497959584787](https://support.spotgamma.com/hc/en-us/articles/50497959584787), [best-spx-0dte-indicators](https://spotgamma.com/best-spx-0dte-indicators/))

---

### E. Equity Hub (3,500+ names)

**30. Total OI Model**
- Pulls **total** OI, applies "some SpotGamma adjustments," and **predominantly assumes all options are sold by market makers**. Updated **nightly before the open**. Longest history / most validation. ([HIGH — 39946988410771](https://support.spotgamma.com/hc/en-us/articles/39946988410771))

**31. Synthetic OI Model (Alpha only)**
- "Eliminates assumptions and categorizes transactions based on multiple new data feeds and proprietary SpotGamma algorithms" — i.e. **infers whether each contract was bought or sold by the customer**, producing *signed* dealer inventory. Same logic used in TRACE for SPX. Updated daily pre-open. **Negative OI values are legitimate output and mean dealers are estimated net short those contracts.** Adds HVP/LVP levels. Positioned as superior to Total OI in a 0DTE-dominated market. ([HIGH — 39946919887891](https://support.spotgamma.com/hc/en-us/articles/39946919887891), [50266092992019](https://support.spotgamma.com/hc/en-us/articles/50266092992019))

**32. Put & Call Impact chart (both models)**
- x = strike. Bars = total/put/call gamma (or delta, or OI) by strike; overlaid **cumulative curves** with five toggles: total, next-expiration, monthly-expiration, **total minus next expiration**, **total minus monthly expiration** — i.e. an explicit "what does the surface look like after this expiry rolls off" differencing tool. Cumulative gamma curve is defined as "sum of ATM market maker gamma across all strikes." OI lens has three sub-views: total OI, **daily OI change**, and **net positioning** (bought vs sold). Rule: where the gamma curve **flattens**, hedging flow wanes → momentum stalls; steep = volatile. ([HIGH — 39946646214547](https://support.spotgamma.com/hc/en-us/articles/39946646214547), [8711555931027](https://support.spotgamma.com/hc/en-us/articles/8711555931027))

**33. Composite View — SG Momentum Indicator (Total OI) / SG Acceleration Indicator (Synthetic OI)**
- y-axis = **rate of change of gamma across strikes**; spikes ⇒ expect higher volatility in the name. Color encodes dominance: **green = calls driving (stability), red = puts driving (volatility)**; darkness = magnitude of options activity; a **blue outline** whose darkness = amount of options activity yesterday (dark blue = heavily traded, faint = large but stale position). ([HIGH — 14356919886227](https://support.spotgamma.com/hc/en-us/articles/14356919886227), [39946656110739](https://support.spotgamma.com/hc/en-us/articles/39946656110739))

**34. Options Impact gauge**
- "Measures how large **gamma exposure is relative to the stock's notional trading volume**." Green = options likely dominate flow, MM hedging should move spot, gamma levels reliable; red = stock volume dominates, gamma levels unreliable. Explicitly "a visual signal … not meant for precise analytical measurement."
- *Reconstruction:* `Impact ≈ |GEX$| / (ADV_shares × price)`, then percentile-ranked cross-sectionally.
- ([HIGH on definition / MEDIUM on exact ratio — 50204566966547](https://support.spotgamma.com/hc/en-us/articles/50204566966547))

**35. Equity Hub metric panel — the full column list (each is a distinct published metric)**
- *Levels:* Key Gamma Strike, Key Delta Strike, Hedge Wall, Call Wall, Put Wall, Call Gamma, Put Gamma, **Next Expiry Gamma %**, **Next Expiry Delta %** (>25% = significant short-dated concentration; large put deltas expiring → rally as dealers cover, large call deltas expiring → sell-off as dealers dump long hedges), Top Gamma Expiry, Top Delta Expiry, Call/Put Volume, Next Expiry Call/Put Volume %.
- *Directional:* Put/Call OI Ratio, **Gamma Ratio = total call gamma / total put gamma**, **Delta Ratio = total call delta / total put delta**, Volume Ratio = put vol / call vol. Low ratios ⇒ downside pressure.
- *Volatility:* **Net Expiry Skew** (next-expiry IV skew), **Skew** (30-day), 1M RV, 1M IV, **IV Rank** (vs prior year), **Garch Rank** ("proprietary measure of how a stock's volatility compares to the prior 30 days, **ignoring event-specific volume**"), **Skew Rank** (percentile of 25Δ call IV − 25Δ put IV vs prior year; high = bullish), **Options Implied Move** (30-day expected % move from IV).
- *Dark pool:* DPI, % DPI Volume, 5-Day DPI, 5-Day % DPI Volume.
- *History tab:* 30 trading days (Synthetic OI) / 10 days (Total OI); also 1M RV and **RV Rank** per ticker.
- ([HIGH — 14356859960339](https://support.spotgamma.com/hc/en-us/articles/14356859960339), [50264244088595](https://support.spotgamma.com/hc/en-us/articles/50264244088595))

**36. Equity Hub Skew chart**
- x = option **delta**, y = IV. Construction rule stated exactly: **for delta ≥ 50 use PUT IV; for delta ≤ 50 use CALL IV; at 50Δ average the two.** Green line = ~30 DTE, blue = next available expiry, dashed = yesterday's readings. Baseline assumption: "traders are on net selling calls and buying puts," so normal skew slopes up toward puts. Bullish skew (call IV ≥ put IV) flagged as a squeeze signature (GME example). ([HIGH — 8711432245779](https://support.spotgamma.com/hc/en-us/articles/8711432245779))

---

### F. Index/market-wide models (SPX, SPY, NDX, QQQ, RUT, IWM)

**37. SpotGamma Gamma Model**
- Gamma notional vs hypothetical spot. **Teal = current, gray = next expiration.** Steepest/most vertical slope ⇒ highest gamma rate of change ⇒ most expected volatility; flat ⇒ calm. Nearly vertical curve near the middle = very strong pin. ([HIGH — 15350835468307](https://support.spotgamma.com/hc/en-us/articles/15350835468307))

**38. SpotGamma Vanna Model** — *the most reconstructible of the "secret" models*
- x = spot, y = **delta notional**. **Gray/beige line = dealer delta exposure as spot moves with IV held constant. Purple line = same curve computed under "a complex SpotGamma implied volatility model, wherein we shift implied volatility along with the underlying asset price"** — i.e. an embedded spot–vol correlation (skew-dynamics) model.
- *Read:* the **gap between purple and gray = estimated vanna impact**. Purple **above** gray ⇒ extra dealer **selling** required ⇒ bearish vanna flow; purple **below** gray ⇒ net buying flow ⇒ bullish. Two prior days selectable.
- *Companion mechanism (glossary):* IV↑ pushes all deltas toward 50; IV↓ shrinks the implied range so OTM put deltas fall ⇒ dealers short puts on the Put Wall **buy back shares** ⇒ the classic "IV crush → rally" vanna flow.
- ([HIGH — 15350867797267](https://support.spotgamma.com/hc/en-us/articles/15350867797267), [16876455544851](https://support.spotgamma.com/hc/en-us/articles/16876455544851))

**39. SpotGamma Delta Model**
- Delta notional vs spot, point-in-time. **Orange = current expiration, gray = next expiration**; the **spread between the two lines** measures how much large ITM open interest is about to expire → expiration-driven regime shifts (calls expiring → downward pressure; puts expiring → upswing). ([HIGH — 15350839753875](https://support.spotgamma.com/hc/en-us/articles/15350839753875))

**40. SIV Index (SpotGamma Implied Volatility Index)**
- A curve of **expected % move as a function of strike/spot** — "how much volatility will take place relative to a shift in the underlying price." Green line higher ⇒ higher expected vol at that price. Explicitly reflexive: as spot moves, gamma changes, therefore vol changes. Use: structure positions against where vol is modeled to expand/contract; call/put gamma imbalance ⇒ expect more movement next day. ([HIGH on semantics / LOW on math — 15350841762963](https://support.spotgamma.com/hc/en-us/articles/15350841762963))

**41. SpotGamma Gamma Index™ (SG Index)**
- "Proprietary measurement of the total amount of market gamma … calculated by **computing market maker profits and losses based on the modeled data**"; described elsewhere as "the change in portfolio value due to gamma for a given change in SPX," compressed into a **two-digit scale with range −4 to +4**. Large positive ⇒ low forward RV, mean-reversion & premium selling; large negative ⇒ high forward RV, momentum/long-convexity. Claimed advantage over raw Gamma Notional: vol expansion clusters around 0 on the SG Index rather than around an arbitrary $1bn line. ([HIGH on range/use / LOW on scaling function — 15413702816275](https://support.spotgamma.com/hc/en-us/articles/15413702816275), [spotgamma.com/spot-gamma-index](https://spotgamma.com/spot-gamma-index/))

**42. Gamma Tilt & Delta Tilt charts / CP Gamma Tilt**
- **`CP Gamma Tilt = total call gamma / total put gamma`** — "much like a standard put/call ratio however we apply a **gamma weighting to the open interest**." Charted as a time series against price (left axis = price, right axis = tilt). Ratio ↑ = bullish signal; ratio ↓ = bearish. But as a **contrarian oscillator**: high peaks mark tops prone to reversal; **low readings are the higher-confidence signal** ("dealers have exhausted their positions and are properly hedged") for a reversal higher. Delta Tilt is the ITM-weighted analogue. ([HIGH — 1500006842661](https://support.spotgamma.com/hc/en-us/articles/1500006842661), [15350737304595](https://support.spotgamma.com/hc/en-us/articles/15350737304595))

**43. Absolute Gamma index chart** — gamma notional by strike, call gamma orange / put gamma blue, filterable to current or next expiration. Bar size = S/R strength; **clustering** of large bars = sticky zone that suppresses vol. ([HIGH — 15350709067027](https://support.spotgamma.com/hc/en-us/articles/15350709067027))

**44. Expiration Concentration chart / Concentration Table / Strike Table**
- Expiration Concentration: histogram of **delta notional hedging tied to each expiration out two years** (calls orange, puts blue) — quarterlies dominate. Concentration Table: by-expiry calls, puts, gamma notional, delta notional and their absolute values. Strike Table: same columns **by strike** for the upcoming expiry. **Explicit house threshold: look for strikes/expiries with >20% of total delta or gamma expiring** — puts-heavy ⇒ short-term bottom, calls-heavy ⇒ short-term top. (Scanner version uses ≥30%.) ([HIGH — 15350774629523](https://support.spotgamma.com/hc/en-us/articles/15350774629523), [15350936322963](https://support.spotgamma.com/hc/en-us/articles/15350936322963), [15350951180179](https://support.spotgamma.com/hc/en-us/articles/15350951180179))

**45. 0DTE Volume/Open Interest chart**
- White spikes = **0DTE volume as % of total options volume**; pink spikes = **0DTE-tied OI at the next expiration relative to total OI**. Rule: high levels ⇒ high speculation; **volume rising while OI flat ⇒ pure day-trading/intraday churn** (positions not carried). ([HIGH — 15350782964755](https://support.spotgamma.com/hc/en-us/articles/15350782964755))

**46. Open Interest & Volume Adjustments chart** — overnight OI change and prior-day volume by expiration, filterable puts/calls. ([HIGH — 15350877023123](https://support.spotgamma.com/hc/en-us/articles/15350877023123))

**47. Options Risk Reversal (index chart) + Risk Reversal (glossary) + 25D Risk Reversal**
- **`Risk Reversal = IV(30DTE 25Δ call) − IV(30DTE 25Δ put)`** (explicitly given in the Compass article). Falling / more negative ⇒ rising put demand ⇒ bearishness ⇒ often marks a near-term **bottom**; rising / less negative ⇒ call demand ⇒ often marks a near-term **top**. Also read as a skew-value trade ("if sharply negative, call skew may be underpriced"). ([HIGH — 15350940293523](https://support.spotgamma.com/hc/en-us/articles/15350940293523), [15412858897043](https://support.spotgamma.com/hc/en-us/articles/15412858897043), [1500007068782](https://support.spotgamma.com/hc/en-us/articles/1500007068782), [39936624524691](https://support.spotgamma.com/hc/en-us/articles/39936624524691))

**48. Realized Volatility chart / Price vs 2M-over-6M RV ratio**
- RV across multiple horizons on one chart; and **RV(2M)/RV(6M)** ratio overlaid on price — "tracked by many institutional investors" (this is the CTA/vol-target proxy). Ratio falling ⇒ stabilizing regime ⇒ systematic buying; ratio rising ⇒ near-term vol expansion. Tactical rule offered: sell equities if 5-day RV breaks out meaningfully vs 1-month+. ([HIGH — 15350881328403](https://support.spotgamma.com/hc/en-us/articles/15350881328403), [15350875021075](https://support.spotgamma.com/hc/en-us/articles/15350875021075))

**49. 5-Day & 30-Day Return Histogram** — distribution of 5d (red) and 30d (blue) returns; divergence in skew between the two windows drives breakout-vs-fade choice. ([HIGH — 15350947392915](https://support.spotgamma.com/hc/en-us/articles/15350947392915))

**50. Equity Put/Call Ratio chart** — **stocks only, ETFs and indices excluded.** White line = put volume / call volume; blue line = put OI / call OI, across all equities. Widening gap between the lines = rising speculation. ([HIGH — 15417104162835](https://support.spotgamma.com/hc/en-us/articles/15417104162835))

**51. Index Historical Chart / Real Time Updates chart** — SPX price history vs Call Wall, Put Wall, Volatility Trigger over time; and live intraday price overlaid on nearby SG levels. ([HIGH — 15350990363795](https://support.spotgamma.com/hc/en-us/articles/15350990363795), [15350634159123](https://support.spotgamma.com/hc/en-us/articles/15350634159123))

**52. SpotGamma Implied 1-Day Move / Implied 5-Day Move (EDM)**
- 1σ (68.3%) expected range for SPX, SPY, QQQ, NQ, RUT. **Critical methodological statement: "This is NOT a simple formula derived from implied volatility, but something that uses analysis based on decades of historical datasets"** — a historical/empirical expected-move estimator that *complements* the options-implied number.
- *Stats:* Implied 1-Day Move **not broken on 35%** of SPX trading days; SPX **closes within it 76%** of days. (LuxAlgo cites 78% for the same statistic.)
- *Rule:* build short-dated iron condors with wings at ±EDM; range = Reference Price ± EDM; **strong confluence signal when an EDM bound lands on a Wall or key level.**
- ([HIGH — 15297901147923](https://support.spotgamma.com/hc/en-us/articles/15297901147923), [15297916291347](https://support.spotgamma.com/hc/en-us/articles/15297916291347), [28242250556819](https://support.spotgamma.com/hc/en-us/articles/28242250556819))

**53. COR1M (1-month implied correlation) / dispersion context**
- 1-month implied correlation of constituents to index. **Explicit meta-rule: LOW COR1M ⇒ single-stock gamma levels are most reliable; HIGH COR1M ⇒ macro/index flow overrides single-name gamma, reduce reliance on individual levels.** Dispersion positioning shows up in HIRO/Synthetic OI as simultaneous unusual call/put activity across many single names with index vol moving the other way. ([HIGH — 50222242100627](https://support.spotgamma.com/hc/en-us/articles/50222242100627))

---

### G. Volatility Dashboard (Alpha)

**54. Fixed Strike Matrix** — real-time IV grid, strikes × expirations. **Color = IV Z-score vs the trailing mean (30/60/90-day, default 60) computed per expiration**; green = IV high vs the last two months, red = low. Toggle Statistical Mode off → teal shading = purely cross-sectional relative IV today. **Compare Mode** = IV delta between a reference date and a comparison date. **Show Highlights** = yellow border on cells with anomalous IV vs adjacent cells. **Skew Premium mode**. Prune Expirations / Prune Strikes to drop illiquid rows/columns; Zoomed Out view. ([HIGH — 23982224020115](https://support.spotgamma.com/hc/en-us/articles/23982224020115), [24155600468627](https://support.spotgamma.com/hc/en-us/articles/24155600468627), [24155655788947](https://support.spotgamma.com/hc/en-us/articles/24155655788947))

**55. Term Structure tab** — ATM IV vs expiration (x-axis switchable to DTE). Three overlays: (a) **Forward Implied Volatility Adjustment** — the time-adjusted forward IV; adjusted line **above** the spot IV curve ⇒ vol should be higher than priced ⇒ **mispricing/long-vol signal**; below ⇒ short-vol signal. (b) **Statistics cone** = 10th–90th percentile of historical IV for the same DTE. (c) **Economic Events overlay**. Multi-date comparison. ([HIGH — 23982205386131](https://support.spotgamma.com/hc/en-us/articles/23982205386131), [24155430800787](https://support.spotgamma.com/hc/en-us/articles/24155430800787))

**56. Volatility Skew tab** — IV across all strikes for one expiry; x-axis = **moneyness / fixed strike / delta**; 10th–90th percentile shaded band with **30/60/90-day lookback control**; above band = options expensive, below = cheap. ([HIGH — 23982082962195](https://support.spotgamma.com/hc/en-us/articles/23982082962195), [50261247317779](https://support.spotgamma.com/hc/en-us/articles/50261247317779))

**57. VIX Term Structure tab** — VX futures curve out ~9 months, multi-date compare, contango vs backwardation read. ([HIGH — 47604412344851](https://support.spotgamma.com/hc/en-us/articles/47604412344851))

---

### H. Flow products

**58. Tape** — live OPRA prints for 3,000+ tickers. **Flags: Sweep** (one order split across exchanges), **Cross** (buy and sell match exactly, i.e. net-zero), **Block** (privately negotiated), **Multileg**. Summary charts aggregate the filtered set into **volume / premium / delta / gamma / vega**, split puts vs calls ("Delta indicates how much directional market maker hedging is taking place"). Contract Data tab aggregates by strike/expiry. Reading framework: **Direction** (note: the article's wording is inverted/erroneous — it says "Call buying or put selling can indicate a bearish outlook," contradicting HIRO's own convention), **Conviction** (large premium, prints above ask / below bid, longer-dated), **Size**. ([HIGH — 36233401585683](https://support.spotgamma.com/hc/en-us/articles/36233401585683), [36233574999955](https://support.spotgamma.com/hc/en-us/articles/36233574999955), [36233656612243](https://support.spotgamma.com/hc/en-us/articles/36233656612243))

**59. Tape Highlights scanners** (refresh ~every 30 s, measured from prior close): **Top Options Volume**, **Top Daily Gamma Notional**, **Top Daily Movers**, **Largest Daily Trades (by premium)**. ([HIGH — 36233482307219](https://support.spotgamma.com/hc/en-us/articles/36233482307219))

**60. FlowPatrol** — daily report built on the **Synthetic OI model**, "identifying precisely whether calls or puts were bought or sold." Five reporting buckets: **Directional Positioning** (largest delta exposure), **Volatility Positioning** (gamma sign per name), **Premium** (capital committed), **Unusual Flows** (statistically unusual volume / "extreme" flow events), **Algo-driven Names** (names where algos react fast enough to amplify vol → trade cautiously). ([HIGH — 43687207115795](https://support.spotgamma.com/hc/en-us/articles/43687207115795))

**61. Dark Pool Indicator (DPI) + % DPI Volume + 5-Day DPI**
- Built from off-exchange (FINRA TRF) reported prints. `% DPI Volume` is defined in-doc as "**the number of shares sold short, both in dark pools and on listed exchanges, divided by the total shares outstanding**." DPI itself is a 0–100 % institutional-buying proxy exploiting the fact that a market maker buying from a seller books the fill as a *short sale* — so high off-exchange short % ⇒ institutional accumulation (the SqueezeMetrics DIX construction).
- *Published thresholds:* **DPI > 60 ⇒ positive 60-day forward return; DPI < 30 ⇒ negative 60-day forward return.** Color scale green (high) → red (low). Practical example readings cited: 55–56% = "strong institutional buying."
- *Confidence:* MEDIUM (exact numerator/denominator and normalization not disclosed). [1500006847122](https://support.spotgamma.com/hc/en-us/articles/1500006847122), [14356859960339](https://support.spotgamma.com/hc/en-us/articles/14356859960339), [14356662523027](https://support.spotgamma.com/hc/en-us/articles/14356662523027)

**62. OCC Indicator** — weekly refresh of OCC clearing data back to **2018**: opening vs closing transactions, by contracts and by premium, gross and net, split equities/ETFs/indices and calls/puts, and **filterable by transaction size as a retail-vs-institutional proxy**. Net call opening/premium buying ⇒ bullish speculation; put buying ⇒ hedging/downside speculation. ([HIGH — 1500006839861](https://support.spotgamma.com/hc/en-us/articles/1500006839861))

---

### I. Scanners, Compass, calculators

**63. Compass — Guided View**
- 2-D grid: **x/y = IV Rank** (current IV vs prior year) **and Risk Reversal Rank** (percentile of `IV(30DTE 25Δ call) − IV(30DTE 25Δ put)` vs prior year).
- *Backtested (1 year, 3,500+ US stocks; forward vol = stdev of daily returns over 10 days):*
  - Forward **returns highest** when Risk Reversal Rank **< 0.2**; lowest when RR Rank **> 0.6**, especially with IV Rank > 0.6.
  - Forward **volatility highest** when IV Rank **> 0.8** and RR Rank **< 0.2**; lowest when IV Rank **< 0.20**.
- *Rules:* high RR Rank ⇒ sell call spreads / buy puts; low RR Rank ⇒ sell put spreads / buy calls; low IV Rank + high RR Rank quadrant ⇒ buy puts (cheap options, rich call skew).
- ([HIGH — 39936624524691](https://support.spotgamma.com/hc/en-us/articles/39936624524691), [39936685498899](https://support.spotgamma.com/hc/en-us/articles/39936685498899))

**64. Compass — Explorer View** — arbitrary x/y + **z-axis as dot size**. Available fields include Call Skew Percentile, Put Skew Percentile, **IV Percentile** (% of prior-year days with lower IV), **Risk Reversal Percentile**, **Proximity to Call Wall / Put Wall** (% distance; broken walls plot on the grid border), RSI, **High Bollinger Band %**. Saveable configurations. ([HIGH — 39936583267859](https://support.spotgamma.com/hc/en-us/articles/39936583267859))

**65. The 15 Scanners** (universe = 3,500 names; four categories) — [14356506341395](https://support.spotgamma.com/hc/en-us/articles/14356506341395), [14356579936403](https://support.spotgamma.com/hc/en-us/articles/14356579936403)
- **Proprietary:** *Volatility Risk Premium* (unusually expensive options → sell premium); *Squeeze* ("based on **short interest, gamma levels, options volume, and a proprietary SpotGamma formula**").
- **Bullish:** Most Call Gamma; Lowest Put/Call Ratio; **Gamma Squeeze** (curated); Bullish Dark Pool (**DPI > 60**).
- **Bearish:** Most Put Gamma; Highest Put/Call Ratio; Bearish Dark Pool (**DPI < 30**).
- **Variable:** *1% Margin of Hedge Wall*; *Top Gamma % Expiring this Friday* (**≥30% of gamma expiring** = magnet that releases post-expiry); *Top Delta % Expiring this Friday* (**>30% of delta**= post-expiry reversal candidate); *Largest Delta Positions*; *1% Margin of Key Delta Strike* (acceleration or pinning); *High Impact* ("options activity which is driving the price and therefore respect our levels").
- *Confidence:* HIGH on rules/thresholds, LOW on the Squeeze/VRP/High-Impact formulas.

**66. Gamma Squeeze detection (conceptual model)**
- Published amplifying conditions: high OI concentrated in **near-term, slightly OTM calls**; short-dated expiry (peak gamma); **low float**; **negative Net GEX**. Escalation loop documented in 8 steps. GME/AMC Jan-2021 as case studies. Delivered operationally as the Gamma Squeeze scanner + **Top 5 Gamma Squeeze Candidates posted in Discord every Monday 08:30 ET**. ([HIGH — 31612163559955](https://support.spotgamma.com/hc/en-us/articles/31612163559955), [8703166764435](https://support.spotgamma.com/hc/en-us/articles/8703166764435))

**67. Options Calculator** — real-time-chain P&L modeling; 15 strategy templates (long call/put, 4 verticals, iron condor, iron butterfly, call/put fly, call/put calendar, call/put diagonal…); per-leg IV/Γ/vega/Δ/θ; **time-to-expiration slider** and **IV Shift + independent Call Skew / Put Skew shifts** rendering three curves (At-Expiration, Market-IV, IV-Adjusted); SpotGamma levels overlaid; saved positions; underlying stock legs. ([HIGH — 45971065009299](https://support.spotgamma.com/hc/en-us/articles/45971065009299), [45991791452691](https://support.spotgamma.com/hc/en-us/articles/45991791452691), [45991805373459](https://support.spotgamma.com/hc/en-us/articles/45991805373459), [45991838217619](https://support.spotgamma.com/hc/en-us/articles/45991838217619))

**68. Canvas** — customizable workspace: Workspaces → Containers (tabbed up to 5 components, or single) → **30+ Components** (HIRO, TRACE, Tape, Compass, Founder's Note, Vol Dashboard charts, Equity Hub charts). HIRO/TRACE/Tape limited to 2 instances per workspace. ([HIGH — 53010184312339](https://support.spotgamma.com/hc/en-us/articles/53010184312339), [53009660644371](https://support.spotgamma.com/hc/en-us/articles/53009660644371))

**69. Free tools (public, no login)** — [spotgamma.com/free-tools](https://spotgamma.com/free-tools/)
- **SPX Gamma Exposure chart**: "a standard net gamma curve, using basic assumptions that options liquidity providers are **short put options and long calls**," updated **daily**.
- **Implied Earnings Moves**: **ATM straddle price of the first expiration after the scheduled earnings date**, real-time.
- **Volatility Ranking Chart**: scatter of **IV Rank (x) vs Skew Rank (y)**, percentile-ranked, universe = largest options-volume names.
- **HIRO Indicator EOD charts**; **Options Profit Calculator**.

**70. Cloud Notes / platform level distribution** — SpotGamma levels streamed to **Bookmap, NinjaTrader, Jigsaw, eSignal, Sierra Chart, TradingView, EdgePro, thinkorswim**. Combo 1 = strongest. For futures: **labels stay in SPX/NDX terms but plot at the equivalent ES/NQ price; the basis "changes daily and is automatically adjusted by SpotGamma."** ([HIGH — 15297419607571](https://support.spotgamma.com/hc/en-us/articles/15297419607571), [1500006926242](https://support.spotgamma.com/hc/en-us/articles/1500006926242), [50270825725203](https://support.spotgamma.com/hc/en-us/articles/50270825725203))

**71. Founder's Note** — twice daily (pre-open and post-close). Contains Reference Prices, Gamma Notional (MM), SG Gamma Index, all key levels, Implied 1-day/5-day moves, economic-event warnings at the top, COR1M commentary. AM note weighted more heavily (**OI only refreshes ~00:00 ET**). ([HIGH — 15341610402579](https://support.spotgamma.com/hc/en-us/articles/15341610402579))

**72. Published academic/literature basis** — SpotGamma's own "Citations and Additional Reading" is **books only** (Natenberg 2015 — cited inline for the charm ≈20/80Δ peak and color ≈15/85Δ zero results, p.140/p.152; Bennett 2014 *Trading Volatility* p.87 for the vol feedback loop; Sinclair 2020 p.39-40 for VRP; Taleb, Gatheral, Derman & Miller, Cottle, Baird, Augen, McMillan, Passarelli, Mandelbrot, Wyckoff, Dalton, Schwager). **No peer-reviewed papers are cited by SpotGamma itself.** Third-party write-ups attach the standard literature — Baltussen/Da/Lammers/Martens (2021, JFE) on negative dealer net gamma amplifying moves; Ni/Pearson/Poteshman (2005) and Ni/Pearson/Poteshman/White (2021, RFS) on hedging-induced strike pinning; Gârleanu/Pedersen/Poteshman (2009, RFS) demand-based option pricing. SpotGamma also cites **Nations** whitepapers for SDEX and TDEX. ([HIGH for the book list — 15250346830995](https://support.spotgamma.com/hc/en-us/articles/15250346830995); MEDIUM for the paper attributions, which are third-party)

---

## PART 2 — MATH GAPS (what is genuinely secret, and a defensible approximation for each)

**G1. Volatility Trigger™ — the single most valuable secret.**
Known: it is derived from the *distribution* of dealer gamma, not a zero-crossing; it sits **above** Zero Gamma; it is "the last major level of positive gamma support"; it is generally the last major support above the Put Wall.
*Approximation:* build the dealer gamma profile `G(S)` on a spot grid (using the index convention: dealers long calls / short puts, and **re-solving IV per grid point via a spot-vol beta**, since the level's asymmetry vs Zero Gamma strongly implies vol dynamics are embedded). Then define VT as the **highest grid price `S* < spot` at which the positive-gamma density falls below a threshold τ·max(G)** — i.e. the lower edge of the last dense positive-gamma cluster — rather than the root of G. Calibrate τ (start τ ≈ 0.25–0.35) so the historical VT−ZeroGamma spread reproduces the published relationship and so that the RV split (13% above / 18% below, 5-day) is reproduced. A simpler and surprisingly serviceable proxy used widely in the wild: **VT ≈ the highest strike below spot whose strike-level net gamma is ≥ ~50% of the Put Wall's gamma**, i.e. the last big positive-gamma shelf.

**G2. HIRO's buy/sell (aggressor) attribution.**
Known: output is signed delta notional; the convention is + for customer call-buying/put-selling.
*Approximation:* Lee-Ready on OPRA prints against the prevailing NBBO — print ≥ ask ⇒ customer buy, ≤ bid ⇒ customer sell, mid ⇒ tick-test or drop. Then `impact = side × Δ × qty × 100 × S`, with Δ from a live-IV BSM fit. This is almost certainly the core; the residual secret is the refinement (exchange-specific quote latency alignment, sub-penny mid handling, and probably weighting by distance from mid to express conviction).

**G3. HIRO's "hedged trade" exclusion filter.**
Known: "proprietary logic to filter out some trades that we consider hedged and therefore do not drive the underlying."
*Approximation:* drop prints flagged **Cross**, **Multileg** legs whose net delta ≈ 0 (straddles/strangles/flies/condors/box), stock-tied (delta-neutral) prints, and same-timestamp same-size opposing prints across exchanges; net-out sweep child orders into one parent. Keep sweeps and blocks with non-zero net delta.

**G4. HIRO's cross-underlying standardization.**
Known: "standardized across underlyings so that you can compare HIRO values across instruments."
*Approximation:* divide raw delta-notional flow by a per-ticker scale — best candidates: 20-day median absolute HIRO, or `ADV_shares × price` (which is exactly the Options Impact gauge's denominator), or 20-day realized σ × market cap. The published 30-day/5-day range gauge is evidence they keep a trailing empirical distribution per ticker anyway, so **z-scoring against the trailing 30-day distribution is the defensible reconstruction**, and it also gives you Flow-Alert thresholds for free (G5).

**G5. HIRO Flow Alert "impact threshold" per security.**
*Approximation:* fire when the rolling-window HIRO increment exceeds `k` × (trailing 30-day standard deviation of same-window increments), with `k` ≈ 2.5–3, plus hysteresis (require the signal to cross back inside before re-arming) and a per-name cooldown. The docs' "wait for flows to shut off, then look for reversals" implies the alert is a *level-crossing of a rate*, not a cumulative total.

**G6. Synthetic OI / Options Inventory Model — participant classification and signed OI.**
Known: signed dealer OI (negative = dealers net short), participant classes MM/Customer/ProCustomer/Firm/BrokerDealer, daily pre-open for equities and 1-minute intraday for SPX.
*Approximation:* two-stage. (i) Classify each print's initiator by aggressor side + size/venue/flag signature (blocks & crosses → Firm/BrokerDealer; small sweeps at the ask → retail Customer; complex multileg at mid → Pro Customer). (ii) Maintain a per-strike running **net customer position** = Σ(opening buys − opening sells), reconciled nightly against the **actual OI change** published by OCC — the reconciliation constraint (Σ signed flow must match ΔOI) is the mechanism that turns noisy per-trade guesses into a stable inventory. Dealer inventory = −(customer inventory). Also use OCC's opening/closing volume splits (which SpotGamma already licenses for the OCC Indicator) as a weekly calibration prior.

**G7. TRACE Stability Gauge (P[large move in next 10 min]).**
*Approximation:* a supervised classifier / logistic model on features that TRACE already computes: local MM gamma sign and density at spot, distance to nearest gamma flip contour, charm-pressure gradient, 0DTE gamma share, realized 5-min σ vs its intraday norm, time of day. Target = |10-min forward return| > q-th percentile. Score inverted so high = stable. The 09:30–15:30 restriction is a strong hint the model was fit on intraday windows only and breaks down in the closing auction.

**G8. Implied 1-Day / 5-Day Move (EDM).**
Known: explicitly **not** an IV formula; built from "decades of historical datasets"; hit rates 65% not-broken / 76% close-within (1-day).
*Approximation:* a conditional empirical-quantile model: `EDM = 1σ of the historical distribution of |1-day return| conditioned on the current state` — state variables almost certainly including VIX level and term-structure slope, current Net GEX / SG Index bucket, distance to Vol Trigger, and event-calendar dummies. Fit as quantile regression or a bucketed empirical lookup; calibrate so 76% of closes land inside. A cheap baseline that gets close: `EDM ≈ β(regime) × VIX/16`, with β < 1 in positive-gamma regimes and β > 1 below the Vol Trigger — this alone reproduces the qualitative behaviour and the RV 13%/18% split.

**G9. SG Gamma Index scaling to [−4, +4].**
Known: computed from **modeled market-maker P&L** for a given SPX move, then compressed to two digits.
*Approximation:* `SGIndex = f(Σ ½·Γ_dealer·(ΔS)² )` — i.e. the second-order dealer P&L for a reference shock (a 1% SPX move is the natural choice) — then mapped through a **signed log or rank transform** normalized by a long-run scale so ±4 corresponds to historical extremes: `SGI = 4 · tanh( GammaPnL / c )` or `SGI = sign · min(4, log10(1+|GammaPnL|/c))`. The doc's claim that vol expansion clusters around 0 on SGI but around $1bn on Gamma Notional confirms a **nonlinear, non-centered** transform of raw notional.

**G10. Hedge Wall.**
Known: single-stock analogue of Vol Trigger; "where risk exposure changes significantly for options dealers"; statistically predictive of forward RV; sits between Put Wall and Call Wall.
*Approximation:* on the single-stock convention (dealers short **both** puts and calls), compute `D(S)` and `G(S)`; take the spot level where **|∂D/∂S| (i.e. total dealer gamma) is maximal**, or equivalently the price at which the dealer's required hedge quantity changes fastest. Given the "risk exposure changes significantly" wording, a defensible alternative is the argmax of `|D(S+δ) − D(S−δ)|` over the grid — a discrete max-hedging-shift point. Given it is described as functionally identical to VT, applying G1's threshold recipe to single-name gamma profiles is the cheapest consistent reconstruction.

**G11. SIV Index (expected % move as a function of spot).**
*Approximation:* `SIV(S) = σ_base × h( G(S) )` where h is decreasing in dealer gamma — e.g. fit `log RV_fwd = a + b·GEX_normalized(S) + c·log IV_ATM` historically, then evaluate across the spot grid. This is exactly the empirical content of the published RV 13%/18% split, generalized to a continuum.

**G12. Vanna model's "complex SpotGamma implied volatility model."**
*Approximation:* a spot-vol rule `ΔIV = −β · (ΔS/S)` applied to the whole surface (β ≈ 4–8 for SPX ATM 30d, higher for short-dated), optionally sticky-strike vs sticky-delta blended, then re-solve deltas at each grid point. The purple-minus-gray gap is then just `Σ vanna × ΔIV`. Higher fidelity: shift by the empirically fitted SPX skew-dynamics regression per tenor rather than a single β.

**G13. Squeeze scanner, VRP scanner, High Impact, Garch Rank, Trending algorithm.** All undisclosed.
*Approximations:* **Squeeze** = weighted rank composite of (short float, days-to-cover, call gamma concentration in near-term OTM strikes / float, options volume vs ADV, negative net GEX flag). **VRP** = `IV(30d) − RV(30d)` z-scored, or `IV/RV` percentile, ranked cross-sectionally. **High Impact** = the Options Impact gauge (`GEX$ / stock notional volume`) above a percentile cut. **Garch Rank** = fit GARCH(1,1) on returns with earnings/event days excluded (they say "ignoring event-specific volume"), then percentile-rank the conditional σ forecast against the last 30 days. **Trending** = per-ticker z-score of options volume / HIRO magnitude / price range vs its own recent baseline.

**G14. TRACE 5-day forward projection.**
*Approximation:* hold current OI fixed, roll `t` forward day by day (decaying θ/charm, re-computing Γ and Δ across the price grid, removing each expiration as it passes) → the heatmap is simply the current inventory re-Greeked on a (price × future-time) mesh. This one is fully reconstructible; no hidden data needed beyond the inventory.

**G15. Combo ranking 1–5 and the ETF↔index price mapping.** The mapping is a divisor/basis fit (SPX ≈ 10.0×SPY minus dividend/basis drift); the ranking is presumably just sorted combined gamma. Low risk.

**G16. Known internal inconsistencies to be aware of when replicating:**
- Call Wall / Put Wall are defined as **largest net call/put gamma** in the 2025 articles but as **largest call/put open interest** in the older Equity Hub levels article. Both are shipped in different places.
- The GEX formula as published (`Γ·OI·100·S²`) is missing the `×0.01` needed for the stated "per 1% move" interpretation.
- Tape's "Direction" paragraph inverts bullish/bearish relative to HIRO's own convention.
- Put gamma is signed **negative** on indices but put delta is summed as **positive** from the dealer perspective — sign conventions are not uniform across metrics.

---

## PART 3 — ALERT / SIGNAL TAXONOMY (everything the platform pushes)

**Real-time, event-driven (in-app bell + log + chart marker):**
1. **HIRO Flow Alert** — fires when a symbol's hedging impact breaches its own proprietary per-security impact threshold. On by default for the most active US tickers. Renders on the HIRO chart at fire time; addable as a chart indicator via **"SpotGamma Alerts."** Log has **All** and **Watchlist** tabs; bell turns red. ([47871269691667](https://support.spotgamma.com/hc/en-us/articles/47871269691667))
2. **Call Wall Breached**
3. **Within 1% of Call Wall**
4. **Put Wall Breached**
5. **Within 1% of Put Wall** — (2)–(5) are user-togglable in HIRO. ([47871269691667](https://support.spotgamma.com/hc/en-us/articles/47871269691667))
6. **Equity Hub Call & Put Wall Alerts** — same level events surfaced inside Equity Hub for single stocks, click-through to that name's Live Price & SG Levels chart. ([14433769048851](https://support.spotgamma.com/hc/en-us/articles/14433769048851))
7. **Fixed Strike Matrix "Show Highlights"** — yellow border flags cells whose IV is anomalous vs adjacent strikes/expiries (an in-grid alert, not a push).
8. **TRACE Stability Gauge** — continuous forward-looking risk read; low value = vol-expansion warning; greys out after 15:30 ET.
9. **Institutional tier** advertises **"Real-time alerts"** + **custom risk indicators** as a distinct entitlement (≥$1,999/mo).

**Scheduled reports:**
10. **Founder's Note AM** (pre-market) and **Founder's Note PM** (post-close) — levels, SG Index, Gamma Notional, Implied 1-/5-day moves, and an economic-event warning block at the top. AM is authoritative (OI refreshes ~midnight).
11. **FlowPatrol** — daily flow report (directional / volatility / premium / unusual flows / algo-driven names).
12. **OCC Indicator** — refreshed every weekend.
13. **Discord: Top 5 Gamma Squeeze Candidates — every Monday 08:30 ET.** ([8703166764435](https://support.spotgamma.com/hc/en-us/articles/8703166764435))
14. **Twice-weekly subscriber Q&A sessions** + Discord community.
15. **Cloud-note level pushes** to Bookmap / NinjaTrader / Jigsaw / eSignal / Sierra Chart / TradingView / EdgePro / thinkorswim, refreshed on their own schedules (index levels auto-adjusted to ES/NQ basis daily).

**Continuous scan lists (pull, ~30 s or daily refresh):**
16. **Tape Highlights** ×4 — Top Options Volume, Top Daily Gamma Notional, Top Daily Movers, Largest Daily Trades (≈30 s refresh).
17. **Tape trade flags** ×4 — Sweep, Cross, Block, Multileg (with savable filter presets).
18. **The 15 Scanners** — Volatility Risk Premium, Squeeze, Most Call Gamma, Lowest Put/Call, Gamma Squeeze, Bullish Dark Pool (DPI>60), Most Put Gamma, Highest Put/Call, Bearish Dark Pool (DPI<30), 1% Margin of Hedge Wall, Top Gamma % Expiring Friday (≥30%), Top Delta % Expiring Friday (>30%), Largest Delta Positions, 1% Margin of Key Delta Strike, High Impact.
19. **HIRO Trending tab** — proprietary per-security "material interest" trigger.
20. **HIRO Signal gauge extremes** — dot at either end of the 30-day range = today's flow is an outlier (soft alert).

---

## Practical takeaways for building against this

- **Fully reconstructible today** with an options chain + OI: GEX by strike, Net GEX, Call/Put Wall, Absolute Gamma, Key Gamma/Delta Strike, Net Gamma, Gamma/Delta Ratio, CP Gamma Tilt, Gamma/Delta profiles, Zero Gamma, Combos (SPX+SPY / NDX+QQQ), Expiration & Strike concentration with the **>20–30% expiring** rules, 25Δ Risk Reversal, IV/Skew/RV ranks, Max Pain, TRACE-style 5-day forward re-Greeking.
- **Needs a tick-level OPRA feed + aggressor inference**: HIRO, Tape, Synthetic OI / Options Inventory Model, Delta & Charm Pressure heatmaps, FlowPatrol.
- **Genuinely secret and only approximable**: Volatility Trigger, Hedge Wall, Stability Gauge, Implied 1-/5-Day Move, SG Gamma Index scaling, SIV, the vanna spot-vol model, Squeeze/Garch/Trending formulas, DPI's exact construction.
- **Highest-value published empirical anchors for calibrating your own levels** (SPX, 2019-05-10 → 2024-05-28): Call Wall holds 83% / closes below 88%; Put Wall holds 89% / closes above 93%; Vol Trigger splits 5-day RV 13% vs 18% and 1-day return σ 0.9% vs 1.3%; Implied 1-Day Move unbroken 35% of days, contains the close 76% of days; DPI>60 → positive 60-day forward return, DPI<30 → negative. ([31209900542867](https://support.spotgamma.com/hc/en-us/articles/31209900542867))

**Sources:**
- [SpotGamma home](https://spotgamma.com/) · [Support Center (KB)](https://support.spotgamma.com/hc/en-us) · [Plans & Pricing](https://spotgamma.com/subscribe-to-spotgamma/) · [Free Tools](https://spotgamma.com/free-tools/)
- [GEX Explained](https://support.spotgamma.com/hc/en-us/articles/15214161607827) · [DDOI](https://support.spotgamma.com/hc/en-us/articles/15246735925395) · [Volatility Trigger](https://support.spotgamma.com/hc/en-us/articles/15297954935699) · [Zero Gamma](https://support.spotgamma.com/hc/en-us/articles/15297958613907) · [Gamma Flip](https://support.spotgamma.com/hc/en-us/articles/15413261162387) · [Call Wall](https://support.spotgamma.com/hc/en-us/articles/15297391724179) · [Put Wall](https://support.spotgamma.com/hc/en-us/articles/15297856056979) · [Hedge Wall](https://support.spotgamma.com/hc/en-us/articles/15297582984723) · [Key Gamma Strike](https://support.spotgamma.com/hc/en-us/articles/15297780226451) · [Key Delta Strike](https://support.spotgamma.com/hc/en-us/articles/15297677809683) · [Absolute Gamma](https://support.spotgamma.com/hc/en-us/articles/15297255426195) · [Combos](https://support.spotgamma.com/hc/en-us/articles/15297504641811) · [SPX Key Levels Statistics](https://support.spotgamma.com/hc/en-us/articles/31209900542867)
- [HIRO](https://support.spotgamma.com/hc/en-us/articles/4420646443539) · [HIRO axes](https://support.spotgamma.com/hc/en-us/articles/4421103606803) · [HIRO rolling window](https://support.spotgamma.com/hc/en-us/articles/50265906309907) · [HIRO Flow Alerts](https://support.spotgamma.com/hc/en-us/articles/47871269691667) · [HIRO Screener](https://support.spotgamma.com/hc/en-us/articles/47874015095827) · [HIRO checklist](https://support.spotgamma.com/hc/en-us/articles/28192381417747) · [HIRO product page](https://spotgamma.com/hiro-indicator/) · [How to use HIRO](https://spotgamma.com/how-to-use-spotgamma-hiro-indicator/)
- [TRACE](https://support.spotgamma.com/hc/en-us/articles/33607907909011) · [Gamma Heatmap](https://support.spotgamma.com/hc/en-us/articles/33608037264787) · [Delta Pressure](https://support.spotgamma.com/hc/en-us/articles/33608084842643) · [Charm Pressure](https://support.spotgamma.com/hc/en-us/articles/33608198289043) · [Strike Plot](https://support.spotgamma.com/hc/en-us/articles/33608227551379) · [Stability Gauge](https://support.spotgamma.com/hc/en-us/articles/50497959584787) · [TRACE manual PDF (image-only)](https://spotgamma.com/wp-content/uploads/2025/07/TRACE-User-Manual-Final-Version.pdf)
- [Equity Hub](https://support.spotgamma.com/hc/en-us/articles/1500003037862) · [Equity Hub levels glossary](https://support.spotgamma.com/hc/en-us/articles/14356859960339) · [Synthetic OI model](https://support.spotgamma.com/hc/en-us/articles/39946919887891) · [Total OI model](https://support.spotgamma.com/hc/en-us/articles/39946988410771) · [Put & Call Impact](https://support.spotgamma.com/hc/en-us/articles/39946646214547) · [Negative OI](https://support.spotgamma.com/hc/en-us/articles/50266092992019) · [Options Impact gauge](https://support.spotgamma.com/hc/en-us/articles/50204566966547) · [Skew chart](https://support.spotgamma.com/hc/en-us/articles/8711432245779)
- [Gamma Model](https://support.spotgamma.com/hc/en-us/articles/15350835468307) · [Vanna Model](https://support.spotgamma.com/hc/en-us/articles/15350867797267) · [Delta Model](https://support.spotgamma.com/hc/en-us/articles/15350839753875) · [SIV Index](https://support.spotgamma.com/hc/en-us/articles/15350841762963) · [SG Gamma Index](https://support.spotgamma.com/hc/en-us/articles/15413702816275) · [SpotGamma Index page](https://spotgamma.com/spot-gamma-index/) · [Gamma/Delta Tilt](https://support.spotgamma.com/hc/en-us/articles/15350737304595) · [CP Gamma Tilt](https://support.spotgamma.com/hc/en-us/articles/1500006842661) · [Implied 1-Day Move](https://support.spotgamma.com/hc/en-us/articles/15297901147923) · [Implied 5-Day Move](https://support.spotgamma.com/hc/en-us/articles/15297916291347) · [COR1M](https://support.spotgamma.com/hc/en-us/articles/50222242100627)
- [Volatility Dashboard](https://support.spotgamma.com/hc/en-us/articles/24155944045459) · [Fixed Strike Matrix](https://support.spotgamma.com/hc/en-us/articles/23982224020115) · [Term Structure](https://support.spotgamma.com/hc/en-us/articles/23982205386131) · [Vol Skew](https://support.spotgamma.com/hc/en-us/articles/23982082962195) · [VIX Term Structure](https://support.spotgamma.com/hc/en-us/articles/47604412344851)
- [Tape](https://support.spotgamma.com/hc/en-us/articles/36233401585683) · [Tape flags](https://support.spotgamma.com/hc/en-us/articles/36233574999955) · [Tape scanners](https://support.spotgamma.com/hc/en-us/articles/36233482307219) · [FlowPatrol](https://support.spotgamma.com/hc/en-us/articles/43687207115795) · [Compass](https://support.spotgamma.com/hc/en-us/articles/39936536033171) · [Guided View](https://support.spotgamma.com/hc/en-us/articles/39936624524691) · [Guided View statistics](https://support.spotgamma.com/hc/en-us/articles/39936685498899) · [Explorer View](https://support.spotgamma.com/hc/en-us/articles/39936583267859) · [Scanners](https://support.spotgamma.com/hc/en-us/articles/14356579936403)
- [DPI](https://support.spotgamma.com/hc/en-us/articles/1500006847122) · [OCC Indicator](https://support.spotgamma.com/hc/en-us/articles/1500006839861) · [Gamma Squeeze](https://support.spotgamma.com/hc/en-us/articles/31612163559955) · [0DTE Explained](https://support.spotgamma.com/hc/en-us/articles/15298463039251) · [Citations](https://support.spotgamma.com/hc/en-us/articles/15250346830995) · [Data sources](https://support.spotgamma.com/hc/en-us/articles/50266146223123) · [API/export](https://support.spotgamma.com/hc/en-us/articles/50266085426195)
- [GEX playbook](https://spotgamma.com/gex/) · [Delta Pressure explained](https://spotgamma.com/options-delta-pressure-explained/) · [Combo Strike](https://spotgamma.com/combo-strike/) · [Best SPX 0DTE indicators](https://spotgamma.com/best-spx-0dte-indicators/) · [Vol Trigger for ES traders](https://spotgamma.com/volatility-trigger-zero-gamma-trading/) · [LuxAlgo third-party writeup](https://www.luxalgo.com/blog/spotgamma-levels-reveal-dealer-positioning/) · [BullishBears review](https://bullishbears.com/spotgamma-review/) · [OptionsScanners review](https://optionsscanners.com/review/spotgamma) · [Amberdata Derivs podcast Ep.67 w/ Brent Kochuba](https://amberdataderivatives.substack.com/p/ad-derivs-podcast-ep-67-brent-kochuba) · [Panoptica interview w/ Brent Kochuba](https://www.panoptica.com/the-intentional-investor-28-brent-kochuba/)