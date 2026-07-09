#!/usr/bin/env python3
"""Real top-gainer universe sources. Multiple providers, merged + deduped, so a
single provider outage never blinds the scanner. Penny-preferred.

Providers:
  1) Yahoo custom screener (yfinance EquityQuery) — ranked penny gainers with
     price/%chg/volume/marketcap AND premarket fields. Primary; maintained.
  2) Finviz top-gainers screener (via finvizfinance if installed) — secondary.
Both return dicts: {sym, price, gain_pct, premarket_pct, volume, market_cap, src}.
The scanner then applies the selectivity filters (penny range, liquidity,
skip parabolic blow-offs) — the junk $0.00 +900% names get dropped there.
"""
import os
import warnings

warnings.filterwarnings("ignore")


def yahoo_penny_gainers(max_price=10.0, min_change=4.0, min_vol=300_000, size=100):
    try:
        import yfinance as yf
        from yfinance import EquityQuery as Q
        q = Q('and', [
            Q('lt', ['intradayprice', max_price]),
            Q('gt', ['percentchange', min_change]),
            Q('gt', ['dayvolume', min_vol]),
            Q('eq', ['region', 'us']),
        ])
        r = yf.screen(q, sortField='percentchange', sortAsc=False, size=size)
        out = []
        for x in r.get("quotes", []):
            sym = x.get("symbol")
            if not sym or "." in sym:
                continue
            out.append({
                "sym": sym,
                "price": float(x.get("regularMarketPrice") or 0),
                "gain_pct": float(x.get("regularMarketChangePercent") or 0),
                "premarket_pct": float(x.get("preMarketChangePercent") or 0),
                "volume": float(x.get("regularMarketVolume") or 0),
                "market_cap": float(x.get("marketCap") or 0),
                "src": "yahoo_screen",
            })
        return out
    except Exception as e:
        print(f"yahoo_penny_gainers err {repr(e)[:100]}")
        return []


def yahoo_premarket_gainers(max_price=10.0, size=100):
    """Premarket movers (for the 6 AM run before the open). Falls back to the
    regular screen but re-ranks by premarket % when available."""
    rows = yahoo_penny_gainers(max_price=max_price, min_change=0.0, size=size)
    pm = [r for r in rows if r.get("premarket_pct")]
    pm.sort(key=lambda r: r["premarket_pct"], reverse=True)
    return pm or rows


def finviz_gainers(max_price=10.0):
    """Finviz Top Gainers signal, price-filtered. Optional (needs finvizfinance)."""
    try:
        from finvizfinance.screener.overview import Overview
        fv = Overview()
        price_filter = "Under $10" if max_price >= 10 else "Under $5"
        fv.set_filter(signal="Top Gainers", filters_dict={"Price": price_filter})
        df = fv.screener_view()
        out = []
        if df is not None and len(df):
            for _, r in df.iterrows():
                try:
                    out.append({"sym": str(r["Ticker"]),
                                "price": float(r.get("Price", 0) or 0),
                                "gain_pct": float(str(r.get("Change", "0")).strip("%") or 0),
                                "premarket_pct": 0.0,
                                "volume": float(str(r.get("Volume", "0")).replace(",", "") or 0),
                                "market_cap": 0.0, "src": "finviz"})
                except Exception:
                    continue
        return out
    except Exception:
        return []   # finvizfinance not installed / blocked -> silently skip


def top_gainer_universe(premarket=False, max_price=10.0, favorites=None):
    """Merged, deduped candidate rows (best gain kept per symbol)."""
    rows = []
    rows += (yahoo_premarket_gainers(max_price) if premarket
             else yahoo_penny_gainers(max_price=max_price))
    rows += finviz_gainers(max_price)
    best = {}
    for r in rows:
        s = r["sym"]
        key = max(r.get("premarket_pct", 0), r.get("gain_pct", 0))
        if s not in best or key > max(best[s].get("premarket_pct", 0), best[s].get("gain_pct", 0)):
            best[s] = r
    for f in (favorites or []):
        best.setdefault(f, {"sym": f, "price": 0, "gain_pct": 0, "premarket_pct": 0,
                            "volume": 0, "market_cap": 0, "src": "favorite"})
    return list(best.values())


if __name__ == "__main__":
    import sys
    pm = "--premarket" in sys.argv
    u = top_gainer_universe(premarket=pm)
    u.sort(key=lambda r: max(r.get("premarket_pct", 0), r.get("gain_pct", 0)), reverse=True)
    print(f"{len(u)} candidates ({'premarket' if pm else 'regular'}):")
    for r in u[:25]:
        print(f"  {r['sym']:6s} ${r['price']:8.3f} reg +{r['gain_pct']:6.1f}% "
              f"pm +{r['premarket_pct']:6.1f}% vol {r['volume']:,.0f} src {r['src']}")
