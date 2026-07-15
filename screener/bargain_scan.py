#!/usr/bin/env python3
"""bargain_scan — alertas de GANGA (Yunior 2026-07-15: "create a bot to send
bargain alerts on the tickers of our fleet based on trading agents research,
finviz, etc" + "bargain bot on topgainers, and some others as well, but be
selective").

Tres carriles, todos REALTIME (Yahoo/delayed prohibido, orden #4):
  1) FLEET DIP    : tickers de la flota con caida intradia fuerte (Finnhub
                    quote realtime) — nombre de calidad en rebaja.
  2) GAINER DIP   : top gainers Finviz (mcap>=$50M, sin cap penny) que
                    retrocedieron >=1/3 del rango del dia desde el maximo
                    pero siguen verdes — comprar el pullback del corredor.
  3) OVERSOLD     : preset finviz 'oversold' (mcap>=$50M, RSI<30, dia verde,
                    rvol>2) — rebote de sobreventa con volumen.

SELECTIVIDAD: mcap>=$50M, top-N por score, 1 alerta por simbolo por dia.
TA OBLIGATORIO Y EXCLUYENTE: TradingAgents vete cada candidato; SOLO los BUY
se notifican (banner Mac + espejo Desktop). TODO — candidatos, veredictos,
rechazados — queda en data/screener/bargain_log_YYYYMMDD.jsonl para la
validacion de fin de dia. SIGNAL-ONLY: este bot JAMAS opera.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state  # noqa: E402
import research  # noqa: E402
from price import finnhub_quote  # noqa: E402
from sources import _finviz_elite_export, finviz_elite_screen  # noqa: E402

FLEET = ["DRAM", "NOK", "SPCX", "TSLA", "NVDA", "TXN", "TSM", "AMD", "INTC",
         "ASML", "AAPL", "GLD", "QQQ", "SLV", "CPER", "USO", "MU", "SKHY"]
FLEET_DIP_PCT = float(os.getenv("BARGAIN_FLEET_DIP", "2.5"))    # caida >= %
GAINER_MIN_UP = float(os.getenv("BARGAIN_GAINER_MIN_UP", "3.0"))  # sigue verde >=
PULLBACK_FRAC = float(os.getenv("BARGAIN_PULLBACK", "0.33"))   # retroceso >= 1/3 rango
MIN_MCAP_M = float(os.getenv("BARGAIN_MIN_MCAP", "50.0"))
TOP_N = int(os.getenv("BARGAIN_TOPN", "5"))
TA_TOPN = int(os.getenv("BARGAIN_TA_TOPN", "2"))               # research/corrida


def _day():
    return datetime.now().astimezone().strftime("%Y%m%d")


def _log_path():
    return os.path.join(state.BASE, f"bargain_log_{_day()}.jsonl")


def _log(rec):
    try:
        with open(_log_path(), "a") as f:
            f.write(json.dumps({"ts": state.now_iso(), **rec}) + "\n")
    except Exception:
        pass


def _seen_today():
    """symbols ya alertados o ya vetados hoy (carry-over entre corridas)."""
    alerted, verdicts = set(), {}
    try:
        for line in open(_log_path()):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") == "alert":
                alerted.add(r["sym"])
            if r.get("kind") == "verdict":
                verdicts[r["sym"]] = r.get("ta_action")
    except FileNotFoundError:
        pass
    return alerted, verdicts


def lane_fleet_dip():
    out = []
    for sym in FLEET:
        q = finnhub_quote(sym)
        if not q or not q.get("price") or not q.get("prev_close"):
            continue
        chg = (q["price"] - q["prev_close"]) / q["prev_close"] * 100
        if chg <= -FLEET_DIP_PCT:
            out.append({"sym": sym, "price": round(q["price"], 4),
                        "gain_pct": round(chg, 2), "market_cap": 0,
                        "lane": "fleet_dip", "score": abs(chg),
                        "note": f"flota {chg:+.1f}% hoy"})
    return out


def lane_gainer_dip():
    rows = _finviz_elite_export("ta_topgainers", price_cap=False,
                                filters=["cap_microover"], src="bargain_gainers")
    out = []
    for r in rows[:40]:
        if r["market_cap"] < MIN_MCAP_M or r["gain_pct"] < GAINER_MIN_UP:
            continue
        q = finnhub_quote(r["sym"])
        if not q or not q.get("high") or not q.get("low") or not q.get("price"):
            continue
        rng = q["high"] - q["low"]
        if rng <= 0:
            continue
        pull = (q["high"] - q["price"]) / rng
        if pull >= PULLBACK_FRAC and r["gain_pct"] >= GAINER_MIN_UP:
            out.append({"sym": r["sym"], "price": round(q["price"], 4),
                        "gain_pct": r["gain_pct"], "market_cap": r["market_cap"],
                        "lane": "gainer_dip",
                        "score": r["gain_pct"] * pull,
                        "note": f"gainer +{r['gain_pct']:.0f}% retrocedio "
                                f"{pull * 100:.0f}% del rango"})
    return out


def lane_oversold():
    rows = finviz_elite_screen("oversold")
    out = []
    for r in rows[:20]:
        if r["market_cap"] < MIN_MCAP_M:
            continue
        out.append({"sym": r["sym"], "price": r["price"],
                    "gain_pct": r["gain_pct"], "market_cap": r["market_cap"],
                    "lane": "oversold", "score": 5.0 + r["gain_pct"],
                    "note": "RSI<30 rebotando con rvol>2"})
    return out


def main():
    now = datetime.now().astimezone()
    if now.weekday() > 4 or not ("09:30" <= now.strftime("%H:%M") <= "16:00"):
        return 0
    alerted, verdicts = _seen_today()
    cands, have = [], set()
    for lane in (lane_fleet_dip, lane_gainer_dip, lane_oversold):
        try:
            for c in lane():
                if c["sym"] not in have:
                    have.add(c["sym"])
                    cands.append(c)
        except Exception as e:
            print(f"lane {lane.__name__} fallo: {e}", file=sys.stderr)
    cands.sort(key=lambda c: c["score"], reverse=True)
    cands = [c for c in cands if c["sym"] not in alerted][:TOP_N]
    if not cands:
        return 0
    _log({"kind": "scan", "candidates": cands})

    # veredictos previos del dia (no re-quemar TA en lo ya juzgado)
    for c in cands:
        if c["sym"] in verdicts:
            c["ta_action"] = verdicts[c["sym"]]
    date_str = now.strftime("%Y-%m-%d")
    os.environ["TA_RESEARCH"] = "1"
    cands = research.enrich_candidates(cands, date_str, topn=TA_TOPN)
    for c in cands:
        if c.get("ta_action") and c["sym"] not in verdicts:
            _log({"kind": "verdict", "sym": c["sym"],
                  "ta_action": c["ta_action"],
                  "ta_note": str(c.get("ta_note", ""))[:200], "lane": c["lane"]})

    # SOLO TA-BUY notifica (orden 2026-07-15); todo lo demas queda en el log
    for c in cands:
        if c.get("ta_action") == "BUY" and c["sym"] not in alerted:
            msg = (f"{c['sym']} ${c['price']} {c['gain_pct']:+.1f}% | "
                   f"{c['note']} | TA: BUY")
            state.notify_mac("BARGAIN (TA BUY)", msg, sound="Ping")
            _log({"kind": "alert", "sym": c["sym"], "price": c["price"],
                  "lane": c["lane"], "note": c["note"]})
            print(f"BARGAIN ALERT {c['sym']} — {c['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
