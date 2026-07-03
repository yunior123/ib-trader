#!/usr/bin/env python3
"""bargain_hunt — caceria de GANGAS bajo demanda (Yunior 2026-07-15: "run
trading agents to search for bargains... as of now, at least 15 bargains").

Junta un pool ancho de candidatos AHORA (flota en dip, gainers en pullback,
oversold, top losers de calidad, new lows de calidad — todo Finviz Elite
realtime + Finnhub) y corre TradingAgents sobre TODOS en paralelo limitado
(3 subprocesos — Mac de 8GB). Salida: reporte ranked con veredicto TA por
nombre + data/screener/bargain_hunt_<ts>.json. Signal-only, jamas opera.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
import research  # noqa: E402
import bargain_scan as bs  # noqa: E402
from sources import _finviz_elite_export  # noqa: E402

POOL_TARGET = int(os.getenv("HUNT_POOL", "24"))
PARALLEL = int(os.getenv("HUNT_PARALLEL", "3"))
MIN_MCAP_M = 50.0


def lane_toplosers():
    """Nombres de calidad (mcap>=$300M) masacrados HOY — la ganga clasica."""
    rows = _finviz_elite_export("ta_toplosers", price_cap=False,
                                filters=["cap_smallover"], src="hunt_losers")
    return [{"sym": r["sym"], "price": r["price"], "gain_pct": r["gain_pct"],
             "market_cap": r["market_cap"], "lane": "toploser",
             "score": abs(r["gain_pct"]),
             "note": f"caida {r['gain_pct']:+.1f}% hoy, mcap ${r['market_cap']:,.0f}M"}
            for r in rows[:15] if r["gain_pct"] <= -5]


def lane_newlow():
    """Minimos de 52 semanas con mcap>=$300M y volumen — value en capitulacion."""
    rows = _finviz_elite_export(None, price_cap=False,
                                filters=["cap_smallover", "ta_highlow52w_nl",
                                         "sh_avgvol_o300"], src="hunt_newlow")
    return [{"sym": r["sym"], "price": r["price"], "gain_pct": r["gain_pct"],
             "market_cap": r["market_cap"], "lane": "newlow52w",
             "score": 5 + abs(min(r["gain_pct"], 0)),
             "note": f"minimo 52w, {r['gain_pct']:+.1f}% hoy"}
            for r in rows[:12]]


def lane_rsi_oversold_wide():
    """RSI<30 mcap>=$50M sin exigir dia verde (version ancha del preset)."""
    rows = _finviz_elite_export(None, price_cap=False,
                                filters=["cap_microover", "ta_rsi_os30",
                                         "sh_avgvol_o200"], src="hunt_rsi")
    return [{"sym": r["sym"], "price": r["price"], "gain_pct": r["gain_pct"],
             "market_cap": r["market_cap"], "lane": "rsi_oversold",
             "score": 4 + abs(min(r["gain_pct"], 0)),
             "note": f"RSI<30, {r['gain_pct']:+.1f}% hoy"}
            for r in rows[:12]]


def main():
    now = datetime.now().astimezone()
    cands, have = [], set()
    lanes = (bs.lane_fleet_dip, bs.lane_gainer_dip, bs.lane_oversold,
             lane_toplosers, lane_newlow, lane_rsi_oversold_wide)
    for lane in lanes:
        try:
            got = lane()
            print(f"[pool] {lane.__name__}: {len(got)}", flush=True)
            for c in got:
                if c["sym"] not in have and (c.get("market_cap", 0) >= MIN_MCAP_M
                                             or c["lane"] == "fleet_dip"):
                    have.add(c["sym"]); cands.append(c)
        except Exception as e:
            print(f"[pool] {lane.__name__} fallo: {e}", flush=True)
    cands.sort(key=lambda c: c["score"], reverse=True)
    pool = cands[:POOL_TARGET]
    print(f"[pool] total {len(cands)} unicos -> investigando {len(pool)}", flush=True)

    date_str = now.strftime("%Y-%m-%d")
    os.environ["TA_RESEARCH"] = "1"

    def vet(c):
        note = research.research_ticker(c["sym"], date_str)
        if note:
            c["ta_action"] = note["action"]
            c["ta_note"] = note["decision"]
        else:
            c["ta_action"] = "?"
        print(f"[TA] {c['sym']:6s} {c['lane']:12s} -> {c['ta_action']}", flush=True)
        return c

    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        pool = list(ex.map(vet, pool))

    order = {"BUY": 0, "HOLD": 1, "?": 2, "SELL": 3}
    pool.sort(key=lambda c: (order.get(c["ta_action"], 2), -c["score"]))
    ts = now.strftime("%Y%m%d_%H%M")
    out = os.path.join(state.BASE, f"bargain_hunt_{ts}.json")
    json.dump({"ts": state.now_iso(), "pool": pool}, open(out, "w"), indent=1)

    buys = [c for c in pool if c["ta_action"] == "BUY"]
    print(f"\n===== BARGAIN HUNT {ts} — {len(pool)} investigados, "
          f"{len(buys)} TA BUY =====", flush=True)
    for c in pool:
        print(f"{c['ta_action']:4s} {c['sym']:6s} ${c['price']:<9.2f} "
              f"{c['gain_pct']:+6.1f}% mcap ${c.get('market_cap', 0):>8,.0f}M "
              f"[{c['lane']}] {c['note']}", flush=True)
    if buys:
        state.notify_mac("BARGAIN HUNT (TA BUY)",
                         ", ".join(f"{c['sym']} {c['gain_pct']:+.0f}%" for c in buys[:8]))
    print(f"\nguardado: {out}", flush=True)


if __name__ == "__main__":
    main()
