"""uw_endpoint_probe: el sondeador de reconocimiento. Payloads REALES capturados
el 2026-08-04 06:19 UTC contra la API de Unusual Whales. Cero red en los tests."""
import datetime as dt
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_endpoint_probe as ep  # noqa: E402

# fila REAL de /api/stock/SPY/flow-alerts (2026-08-03 20:13:07Z)
FLOW_ALERT = {
    "type": "put", "ticker": "SPY", "created_at": "2026-08-03T20:13:07.054951Z",
    "price": "1.24", "expiry": "2026-08-04", "strike": "757", "open_interest": 33,
    "total_premium": "104160", "volume": 63330, "underlying_price": "757.92",
    "trade_count": 28, "iv_end": "0.107013899704288", "iv_start": "0.107013899704288",
    "has_floor": False, "has_multileg": False, "has_sweep": False,
    "all_opening_trades": False, "total_size": 840, "alert_rule": "RepeatedHits",
    "total_bid_side_prem": "124", "total_ask_side_prem": "104036",
    "volume_oi_ratio": "1919.09090909091", "option_chain": "SPY260804P00757000",
    "has_singleleg": True, "expiry_count": 1}

# filas REALES de /api/market/market-tide (cubos de 5 min)
TIDE = [
    {"timestamp": "2026-08-03T09:30:00-04:00", "date": "2026-08-03",
     "net_call_premium": "-12393914.0000", "net_put_premium": "-840030.0000",
     "net_volume": 46649},
    {"timestamp": "2026-08-03T15:55:00-04:00", "date": "2026-08-03",
     "net_call_premium": "38066157.0000", "net_put_premium": "742416.0000",
     "net_volume": 170094}]


def test_shape_resume_tipos_no_valores():
    s = ep.shape({"data": [FLOW_ALERT]})
    assert s["data"][1] == "x1"
    fila = s["data"][0]
    assert fila["ticker"] == "str"
    assert fila["open_interest"] == "int"
    assert fila["has_sweep"] == "bool"
    # el premium de UW viaja como STRING: si esto cambia, el motor que lo sume revienta
    assert fila["total_ask_side_prem"] == "str"


def test_shape_marca_lista_vacia_y_null():
    # {"data": []} es exactamente lo que devuelve /api/alerts sin alertas configuradas
    assert ep.shape({"data": []}) == {"data": "[] (vacia)"}
    assert ep.shape({"sector": None}) == {"sector": "null"}


def test_shape_corta_por_profundidad():
    hondo = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    assert ep.shape(hondo, max_depth=2) == {"a": {"b": {"c": "..."}}}


def test_trim_recorta_listas_y_dice_cuantas_quedan():
    t = ep.trim({"data": [1, 2, 3, 4, 5]}, n=2)
    assert t["data"] == [1, 2, "... +3 filas"]
    # con menos filas que el corte no se añade la coletilla
    assert ep.trim({"data": [1]}, n=2)["data"] == [1]


def test_newest_timestamp_coge_el_mas_reciente_no_el_primero():
    payload = {"data": [
        {"created_at": "2026-08-03T18:00:00Z"},
        {"created_at": "2026-08-03T20:13:07.054951Z"},
        {"created_at": "2026-08-03T19:00:00Z"}]}
    assert ep.newest_timestamp(payload) == "2026-08-03T20:13:07.054951Z"


def test_newest_timestamp_anidado_y_multiclave():
    assert ep.newest_timestamp({"data": TIDE}) == "2026-08-03T15:55:00-04:00"
    assert ep.newest_timestamp({"data": {"tape_time": "2026-08-03T23:59:42Z"}}) \
        == "2026-08-03T23:59:42Z"


def test_newest_timestamp_devuelve_none_si_no_hay_sello():
    # market_top_net_impact NO trae sello: debe decir None, jamas fabricar "ahora"
    assert ep.newest_timestamp({"data": [{"ticker": "SPY", "net_premium": 84214246.0}]}) is None
    assert ep.newest_timestamp({}) is None


def test_age_seconds_mide_contra_un_ahora_explicito():
    ahora = dt.datetime(2026, 8, 4, 6, 19, 17, tzinfo=dt.timezone.utc)
    # 2026-08-03T20:13:07Z -> 36370 s de antiguedad (medido en el recon)
    a = ep.age_seconds("2026-08-03T20:13:07.054951Z", now=ahora)
    assert 36369 <= a <= 36371


def test_age_seconds_solo_fecha_cuenta_en_dias():
    ahora = dt.datetime(2026, 8, 4, 6, 19, 17, tzinfo=dt.timezone.utc)
    assert ep.age_seconds("2026-08-03", now=ahora) == 86400.0


def test_age_seconds_none_en_vez_de_cero_plausible():
    # regla dura: un sello ilegible es "no se", NUNCA 0 (que leeria como tiempo real)
    assert ep.age_seconds(None) is None
    assert ep.age_seconds("") is None
    assert ep.age_seconds("no-es-una-fecha") is None


def test_endpoints_bien_formados():
    assert ENDPOINTS_OK()


def ENDPOINTS_OK():
    for nombre, tpl in ep.ENDPOINTS.items():
        assert tpl.startswith("/api/"), nombre
        for campo in ("sym", "date", "sector", "expiry"):
            tpl.format(sym="SPY", date="2026-08-03", sector="Technology",
                       expiry="2026-08-11")
        assert " " not in tpl, nombre
    return True


def test_flow_set_es_subconjunto_de_endpoints():
    faltan = [n for n in ep.FLOW_SET if n not in ep.ENDPOINTS]
    assert faltan == [], faltan


def test_verdict_usa_la_PEOR_edad_no_la_media():
    v, peor = ep.verdict({"a": 5.0, "b": 90.0})
    assert v == "DELAYED — no dispara" and peor == 90.0
    v, peor = ep.verdict({"a": 5.0, "b": 42.0})
    assert v == "CANDIDATO A TIEMPO-REAL" and peor == 42.0


def test_verdict_ignora_los_none_pero_no_inventa_veredicto_sin_datos():
    # un endpoint sin sello no debe arrastrar el veredicto...
    assert ep.verdict({"a": 10.0, "b": None})[0] == "CANDIDATO A TIEMPO-REAL"
    # ...pero si NO hay ni una edad, el veredicto es None, jamas "tiempo real" por ausencia
    assert ep.verdict({"a": None, "b": None}) == (None, None)
    assert ep.verdict({}) == (None, None)


def test_verdict_en_el_umbral_exacto_es_delayed():
    # 60 s = un cubo entero de retraso: no dispara (mismo umbral que uw_latency_probe.py)
    assert ep.verdict({"a": ep.REALTIME_S})[0] == "DELAYED — no dispara"


def test_cube_lag_cuenta_cubos_no_segundos():
    ahora = dt.datetime(2026, 8, 4, 14, 7, 30, tzinfo=dt.timezone.utc)
    # el cubo 14:07 ya publicado a los 30 s -> 0 cubos de retraso
    assert ep.cube_lag("2026-08-04T14:07:00Z", now=ahora) == 0
    # solo esta el 14:06 -> va un cubo por detras (normal si consolida por minuto)
    assert ep.cube_lag("2026-08-04T14:06:00Z", now=ahora) == 1
    # el 14:05 -> dos cubos: ya no sirve para disparar
    assert ep.cube_lag("2026-08-04T14:05:00Z", now=ahora) == 2


def test_cube_lag_sin_sello_es_none():
    assert ep.cube_lag(None) is None
    assert ep.cube_lag("basura") is None


def test_in_rth_falso_en_fin_de_semana_y_fuera_de_horario():
    import time as _t
    # sabado 12:00 -> False sin ni mirar el calendario de mercado
    sab = _t.struct_time((2026, 8, 8, 12, 0, 0, 5, 220, 0))
    assert ep.in_rth(sab) is False
    # martes 02:19 (la hora de este recon) -> False
    madrugada = _t.struct_time((2026, 8, 4, 2, 19, 0, 1, 216, 0))
    assert ep.in_rth(madrugada) is False
    # martes 16:00 en punto -> ya fuera (RTH es [09:30, 16:00))
    cierre = _t.struct_time((2026, 8, 4, 16, 0, 0, 1, 216, 0))
    assert ep.in_rth(cierre) is False


def test_rth_set_solo_endpoints_con_sello_intradia():
    for n in ep.RTH_SET:
        assert n in ep.ENDPOINTS, n
    # los EOD no pueden entrar: su edad se mide en dias y falsearia el veredicto
    for n in ("greek_exposure", "max_pain", "vol_term_structure", "oi_change"):
        assert n not in ep.RTH_SET, n


def test_endpoints_de_flujo_medidos_estan_presentes():
    # los que dieron 200 el 2026-08-04 y sostienen el diseño de alertas
    for n in ("flow_alerts_global", "net_prem_ticks", "greek_flow", "market_tide",
              "flow_per_strike", "spot_exposures", "oi_change"):
        assert n in ep.ENDPOINTS, n
