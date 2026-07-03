# MenthorQ: Open-Source Archaeology & Reproducible Spec

## Headline

MenthorQ's levels are **not a secret algorithm** — they are ranked/aggregated **dealer gamma exposure over a strike × expiration cube**. Three independent open-source artifacts leak the exact taxonomy, and one leaks the **private API itself**. Two Python repos implement the level extraction faithfully enough to clone. Everything except *Blind Spots* is reproducible today from an option chain with OI + gamma.

The single most valuable find: `joemccann/radon` contains a working, documented client for MenthorQ's authenticated dashboard API, including endpoint paths, payload schema, field names, and **units**.

---

## 1. Table of every public replication found

| Metric(s) covered | Repo / URL | Language | Quality | Data it needs |
|---|---|---|---|---|
| **The MenthorQ API itself** — endpoints, auth flow, full payload schema, units | [joemccann/radon → `scripts/clients/menthorq_dashboard_client.py`](https://github.com/joemccann/radon/blob/main/scripts/clients/menthorq_dashboard_client.py) | Python | **Faithful (authoritative)** — it *is* MenthorQ's data | MenthorQ account (Cognito/NextAuth session) |
| Call Resistance, Put Support, HVL, Gamma Wall, GEX 1-10, 1D Min/Max, 0DTE variants — **full computation from raw chain** | [maxkru92/mk-quant-monitor-cboe-gex → `cboe_menthorq_dashboard/gex_calculator.py`](https://github.com/maxkru92/mk-quant-monitor-cboe-gex/blob/main/cboe_menthorq_dashboard/gex_calculator.py) | Python | **Faithful on GEX/CR/PS/Wall/GEX1-10; WRONG on HVL** (uses volume+OI max instead of gamma flip) | CBOE delayed chain: strike, type, OI, volume, gamma, IV, expiry, spot |
| The exact MenthorQ output string format | [same repo → `menthorq_formatter.py`](https://github.com/maxkru92/mk-quant-monitor-cboe-gex/blob/main/cboe_menthorq_dashboard/menthorq_formatter.py) | Python | Faithful (byte-compatible with MQ bot output) | levels dict |
| Call Resistance / Put Support / HVL as **cumulative-GEX zero crossing** + gamma pin + negative-gamma pocket | [rxsinx/gex-analyzer → `modules/menthorq_gex.py`](https://github.com/rxsinx/gex-analyzer/blob/main/modules/menthorq_gex.py) | Python (plotly) | **Faithful on HVL** (cumsum zero-crossing = flip, matches MQ docs); definitions documented in-source | per-strike df: strike, call_gex, put_gex, total_gex, call_oi, put_oi |
| **Dealer's Bias** composite score from MenthorQ levels (6 weighted components, full formula + worked examples) | [jackson97300/MIA_IA_system_mentor_q → `docs/CALCUL_DEALERS_BIAS_MENTHORQ_SANS_POLYGON.md`](https://github.com/jackson97300/MIA_IA_system_mentor_q/blob/main/docs/CALCUL_DEALERS_BIAS_MENTHORQ_SANS_POLYGON.md) + `features/menthorq_dealers_bias.py` (933 lines) | Python | Rough-but-complete (heuristic weights, not derived) | MQ levels + blind spots + swing levels + VIX |
| **The definitive 19-subgraph level map** (Sierra Chart MenthorQ studies) | [same repo → `extracteur/MIA_Dumper_G10_MenthorQ.cpp`](https://github.com/jackson97300/MIA_IA_system_mentor_q/blob/main/extracteur/MIA_Dumper_G10_MenthorQ.cpp) | C++ (Sierra ACSIL) | **Faithful (authoritative ordering)** | Sierra Chart + paid MQ studies |
| GEX/DEX by DTE bucket, VRP, skew — as ML features | [PapaPablano/SwiftBolt_ML → `ml/src/models/menthorq_features.py`](https://github.com/PapaPablano/SwiftBolt_ML/blob/main/ml/src/models/menthorq_features.py) | Python | Rough (drops the ×0.01 1%-move scaling; puts not sign-flipped) | chain with OI, gamma, delta, IV + realized vol |
| Blind-spot / cross-asset **ratio projection** (VIX-scale levels → index scale) | [arnabmitra/menthorq-blind-spot-calculator](https://github.com/arnabmitra/menthorq-blind-spot-calculator) | Go | Toy (a multiplier + string reformatter) | MQ bot text output + a ratio |
| MenthorQ level ingestion + reversal/wick signal rules | [TraderOracle/TradingView → `MenthorQScanner.pine`](https://github.com/TraderOracle/TradingView/blob/main/MenthorQScanner.pine) | Pine v6 | Display + a real tradable rule (see §2.9) | pasted MQ string |
| MenthorQ level rendering (ATAS) | [TraderOracle/ATAS → `MenthorQ/MenthorQ_ATAS/MenthorQ_ATAS.cs`](https://github.com/TraderOracle/ATAS/blob/main/MenthorQ/MenthorQ_ATAS/MenthorQ_ATAS.cs) | C# | Display-only (reads local `Q-Levels.txt` CSV) | MQ level text file |
| MenthorQ → thinkorswim transpiler + **complete level color/name map** | [unfool/tos-mq → `mq-tos-bookmarklet.js`](https://github.com/unfool/tos-mq/blob/main/mq-tos-bookmarklet.js) | JavaScript | Faithful transpiler, zero math | scraped `.mb-2` text / clipboard |
| Canonical GEX + zero-gamma solver (the math MQ is built on) | [jensolson/SPX-Gamma-Exposure → `GEX.py`](https://github.com/jensolson/SPX-Gamma-Exposure/blob/master/GEX.py) | Python | **Faithful reference** | CBOE `.dat` chain download |
| Gamma flip via Newton solve on **live IBKR** data | [HKanwal/gamma-flip-line → `GEX_curve.py`](https://github.com/HKanwal/gamma-flip-line) | Python + ib_insync | Faithful (best fit for an IBKR shop) | IBKR: option contracts, OI, IV, greeks, spot |
| GEX theory + formulas + dealer sign conventions | [FlashAlpha-lab/gex-explained](https://github.com/FlashAlpha-lab/gex-explained) | Python + docs | Faithful (didactic) | chain |
| CBOE scraper → GEX by strike/expiry/surface | [Matteo-Ferrara/gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker) | Python | Faithful, minimal | CBOE web scrape |
| CBOE → GEX + **auto-generates Pine Script levels** + Telegram bot | [VandersonTorres/gamma-exposure-indicator](https://github.com/VandersonTorres/gamma-exposure-indicator) | Python + Playwright | Faithful, productionized | CBOE `delayed_quotes/{sym}/quote_table` |
| Peer-reviewed GEX pattern research + full pipeline | [iAmGiG/gex-llm-patterns](https://github.com/iAmGiG/gex-llm-patterns) | Python | Research-grade (IEEE BigData 2025) | Alpha Vantage premium chains, PostgreSQL |
| TradingView Pine "GEX levels" family — **all display-only shells** | [AlgoStorm GEX-L](https://www.tradingview.com/script/njrnkKZq-AlgoStorm-Gamma-Exposure-Levels-GEX-L/), [BackQuant](https://www.tradingview.com/script/nyyInUl8-Gamma-Exposure-Levels-BackQuant/), [GEX Walls](https://www.tradingview.com/script/lv1X2t8z-GEX-Walls-Market-Open-Shading/) | Pine | **Toy** — "blank visualization engine", zero computation | pasted CSV string (21 values: cw1-10, pw1-10, flip) |
| MenthorQ's own official TradingView indicator | [Menthor Q Levels](https://www.tradingview.com/script/pmd9wFIw-Menthor-Q-Levels) | Pine | **PROTECTED SOURCE** — closed | subscription |

**Discord bot** `David88-HH/menthorq-discord-bot` (Python) exists but contains no metric math — pure relay.

---

## 2. Reproducible algorithm specs

### 2.0 The ground truth: MenthorQ's own data model (reverse-engineered)

From `menthorq_dashboard_client.py` — this is what MenthorQ actually serves:

```
Auth:  dashboard.menthorq.io/api/auth/session  →  bearer access token (JWT, has exp)
       (WordPress login on menthorq.com redirects into a Cognito/NextAuth session)

GET https://gateway.menthorq.io/clickhouse-api/api/web/v1/options/net-gex-by-expiration/{SYMBOL}?frequency={eod|intraday}
GET https://gateway.menthorq.io/clickhouse-api/api/web/v1/gamma-levels/{SYMBOL}/eod
```

Exposure payload = **a sparse 2-D cube**:
```
ticker, frequency, timestamp, spot_price
strikes:     [float, ...]
expirations: [{expiration_date: "YYYY-MM-DD", dte: int}, ...]
cells: parallel arrays, one entry per (strike, expiration) pair:
    strike_idx, expiration_idx, net_gex, abs_gex, net_dex, abs_dex, oi_call, oi_put
```

Levels payload field names:
```
hvl, call_resistance, put_support, call_resistance_0dte, put_support_0dte, max_1d, min_1d
```

**Units — this is the load-bearing detail:**
```
net_gex, abs_gex  →  "usd_per_1pct_move"
net_dex, abs_dex  →  "usd"
oi_call, oi_put   →  "contracts"
```

`usd_per_1pct_move` is the fingerprint of exactly one formula: `Γ · OI · 100 · S² · 0.01`. MenthorQ is running the standard Perfiliev/SqueezeMetrics dollar-gamma convention. There is no proprietary kernel.

**The definitive level ordering** (Sierra Chart "MenthorQ Gamma Levels" study, 19 subgraphs — from `MIA_Dumper_G10_MenthorQ.cpp`):

```cpp
case 0: "call_resistance"       case 7:  "hvl_0dte"
case 1: "put_support"           case 8:  "gamma_wall_0dte"
case 2: "hvl"                   case 9..18: "gex_1" ... "gex_10"
case 3: "1d_min"
case 4: "1d_max"                // separate studies:
case 5: "call_resistance_0dte"  //   Blind Spots Levels = 10 subgraphs (BL 1..10)
case 6: "put_support_0dte"      //   Swing Levels       = 9 subgraphs
```

Corroborated independently by the tos-mq bookmarklet color map (`'Call Resistance', 'Put Support', 'HVL', '1D Min', '1D Max', 'Call Resistance 0DTE', 'Put Support 0DTE', 'HVL 0DTE', 'Gamma Wall 0DTE', 'GEX 1-10', 'BL 1-10'`) and the radon API `_LEVEL_FIELDS`.

Wire format of the MQ bot string (byte-exact, from `menthorq_formatter.py`):
```
$SPX: Call Resistance, 7600, Put Support, 7300, HVL, 7495, 1D Min, 7451.62, 1D Max, 7580.18,
Call Resistance 0DTE, 7550, Put Support 0DTE, 7475, HVL 0DTE, 7530, Gamma Wall 0DTE, 7550,
GEX 1, 7500, GEX 2, 7575, ...
```
Note weekly variants exist too (`HVL 1WTE`, `Put Support 1WTE`, `GEX Level 2`) and **multiple names collapse onto one price** when the same strike wins several rankings — visible in the arnabmitra README: `"HVL 1WTE & Put Support 1WTE & GEX Level 2, 12.5"`. Your parser must handle `&`-joined labels.

---

### 2.1 Foundation — Net GEX cube

**Inputs:** per contract `(strike K, expiry T, right, OI, gamma Γ or IV σ)`, spot `S`, risk-free `r`, multiplier `M` (100 equities/index; futures use contract multiplier).

**Steps:**
1. If gamma not supplied, compute Black-Scholes gamma at spot:
   `Γ = φ(d₁) / (S·σ·√τ)`,  `d₁ = [ln(S/K) + (r + σ²/2)τ] / (σ√τ)`,  `τ = DTE/365`.
   For index/futures options use the Black-76 forward form (jensolson uses `blackGamma(F=spotF)`).
2. Dollar gamma per contract, denominated per **1% move**:
   ```
   gex = Γ · OI · M · S² · 0.01
   if right == PUT: gex = -gex          # dealer short-gamma convention
   ```
3. Aggregate:
   ```
   call_gex[K] = Σ gex over calls at K       (≥ 0)
   put_gex[K]  = Σ gex over puts at K        (≤ 0)
   net_gex[K]  = call_gex[K] + put_gex[K]
   abs_gex[K]  = |net_gex[K]|
   gross[K]    = |call_gex[K]| + |put_gex[K]|
   ```
4. Same with delta for DEX: `dex = Δ · OI · M · S` (units USD, no 0.01).

**Edge cases:** drop `OI == 0` and `IV` NaN/≤0; `τ→0` on expiry day blows Γ up — floor `τ` at ~1/(365·6.5) (one hour) or 0DTE gamma goes to infinity at ATM; futures ↔ index price offset (Sierra's `NormalizePx` exists for exactly this — ES vs SPX basis); jensolson applies an ETF scale factor (`1.0` for SPX/NDX, `0.1` otherwise) — that's a display normalization, not physics.

**Sign-convention warning:** this convention assumes dealers are long calls / short puts. It is a *convention*, not a measurement. If you can classify trades (you cannot with OI alone) the true dealer book differs. Every public implementation makes the same assumption — including, by the units evidence, MenthorQ.

---

### 2.2 HVL (High Volume Level) = the gamma flip ⚠️ *the one definition the community gets wrong*

MenthorQ's own ES guide is unambiguous: *"Above 6975, net dealer gamma is positive. Below 6975, net dealer gamma turns negative"* — **HVL is the gamma flip**, not a volume level, despite the name.

**Two implementations exist. Use the second.**

- ❌ `maxkru92`: `hvl = argmax_K (total_volume[K] + total_oi[K])`. Literal reading of "high volume level". Cheap, wrong.
- ✅ `rxsinx`: zero-crossing of cumulative GEX. Documented in-source: *"Crosses zero exactly at the HVL / Gamma Flip level."*
- ✅✅ Best: full **re-priced** flip (jensolson / HKanwal), which is what a vendor computing this properly would do.

**Spec (cheap version, O(n)):**
```
sort strikes ascending
cum[i] = Σ_{j≤i} net_gex[K_j]
find i where cum[i] and cum[i+1] straddle 0
HVL = linear interpolation of K at cum = 0
```

**Spec (correct version — re-priced flip):**
Net gamma is a *function of spot*, because Γ itself moves. So solve for the spot where it vanishes:
```
def net_gamma(S_hyp):
    recompute Γ for every contract at S = S_hyp, holding σ, τ, K, OI fixed
    return Σ Γ · OI · M · sign(right) · S_hyp² · 0.01

coarse scan: S in [spot-500, spot+500] step 100   # HKanwal
    find bracketing interval where net_gamma changes sign
refine: Newton / secant to |net_gamma| < threshold
HVL = root
```
jensolson does the same thing with `np.interp(x=0, xp=gex_series, fp=index_prices)` over a sensitivity table.

**Edge cases:** multiple roots (report the one nearest spot, and flag the others — a second flip below is the real tail risk); no sign change in range → widen the scan, then return `None` and **degrade loudly**, never silently default to spot (the ATAS/bias code's `spot_price * 0.99` fallback is a landmine); holding σ fixed while moving S ignores the vol-spot correlation, which biases the flip *upward* in a selloff — accept it or add a skew-slide term.

**Validation:** re-price the flip 15 min apart on a quiet day — it should move far less than spot. Also assert `sign(net_gex_total)` agrees with `spot > HVL`.

---

### 2.3 Call Resistance ⚠️ *definitions conflict — pick one and measure*

Three mutually incompatible public definitions:

| Source | Rule |
|---|---|
| `maxkru92` | `argmax_{K > spot} call_gex[K]` — highest call GEX **above spot** |
| `rxsinx` | `argmin_K call_gex[K]` — most **negative** call GEX (their calls carry dealer sign already) |
| MenthorQ docs | *"the highest concentration of call gamma… dealers selling futures into strength"* |

The docs are consistent with `maxkru92`. `rxsinx`'s `idxmin` only makes sense under an inverted sign convention.

**Spec:**
```
candidates = {K : K > spot}
CR = argmax over candidates of call_gex[K]
if candidates empty: CR = argmax over all K of call_gex[K]
```
**Edge cases:** on a large gap-up the old CR sits below spot — recompute intraday, don't carry EOD levels through a gap. Require a minimum OI (HKanwal uses an `OI_CUTOFF`) or an illiquid far strike wins on a stale gamma print. For 0DTE (`call_resistance_0dte`) filter to `expiration == today` first.

---

### 2.4 Put Support

```
candidates = {K : K < spot}
PS = argmin over candidates of put_gex[K]     # most negative = largest put gamma
if candidates empty: PS = argmin over all K
```
Same edge cases mirrored. Docs: *"dealers typically hedge by buying futures, which can slow or halt downside momentum."*

---

### 2.5 Gamma Wall 0DTE

```
chain_0dte = {contracts : expiration == today}     # US/Eastern normalized
by_strike  = aggregate(chain_0dte)
gamma_wall = argmax_K abs_gex[K]                   # largest |net GEX|, either sign
```
**Edge cases:** the sign matters enormously and the metric throws it away — a `+` wall pins, a `−` wall accelerates. Carry `sign(net_gex[wall])` alongside the price; a "wall" at a negative-gamma strike is a trapdoor, not a floor. After ~15:00 ET 0DTE gamma is so concentrated that the wall == max OI strike and pinning dominates. This is directly your `oi-magnets-protocol` rule: **no bought 0DTE at a monster wall ±1 strike from spot.**

---

### 2.6 GEX 1 … GEX 10

```
GEX[1..10] = top 10 strikes ranked by abs_gex, descending
```
(`maxkru92`: `by_strike.sort_values("abs_gex", ascending=False).head(10)`.)

**Edge cases:** ties; strikes 1 tick apart producing 10 levels inside one point (dedupe by min-separation ≥ 1 strike interval); and note these are *unsigned* — half may be negative-gamma pockets. Keep the sign.

**The multiple-comparisons trap** — a Trustpilot reviewer nailed it: *"with 6 GEX levels, price hitting any one of them doesn't necessarily validate the model."* With 10 levels plus CR/PS/HVL/Wall/1D-Min/Max you have **≥16 lines** on the chart. Price will touch several every day by construction. Any hit-rate you measure must be against a null model of 16 random levels drawn from the same strike distribution. Do not skip this.

---

### 2.7 1D Min / 1D Max (expected move)

```
σ_atm = IV of the strike nearest spot in the front expiry
move  = S · σ_atm / √252
1D Min = S − move ;  1D Max = S + move
```
(`maxkru92.expected_move_1d`.)

Refinements worth making: use the **ATM straddle price** of the nearest expiry instead (`≈ 0.8 × straddle` for a 1σ day) — it embeds skew and event premium that a single IV print doesn't; interpolate IV to exactly ATM rather than snapping to nearest strike; use `√(1/252)` on trading days but **calendar** days across weekends/holidays (a Friday-close 1D level must span 3 days).

**Edge cases:** earnings day — this formula badly understates the move; MU/NVDA prints will blow through 1D Max routinely. Gate the level as invalid on the ticker's earnings date.

---

### 2.8 Blind Spots (BL 1 … BL 10) — *the only genuinely undisclosed metric*

MenthorQ's own guides describe inputs but not math: *"surface reaction zones calculated from gamma shifts in correlated markets"*; *"The Blind Spots Model finds zones where price levels from multiple correlated assets overlap, creating clusters of potential market reaction points"*, ranked **BL 1–BL 10 by overlap density**, with three stated input families: options positioning, momentum, asset correlation.

**Reconstructible spec (inference, clearly marked):**

```
1. UNIVERSE: for target asset X, pick correlated set C = {A₁..Aₙ}
   (rolling 60d return correlation |ρ| ≥ threshold; e.g. for ES:
    NQ, RTY, VIX, ZN, DX, GC, CL — for MU: SMH, NVDA, SKHY, EWY)

2. LEVELS: for each Aᵢ compute its own gamma level set
   L(Aᵢ) = {CR, PS, HVL, Gamma Wall, GEX 1..10}   (§2.1–2.6)

3. PROJECT onto X's price scale. Two ways:
   a) RATIO (what the community actually does — arnabmitra's tool
      multiplies VIX-scale levels by ~401–409 to land on index scale):
          K_X = K_Aᵢ · (S_X / S_Aᵢ)
   b) BETA (better): K_X = S_X · [1 + β_{X,Aᵢ} · (K_Aᵢ/S_Aᵢ − 1)]
      with β from the same rolling regression as ρ.

4. WEIGHT each projected level:
      w = |ρ_{X,Aᵢ}| · (normalized abs_gex of that level) · (momentum agreement)

5. CLUSTER projected levels on X's axis (1-D, e.g. mean-shift or
   simple bandwidth = 0.15% of S_X). Cluster score = Σ w  ("overlap density").

6. BL 1..10 = top 10 clusters by score, cluster centroid = the price.
```

**Validation:** you can *falsify* this against ground truth. Pull real BL 1-10 from the MenthorQ TradingView/Sierra study for ES, and grid-search over `{correlated set, projection method, bandwidth, weight formula}` minimizing mean |BL_yours − BL_theirs|. If a config lands within a few ticks on 10/10 levels across 20 sessions, you have cloned it. This is the single highest-value experiment in this whole document.

---

### 2.9 Community-derived signal rules (bonus — these are tradable, not just descriptive)

**MenthorQ Reversal** (`MenthorQScanner.pine`, `findMQMap`) — engulfing-style reversal *at* a level:
```
level L is "active" if  High > L and Low < L  AND  PrevHigh > L and PrevLow < L
                       (two consecutive bars straddle L)
REV LONG  := prev bar red  AND  current bar green  AND L active
REV SHORT := prev bar green AND current bar red    AND L active
```
This is your **PRINT-O-NADA rule expressed in code**: two readings crossing the level, not "está cerca." Worth porting straight into the fleet's signal layer.

**MenthorQ Wick** — rejection: `(High > L and Close < L) or (High > L and Open < L)`, with wick-dominance `|High−Close| > |Open−Close|`.

**Dealer's Bias** (`jackson97300`) — one composite number from the level set:
```
score = 0.25·gamma_resistance_bias + 0.20·gamma_support_bias
      + 0.20·blind_spots_bias      + 0.15·swing_levels_bias
      + 0.15·gex_levels_bias       + 0.05·vix_regime_bias
bias  = 2·(score − 0.5)                      # → [−1, +1]
BULLISH if bias > +0.30 ; BEARISH if < −0.30 ; else NEUTRAL

resistance_bias: dist ≤ 10 ticks → 0.2 ; spot < min(res) → 0.3 ; else 0.7
support_bias:    dist ≤ 10 ticks → 0.8 ; spot > max(sup) → 0.7 ; else 0.3
blind_spot_bias: dist ≤ 5 ticks → 0.2 ; ≤ 10 → 0.4 ; else 0.6
gex_bias:        fraction of GEX levels below spot
swing_bias:      fraction of swing levels below spot
vix_bias:        ≤15 → 0.6 ; ≤25 → 0.5 ; ≤35 → 0.4 ; else 0.3
```
Weights and cut-points are **hand-picked, not fitted** — treat the *structure* as the contribution and re-derive every constant against your own labelled outcomes (this is exactly the `calibration_ledger.py` pattern: probability by measured bucket, never hardcoded).

---

## 3. Published empirical evidence, with numbers

### Strong — vendor-published level statistics (directly transferable to CR/PS)
[SpotGamma SPX Key Levels Statistics](https://support.spotgamma.com/hc/en-us/articles/31209900542867-SpotGamma-SPX-Key-Levels-Statistics), the closest thing to a published hit rate for a Call/Put Wall:

| Statistic | Value |
|---|---|
| Call Wall held (intraday high did **not** exceed it) | **83%** of sessions |
| Put Wall held (intraday low did **not** breach it) | **89%** of sessions |
| SPX **closed** below Call Wall | **88%** of sessions |
| SPX **closed** above Put Wall | **93%** of sessions |
| Fwd return after Call Wall breach | **−7 bps** (1d), **+5 bps** (5d) |
| Fwd return after Put Wall breach | **+14 bps** (1d), **+7 bps** (5d), **+39 bps** (10d) |

Read this carefully before trading it: an 83–93% "hold" rate on a level that sits ~1–2% away is **mostly the unconditional distribution of daily ranges**, not edge. The tradable content is the asymmetry — breaching the Put Wall is mildly *bullish* forward (mean reversion / dealers buying), breaching the Call Wall is flat-to-negative. That matches your captain doctrine: **massive put flow from the captain = sector rebound.** An independent backtest cited alongside found sustained (non-transient) wall breaks occur only **14–30%** of the time across three tickers — i.e. first touch usually rejects, consistent with your "1er toque rebota ~70%."

### Strong — peer-reviewed academic
| Paper | Finding with numbers |
|---|---|
| Baltussen, Da, Lammers, Martens, **JFE** Oct 2021, *[Hedging Demand and Market Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365)* | 60+ futures, 1974–2020. Last-30-min return positively predicted by rest-of-day return; economically and statistically highly significant; reverts over following days. **Momentum is significantly stronger on negative Net Gamma Exposure days.** This is the academic license for your negative-gamma = band-walk regime. |
| Buis, Pieterse-Bloem, Verschoor, Zwinkels, **JEDC** 164 (2024) art. 104880, *[Gamma Positioning and Market Quality](https://pure.eur.nl/files/149733755/1-s2.0-S0165188924000721-main.pdf)* | Higher net dealer gamma → **lower volatility, higher stability**; negative gamma → **higher volatility, market more prone to failure**. Positive gamma sustains liquidity in stress; negative gamma depletes it. Caveat with teeth: **price discovery worsens as dynamic hedgers grow, regardless of sign** — levels get stickier but less informative. |
| Ni, Pearson, Poteshman (2005) | Option-market-maker hedging impact **clusters at expiration around optionable strikes** — the original pinning result underneath "Gamma Wall 0DTE". |
| Dim, Eraker, Vilkov, *[0DTEs: Trading, Gamma Risk and Volatility Propagation](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4692190)* | 0DTE gamma imbalance and intraday volatility propagation; large negative gamma imbalance correlates with **increased intraday price jumps**. |

### Strong — and the most sobering number in this document
[iAmGiG/gex-llm-patterns](https://github.com/iAmGiG/gex-llm-patterns), IEEE BigData 2025 ([arXiv 2512.17923](https://arxiv.org/abs/2512.17923)) + AIAI 2026:

| Metric | Result |
|---|---|
| GEX-regime detection, obfuscated data | **71.5%** (242 SPY days, 2024) |
| Predictive accuracy on forward returns | **90.9%** |
| **Raw strike chain vs pre-computed GEX scalar** | **92.3% vs 61.5% (+30.8 pp)** |
| Regime detection 2024 vs 2020 | **81.2% vs 12.1%**; 69.1 pp separation, φ=0.672, p<0.0001, 1,412 windows + 809 controls |
| 0DTE adoption over period | 3.7% (2021) → 100% (2024); GEX magnitude **+360%** |
| **Detection ≠ profitability** | detection stable 68–74% quarterly while **Sharpe collapses 1.8 → 0.1** |

Two conclusions you should act on. First: **scalar aggregation destroys signal** — the raw strike-level chain outperformed pre-computed GEX by 30.8 pp. MenthorQ sells you 19 scalars extracted from a cube; keep the cube. Second: the structure is real and *still* stopped paying. Detectable ≠ exploitable.

### Weak / cautionary — the only public MenthorQ-specific "backtests"
From `jackson97300/MIA_IA_system_mentor_q`, reported honestly because it matters:

| File | Numbers |
|---|---|
| `menthorq_optimization_recommendations.json` | baseline **15 trades, 33.3% WR, avg −0.85**; "optimized" **2 trades, 100% WR** → reported as "+66.7 pp winrate improvement" |
| `menthorq_optimization_results.json` | **1,000 parameter combinations tested**, `best_performance.total_trades = 0`, all metrics 0.0 |
| `menthorq_distance_analysis.json` | bullish n=2 (50% WR), bearish n=1 (0% WR) |

This is textbook overfitting — a 1000-combo grid search on ~15 trades, "best" params that generate zero trades, and a 100% win rate on n=2 presented as validation. **There is no credible public backtest of MenthorQ's levels.** Anyone quoting a MenthorQ hit rate to you is quoting either SpotGamma's numbers or nothing.

---

## 4. DATA REQUIREMENTS

| Metric | Required feed | Fields | Frequency | Notes for an IBKR/Polygon shop |
|---|---|---|---|---|
| Net GEX cube (foundation) | **Option chain snapshot** | strike, expiry, right, OI, gamma **or** IV, spot, r | EOD for daily; **15 min** intraday (MenthorQ's own `frequency=intraday`) | IBKR `reqSecDefOptParams` + snapshot greeks; your `fetch_option_walls.py` already does this. No tape needed. |
| **HVL / gamma flip** (cheap, cumsum) | same | net_gex by strike | 15 min | O(n), free once cube exists |
| **HVL / gamma flip** (re-priced solve) | same + **IV per contract** | σ, τ, K, OI per contract | 15–30 min (compute-bound) | Must have IV, not just gamma. HKanwal's IBKR version is your reference. |
| **Call Resistance / Put Support** | same | call_gex/put_gex by strike, spot | 15 min (recompute after any gap) | Add `OI_CUTOFF` to kill illiquid strikes |
| **Gamma Wall 0DTE** | chain **filtered to today's expiry** | strike, OI, gamma, spot | **1–5 min after 14:00 ET** | Only tickers with dailies. Your flota: QQQ SPY NVDA TSLA AMD META AMZN GOOGL MSFT AAPL SMH. Not DRAM/SPCX/SKHY. |
| **GEX 1-10** | same as foundation | abs_gex by strike | 15 min / EOD | Keep the sign of net_gex per level |
| **1D Min / 1D Max** | ATM IV **or** ATM straddle quote, front expiry | σ_atm or (call_mid+put_mid), spot | Once premarket + once at open | Straddle version needs NBBO on 2 contracts only — cheap |
| **Blind Spots BL 1-10** | Full chain **for every correlated asset** + price history for ρ/β | chains for A₁..Aₙ + 60d daily returns | EOD (levels) + rolling ρ/β weekly | The expensive one — n× the chain cost. Correlated set for semis is already in your `korea-memoria` / `flow-captains` doctrine. |
| **Dealer's Bias** | MQ level set + VIX + swing levels | levels, VIX last | 15 min | VIX delayed is fine (your `cboe-data` skill) |
| **Reversal / Wick signals** | **OHLC bars only** + level set | O,H,L,C current + prior bar | 1m / 5m / 15m | Cheapest signal in the stack. No option data at signal time. |
| **Validation / calibration** | Historical chain snapshots + intraday OHLCV | full cube history, ≥1y | daily snapshots retained | Polygon options (`polygon-options-data`) is your path; IBKR won't give you history. |

**What you do NOT need — and this is the good news:** no full tick tape, no intraday option trades with sizes/exchange, no signed trade classification, no dark-pool data. Every MenthorQ level is computable from **open-interest snapshots plus greeks**. That is categorically cheaper than SpotGamma HIRO (which needs intraday signed option trades) or your own whale-flow alarm. MenthorQ's entire moat is *packaging and distribution* (9 platform integrations), not data or math.

---

## Recommendations for ib-trader

1. **Build the cube, not the scalars.** MenthorQ's own API serves `(strike × expiration) → {net_gex, abs_gex, net_dex, abs_dex, oi_call, oi_put}`. Your `gex_core` should store that shape and derive all 19 levels as views. The IEEE result (+30.8 pp raw-chain over scalar) says the cube is where the signal lives.
2. **Fix HVL properly.** Use the re-priced Newton solve (HKanwal pattern) on your existing IBKR feed, not the cumsum shortcut, and not `maxkru92`'s volume proxy. Report *all* roots — a second flip below spot is the trapdoor.
3. **Sign-tag every wall.** `abs_gex` ranking throws away the one bit that decides pin vs trapdoor. Your `gamma-regime-walls` doctrine already depends on this.
4. **Port the Reversal rule verbatim** — `two consecutive bars straddle L` + colour flip is your PRINT-O-NADA discipline in 6 lines of code, and it needs only OHLC at signal time.
5. **Run the Blind Spot falsification experiment** (§2.8). It is the only unpublished metric, it is cloneable, and you have ground truth available for grid-search.
6. **Calibrate against a 16-random-levels null.** With ≥16 lines on the chart, raw touch rates are meaningless. Every probability you publish must beat that null, per `calibration_ledger.py`.
7. **Take nobody's word on performance.** The only MenthorQ backtests in public are n=2 and n=15. The best-documented level statistics anywhere (SpotGamma's 83%/89%) still imply forward returns of **single-digit basis points** — and the most rigorous study on the market found Sharpe decaying 1.8 → 0.1 while the structure stayed perfectly detectable.

**Local working files:** `/private/tmp/claude-502/-Users-yuniorrodriguezosorio/76ae049f-f97e-4afe-8984-bd226d4c93ba/scratchpad/` — `mq_client.py` (MenthorQ API client), `gexcalc.py` (level computation), `rx.py` (HVL/cumsum + definitions), `bias.py` + `bias.md` (Dealer's Bias), `g10.cpp` (19-subgraph map), `flip.py` (IBKR Newton flip solver), `sb.py` (DTE-bucketed features), `mk.py` (output string format), `scan.pine` (reversal rules).

Sources: [joemccann/radon MenthorQ client](https://github.com/joemccann/radon/blob/main/scripts/clients/menthorq_dashboard_client.py) · [maxkru92 gex_calculator](https://github.com/maxkru92/mk-quant-monitor-cboe-gex/blob/main/cboe_menthorq_dashboard/gex_calculator.py) · [rxsinx menthorq_gex](https://github.com/rxsinx/gex-analyzer/blob/main/modules/menthorq_gex.py) · [jackson97300 MIA_IA_system_mentor_q](https://github.com/jackson97300/MIA_IA_system_mentor_q) · [PapaPablano SwiftBolt_ML](https://github.com/PapaPablano/SwiftBolt_ML) · [arnabmitra blind-spot-calculator](https://github.com/arnabmitra/menthorq-blind-spot-calculator) · [unfool/tos-mq](https://github.com/unfool/tos-mq) · [TraderOracle/ATAS](https://github.com/TraderOracle/ATAS/blob/main/MenthorQ/MenthorQ_ATAS/MenthorQ_ATAS.cs) · [TraderOracle/TradingView](https://github.com/TraderOracle/TradingView/blob/main/MenthorQScanner.pine) · [jensolson SPX-Gamma-Exposure](https://github.com/jensolson/SPX-Gamma-Exposure/blob/master/GEX.py) · [HKanwal gamma-flip-line](https://github.com/HKanwal/gamma-flip-line) · [FlashAlpha-lab gex-explained](https://github.com/FlashAlpha-lab/gex-explained) · [Matteo-Ferrara gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker) · [VandersonTorres gamma-exposure-indicator](https://github.com/VandersonTorres/gamma-exposure-indicator) · [iAmGiG gex-llm-patterns](https://github.com/iAmGiG/gex-llm-patterns) · [arXiv 2512.17923](https://arxiv.org/pdf/2512.17923) · [Perfiliev GEX & zero gamma](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/) · [SpotGamma SPX Key Levels Statistics](https://support.spotgamma.com/hc/en-us/articles/31209900542867-SpotGamma-SPX-Key-Levels-Statistics) · [SpotGamma Call Wall](https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall-What-It-Is-and-How-SpotGamma-Uses-It) · [MenthorQ Quant Models](https://menthorq.com/guide/menthorq-quant-models/) · [MenthorQ Blind Spots](https://menthorq.com/guide/blind-spots-levels/) · [MenthorQ Gamma Levels on ES](https://menthorq.com/guide/gamma-levels-on-es/) · [Baltussen et al. JFE 2021](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365) · [Buis et al. JEDC 2024](https://pure.eur.nl/files/149733755/1-s2.0-S0165188924000721-main.pdf) · [Dim/Eraker/Vilkov 0DTE](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4692190) · [Menthor Q Levels (protected Pine)](https://www.tradingview.com/script/pmd9wFIw-Menthor-Q-Levels) · [AlgoStorm GEX-L](https://www.tradingview.com/script/njrnkKZq-AlgoStorm-Gamma-Exposure-Levels-GEX-L/) · [Trustpilot MenthorQ reviews](https://ca.trustpilot.com/review/menthorq.com)