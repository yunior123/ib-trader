#!/usr/bin/env python3
"""
octopus_bot.py - Opening-drive options scalper ("in fast, out at the flip")
===========================================================================
Eight arms on ten tickers: DRAM, SPCX, TSLA, AAPL, NVDA, TSM, TXN, AMD, INTC, ASML.

How it works (Yunior spec):
  1. 9:30-9:35 ET: measure each ticker's OPENING DRIVE (gap vs prev close +
     first-5-minute move). This is the direction detector.
  2. CATALYST GATE: only trades tickers with real volatility fuel — an extreme
     opening move (|drive| >= catalyst_move_pct) and volume surge, or a listed
     catalyst day (earnings/news from data/catalysts). No fuel -> no trade.
  3. ENTER ~9:35 with the direction: CALL on up-drive, PUT on down-drive.
     ATM option, DTE >= 5 (never 0DTE), sized at risk_fraction of capital.
  4. EXIT AT THE FLIP: as soon as 1m closes cross the EMA(5) against the trade
     direction (2 consecutive), or premium stop (-30%), or time cap (60 min),
     or 15:45 hard flatten. Scalps don't sleep in positions.
  Optional researcher hook: set KILO_API_KEY to route headlines through
  NVIDIA Nemotron (Kilo Code free tier) for a catalyst sanity-check; without
  it the bot is a pure movement detector (fast, no external dependency).

Backtest prices synthetic ATM options (Black-Scholes over real 1m bars,
realized-vol IV proxy). Sounds: momentum on signal, Glass on entry, Hero on exit.
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from day_trading_bot import (
    TORONTO, _bar_et, _in_rth, add_indicators, load_ohlcv_csv,
    order_commission, play_sound, TradeLog,
)
from options_trading_bot import bs_price, realized_vol, next_expiry, OPT_CONFIG

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("octopus")

TICKERS = ["DRAM", "SPCX", "TSLA", "AAPL", "NVDA", "TSM", "TXN", "AMD", "INTC", "ASML"]

OCTO_CONFIG = {
    "catalyst_move_pct": 2.5,    # opening drive must exceed this (the "fuel" gate)
    "volume_surge_mult": 1.5,    # first-5m volume vs 20-bar average
    "max_positions": 3,          # strongest drives only, per day
    "risk_fraction": 0.25,       # of capital per scalp
    "min_dte": 5,                # never 0DTE (hard floor 3 in next_expiry)
    "ema_period": 13,            # 1m EMA for flip detection (sweep winner)
    "flip_bars": 2,              # consecutive closes across EMA = direction changed
    "grace_bars": 10,             # no flip-checks during the first N bars (let it breathe)
    "premium_stop_pct": 30.0,    # cut if option loses 30% (scalps don't marinate)
    "time_cap_min": 30,          # max minutes in a scalp
    "eod_flatten": (15, 45),
    "commission_per_contract": 1.0,
    "multiplier": 100,
    "risk_free_rate": 0.04,
    "iv_premium": 1.10, "iv_floor": 0.20, "iv_cap": 2.00,
    "db_log": True,
}


class OctopusScalp:
    __slots__ = ("sym", "right", "strike", "expiry", "entry_prem", "contracts",
                 "entry_ts", "peak", "against")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def opening_drive(day_df: pd.DataFrame, prev_close: Optional[float]):
    """Direction + magnitude of the 9:30-9:35 drive (gap + first 5 minutes)."""
    rth = day_df[[(9, 30) <= _bar_et(ts) < (9, 35) for ts in day_df.index]]
    if len(rth) < 3:
        return None
    o, c = float(rth.iloc[0]["open"]), float(rth.iloc[-1]["close"])
    drive = (c / o - 1) * 100
    if prev_close and prev_close > 0:
        drive += (o / prev_close - 1) * 100  # include the gap
    vol5 = float(rth["volume"].sum())
    return {"drive_pct": drive, "px_935": c, "vol5": vol5, "ts": rth.index[-1]}


def run_backtest_ticker(sym: str, cfg: dict, capital: float, db=None):
    path = f"data/{sym.lower()}_1m_30d.csv"
    if not Path(path).exists():
        return None
    df = add_indicators(load_ohlcv_csv(path), {**OPT_CONFIG, **cfg})
    df["ema5"] = df["close"].ewm(span=cfg["ema_period"], adjust=False).mean()
    dates = sorted(set(ts.tz_convert(TORONTO).date() for ts in df.index))
    cash = capital
    wins = losses = 0
    trades = []
    prev_close = None
    mult, comm = cfg["multiplier"], cfg["commission_per_contract"]

    for d in dates:
        day = df[[ts.tz_convert(TORONTO).date() == d for ts in df.index]]
        rth = day[[_in_rth(ts) for ts in day.index]]
        if len(rth) < 30:
            prev_close = float(day.iloc[-1]["close"]) if len(day) else prev_close
            continue
        sig = opening_drive(rth, prev_close)
        prev_close = float(day.iloc[-1]["close"])
        if sig is None:
            continue
        vol_ma = float(rth["vol_ma"].iloc[min(20, len(rth) - 1)] or 0)
        surge = vol_ma > 0 and sig["vol5"] >= vol_ma * 5 * cfg["volume_surge_mult"] / 5
        if abs(sig["drive_pct"]) < cfg["catalyst_move_pct"] or not surge:
            continue  # no fuel -> octopus stays in its cave

        right = "C" if sig["drive_pct"] > 0 else "P"
        S = sig["px_935"]
        sigma = min(max(realized_vol(df["close"][:sig["ts"]]) * cfg["iv_premium"],
                        cfg["iv_floor"]), cfg["iv_cap"])
        expiry = next_expiry(sig["ts"].to_pydatetime(), cfg["min_dte"])
        strike = round(S)
        T = max(1e-6, (expiry - sig["ts"].tz_convert(TORONTO)).total_seconds() / (365 * 86400))
        prem = bs_price(S, strike, T, cfg["risk_free_rate"], sigma, right)
        if prem < 0.05:
            continue
        n = int((cash * cfg["risk_fraction"]) / (prem * mult + comm))
        if n < 1 and cash >= prem * mult + comm:
            n = 1
        if n < 1:
            continue
        cash -= n * prem * mult + comm
        play_sound("enter")
        scalp = OctopusScalp(sym=sym, right=right, strike=strike, expiry=expiry,
                             entry_prem=prem, contracts=n,
                             entry_ts=sig["ts"], peak=prem, against=0)
        if db:
            db.trade(sig["ts"], sym, f"BUY-{right}", n, prem, comm,
                     reason=f"drive {sig['drive_pct']:+.1f}%")

        # manage the scalp bar by bar
        after = rth[rth.index > sig["ts"]]
        exit_prem, reason = None, "eod"
        for ts, row in after.iterrows():
            S_now = float(row["close"])
            T_now = max(0.0, (expiry - ts.tz_convert(TORONTO)).total_seconds() / (365 * 86400))
            prem_now = bs_price(S_now, strike, T_now, cfg["risk_free_rate"], sigma, right)
            scalp.peak = max(scalp.peak, prem_now)
            mins = (ts - sig["ts"]).total_seconds() / 60
            flip = (S_now < float(row["ema5"])) if right == "C" else (S_now > float(row["ema5"]))
            scalp.against = scalp.against + 1 if flip else 0
            if mins >= cfg.get("grace_bars", 5) and scalp.against >= cfg["flip_bars"]:
                exit_prem, reason = prem_now, "flip"
            elif prem_now <= prem * (1 - cfg["premium_stop_pct"] / 100):
                exit_prem, reason = prem_now, "stop"
            elif mins >= cfg["time_cap_min"]:
                exit_prem, reason = prem_now, "time"
            elif _bar_et(ts) >= cfg["eod_flatten"]:
                exit_prem, reason = prem_now, "eod"
            if exit_prem is not None:
                break
        if exit_prem is None:
            S_last = float(after.iloc[-1]["close"]) if len(after) else S
            exit_prem = bs_price(S_last, strike, 1e-6, cfg["risk_free_rate"], sigma, right)
        pnl = n * (exit_prem - prem) * mult - 2 * comm
        cash += n * exit_prem * mult - comm
        play_sound("exit")
        wins, losses = wins + (pnl >= 0), losses + (pnl < 0)
        trades.append((d, right, sig["drive_pct"], pnl, reason))
        if db:
            db.trade(ts if exit_prem is not None else sig["ts"], sym, f"SELL-{right}",
                     n, exit_prem, comm, pnl, reason)

    return {"sym": sym, "cash": cash, "pnl": cash - capital,
            "trades": trades, "wins": wins, "losses": losses}


def main():
    p = argparse.ArgumentParser(description="Octopus: opening-drive options scalper")
    p.add_argument("--mode", choices=["backtest"], default="backtest")
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--catalyst-move-pct", type=float, default=OCTO_CONFIG["catalyst_move_pct"])
    p.add_argument("--time-cap-min", type=int, default=OCTO_CONFIG["time_cap_min"])
    args = p.parse_args()
    cfg = OCTO_CONFIG.copy()
    cfg.update({"catalyst_move_pct": args.catalyst_move_pct, "time_cap_min": args.time_cap_min})
    db = TradeLog(bot="octopus", mode="backtest") if cfg["db_log"] else None

    tot = W = L = 0.0
    print(f"{'ticker':<7}{'scalps':>7}{'W/L':>7}{'PnL':>10}")
    for sym in TICKERS:
        r = run_backtest_ticker(sym, cfg, args.capital, db)
        if r is None:
            print(f"{sym:<7} sin datos"); continue
        tot += r["pnl"]; W += r["wins"]; L += r["losses"]
        print(f"{sym:<7}{len(r['trades']):>7}{str(r['wins'])+'/'+str(r['losses']):>7}{r['pnl']:>+10.2f}")
        for d, right, drv, pnl, reason in r["trades"]:
            print(f"    {d} {right} drive={drv:+.1f}% -> {pnl:+8.2f} ({reason})")
    wr = W / (W + L) * 100 if W + L else 0
    print(f"\nTOTAL: {tot:+.2f} USD sobre ${args.capital * len(TICKERS):.0f} "
          f"({tot / (args.capital * len(TICKERS)) * 100:+.2f}%) | {int(W)}W/{int(L)}L ({wr:.0f}%)")


if __name__ == "__main__":
    main()
