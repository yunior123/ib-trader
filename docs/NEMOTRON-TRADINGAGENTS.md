# Nemotron TradingAgents profile

The off-hot-path research graph uses NVIDIA's OpenAI-compatible NIM endpoint with
`nvidia/nemotron-3.5-lightning-30b-a3b` for both quick and deep roles.  The model
choice lives in `config/llm.env`; the bridge maps it to the environment names read
by TradingAgents.  The NVIDIA credential is loaded in-process from the external
TradingAgents `.env` and is never copied or printed.

`scripts/ta_view.py` injects local IBKR bars, OI walls, gamma regime, the LSE
activity heatmap, and the Massive equity-footprint health state.  It keeps two
layers separate:

- LSE gamma×volume is descriptive option activity, not dealer GEX.
- Polygon OPRA start-of-day OI supports modeled structural GEX and flip levels
  under the repository's explicit calls-positive/puts-negative convention.

If Massive lacks real-time stock WebSocket access, order flow is emitted as
`DATA` under `REALTIME_OR_FAIL_CLOSED`; tokenized-stock perpetuals are not silently
substituted for equity prints.  The research output remains signal-only and never
enters the live execution path.
