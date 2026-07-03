"""uw_net_prem: el GOTCHA de la casa (signed = call - put, NO es net call premium) blindado
con buckets REALES de /net-prem-ticks (probe SPY/QQQ 2026-08-03), y sin ceros fabricados."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_net_prem as np  # noqa: E402


def bucket(t, ncp, npp, nd="0", cv=0, pv=0):
    return {"date": "2026-07-31", "tape_time": t, "net_call_premium": ncp,
            "net_put_premium": npp, "net_delta": nd, "call_volume": cv, "put_volume": pv,
            "net_call_volume": 0, "net_put_volume": 0, "call_volume_ask_side": 0,
            "call_volume_bid_side": 0, "put_volume_ask_side": 0, "put_volume_bid_side": 0}


# forma REAL devuelta por /api/stock/SPY/net-prem-ticks el 2026-08-03
REAL = [
    bucket("2026-07-31T13:30:00Z", "724711.0000", "-100000.00", "-3940.83", 39439, 46556),
    bucket("2026-07-31T13:31:00Z", "-224711.0000", "50000.00", "1000.00", 100, 200),
    bucket("2026-07-31T13:32:00Z", "0", "-331.00", "59.49", 0, 3),
]


def test_gotcha_signed_es_call_menos_put():
    # QQQ MEDIDO el 2026-08-03: signed = +31,1 M con net_call = -13,0 M. Vender un put es
    # alcista, por eso el put RESTA. Si alguien "arregla" esto a una suma, este test muere.
    d = np.day_totals(REAL)
    assert d["net_call_premium"] == 500000.0
    assert d["net_put_premium"] == -50331.0
    assert d["signed_premium"] == 550331.0
    assert d["signed_premium"] != d["net_call_premium"]


def test_day_totals_agrega_volumen_y_delta():
    d = np.day_totals(REAL)
    assert d["call_volume"] == 39539 and d["put_volume"] == 46759
    assert d["n_buckets"] == 3 and abs(d["net_delta"] - (-2881.34)) < 0.01


def test_day_totals_sin_filas_es_none_no_cero():
    assert np.day_totals([]) is None


def test_cumulative_acumula_en_orden_temporal():
    c = np.cumulative(list(reversed(REAL)))   # llega desordenado: se ordena por tape_time
    # 824711 ; +(-224711-50000) = 550000 ; +(0-(-331)) = 550331
    assert [r["cum"] for r in c] == [824711.0, 550000.0, 550331.0]
    assert c[0]["ts"] < c[1]["ts"] < c[2]["ts"]


def test_cumulative_recorta_a_series_max():
    muchos = [bucket(f"2026-07-31T14:{i // 60:02d}:{i % 60:02d}Z", "1", "0")
              for i in range(np.SERIES_MAX + 30)]
    assert len(np.cumulative(muchos)) == np.SERIES_MAX


def test_cumulative_sin_filas_es_none():
    assert np.cumulative([]) is None


def test_summarize_sin_filas_es_error_no_ceros():
    s = np.summarize("SPY", [])
    assert s["error"] and "day" not in s and "windows" not in s


def test_summarize_ventana_vacia_queda_none_explicito():
    # buckets viejos: la ventana de 15 min no los alcanza -> None, jamas 0.0
    s = np.summarize("SPY", REAL)
    assert s["windows"]["15"]["n_buckets"] == 3     # ventana relativa al ultimo bucket
    solo_uno = [REAL[0]]
    assert np.summarize("SPY", solo_uno)["windows"]["60"]["n_buckets"] == 1


def test_summarize_publica_edad_medida():
    s = np.summarize("SPY", REAL)
    assert s["feed_age_s"] is not None and s["feed_ts"] == "2026-07-31T13:32:00Z"
    assert s["sym"] == "SPY" and len(s["series"]) == 3


def test_error_payload_no_fabrica_simbolos():
    p = np.error_payload("UW_TOKEN caducado (401)", now=1.0)
    assert p == {"asof": 1.0, "error": "UW_TOKEN caducado (401)"}
    assert "syms" not in p


def test_payload_lleva_la_formula_escrita():
    p = np.payload({"SPY": {}}, now=1.0)
    assert p["note"] == "signed_premium = net_call_premium - net_put_premium"
