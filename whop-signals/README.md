# La Manada — Whop-ready product preview

An original educational market-structure product kit built around the measured data
already exposed by `ib-trader`. It borrows the broad membership pattern common to trading
communities—member dashboard, recurring market context, and education—but does not copy
another creator's assets, wording, branding, curriculum, or proprietary experience.

This directory is an internal preview. It does not create a Whop product, configure a
checkout, charge users, authenticate members, deploy code, publish posts, or execute trades.

## What is included

| Path | Purpose |
|---|---|
| `gameplan.py` | Builds versioned JSON and Markdown snapshots from live endpoints or offline fixtures |
| `app/index.html` | Responsive member dashboard that reads `output/latest.json` |
| `app/dashboard.js` | Same-origin snapshot loader and safe DOM renderer |
| `landing.html` | Honest sales-page preview with release boundaries and no checkout |
| `fixtures/` | Deterministic fresh, stale, missing, and crossed-wall examples |
| `tests/` | Generator, data-contract, CLI, disclosure, HTML, and JavaScript checks |

## Data contract and product boundaries

The generator consumes:

- `/api/niveles`: structural fields such as spot, put/call wall, flip, expected move,
  house-scale net GEX, and source timestamp.
- `/api/flujo`: observed options-contract activity with a source timestamp.
- Optional local `compass_*.json`, `consensus_signals.jsonl`, and `breadth.json` context.

It then applies these rules:

- Levels are **structural context**, not an execution trigger.
- Options activity is never called bullish or bearish because call/put type does not reveal
  aggressor side.
- `null` stays `null`; absent evidence is never converted into zero.
- Stale rows remain visible and labeled. Invalid future timestamps are also flagged.
- Crossed walls (`put_wall > call_wall`) and side-semantic violations
  (`put_wall > spot` or `call_wall < spot`) are flagged rather than silently repaired.
- Compass probability is only carried when its source declares measured/calibrated evidence.
- Counts and descriptive breadth scores are not presented as win rates or forecasts.

Naive `/api/niveles` source timestamps are interpreted in `America/New_York`; naive
`/api/flujo` timestamps are interpreted as `UTC`, matching the measured endpoint contract on
2026-08-27. Both are overrideable with `--levels-source-timezone` and
`--flow-source-timezone`.

The default freshness thresholds are explicit conventions for the preview, not latency claims:
30 minutes for levels, 5 minutes for flow, and 10 minutes for context. Override them on the CLI
when the production data contract establishes different service-level expectations.

## Run completely offline

```bash
cd /Users/yuniorrodriguezosorio/ib-trader/whop-signals
python3 gameplan.py \
  --offline \
  --levels-file fixtures/levels.json \
  --flow-file fixtures/flow.json \
  --compass-dir fixtures/compass \
  --consensus-file fixtures/consensus.jsonl \
  --breadth-file fixtures/breadth.json \
  --now 2026-08-27T16:30:00Z \
  --date 2026-08-27
```

This writes:

- `output/gameplan-2026-08-27.json`
- `output/gameplan-2026-08-27.md`
- `output/latest.json` for the dashboard

To fetch the existing worker endpoints instead, omit `--offline`, `--levels-file`, and
`--flow-file`. A network/source error fails visibly; there is no silent fallback.

Use `--strict` when a release job should fail if it receives zero fresh level rows.

## Review the web preview

Browsers block local `fetch()` from `file://`, so serve the folder locally:

```bash
cd /Users/yuniorrodriguezosorio/ib-trader/whop-signals
python3 -m http.server 8765
```

Then visit:

- Sales preview: `http://127.0.0.1:8765/landing.html`
- Member desk: `http://127.0.0.1:8765/app/`

The dashboard only accepts same-origin snapshot URLs. For local QA, a different same-origin
snapshot can be selected with `?data=../output/gameplan-2026-08-27.json`.

## Validate

```bash
cd /Users/yuniorrodriguezosorio/ib-trader/whop-signals
python3 -m unittest discover -s tests -v
node --check app/dashboard.js
```

No third-party test packages or network calls are required.

## Whop release checklist

No API setup helper is included. Creating plans, pricing, checkout, and memberships changes an
external commercial account, and those details must be implemented against the current official
Whop documentation after the owner chooses the product structure.

Before release:

1. Choose the brand, offer, currency, price, refund policy, and jurisdiction-specific disclosures.
2. Configure a Whop product manually or implement a reviewed server-side integration using only
   current official Whop API documentation and credentials stored outside this repository.
3. Add server-side membership authentication. A public static URL is not access control.
4. Host the generator behind an authenticated service; do not expose private data files.
5. Replace any preview copy only with benefits that are actually delivered.
6. Run the tests and manually inspect fresh, stale, missing, and no-data states.
7. Obtain legal/compliance review before accepting payment for market-related content.

### Market-data rights are a release gate

The preview can consume local fixtures and owner-approved sources, but the current upstreams
must not be assumed sublicensable:

- Cboe's delayed-quotes page says automated extraction/download of its quote-table data is
  prohibited. Do not build a paid feed on that endpoint without written rights from Cboe.
- The official LSE client states that retrieved data may be used for the account holder's own
  research/trading/model training, but may not be redistributed, resold, or exposed to third
  parties through a competing feed or interface.

The clean commercial architecture is either a licensed redistribution agreement or a
bring-your-own-data design where each member connects a source whose terms permit that use.
Until one of those exists, keep this kit an internal educational preview.

## Explicitly not claimed

- No returns, win rate, member count, revenue, savings, or income claim.
- No guaranteed alerts, trades, entries, stops, targets, or outcomes.
- No claim that options volume reveals dealer inventory or aggressor direction.
- No claim that the dashboard is real-time merely because an endpoint responds.
- No affiliation with or endorsement by the reference product or its creator.
