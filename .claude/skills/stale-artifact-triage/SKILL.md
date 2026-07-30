---
name: stale-artifact-triage
description: Trace a stale ib-trader file or screen widget to its producer, keepalive, consumer, and safe recovery. Use when the cockpit is blank, arrows are old, feeds stop, or a JSON/text artifact freezes.
---

# Stale Artifact Triage

1. Resolve the displayed field to its artifact and consumer with `rg`.
2. Check file mtime, embedded timestamp, producer PID, keepalive PID, and recent log.
3. Distinguish closed-session silence from a crashed producer.
4. Validate dependencies and dynamic IBKR mode/port before restarting.
5. Restart only the owning keepalive; never restart the entire fleet without evidence.
6. Confirm two fresh cycles and consumer refresh.

Report the complete chain: `producer -> artifact -> consumer -> screen`.
