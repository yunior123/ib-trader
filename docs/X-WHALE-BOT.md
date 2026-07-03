# X Whale Bot — project memo / playbook (2026-07-17)

> Permanent ops memo for the daily semiconductor / whale scan poster on X.
> Signal-only (ley #0): no broker orders. C++ only (ley #4). Budget-first.

**Skill for agents:** `.claude/skills/x-bot/SKILL.md`  
**Also indexed in:** [AGENTS.md](../AGENTS.md), [OPERATIONS.md](OPERATIONS.md)

---

## Purpose

Post **once per trading day** (target **09:00 America/Toronto**) a short, systematic
scan of the **ib-trader fleet** focused on semiconductors and “whale” proxies from
**Finviz Elite** (rel volume, gap, short float, change). Optional backup: cached
`data/finviz_<sym>.txt` when live Finviz fails (same files `finviz_scout` writes).

Not a news spam bot. Not a chat bot. **One deliberate post / day.**

---

## Budget law (hard — do not violate)

X API pay-per-use (2026 reference prices used in the ledger):

| Action | Approx cost | Policy |
|--------|-------------|--------|
| Create post **without** URL | **$0.015** | Allowed |
| Create post **with** URL / link | **$0.20** | **FORBIDDEN** in bot |
| Multiple `$TICKER` cashtags | 403 | **Max ONE cashtag** per post (free/PPU rule, verified 2026-07-17) |
| Timeline / search / bulk reads | $0.001–$0.005+ | **Do not use** from this bot |

**Monthly hard cap: $5.00** (`X_MONTHLY_BUDGET_USD` in `x.env`).

| Plan | Math |
|------|------|
| Full trading-month utilization | 1 × 22 days × $0.015 ≈ **$0.33/mo** |
| Absolute max posts | 30 × $0.015 = **$0.45/mo** |
| Headroom under $5 | Large — **only if posts stay link-free** |

Ledger: `data/x_budget.txt` → `YYYY-MM posts_count estimated_usd`  
Audit: `data/x_posts.jsonl` (every dry / live / fail attempt)  
Daily quota counts **only** successful `"mode":"live"` posts.

---

## Auth (critical lesson 2026-07-17)

| Token type | Can POST `/2/tweets`? |
|------------|------------------------|
| Bearer **app-only** | **NO** → HTTP 403 *Unsupported Authentication* |
| OAuth **1.0a user** (API key+secret + access token+secret, Read+Write) | **YES** (preferred) |
| OAuth **2.0 user** context | YES (not implemented in bot yet; OAuth1 is enough) |

**Live test 2026-07-17:** dry-run OK (Finviz 21 rows). `--post-now` with Bearer only → **403**.
**$0 charged.** Fix: put user OAuth1 keys in `x.env`.

### Secrets location (NEVER commit)

```
x.env          # X credentials + budget knobs  (gitignored via *.env)
feeds.env      # FINVIZ_AUTH3 for live export   (gitignored)
```

Required for live posts:

```bash
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...
# optional:
X_BEARER_TOKEN=...
X_MONTHLY_BUDGET_USD=5.00
X_COST_POST_NO_URL=0.015
X_COST_POST_WITH_URL=0.20
X_MAX_POSTS_PER_DAY=1
X_MAX_POSTS_PER_MONTH=30
```

Rotate any token that was pasted into chat.

---

## Data flow (Claude-way Finviz — upgraded 2026-07-17)

```
data/focus_ticker + semis universe
        │
        ▼
IF ≥ half of data/finviz_<sym>.txt age < 30m  ──►  CACHE (scout already paid rate limit)
        │ else
        ▼
Finviz Elite live /export/screener v=152 (FINVIZ_AUTH3)
  cols: scout base + InstOwn/InstTrans + AH Close/Change
  parse by HEADER NAMES (not blind indices)
        │ fail
        ▼
cold cache fallback
        │
        ▼
Score SESSION-AWARE:
  premarket/AH: boost gap + short + AH change; mute overnight RVOL noise
  RTH: full RVOL weight + same whale cols
        │
        ▼
Compose ≤275 chars, NO URLs, MAX ONE $cashtag, insight on lead
        │
        ▼
Budget gate → POST api.x.com/2/tweets → ledger + jsonl
```

**Was Finviz used properly on first post?** Yes on transport (Elite export URL, AUTH3, v=152, header parse, 21 rows). Not yet maximal on *strategy*: double-fetched live while scout exists; premarket RVOL 0.1x over-weighted. Fixed: cache-first + session-aware score + inst/AH columns.

### Universe

Focus file tickers (US) **plus always:**  
NVDA AMD INTC TSM ASML MU SMH TXN AVGO QCOM SKHY DRAM SPCX NOK AAPL MSFT AMZN META GOOGL QQQ TSLA  

**Skipped** for this bot: kospi/samsung/skhynix, GLD/SLV/CPER/USO (commod noise).

### Score intuition (whale proxy)

- High **relative volume** (esp. ≥2–3×) → institutional / crowded flow
- Large **gap** → premarket interest
- Elevated **short float** → squeeze fuel / trap risk
- Large **day change** → attention
- Slight boost for core semis names

---

## Build & commands

```bash
cd ~/Documents/GitHub/ib-trader
OPENSSL=/opt/homebrew/opt/openssl@3
clang++ -std=c++17 -O2 -I"$OPENSSL/include" -L"$OPENSSL/lib" \
  -o x_whale_bot scripts/x_whale_bot.cpp -lcurl -lcrypto

bin/x_whale_bot --budget              # month spend remaining
bin/x_whale_bot --dry-run             # compose only, $0
bin/x_whale_bot --compose-only        # same spirit
bin/x_whale_bot --post-now            # 1 live post if gates pass
bin/x_whale_bot --post-now --force    # allow 2nd same day; still money-capped
bin/x_whale_bot --daemon              # weekdays 09:00–09:15 Toronto window
zsh scripts/x_whale_bot_keepalive.sh
```

### Agent rules (systematicity)

1. Prefer `--dry-run` / `--budget` unless Yunior explicitly wants a live post.
2. Never invent URLs or chart links in the text.
3. Never print secrets from `x.env` / `feeds.env`.
4. Do not scrape timelines or burn paid reads for this workflow.

---

## Schedule

| When | What |
|------|------|
| Premarket | `finviz_scout` keeps `data/finviz_*.txt` warm (60s cycle) |
| **09:00 America/Toronto** | `x_whale_bot --daemon` morning window posts **once** (weekdays) |
| Weekend | Daemon sleeps; no post |

Keepalive respects `data/fleet_sleep` (exits clean if sleep file present).

---

## Files map

| Path | Role |
|------|------|
| `scripts/x_whale_bot.cpp` | Source |
| `x_whale_bot` | Binary (gitignored) |
| `scripts/x_whale_bot_keepalive.sh` | Restart daemon |
| `x.env` | Secrets + budget knobs |
| `data/x_budget.txt` | Monthly spend ledger |
| `data/x_posts.jsonl` | Post audit log |
| `x_whale_bot.log` | Daemon stdout |
| `.claude/skills/x-bot/SKILL.md` | Agent skill |

Related: `scripts/finviz_scout.cpp`, `.claude/skills/finviz-elite/SKILL.md`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| HTTP 401/403 | Add OAuth1 **user** Read+Write tokens to `x.env` |
| FINVIZ empty / ROTO | `bin/finviz_scout --once`; check `FINVIZ_AUTH3` |
| BLOCK budget | Wait next calendar month or stop posting |
| Already posted today | Wait next day or `--force` (still capped by $ and max/month) |
| Compile missing openssl | `-I/opt/homebrew/opt/openssl@3/include -L.../lib` |
| Secrets in git | Must not happen — `*.env` gitignored; never force-add |

---

## Example composed post (dry-run 2026-07-17)

```
SEMICON WHALE SCAN 07-17 (Toronto premarket)
1) $SPCX … gap … short …
2) $DRAM …
3) $AMD …
Insight: gap on $SPCX. Map OR then trade resolution, not the gap itself.
#semiconductors #NVDA #stocks
```

Tone: fleet scan + one insight. No hype, no links, no broker advice framing beyond public tape stats.

**First live post (2026-07-17):** id `2078031728216625396`  
https://x.com/YuniorR62327146/status/2078031728216625396  
($0.015 charged; OAuth1 Read+Write; single cashtag `$SPCX` only.)

---

## Change control

- Cost constants live in `x.env` so pricing changes do not require a rebuild.
- Any raise of `X_MAX_POSTS_PER_DAY` or allowing URLs needs explicit owner OK (budget risk).
- This memo supersedes chat history for “how X posting works in ib-trader.”
