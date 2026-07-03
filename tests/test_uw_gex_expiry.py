"""uw_gex_expiry: GEX por vencimiento con filas REALES (probe QQQ 2026-08-03).
Cubre el agujero medido ese dia: el archivo propio se paraba en 2026-08-21 y la cadena viva
en UN vencimiento, asi que 08-24..08-31 no existia. Y la latencia EOD va DECLARADA."""
import datetime as dt
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_gex_expiry as ge  # noqa: E402


def raw(expiry, dte, cg, pg, cd=0.0, pd_=0.0):
    return {"date": "2026-07-31", "expiry": expiry, "dte": dte,
            "call_gex": str(cg), "put_gex": str(pg),
            "call_delta": str(cd), "put_delta": str(pd_),
            "call_charm": "10.5", "put_charm": "-4.5",
            "call_vanna": "100.25", "put_vanna": "-40.25"}


# filas REALES de /api/stock/QQQ/greek-exposure/expiry el 2026-08-03
REAL = [
    raw("2026-08-03", 3, 127448, -74672, 2000000, -381819),
    raw("2026-08-21", 21, 276990, -455315, 1000000, -10934218),
    raw("2026-08-28", 28, 21754, -16551),
    raw("2026-08-31", 31, 71143, -58671),
    raw("2026-12-18", 137, 999999, -999999),   # fuera de DTE_MAX: no debe colarse
]


HOY = dt.date(2026, 8, 3)


def test_map_row_netea_call_mas_put():
    m = ge.map_row(REAL[0], today=HOY)
    assert m["expiry"] == "2026-08-03" and m["dte"] == 0
    assert m["net_gex"] == 127448 - 74672      # put_gex ya viene NEGATIVO de UW
    assert m["net_delta"] == 2000000 - 381819
    assert m["net_charm"] == 6.0 and m["net_vanna"] == 60.0


def test_dte_se_recalcula_contra_hoy_no_contra_el_sello_de_uw():
    # UW sirve dte relativo a su `date` (cierre del viernes). El lunes eso pintaba el
    # vencimiento del 07-31 como "0d" cuando ya habia expirado hace 3 dias.
    m = ge.map_row(REAL[0], today=HOY)
    assert m["dte_uw"] == 3 and m["dte"] == 0
    viernes = ge.map_row(raw("2026-07-31", 0, 1, -1), today=HOY)
    assert viernes["dte_uw"] == 0 and viernes["dte"] == -3


def test_map_row_malformada_devuelve_none():
    assert ge.map_row(dict(REAL[0], call_gex="no-numero"), today=HOY) is None
    assert ge.map_row(dict(REAL[0], expiry="no-fecha"), today=HOY) is None
    sin = dict(REAL[0])
    del sin["put_gex"]
    assert ge.map_row(sin, today=HOY) is None


def test_summarize_cubre_08_28_y_08_31():
    # el agujero que motivo el script: estos dos NO estan en data/history ni en la cadena viva
    s = ge.summarize("QQQ", REAL, today=HOY)
    exps = [r["expiry"] for r in s["rows"]]
    assert "2026-08-28" in exps and "2026-08-31" in exps
    assert s["exp_hasta"] == "2026-08-31" and s["n_expiries"] == 4
    assert s["asof_date"] == "2026-07-31"


def test_summarize_recorta_por_dte_max_y_ordena():
    s = ge.summarize("QQQ", REAL, today=HOY)
    assert "2026-12-18" not in [r["expiry"] for r in s["rows"]]
    assert [r["dte"] for r in s["rows"]] == [0, 18, 25, 28]
    assert s["net_gex_total"] == sum(r["net_gex"] for r in s["rows"])


def test_summarize_dte_max_estrecho():
    s = ge.summarize("QQQ", REAL, dte_max=20, today=HOY)
    assert [r["dte"] for r in s["rows"]] == [0, 18]


def test_summarize_sin_vencimientos_vivos_es_error_no_lista_vacia():
    s = ge.summarize("QQQ", [raw("2026-12-18", 137, 1, -1)], today=HOY)
    assert s["error"] and "rows" not in s
    assert ge.summarize("QQQ", [], today=HOY)["error"]


def test_summarize_descarta_los_ya_expirados():
    s = ge.summarize("QQQ", [raw("2026-08-03", 3, 1, -1), raw("2026-07-31", 0, 5, -5)],
                     today=HOY)
    assert [r["expiry"] for r in s["rows"]] == ["2026-08-03"]


def test_stamp_es_el_maximo_no_la_primera_fila():
    # aviso 2026-08-03: en /greek-exposure (endpoint hermano) la primera fila venia con
    # date 2025-08-04. Tomar rows[0] daria un cierre de hace un año como "hoy".
    viejo = dict(raw("2026-08-03", 3, 1, -1), date="2025-08-04")
    s = ge.summarize("QQQ", [viejo, raw("2026-08-21", 21, 1, -1)], today=HOY)
    assert s["asof_date"] == "2026-07-31"


def test_stamp_age_days_mide_la_rancidez():
    by = {"QQQ": ge.summarize("QQQ", REAL, today=HOY)}
    assert ge.stamp_age_days(by, today=dt.date(2026, 8, 3)) == 3   # cierre del viernes
    assert ge.stamp_age_days({"QQQ": {"error": "x"}}) is None


def test_payload_declara_que_es_EOD_y_no_dispara():
    p = ge.payload({"QQQ": ge.summarize("QQQ", REAL, today=HOY)}, now=1.0, today=HOY)
    assert p["latency"] == "EOD_DIARIO"      # doctrina: fuente delayed JAMAS dispara
    assert p["stamp_age_days"] == 3 and p["dte_max"] == ge.DTE_MAX


def test_error_payload_no_fabrica_simbolos():
    p = ge.error_payload("error 401 (token caducado)", now=1.0)
    assert p == {"asof": 1.0, "error": "error 401 (token caducado)"}
    assert "syms" not in p


def test_user_agent_declarado():
    # urllib pelado -> Cloudflare 1010 (medido 2026-08-03: 6 requests 403 seguidos)
    assert "ib-trader" in ge.UA
