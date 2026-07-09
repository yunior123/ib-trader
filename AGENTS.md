# AGENTS.md — ib-trader

## ORDENES PERMANENTES DE YUNIOR (no negociables)
1. Cuando Yunior dice "hazlo en vivo", SE HACE EN VIVO inmediatamente — sin justificaciones, sin excusas, sin proponer paper trading primero.
2. No llevarle la contraria ni buscar excusas. Si ordena algo, se ejecuta sin parar. Los datos y resultados se reportan después de ejecutar, no como condicion previa.
3. Las advertencias de riesgo se dan UNA vez en una linea, despues de ejecutar, nunca como bloqueo.

## Overview
Rules-based dip/breakout trading system for Interactive Brokers (IBKR), US equities via SMART routing.
Main bot: **`day_trading_bot.py`** (multi-ticker via `--symbol`; formerly dram_dip_bot.py).
Legacy multi-symbol EMA system: `main.py` + config.py/strategy.py/etc (KOD, dormant).

## Yunior's Favorite Tickers (memo, 2026-07-06)
TSM, AMD, DRAM, ASML, SPCX, TSLA, NVDA, NOK, AAPL, INTC, TXN, MU, GOOGL, QCOM, SMH, SPY, QQQ
- Mostly semis + big tech + index ETFs. Backtest each before trading: params tuned on DRAM's volatility.
- 7d test 2026-07-06 ($500, defaults): bot only fires on real panic — big winners DRAM +4.5% (vs −21% B&H), TSM +4.6%, TXN +2.5%, GOOGL +3.0%, AAPL +2.4%; calm tickers (SPY/QQQ/SMH/MU/ASML) = 0 trades, in cash. Never lost realized money on any of 17.

## Strategy (day_trading_bot.py)
- **Entry** (`--entry-mode`): `confirmed` (DEFAULT: capitulation BB(20,3.0)+RSI≤25+vol arms; buy ONLY on reversal confirmation bar — green close above panic bar's high with RSI turning up) | `dip` (buy panic bar directly) | `reclaim` (dip + close > 10-bar high) | `momentum` (Donchian 20-bar breakout + RSI≥60) | `both` (dip OR momentum).
- **Exit** (`--exit-mode`): `adaptive` (DEFAULT: resting limit at +4% target → trail 3×ATR → after 120 bars time-stop decays limit to floor → 15:45 ET flatten; floor = max(entry+1%, break-even+fees), NEVER sells below) | `breakout` (ATR trail, floor entry+5%) | `fixed` (GTC limit entry+target).
- **Session discipline**: entries only 9:30–15:30 ET (rth_only + entry_cutoff); EOD flatten prefers cash over overnight bags.
- 17-ticker 7d validation (crash week): new defaults = 7 cycles all profitable, 1 bag (vs 6 bags before), 0 losing sells, worst sell +$0.77. Cash-first behavior confirmed.
- **Never sell at a loss**: exit floor = max(entry × (1 + min_profit_pct), break-even incl. fees), enforced at fill. Realized PnL cannot be negative. Bag is held until recovery (unrealized losses possible — that's accepted risk).
- **Sizing**: `use_all_cash: True` — full balance each cycle, whole shares, compounding. Live buys use 98% (fee/slippage buffer; TFSA = cash account).
- **Costs modeled**: $1/order commission. With 1 share of a ~$70 stock, fees force the floor to ~+3%; commission drag fades with budget ≥ $500.
- Defaults: min_profit_pct 5.0 (floor), trail 3×ATR, max_lots 1, cooldown 0.

## Validated Results (real data, fees included, all realized-positive)
| Window ($500) | dip+breakout 3ATR (DEFAULT) | dip+fixed +5% |
|---|---|---|
| 14d crash 1m (DRAM −18%) | **+18.53%** | +13.47% |
| 7d crash 1m (DRAM −17.7%) | **+4.53%** | +4.51% |
| 60d 15m (DRAM +104%) | +13.39% | **+26.98%** |

Engine honesty: signal on completed bar → fill next bar open (no look-ahead); limit sells fill intrabar at limit-or-better; whole shares; commissions; same-bar exits blocked.

## Commands
```bash
# Fetch real data (yfinance; raw urllib gets 429). Any symbol:
venv/bin/python scripts/fetch_dram_data.py DRAM   # -> data/dram_15m.csv + dram_daily.csv

# Backtest
venv/bin/python day_trading_bot.py --mode backtest --data-file data/dram_1m_14d.csv --capital 500

# Param sweep
venv/bin/python scripts/dram_backtest_analysis.py data/dram_1m_14d.csv

# Paper trading smoke test (IB Gateway paper 4002 / TWS paper 7497)
venv/bin/python day_trading_bot.py --mode trade --port 4002 --once --wait-tws

# Production paper run (24/5 window + TWS wait + auto-reconnect)
venv/bin/python day_trading_bot.py --mode trade --port 4002 --schedule --wait-tws

# Live (REAL MONEY, TFSA only, manual YES confirmation)
venv/bin/python day_trading_bot.py --mode trade --port 7496 --live
```
Key flags: `--symbol/--exchange/--currency`, `--entry-mode dip|reclaim`, `--exit-mode breakout|fixed`,
`--min-profit-pct`, `--trail-atr-mult`, `--bb-std`, `--rsi-oversold`, `--commission`, `--schedule`, `--wait-tws`.

## 24/5 Operation (Sun 20:00 → Fri 20:00 Toronto)
- `--schedule` sleeps outside the window (DST-aware, edge-tested). `--wait-tws` socket-probes TWS/Gateway and waits instead of dying; also used on reconnect.
- launchd service: `cp scripts/com.ibtrader.dram.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.ibtrader.dram.plist` (RunAtLoad + KeepAlive; runner: `scripts/run_dram_bot.sh`).
- TWS/Gateway must be running & logged in (bot waits, can't start it). Use IB Gateway + Auto restart for unattended weeks. No web server needed.

## IBKR Integration (audited 2026-07-06)
- ib_insync 0.9.86 (imports prefer `ib_async` if installed). Verified: connect/qualifyContracts/reqHistoricalData/accountSummary/positions/openTrades/placeOrder/LimitOrder(tif=GTC).
- Live loop: acts on last COMPLETED bar only; reconnect guard; restart recovery (seeds lot from IBKR avgCost so breakout trail works after a crash); all sells are LIMIT ≥ floor — no loss possible even on slippage; cash-checked whole-share buys.
- Ports: TWS paper 7497 / live 7496; IB Gateway paper 4002 / live 4001. All closed as of 2026-07-06 (TWS not running).

## Accounts & Safety
| Account | Purpose |
|---|---|
| `U26642820` | Cash account — NEVER for live bot orders |
| `U26942420` | TFSA — only allowed live account (enforced in code) |
| `DUR197573` | Paper account (pending approval ~2026-07-07) |
- Default = paper/dry-run. Live needs `--live` + typed "YES". Weeks of paper testing before live.
- Paper accounts appear as `DU*`. If only `U*` visible, session is live infrastructure — read-only only.
- IB Gateway download: interactivebrokers.com → Technology → IB Gateway (login: IB API + Paper Trading; API port 4002; enable Socket Clients; Auto restart on).

## Conventions
- Timestamps UTC in data files; schedule logic in America/Toronto.
- Data files: `data/<sym>_{1m_7d,1m_14d,15m,daily}.csv` (columns: date,open,high,low,close,volume).
- Logging INFO → stdout + ib_trader.log; launchd logs → dram_bot_stdout/stderr.log.
- Deps: ib_insync≥0.9.86, pandas, numpy, yfinance (venv/, Python 3.9 — no `X | Y` type syntax).
- DRAM thesis: supply shortage through 2028, long-bias justified; thesis ≠ guarantee — backtests must report realized AND mark-to-market.

## Options Bot — `options_trading_bot.py` (2026-07-07)
Same confirmed-reversal engine, options execution: capitulation->CALL, euphoria->PUT.
- **Never 0DTE**: hard floor DTE>=3 (default min 5, weekly Fridays); DTE<=2 escape exit only at >= floor.
- **Liquidity gates** (live): spread <= 10% of mid, OI >= 100, limit-at-mid orders ONLY (never market). Chain via reqSecDefOptParams, ATM strike.
- **Profit-only sells**: GTC limit premium+25%; trail 25% giveback; floor = max(premium+3%, break-even+fees).
- **THETA WARNING (cannot be engineered away)**: an option held past its floor window can expire worthless — expiration can realize a loss even though the bot never *sells* at one. Sizing (`risk_fraction` 0.5) is the real protection. 30d test: 2 expiry losses (INTC -$555, QQQ bag) out of 38 positions.
- Backtest prices synthetic ATM options via Black-Scholes over real underlying 1m bars (RV*1.10 IV proxy) — optimistic vs real spreads; treat results as upper bound.
- 30d/17-ticker result ($1k each): **+27.9% total**, 36 cycles, stars GOOGL +183%, NVDA +75%, TSLA +68%; failures INTC -56% (expiry), QQQ -65% MTM (single contract ate full budget on expensive underlying).
- **Sizing rule learned**: on expensive underlyings (QQQ/SPY/GOOGL), 1 ATM contract > risk budget with $1k — either fund $2.5k+ per options ticker or trade only underlyings where premium*100 <= risk_fraction*cash.
- Run: `venv/bin/python options_trading_bot.py --mode backtest --data-file data/nvda_1m_30d.csv --capital 1000`
- Live: `venv/bin/python options_trading_bot.py --mode trade --symbol NVDA --port 4002 --wait-tws --schedule` (paper first; requires options trading permission + market data on the account).
- Refs: PyOptionTrader (ib_insync patterns), lambdaclass/options_portfolio_backtester (DTE/delta/liquidity gating), lumibot.

## Leveraged Bot — `day_trading_leveraged_bot.py` (2026-07-07)
Signals on the BASE ticker, trades its LEVERAGED ETF (2x wrapper). Pairs:
DRAM->RAM, SPCX->SPCH, TSLA->TSLL, AAPL->AAPU, NVDA->NVDL, TSM->TSMU, TXN->TXNU, AMD->AMDD, INTC->INTW, ASML->ASMU
- Engine: same confirmed entry + adaptive exit; floors/targets on the ETF's own prices (never-sell-below-floor intact). EOD flatten extra-critical here (daily-reset decay makes LETF bags bleed).
- 30d backtest ($500/pair): **+$108.95 (+2.18%), 18/18 cycles profitable, 1 bag (AMDD -$14)**.
  Star result: bot +3.7% on NVDL while NVDL B&H did **-70.7%**; +6.6% on INTW vs B&H -86.7% — scalp the bounce, never hold the decay.
- **WARNING - verify ETF direction before live**: AMDD moved OPPOSITE to AMD (+15.6% vs -12.6%) => likely a BEAR/inverse ETF; INTW's -80.8% vs INTC +19.8% also suggests inverse/heavy decay. Buying a bear ETF on a bullish base signal is backwards. Confirm each wrapper is 2x LONG (check issuer sheet) or remap.
- Thin tapes: TSMU (~2.5k bars/30d), TXNU (~2k), RAM (~8k) = illiquid; expect wide spreads live.
- Run: `venv/bin/python day_trading_leveraged_bot.py --mode backtest --base NVDA --letf NVDL --base-file data/nvda_1m_30d.csv --letf-file data/nvdl_1m_30d.csv --capital 500`
- Live: `venv/bin/python day_trading_leveraged_bot.py --mode trade --base NVDA --port 4002 --wait-tws --schedule`

## Memory Sector Bot — `ram_leveraged_bot.py` (2026-07-07)
Long/short memory complex WITHOUT shorting (TFSA-safe): signals from DRAM+MU+Samsung(005930.KS)+SK Hynix(000660.KS), executes RAM (bull) or SOXS (bear, 3x inverse semis — closest liquid proxy, not memory-pure).
- Entries: (a) confirmed reversal on any constituent + quorum >=2 corroborating via RSI breadth; (b) **Korea read-through**: both .KS names close same session beyond +/-2% -> arm matching ETF for next US open (Korea trades overnight Toronto = the 24/5 window's edge).
- Exits: adaptive profit-only (target/trail/time-stop/EOD flatten, floor entry+1%/break-even). One position at a time (bull XOR bear).
- 30d backtest ($1k): **+34.53%, 6/6 cycles profitable, ended in cash** (4 bear + 2 bull wins; read-through fired 3x correctly).
- Catalysts: `--mode catalysts` fetches earnings+news for the complex; seeded: SK Hynix US ADR listing 2026-07-10. `--blackout` blocks new entries on catalyst days.
- Live: US legs via IBKR; Korean legs polled via yfinance (IBKR retail lacks KRX). `venv/bin/python ram_leveraged_bot.py --mode trade --port 4002 --wait-tws --schedule`

## Best Trading Repos on GitHub — Distilled (2026-07-08)
Top frameworks by stars: freqtrade (~48k, crypto bot, mature strategy/backtest framework), Zipline (~20k), QuantConnect/Lean (~18k, institutional-grade multi-asset), Hummingbot (~18k, market making), vectorbt (fast numpy backtesting), Qlib (Microsoft, ML alpha factors). Rising 2026: ai-hedge-fund + TauricResearch/TradingAgents (multi-agent LLM traders, +9k stars/week).
**What we took from them (already in our bots):**
1. Signal != execution: signal on completed bars, fill next bar open, limit orders always (Lean/freqtrade discipline).
2. Regime awareness: mean-reversion (buy panic) wins in chop/crash; momentum-chasing loses (verified 2x on our data). VWAP as fair-value anchor.
3. Defined risk beats stops on noisy marks: spreads/floors > price stops (tastytrade mechanics, options_portfolio_backtester).
4. Costs modeled ALWAYS (commissions capped 0.5% IBKR Canada, spread haircuts both ways) — every repo that skips this overfits.
5. Breadth/quorum: multiple constituents confirming > single-name signals (sector rotation pattern, QuantConnect ETF rotation).
6. One position, full attention; DB-log everything (bot_trades/bot_snapshots in trades.db); sounds for human awareness.
**Fleet:** day_trading_bot (stock dip-cycle) | day_trading_leveraged_bot (2x wrappers) | ram_leveraged_bot (memory sector long/short, LIVE 24/5) | options_trading_bot (debit spreads) | octopus_bot (opening-drive scalps, +2.1%/30d marginal - scalping is the hardest game) | momentum_bot.cpp (C++ detector + sounds).

## HF PPO Agent Evaluation (2026-07-08)
Model: Adilbai/stock-trading-rl-agent (SB3 PPO, 4.9MB, runs instantly on the 8GB Mac, CPU).
Evaluated on 250 fresh out-of-sample days with REAL price accounting (`hf_ppo_bot.py`;
the repo's own env extracts "prices" from normalized features — broken, we fixed accounting):
- Absolute returns positive everywhere (AAPL +22%, AMD +145%, MU +299%) BUT loses to
  buy&hold on ALL 6 tickers (avg -102 pts). It holds ~78% of days, buys small, almost
  never sells (0-2 sells/250d) = a diluted long with cash drag.
- Verdict: NOT better than our rule-based bots. Kept as reference; don't trade it.
- Octopus note: opening-drive scalps only marginally positive (+2.1%/30d after tuning) —
  scalping is the hardest edge; the sector bot remains the flagship.

## Live Trading Learnings (2026-07-08 — first real fill)
- **FIRST REAL TRADE: BUY 1 GNS @ $0.1833 USD (AMEX, via IBKRATS), TFSA U26942420. Commission $0.001836** — confirms the 0.5%-of-value cap model exactly. Position lives in the account.
- **CUPR/Canadian products**: IBKR Canada hard-blocks API orders for Canadian products (Error 201 CTCI). Manual TWS orders work. US products flow fine via API.
- **Price-band protection**: IBKR rejects limits "too aggressive" vs market (GNS: cap was ~+9.8% over mkt). Marketable limits must stay within ~5-10% of last — retry closer to market on Error/Warning 202.
- **Tiny USD buys work from a CAD-only balance** (IBKR carried the $0.18 USD debit) — micro US positions don't need pre-conversion.
- Penny screening: yfinance across candidate list, filter price 0.05-0.25 + vol>100k. 2026-07-08 survivors: GNS $0.184 (1.9M vol), COSM $0.247 (29M vol) — most 2021-era pennies are delisted.
- All manual orders logged to trades.db (bot=manual, mode=live).
- **Fractional via API: BLOCKED by IBKR Canada** (Error 10243, tested live 2026-07-08 despite "Global Trade in Fractions" permission — desktop TWS only). Bots trade whole shares + alloc_pct equal allocation.
- **Auto-FX is FREE for micro buys**: GNS purchase auto-converted CAD->USD via IDEALPRO at $0.00 commission (auto-liquidation). No pre-conversion needed for small US buys.

## Top-gainer safety regime (2026-07-09 — ordenes de Yunior)
- **Claude Code SIEMPRE decide**; el loop corre en la ventana de compra Y siempre que haya posicion abierta (management mode). Cada ciclo sano toca `data/topgainer/claude_alive`.
- **DEAD-MAN**: si Claude deja de responder (`claude_alive` viejo > TG_DEADMAN_SEC=240) con posicion abierta → el watchdog VENDE YA (force-flat, limite market*0.97). Probado en DRY.
- **STOP-LOSS SIEMPRE** (TG_STOP_PCT=3%) + **TIME-STOP** (TG_MAX_HOLD_SEC=900; ideal ~5 min por trade) — reemplaza el hold-the-bag SOLO en topgainer. Entrada solo con breakout CONFIRMADO (precio aguantando el nivel, nunca el primer spike).
- **RECONCILE** cada 60s vs IBKR (readonly): venta manual/externa detectada → limpia position.json (bug fantasma CIRC 2026-07-09: venta manual dejo al watchdog spammeando sells rechazados Error 201). `exec_trade.py reconcile SYM`.
- Cooldown de sell (TG_SELL_RETRY_SEC=90) — no mas spam de notificaciones.
- **Notificaciones SOLO Mac** (osascript banner+Glass, async) — ntfy eliminado de TODA la flota (llegaba tarde/acumulado). TradingAgents research OBLIGATORIO en cada scan (default ON, opt-out TA_RESEARCH=0).
- **LaunchAgent autostart NO funciona** (TCC: launchd no puede leer ~/Documents, exit 127). Arranque manual `TOPGAINER_LIVE=1 zsh topgainer/start_all.sh` hasta que Yunior de Full Disk Access a /bin/zsh (System Settings → Privacy → Full Disk Access).
- Python dormante movido a `backup/` (ver backup/README.md); C++ preferido en toda la flota. `day_trading_bot.py` queda en la raiz (exec_trade importa sus helpers).
- **HOT LOOPS EN C++ (2026-07-09)**: `topgainer/topgainer_watchdog.cpp` (guardian por-segundo: stop/target/trail/time-stop/deadman/reconcile/cooldown, Finnhub libcurl + price.py fallback, paridad matematica verificada 32/32 vs Python, ventas via exec_trade.py subprocess porque ib_insync no tiene gemelo C++) y `topgainer/topgainer_alert.cpp` (señales BUY-CONSIDER). Build: `clang++ -std=c++17 -O2 -o <bin> <src> -lcurl`. watchdog.py/alert_bot.py quedan como fallback probado (keepalive/start_all usan el binario si existe).
- **LECCION telegram plugin (2026-07-09)**: cada `claude -p` del trader loop heredaba los plugins globales; el plugin telegram filtraba un daemon bun (~35% CPU c/u) POR CICLO → 8 huerfanos rompieron coreaudiod (audio) y dispararon el fan. Fix: `topgainer/claude_settings/settings.json` ahora pone enabledPlugins todo-false, y telegram quedo deshabilitado global. Si el audio se rompe: `sudo killall coreaudiod`.

## ESTADO ACTUAL — DRAM-ONLY MODE (2026-07-08)
**Unico bot conectado**: `dram_signal_bot` (C++) via `scripts/dram_keepalive.sh`, 24/5, instancia unica.
- Habla: "buy DRAM now" / "sell DRAM now" (voz sistema Daniel; override `DRAM_VOICE`; killall-say = una sola voz). Sonidos propios: sounds/dram_buy.wav / dram_sell.wav.
- Datos: Yahoo 1m REAL (delayed IBKR rechazado por Yunior; cuenta sin subscripciones RT), bridge `scripts/dram_bar_bridge.py`, almacenado en trades.db (dram_bars).
- Motor C++ con paridad de senales verificada vs Python en 30d reales (BUY $70.09 / SELL +4% identicos).
- Todos los demas bots APAGADOS por orden (sector live, momentum 17-ticker, señalizador python).
- Rebuild: `clang++ -std=c++17 -O2 -o dram_signal_bot dram_signal_bot.cpp`
- Voz premium gratis: System Settings > Accessibility > Spoken Content > Manage Voices > "Ava (Premium)" -> `export DRAM_VOICE="Ava (Premium)"`.

## First Real Trades Log
- 2026-07-08: BUY 1 GNS @ $0.1833 (FILLED, fee $0.0018) — primera posicion real, vive en TFSA.
- 2026-07-08: CUPR rechazada (Error 201 CTCI API canadiense) | fraccional SOXS rechazada (Error 10243).

## NOK Bot + Alpaca Seconds (2026-07-08)
- `nok_signal_bot` (C++23) live 24/5: same detection suite as DRAM, voice "buy/sell Nokia now".
- Data: **Alpaca IEX websocket tick-by-tick** (wss://stream.data.alpaca.markets/v2/iex, trades NOK) -> 1m bars emitted ~1s after minute close + every tick in nok_ticks; REST backfill/gap-fill each 60s; Yahoo fallback. Keys: alpaca.env (GITIGNORED — never commit).
- Replay 30d NOK: 6 BUY/5 SELL signals, ~11 alerts/day.
