"""Tests de uw_flow_archive: el archivador NO puede etiquetar mal ni fabricar datos.

Cero red: fetch se monkeypatchea siempre. Un test que llame a UW de verdad quema cupo y
depende de la hora a la que corra la suite.
"""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location(
    "ibt_uw_flow_archive", os.path.join(SCRIPTS, "uw_flow_archive.py"))
A = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = A
spec.loader.exec_module(A)


# --- dia de sesion: el bug que se cazo en vivo el 2026-08-04 -----------------------------
def test_dia_sale_del_dato_no_del_reloj():
    """A las 02:37 del dia 4, UW sirve la sesion del 3. Etiquetar por reloj la esconderia."""
    rows = [{"date": "2026-08-03", "tape_time": "x"}, {"date": "2026-08-03", "tape_time": "y"}]
    assert A.session_day("net_prem_ticks", rows) == "2026-08-03"


def test_dia_desde_timestamp_utc():
    rows = [{"timestamp": "2026-08-03T13:30:00Z"}, {"timestamp": "2026-08-03T20:15:00Z"}]
    assert A.session_day("greek_flow", rows) == "2026-08-03"


def test_respuesta_que_mezcla_dias_levanta():
    """Mezclar dos sesiones en un fichero envenena cualquier backtest posterior."""
    rows = [{"date": "2026-08-03"}, {"date": "2026-08-04"}]
    with pytest.raises(A.ShapeError) as e:
        A.session_day("net_prem_ticks", rows)
    assert "mezcla" in str(e.value)


def test_sin_fecha_levanta_en_vez_de_inventar_hoy():
    with pytest.raises(A.ShapeError):
        A.session_day("net_prem_ticks", [{"call_volume": 1}])


def test_dest_usa_el_dia_que_se_le_da():
    p = A.dest("greek_flow", "SPY", "2026-08-03")
    assert p.endswith("data/history/2026-08-03/uw_greek_flow_spy.json")


# --- validacion de forma ----------------------------------------------------------------
def test_validate_acepta_filas_completas():
    assert A.validate("net_prem_ticks", [
        {"tape_time": "1", "net_call_premium": "5", "net_put_premium": "3"}]) == 1


def test_validate_levanta_si_falta_un_campo_obligatorio():
    """Sin net_put_premium el signed_premium seria falso; se levanta, no se rellena con 0."""
    with pytest.raises(A.ShapeError) as e:
        A.validate("net_prem_ticks", [{"tape_time": "1", "net_call_premium": "5"}])
    assert "net_put_premium" in str(e.value)


def test_validate_levanta_si_la_fila_no_es_objeto():
    with pytest.raises(A.ShapeError):
        A.validate("greek_flow", [[1, 2, 3]])


def test_validate_lista_vacia_es_cero_no_error():
    """0 filas es un hecho legitimo (premarket): se archiva vacio, no se finge contenido."""
    assert A.validate("greek_flow", []) == 0


# --- escritura --------------------------------------------------------------------------
def test_snapshot_escribe_atomico_y_sin_tmp(tmp_path, monkeypatch):
    rows = [{"timestamp": "2026-08-03T13:30:00Z", "dir_vega_flow": -12.5}]
    monkeypatch.setattr(A, "fetch", lambda p, t: (rows, {"x-uw-daily-req-count": "7"}))
    monkeypatch.setattr(A, "REPO", str(tmp_path))
    monkeypatch.setattr(A, "dest", lambda k, s, d: os.path.join(
        str(tmp_path), "data", "history", d, "uw_%s_%s.json" % (k, s.lower())))
    n, out, headers = A.snapshot("greek_flow", "SPY", "tok")
    assert n == 1
    assert "2026-08-03" in out and not os.path.exists(out + ".tmp")
    with open(out) as f:
        saved = json.load(f)
    assert saved["sym"] == "SPY" and saved["rows"] == rows and saved["n"] == 1


def test_used_quota_lee_la_cabecera():
    assert A.used_quota({"x-uw-daily-req-count": "590"}) == 590


def test_used_quota_sin_cabecera_devuelve_none_no_cero():
    """Un 0 plausible haria creer que el cupo esta intacto. Ausente es None."""
    assert A.used_quota({}) is None
    assert A.used_quota({"x-uw-daily-req-count": "basura"}) is None


# --- presupuesto y portero ---------------------------------------------------------------
def test_las_series_declaradas_tienen_campos_obligatorios():
    assert set(A.SERIES) == set(A.REQUIRED)


def test_cadencia_de_cada_serie_es_positiva():
    for kind, (path, cada) in A.SERIES.items():
        assert cada > 0 and "{sym}" in path


def test_presupuesto_de_los_5_por_defecto_cabe_en_el_cupo():
    """Si alguien añade simbolos sin mirar, el arranque debe negarse — no reventar el cupo."""
    por_dia = sum(int(390 * 60 / cada) for _, cada in A.SERIES.values()) * len(A.DEFAULT_SYMS)
    assert por_dia <= A.DAILY_CAP * A.SAFETY_FRACTION


def test_in_session_rechaza_fin_de_semana():
    import time as _t
    sabado = _t.struct_time((2026, 8, 8, 12, 0, 0, 5, 220, 1))
    assert A.in_session(sabado) is False


def test_in_session_rechaza_antes_de_la_apertura():
    import time as _t
    martes_pre = _t.struct_time((2026, 8, 4, 8, 0, 0, 1, 216, 1))
    assert A.in_session(martes_pre) is False


# --- contrato con lo ya archivado ---------------------------------------------------------
def test_lo_archivado_del_2026_08_03_tiene_la_forma_esperada():
    """Contra los ficheros reales que se capturaron: si el contrato cambia, salta aqui."""
    p = os.path.join(REPO, "data", "history", "2026-08-03", "uw_net_prem_ticks_spy.json")
    if not os.path.exists(p):
        pytest.skip("sin archivo del 2026-08-03 en esta maquina")
    with open(p) as f:
        d = json.load(f)
    assert d["kind"] == "net_prem_ticks" and d["sym"] == "SPY" and d["n"] == len(d["rows"])
    assert A.session_day("net_prem_ticks", d["rows"]) == "2026-08-03"
    assert A.validate("net_prem_ticks", d["rows"]) == d["n"]
