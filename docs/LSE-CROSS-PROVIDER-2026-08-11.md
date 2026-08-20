# LSE cross-provider audit — 2026-08-11

## Scope and definitions

- Cockpit runtime remained London-only throughout the audit.
- Same-session comparison used the first three unexpired expiries returned by LSE after
  the 16:00 ET rollover.
- The fair comparison is **gamma × current-day volume** by contract. This is the metric
  used for LSE walls, magnet, and heatmap. It is not dealer GEX.
- Polygon OI × gamma and plain-OI walls are reported separately. Databento independently
  checked Polygon's start-of-day OI; it did not supply a comparable full-session heatmap.
- Spot used for side classification was the current LSE WebSocket midpoint in each cockpit.

## Like-for-like results

| Symbol | LSE CW / PW / magnet | Polygon gamma×volume CW / PW / magnet | Spearman profile | top-5 overlap |
|---|---:|---:|---:|---:|
| QQQ | 720 / 718 / 720 | 720 / 718 / 720 | 0.9000 | 4/5 |
| NVDA | 220 / 217.5 / 220 | 220 / 217.5 / 220 | 0.5329 | 5/5 |
| SMH | 582.5 / 565 / 565 | 582.5 / 565 / 565 | 0.9668 | 5/5 |
| MU | 900 / 850 / 900 | 900 / 850 / 900 | 0.9099 | 4/5 |
| AAPL | 307.5 / 305 / 307.5 | 307.5 / 305 / 307.5 | 0.8188 | 4/5 |
| MSFT | 505 / 500 / 505 | 505 / 500 / 500 | 0.7949 | 4/5 |

Aggregate: 12/12 side-specific walls agree, 5/6 magnets agree, 26/30 top-five strikes
overlap, and median Spearman rank correlation is 0.8594. NVDA has identical top-five
strikes and levels despite a weaker full-profile rank correlation, so the disagreement is
in the low-activity tail rather than the displayed levels.

## Coverage and provenance

| Symbol | Expiries | LSE contracts used | Polygon contracts used | LSE latest option event |
|---|---|---:|---:|---|
| QQQ | 12, 13, 14 Aug | 583 | 721 | 16:15:00 ET |
| NVDA | 12, 14, 17 Aug | 242 | 248 | 16:00:35 ET |
| SMH | 12, 14, 17 Aug | 333 | 529 | 16:14:16 ET |
| MU | 12, 14, 17 Aug | 738 | 1,079 | 16:00:35 ET |
| AAPL | 12, 14, 17 Aug | 192 | 262 | 16:00:35 ET |
| MSFT | 12, 14, 17 Aug | 397 | 468 | 16:00:35 ET |

The post-close `stale=true` flag is expected under the 15-minute live freshness gate. It
must remain visible, even though the completed-session snapshot is still useful for this
end-of-day audit.

## Databento and Intrinio

- Databento OPRA historical availability for this account ended at 09:30 ET on the audit
  date. A bounded QQQ request for the 1,144 contracts in the three compared expiries found
  all 1,144 and matched Polygon OI exactly: 100.00% exact, MAE 0 contracts. Both produced
  plain-OI walls of call 735 and put 685. The bounded validation download cost $0.013501;
  earlier schema/coverage inspection brought total audit downloads to about $0.179.
- Intrinio's documented `source=delayed` endpoint returned HTTP 403 for both tested QQQ
  expiries. The configured source is valid; this account lacks the required options
  entitlement, so no Intrinio value was substituted or inferred.

## Integration defect found and fixed

At and after 16:00 ET, the LSE expiry selector retained the just-expired 0DTE. Since LSE
returns each contract's latest trade, QQQ then mixed 10-Aug rows from the expired 11-Aug
chain into the 11-Aug close profile. `lse_gamma_map.py` now rolls today's expiry out at
16:00 ET before discovering the next three live expiries. A regression test proves that
the expired chain is neither requested nor included.

Provider HTTP errors were also sanitized so native httpx exceptions cannot print Polygon
or Intrinio API keys embedded in request URLs.

## Verdict

For today's **gamma×volume activity map**, LSE reproduced Polygon's important structure
very well and with real-time equity WebSocket prices. It is suitable as the cockpit's sole
runtime context source under the current labels and stale gates. It is not a replacement
for OI-based dealer GEX or gamma flip: LSE does not expose open interest, and the cockpit
correctly keeps `flip=null`.

## v24 runtime verification

After rebuilding and relaunching the six London-only windows, every heatmap `fetch_ts`
advanced automatically by exactly 300 seconds in one unattended cycle. The corresponding
WebSocket history frames reported `chain_src=lse_gamma_volume`,
`profile_metric=gamma_volume`, `feed.lse_only=true`, and the same advanced epoch for the
heatmap, walls, magnets, and gamma-flip countdowns. Six and only six `--lse-only` bridges
were running; their external sockets were connected to London, with no Polygon, Intrinio,
Databento, provider-bridge, or legacy heatmap daemon in the runtime.
