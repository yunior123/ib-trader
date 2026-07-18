# ib-trader — Trading Rules (the law) and their evidence

> Every rule below is an explicit owner order (Yunior, dates cited) or a
> data-driven decision under his standing orders. Any future operator/model:
> these are not suggestions. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md).

## Standing orders (non-negotiable, see AGENTS.md + memory for full text)

1. Live means live — execute immediately, risk warnings ONE line after, never a blocker.
2. **Real-time data only.** Yahoo and delayed feeds forbidden on every signal path.
   If the real-time source dies, fail LOUD with nothing — never degrade silently.
3. **Websockets are the priority** (reaffirmed 2026-07-11): RTH 9:30–16:00 market data
   flows only via ws; REST solely where no ws exists (overnight feed, one-time warm-up).
4. **WR ≥ 70% + positive out-of-sample walk-forward or the strategy ships OFF.**
5. **Detection covers BOTH directions on ALL tickers** (terremoto banners), regardless
   of whether a tradeable strategy validated. Positions stay validated-only.
6. **Signals are broker-generic** for the human: UP = `BUY NOW` (shares or CALL),
   DOWN = `BUY PUT`. Never phrased as short-selling (TFSA-safe).
7. C++ for fleet code (money at stake); Python only where a library demands it.

## The double-purpose design (order 2026-07-11)

- **Signals always on** → the HUMAN trades options (calls on BUY NOW, puts on BUY PUT)
  and sometimes shares, from Mac banners/voice.
- **The executor trades leveraged ETFs** on the same signals, autonomously, on the
  IBKR TFSA — "we don't operate on the ticker itself but on the leveraged ETF".

## Leveraged-ETF execution rules

### The map (live-verified on Alpaca's 14k asset list + IBKR contract qualification)

| Base | Bull (2x unless noted) | Bear | Base | Bull | Bear |
|---|---|---|---|---|---|
| TSLA | TSLL (Direxion) | TSLS (1x) | QQQ | TQQQ (3x) | SQQQ (3x) |
| AAPL | AAPU (Direxion) | AAPD (1x) | GLD | UGL | GLL |
| TSM | TSMU (GraniteShares) | TSMZ (1x) | SLV | AGQ | ZSL |
| NVDA | NVDL (GraniteShares) | NVDD (1x) | USO | UCO | SCO |
| AMD | AMDL (GraniteShares) | AMDD (1x) | CPER | CPXR | — |
| INTC | INTW (GraniteShares) | — | NOK | LNOK | — |
| ASML | ASMU (Direxion) | — | SPCX | LOFF (Direxion) | SNK |
| TXN | TXNU (Direxion) | — | DRAM | RAM (T-REX) | — |

AMUU ($263) and LINT ($154) were rejected: they don't fit a $500-account slot.
No bear ETF exists for INTC/ASML/TXN/NOK/DRAM/CPER — their put signals stay human-only.

### Bulls — "we buy and sell higher only, if not we keep the bag"

- BUY signal → buy the bull ETF. Slot = NetLiq/4, whole shares, $25 cash reserve
  untouchable, fresh balance check before EVERY order, 15-min cooldown per ETF,
  no re-entry while a position/bag is open, max 4 active positions.
- Sell ONLY at ≥ `profit_floor` = entry + max(1%, round-trip minimum fees + 0.2%) —
  small positions automatically demand more; every sell limit is ceiling-rounded.
  **A sell below net-fees profit is impossible by construction.**
- Sell signal below the floor → **the bag**: hold, with a GTC recovery limit at the
  floor AND a catastrophic stop at **−25%** (order 2026-07-11 "stop loss should be on
  price as well") — both resident at IBKR in one OCA group (one fills → broker cancels
  the other; survives any local failure). −25% on a 2x ETF ≈ −12% underlying: normal
  bags live (backtest: bags averaged −20%, 86% recovered, longest 26 days), a
  single-name collapse cannot destroy the account.
- Owner explicitly accepts bag risk on these tickers ("my favorites", 2026-07-11).

### Bears — "never hold the bag of falling; only when sure and real fast, when earthquake"

- Regular PUT-signal bears: **DISABLED** (`ETF_BEARS=0`). Evidence: 90d translation
  backtest = 252 trades, **37% WR, −84%** (flat stop 2–5× wider than the bots' tuned
  stops + fee drag kills the small short edge). Standing order #4 applies. A one-line
  flag re-enables after a per-ticker stop retune.
- **Quake-bears: ENABLED.** Trigger = TERREMOTO CAIDA banner only (CUSUM structural
  break, per-ticker thresholds tuned to 88–99% precision, ≤10 alerts/week). Guards:
  server-side stop −3% placed on fill (position closed instantly if the stop can't be
  placed), 45-min time-stop, forced flat 15:50 ET, no entries after 15:20, max age 8h
  (safety net), instant exit on TERREMOTO ALZA reversal, max 2 concurrent, blocked when
  a bull/bag exists on the same underlying. **An inverse leveraged ETF never sleeps
  overnight** (daily-reset decay + gap risk).

### Account safety (order 2026-07-11 "be careful with account… account is source of truth")

- The human trades the same TFSA manually. Therefore: pre-buy the broker is checked
  (existing holding → adopt, never duplicate); pre-sell the REAL broker quantity is
  used; positions closed manually are detected and state-cleaned; reconcile every
  5 min re-creates any missing protection; shorts in fleet ETFs raise an alarm and are
  never touched (they may be intentional and human).
- Activation gate: `data/etf_armed` present AND NetLiq ≥ **USD 500**. Kill switch:
  `rm data/etf_armed`. Verified live: injected signals were correctly refused with
  "equity < 500 — esperar fondeo" before funding.
- Every operation lands in `data/etf_ledger.csv` (timestamps, qty, price, REAL
  commissions from fills, PnL, reason) — full history, append-only.

## Risk architecture (pro-desk audit, 2026-07-11 — two independent fresh agents)

An IBKR-API audit (every assumption verified against official TWS/ib_insync docs)
and a pro-trader audit (with the project's trading skills as reference) ran before
this documentation shipped. Confirmed: OCA one-cancels-other is server-side with
overfill protection; IBKR rejects over-budget cash-account buys upfront; TFSAs
cannot short; DAY orders queue after-hours (hence the RTH gate on all sells);
stops trigger RTH-only by default (overnight gaps fill at the open — bears are
flat by 15:50 precisely for this). Their findings produced:
- **Daily-loss halt**: realized day PnL ≤ −5% NetLiq → no new buys until tomorrow.
- **Sector cap**: max 2 active positions per bucket (tech = the 12 semis/megacaps,
  commod = GLD/SLV/USO/CPER); ≥2 open bags in a bucket also block new buys there.
  Rationale: 11 of 16 underlyings are one correlated tech bet — the capitulation
  engines would otherwise buy four leveraged semis into the same panic.
- **Gross leverage cap**: Σ(ETF leverage × notional) ≤ 1.5× NetLiq.
- **Leverage-normalized stops**: constant underlying risk (quake-bears lev×1.5%;
  bull disaster stop scales 25%@2x → 35%@3x). Flat stops were the documented cause
  of the failed regular-bear backtest.
- **Real fee model**: IBKR min ~$0.35/side with a 0.5% cap — the previous $1-flat
  model doubled the profit floor on small positions and held bags days longer.
- **Settlement**: buy budget = min(AvailableFunds, SettledCash) − reserve
  (cash-account free-riding protection).
- Known accepted risks (owner-informed): 2x daily-reset drag means a bag's recovery
  target recedes ~2.5–3.5%/month on volatile names (the GTC floor may need a new
  underlying high, not just a round trip); CRA can recharacterize high-frequency
  TFSA trading as business income at scale — visible in the ledger's round-trip
  counts; quake-bears depend on the 15:50 flatten window (belt: server stop + 8h
  max-age + next-open retry).

## Evidence trail

| Claim | Evidence |
|---|---|
| Signal engines validated | Full-2026 + 90d WFO backtests per ticker in keepalive comments, `data/fleet_bt_*`, `data/fleet_wfo_ship.txt` |
| Terremoto precision 88–99% | Tuned on 2026 data, metric = no >50% retrace in 30min (commit a1253ab); USO/SLV/CPER calibrated with GLD control reproducing 95% |
| ETF translation economics | `data/leveraged_bt_90d.txt` (bulls +632.9% closed / 32 open bags −654% MTM / 86% bag recovery; bears 37% WR → disabled) |
| Pipeline ~1ms | Measured 0.28–0.33ms file→bot + 1.1µs compute (2026-07-11, twice) |
| Executor correctness | Selftest + live injection tests + adversarial review with 17 findings fixed (commit 1ef5021) |

## Change control

Any parameter change to a shipped strategy: replay 90d → train/OOS 60/40 → WR ≥ 70 +
positive OOS or it does not ship. Any executor logic change: `--selftest` + the
adversarial checklist in memory (`leveraged-etf-execution.md` — "do NOT reintroduce").

## Options-flow law (order 2026-07-17)
Evidence: OPEX 2026-07-17 — +117k fresh NVDA calls 205-210 in 38 min pushed price to 204.8, then
pullback to 203.1 before continuation. Pattern confirmed live by Yunior's flow alerts.
1. High call-flow spike = local top risk, NOT an immediate-buy signal (late retail + short-gamma
   dealers selling the underlying as they hedge). Entry is the pullback after the spike.
2. Massive-OI call strike = magnet AND ceiling on first touch; massive-OI put strike = probable floor.
3. Extreme one-sided intraday flow (especially OPEX) = short-term reversion/pin risk; flow confirms
   medium-term direction only.
4. Every directional signal must cite current flow and adjust its `prob NN%` accordingly.
   Source: scripts/fetch_option_walls.py (TWS 7496, OI+volume delta between reads).
