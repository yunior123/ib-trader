# Order path QA/security audit — 2026-07-29

## Verdict

**NO-GO for the inaugural live order.** No broker order was placed, modified, or
cancelled during this audit.

Runtime is currently safe but not execution-ready:

- `data/ib_mode.txt` says `live` and Gateway port 4001 is listening.
- Six `chart_bridge.py` processes answer `/health` with `signal_only=true`.
- `order_engine` is not running.
- `order_engine/ARM_LIVE` is absent.
- The QQQ account query over the chart WebSocket timed out without returning an
  account frame, so the UI path did not prove account visibility.

The absence of both the engine and arm file means an order cannot be transmitted
now. It is not proof that the path is safe once armed.

## End-to-end path

### Entry from the cockpit

1. The UI builds a draft and asks the bridge for a local preflight
   (`charts/live.html:2019-2147`).
2. The bridge validates basic fields and derives a contract preview
   (`scripts/chart_bridge.py:1447-1519`).
3. On human confirmation the bridge persists a zone with `exec=true`,
   `confirm_id`, timestamp, and date (`scripts/chart_bridge.py:1289-1322`).
4. The engine reloads `data/exec_zones_<sym>.json`, waits for two distinct bar
   prints through the trigger, applies gates, then calls `place_limit`
   (`order_engine/order_engine.cpp:744-1018`).
5. `TwsAdapter::place_limit` constructs a DAY limit and calls the only live
   `EClientSocket::placeOrder` boundary
   (`order_engine/tws_adapter.cpp:57-80`).

### Position actions

1. Account rows send `close`, `cancel`, or `modify`
   (`charts/live.html:1756-1803`).
2. The bridge appends a JSON command to `order_engine/commands.jsonl`
   (`scripts/chart_bridge.py:1586-1611`).
3. The engine consumes complete new lines, validates closes against broker
   positions and prices the exact option contract before calling TWS
   (`order_engine/order_engine.cpp:576-736`).

### Session policy

- Options are RTH-only.
- Stock entries and stock closes request `OVERNIGHT_AND_DAY`, which sets
  `outsideRth=true` and `includeOvernight=true`
  (`order_engine/order_policy.h:13-85`).
- Native stock stops set `outsideRth=true` but explicitly set
  `includeOvernight=false` (`order_engine/tws_adapter.cpp:83-105`).

## Findings

### Resolved during this audit — compile, naked SELL and protective stops

Concurrent remediation initially broke the full build, but both compile errors
were corrected and the current full engine compiles cleanly.

The engine now runs `decide_entry_side` before both STK and OPT entries. BUY may
open/increase a long; SELL must reduce a broker-confirmed long of the exact
contract and cannot exceed its quantity
(`order_engine/guards.h:255-273`;
`order_engine/order_engine.cpp:922-935,1007-1021`). This closes the stock-short
and naked-option bypass.

Clean disarm now preserves native stops and cancels only unfilled
entries/closes (`order_engine/guards.h:116-124`;
`order_engine/tws_adapter.cpp:172-185`). This closes the prior clean-exit gap.

### P0 — overnight stock can fill without overnight protection

Stock entry uses `OVERNIGHT_AND_DAY`, but its native STP cannot participate in
the overnight venue. A fill during the overnight session can therefore exist
without the advertised native protection. Either:

- disable automatic overnight entries entirely; or
- use a broker-supported overnight protection design proven with paper
  what-if/soak testing and label the gap explicitly.

Do not describe the current GTC STP as overnight protection.

### P1 — localhost WebSocket protection is improved but incomplete

The service defaults to `127.0.0.1`, which limits network exposure, but
`/stream` now rejects non-local browser Origins
(`scripts/chart_bridge.py:1578-1587,2618-2623`). Missing Origin is still allowed
for native/non-browser clients, and there is no connection-level app token.

Arming is materially stronger: the bridge issues a two-minute, single-use
challenge bound to the zone's money/contract fields and consumes it before
`exec=true` (`scripts/chart_bridge.py:1524-1575,2744-2760`). The engine separately
requires the persisted human-confirmation fields at trigger time
(`order_engine/order_engine.cpp:889-899`). Broker `whatIf` is now called on both
STK and OPT final orders before transmit
(`order_engine/order_engine.cpp:963-970,1068-1076`).

Remaining hardening: require a connection-level app token for every mutating
command, reject missing Origin for browser deployments, and make the engine's
confirmation proof cryptographically verifiable rather than only checking the
shape/date of fields written by the bridge.

### P1 — commands now reject engine-down, but ACK is still incomplete

The bridge now rejects a position action when the engine is down and writes
nothing (`scripts/chart_bridge.py:1669-1682`), matching the engine's intentional
start-at-EOF behavior (`order_engine/order_engine.cpp:314-317`).

There is still no durable command ID or correlated accepted/rejected/broker ACK
returned to the initiating window. UI success means “line appended”, not broker
acceptance.

### P1 — option preview does not lock the contract

The UI reviews a derived strike, but the zone request persists trigger price,
kind and expiry—not `conId` or the reviewed strike. At trigger time the engine
again chooses the nearest strike (`order_engine/chain.h:81-94,130-142`). A chain
change can therefore select a different contract from the one the user reviewed.
If expiry is empty, nearest-row can also match any expiry.

Required contract: persist and require exact `conId` plus symbol, expiry, strike,
right, multiplier, trading class, exchange and currency. Requalify that exact
contract at transmit time; a mismatch invalidates confirmation.

### P1 — handmade contracts are not generally qualified

Every stock contract hardcodes `primaryExchange="NASDAQ"` and every option sets
`tradingClass=symbol` (`order_engine/tws_adapter.h:52-77`). This is not correct
for every supported symbol/class. The order boundary checks string fields but
does not prove IBKR qualification.

Required gate: resolve a unique conId through IBKR and transmit that qualified
contract. Do not infer primary exchange or option trading class.

### P1 — multi-account state is ambiguous

Startup requires the expected account to appear in `managedAccounts`, which is
good, but multiple managed accounts can pass. Position callbacks discard their
account and key positions only by contract
(`order_engine/tws_adapter.cpp:278-284`). Orders do not set an explicit account.

Required gate: live mode must select exactly one configured account, set
`Order.account`, keep positions keyed by account+contract, and expose the same
account in every preview, confirmation and ACK.

### P1 — future timestamps pass freshness gates

Chain freshness uses `now - epoch <= 900`, so a future epoch passes
(`order_engine/chain.h:143-160`). Stock-bar freshness has the same one-sided
comparison (`order_engine/order_engine.cpp:828-838`).

Reject data older than the limit and data beyond a small positive clock-skew
tolerance.

### P1 — cancel ownership and UI scope

The account view displays all open orders and offers Cancel for each. The cancel
path forwards an arbitrary order ID and `TwsAdapter::cancel` does not require an
`OE:` ownership match (`order_engine/tws_adapter.cpp:108-113`). Risk-off cancel
may be deliberately broad, but it is not labelled as such and can target manual
orders.

Choose and enforce one policy: OE-only cancellation, or an explicit separate
“cancel external/manual order” confirmation showing account and full contract.

## Controls already present

- Dry by default; live transmission requires `--arm-live` plus a dated arm file.
- Expected broker account is required and exact-token matched
  (`order_engine/order_engine.cpp:340-378`).
- Reconciliation and position snapshots fail closed before dependent actions
  (`order_engine/order_engine.cpp:382-404`).
- Entry budgets exist per contract/order, per stock order, and account aggregate.
- Option gate rejects stale chain, invalid quote, spread above 5%, OI at or below
  500, and excess premium (`order_engine/chain.h:114-161`).
- Close path validates direction/quantity against broker positions and uses an
  exact option row.
- Partial fills are protected; native stops require broker ACK and have a
  watchdog.
- Entries are DAY limits and orders carry `OE:` references.
- SELL entries are position-reducing only.
- Human arming uses a short-lived, one-shot bridge challenge and a second engine
  gate.
- Broker what-if runs on the exact order assembled at trigger time.
- Clean shutdown preserves protective native stops.

## Tests run

- `test_guards`: passed, including the new SELL-reduction, confirmation and
  stop-preservation cases.
- `test_chain`: 39 passed.
- `test_orders`: 499 passed.
- `test_policy`: passed.
- All four were compiled in release and ASan/UBSan mode using temporary output.
- Chart bridge suites: 9 passed.

The official `order_engine/tests/run_tests.sh` itself still fails on the host’s
Bash 3.2 at line 24 because expanding an empty `extra[@]` under `set -u` is
treated as an unbound variable. The same current suites pass when compiled
manually in release and ASan/UBSan modes. A separate full-engine compile also
passes. The bridge backend script passes when invoked directly; it is a script,
not pytest-discoverable, so `pytest` reports “no tests ran”.

No paper or live order was used as a test.

## Inaugural live BUY checklist

All items are mandatory. Any unchecked item is **NO-GO**.

1. Clean worktree for the execution components; commit hash recorded.
2. Full engine compiles with zero warnings; release and ASan/UBSan suites pass.
3. Paper soak covers BUY STK, BUY OPT, partial fill, reject, cancel, stop ACK,
   reconnect and clean shutdown.
4. SELL-open routes are disabled; SELL is proven position-reducing only.
5. Exact account is displayed and matches an explicit `Order.account`.
6. Exact qualified conId and full contract are displayed and locked.
7. Side, quantity, limit policy, session and maximum loss are displayed.
8. Data timestamps are fresh and not future; option bid/ask/OI gate is green.
9. Broker what-if succeeds on the exact final order with `transmit=false`.
10. Confirmation nonce is server-issued, recent, single-use and required by the
    engine—not merely the UI.
11. WebSocket Origin/token protections pass negative tests.
12. Engine is running in PAPER first; command IDs receive correlated ACKs.
13. No position is open before the test; no unrelated working order can be
    cancelled or modified.
14. For shares, first live BUY is RTH-only until overnight protection is solved.
15. Protective stop behavior is proven; clean exit preserves it while position
    remains open.
16. Only then: switch to the exact live account, one share or one defined-risk
    long option, conservative limit, human final click in IBKR/TWS.
17. Verify broker ACK, fill/partial fill, position quantity, stop ACK and ledger.
18. Disarm immediately after verification; confirm no residual entry exists and
    never cancel protection while a position remains.
