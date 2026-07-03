"""uw_darkpool: agregacion descriptiva con prints REALES capturados (probe SPY 2026-08-03),
y la regla dura de la casa — un fallo jamas fabrica un cero plausible."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_darkpool as dp  # noqa: E402

# prints REALES de /api/darkpool/SPY el 2026-08-03 (recorte de la pagina de 500)
REAL = [
    {"size": 275, "ticker": "SPY", "price": "744.39", "executed_at": "2026-07-31T23:59:40Z",
     "premium": "204707.25", "canceled": False, "sale_cond_codes": None, "nbbo_ask": "744.36",
     "nbbo_bid": "743.91", "volume": 62443606, "ext_hour_sold_codes": "extended_hours_trade",
     "market_center": "L", "nbbo_ask_quantity": 273, "nbbo_bid_quantity": 75,
     "tracking_id": 10509871354210, "trade_code": None, "trade_settlement": "regular",
     "trf_executed_at": "2026-07-31T23:59:40Z"},
    {"size": 1000, "ticker": "SPY", "price": "744.3901", "executed_at": "2026-07-31T23:59:34Z",
     "premium": "744390.1000", "canceled": False, "sale_cond_codes": None, "nbbo_ask": "744.58",
     "nbbo_bid": "743.91", "volume": 62442666, "ext_hour_sold_codes": "extended_hours_trade",
     "market_center": "L", "nbbo_ask_quantity": 137, "nbbo_bid_quantity": 75,
     "tracking_id": 10509871348169, "trade_code": None, "trade_settlement": "regular",
     "trf_executed_at": "2026-07-31T23:59:34Z"},
    {"size": 502, "ticker": "SPY", "price": "744.58", "executed_at": "2026-07-31T23:59:29Z",
     "premium": "373779.16", "canceled": False, "sale_cond_codes": None, "nbbo_ask": "744.58",
     "nbbo_bid": "744.5", "volume": 62440826, "ext_hour_sold_codes": "extended_hours_trade",
     "market_center": "L", "nbbo_ask_quantity": 137, "nbbo_bid_quantity": 30,
     "tracking_id": 10509871343297, "trade_code": None, "trade_settlement": "regular",
     "trf_executed_at": "2026-07-31T23:59:29Z"},
]


def test_clean_mapea_los_reales():
    rs = dp.clean(REAL)
    assert len(rs) == 3
    r = rs[0]
    assert r["size"] == 275 and r["price"] == 744.39 and r["premium"] == 204707.25
    assert r["bid"] == 743.91 and r["ask"] == 744.36 and r["vol"] == 62443606
    assert r["ext"] is True and r["trf_lag_s"] == 0.0


def test_clean_descarta_canceladas_y_malformadas():
    assert dp.clean([dict(REAL[0], canceled=True)]) == []
    assert dp.clean([dict(REAL[0], price="no-numero")]) == []
    sin_campo = dict(REAL[0])
    del sin_campo["executed_at"]
    assert dp.clean([sin_campo]) == []


def test_vs_mid_reparte_por_tamano():
    # tol = 1 pb ~ 0.0744. print0 744.39 vs mid 744.135 (d=+0.255) y print1 744.3901 vs
    # mid 744.245 (d=+0.145) van ARRIBA; print2 744.58 vs mid 744.54 (d=+0.04) cae AL MEDIO.
    v = dp.vs_mid(dp.clean(REAL))
    assert v["total_size"] == 1777
    assert abs(v["above_mid_pct"] + v["at_mid_pct"] + v["below_mid_pct"] - 100.0) < 0.01
    assert v["above_mid_pct"] == round(100.0 * 1275 / 1777, 2)   # 71.75
    assert v["at_mid_pct"] == round(100.0 * 502 / 1777, 2)       # 28.25
    assert v["below_mid_pct"] == 0.0


def test_vs_mid_sin_nbbo_devuelve_none():
    # nunca un 50/50 plausible cuando no hay NBBO utilizable
    roto = [dict(REAL[0], nbbo_bid="0", nbbo_ask="0")]
    assert dp.vs_mid(dp.clean(roto)) is None


def test_vs_ref_y_referencia_invalida():
    rs = dp.clean(REAL)
    v = dp.vs_ref(rs, 744.39)
    assert v["ref_price"] == 744.39 and v["total_size"] == 1502   # el print exacto no cuenta
    assert abs(v["above_pct"] + v["below_pct"] - 100.0) < 0.01
    assert dp.vs_ref(rs, 0) is None and dp.vs_ref([], 744.0) is None


def test_dark_share_usa_el_avance_de_volumen_consolidado():
    d = dp.dark_share(dp.clean(REAL))
    assert d["dark_size"] == 1777
    assert d["consolidated"] == 62443606 - 62440826   # 2780
    assert d["pct"] == round(100.0 * 1777 / 2780, 2)
    assert d["window_s"] == 11.0


def test_dark_share_sin_avance_devuelve_none():
    plano = [dict(r, volume=1000) for r in REAL]
    assert dp.dark_share(dp.clean(plano)) is None
    assert dp.dark_share(dp.clean(REAL[:1])) is None


def test_levels_un_solo_precio_devuelve_none():
    # sin rango no hay histograma: el widget dice "sin dato", no dibuja una barra inventada
    igual = [dict(r, price="744.39") for r in REAL]
    assert dp.levels(dp.clean(igual)) is None
    assert dp.levels([]) is None


def test_levels_reparte_todo_el_tamano():
    L = dp.levels(dp.clean(REAL))
    assert L is not None and L["total_size"] == 1777
    assert sum(r["size"] for r in L["rows"]) == 1777
    assert L["lo"] == 744.39 and L["hi"] == 744.58


def test_latency_mide_dos_cosas_distintas():
    lat = dp.latency(dp.clean(REAL), now=dp._epoch("2026-08-01T00:59:40Z"))
    assert lat["trf_lag_med_s"] == 0.0 and lat["n_lags"] == 3
    assert lat["feed_age_s"] == 3600.0
    assert lat["newest_iso"].startswith("2026-07-31T23:59:40")
    assert dp.latency([]) is None


def test_summarize_sin_filas_utilizables_es_error_no_ceros():
    s = dp.summarize("SPY", [dict(REAL[0], canceled=True)])
    assert s["error"] and "total_size" not in s and "levels" not in s


def test_summarize_real_completo():
    s = dp.summarize("SPY", REAL)
    assert s["sym"] == "SPY" and s["n_prints"] == 3 and s["total_size"] == 1777
    assert s["last_price"] == 744.39
    for k in ("levels", "vs_mid", "vs_last", "dark_share", "latency", "prints"):
        assert s[k] is not None
    # prints ordenados por prima, con el signo vs punto medio ya calculado
    assert [p["premium"] for p in s["prints"]] == [744390.1, 373779.16, 204707.25]
    assert s["prints"][0]["size"] == 1000 and s["prints"][0]["vs_mid"] == 0.1451


def test_error_payload_no_fabrica_simbolos():
    p = dp.error_payload("error 401 (token caducado)", now=1.0)
    assert p == {"asof": 1.0, "error": "error 401 (token caducado)"}
    assert "syms" not in p


def test_payload_se_declara_descriptivo():
    # killlist #3: dark pool NO es señal. El payload lo dice para que nadie lo cablee a un gatillo.
    p = dp.payload({"SPY": {}}, now=1.0)
    assert p["kind"] == "descriptivo" and "unusual whales" in p["source"].lower()
