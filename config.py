"""
Configuration for the IB trading bot.
Edit values here, or override via environment variables.
"""
import os

# --- Connection ---
# TWS paper = 7497, TWS live = 7496, IB Gateway paper = 4002, IB Gateway live = 4001
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", 7496))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", 7))
IB_ACCOUNT = os.getenv("IB_ACCOUNT", "U26942420")  # TFSA account; set to U26642820 for individual

# --- Universe ---
SYMBOLS = ["CUPR"]  # SUPER COPPER CORP - ~0.47 CAD, Canadian
EXCHANGE = "SMART"
CURRENCY = "CAD"

# --- Trend / momentum indicators ---
EMA_FAST = 20
EMA_MED = 50
EMA_SLOW = 200
RSI_PERIOD = 14
ATR_PERIOD = 14

# --- Entry / exit thresholds ---
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 70
ATR_TRAIL_MULT = 2.0  # used both for the overbought stretch check and stop distance

# --- Core / trading split (never sell the core; actively trade the rest) ---
CORE_FRACTION = 0.70
TRADING_FRACTION = 0.30

# --- Partial profit ladder: (gain_from_avg_cost, fraction_of_trading_shares_to_sell) ---
PROFIT_LADDER = [
    (0.04, 0.10),
    (0.08, 0.20),
    (0.12, 0.20),
    (0.18, 0.20),
]

# --- Risk sizing ---
ACCOUNT_RISK_PER_TRADE = 0.01   # fraction of net liq risked per new entry
MAX_POSITION_PCT_OF_NAV = 0.25  # hard cap per symbol

# --- Data / loop ---
BAR_SIZE = "1 day"
HISTORY_DURATION = "2 Y"
USE_RTH = True
POLL_SECONDS = 300  # how often the loop re-evaluates each symbol

# --- Safety ---
# Starts True on purpose. Only flip to False after extended paper-trading
# testing, and only when connected to a PAPER account port first.
DRY_RUN = True
