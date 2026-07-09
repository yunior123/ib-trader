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

PENNY_MIN = float(os.getenv("SCAN_PENNY_MIN", "0.10"))
PENNY_MAX = float(os.getenv("SCAN_PENNY_MAX", "8.0"))
MIN_GAIN_PCT = float(os.getenv("SCAN_MIN_GAIN", "5.0"))
MIN_DOLLAR_VOL = float(os.getenv("SCAN_MIN_DOLLARVOL", "1_000_000".replace("_", "")))
BLOWOFF_PCT = float(os.getenv("SCAN_BLOWOFF", "150.0"))   # skip already-parabolic
TOP_N = int(os.getenv("SCAN_TOPN", "8"))
FAVORITES = ["GNS", "KOD", "DRAM", "NOK", "SPCX"]


def finnhub_movers():
    """Pull a candidate universe. Finnhub free tier has no movers endpoint, so we
    take the US symbol list once and let the per-name quote filter do the work.
    To stay fast/free we cap to a rotating slice unless SCAN_FULL=1."""
    key = _load_finnhub_key()
    if not key:
        return []
    try:
        import urllib.request
        import json
        url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={key}"
        with urllib.request.urlopen(url, timeout=15) as r:
            syms = json.load(r)
        names = [s["symbol"] for s in syms if s.get("type") == "Common Stock"
                 and s.get("symbol") and "." not in s["symbol"]]
        if os.getenv("SCAN_FULL") == "1":
            return names
        # rotating slice keeps free-tier rate limits sane; favorites always included
        cap = int(os.getenv("SCAN_SLICE", "600"))
        return names[:cap]
    except Exception as e:
        print(f"universe err {e}", file=sys.stderr)
        return []


def enrich_yahoo(sym):
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        fi = getattr(t, "fast_info", {}) or {}
        mc = fi.get("market_cap") or 0
        vol = fi.get("last_volume") or 0
        prev = fi.get("previous_close") or 0
        last = fi.get("last_price") or 0
        # prior-day move
        hist = t.history(period="5d", interval="1d")
        prior_move = 0.0
        if len(hist) >= 2:
            prior_move = (hist.Close.iloc[-1] - hist.Close.iloc[-2]) / hist.Close.iloc[-2] * 100
        return {"market_cap": float(mc or 0), "volume": float(vol or 0),
                "prev_close": float(prev or 0), "last": float(last or 0),
                "prior_move": float(prior_move)}
    except Exception:
        return {}


def evaluate(sym):
    q = finnhub_quote(sym) or yahoo_last(sym)
    if not q or q["price"] <= 0:
        return None
    px = q["price"]
    prev = q.get("prev_close") or 0
    gain = (px - prev) / prev * 100 if prev else 0.0
    if not (PENNY_MIN <= px <= PENNY_MAX):
        return None
    if gain < MIN_GAIN_PCT:
        return None
    y = enrich_yahoo(sym)
    dollar_vol = (y.get("volume", 0) or 0) * px
    prior = y.get("prior_move", 0)
    if dollar_vol and dollar_vol < MIN_DOLLAR_VOL:
        return None
    if prior >= BLOWOFF_PCT:      # already blew off yesterday -> skip (selectivity)
        return None
    # score: reward the move + liquidity, penalize being extended
    liq = min(1.0, dollar_vol / (MIN_DOLLAR_VOL * 10)) if dollar_vol else 0.3
    extended_pen = max(0.0, (prior - 40) / 100)
    score = gain * (0.5 + liq) - extended_pen * 10
    return {"sym": sym, "price": round(px, 4), "gain_pct": round(gain, 2),
            "prior_day_pct": round(prior, 2), "market_cap": y.get("market_cap", 0),
            "dollar_vol": round(dollar_vol), "score": round(score, 2)}


def main():
    explicit = [a.upper() for a in sys.argv[1:]]
    universe = explicit or (finnhub_movers() + FAVORITES)
    seen, uniq = set(), []
    for s in universe:
        if s not in seen:
            seen.add(s); uniq.append(s)
    print(f"scanning {len(uniq)} symbols...", file=sys.stderr)
    hits = []
    for i, s in enumerate(uniq):
        r = evaluate(s)
        if r:
            hits.append(r)
            print(f"  candidate {r['sym']} +{r['gain_pct']}% ${r['price']} score {r['score']}",
                  file=sys.stderr)
        if i % 100 == 0 and i:
            print(f"  ...{i}/{len(uniq)}", file=sys.stderr)
    hits.sort(key=lambda x: x["score"], reverse=True)
    top = hits[:TOP_N]
    data = {"date": state.now_iso(), "generated_by": "scanner",
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
