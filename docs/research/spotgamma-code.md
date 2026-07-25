# SpotGamma — Open-Source Archaeology & Reproducible Algorithm Specs

## 0. Executive finding

SpotGamma's level suite is **fully reproducible from a plain option-chain snapshot** (OI + IV/greeks per contract) — that part has been reverse-engineered dozens of times and one repo (`billyribeiro-ux/spot-gamma`) literally names its package `spotgamma` and reimplements Zero Gamma / Volatility Trigger / Call Wall / Put Wall / Absolute Gamma / Hedge Wall with docstrings citing SpotGamma. The genuinely hard product is **HIRO**, which needs the *full US option trade tape with sizes + NBBO for signed classification*; exactly one credible open replication exists (`cedricpoma/open-gamma`, HIRO engine V1→V3, in French, with a documented migration from a wrong gamma formula to the correct **delta-notional** formula and to the SPX+SPY+ES+XSP aggregation SpotGamma actually uses).

---

## 1. Catalogue of open-source / public replications

| Metric(s) replicated | Repo / URL | Lang | Quality | Data it needs |
|---|---|---|---|---|
| **Full SG level suite**: net GEX, Zero Gamma (bisection-refined), Volatility Trigger, Call/Put Wall, **Absolute Gamma**, **Hedge Wall**, 0DTE share, ThinkScript export | `billyribeiro-ux/spot-gamma` — `engine/spotgamma/{gex,levels,profile,greeks}.py` (+ `docs/METHODOLOGY.md`) | Python (+Tauri/TS dashboard) | **Faithful — best single source.** Pluggable sources, vectorized BS re-gamma at hypothetical spots, carry-adjusted | Option chain snapshot: strike, expiry, type, OI, IV (or gamma), spot, r, q, multiplier |
| **HIRO** (delta-notional CVD, Lee-Ready signing, multi-instrument SPX+SPY+ES+XSP normalization, gamma wall, CVD velocity, C/P ratio) + Zero Gamma from CBOE CSV | `cedricpoma/open-gamma` — `HIRO/hero_engine_v3.py`, `HIRO/HIRO_V3_Documentation.md`, `HIRO/HIRO_V2_Migration.md` | Python (Tastytrade DXLink stream) | **Faithful in method, rough in coverage** (±20 strikes/instrument, 30s snapshots). Docs explicitly diagnose V1's error (used gamma; must be delta) | Real-time option **trade** stream (price+size) + **NBBO quotes** + streaming greeks, per instrument; CBOE chain CSV for static GEX |
| GEX, gamma flip, call/put wall, DEX/VEX/CHEX, dealer-hedging-flow narrative | `FlashAlpha-lab/gex-explained` — `code/{compute_gex,gamma_flip_level_tracker,call_wall_put_wall_finder,delta_vanna_charm_exposure,dealer_hedging_flow_analysis}.py` | Python | Faithful (pedagogical, tested, CI) — but core numbers come from their **paid API** in some scripts | Raw chain CSV (sample included) or FlashAlpha API |
| Δ/Γ/Vanna/Charm **exposure by strike with exact closed-form greeks** (numba) | `aaguiar10/gflows` — `modules/stats.py`, `modules/calc.py` | Python (numba/Dash) | **Faithful — best greeks source.** Real dividend-adjusted formulas, FRED yield-curve term interpolation, monthly-OPEX bucketing | CBOE free `*_quotedata.csv` (15-min delayed) for SPX/NDX/RUT |
| Notional GEX by strike / expiry / 3D surface | `Matteo-Ferrara/gex-tracker` (205★) | Python | Faithful but minimal | CBOE delayed chain scrape |
| MM gamma exposure + **gamma profile & zeroGEX by interpolation** | `jensolson/SPX-Gamma-Exposure` (162★) | Python (`py_vollib`) | Faithful, the original widely-copied SPX script | CBOE CSV |
| GEX/DEX/VEX + **gamma-$ walls, cumulative-net-gamma flip**, forward-based | `pixelbrow720/flowdesk` — `services/engine/src/engine/levels.py` | Python | **Faithful + best-documented wall semantics** (explicitly rejects raw-OI walls in favour of gamma-$; deterministic tie-breaks) | Chain snapshot w/ OI + Black-76 IV-solved gammas; volume-based exposure profile for dynamic levels |
| GEX math from *prices only* (BS gamma, **IV inversion by bisection, implied forward/q from put-call parity**), flip, walls | `0xsickre/gex-gamma` — `gex_gamma/core/gex_math.py` | Python (stdlib only) | **Faithful — best "no-greeks-feed" fallback** | Chain with prices + OI, no greeks needed |
| GEX, DEX, wall strength delta-tracking, **pin probability / max pain**, unusual activity | `anuragjuneja87-bot/spotgamma-killer` — `backend/analyzers/{gex_calculator,wall_strength_tracker,pin_probability_calculator,delta_pressure}.py` | Python (ThetaData v3) | Rough/heuristic (hand-tuned thresholds, no calibration) — but the **wall-strength Δ-OI tracker and time-of-day pin factors are directly usable ideas** | 5-min chain snapshots (OI+volume) intraday, ThetaData |
| GEX + **empirical backtesting infrastructure** with side-classified trades: side-weighted GEX, GCI (HHI of gamma), PGR, GDW, CAR, vomma/zomma | `emlama/gex-backtesting` | Python/Jupyter | **Faithful + rare: pre-registered hypothesis tests, Fisher exact, FDR correction, control experiments** | **513 days** SPX 0DTE trade parquet (Polygon flat files) w/ bid/ask + side label, 400k–900k trades/day, 2.3 GB |
| Gamma/vanna/charm zones pushed onto **NinjaTrader ES/NQ** charts; CEX = 1 calendar day of decay | `OrderRejected/gamma-vanna-charm` (repo now private/404 — README indexed via search) | Python + NinjaScript | Rough (per description) | Chain snapshots + futures chart bridge |
| GEX/VEX Dash app | `Proshotv2/Gamma-Vanna-Options-Exposure` | Python/Dash | Rough | Tradier chain API |
| GEX + **auto-generates Pine Script lines for TradingView** | `VandersonTorres/gamma-exposure-indicator` | Python → Pine v5 | Rough, but the *bridge pattern* is the useful part | CBOE CSV download |
| Composite momentum from GEX + Delta Flow + Gamma Squeeze + **Vanna** + IV skew signals | `aakash-code/GammaGEX` | Python | Toy (unvalidated weights) | Chain snapshot |
| GEX dashboards, max pain, OI, IV surface, Docker | `gammagrid/gammagrid`, `zrack/gex-terminal`, `jwolberg/options-scanner` (JS) | Python / JS | Rough→faithful GEX, no SG-specific levels | Chain snapshot |
| GEX in **R** | `carlosjimenezdiaz/GEX` — `Gamma Exposure CBOE Data.R` | R | Rough | CBOE CSV |
| Crypto (BTC) dealer gamma | `schepal/crypto_gamma_exposure` | Jupyter | Research-grade | Deribit chain |
| GEX pattern research + arXiv paper | `iAmGiG/gex-llm-patterns` + [arXiv 2512.17923](https://arxiv.org/pdf/2512.17923) | Python + paper | Faithful math doc (`docs/reference/technical/gex_calculations.md`) | Chain snapshots + OHLCV |
| **TradingView Pine** — GEX/wall/flip *plotting only* | [`Gamma Exposure (GEX) Levels – JMerc567`](https://www.tradingview.com/script/BfpuBHBh-Gamma-Exposure-GEX-Levels-JMerc567/), [`AlgoStorm GEX-L`](https://www.tradingview.com/script/njrnkKZq-AlgoStorm-Gamma-Exposure-Levels-GEX-L/), [`GEX Levels [BackQuant]`](https://www.tradingview.com/script/nyyInUl8-Gamma-Exposure-Levels-BackQuant/), [`GEX Profile [PRO] TanukiTrade`](https://www.tradingview.com/script/v04Kzl4Q-GEX-Profile-PRO-Real-Auto-Updated-Gamma-Exposure-Levels/) | Pine v5/v6 | **Toy as *calculators*** — Pine cannot read option chains; all require pasted/webhooked levels. TanukiTrade pipes 15-min-delayed ORATS in | External level string, updated daily |
| SpotGamma→ATAS chart integration | `xentres86/SpotGammaATAS` | C# | Integration only, no math | SpotGamma subscription |
| Awesome-list index of everything above | `FlashAlpha-lab/awesome-options-analytics` | — | Useful map | — |

**Verdict on the wall:** nobody has open-sourced HIRO at SpotGamma's coverage (they consume the *entire* US options tape across SPX/SPY/ES/XSP and equities). Everything else is commodity math.

---

## 2. Reproducible algorithm specs

### Notation
`S` spot (or forward `F`), `K` strike, `τ` time to expiry in years, `σ` IV, `r` risk-free, `q` dividend yield, `OI` open interest, `M` contract multiplier (100 index/equity, 50 for /ES).

Carry-adjusted BS gamma (use this, not the naive one — `gflows`, `0xsickre`, `spot-gamma` all agree):

```
d1    = (ln(S/K) + (r - q + σ²/2)·τ) / (σ·√τ)
Γ     = e^(-qτ) · φ(d1) / (S · σ · √τ)          # same for calls and puts
```

---

### METRIC 1 — Net GEX (dealer dollar gamma)

**Inputs:** full chain snapshot (all expiries, all strikes): type, K, expiry, OI, IV or vendor gamma; S; r; q; M.

**Step-by-step:**
1. For each contract *i*: `Γᵢ` = vendor gamma if evaluating at snapshot spot, else recompute BS gamma.
2. `GEXᵢ = Γᵢ · OIᵢ · M · S² · 0.01` → dollars of underlying to re-hedge per **1% move**.
3. **Sign (the "naive dealer" convention SpotGamma/SqueezeMetrics use):** dealers long calls, short puts →
   `GEXᵢ = +magnitude` if call, `−magnitude` if put.
4. `NetGEX = Σᵢ GEXᵢ`. Regime = `positive` if ≥0 else `negative`.
5. Aggregate into `by_strike` (call_gex, put_gex, net_gex, total_abs_gex) and `by_expiry`.

Verbatim (`billyribeiro-ux/spot-gamma/engine/spotgamma/gex.py`):
```python
magnitude = gamma * c.open_interest * snap.multiplier * s * s * 0.01
return magnitude if c.option_type is OptionType.CALL else -magnitude
```
Verbatim (`jensolson/SPX-Gamma-Exposure`), same thing in one pandas line:
```python
df[str(F)+'_GEX'] = 10**-6*(100*F*(df['Flag']=='c')*df[str(F)+'_g']*df['Open Int']\
                           -100*F*(df['Flag']=='p')*df[str(F)+'_g']*df['Open Int'])
```

**Edge cases:** (a) zero-OI contracts → drop (they cost 100k wasted gamma evals on a 30k-contract chain); (b) missing IV **and** missing gamma → `spot-gamma` falls back to flat `IV=0.20` rather than silently zero-weighting; (c) `τ→0` on expiry day: floor τ at ~1 hour (`_MIN_TAU = 1/(365*24)` in `0xsickre`) or gamma explodes; (d) SPX vs SPXW vs XSP double-counting; (e) equity chains: divide by shares outstanding to compare across names.

**Validation:** SpotGamma/gexa publish net GEX in $Bn — reconcile your SPX number to theirs same-timestamp; sign and order of magnitude must match ($1–15 Bn/1% for SPX). Also verify `Σ|GEX|` is dominated by 0DTE+front-week on SPX (0DTE share typically 25–50%).

---

### METRIC 2 — Zero Gamma / Gamma Flip (continuous)

**Inputs:** same chain + a spot grid.

**Do NOT** just find the strike where cumulative GEX changes sign. The honest method re-prices the whole chain at hypothetical spots:

1. Build vectorized evaluator `net_at(spot)`: pre-extract arrays `K[], τ[], IV[], signed_OI[]` (signed = `+OI` calls, `−OI` puts) once; then
   `net_at(s) = (Γ_array(s, K, τ, IV, r, q) · signed_OI).sum() · M · s² · 0.01`
2. Grid: `spots = linspace(S·(1−0.15), S·(1+0.15), 121…201)`.
3. Find adjacent pairs with strict sign change; linear estimate
   `est = s0 + (s1−s0)·(−g0)/(g1−g0)`
4. **Pick the crossing nearest current spot** (there can be several).
5. Refine with **bisection on the real curve** (50 iters) — grid alone caps precision at ~0.25%.

Verbatim (`spot-gamma/profile.py`):
```python
def net_at(spot: float) -> float:
    gamma = bs_gamma_array(spot, strike, t_years, iv, rate, q)
    return float((gamma * signed_oi).sum() * mult * spot * spot * 0.01)
```

**Edge cases (all bugs seen in the wild):**
- Flat all-zero profile (empty/no-OI chain) → naive code reports *every* node as a flip. Fix: an exact-zero node counts as a crossing **only if the nearest non-zero neighbours on each side have opposite signs**.
- No crossing in ±15% → return `None` and report regime from the mid-profile sign (`Short Gamma` / `Long Gamma`), don't fabricate a level.
- **Flip instability**: `open-gamma` found the daily flip jitters violently when near-dated τ→0 dominates. Their hack: compute the profile using a **stable reference date 180 days back** so every option has τ ≥ 6 months → smooth profile, stable pivot. (Deliberately biased but stable — a real tradeoff to decide, not copy blindly.)
- `find_zero_gamma` must share the *exact same BS basis* as the profile grid, else the bisection converges to a different curve.

**Validation:** flip must sit **above spot on ~85% of days** for SPX (community backtest figure) — if yours is below spot half the time your sign convention or expiry filter is wrong. Compare to gexa.ai flip daily; ±0.3% agreement is achievable.

---

### METRIC 3 — Volatility Trigger (VT)

SpotGamma's own docs: *"the level below which bearish feedback loops are expected to start"*, *"dealers' last major level of positive gamma support"*, *"the last major support/resistance near Zero Gamma"* — i.e. **a strike-snapped, tradable version of the flip**, not the flip itself.

**Algorithm (from `spot-gamma/levels.py`, verbatim):**
```python
def _volatility_trigger(strikes, spot, zero_gamma):
    if not strikes: return None
    if zero_gamma is not None:
        return min(strikes, key=lambda s: abs(s.strike - zero_gamma)).strike
    positive = [s for s in strikes if s.net_gex > 0]
    return max(positive, key=lambda s: s.net_gex).strike if positive else None
```
1. Compute Zero Gamma (Metric 2).
2. VT = **listed strike nearest the continuous Zero Gamma**.
3. Fallback when no flip exists in range: strike with largest positive net GEX.

**Refinement worth adding (SpotGamma clearly does something like this):** restrict step 3's candidate set to strikes ≤ spot with meaningful positive net GEX and require a minimum GEX mass (e.g. ≥5% of total abs GEX) so VT lands on a *major* shelf rather than a thin strike. Also: SpotGamma's VT is a **daily, OI-based** number published pre-open — freeze it at the open and don't re-flap it intraday, or you get the crying-wolf problem.

**Regime rule:** spot > VT → dealer hedging dampens (mean-revert, sell rallies into Call Wall / buy dips); spot < VT → pro-cyclical (momentum, no fading, widen stops). This maps 1:1 onto your `gamma-regime-walls` doctrine.

**Validation:** classify each day by open vs VT; realized vol (Parkinson or 5-min RV) below-VT days should be materially higher than above-VT days. That's a two-sample test with n≈250/yr — do it before trusting the level.

---

### METRIC 4 — Call Wall / Put Wall

Two competing definitions, and the choice matters:

**(A) Net-GEX walls** (`spot-gamma`) — *keyed on net GEX so the near-ATM 0DTE spike where call and put gamma cancel doesn't masquerade as the wall*:
```python
def _call_wall(strikes, spot):
    above = [s for s in strikes if s.strike >= spot and s.net_gex > 0]
    pool  = above or [s for s in strikes if s.net_gex > 0]
    return max(pool, key=lambda s: s.net_gex).strike if pool else None
# put wall: strikes <= spot with net_gex < 0, take min(net_gex)
```

**(B) Gamma-dollar per-leg walls** (`flowdesk`, explicitly documented as superseding raw-OI):
- weight_call(K) = `call_gamma(K) · call_OI(K)`, candidates **strictly above forward**; Top-N by weight.
- weight_put(K) = `put_gamma(K) · put_OI(K)`, candidates **strictly below forward**; Top-N.
- `M·F²·0.01` is constant across strikes so it's omitted (doesn't change ranking).
- Deterministic tie-break: `(weight desc, |K − F| asc, K asc)`.
- Rationale quoted: *"a strike with huge OI but negligible gamma (deep ITM / far OTM) no longer mis-ranks as a wall."*

**Recommendation:** compute **both**, plus `Top-N` lists not just the argmax. Use forward `F = S·e^((r−q)τ)` not raw spot for the above/below split on longer-dated chains. Call Wall is SpotGamma's *upside pin / resistance*; a **sustained break above it flips dealer hedging from selling to buying** = regime change (this is exactly your "ruptura confirmada INVIERTE el nivel").

**Edge cases:** walls at the extreme end of the strike grid = artifact of chain truncation; require the wall to have neighbours on both sides. Filter expiries: a wall computed on all-expiry OI is a *weekly/monthly* wall; 0DTE-only walls are different levels — publish both.

**Validation (measurable, and directly useful to you):** for each day, log first-touch outcome at the wall (rejection vs break) and touch count. Community/vendor lore says 1st touch rejects ~70%, 3rd+ is exhausted. **Measure it per regime bucket** (spot above/below VT) — Wilson CI, like your `calibration_ledger.py` already does.

---

### METRIC 5 — Absolute Gamma & Hedge Wall

Both from `spot-gamma/levels.py`, verbatim docstrings:

```python
def _absolute_gamma(strikes):   # SpotGamma "Absolute Gamma"
    """Strike holding the most *total* option gamma (calls + puts, side-agnostic).
    The single largest gamma concentration, which tends to act as the strongest
    magnet/pin. Distinct from the walls (net gamma) because near-ATM strikes can
    stack large call *and* put gamma at once."""
    return max(strikes, key=lambda s: s.total_abs_gex).strike

def _hedge_wall(strikes):       # SpotGamma "Hedge Wall"
    """Strike with the largest *net* dealer gamma magnitude (the dominant wall) —
    the level around which dealer hedging flux is greatest."""
    return max(strikes, key=lambda s: abs(s.net_gex)).strike
```

- **Absolute Gamma** = `argmax_K Σ(|GEX_call| + |GEX_put|)` → the pin magnet. **Operational consequence you already know: monster absolute gamma at ±1 strike from spot = pin day = never buy 0DTE there.**
- **Hedge Wall** = `argmax_K |net_GEX(K)|`, either side of spot.

**Validation:** on expiry days, measure |close − AbsoluteGamma| vs |close − random nearby strike|. Ni/Pearson/Poteshman-style pinning literature says this should be significantly smaller on OPEX.

---

### METRIC 6 — HIRO (Hedging Impact Real-time Options)

**This is the only metric that needs a tape, and the only one with real moat.**

**Inputs:** live option **trade** prints (price, size, symbol, timestamp) + **NBBO quote** at trade time + streaming per-contract **delta** (and gamma for the wall), for every instrument you're aggregating; spot for each instrument.

**Step-by-step (from `cedricpoma/open-gamma/HIRO/hero_engine_v3.py`, verbatim core):**

```python
# 1. Lee-Ready trade signing against NBBO mid
trade_price = float(trade.price)
mid = (float(quote.bid_price) + float(quote.ask_price)) / 2
if   trade_price > mid: direction =  1      # customer bought (aggressive)
elif trade_price < mid: direction = -1      # customer sold
else:                                        # tick test fallback
    last = self.last_trade_prices.get(sym, 0.0)
    direction = 1 if trade_price > last else -1 if (last>0 and trade_price!=last) else None

# 2. Delta notional, normalized to SPX-equivalent
delta_notionnel = size * direction * delta * mult_norm * spot

# 3. Accumulate signed CVD (note: += for BOTH calls and puts)
if opt_type == "call": self.call_delta_cvd += delta_notionnel
else:                  self.put_delta_cvd  += delta_notionnel
```

**Critical corrections their V1→V2→V3 migration doc documents (do not repeat their mistakes):**
1. **Use delta, not gamma.** *"le delta mesure la pression de hedging immédiate… le gamma est un signal de 2e ordre. SpotGamma utilise le delta notionnel."* V1 used gamma and was wrong.
2. **Use `+=` for puts too.** Put delta is *natively negative* (−1..0), so the sign handles direction automatically: customer buys put → `dir=+1 × δ<0` → negative → downward pressure. Using `−=` (needed when weighting by always-positive gamma) double-flips and inverts your put signal.
3. **Aggregate 4 instruments, normalized to SPX-equivalent notional.** SPX alone captures only ~40–60% of the flow:

| Instrument | mult_norm | why |
|---|---|---|
| SPX | `100 × spot_spx` | reference (~50% of flow) |
| SPY | `1000 × spot_spy` | SPY = SPX/10 → ×10 (~30%) |
| XSP | `1000 × spot_xsp` | XSP = SPX/10 exactly (~5%) |
| /ES | `50 × spot_es` | ES multiplier is 50 (~15%) |

4. **Strike normalization for the gamma wall:** `strike_key = strike if instrument in ("SPX","ES") else strike * 10`; wall = `argmax_K Σ(size · |gamma|)`.
5. **Derived readouts:** `net_delta = call_cvd + put_cvd`; `cvd_velocity = net_delta(t) − net_delta(t − 5min)`; `C/P ratio = |call_cvd| / |put_cvd|`; per-instrument CVD breakdown to tell *who* is pressing (SPX neutral + SPY collapsing = retail selling).

**Edge cases:** trades at mid (~large fraction of multi-leg/auction prints) — tick-test fallback, else drop; complex/spread prints get split into legs and each leg signs independently, which mis-signs spreads (SpotGamma reportedly handles combos specially); stale quotes → skip; opening-auction prints → exclude; scale drifts with spot so thresholds must be recalibrated when index level changes (their V1 thresholds of ±5 became meaningless in $Bn units).

**Validation:** HIRO is a *flow* series, so validate as an event study: at |cvd_velocity| > threshold, measure forward index return at +1/+5/+15 min vs unconditional. Your own `whale-scalper-engine` backtest already found the fade wins at **+5 min, not +1 min** — same shape of result, and consistent with the "flow marks local extremes" reading. Bucket by regime (above/below VT) because *the same HIRO print means the opposite thing in positive vs negative gamma*.

---

### METRIC 7 — Vanna (VEX) & Charm (CEX) exposure

**Inputs:** chain + IV + r + q. **Exact closed forms, verbatim from `aaguiar10/gflows/modules/stats.py`** (these are the cleanest published versions):

```python
def calc_delta_ex(S, T, q, opt_type, OI, cdf_dp):
    delta = exp(-q*T) * cdf_dp            if call else -exp(-q*T)*(1-cdf_dp)
    return delta * OI * S                                   # DEX, per 1% move

def calc_gamma_ex(S, vol, T, q, OI, pdf_dp):
    gamma = exp(-q*T) * pdf_dp / (S * vol * sqrt(T))
    return gamma * OI * S * S                               # GEX

def calc_vanna_ex(S, vol, T, q, OI, dp, pdf_dp):
    dm = dp - vol*sqrt(T)
    vanna = -exp(-q*T) * pdf_dp * (dm / vol)
    return vanna * OI * S * vol            # Δdelta per 1% move in IV

def calc_charm_ex(S, vol, T, r, q, opt_type, OI, dp, cdf_dp, pdf_dp):
    dm = dp - vol*sqrt(T)
    if call:  charm =  q*exp(-q*T)*cdf_dp     - exp(-q*T)*pdf_dp*(2*(r-q)*T - dm*vol*sqrt(T))/(2*T*vol*sqrt(T))
    else:     charm = -q*exp(-q*T)*(1-cdf_dp) - exp(-q*T)*pdf_dp*(2*(r-q)*T - dm*vol*sqrt(T))/(2*T*vol*sqrt(T))
    return charm * OI * S * T              # Δdelta per day until expiry
```
Aggregation convention in `gflows/calc.py`: `total_vanna = (call_vanna_ex.sum() − put_vanna_ex.sum())/1e9`, same for charm — i.e. **subtract the put leg**, and bucket into `all` / `ex_next` (next expiry) / `ex_fri` (up to monthly OPEX). `dp` = `d1`, `dm` = `d2`.

**Why you care:** VEX is the *vol-crush ramp* (IV drops → dealers must buy → the melt-up); CEX is the *time-decay drift* (why pinned Fridays grind toward the Absolute Gamma strike). `gamma-vanna-charm` defines CEX as the hedge required for **one calendar day** of decay — the practical unit.

**Edge case:** `τ` appears in denominators as `2·T·vol·√T` → charm blows up at expiry. Floor τ, and never publish CEX for 0DTE after ~15:00.

---

### METRIC 8 — Max Pain & Pin Probability (SG-adjacent, cheap, useful)

From `spotgamma-killer/pin_probability_calculator.py`:
1. Aggregate `call_OI[K]`, `put_OI[K]`.
2. For each candidate `K*`: `pain(K*) = Σ_{K<K*} call_OI[K]·(K*−K)·100 + Σ_{K>K*} put_OI[K]·(K−K*)·100`.
3. **Max Pain = `argmin pain(K*)`** (minimum total seller payout).
4. Multiply a base pin score by a time-of-day factor: `morning 0.30, midday 0.50, power_hour 0.80, final_hour 0.95`.

Those factors are **hand-invented, not measured** — that's the toy part. Replace with your own measured `P(close within ½ strike | hour, regime, |spot−maxpain|)`.

Companion: `wall_strength_tracker.py` snapshots wall OI every 5 min against a persisted daily baseline and classifies **building** (+10/+20/+35%) vs **weakening/breaking** (−8/−15/−25%). Also hand-tuned, but this is precisely the missing "muros DECAEN por toques" instrumentation — same idea, measured on ΔOI instead of touch count.

---

## 3. Published empirical evidence (with numbers)

| Study | Finding | Numbers |
|---|---|---|
| **Ni, Pearson, Poteshman, White**, *Does Option Trading Have a Pervasive Impact on Underlying Stock Prices?* (RFS/SSRN 2867461; [OU PDF](https://www.ou.edu/dam/price/Finance/CFS/paper/pdf/pearsonPoteshmanWhite.pdf)) | Non-informational channel: MM hedge rebalancing moves stocks. Negative relation between stock vol and net gamma of likely delta-hedgers. | **≈12% of daily absolute returns** of optionable stocks attributable to option-MM hedge rebalancing. Statistically & economically significant. |
| **Barbon & Buraschi**, *Gamma Fragility* ([SSRN 3725454](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454)) | Intraday **momentum** when aggregate dealer gamma is negative, **reversal** when positive — and the effect is conditional on **illiquidity**. Distinct from adverse selection and funding frictions. | Effect strongest in least-liquid underlyings; large panel of index + equity options. This is the academic backbone for VT/regime switching. |
| **Baltussen, Da, Lammers, Martens**, *Hedging Demand and Market Intraday Momentum*, JFE 142 (2021) 377–403 ([PDF](https://academicweb.nd.edu/~zda/intramom.pdf)) | Last-30-min return positively predicted by rest-of-day return; mechanism = hedging short gamma; reverts over following days. | **60+ futures, 1974–2020**. Annualized **Sharpe 0.87–1.73** by asset class for the naive intraday-momentum strategy. Predictive R² of a few % (≈2.9% cited). |
| **CBOE**, *0DTE Index Options and Market Volatility: How Large is Their Impact?* ([PDF](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf)) / QuantPedia summary | 0DTE flow shifts MM hedging needs in the direction that **attenuates** SPX volatility — the opposite of the retail "0DTE breaks the market" narrative. | Measured as the fraction of SPX shares MMs must buy to hedge a −1% index move. |
| **Confirm Signal**, *Testing SqueezeMetrics GEX and DIX* ([substack](https://confirmsignal.substack.com/p/testing-squeezemetrics-gex-and-dix/comments)) | Independent Bayesian test of the six SqueezeMetrics claims. **Only the "low GEX → bullish" leg survives**; "high GEX → bearish" shows no signal; DIX effects ≈0. | Low GEX/RVOL → bullish: mean return diff **+2.1%** (CI −0.5% to +5%). Low raw GEX → bullish: **+2.1%** (CI −0.6% to +4.7%). High GEX → bearish: **no signal**. High DIX → bullish: **"probably zero"**. Author flags recency clustering. |
| **`emlama/gex-backtesting`** | Pre-registered tests of GCI (HHI of gamma by strike), PGR, GDW, CAR, charm, vomma, zomma as predictors of 0DTE put explosions and outsized late-day SPX moves, with **control experiments + FDR correction**. | **513 trading days**, 2024-01-02 → 2026-02-19, 400k–900k side-classified SPX 0DTE trades/day, 2.3 GB. Methodology is the point; results live in the notebooks. |
| **arXiv 2512.17923** (companion to `iAmGiG/gex-llm-patterns`) | Obfuscation testing of GEX-pattern detection. | Reports a **91.2% "materialization rate"** for detected dealer-hedging signals — treat with suspicion: materialization ≠ tradable edge and the definition is loose. |
| Community backtest (via FlashAlpha writeup) | Base rate that kills naive flip signals. | **Gamma flip sits above spot ~85% of days** → "price is below the flip" alone carries almost no information. Any flip signal must be conditioned on *distance* and *crossing*, not level. |

**Honest read:** the *regime* claim (negative gamma ⇒ amplification, positive ⇒ suppression) has genuine academic support with real effect sizes. The *level-precision* claims (call wall = ceiling to the strike, VT = exact trigger) have **essentially zero published validation** — that's where you must generate your own measured probabilities, exactly as your `calibration_ledger.py` doctrine demands.

---

## 4. DATA REQUIREMENTS

| Metric | Minimum feed | Fields required | Frequency | Free option? | Cost/latency notes |
|---|---|---|---|---|---|
| Net GEX, GEX by strike/expiry | **Option chain snapshot** | K, expiry, type, OI, IV *or* gamma, spot, r, q, multiplier | 1×/day pre-open is enough (OI updates overnight); 15–30 min intraday for IV-drift | ✅ CBOE delayed `_SPX.json` / `*_quotedata.csv`; IBKR TWS live | Your `opt_chain_<sym>.txt` cache already satisfies this |
| Zero Gamma / Gamma Flip | Same + **BS re-pricing** | + full IV surface per contract (needed to re-gamma at hypothetical spots) | 1×/day + refresh on ±0.5% spot moves | ✅ same | Compute cost O(contracts × grid) — vectorize or 200-point grid on 30k contracts is slow in Python |
| Volatility Trigger | Same as Zero Gamma + **listed strike grid** | + strike increments | 1×/day, **frozen at the open** | ✅ same | Freezing matters more than precision |
| Call Wall / Put Wall | Chain snapshot | K, type, OI, gamma (per-leg), forward | 1×/day; **5-min ΔOI/Δvolume snapshots if you want wall decay/build** | ✅ delayed; ⚠️ intraday OI is *not* updated intraday by most feeds — use **volume** as the intraday proxy | OI is once-daily from OCC; anyone claiming intraday OI is using volume |
| Absolute Gamma / Hedge Wall | Chain snapshot | K, type, OI, gamma | 1×/day | ✅ | Cheapest high-value level |
| DEX / VEX (vanna) / CEX (charm) | Chain snapshot | + r term structure (FRED DGS1MO…DGS10) + q | 1×/day | ✅ CBOE + FRED | `gflows` shows exact tenor interpolation |
| **HIRO / delta-notional CVD** | **Full option trade tape + NBBO + streaming greeks**, per instrument (SPX, SPY, XSP, /ES for index; per-name for equities) | trade price, **size**, timestamp, contract id; **bid & ask at trade time**; delta (and gamma); spot per instrument; ideally exchange code + condition codes to drop auctions/spreads | **Real-time tick**; snapshot/persist every 15–30 s | ❌ | This is the wall. Options: **Polygon options** (flat files for backtest, WS for live), **ThetaData**, **Tastytrade DXLink** (what `open-gamma` uses — cheapest live route, ±20 strikes practical limit), **CBOE/OPRA** direct. Backtest needs quote-matched trade side per print (`emlama` = 2.3 GB for 513 days of SPX 0DTE *alone*) |
| Signed/side-weighted GEX | Trade tape + NBBO | + `side ∈ {at_bid, below_bid, at_ask, above_ask, mid}` | Tick, aggregated daily | ❌ | Removes the "dealers long calls short puts" assumption — the single biggest accuracy upgrade over naive GEX |
| Max Pain / Pin probability | Chain snapshot (OI only) | K, type, OI | 1×/day | ✅ | No greeks needed at all |
| Wall strength (building/breaking) | Intraday chain snapshots | K, type, OI, **volume**, timestamp | **5 min** | ⚠️ needs a live chain poller | `wall_strength_tracker.py` pattern; use volume Δ not OI Δ intraday |
| Regime/level **validation & calibration** | Levels time series + **1-min underlying OHLCV** | level values per day; bars for touch/rejection/RV | 1 min bars, daily levels, ≥250 days | ✅ | The only feed you need to turn any of the above from lore into measured probability |

---

## 5. Build order recommendation (what to steal, in order)

1. **Port `billyribeiro-ux/spot-gamma`'s `gex.py` + `profile.py` + `levels.py` verbatim-equivalent into C++23** — it is the cleanest, most auditable SG-level implementation in existence, already single-pass-optimized, and it gives you Zero Gamma, VT, both Walls, Absolute Gamma, Hedge Wall and 0DTE share from the IBKR chain cache you already build. Zero new data cost.
2. **Take `gflows/modules/stats.py` greeks verbatim** for DEX/VEX/CEX (they're correct and dividend-adjusted; most repos' vanna/charm are not).
3. **Keep `0xsickre/gex-gamma`'s IV-inversion + put-call-parity forward** as the fallback path for tickers where IBKR/gexa gives no greeks (NOK, DRAM, SPCX, SKHY, EWY — exactly your illiquid-chain problem).
4. **HIRO is a separate project with a real data bill.** Prototype `open-gamma`'s V3 method on Tastytrade DXLink for QQQ/SPY/SPX only, ±20 strikes, and validate against your existing whale-flow alarm before spending on Polygon/ThetaData.
5. **Nothing goes live without a measured hit rate** per `setup_type × regime` bucket with Wilson CI — the published evidence says the *regime* is real (Barbon-Buraschi, Baltussen: Sharpe 0.87–1.73, ~12% of abs returns) while the *level precision* is unvalidated folklore, and the "flip above spot 85% of days" base rate will silently wreck any unconditional flip signal.

**Sources:** [spot-gamma engine](https://github.com/billyribeiro-ux/spot-gamma), [open-gamma HIRO](https://github.com/cedricpoma/open-gamma), [gflows](https://github.com/aaguiar10/gflows), [gex-explained](https://github.com/FlashAlpha-lab/gex-explained), [gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker), [SPX-Gamma-Exposure](https://github.com/jensolson/SPX-Gamma-Exposure), [flowdesk](https://github.com/pixelbrow720/flowdesk), [gex-gamma](https://github.com/0xsickre/gex-gamma), [spotgamma-killer](https://github.com/anuragjuneja87-bot/spotgamma-killer), [gex-backtesting](https://github.com/emlama/gex-backtesting), [gex-llm-patterns](https://github.com/iAmGiG/gex-llm-patterns), [awesome-options-analytics](https://github.com/FlashAlpha-lab/awesome-options-analytics), [VandersonTorres/gamma-exposure-indicator](https://github.com/VandersonTorres/gamma-exposure-indicator), [SpotGammaATAS](https://github.com/xentres86/SpotGammaATAS), [SpotGamma Volatility Trigger](https://support.spotgamma.com/hc/en-us/articles/15297954935699-Volatility-Trigger), [SpotGamma Zero Gamma](https://support.spotgamma.com/hc/en-us/articles/15297958613907-Zero-Gamma), [SpotGamma Call Wall](https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall-What-It-Is-and-How-SpotGamma-Uses-It), [SpotGamma HIRO](https://support.spotgamma.com/hc/en-us/articles/4420646443539-What-is-the-SpotGamma-HIRO-Indicator), [SpotGamma Implied 1-Day Move](https://support.spotgamma.com/hc/en-us/articles/15297901147923-SpotGamma-Implied-1-Day-Move), [Gamma Fragility](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454), [Hedging Demand and Market Intraday Momentum](https://academicweb.nd.edu/~zda/intramom.pdf), [Ni-Pearson-Poteshman-White](https://www.ou.edu/dam/price/Finance/CFS/paper/pdf/pearsonPoteshmanWhite.pdf), [CBOE 0DTE gamma squeezes](https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf), [Confirm Signal GEX/DIX test](https://confirmsignal.substack.com/p/testing-squeezemetrics-gex-and-dix/comments), [arXiv 2512.17923](https://arxiv.org/pdf/2512.17923), [TradingView GEX Levels JMerc567](https://www.tradingview.com/script/BfpuBHBh-Gamma-Exposure-GEX-Levels-JMerc567/), [AlgoStorm GEX-L](https://www.tradingview.com/script/njrnkKZq-AlgoStorm-Gamma-Exposure-Levels-GEX-L/), [BackQuant GEX Levels](https://www.tradingview.com/script/nyyInUl8-Gamma-Exposure-Levels-BackQuant/), [TanukiTrade GEX Profile](https://www.tradingview.com/script/v04Kzl4Q-GEX-Profile-PRO-Real-Auto-Updated-Gamma-Exposure-Levels/)