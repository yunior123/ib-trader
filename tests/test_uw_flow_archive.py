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


# =========================================================================================
# BACKFILL (--backfill --days N): sesiones pasadas via ?date=. Anadido 2026-08-04.
# =========================================================================================
import datetime as _dt   # noqa: E402
import urllib.error      # noqa: E402
import io                # noqa: E402


@pytest.fixture
def hist(tmp_path, monkeypatch):
    """Aisla data/history en tmp: ningun test toca el archivo real."""
    monkeypatch.setattr(A, "REPO", str(tmp_path))
    return tmp_path


def _rows(day, kind="net_prem_ticks", n=3):
    if kind == "greek_flow":
        return [{"timestamp": "%sT13:%02d:00Z" % (day, i), "dir_vega_flow": -1.5 * i}
                for i in range(n)]
    if kind == "flow_per_strike":
        return [{"date": day, "strike": "%d" % (700 + i)} for i in range(n)]
    return [{"date": day, "tape_time": "%sT13:%02d:00Z" % (day, i),
             "net_call_premium": "10", "net_put_premium": "4"} for i in range(n)]


# --- parseo de ?date= --------------------------------------------------------------------
def test_backfill_pide_la_fecha_en_query(hist, monkeypatch):
    visto = {}

    def fake(path, tok):
        visto["path"] = path
        return _rows("2026-06-05"), {"x-uw-daily-req-count": "800"}

    monkeypatch.setattr(A, "fetch", fake)
    est, n, q = A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")
    assert visto["path"] == "/api/stock/SPY/net-prem-ticks?date=2026-06-05"
    assert est == "nuevo" and n == 3 and q == 800


def test_backfill_archiva_bajo_la_fecha_pedida_con_procedencia(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch",
                        lambda p, t: (_rows("2026-06-05"), {"x-uw-daily-req-count": "1"}))
    A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")
    p = A.dest("net_prem_ticks", "SPY", "2026-06-05")
    with open(p) as f:
        d = json.load(f)
    assert d["session_date"] == "2026-06-05"
    assert d["source"] == "backfill"           # backfill y vivo jamas se mezclan sin declararlo
    assert d["pull_date"] == _dt.date.today().isoformat()


def test_backfill_NO_PUEDE_escribir_con_la_fecha_del_reloj(hist, monkeypatch):
    """Si UW ignorase ?date= y sirviese HOY, archivar bajo la fecha pedida seria envenenar
    el backtest con look-ahead. Se levanta y no se escribe nada."""
    hoy = _dt.date.today().isoformat()
    monkeypatch.setattr(A, "fetch", lambda p, t: (_rows(hoy), {}))
    with pytest.raises(A.ShapeError) as e:
        A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")
    assert "2026-06-05" in str(e.value) and hoy in str(e.value)
    assert not os.path.exists(A.dest("net_prem_ticks", "SPY", "2026-06-05"))
    assert not os.path.exists(A.dest("net_prem_ticks", "SPY", hoy))


def test_backfill_rechaza_dia_distinto_aunque_sea_pasado(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch", lambda p, t: (_rows("2026-06-04"), {}))
    with pytest.raises(A.ShapeError):
        A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")


# --- reanudable: un dia ya archivado se salta --------------------------------------------
def test_dia_ya_archivado_no_gasta_peticion(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch",
                        lambda p, t: (_rows("2026-06-05"), {"x-uw-daily-req-count": "1"}))
    assert A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")[0] == "nuevo"

    def prohibido(p, t):
        raise AssertionError("no debe volver a pedir un dia ya archivado")

    monkeypatch.setattr(A, "fetch", prohibido)
    est, n, q = A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")
    assert est == "ya" and n == 3 and q is None


def test_hueco_ya_marcado_tampoco_se_repide(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch", lambda p, t: ([], {}))
    assert A.backfill_one("greek_flow", "MU", "2026-06-05", "tok")[0] == "hueco"

    def prohibido(p, t):
        raise AssertionError("el hueco ya estaba marcado")

    monkeypatch.setattr(A, "fetch", prohibido)
    assert A.backfill_one("greek_flow", "MU", "2026-06-05", "tok")[0] == "ya"


def test_fichero_corrupto_cuenta_como_ausente_y_se_rehace(hist, monkeypatch):
    p = A.dest("net_prem_ticks", "SPY", "2026-06-05")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write("{roto")
    assert A.archived_state("net_prem_ticks", "SPY", "2026-06-05") == (None, 0)
    monkeypatch.setattr(A, "fetch", lambda pa, t: (_rows("2026-06-05"), {}))
    assert A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")[0] == "nuevo"


def test_fichero_con_OTRO_dia_dentro_no_se_da_por_bueno(hist):
    """Un fichero de 2026-06-04 guardado en la carpeta del 05 no cuenta como cobertura del 05."""
    A.write_atomic(A.dest("net_prem_ticks", "SPY", "2026-06-05"),
                   {"n": 3, "rows": _rows("2026-06-04")})
    assert A.archived_state("net_prem_ticks", "SPY", "2026-06-05") == (None, 0)


# --- 0 filas = HUECO explicito, jamas relleno ---------------------------------------------
def test_cero_filas_marca_hueco_y_no_escribe_json_de_datos(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch", lambda p, t: ([], {"x-uw-daily-req-count": "9"}))
    est, n, q = A.backfill_one("net_prem_ticks", "SPY", "2026-06-06", "tok")
    assert est == "hueco" and n == 0
    assert not os.path.exists(A.dest("net_prem_ticks", "SPY", "2026-06-06"))
    with open(A.hole_path("net_prem_ticks", "SPY", "2026-06-06")) as f:
        d = json.load(f)
    assert d["hueco"] is True and d["n"] == 0 and d["session_date"] == "2026-06-06"


def test_la_marca_de_hueco_no_la_ve_un_consumidor_de_uw_json(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch", lambda p, t: ([], {}))
    A.backfill_one("net_prem_ticks", "SPY", "2026-06-06", "tok")
    assert not A.hole_path("net_prem_ticks", "SPY", "2026-06-06").endswith(".json")


# --- un fallo jamas destruye lo bueno -----------------------------------------------------
def test_403_no_borra_el_fichero_bueno(hist, monkeypatch):
    """Descargado ayer, hoy la ruta da 403: el fichero de ayer sigue intacto."""
    monkeypatch.setattr(A, "fetch", lambda p, t: (_rows("2026-06-05"), {}))
    A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")
    p = A.dest("net_prem_ticks", "SPY", "2026-06-05")
    antes = open(p).read()

    def da_403(pa, t):
        raise A.WallError("403 historic_data_access_missing")

    monkeypatch.setattr(A, "fetch", da_403)
    # ya archivado -> ni siquiera pide; y si se fuerza el estado, el contenido no cambia
    assert A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")[0] == "ya"
    assert open(p).read() == antes


def test_403_en_un_dia_sin_archivar_no_escribe_nada(hist, monkeypatch):
    def da_403(pa, t):
        raise A.WallError("403 historic_data_access_missing")

    monkeypatch.setattr(A, "fetch", da_403)
    with pytest.raises(A.WallError):
        A.backfill_one("net_prem_ticks", "SPY", "2026-03-01", "tok")
    assert not os.path.exists(A.dest("net_prem_ticks", "SPY", "2026-03-01"))
    assert not os.path.exists(A.hole_path("net_prem_ticks", "SPY", "2026-03-01"))


def test_fetch_distingue_403_de_pared_de_403_de_estrangulamiento(monkeypatch):
    """La pared no se reintenta: esperar 60 s no acerca marzo. Y no debe dormir."""
    def urlopen_403(req, timeout=None):
        raise urllib.error.HTTPError(
            "u", 403, "Forbidden", {},
            io.BytesIO(b'{"code":"historic_data_access_missing","message":"earliest 2026-03-24"}'))

    monkeypatch.setattr(A.urllib.request, "urlopen", urlopen_403)
    monkeypatch.setattr(A.time, "sleep", lambda s: (_ for _ in ()).throw(
        AssertionError("la pared no se reintenta")))
    with pytest.raises(A.WallError) as e:
        A.fetch("/api/stock/SPY/net-prem-ticks?date=2026-01-16", "tok")
    assert "2026-03-24" in str(e.value)


# --- planificacion de sesiones -------------------------------------------------------------
def test_sessions_back_excluye_hoy_y_los_fines_de_semana():
    """La sesion de hoy es del daemon y esta incompleta: el backfill no la toca."""
    d = A.sessions_back(5, _dt.date(2026, 8, 3))
    assert d == ["2026-08-03", "2026-07-31", "2026-07-30", "2026-07-29", "2026-07-28"]


def test_sessions_back_por_defecto_no_incluye_hoy():
    assert _dt.date.today().isoformat() not in A.sessions_back(3)


def test_sessions_back_salta_festivos():
    """4-jul-2026 cae en sabado; el observado es el viernes 3. Ninguno de los dos es sesion."""
    d = A.sessions_back(10, _dt.date(2026, 7, 8))
    assert "2026-07-04" not in d and "2026-07-03" not in d and "2026-07-02" in d


def test_sessions_back_no_pasa_de_la_pared():
    d = A.sessions_back(500, _dt.date(2026, 8, 3))
    assert min(d) >= "2026-03-01"     # no baja indefinidamente pidiendo 403s


# --- cobertura -----------------------------------------------------------------------------
def test_coverage_cuenta_ok_hueco_y_falta(hist, monkeypatch):
    monkeypatch.setattr(A, "fetch", lambda p, t: (_rows("2026-06-05"), {}))
    A.backfill_one("net_prem_ticks", "SPY", "2026-06-05", "tok")
    monkeypatch.setattr(A, "fetch", lambda p, t: ([], {}))
    A.backfill_one("net_prem_ticks", "SPY", "2026-06-04", "tok")
    cov = A.coverage(["net_prem_ticks"], ["SPY"], ["2026-06-05", "2026-06-04", "2026-06-03"])
    assert cov[("net_prem_ticks", "SPY", "2026-06-05")] == ("ok", 3)
    assert cov[("net_prem_ticks", "SPY", "2026-06-04")] == ("hueco", 0)
    assert cov[("net_prem_ticks", "SPY", "2026-06-03")] == (None, 0)


def test_freno_de_cupo_es_una_fraccion_del_cupo_no_un_numero_clavado():
    assert 0 < A.BACKFILL_STOP_FRACTION <= 1.0
    assert A.DAILY_CAP * A.BACKFILL_STOP_FRACTION < A.DAILY_CAP


def test_la_pared_medida_es_la_declarada_por_el_servidor():
    """Medido 2026-08-04: 2026-03-24 -> 200, 2026-03-23 -> 403 historic_data_access_missing."""
    assert A.WALL_HINT == "2026-03-24"
    assert A.WALL_CODE == "historic_data_access_missing"
