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


def _mcap_millions(raw):
    """Finviz export Market Cap viene en millones ("512.34") o vacio ("-")."""
    try:
        return float(str(raw).replace(",", ""))
    except Exception:
        return 0.0


def _finviz_elite_export(signal, max_price=10.0, auth=None, src="finviz_elite",
                         breakout=False, filters=None, price_cap=True):
    """Shared Finviz Elite export fetch for any screener signal (paid; needs
    auth token in FINVIZ_AUTH). Returns [] if no token or on error.
    filters: lista extra de codigos finviz (f=) que se suman al price cap.
    price_cap=False: sin filtro de precio penny (screens de calidad/no-penny)."""
    auth = auth or os.environ.get("FINVIZ_AUTH") or os.environ.get("FINVIZ_API_KEY")
    if not auth:
        return []
    fparts = list(filters or [])
    if price_cap:
        fparts.insert(0, "sh_price_u10" if max_price >= 10 else
                      ("sh_price_u5" if max_price >= 5 else "sh_price_u1"))
    sig = f"&s={signal}" if signal else ""
    fstr = f"&f={','.join(fparts)}" if fparts else ""
    # NOTE: use the /export/screener path. The legacy export.ashx 301-redirects to
    # an EMPTY body for clients that don't follow redirects. urllib follows 301 by
    # default, but the direct path avoids the round-trip entirely.
    url = (f"https://elite.finviz.com/export/screener?v=111{sig}"
           f"{fstr}&o=-change&auth={auth}")
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
                            "market_cap": _mcap_millions(row.get("Market Cap", 0)),
                            "src": src, "breakout": breakout})
            except Exception:
                continue
        return out
    except Exception as e:
        print(f"finviz_elite err ({signal or ','.join(fparts)}) {repr(e)[:100]}")
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


# --------------------------------------------------------------------------
# SCREENS adicionales (Yunior 2026-07-12) — presets Finviz Elite realtime.
# NO se mezclan en top_gainer_universe: el scanner es penny-gated y los
# filtraria; son universos aparte (swing/calidad). CLI: --screen <name>.
# --------------------------------------------------------------------------
SCREENS = {
    # 1) gainers de CALIDAD: mcap>$50M, precio sobre SMA20, beta>1.5,
    #    EPS next-5Y>10%, ROE>15%, current ratio>1.5, y subiendo >=2% hoy.
    #    OJO: el signal ta_topgainers (top ~1% del dia) intersectado con
    #    estos fundamentales da 0 casi siempre (verificado 2026-07-12);
    #    ta_change_u2 es la version util del mismo concepto.
    "quality": dict(signal=None, price_cap=False, filters=[
        "cap_microover", "ta_sma20_pa", "ta_beta_o1.5",
        "fa_estltgrowth_o10", "fa_roe_o15", "fa_curratio_o1.5",
        "ta_change_u2"]),
    # 2) rebote: RSI oversold(30) + dia verde + relative volume > 2
    "oversold": dict(signal=None, price_cap=False, filters=[
        "ta_rsi_os30", "ta_change_u", "sh_relvol_o2"]),
    # 3) cosecha propia — squeeze igniter: short float >20% + rvol>2 + dia
    #    verde + sobre SMA20 + liquidez minima. Los cortos atrapados son la
    #    gasolina de los top gainers de MAÑANA: este screen los ve encenderse.
    #    (rvol>1.5 y no >2: con >2 el stack completo da 0 en dias tranquilos
    #    — verificado 2026-07-12)
    "squeeze": dict(signal=None, price_cap=False, filters=[
        "sh_short_o20", "sh_relvol_o1.5", "ta_change_u",
        "ta_sma20_pa", "sh_avgvol_o300", "cap_microover"]),
    # 4) newhigh (Yunior 2026-07-12): sobre SMA20 y SMA50, NEW HIGH de 50
    #    dias, deuda/equity < 1, ROE > 20%, avg vol > 100k. Momentum de
    #    calidad: maximos nuevos sin balance apalancado.
    "newhigh": dict(signal=None, price_cap=False, filters=[
        "ta_sma20_pa", "ta_sma50_pa", "ta_highlow50d_nh",
        "fa_debteq_u1", "fa_roe_o20", "sh_avgvol_o100"]),
    # 5) shorts (Yunior 2026-07-12) — universo para POSICIONES CORTAS:
    #    mcap > $300M, short float > 20%, avg vol > 500k, rvol > 1,
    #    volumen del dia > 500k. Liquido y muy shorteado.
    "shorts": dict(signal=None, price_cap=False, filters=[
        "cap_smallover", "sh_short_o20", "sh_avgvol_o500",
        "sh_relvol_o1", "sh_curvol_o500"]),
    # 6) recovery (Yunior 2026-07-12): sobre SMA20 pero AUN bajo SMA50
    #    (rebote temprano dentro de correccion), avg vol > 400k, rvol > 1,
    #    volumen del dia > 2M.
    "recovery": dict(signal=None, price_cap=False, filters=[
        "ta_sma20_pa", "ta_sma50_pb", "sh_avgvol_o400",
        "sh_relvol_o1", "sh_curvol_o2000"]),
    # 7) earnings (Yunior 2026-07-12): sobre SMA200, avg vol > 400k,
    #    EPS growth this year > 25%, EPS qtr/qtr > 25%, RSI not oversold
    #    (>50), EPS next year > 25%. OJO: Finviz NO tiene filtro "sales
    #    growth next year" — se usa sales qtr/qtr > 25% como proxy.
    "earnings": dict(signal=None, price_cap=False, filters=[
        "ta_sma200_pa", "sh_avgvol_o400", "fa_epsyoy_o25",
        "fa_epsqoq_o25", "ta_rsi_nos50", "fa_epsyoy1_o25",
        "fa_salesqoq_o25"]),
}


def finviz_elite_screen(name, auth=None):
    """Corre un preset de SCREENS y devuelve rows estandar (src=finviz_<name>)."""
    cfg = SCREENS[name]
    return _finviz_elite_export(cfg["signal"], auth=auth, src=f"finviz_{name}",
                                filters=cfg["filters"], price_cap=cfg["price_cap"])


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
    if "--screen" in sys.argv:
        name = sys.argv[sys.argv.index("--screen") + 1]
        rows = finviz_elite_screen(name)
        rows.sort(key=lambda r: r["gain_pct"], reverse=True)
        print(f"screen '{name}': {len(rows)} matches")
        for r in rows[:30]:
            print(f"  {r['sym']:6s} ${r['price']:9.2f} {r['gain_pct']:+6.1f}% "
                  f"vol {r['volume']:>12,.0f} mcap ${r['market_cap']:>9,.0f}M "
                  f"{r['country']}")
        sys.exit(0)
    pm = "--premarket" in sys.argv
    u = top_gainer_universe(premarket=pm)
    u.sort(key=lambda r: max(r.get("premarket_pct", 0), r.get("gain_pct", 0)), reverse=True)
    print(f"{len(u)} candidates ({'premarket' if pm else 'regular'}):")
    for r in u[:25]:
        print(f"  {r['sym']:6s} ${r['price']:8.3f} reg +{r['gain_pct']:6.1f}% "
              f"pm +{r['premarket_pct']:6.1f}% vol {r['volume']:,.0f} src {r['src']}")
