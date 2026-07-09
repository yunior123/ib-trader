#!/usr/bin/env python3
"""6 AM daily research — pick today's selective top-gainer penny candidates.

Yunior's friend checks premarket movers + prior-day explosions every 6 AM and
got rich being SELECTIVE. This reproduces that: build a candidate list, score it,
write the watchlist the alert bot + Claude session trade from.

Pipeline:
  1) Universe: Finnhub US symbols filtered to plausible penny names, plus any
     tickers passed on argv, plus the fleet favorites.
  2) For each: Finnhub /quote (premarket-aware) -> price, % vs prev close,
     day range. yfinance fills market cap + avg volume + prior-day move.
  3) FILTERS (the selectivity):
       - price in [PENNY_MIN, PENNY_MAX]           (penny stocks)
       - premarket/day change >= MIN_GAIN_PCT      (it's actually moving)
       - dollar-volume >= MIN_DOLLAR_VOL           (liquid enough to exit)
       - not a prior-day parabolic blowoff (avoid buying the top of a +300% day)
  4) SCORE = gain% weighted by liquidity, penalized for gap-too-extended.
  5) Optionally enrich the top N with a TradingAgents research note (local repo).
  6) Write data/topgainer/watchlist_YYYYMMDD.json + push a summary to phone.

Run:  venv/bin/python topgainer/scanner.py            (auto universe)
      venv/bin/python topgainer/scanner.py GNS KOD ... (explicit tickers)
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from price import finnhub_quote, yahoo_last, _load_finnhub_key  # noqa: E402
from sources import top_gainer_universe  # noqa: E402
import research  # noqa: E402

PENNY_MIN = float(os.getenv("SCAN_PENNY_MIN", "0.10"))
PENNY_MAX = float(os.getenv("SCAN_PENNY_MAX", "8.0"))
MIN_GAIN_PCT = float(os.getenv("SCAN_MIN_GAIN", "5.0"))
MIN_DOLLAR_VOL = float(os.getenv("SCAN_MIN_DOLLARVOL", "1_000_000".replace("_", "")))
BLOWOFF_PCT = float(os.getenv("SCAN_BLOWOFF", "150.0"))   # skip already-parabolic
TOP_N = int(os.getenv("SCAN_TOPN", "8"))
FAVORITES = ["GNS", "KOD", "DRAM", "NOK", "SPCX"]


def prior_day_move(sym):
    try:
        import yfinance as yf
        hist = yf.Ticker(sym).history(period="5d", interval="1d")
        if len(hist) >= 2:
            return (hist.Close.iloc[-1] - hist.Close.iloc[-2]) / hist.Close.iloc[-2] * 100
    except Exception:
        pass
    return 0.0


def evaluate(row):
    """Apply the selectivity filters to a real top-gainer source row. The junk
    (sub-penny, illiquid, +900% parabolic pumps) is dropped here."""
    sym = row["sym"]
    px = row.get("price") or 0
    gain = max(row.get("premarket_pct", 0) or 0, row.get("gain_pct", 0) or 0)
    if px <= 0:
        q = finnhub_quote(sym) or yahoo_last(sym)   # favorites arrive with px 0
        if not q:
            return None
        px = q["price"]
        gain = gain or ((px - (q.get("prev_close") or px)) / (q.get("prev_close") or px) * 100)
    if not (PENNY_MIN <= px <= PENNY_MAX):
        return None
    if gain < MIN_GAIN_PCT:
        return None
    vol = row.get("volume", 0) or 0
    dollar_vol = vol * px
    if dollar_vol and dollar_vol < MIN_DOLLAR_VOL:
        return None
    prior = prior_day_move(sym)
    if prior >= BLOWOFF_PCT:      # already blew off yesterday -> skip (selectivity)
        return None
    liq = min(1.0, dollar_vol / (MIN_DOLLAR_VOL * 10)) if dollar_vol else 0.3
    extended_pen = max(0.0, (prior - 40) / 100)
    score = gain * (0.5 + liq) - extended_pen * 10
    return {"sym": sym, "price": round(px, 4), "gain_pct": round(gain, 2),
            "prior_day_pct": round(prior, 2), "market_cap": row.get("market_cap", 0),
            "dollar_vol": round(dollar_vol), "score": round(score, 2), "src": row.get("src")}


def main():
    explicit = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
    premarket = "--premarket" in sys.argv
    if explicit:
        universe = [{"sym": s, "price": 0, "gain_pct": 0, "premarket_pct": 0,
                     "volume": 0, "market_cap": 0, "src": "explicit"} for s in explicit]
    else:
        universe = top_gainer_universe(premarket=premarket, max_price=PENNY_MAX,
                                       favorites=FAVORITES)
    print(f"scanning {len(universe)} real top-gainer rows "
          f"({'premarket' if premarket else 'regular'})...", file=sys.stderr)
    hits = []
    for row in universe:
        r = evaluate(row)
        if r:
            hits.append(r)
            print(f"  candidate {r['sym']} +{r['gain_pct']}% ${r['price']} score {r['score']}",
                  file=sys.stderr)
    hits.sort(key=lambda x: x["score"], reverse=True)
    top = hits[:TOP_N]

    # MANDATORY TradingAgents research on the finalists (6 AM job sets TA_RESEARCH=1).
    date_str = state.datetime.now().astimezone().strftime("%Y-%m-%d")
    top = research.enrich_candidates(top, date_str)
    if os.getenv("TA_RESEARCH") == "1":
        # research is mandatory: drop finalists TradingAgents did not bless as BUY
        vetted = [c for c in top if c.get("ta_action") == "BUY"]
        print(f"TradingAgents: {len(vetted)}/{len(top)} finalists rated BUY", file=sys.stderr)
        top = vetted or top   # if TA blessed none, keep list but flagged (Claude sees ta_action)

    data = {"date": state.now_iso(), "generated_by": "scanner",
            "premarket": premarket, "research_mandatory": os.getenv("TA_RESEARCH") == "1",
            "filters": {"penny": [PENNY_MIN, PENNY_MAX], "min_gain": MIN_GAIN_PCT,
                        "min_dollar_vol": MIN_DOLLAR_VOL, "blowoff": BLOWOFF_PCT},
            "candidates": top}
    p = state.write_watchlist(data)
    print(f"wrote {p}: {len(top)} candidates", file=sys.stderr)
    for c in top:
        print(f"  {c['sym']:6s} +{c['gain_pct']:6.2f}% ${c['price']:8.4f} "
              f"score {c['score']:6.2f} $vol {c['dollar_vol']:,}")
    # phone summary
    if top:
        names = ", ".join(f"{c['sym']}+{c['gain_pct']:.0f}%" for c in top[:5])
        try:
            import subprocess
            subprocess.Popen(["curl", "-s", "-m", "10", "-X", "POST",
                              "https://ntfy.sh/yunior-daily-brief-2026",
                              "-H", "Title: Top gainers 6AM", "-H", "Tags: chart",
                              "-d", f"Candidatos hoy: {names}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


if __name__ == "__main__":
    main()
