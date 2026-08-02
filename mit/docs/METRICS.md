# Metrics

## Net GEX scenario

Per-contract contribution:

```text
sign × gamma × open_interest × 100 × spot² × 0.01
```

The sign convention is call-positive and put-negative. It is a scenario proxy, not proof of dealer inventory.

## Net DEX scenario

```text
delta × open_interest × 100 × spot
```

## Gamma flip

The engine reprices every option on a spot grid from 72% to 128% of current spot using its IV (or a fallback IV), sums scenario GEX and linearly interpolates the nearest zero crossing.

## Expected move

Nearest-expiry at-the-money call mid + put mid.

## Max pain

The strike minimizing aggregate intrinsic payout across open interest at settlement.

## Deep-book imbalance

```text
(sum bid size - sum ask size) / (sum bid size + sum ask size)
```

## Microprice

```text
(best ask × best bid size + best bid × best ask size)
/ (best bid size + best ask size)
```

## Shock and reversion calibration

A shock is either:

- absolute daily return ≥ configured 10% or 15% threshold; or
- absolute rolling z-score ≥ configured threshold.

For historical shocks above the active threshold, a reversion success means at least one close during the next `N` sessions moved opposite to the shock close. This deliberately measures occurrence, not first-touch order or tradable P&L.
