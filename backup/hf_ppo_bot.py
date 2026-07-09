#!/usr/bin/env python3
"""
hf_ppo_bot.py - Evaluate the Hugging Face PPO trading agent on REAL fresh data
==============================================================================
Model: Adilbai/stock-trading-rl-agent (stable-baselines3 PPO, 4.9MB — runs
fine on the 8GB Mac, CPU-only). Trained on FAANG daily data up to mid-2025.

We rebuild its exact feature pipeline (the repo's own dataprocessor +
environment) on FRESH Yahoo daily data and let the agent trade the most
recent out-of-sample year. Reports agent return vs buy & hold per ticker.

Action space (matches the model card):
  action[0] 0=Hold 1=Buy 2=Sell | action[1] position size 0-1

SECURITY WARNING (accepted risk, research-only tool):
  * PPO.load() and scaler.pkl deserialize PICKLE data -> arbitrary code
    execution if the files are malicious. dataprocessor/enviromentcreator
    are third-party code executed locally.
  * Mitigation: files come only from the pinned HF revision below (no silent
    updates), models/ is gitignored, and this bot NEVER touches the broker —
    it is an offline evaluator. Do not point it at other repos casually.
  * Verdict was "do not trade this model" — see AGENTS.md.
"""

# Pin the exact HF revision evaluated; refuse silent upstream changes.
HF_REPO = "Adilbai/stock-trading-rl-agent"
HF_REVISION = "a317fec1939eda44d04088b47b48ca3ee158bc1f"  # pinned commit evaluated 2026-07-08

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, "models/hf_ppo")
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

MODEL_DIR = Path("models/hf_ppo")
TICKERS_SEEN = ["AAPL", "TSLA", "GOOGL"]        # in training distribution
TICKERS_UNSEEN = ["NVDA", "MU", "AMD"]           # never seen by the agent


def build_rl_data(sym: str):
    """Run the repo's own pipeline: indicators -> lags -> normalize -> RL states."""
    from dataprocessor import StockDataProcessor
    proc = StockDataProcessor(data_dir="models/hf_ppo/stock_data",
                              cache_dir="models/hf_ppo/cache")
    df = proc.download_stock_data(sym, period="3y")
    if df is None or len(df) < 400:
        return None
    df["Ticker"] = sym
    df = proc.calculate_technical_indicators(df)
    df = proc.create_lagged_features(df)
    df = proc.clean_and_normalize_data(df)
    real_close = df.set_index("Date")["Close"].copy()  # REAL prices before env mangling
    rl_data, _scaler = proc.create_rl_states_actions(df)
    return rl_data, real_close


def evaluate(sym: str, model):
    from enviromentcreator import EnhancedStockTradingEnvironment
    out = build_rl_data(sym)
    if out is None:
        return None
    rl_data, real_close = out
    if sym not in rl_data:
        return None
    # out-of-sample: keep only the last ~250 sequences (fresh year)
    d = rl_data[sym]
    n = min(250, len(d["states"]))
    rl_slice = {sym: {
        "states": d["states"][-n:], "rewards": d["rewards"][-n:],
        "dates": d["dates"][-n:], "state_features": d["state_features"],
    }}
    env = EnhancedStockTradingEnvironment(rl_data=rl_slice, ticker=sym,
                                          initial_balance=10_000.0,
                                          enable_logging=False)
    # REAL price series aligned to the sliced dates (the repo env's own price
    # extraction is broken: it reads normalized features as prices)
    dates = rl_slice[sym]["dates"]
    px = np.array([float(real_close.loc[d]) for d in dates])

    obs, _ = env.reset()
    acts = {0: 0, 1: 0, 2: 0}
    cash, shares = 10_000.0, 0.0
    cost_bp = 0.001
    i = 0
    done = False
    while not done and i < len(px):
        action, _ = model.predict(obs, deterministic=True)
        a, size = int(action[0]), float(action[1])
        acts[a] += 1
        p = px[i]
        if a == 1 and size > 0:      # BUY size fraction of cash
            spend = cash * min(size, 1.0)
            if spend > 1:
                cash -= spend
                shares += spend * (1 - cost_bp) / p
        elif a == 2 and size > 0:    # SELL size fraction of shares
            qty = shares * min(size, 1.0)
            if qty * p > 1:
                shares -= qty
                cash += qty * p * (1 - cost_bp)
        obs, _, term, trunc, _ = env.step(action)
        done = bool(term) or bool(trunc)
        i += 1
    equity = cash + shares * px[min(i, len(px) - 1)]
    bh = float(px[-1] / px[0] - 1)
    return {
        "sym": sym,
        "agent_ret": equity / 10_000.0 - 1,
        "bh_ret": bh,
        "actions": acts,
        "days": n,
    }


def main():
    from stable_baselines3 import PPO
    model = PPO.load(MODEL_DIR / "final_model.zip", device="cpu")
    print(f"Modelo cargado: obs={model.observation_space.shape} act={model.action_space}")
    rows = []
    for group, syms in (("VISTO EN TRAIN", TICKERS_SEEN), ("NUNCA VISTO", TICKERS_UNSEEN)):
        for sym in syms:
            try:
                r = evaluate(sym, model)
            except Exception as e:
                print(f"{sym}: error {str(e)[:90]}")
                continue
            if r is None:
                print(f"{sym}: sin datos")
                continue
            r["group"] = group
            rows.append(r)
            a = r["actions"]
            print(f"{sym:<6} [{group}] agente={r['agent_ret']*100:+7.2f}%  B&H={r['bh_ret']*100:+7.2f}%  "
                  f"ventaja={(r['agent_ret']-r['bh_ret'])*100:+6.2f} pts  "
                  f"acciones H/B/S={a[0]}/{a[1]}/{a[2]} ({r['days']}d)")
    if rows:
        adv = np.mean([r["agent_ret"] - r["bh_ret"] for r in rows]) * 100
        print(f"\nVENTAJA MEDIA vs buy&hold: {adv:+.2f} pts en {len(rows)} tickers")


if __name__ == "__main__":
    main()
