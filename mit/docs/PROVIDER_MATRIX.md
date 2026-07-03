# Provider matrix

| Provider | Quotes | Intraday bars | Daily history | L2/L3 depth | Option chain | Greeks/IV/OI | Flow/GEX streams |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mock | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Databento | ✓ | ✓ | ✓ | ✓ | Dataset-dependent | Requires additional normalization/data | — |
| Intrinio | ✓ | ✓* | ✓ | — | ✓ | ✓ | Product-dependent |
| Unusual Whales | — | — | — | — | Topic-dependent | Topic-dependent | ✓ |

`*` Intrinio intraday endpoint/source availability depends on subscription. The adapter reports a capability-local fallback when an entitlement is missing.

## Adding another provider

1. Implement one or more interfaces in `providers/base.py`.
2. Normalize all timestamps to timezone-aware UTC.
3. Return domain models, not raw dictionaries.
4. Register the provider name in `config.py` and `registry.py`.
5. Add fixture-based normalization tests.
6. Document rate limits and entitlements.
