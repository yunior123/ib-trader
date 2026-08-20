#!/usr/bin/env python3
"""Chronological audit of four daily/weekly London volume-only proxies.

Historical LSE option candles do not contain model Greeks.  For WDN only, this
research lane reconstructs Black-Scholes IV/delta/gamma from the daily option
close and the synchronized underlying close.  MM$ uses weekly option volume
directly.  Results are structural next-session magnet tests, never dealer-book
or proprietary-PML claims.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "research" / "wdn_mm_backtest_raw"
OUT_JSON = REPO / "data" / "research" / "milk_proxy_backtest.json"
OUT_MD = REPO / "data" / "research" / "milk_proxy_backtest.md"
SYMS = ("QQQ", "NVDA", "SMH", "MU", "AAPL", "MSFT")
THRESHOLDS = (0.25, 0.50, 1.00, 1.50, 2.00, 3.00, 5.00)
RISK_FREE = 0.04
PRICE_CACHE = RAW / "lse_underlying_daily.json"


def n_cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def n_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(spot, strike, t, sigma, right):
    root = math.sqrt(t)
    d1 = (math.log(spot / strike) + (RISK_FREE + 0.5 * sigma * sigma) * t) / (sigma * root)
    d2 = d1 - sigma * root
    disc = math.exp(-RISK_FREE * t)
    if right == "C":
        return spot * n_cdf(d1) - strike * disc * n_cdf(d2)
    return strike * disc * n_cdf(-d2) - spot * n_cdf(-d1)


def implied_greeks(spot, strike, t, premium, right):
    disc = math.exp(-RISK_FREE * t)
    intrinsic = max(spot - strike * disc, 0.0) if right == "C" else max(strike * disc - spot, 0.0)
    upper = spot if right == "C" else strike * disc
    if premium < intrinsic - 0.02 or premium <= 0 or premium >= upper:
        return None
    lo, hi = 0.005, 5.0
    if bs_price(spot, strike, t, hi, right) < premium:
        return None
    for _ in range(55):
        mid = (lo + hi) / 2.0
        if bs_price(spot, strike, t, mid, right) < premium:
            lo = mid
        else:
            hi = mid
    sigma = (lo + hi) / 2.0
    root = math.sqrt(t)
    d1 = (math.log(spot / strike) + (RISK_FREE + 0.5 * sigma * sigma) * t) / (sigma * root)
    delta = n_cdf(d1) if right == "C" else n_cdf(d1) - 1.0
    gamma = n_pdf(d1) / (spot * sigma * root)
    return delta, gamma, sigma


def next_friday(day):
    add = (4 - day.weekday()) % 7
    if add == 0:  # daily candle is end-of-day; today's weekly has settled
        add = 7
    return day + dt.timedelta(days=add)


def volume_pain(frame, spot):
    calls = frame[frame.opt_type == "C"].groupby("strike").volume.sum().to_dict()
    puts = frame[frame.opt_type == "P"].groupby("strike").volume.sum().to_dict()
    candidates = sorted(set(calls) | set(puts))
    if not candidates:
        return None

    def payout(price):
        return (sum(v * max(price - k, 0.0) for k, v in calls.items()) +
                sum(v * max(k - price, 0.0) for k, v in puts.items()))
    return min(candidates, key=lambda price: (payout(price), abs(price - spot)))


def fetch_price_cache(start="2026-04-01", end="2026-08-12"):
    """Fetch bounded underlying daily OHLC from London only."""
    sys.path.insert(0, str(REPO / "scripts"))
    from lse_client import LSE
    client = LSE()
    payload = {"src": "lse", "start": start, "end": end, "symbols": {}}
    for sym in SYMS:
        rows = client.candles(sym, timeframe="1d", start=start, end=end,
                              limit=5000, order="asc")
        payload["symbols"][sym] = rows
    PRICE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PRICE_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    tmp.replace(PRICE_CACHE)
    return payload


def load_prices():
    out = {}
    cache = json.loads(PRICE_CACHE.read_text())
    if cache.get("src") != "lse":
        raise RuntimeError("underlying cache is not declared src=lse")
    for sym, rows in (cache.get("symbols") or {}).items():
        parsed = {}
        for row in rows:
            stamp = row.get("ts") or row.get("timestamp")
            day = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).date()
            parsed[day] = tuple(float(row[key]) for key in ("open", "high", "low", "close"))
        out[sym] = parsed
    for path in RAW.glob("stocks_*_1d.parquet"):
        sym = path.name.split("_")[1]
        frame = pd.read_parquet(path)
        rows = {}
        for row in frame.itertuples(index=False):
            day = row.ts.date()
            rows[day] = (float(row.open), float(row.high), float(row.low), float(row.close))
        out[sym] = rows
    return out


def expiry_levels(frame, spot, day, expiry):
    """Fit both disclosed proxies to exactly one expiry; return diagnostics too."""
    selected = frame[frame.expiry == expiry]
    if selected.empty:
        return None, None, 0, 0, 0
    mm = volume_pain(selected, spot)
    delta_net = gamma_gross = 0.0
    strikes, iv_rows, iv_ok = [], 0, 0
    t = max((expiry - day).days / 365.0, 1.0 / 365.0)
    greek_rows = selected[(selected.strike >= 0.70 * spot) &
                          (selected.strike <= 1.30 * spot)]
    for row in greek_rows.itertuples(index=False):
        iv_rows += 1
        got = implied_greeks(spot, float(row.strike), t, float(row.close), row.opt_type)
        if got is None:
            continue
        delta, gamma, _iv = got
        vol = float(row.volume) * 100.0
        delta_net += delta * vol
        gamma_gross += gamma * vol
        strikes.append(float(row.strike))
        iv_ok += 1
    neutral = spot - delta_net / gamma_gross if gamma_gross > 0 and strikes else None
    if neutral is not None and not (min(strikes) <= neutral <= max(strikes)):
        neutral = None
    return neutral, mm, len(selected), iv_rows, iv_ok


def make_levels(sym, prices, diag):
    path = RAW / f"options_{sym}_1d.parquet"
    if not path.exists() or sym not in prices:
        diag[sym] = {"state": "MISSING", "why": "options parquet or underlying daily bars absent"}
        return []
    frame = pd.read_parquet(path, columns=["ts", "expiry", "opt_type", "strike", "close", "volume"])
    frame["date"] = frame.ts.dt.date
    frame["expiry"] = frame.expiry.map(lambda x: x if isinstance(x, dt.date) else x.date())
    frame = frame[frame.volume > 0]
    records, iv_rows, iv_ok = [], 0, 0
    for day, day_frame in frame.groupby("date", sort=True):
        px = prices[sym].get(day)
        if not px:
            continue
        spot = px[3]
        active = sorted(expiry for expiry in day_frame.expiry.unique() if expiry > day)
        if not active:
            continue
        daily_expiry, weekly_expiry = active[0], next_friday(day)
        daily = expiry_levels(day_frame, spot, day, daily_expiry)
        weekly = expiry_levels(day_frame, spot, day, weekly_expiry)
        iv_rows += daily[3] + weekly[3]
        iv_ok += daily[4] + weekly[4]
        records.append({"symbol": sym, "date": day, "spot": spot,
                        "daily_expiry": daily_expiry, "weekly_expiry": weekly_expiry,
                        "wdn_daily": daily[0], "mm_top_daily": daily[1],
                        "wdn_weekly": weekly[0], "mm_top_weekly": weekly[1],
                        "daily_contracts": daily[2], "weekly_contracts": weekly[2]})
    diag[sym] = {"state": "OK", "dates": len(records), "iv_rows": iv_rows,
                 "iv_solved": iv_ok, "iv_solve_pct": round(100 * iv_ok / iv_rows, 2) if iv_rows else 0}
    return records


def observations(records, prices, key):
    out = []
    by_sym = {}
    for row in records:
        by_sym.setdefault(row["symbol"], []).append(row)
    for sym, rows in by_sym.items():
        days = sorted(prices[sym])
        pos = {day: i for i, day in enumerate(days)}
        for row in rows:
            level = row[key]
            i = pos.get(row["date"])
            if level is None or i is None or i + 1 >= len(days):
                continue
            next_day = days[i + 1]
            opn, high, low, close = prices[sym][next_day]
            spot = row["spot"]
            null_level = 2.0 * spot - level
            hit = low <= level <= high
            null_hit = low <= null_level <= high
            dist_entry = abs(level - opn)
            barrier = None
            if dist_entry / opn >= 0.0005:
                direction = 1 if level > opn else -1
                target_hit = high >= level if direction > 0 else low <= level
                stop = opn - direction * dist_entry
                stop_hit = low <= stop if direction > 0 else high >= stop
                barrier = -1 if target_hit and stop_hit else 1 if target_hit else -1 if stop_hit else 0
            out.append({"symbol": sym, "date": row["date"], "next_date": next_day,
                        "level": level, "spot": spot,
                        "distance_pct": abs(level - spot) / spot * 100.0,
                        "hit": int(hit), "null_hit": int(null_hit), "barrier": barrier})
    return out


def wilson_lb(wins, n, z=1.96):
    if n <= 0:
        return None
    p = wins / n
    den = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / den


def effective_n(rows, field="hit"):
    by_date = {}
    for row in rows:
        by_date.setdefault(row["date"], []).append(row[field])
    n, k = len(rows), len(by_date)
    if n <= 1 or k <= 1:
        return float(n), 0.0
    p = sum(row[field] for row in rows) / n
    total = p * (1 - p)
    within = sum(sum((x - sum(v) / len(v)) ** 2 for x in v) for v in by_date.values()) / n
    rho = max(0.0, min(1.0, (total - within) / total)) if total > 0 else 0.0
    mbar = n / k
    return n / (1 + (mbar - 1) * rho), rho


def exact_sign_p(rows):
    by_date = {}
    for row in rows:
        by_date.setdefault(row["date"], []).append(row["hit"] - row["null_hit"])
    pos = neg = 0
    for vals in by_date.values():
        avg = sum(vals) / len(vals)
        pos += avg > 0
        neg += avg < 0
    n = pos + neg
    if not n:
        return 1.0, pos, neg
    tail = sum(math.comb(n, i) for i in range(0, min(pos, neg) + 1)) / (2 ** n)
    return min(1.0, 2 * tail), pos, neg


def stats(rows, threshold):
    use = [row for row in rows if row["distance_pct"] <= threshold]
    n = len(use)
    neff, rho = effective_n(use)
    hit = sum(row["hit"] for row in use)
    null = sum(row["null_hit"] for row in use)
    p, pos, neg = exact_sign_p(use)
    resolved = [row["barrier"] for row in use if row["barrier"] in (-1, 1)]
    wins = sum(x == 1 for x in resolved)
    lb = wilson_lb(wins, len(resolved))
    return {"threshold_pct": threshold, "n": n,
            "date_clusters": len({row["date"] for row in use}),
            "effective_n": round(neff, 2), "intra_date_rho": round(rho, 4),
            "touch_rate": round(hit / n, 4) if n else None,
            "matched_null_rate": round(null / n, 4) if n else None,
            "touch_edge": round((hit - null) / n, 4) if n else None,
            "cluster_sign_p": round(p, 6), "positive_dates": pos, "negative_dates": neg,
            "barrier_resolved": len(resolved),
            "barrier_win_rate": round(wins / len(resolved), 4) if resolved else None,
            "barrier_wilson_lb": round(lb, 4) if lb is not None else None,
            "barrier_expectancy_lb_r": round(2 * lb - 1, 4) if lb is not None else None}


def bh_fdr(cells, alpha=0.05):
    ranked = sorted(enumerate(cells), key=lambda x: x[1]["cluster_sign_p"])
    cutoff = -1
    for rank, (_idx, cell) in enumerate(ranked, 1):
        if cell["cluster_sign_p"] <= alpha * rank / len(cells):
            cutoff = rank
    passed = set(idx for rank, (idx, _cell) in enumerate(ranked, 1) if rank <= cutoff)
    for idx, cell in enumerate(cells):
        cell["bh_fdr_05"] = idx in passed


def audit(indicator, rows):
    dates = sorted({row["date"] for row in rows})
    cut = max(1, int(len(dates) * 0.60))
    split_date = dates[cut - 1] if dates else None
    train = [row for row in rows if split_date and row["date"] <= split_date]
    oos = [row for row in rows if split_date and row["date"] > split_date]
    grid = [stats(train, threshold) for threshold in THRESHOLDS]
    bh_fdr(grid)
    eligible = [cell for cell in grid if cell["n"] >= 20]
    chosen = max(eligible, key=lambda cell: (cell["touch_edge"], -cell["threshold_pct"])) if eligible else None
    frozen = chosen["threshold_pct"] if chosen else None
    oos_stats = stats(oos, frozen) if frozen is not None else None
    enough = (len({row["date"] for row in train}) >= 60 and
              len({row["date"] for row in oos}) >= 40)
    proven = bool(enough and chosen and (chosen["touch_edge"] or 0) > 0 and
                  chosen["bh_fdr_05"] and oos_stats and
                  (oos_stats["touch_edge"] or 0) > 0 and
                  (oos_stats["barrier_expectancy_lb_r"] or -1) > 0)
    if not chosen or (chosen["touch_edge"] or 0) <= 0:
        preliminary = "NO_POSITIVE_TRAIN_EDGE"
    elif not chosen["bh_fdr_05"]:
        preliminary = "TRAIN_EDGE_NOT_SIGNIFICANT"
    elif not oos_stats or (oos_stats["barrier_expectancy_lb_r"] or -1) <= 0:
        preliminary = "NO_TRADABLE_OOS_LOWER_BOUND"
    else:
        preliminary = "PASSES_POINT_CHECKS_AWAITING_COVERAGE"
    return {"indicator": indicator, "hypothesis": "next-session magnet touch",
            "split_date": split_date.isoformat() if split_date else None,
            "train_dates": len({row["date"] for row in train}),
            "oos_dates": len({row["date"] for row in oos}),
            "train_grid": grid, "selected_train": chosen, "oos_frozen": oos_stats,
            "preliminary": preliminary,
            "verdict": "PROVEN" if proven else "DATA_INSUFFICIENT" if not enough else "REJECTED_OOS"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=str(OUT_JSON))
    parser.add_argument("--md", default=str(OUT_MD))
    parser.add_argument("--fetch-prices", action="store_true")
    args = parser.parse_args()
    if args.fetch_prices or not PRICE_CACHE.exists():
        fetch_price_cache()
    prices = load_prices()
    diag, levels = {}, []
    for sym in SYMS:
        levels.extend(make_levels(sym, prices, diag))
    observation_sets = {
        "DN_DAY_VOL": observations(levels, prices, "wdn_daily"),
        "DN_WEEK_VOL": observations(levels, prices, "wdn_weekly"),
        "MM_TOP_DAY_VOL": observations(levels, prices, "mm_top_daily"),
        "MM_TOP_WEEK_VOL": observations(levels, prices, "mm_top_weekly"),
    }
    result = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "LSE daily option candles + LSE REST daily underlying OHLC",
        "method": {
            "snapshot": "end-of-day; day=nearest expiry strictly after snapshot date; week=first Friday strictly after snapshot date",
            "entry": "next session open",
            "outcome": "next-session level touch; same-distance mirror around prior close is matched null",
            "barrier": "target=level; symmetric 1R stop from next open; same-day target+stop tie=failure; timeout=null",
            "split": "first 60% unique chronological dates train; final 40% one-shot OOS",
            "grid": list(THRESHOLDS), "multiple_testing": "BH-FDR 5% on train cells",
            "cluster_control": "date-cluster sign test and design-effect effective n",
            "wdn_history_limit": "daily closes lack model Greeks; IV/delta/gamma reconstructed from last option close, r=4%, strikes 70-130% spot",
            "mm_history_limit": "volume-weighted payout minimizer; not OI max pain or proprietary MM profit",
        },
        "coverage": diag, "level_rows": len(levels),
        "observations": {key: len(rows) for key, rows in observation_sets.items()},
        "audits": [audit(key, rows) for key, rows in observation_sets.items()],
        "promotion_gate": "60 train dates + 40 untouched OOS dates + BH-FDR train + positive OOS matched-null edge + positive OOS Wilson-LB expectancy",
        "proprietary_replication": False,
    }
    out_json = Path(args.json); out_md = Path(args.md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, default=str) + "\n")
    lines = ["# Dealer-neutral / MM top-profit daily + weekly chronological audit", "",
             f"Generated: {result['generated']}", "",
             "These are London volume-only proxies, not Net Dealer, PML, OI max pain, or a market-maker book.", "",
             "## Coverage", ""]
    for sym, row in diag.items():
        lines.append(f"- {sym}: {row}")
    for audit_row in result["audits"]:
        lines += ["", f"## {audit_row['indicator']}", "",
                  f"- Verdict: **{audit_row['verdict']}**",
                  f"- Preliminary: **{audit_row['preliminary']}**",
                  f"- Train/OOS dates: {audit_row['train_dates']} / {audit_row['oos_dates']}",
                  f"- Frozen train cell: `{audit_row['selected_train']}`",
                  f"- Frozen OOS: `{audit_row['oos_frozen']}`"]
    lines += ["", "## Guard", "", result["promotion_gate"], ""]
    out_md.write_text("\n".join(lines))
    print(json.dumps({"json": str(out_json), "md": str(out_md),
                      "observations": result["observations"],
                      "verdicts": {x["indicator"]: x["verdict"] for x in result["audits"]}}, indent=2))


if __name__ == "__main__":
    main()
