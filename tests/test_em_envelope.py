"""em_envelope: el EM del straddle sale bien en un caso hecho A MANO, el conteo de dias
de mercado distingue viernes->lunes, y sin IV ni straddle devuelve None (jamas 0).
"""
import datetime as dt
import importlib.util
import json
import math
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def em():
    return _load("em_envelope")


# --------------------------------------------------------------- calendario

def test_dias_de_mercado_viernes_a_lunes(em):
    vie = dt.date(2026, 7, 24)                  # viernes
    lun = dt.date(2026, 7, 27)                  # lunes
    assert em.market_days_between(vie, lun) == 1     # 1 dia de MERCADO
    assert (lun - vie).days == 3                     # 3 de calendario
    assert em.next_market_day(vie) == dt.date(2026, 7, 27)


def test_festivo_no_es_dia_de_mercado(em):
    assert em.is_market_day(dt.date(2026, 7, 3)) is False      # Independence observado
    assert em.is_market_day(dt.date(2026, 11, 26)) is False     # Thanksgiving
    assert em.is_market_day(dt.date(2026, 7, 2)) is True
    # el 4-jul cae sabado en 2026: del 2 al 6 hay 1 sola sesion (el lunes 6)
    assert em.market_days_between(dt.date(2026, 7, 2), dt.date(2026, 7, 6)) == 1


def test_tabla_de_festivos_agotada_levanta(em):
    with pytest.raises(ValueError):
        em.is_market_day(dt.date(2029, 3, 15))      # asumir "sin festivos" seria fabricar


# --------------------------------------------------------------- EM a mano

CHAIN = """# opt_chain TEST | epoch {ep} | x | spot 100.00 | exps 20260727
# strike right exp bid ask vol oi iv delta gamma
100.00 C 20260727 1.90 2.10 100 500 0.3000 0.5000 0.0500
100.00 P 20260727 1.40 1.60 100 500 0.3000 -0.5000 0.0500
105.00 C 20260727 0.40 0.60 50 400 0.3000 0.2000 0.0300
"""

# 2026-07-27 lunes 10:00 local
MON = int(dt.datetime(2026, 7, 27, 10, 0, 0).timestamp())


def _chain(em, tmp_path, sym="test", ep=MON, body=CHAIN):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    p = d / ("opt_chain_%s.txt" % sym)
    p.write_text(body.format(ep=ep))
    em.CUBE.latest_chain = lambda s: str(p) if s.lower() == sym else None
    em.CUBE.full_chain_path = lambda s, date=None: None
    em.levels_of = lambda s: None
    return str(p)


def test_em_del_straddle_calculado_a_mano(em, tmp_path):
    """call_mid = 2.00, put_mid = 1.50 -> em_straddle = 0.8*3.50 = 2.80 sobre spot 100.
    Expiry = la propia sesion (span 1 = exp_span 1) -> em_pct = 2.8%."""
    _chain(em, tmp_path)
    e = em.envelope("TEST", now=MON + 60)
    assert e["em_src"] == "straddle"
    assert e["atm_strike"] == 100.0
    assert e["em_straddle"] == pytest.approx(2.80, abs=1e-9)
    assert e["em_straddle_pct"] == pytest.approx(0.028, abs=1e-9)
    assert e["span_days"] == 1 and e["exp_span_days"] == 1
    assert e["scaled_from_exp"] is False
    assert e["em_pct"] == pytest.approx(0.028, abs=1e-9)
    assert e["em_hi"] == pytest.approx(100 * math.exp(0.028), abs=1e-4)
    assert e["em_lo"] == pytest.approx(100 * math.exp(-0.028), abs=1e-4)
    assert e["coverage_hist"] is None


def test_expiry_mas_lejano_se_escala_en_tiempo(em, tmp_path):
    """El viernes 24 con expiry del lunes 27: 1 dia de mercado de span, 1 de exp_span
    (viernes->lunes) => sin escalar. Con el snapshot del jueves 23, exp_span = 2 y el
    straddle debe encogerse por sqrt(1/2) para vallar SOLO la sesion objetivo."""
    thu = int(dt.datetime(2026, 7, 23, 10, 0, 0).timestamp())
    _chain(em, tmp_path, ep=thu)
    e = em.envelope("TEST", now=thu + 60)
    assert e["span_days"] == 1 and e["exp_span_days"] == 2
    assert e["scaled_from_exp"] is True
    assert e["em_pct"] == pytest.approx(0.028 * math.sqrt(0.5), abs=1e-6)


def test_viernes_publica_los_dos_conteos(em, tmp_path):
    """El caso del doc: el nivel del viernes abarca hasta el LUNES."""
    fri = int(dt.datetime(2026, 7, 24, 16, 30, 0).timestamp())     # tras el cierre
    _chain(em, tmp_path, ep=fri)
    e = em.envelope("TEST", now=fri + 60)
    assert e["target_session"] == "2026-07-27"
    assert e["span_days"] == 1 and e["calendar_days"] == 3


# --------------------------------------------------------------- fail-loud

NOQUOTE = """# opt_chain TEST | epoch {ep} | x | spot 100.00 | exps 20260727
# strike right exp bid ask vol oi iv delta gamma
100.00 C 20260727 -1.00 -1.00 100 500 -1.0000 -1.0000 -1.0000
100.00 P 20260727 -1.00 -1.00 100 500 -1.0000 -1.0000 -1.0000
"""


def test_sin_iv_ni_straddle_devuelve_none_no_cero(em, tmp_path):
    _chain(em, tmp_path, body=NOQUOTE)
    e = em.envelope("TEST", now=MON + 60)
    assert e["em_hi"] is None and e["em_lo"] is None and e["em_pct"] is None
    assert e["invalid_reason"] == "sin_iv_ni_straddle"
    assert e["em_src"] is None


IVONLY = """# opt_chain TEST | epoch {ep} | x | spot 100.00 | exps 20260727
# strike right exp bid ask vol oi iv delta gamma
100.00 C 20260727 -1.00 -1.00 100 500 0.3170 0.5000 0.0500
100.00 P 20260727 -1.00 -1.00 100 500 0.3170 -0.5000 0.0500
"""


def test_ruta_iv_cuando_no_hay_cotizaciones(em, tmp_path):
    """Fuera de RTH el bid/ask es -1.00: se cae a la IV real de la cadena, etiquetada."""
    _chain(em, tmp_path, body=IVONLY)
    e = em.envelope("TEST", now=MON + 60)
    assert e["em_src"] == "iv_atm_chain"
    assert e["iv_atm"] == pytest.approx(0.317)
    assert e["em_pct"] == pytest.approx(0.317 * math.sqrt(1 / 252.0), abs=1e-6)
    assert e["em_hi"] > 100 > e["em_lo"]


def test_una_sola_pata_cotizada_no_es_straddle(em, tmp_path):
    body = """# opt_chain TEST | epoch {ep} | x | spot 100.00 | exps 20260727
# strike right exp bid ask vol oi iv delta gamma
100.00 C 20260727 1.90 2.10 100 500 0.3000 0.5000 0.0500
100.00 P 20260727 -1.00 -1.00 100 500 -1.0000 -1.0000 -1.0000
"""
    _chain(em, tmp_path, body=body)
    e = em.envelope("TEST", now=MON + 60)
    assert e["em_src"] == "iv_atm_chain", "no se completa la pata que falta"


def test_sin_cadena_ni_spot_no_inventa_valla(em, tmp_path):
    em.CUBE.latest_chain = lambda s: None
    em.CUBE.full_chain_path = lambda s, date=None: None
    em.levels_of = lambda s: None
    e = em.envelope("ZZZZ", now=MON)
    assert e["em_hi"] is None and e["invalid_reason"] == "sin_spot"


# --------------------------------------------------------------- confluencia

def test_confluencia_con_el_muro(em, tmp_path):
    _chain(em, tmp_path)
    hi = 100 * math.exp(0.028)
    em.levels_of = lambda s: {"spot": 100.0, "call_wall": round(hi + 0.05, 2), "put_wall": 90.0}
    e = em.envelope("TEST", now=MON + 60)
    assert e["confluence"] and e["confluence"]["side"] == "up"
    assert e["confluence"]["wall"] == "call_wall"
    assert e["confluence"]["gap_pct"] < 0.15


def test_muro_lejano_no_es_confluencia(em, tmp_path):
    _chain(em, tmp_path)
    em.levels_of = lambda s: {"spot": 100.0, "call_wall": 120.0, "put_wall": 80.0}
    e = em.envelope("TEST", now=MON + 60)
    assert e["confluence"] is None


def test_earnings_no_se_afirma_sin_fuente(em, tmp_path):
    _chain(em, tmp_path)
    e = em.envelope("TEST", now=MON + 60)
    assert e["earnings_checked"] is False and e["earnings_src"] is None
    assert e["invalid_reason"] is None, "no mirado != invalidado"


def test_escritura_atomica(em, tmp_path, monkeypatch):
    _chain(em, tmp_path)
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    e = em.write_envelope("TEST", now=MON + 60)
    p = os.path.join("data", "em_test.json")
    assert json.load(open(p))["em_hi"] == e["em_hi"]
    assert not [f for f in os.listdir("data") if ".tmp" in f]


TWOEXP = """# opt_chain TEST | epoch {ep} | x | spot 100.00 | exps 20260724 20260727
# strike right exp bid ask vol oi iv delta gamma
100.00 C 20260724 0.04 0.06 100 500 0.3000 0.5000 0.0500
100.00 P 20260724 0.04 0.06 100 500 0.3000 -0.5000 0.0500
100.00 C 20260727 1.90 2.10 100 500 0.3000 0.5000 0.0500
100.00 P 20260727 1.40 1.60 100 500 0.3000 -0.5000 0.0500
"""


def test_no_valla_el_lunes_con_el_0dte_del_viernes(em, tmp_path):
    """Bug cazado en la corrida real: el straddle 0DTE del viernes a las 15:55 da em 0,11%
    (una opcion a 5 minutos de expirar), no el movimiento de la sesion siguiente. El expiry
    elegido debe CUBRIR la sesion objetivo."""
    fri1555 = int(dt.datetime(2026, 7, 24, 15, 55, 0).timestamp())
    sat = int(dt.datetime(2026, 7, 25, 9, 50, 0).timestamp())
    _chain(em, tmp_path, ep=fri1555, body=TWOEXP)
    e = em.envelope("TEST", now=sat)
    assert e["target_session"] == "2026-07-27"
    assert e["exp"] == 20260727, "el 0DTE vencido no puede vallar el lunes"
    assert e["em_straddle"] == pytest.approx(2.80)      # el del lunes, no el de 0.08
    assert e["snap_date"] == "2026-07-24"
    assert e["snap_age_market_days"] == 1               # viernes->lunes: legitimo
    assert e["invalid_reason"] is None


def test_snapshot_de_hace_varias_sesiones_se_marca(em, tmp_path):
    old = int(dt.datetime(2026, 7, 20, 15, 55, 0).timestamp())   # lunes anterior
    sat = int(dt.datetime(2026, 7, 25, 9, 50, 0).timestamp())
    _chain(em, tmp_path, ep=old, body=TWOEXP)
    e = em.envelope("TEST", now=sat)
    assert e["snap_age_market_days"] > 1
    assert e["invalid_reason"] == "snapshot_viejo"
