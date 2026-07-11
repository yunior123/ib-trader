#!/usr/bin/env python3
"""Real top-gainer universe sources — SOLO REALTIME (Finviz Elite export).
Yahoo screener y Finviz free scrape ELIMINADOS 2026-07-10 (orden Yunior:
"yahoo or delayed shit is forbidden").

Providers:
  1) Finviz Elite topgainers (realtime, FINVIZ_AUTH)
  2) Finviz Elite new-high breakouts (realtime, tag breakout=True)
Rows: {sym, price, gain_pct, premarket_pct, volume, market_cap, country, src}.
The scanner then applies the selectivity filters (penny range, liquidity,
skip parabolic blow-offs) — the junk $0.00 +900% names get dropped there.
"""
import csv
import io
import os
import urllib.request
import warnings

warnings.filterwarnings("ignore")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    for name in ("llm.env", "feeds.env"):
        p = os.path.join(_REPO, name)
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()


def _finviz_elite_export(signal, max_price=10.0, auth=None, src="finviz_elite",
                         breakout=False):
    """Shared Finviz Elite export fetch for any screener signal (paid; needs
    auth token in FINVIZ_AUTH). Returns [] if no token or on error."""
    auth = auth or os.environ.get("FINVIZ_AUTH") or os.environ.get("FINVIZ_API_KEY")
    if not auth:
        return []
    price_f = "sh_price_u10" if max_price >= 10 else ("sh_price_u5" if max_price >= 5 else "sh_price_u1")
    # NOTE: use the /export/screener path. The legacy export.ashx 301-redirects to
    # an EMPTY body for clients that don't follow redirects. urllib follows 301 by
    # default, but the direct path avoids the round-trip entirely.
    url = (f"https://elite.finviz.com/export/screener?v=111&s={signal}"
           f"&f={price_f}&o=-change&auth={auth}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        out = []
        for row in csv.DictReader(io.StringIO(text)):
            try:
                out.append({"sym": row["Ticker"].strip(),
                            "price": float(row.get("Price", 0) or 0),
                            "gain_pct": float(str(row.get("Change", "0")).replace("%", "") or 0),
                            "premarket_pct": 0.0,
                            "volume": float(str(row.get("Volume", "0")).replace(",", "") or 0),
                            # país de la empresa (v=111 lo trae): USA priorizado
                            # en el score (orden Yunior 2026-07-10)
                            "country": str(row.get("Country", "") or "").strip(),
                            "market_cap": 0.0, "src": src, "breakout": breakout})
            except Exception:
                continue
        return out
    except Exception as e:
        print(f"finviz_elite err ({signal}) {repr(e)[:100]}")
        return []


def finviz_elite_gainers(max_price=10.0, auth=None):
    """REAL-TIME top gainers via Finviz Elite export API (paid; needs auth token).
    This is the realtime source Yunior wants. Set FINVIZ_AUTH in llm.env/feeds.env
    (the 'auth=' value from an Elite export URL). Returns [] if no token."""
    return _finviz_elite_export("ta_topgainers", max_price, auth,
                                src="finviz_elite_realtime")


def finviz_elite_breakouts(max_price=10.0, auth=None):
    """REAL-TIME breakouts via Finviz Elite: names making a NEW HIGH (the
    classic breakout screen). Yunior's order 2026-07-09: use topgainers AND
    breakout screens together. Rows are tagged breakout=True so the scanner
    scores them with a breakout bonus and a relaxed min-gain gate."""
    return _finviz_elite_export("ta_newhigh", max_price, auth,
                                src="finviz_elite_breakout", breakout=True)


# yahoo_penny_gainers / yahoo_premarket_gainers / finviz_gainers BORRADOS
# (Yunior 2026-07-10: "yahoo or delayed shit is forbidden")


def top_gainer_universe(premarket=False, max_price=10.0, favorites=None):
    """Merged, deduped candidate rows (best gain kept per symbol).
    SOLO Finviz Elite REALTIME (topgainers + breakouts). Yahoo screener
    (~15m delayed) y Finviz free scrape ELIMINADOS — Yunior 2026-07-10:
    'yahoo or delayed shit is forbidden'. Sin FINVIZ_AUTH el scanner grita
    en vez de degradarse en silencio a datos viejos."""
    rows = finviz_elite_gainers(max_price)       # REALTIME (paid, FINVIZ_AUTH)
    rows += finviz_elite_breakouts(max_price)
    if not rows:
        print("[sources] SIN DATOS REALTIME (FINVIZ_AUTH caido/ausente). "
              "Fuentes delayed PROHIBIDAS — universo vacio a proposito.")
    best = {}
    for r in rows:
        s = r["sym"]
        key = max(r.get("premarket_pct", 0), r.get("gain_pct", 0))
        if s not in best or key > max(best[s].get("premarket_pct", 0), best[s].get("gain_pct", 0)):
            # no perder el país conocido si la fila ganadora viene de una
            # fuente sin columna Country (Yahoo)
            if not r.get("country") and best.get(s, {}).get("country"):
                r = {**r, "country": best[s]["country"]}
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
