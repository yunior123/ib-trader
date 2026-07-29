"""uw_flow_tape: mapeo con respuesta REAL capturada (probe QQQ 2026-07-28), rancidez,
y que un payload de error jamas fabrica filas."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_flow_tape as ft  # noqa: E402

# alert REAL devuelto por /api/stock/QQQ/flow-alerts el 2026-07-28 (sin campo sentiment)
REAL = {
    "type": "call", "ticker": "QQQ", "created_at": "2026-07-28T20:17:58.155573Z",
    "price": "1.67", "expiry": "2026-07-29", "strike": "683", "open_interest": 685,
    "total_premium": "178857", "volume": 12842, "underlying_price": "675.58",
    "trade_count": 35, "iv_end": "0.310419135265881", "iv_start": "0.310419135265881",
    "has_floor": False, "has_multileg": False, "has_sweep": True,
    "all_opening_trades": False, "total_size": 1071, "alert_rule": "RepeatedHits",
    "total_bid_side_prem": "162157", "total_ask_side_prem": "167",
    "volume_oi_ratio": "18.7474452554745", "option_chain": "QQQ260729C00683000",
    "has_singleleg": True, "expiry_count": 1,
}


def test_map_row_real():
    m = ft.map_row(REAL)
    assert m is not None
    assert m["sym"] == "QQQ" and m["type"] == "C"
    assert m["side"] == "bid"          # 162157 bid > 16533 mid > 167 ask
    assert m["strike"] == 683.0 and m["expiry"] == "2026-07-29"
    assert m["premium"] == 178857.0 and m["size"] == 1071
    assert m["oi"] == 685 and m["vol"] == 12842 and m["vol_oi"] == 18.7
    assert m["rule"] == "RepeatedHits" and m["sweep"] is True
    assert abs(m["ts"] - 1785269878.155573) < 1
    assert "sentiment" not in m        # UW no lo trae: JAMAS se inventa


def test_sentiment_solo_si_uw_lo_trae():
    r = dict(REAL, sentiment="bullish")
    assert ft.map_row(r)["sentiment"] == "bullish"


def test_side_ask_y_mid():
    ask = dict(REAL, total_bid_side_prem="100", total_ask_side_prem="150000")
    assert ft.map_row(ask)["side"] == "ask"
    mid = dict(REAL, total_bid_side_prem="100", total_ask_side_prem="200")
    assert ft.map_row(mid)["side"] == "mid"


def test_map_row_malformada_devuelve_none():
    r = dict(REAL)
    del r["created_at"]
    assert ft.map_row(r) is None
    assert ft.map_row(dict(REAL, strike="no-numero")) is None


def test_merge_dedup_y_recorte():
    rows = {}
    ft.merge(rows, [REAL, dict(REAL)])   # mismo alert dos veces = una fila
    assert len(rows) == 1
    muchos = [dict(REAL, created_at=f"2026-07-28T19:{i//60:02d}:{i%60:02d}Z",
                   option_chain=f"QQQ{i}") for i in range(80)]
    ft.merge(rows, muchos)
    assert len(rows) == ft.MAX_ROWS
    p = ft.tape_payload(rows, now=1785270000.0)
    assert p["asof"] == 1785270000.0
    ts = [r["ts"] for r in p["rows"]]
    assert ts == sorted(ts, reverse=True)   # mas reciente arriba


def test_rancidez():
    p = ft.tape_payload({}, now=1000.0)
    assert ft.stale_s(p, now=1400.0) == 400.0
    assert ft.stale_s({}, now=1400.0) is None   # sin asof: no se sabe, no se finge


def test_error_no_fabrica_filas():
    p = ft.error_payload("error 403 tras 3 esperas", now=1000.0)
    assert p["error"] and "rows" not in p
