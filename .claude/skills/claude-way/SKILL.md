---
name: claude-way
description: Operating doctrine for Yunior's ib-trader and all AI agents — signal-only safety, fail-loud, empirical probes, C++ fleet paths, budget honesty, durable docs, Desktop HUD. Use at session start, on emergencies (bots selling), signal redesigns, Finviz/X ops, or when user says "Claude way", "smart as shit", "ultracode", "no excuses".
---

# Claude Way — load this first

**Obsidian brain (full prose):**  
`~/Documents/Obsidian Vault/AI Brain/The Claude Way.md`

**Always:** read that note OR this skill before multi-step fleet work. Then act.

## Priority stack

1. **Danger** — anything that can trade/sell → kill broker orders + quarantine code  
2. **Truth** — probe TWS / bars / Finviz / X with real calls  
3. **Fix** — permanent (code + docs + memory), not a chat promise  
4. **Polish** — only after 1–3  

## 12 laws (compressed)

| # | Law |
|---|-----|
| 0 | **Signal-only** until Yunior re-arms. Cancel *server-side* GTCs too. |
| 1 | Live = execute now; risk = one line after. |
| 2 | Fail **LOUD**. No Yahoo/delayed silent fallback. |
| 3 | Empirical: ports, HTTP codes, bar ages, PIDs. |
| 4 | Root cause (broker OCA, not just local pkill). |
| 5 | C++ for fleet money-path; Python only if forced. |
| 6 | Budget honesty (X $5, no URLs, 1 cashtag; no NATS until multi-host). |
| 7 | Write law to AGENTS.md + memory + docs + skills. |
| 8 | Desktop = human HUD (signals + price-alerts sirens). |
| 9 | Signals = `BUY`/`SELL` + `prob NN%` only. |
| 10 | Multi-TF (1m+15m BB, MACD context/trigger, retest-confirm). |
| 11 | Prefer existing data plane (`data/finviz_*.txt`) before new HTTP. |
| 12 | Test the path that hurts (afterhours, near-threshold alarms, real 201). |

## Emergency: “bots sold my shares”

```bash
# 1) Broker truth
./venv/bin/python scripts/cancel_all_bot_orders.py   # or equivalent IBKR open-order cancel
# 2) Kill local execution
pkill -f fleet_executor; pkill -f screener_watchdog; pkill -f exec_trade
# 3) Quarantine + flags
# move executors → backup/execution_retired_YYYY-MM-DD/
rm -f data/etf_armed; touch data/screener/signal_only
# 4) VERIFY open orders == 0 on TWS 7496
# 5) Document AGENTS.md ley #0 + memory
```

## Finviz the smart way

See skill `finviz-elite` + Obsidian `ib-trader/Finviz Elite.md`.

- URL `/export/screener` + `FINVIZ_AUTH3`
- One `t=` batch, ≥60s spacing
- **Cache-first** if `data/finviz_<sym>.txt` fresh
- Header-name parse; whale cols: short, RVOL, gap, inst, AH

## X the smart way

See skill `x-bot` + `docs/X-WHALE-BOT.md`.

- OAuth1 **Read and Write** access token (not Bearer-only, not Read-only)
- 1 post/day, no URLs, **one** `$cashtag`, cap $5/mo
- First live proof: https://x.com/YuniorR62327146/status/2078031728216625396

## Response template

```
## Now
- [danger action done] evidence…
- [probe] numbers…

## Blocked / next
- one human action if needed
```

No long preambles. Match ES/EN. Recap next step for Yunior in one line.

## Related skills

`fleet-ops` · `finviz-elite` · `x-bot` · `bollinger-mastery` · `liquidity-trading` · `trendline-trading`
