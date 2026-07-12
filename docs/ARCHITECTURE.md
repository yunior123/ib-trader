# ib-trader — Architecture

> Full system reference. For day-to-day operation see [OPERATIONS.md](OPERATIONS.md);
> for the trading rules and their evidence see [TRADING-RULES.md](TRADING-RULES.md);
> for agent-facing operational law see [../AGENTS.md](../AGENTS.md).
> Last verified against running system: 2026-07-11.

## System at a glance

```
                     ┌─────────────────────────  DATA PLANE  ─────────────────────────┐
                     │                                                                 │
 Alpaca ws (IEX) ───►│ alpaca_ws_bridge (C++ daemon, 1 shared conn)                    │
   trades/quotes/bars│   • SELF-AGG: 1m bars built from live trades, emitted at        │
                     │     minute close (event-driven on next trade, 25ms timer net)   │
 Alpaca REST ───────►│   • overnight leg: feed=overnight latest-trades poll, 1 req/5s, │
   (overnight 20-04) │     ONLY 20:00–04:00 ET (RTH is websocket-exclusive, order #5)  │
                     │   • whale prints ≥$50k → data/whale_<sym>.txt                   │
                     │   • NBBO for thin names → data/nbbo_<sym>.txt                   │
                     │        ▼ appends "EPOCH O H L C V"                              │
                     │   data/bars_<sym>.txt          data/bars_<sym>_ibkr.txt ◄────── │◄── IBKR TWS
                     │        ▼                            ▼                           │    (ibkr_bar_bridge.py
                     │   dual-source READER (C++, kqueue wakeup, ~0.3ms)               │     --daemon: SIP 5s→1m
                     │     IBKR file = priority · Alpaca = instant fallback            │     + NBBO all 16 syms,
                     │     2s shadow-hold when IBKR alive (anti volume-mixing)         │     auto-activates when
                     │        ▼ stdin pipe                                             │     data sub is bought)
                     └────────┼────────────────────────────────────────────────────────┘
                              ▼
                     ┌──────────────────────────  SIGNAL PLANE  ──────────────────────┐
                     │ 16 × <sym>_signal_bot (C++, ~1.1µs/bar compute)                 │
                     │   engine v4: confirmed capitulation long + blow-off short       │
                     │   mirror, trend mode, v3 confluence score, candle gates,        │
                     │   CUSUM terremoto (both directions, banner-grade), Supertrend   │
                     │   5m, Donchian-390. Per-ticker params via env from keepalives.  │
                     │        ▼ Mac banners + voice        ▼ append                    │
                     │      (HUMAN trades options           <sym>_operations.log       │
                     │       from these signals)                 │                     │
                     └───────────────────────────────────────────┼─────────────────────┘
                                                                 ▼ tail (offsets, EOF-start)
                     ┌──────────────────────────  EXECUTION PLANE  ───────────────────┐
                     │ fleet_executor.py (ib_insync, TWS 7496, TFSA U26942420)         │
                     │   BUY signal   → bull leveraged ETF (whole shares, slot-sized)  │
                     │   sell-higher-only → profit_floor; below = BAG (GTC recovery    │
                     │     + catastrophic stop −25%, one OCA group AT THE BROKER)      │
                     │   TERREMOTO CAIDA → quake-bear (inverse ETF, stop −3%,          │
                     │     45min time-stop, EOD 15:50 flat, never overnight)           │
                     │   account = source of truth (human co-trades same account)      │
                     │   ledger: data/etf_ledger.csv (append-only, real commissions)   │
                     └─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. `alpaca_ws_bridge.cpp` — data daemon + per-bot reader (one binary, two modes)

**Daemon mode** (`./alpaca_ws_bridge NOK SPCX … USO`, 16 symbols, one instance):
- Single Alpaca websocket (free tier = ONE connection) on `wss://stream.data.alpaca.markets/v2/iex`.
- Subscribes `bars` (official 1m, fallback) + `trades` (fleet syms + topgainer watchlist,
  ≤30 cap: quotes+trades count, bars don't) + `quotes` for thin names (NBBO spread gate).
- **SELF-AGG**: builds the 1m bar from live trades itself and emits it the moment the
  minute closes — event-driven on the first trade of the next minute (ms), 25ms flush
  timer as fallback for quiet symbols. The official `bars` channel arrives ~0.1–1s later
  and is deduped by epoch (first writer wins).
- **Overnight leg (24/5)**: Sun 20:00 → Fri 04:00 ET, one multi-symbol
  `trades/latest?feed=overnight` REST request per 5s on a dedicated dispatch queue
  (never blocks the ws queue). Bars are SAMPLED (closes exact, volume undercounted —
  fine for CUSUM). No overnight websocket exists on the free plan (404, verified).
- Whale prints (≥$50k) → `data/whale_<sym>.txt`; NBBO 1/s → `data/nbbo_<sym>.txt`.
- Watchdog: 300s of RTH silence → reconnect. Bars files truncated on daemon start.

**Reader mode** (`./alpaca_ws_bridge read SYM`, popen'd by each bot):
- One-time REST warm-up (~3 days of 1m bars, feed=iex) to prime BB/RSI/ATR.
- **Dual-source follow**: `data/bars_<sym>_ibkr.txt` (SIP, priority) and
  `data/bars_<sym>.txt` (Alpaca). kqueue EVFILT_VNODE wakeup → **~0.3ms** file→bot
  (measured; 50ms poll fallback if kqueue unavailable).
- Source discipline: an Alpaca bar emits **instantly** if IBKR has been silent >120s
  (today's default — no data sub yet); when IBKR is live, Alpaca bars hold 2s so the
  full-tape bar wins the race. Rationale: IEX volume ≈2–5% of SIP; per-minute source
  mixing would poison volMA-relative gates. Dedupe by epoch, ascending only.

### 2. `scripts/ibkr_bar_bridge.py` — IBKR fleet data daemon (Python/ib_insync)

`--daemon SYM…` (clientId 84): per symbol, `reqRealTimeBars` 5s (TRADES, useRTH=0) →
1m aggregation → append `data/bars_<sym>_ibkr.txt`; the :55 5s-bar closes the minute
(~300ms after close). SIP NBBO via `reqMktData` → `nbbo_<sym>.txt` for ALL 16 names
(no 30-symbol cap here). OVERNIGHT (IBEOS) venue subscribed best-effort.
**Entitlement prober**: subscription errors (420/10089/…) put the symbol on a 10-min
retry; when the $10 SIP bundle activates, the whole fleet upgrades itself — zero deploy.
`reqMarketDataType(1)` pinned: real-time only, delayed data forbidden (standing order #6/4).
Python is allowed here by exception: ib_insync has no C++ twin and this is I/O-bound
(5s bars), not in the tick path. Single-symbol legacy mode exists for USO history.

### 3. `<sym>_signal_bot.cpp` × 16 — the validated signal engines

All byte-clones of the master engine differing only in ticker strings; parameters come
from env (`{SYM}_*`) exported by `scripts/<sym>_keepalive.sh` (the shipped WR-70/WFO
configs — see TRADING-RULES.md). Compute cost ~1.1µs/bar.
- Long: confirmed capitulation (BB low + RSI + volume arm → green confirmation bar) or
  TREND mode (Supertrend 5m flip / day-high break + CUSUM); v3 confluence score optional.
- Short mirror (v4): blow-off arm → red confirmation; own exit envs; yields to longs.
  Signals phrased broker-generically: `BUY PUT` / `SELL PUT` (standing order #9).
- Detection layers (always on, both directions, all 16): CUSUM terremoto
  (8σ EWMA + per-ticker QUAKE_MIN floor, banner-grade, tuned 88–99% precision),
  Supertrend 5m, Donchian-390. Alert window 24/5 (Sun 20:00 → Fri 20:00 ET; USO 24/7).
- Outputs: stdout log (`t=<epoch>` on trades — the backtest parsers rely on this),
  `<sym>_operations.log` (structured `DATE | TITLE | MSG`, `WARMUP `-prefixed during
  replay), Mac banner + voice for money events (audio governor: live bars only,
  anti-burst). Virtual positions persist in `data/pos_<sym>[_s].txt`.

### 4. `scripts/fleet_executor.py` — the execution layer (money path)

Tails the 16 ops logs (persisted inode+offset, EOF-start = never replays history,
partial lines deferred to next cycle). Full rules + rationale in TRADING-RULES.md.
Key engineering properties, each adversarially reviewed (commit `1ef5021`):
- **Sells route to the position's owner venue.** IBKR position + TWS down = wait
  (broker-resident orders keep protecting); never "sold" on the paper fallback.
- **cancel_confirmed()** before any manual sell: `reqAllOpenOrders` refresh (orders
  from prior sessions), symbol match (orderIds can collide after TWS restarts), and
  confirmed cancellation — otherwise the sell is postponed. Kills the async-cancel
  double-sell/short race.
- **OCA protection pairs**: bag recovery GTC + catastrophic stop share one `ocaGroup`
  (ocaType 1) — one fills, the broker cancels the other. Placement is verified
  (`_place_checked`: silent rejections raise); a failed second leg rolls back the first.
- **Account = source of truth**: pre-buy checks broker holdings (human may have bought
  manually — adopt, never duplicate); pre-sell uses real broker qty; reconcile every
  5 min adopts positions, refreshes qty after manual partial sells, re-creates missing
  protection pairs (fresh OCA, never mixed groups), prunes only when the connection is
  >15s old (empty positions() right after connect is not "all closed"), and alarms on
  shorts in our ETFs without touching them.
- **Balance safety**: fresh NetLiq + min(AvailableFunds, SettledCash) before every
  buy (cash-account settlement respected), $25 reserve, slot = NetLiq/4, whole
  shares, BATCH_SPENT discounts same-cycle purchases, buy wait 90s. Fees:
  `profit_floor` = entry + max(1%, real IBKR round trip [min $0.35/side, 0.5% cap]
  + 0.2%), `cent_ceil` on every sell limit.
- **Circuit breakers** (pro-desk audit 2026-07-11): daily halt (realized day loss
  ≥5% NetLiq → no new buys until next session; exits stay live), sector cap (max 2
  active positions per bucket tech/commod; ≥2 open bags in a bucket also block —
  never average into a dying regime), gross leverage cap (Σ leverage×notional ≤
  1.5× NetLiq). Stops are leverage-normalized per ETF (`lev` in the map): quake-bear
  stop = lev×1.5% (TSLS 1.5% / GLL 3% / SQQQ 4.5% — constant underlying risk),
  bull disaster stop scales from 25%@2x (TQQQ 35%). Stop trigger method = double-last
  (thin-ETF odd prints don't trigger).
- Activation: `data/etf_armed` exists AND NetLiq ≥ $500 → trades; kill switch =
  `rm data/etf_armed` (instant dry-run). Ledger: `data/etf_ledger.csv`.
- `--selftest`: parser, map invariants, floor math.

### 5. Supervision & autostart

- Each bot: `scripts/<sym>_keepalive.sh` (env config + restart loop). Executor:
  `scripts/executor_keepalive.sh`. IBKR daemon + ws daemon: pgrep-guarded launches in
  `scripts/fleet_keepalive_start.sh` and `topgainer/ensure_all.sh` / `start_all.sh`.
- LaunchAgents (`com.ibtrader.fleet` every 5 min, `com.ibtrader.topgainer` every 120s)
  re-run the guards — **currently broken by macOS TCC (exit 78)**; see OPERATIONS.md.

## File contracts (the glue)

| File | Writer | Reader | Format |
|---|---|---|---|
| `data/bars_<sym>.txt` | ws daemon | dual reader | `EPOCH O H L C V` per line, truncated on daemon start |
| `data/bars_<sym>_ibkr.txt` | ibkr daemon | dual reader | same; append-only (~30KB/day/sym) |
| `data/nbbo_<sym>.txt` | either daemon | bots (spread gate) | `EPOCH BID ASK`, fresh ≤10s |
| `data/whale_<sym>.txt` | ws daemon | bots (v3 score) | `EPOCH PRICE USD DIR`, daily reset |
| `data/pos_<sym>[_s].txt` | bots | bots (restart) | virtual position persistence |
| `<sym>_operations.log` | bots | executor + humans | `DATE \| TITLE \| MSG`; `WARMUP ` prefix = never trade |
| `data/etf_positions.json` | executor | executor | positions + log offsets + history cache (gitignored) |
| `data/etf_ledger.csv` | executor | humans/audits | append-only full trade history (incl. pnl_usd) |
| `trades.db` → `etf_operations`, `etf_signals` | executor | scorecards/audits/daily-halt | SQLite WAL: every parsed signal + every operation with real commissions and realized PnL (feeds the daily-loss circuit breaker); DB failure never blocks trading (CSV remains) |
| `data/leveraged_map.json` | verified 2026-07-11 | executor | base → {bull, bear} ETF map |
| `data/etf_armed` | operator | executor | existence = armed; `rm` = kill switch |

## Measured performance (2026-07-11, re-verified same day)

| Leg | Latency |
|---|---|
| Bar file write → bot stdin (kqueue reader) | 0.28–0.33ms avg, p95 <0.7ms |
| Bot compute per 1m bar | ~1.1µs |
| Minute close → bar written (Alpaca self-agg, liquid syms) | ms (first next-minute trade) |
| Minute close → bar written (IBKR 5s bars, when entitled) | ~300ms–1s |
| Feed transport (Alpaca ws, measured on crypto) | ~0–30ms |

Build: `clang++ -std=c++17 -O2 -o alpaca_ws_bridge alpaca_ws_bridge.cpp -lcurl -framework Network`;
bots: `clang++ -std=c++17 -O2 -o <sym>_signal_bot <sym>_signal_bot.cpp`.
