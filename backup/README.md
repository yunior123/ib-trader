# backup/ — dormant Python (moved 2026-07-09 por orden de Yunior)

Fleet code defaults to C++; Python stays at the root only where a library forces
it and it is actively used by the live fleet (`day_trading_bot.py` — imported by
`topgainer/exec_trade.py` + `topgainer/watchdog.py` for the IBKR/ib_insync
execution and floor/target math — plus `topgainer/` and `scripts/` bridges).

Here:
- **Legacy KOD system** (self-contained): main.py, config.py, strategy.py,
  execution.py, portfolio.py, risk.py, indicators.py, ib_client.py, logger.py,
  database.py, test_buy.py, test_connection.py.
- **Dormant bots** (validated but switched off; import `day_trading_bot` from the
  repo root, so to reactivate run from the root: `PYTHONPATH=. venv/bin/python
  backup/<bot>.py ...` or move the file back): octopus_bot.py, hf_ppo_bot.py,
  day_trading_leveraged_bot.py, options_trading_bot.py, ram_leveraged_bot.py,
  dram_signal_bot.py (superseded by the C++ dram_signal_bot).
