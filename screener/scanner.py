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
  6) Write data/screener/watchlist_YYYYMMDD.json + push a summary to phone.

Run:  venv/bin/python screener/scanner.py            (auto universe)
      venv/bin/python screener/scanner.py GNS KOD ... (explicit tickers)
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
from price import finnhub_quote, alpaca_spread, _load_finnhub_key  # noqa: E402
from sources import top_gainer_universe  # noqa: E402
import research  # noqa: E402

PENNY_MIN = float(os.getenv("SCAN_PENNY_MIN", "0.10"))
PENNY_MAX = float(os.getenv("SCAN_PENNY_MAX", "8.0"))
MIN_GAIN_PCT = float(os.getenv("SCAN_MIN_GAIN", "5.0"))
MIN_DOLLAR_VOL = float(os.getenv("SCAN_MIN_DOLLARVOL", "1_000_000".replace("_", "")))
BLOWOFF_PCT = float(os.getenv("SCAN_BLOWOFF", "150.0"))   # skip already-parabolic (prior day)
MAX_INTRADAY_GAIN = float(os.getenv("SCAN_MAX_GAIN", "40.0"))  # skip already up >40% today:
# too extended to chase, and LULD volatility-halt risk means orders won't even fill
TOP_N = int(os.getenv("SCAN_TOPN", "8"))
# spread gate (Yunior 2026-07-10): wide bid-ask = illiquid trap, skip it.
# One tick of spread is unavoidable on pennies, so <=1 cent always passes.
MAX_SPREAD_PCT = float(os.getenv("SCAN_MAX_SPREAD", "3.0"))
# selectividad extra (Yunior 2026-07-15 "try making finviz more selective,
# like > 50 millions in market cap, etc"): mcap minimo en $M. Finviz export
# trae Market Cap en millones; 0/desconocido NO pasa (estricto a proposito —
# los shells sin mcap reportado son la trampa clasica de los pumps).
MIN_MCAP_M = float(os.getenv("SCAN_MIN_MCAP", "50.0"))
FAVORITES = ["GNS", "KOD", "DRAM", "NOK", "SPCX"]


def _mcap_m(row):
    """Market cap en $M de la fila (Finviz export la trae en millones)."""
    try:
        return float(row.get("market_cap") or 0)
    except Exception:
        return 0.0


def prior_day_move(sym):
    """% move of the PRIOR session. Alpaca daily bars (Yahoo PROHIBIDO —
    Yunior 2026-07-10 'yahoo or delayed shit is forbidden')."""
    try:
        import json
        import urllib.request
        from price import _load_alpaca_keys
        key, sec = _load_alpaca_keys()
        if not key:
            return 0.0
        from datetime import datetime, timedelta, timezone
        start = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        req = urllib.request.Request(
            f"https://data.alpaca.markets/v2/stocks/{sym}/bars"
            f"?timeframe=1Day&limit=10&feed=iex&start={start}",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=6) as r:
            bars = json.load(r).get("bars") or []
        if len(bars) >= 2:
            c1, c0 = float(bars[-1]["c"]), float(bars[-2]["c"])
            if c0 > 0:
                return (c1 - c0) / c0 * 100
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
        q = finnhub_quote(sym)   # favorites arrive with px 0; Finnhub only (no Yahoo)
        if not q:
            return None
        px = q["price"]
        gain = gain or ((px - (q.get("prev_close") or px)) / (q.get("prev_close") or px) * 100)
    if not (PENNY_MIN <= px <= PENNY_MAX):
        return None
    if gain < MIN_GAIN_PCT:
        return None
    if gain > MAX_INTRADAY_GAIN:   # already too extended today -> chase/halt risk, skip
        return None
    vol = row.get("volume", 0) or 0
    dollar_vol = vol * px
    if dollar_vol and dollar_vol < MIN_DOLLAR_VOL:
        return None
    # mcap >= $50M (Yunior 2026-07-15): fuera micro-shells; explicit/argv salta
    # el gate (el humano ya eligio el ticker a mano)
    if row.get("src") != "explicit" and _mcap_m(row) < MIN_MCAP_M:
        return None
    prior = prior_day_move(sym)
    if prior >= BLOWOFF_PCT:      # already blew off yesterday -> skip (selectivity)
        return None
    liq = min(1.0, dollar_vol / (MIN_DOLLAR_VOL * 10)) if dollar_vol else 0.3
    # volatility (Yunior 2026-07-10: prefer gainers with liquidity AND volatility):
    # intraday range as % of price, from the live quote. A mover with a wide,
    # active range gives the breakout room to pay; a flat drifter does not.
    range_pct = 0.0
    q = finnhub_quote(sym)
    if q and q.get("high") and q.get("low") and px > 0:
        range_pct = max(0.0, (q["high"] - q["low"]) / px * 100)
    vola = min(1.0, range_pct / 15.0)      # 15%+ intraday range = full marks
    # bid-ask spread gate + bonus (only survivors reach here — few API calls)
    spread_pct = None
    sp = alpaca_spread(sym)
    if sp:
        spread_pct = sp["spread_pct"]
        one_tick = (sp["ask"] - sp["bid"]) <= 0.011   # min increment, unavoidable
        if spread_pct > MAX_SPREAD_PCT and not one_tick:
            return None                    # can't exit cleanly -> not a candidate
    tight = 1.0 - min(spread_pct, 5.0) / 10.0 if spread_pct is not None else 0.85
    # US priority (Yunior 2026-07-10 "the top screener should give priority to
    # us companies"): país de la columna Country de Finviz. Extranjero (los
    # pumps chinos de reverse-split, la trampa clásica) baja fuerte; país
    # desconocido (fila solo-Yahoo) apenas.
    country = str(row.get("country") or "").strip()
    us_mult = 1.0 if country == "USA" else (0.9 if not country else 0.6)
    extended_pen = max(0.0, (prior - 40) / 100)
    score = gain * (0.4 + 0.6 * liq) * (0.7 + 0.6 * vola) * tight * us_mult \
        - extended_pen * 10
    return {"sym": sym, "price": round(px, 4), "gain_pct": round(gain, 2),
            "prior_day_pct": round(prior, 2), "market_cap": row.get("market_cap", 0),
            "dollar_vol": round(dollar_vol), "range_pct": round(range_pct, 2),
            "spread_pct": spread_pct, "country": country or None,
            "score": round(score, 2), "src": row.get("src")}


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

    # MANDATORY TradingAgents research on the finalists — default ON for EVERY
    # scan (6AM and on-demand); opt out only with TA_RESEARCH=0 (Yunior 2026-07-09).
    ta_on = os.getenv("TA_RESEARCH", "1") != "0"
    date_str = state.datetime.now().astimezone().strftime("%Y-%m-%d")
    # carry over today's TA verdicts (rescan corre cada 15 min y reconstruye
    # los dicts desde cero — sin esto, re-vetea los mismos 3 nombres todo el
    # dia y los nuevos gainers nunca reciben research)
    prev = {c["sym"]: c for c in (state.read_watchlist() or {}).get("candidates", [])
            if c.get("ta_action")}
    for c in top:
        if c["sym"] in prev and not c.get("ta_action"):
            c["ta_action"] = prev[c["sym"]]["ta_action"]
            c["ta_note"] = prev[c["sym"]].get("ta_note", "")
    top = research.enrich_candidates(top, date_str)
    rejected = []
    if ta_on:
        # research is mandatory Y EXCLUYENTE (Yunior 2026-07-15 "only send
        # notifications on finviz trading agents selected candidates"): al
        # watchlist — que es lo que alerta screener_alert — SOLO entran los
        # BUY de TradingAgents. Cero fallback a la lista sin vetar.
        vetted = [c for c in top if c.get("ta_action") == "BUY"]
        rejected = [c for c in top if c.get("ta_action") != "BUY"]
        print(f"TradingAgents: {len(vetted)}/{len(top)} finalists rated BUY", file=sys.stderr)
        top = vetted

    # registro append-only de TODO lo escaneado (Yunior 2026-07-15 "u store
    # all signals... also finviz"): cada corrida deja hits crudos + veredictos
    # para la validacion de fin de dia, aunque el watchlist quede vacio.
    try:
        import json as _json
        day = state.datetime.now().astimezone().strftime("%Y%m%d")
        with open(os.path.join(state.BASE, f"scan_log_{day}.jsonl"), "a") as f:
            f.write(_json.dumps({"ts": state.now_iso(), "premarket": premarket,
                                 "raw_hits": hits, "ta_buy": top,
                                 "ta_rejected": rejected}) + "\n")
    except Exception as e:
        print(f"scan_log append fallo: {e}", file=sys.stderr)

    data = {"date": state.now_iso(), "generated_by": "scanner",
            "premarket": premarket, "research_mandatory": ta_on,
            "filters": {"penny": [PENNY_MIN, PENNY_MAX], "min_gain": MIN_GAIN_PCT,
                        "min_dollar_vol": MIN_DOLLAR_VOL, "blowoff": BLOWOFF_PCT,
                        "min_mcap_m": MIN_MCAP_M},
            "candidates": top}
    # OJO: los rechazados NO van al watchlist — screener_alert.cpp parsea TODOS
    # los "sym" del JSON y alertaria sobre ellos; quedan solo en scan_log_*.jsonl
    p = state.write_watchlist(data)
    print(f"wrote {p}: {len(top)} candidates", file=sys.stderr)
    for c in top:
        print(f"  {c['sym']:6s} +{c['gain_pct']:6.2f}% ${c['price']:8.4f} "
              f"score {c['score']:6.2f} $vol {c['dollar_vol']:,}")
    # Mac notification summary + espejo Desktop (solo candidatos TA-BUY)
    if top:
        names = ", ".join(f"{c['sym']}+{c['gain_pct']:.0f}%" for c in top[:5])
        state.notify_mac("Top gainers (TA BUY)", f"Candidatos hoy: {names}")


if __name__ == "__main__":
    main()
