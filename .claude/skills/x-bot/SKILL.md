---
name: x-bot
description: Post and manage the ib-trader X (Twitter) semiconductor/whale bot under a hard $5/month API budget. Use when Yunior asks to tweet, post to X, check X budget, compose a whale scan, or wire AI agents to the X API selectively (1 post/day, no URLs).
---

# x-bot — X API for ib-trader (budget-first, 2026-07-17)

**Canonical project memo:** [`docs/X-WHALE-BOT.md`](../../../docs/X-WHALE-BOT.md)  
Also: `docs/OPERATIONS.md` § X whale bot · playbook inventory · `AGENTS.md`.

**Hard budget: $5/month.** X pay-per-use (2026): ~**$0.015**/post without URL, ~**$0.20**/post with URL.
Policy baked into the bot:

| Rule | Why |
|------|-----|
| **1 post/day** max | Systematic, not spam |
| **≤30 posts/month** | $0.45/mo @ $0.015 |
| **NO URLs in posts** | Links cost ~13× more ($0.20) → $6/mo over budget |
| **Spend ledger** | `data/x_budget.txt` — blocks when cap would exceed |
| **Credentials only in `x.env`** | gitignored (`*.env`) — NEVER hardcode, NEVER commit |

## Credentials (`x.env` — local only)

```bash
# Required for most write tiers (preferred):
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...

# Optional / app-only (often 401/403 on POST /2/tweets):
X_BEARER_TOKEN=...

X_MONTHLY_BUDGET_USD=5.00
X_COST_POST_NO_URL=0.015
X_COST_POST_WITH_URL=0.20
X_MAX_POSTS_PER_DAY=1
X_MAX_POSTS_PER_MONTH=30
```

**Important:** Bearer *app-only* tokens usually **cannot** create posts. OAuth 1.0a **user** tokens (Access Token + Secret from the developer portal, with Read+Write) are required. If POST returns 401/403, fill OAuth1 keys in `x.env` and retry.

Finviz: same as fleet — `FINVIZ_AUTH3` in `feeds.env` (already gitignored).

## Binary

```bash
cd /Users/yuniorrodriguezosorio/ib-trader
OPENSSL=/opt/homebrew/opt/openssl@3
clang++ -std=c++17 -O2 -I"$OPENSSL/include" -L"$OPENSSL/lib" \
  -o x_whale_bot scripts/x_whale_bot.cpp -lcurl -lcrypto
```

## Agent / human commands (selective use)

```bash
# Safe: compose + score, $0 spend
./x_whale_bot --dry-run
./x_whale_bot --compose-only
./x_whale_bot --budget

# Live: one post (counts toward $5 ledger)
./x_whale_bot --post-now

# Force second post same day (still blocked by money/month caps)
./x_whale_bot --post-now --force

# Daemon: weekdays 09:00 America/Toronto
./x_whale_bot --daemon
# or: scripts/x_whale_bot_keepalive.sh
```

### What agents SHOULD do
1. Prefer **`--dry-run` / `--compose-only`** when drafting copy.
2. Call **`--budget`** before any live post; refuse if remaining < cost.
3. Use **`--post-now` only when Yunior explicitly asks** to post (or on the scheduled 9:00 job).
4. Never put URLs, chart links, or `t.co` in text.
5. Never print full tokens from `x.env` in chat/logs.

### What agents MUST NOT do
- Bulk post, reply storms, search, or timeline scraping (burns paid reads).
- Post more than 1/day unless Yunior says so **and** budget allows.
- Commit `x.env` or paste secrets into the repo.

## Data flow (systematic)

```
data/focus_ticker + semis universe
        │
        ▼
Finviz Elite export (live)  ──fail──►  data/finviz_<sym>.txt cache
        │
        ▼
Score: RVOL, gap, short float, |change|  (+ semis bias)
        │
        ▼
Compose ≤275 chars, NO URLs, insight line
        │
        ▼
Budget gate → POST /2/tweets → data/x_posts.jsonl + data/x_budget.txt
```

Schedule: **premarket data → post at 09:00 Toronto** (daemon morning window 09:00–09:15).

## Fleet universe (whale scan)

Focus tickers + always: NVDA AMD INTC TSM ASML MU SMH TXN AVGO QCOM SKHY DRAM SPCX NOK AAPL MSFT AMZN META GOOGL QQQ TSLA.  
Skipped as non-US/commod noise for this bot: kospi/samsung/skhynix, GLD/SLV/CPER/USO.

## Files

| Path | Role |
|------|------|
| `scripts/x_whale_bot.cpp` | Bot source |
| `x_whale_bot` | Binary (gitignored pattern via rebuild) |
| `x.env` | Secrets + budget knobs |
| `data/x_budget.txt` | `YYYY-MM posts spent_usd` |
| `data/x_posts.jsonl` | Audit log every attempt |
| `scripts/x_whale_bot_keepalive.sh` | Restart loop for daemon |
| `x_whale_bot.log` | Runtime log |

## Cost math (stay under $5 / 30 days)

- Full plan: 1 post/day × 22 trading days × $0.015 ≈ **$0.33/mo**
- Max config: 30 posts × $0.015 = **$0.45/mo**
- One post with URL: **$0.20** alone — forbidden by bot
- Headroom under $5: plenty for retries only if you keep NO-URL policy

If X pricing changes, update `X_COST_*` in `x.env` and re-check `--budget`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| HTTP 401/403 | Add OAuth1 user tokens to `x.env` (portal → Keys → Access Token Read+Write) |
| FINVIZ empty | Run `./finviz_scout --once` or check `FINVIZ_AUTH3` |
| BLOCK budget | Wait next month or lower costs (no URLs) |
| Already posted today | Wait tomorrow or `--force` (still money-capped) |

## Related skills
- `finviz-elite` — data source for short float / RVOL / gap
- `fleet-ops` — focus ticker + fleet status
