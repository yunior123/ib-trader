#!/usr/bin/env python3
"""korea_pct: referencia de prev-close honesta (bars -> prevclose -> None) + pump study.
Bug 2026-07-29: warmup trunca bars_*.txt y desde ~23:46 no quedaba barra pre-20:00 -> null."""
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import overnight_feed as OF          # noqa: E402
import overnight_pump_study as PS    # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/Toronto")

BOUNDARY_DT = datetime(2026, 7, 30, 20, 0, tzinfo=ET)   # apertura KRX del viernes KST
BOUNDARY = BOUNDARY_DT.timestamp()
PREV_CLOSE_EP = datetime(2026, 7, 30, 15, 30, tzinfo=KST).timestamp()   # cierre jueves KST


def _bars(tmp_path, name, rows):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / f"bars_{name}.txt").write_text(
        "".join(f"{ep:.0f} {c:.4f} {c:.4f} {c:.4f} {c:.4f} 100\n" for ep, c in rows))


def _prevclose(tmp_path, entries):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    p = d / OF.PREVCLOSE_NAME
    p.write_text(json.dumps(entries))
    return str(p)


def _session_rows():
    """Barras de la sesion en curso: 100.0 -> 101.0 (+1% sobre prev close 100.0)."""
    return [(BOUNDARY + 120, 100.5), (BOUNDARY + 180, 101.0)]


# ---------------------------------------------------------------- 1. referencia en el fichero
def test_ref_en_bars_no_toca_prevclose(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", [(BOUNDARY - 60, 100.0)] + _session_rows())
    _prevclose(tmp_path, {"kospi": {"close": 50.0, "epoch": int(PREV_CLOSE_EP),
                                    "session": "2026-07-30"}})   # trampa: si se usa, sale +102%
    pct, src = OF.korea_pct("kospi", BOUNDARY)
    assert src == "bars"
    assert abs(pct - 1.0) < 1e-6


# ---------------------------------------------------------------- 2. fallback a prevclose
def test_sin_ref_usa_prevclose_de_la_sesion_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", _session_rows())        # SOLO barras post-boundary (caso del bug)
    _prevclose(tmp_path, {"kospi": {"close": 100.0, "epoch": int(PREV_CLOSE_EP),
                                    "session": "2026-07-30"}})
    pct, src = OF.korea_pct("kospi", BOUNDARY)
    assert src == "prevclose"
    assert abs(pct - 1.0) < 1e-6


# ---------------------------------------------------------------- 3. prevclose rancio
def test_prevclose_rancio_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", _session_rows())
    viejo = PREV_CLOSE_EP - 3 * 86400
    _prevclose(tmp_path, {"kospi": {"close": 100.0, "epoch": int(viejo),
                                    "session": OF.krx_session_date(viejo)}})
    pct, src = OF.korea_pct("kospi", BOUNDARY)
    assert pct is None and src is None


# ---------------------------------------------------------------- 4. sin fichero prevclose
def test_sin_prevclose_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", _session_rows())
    pct, src = OF.korea_pct("kospi", BOUNDARY)
    assert pct is None and src is None


# ---------------------------------------------------------------- 5. jamas un cero plausible
def test_ningun_camino_devuelve_cero_plausible(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    (tmp_path / "data").mkdir(exist_ok=True)
    casos = []
    casos.append(OF.korea_pct("kospi", BOUNDARY))                     # fichero inexistente
    _bars(tmp_path, "kospi", [])                                      # fichero vacio
    casos.append(OF.korea_pct("kospi", BOUNDARY))
    _bars(tmp_path, "kospi", [(BOUNDARY - 300, 100.0)])               # solo pre-boundary
    casos.append(OF.korea_pct("kospi", BOUNDARY))
    _bars(tmp_path, "kospi", _session_rows())
    _prevclose(tmp_path, {"kospi": {"close": 0.0, "epoch": int(PREV_CLOSE_EP),
                                    "session": "2026-07-30"}})        # close invalido
    casos.append(OF.korea_pct("kospi", BOUNDARY))
    _prevclose(tmp_path, {"kospi": "corrupto"})
    casos.append(OF.korea_pct("kospi", BOUNDARY))
    for pct, src in casos:
        assert pct is None and src is None
        assert pct not in (0, 0.0, 0.5, 50)


def test_prev_krx_session_date_salta_fin_de_semana():
    lunes = datetime(2026, 8, 2, 20, 0, tzinfo=ET).timestamp()   # domingo 20:00 ET = lunes KST
    assert OF.prev_krx_session_date(lunes) == "2026-07-31"       # viernes KST, no sabado
    assert OF.prev_krx_session_date(BOUNDARY) == "2026-07-30"


# ------------------------------------------------- 3bis. festivos KRX (tabla en data/)
FESTIVO_B = datetime(2026, 8, 18, 9, 0, tzinfo=KST).timestamp()   # martes tras Liberacion(17)


def test_prev_krx_session_date_salta_festivo_krx():
    """17-ago-2026 = Dia de la Liberacion (sustituto) y 15/16 fin de semana: la sesion
    anterior al martes 18 es el VIERNES 14, no el lunes 17."""
    assert "2026-08-17" in OF.krx_holidays()
    assert OF.prev_krx_session_date(FESTIVO_B) == "2026-08-14"


def test_ref_del_dia_previo_a_festivo_se_acepta(tmp_path, monkeypatch):
    """El bug: exigir igualdad con dia-1 descartaba una referencia BUENA tras un festivo."""
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    ep = datetime(2026, 8, 14, 15, 30, tzinfo=KST).timestamp()
    _bars(tmp_path, "kospi", [(FESTIVO_B + 120, 101.0)])
    _prevclose(tmp_path, {"kospi": {"close": 100.0, "epoch": int(ep), "session": "2026-08-14"}})
    pct, src = OF.korea_pct("kospi", FESTIVO_B)
    assert src == "prevclose" and abs(pct - 1.0) < 1e-6


def test_año_sin_tabla_acepta_la_mas_reciente_y_la_etiqueta_degradada(tmp_path, monkeypatch):
    """Tabla que se queda corta (2029 no tabulado): en vez de tirar la referencia se acepta
    la mas reciente dentro de KRX_GAP_MAX_DAYS y se DICE que es degradada (_gap)."""
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    assert not OF.krx_year_covered(2029)
    b = datetime(2029, 2, 20, 9, 0, tzinfo=KST).timestamp()
    _bars(tmp_path, "kospi", [(b + 120, 101.0)])
    cerca = datetime(2029, 2, 16, 15, 30, tzinfo=KST).timestamp()      # 4 dias: dentro del tope
    _prevclose(tmp_path, {"kospi": {"close": 100.0, "epoch": int(cerca),
                                    "session": "2029-02-16"}})
    pct, src = OF.korea_pct("kospi", b)
    assert src == "prevclose_gap" and abs(pct - 1.0) < 1e-6
    lejos = datetime(2029, 2, 5, 15, 30, tzinfo=KST).timestamp()       # 15 dias: ni degradada
    _prevclose(tmp_path, {"kospi": {"close": 100.0, "epoch": int(lejos),
                                    "session": "2029-02-05"}})
    assert OF.korea_pct("kospi", b) == (None, None)


# ------------------------------------------------- 3ter. arranque en frio -> historico archivado
def _hist_bars(tmp_path, name, day, rows):
    d = tmp_path / "data" / "history" / day / "bars"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}_krx.txt").write_text(
        "".join(f"{ep:.0f} {c:.4f} {c:.4f} {c:.4f} {c:.4f} 10\n" for ep, c in rows))


def test_arranque_en_frio_cae_al_historico_archivado(tmp_path, monkeypatch):
    """Proceso nuevo a mitad de sesion: warmup ya trunco bars_*.txt y no hay prevclose.
    data/history/<fecha>/bars/kospi_krx.txt SI tiene la barra — usarla, no devolver null."""
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", _session_rows())
    _hist_bars(tmp_path, "kospi", "2026-07-30",
               [(PREV_CLOSE_EP - 60, 99.5), (PREV_CLOSE_EP, 100.0)])
    _hist_bars(tmp_path, "kospi", "2026-07-24", [(PREV_CLOSE_EP - 6 * 86400, 42.0)])
    pct, src = OF.korea_pct("kospi", BOUNDARY)
    assert src == "hist" and abs(pct - 1.0) < 1e-6


def test_historico_rancio_no_sirve_de_referencia(tmp_path, monkeypatch):
    """Si lo unico archivado es de hace 3 sesiones NO se fabrica un pct: null."""
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", _session_rows())
    _hist_bars(tmp_path, "kospi", "2026-07-27", [(PREV_CLOSE_EP - 3 * 86400, 100.0)])
    assert OF.korea_pct("kospi", BOUNDARY) == (None, None)


def test_prevclose_rancio_pero_historico_fresco_usa_el_historico(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    _bars(tmp_path, "kospi", _session_rows())
    viejo = PREV_CLOSE_EP - 3 * 86400
    _prevclose(tmp_path, {"kospi": {"close": 55.0, "epoch": int(viejo),
                                    "session": OF.krx_session_date(viejo)}})
    _hist_bars(tmp_path, "kospi", "2026-07-30", [(PREV_CLOSE_EP, 100.0)])
    pct, src = OF.korea_pct("kospi", BOUNDARY)
    assert src == "hist" and abs(pct - 1.0) < 1e-6


# ------------------------------------------------- 3quater. el boundary se ancla en KST, no en ET
def test_krx_boundary_es_las_0900_kst_tambien_en_invierno():
    """20:00 ET clavado solo acierta en EDT: en EST el KRX abre a las 19:00 ET y la primera
    hora de sesion se estaba midiendo contra si misma."""
    invierno = datetime(2026, 1, 13, 19, 30, tzinfo=ET)
    b = OF.krx_boundary(invierno)
    assert datetime.fromtimestamp(b, KST).strftime("%Y-%m-%d %H:%M") == "2026-01-14 09:00"
    assert OF.krx_boundary(datetime(2026, 7, 30, 20, 30, tzinfo=ET)) == BOUNDARY


# ------------------------------------------------- 3quinquies. el jsonl no crece sin limite
def test_archive_ctx_topa_las_lineas(tmp_path):
    p = str(tmp_path / "hist" / "overnight_ctx.jsonl")
    for i in range(10):
        assert OF.archive_ctx({"ts": float(i), "relleno": "x" * 200}, path=p, max_lines=3)
    lineas = open(p).read().strip().split("\n")
    assert len(lineas) == 3 and json.loads(lineas[-1])["ts"] == 9.0
    assert not any(f.startswith("overnight_ctx.jsonl.tmp")
                   for f in os.listdir(os.path.dirname(p)))


def test_build_escribe_ref_src_y_archiva_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(OF, "REPO", str(tmp_path))
    monkeypatch.setattr(OF, "PREVCLOSE", str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    monkeypatch.setattr(OF, "OUT", str(tmp_path / "overnight_ctx.json"))
    monkeypatch.setattr(OF, "CTX_JSONL", str(tmp_path / "hist" / "overnight_ctx.jsonl"))
    monkeypatch.setattr(OF, "fut_pct", lambda s: 0.25)
    monkeypatch.setattr(OF, "sentiment", lambda: None)
    monkeypatch.setattr(OF, "krx_boundary", lambda now=None: BOUNDARY)
    _bars(tmp_path, "kospi", _session_rows())
    _prevclose(tmp_path, {"kospi": {"close": 100.0, "epoch": int(PREV_CLOSE_EP),
                                    "session": "2026-07-30"}})
    ctx = OF.build()
    assert ctx["kospi_ref_src"] == "prevclose" and abs(ctx["kospi_pct"] - 1.0) < 1e-6
    assert ctx["hynix_pct"] is None and ctx["hynix_ref_src"] is None
    assert json.load(open(str(tmp_path / "overnight_ctx.json")))["kospi_pct"] == ctx["kospi_pct"]
    lineas = open(str(tmp_path / "hist" / "overnight_ctx.jsonl")).read().strip().split("\n")
    assert len(lineas) == 1 and json.loads(lineas[0])["ts"] == ctx["ts"]
    OF.build()
    assert len(open(str(tmp_path / "hist" / "overnight_ctx.jsonl")).read().strip().split("\n")) == 2


# ---------------------------------------------------------------- 6. korea_bar_bridge escribe
def _bridge():
    try:
        import ib_insync  # noqa: F401
    except ImportError:
        m = type(sys)("ib_insync")
        m.IB = object
        m.Contract = object
        m.util = None
        sys.modules["ib_insync"] = m
    import korea_bar_bridge
    return korea_bar_bridge


def test_update_prev_close_escritura_atomica(tmp_path, monkeypatch):
    kb = _bridge()
    monkeypatch.setattr(kb, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir(exist_ok=True)
    rows = [(PREV_CLOSE_EP - 60, 99.0), (PREV_CLOSE_EP, 100.0), (BOUNDARY + 60, 105.0)]
    e = kb.update_prev_close("kospi", rows, BOUNDARY)
    assert e == {"close": 100.0, "epoch": int(PREV_CLOSE_EP), "session": "2026-07-30"}
    p = tmp_path / "data" / OF.PREVCLOSE_NAME
    assert json.load(open(str(p)))["kospi"]["close"] == 100.0
    assert not any(f.endswith(".tmp") for f in os.listdir(str(tmp_path / "data")))
    # otro simbolo no borra el anterior; y no se retrocede a una barra mas vieja
    kb.update_prev_close("samsung", rows, BOUNDARY)
    kb.update_prev_close("kospi", [(PREV_CLOSE_EP - 600, 42.0)], BOUNDARY)
    j = json.load(open(str(p)))
    assert set(j) == {"kospi", "samsung"} and j["kospi"]["close"] == 100.0


def test_update_prev_close_sin_barra_previa_no_escribe(tmp_path, monkeypatch):
    kb = _bridge()
    monkeypatch.setattr(kb, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir(exist_ok=True)
    assert kb.update_prev_close("kospi", [(BOUNDARY + 60, 105.0)], BOUNDARY) is None
    assert kb.update_prev_close("kospi", [], BOUNDARY) is None
    assert not os.path.exists(str(tmp_path / "data" / OF.PREVCLOSE_NAME))


def test_prev_close_from_rows_ignora_precios_invalidos():
    kb = _bridge()
    assert kb.prev_close_from_rows([(BOUNDARY - 60, 0.0)], BOUNDARY) is None
    assert kb.prev_close_from_rows([(BOUNDARY - 60, 7.0), (BOUNDARY - 30, 8.0)],
                                   BOUNDARY) == (8.0, BOUNDARY - 30)


def test_boundary_es_una_sola_definicion():
    kb = _bridge()
    assert kb.ovf.krx_boundary is OF.krx_boundary
    assert kb.krx_market.__code__.co_names.count("ovf") >= 1   # horario KRX: de ovf, no clavado


def test_roll_prev_close_reintenta_el_mismo_boundary_tras_fallo_transitorio(tmp_path, monkeypatch):
    """El bug: _pc_boundary se marcaba ANTES de escribir; si read_bar_rows devolvia []
    (fichero a medio escribir) la referencia de esa sesion se perdia para siempre."""
    kb = _bridge()
    monkeypatch.setattr(kb, "ROOT", str(tmp_path))
    monkeypatch.setattr(kb, "_pc_boundary", 0.0)
    monkeypatch.setattr(kb, "_pc_pending", set())
    monkeypatch.setattr(kb.ovf, "krx_boundary", lambda now=None: BOUNDARY)
    # bars_path explicito: tests/test_korea_bars_archive.py lo reemplaza sin restaurarlo
    monkeypatch.setattr(kb, "bars_path", lambda n: str(tmp_path / "data" / f"bars_{n}.txt"))
    (tmp_path / "data").mkdir(exist_ok=True)
    for name, close in (("kospi", 100.0), ("samsung", 200.0), ("skhynix", 300.0)):
        _bars(tmp_path, name, [(PREV_CLOSE_EP, close)])
    real = kb.read_bar_rows
    intentos = {"n": 0}

    def flaky(path):
        intentos["n"] += 1
        return [] if intentos["n"] <= len(kb.CORE) else real(path)   # 1a vuelta: lectura vacia

    monkeypatch.setattr(kb, "read_bar_rows", flaky)
    assert kb.maybe_roll_prev_close() is True
    assert not os.path.exists(str(tmp_path / "data" / OF.PREVCLOSE_NAME))
    kb.maybe_roll_prev_close()                    # 2a vuelta, MISMO boundary: lo recupera
    j = json.load(open(str(tmp_path / "data" / OF.PREVCLOSE_NAME)))
    assert set(j) == set(kb.CORE) and j["kospi"]["close"] == 100.0
    assert not kb._pc_pending
    lecturas = intentos["n"]
    kb.maybe_roll_prev_close()                    # 3a: nada pendiente -> ni lee
    assert intentos["n"] == lecturas


def test_roll_prev_close_no_reintenta_boundaries_viejos(tmp_path, monkeypatch):
    """Al cambiar de boundary la lista de pendientes se REEMPLAZA: no se arrastra el ayer."""
    kb = _bridge()
    monkeypatch.setattr(kb, "ROOT", str(tmp_path))
    monkeypatch.setattr(kb, "_pc_boundary", 0.0)
    monkeypatch.setattr(kb, "_pc_pending", set())
    monkeypatch.setattr(kb, "bars_path", lambda n: str(tmp_path / "data" / f"bars_{n}.txt"))
    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.setattr(kb.ovf, "krx_boundary", lambda now=None: BOUNDARY)
    assert kb.maybe_roll_prev_close() is True and kb._pc_pending == set(kb.CORE)
    monkeypatch.setattr(kb.ovf, "krx_boundary", lambda now=None: BOUNDARY + 86400)
    assert kb.maybe_roll_prev_close() is True
    assert kb._pc_pending == set(kb.CORE) and kb._pc_boundary == BOUNDARY + 86400


# ---------------------------------------------------------------- 7. pump study
def _synth_history(root, n_sessions):
    """n sesiones KRX sinteticas 09:00-15:30 KST; pares suben, impares bajan."""
    d = datetime(2026, 3, 2, 9, 0, tzinfo=KST)     # lunes
    hechas = 0
    while hechas < n_sessions:
        if d.weekday() < 5:
            base = d.timestamp()
            step = 0.01 if hechas % 2 == 0 else -0.01
            bars = os.path.join(root, d.date().isoformat(), "bars")
            os.makedirs(bars, exist_ok=True)
            with open(os.path.join(bars, "kospi_krx.txt"), "w") as f:
                for i in range(391):               # 09:00 -> 15:30
                    c = 100.0 + i * step
                    f.write(f"{base + i * 60:.0f} {c:.4f} {c:.4f} {c:.4f} {c:.4f} 10\n")
            hechas += 1
        d += timedelta(days=1)


def test_pump_study_data_insuficiente_con_4_sesiones(tmp_path):
    _synth_history(str(tmp_path), 4)
    res = PS.study(history_root=str(tmp_path), min_n=30)
    assert res["status"] == "DATA-INSUFFICIENT" and res["n"] == 4
    b = res["symbols"]["kospi"]["buckets"]
    assert all(x["p_up"] is None and x["wilson_lo"] is None for x in b)
    assert b[0]["n"] == 4


def test_pump_study_wilson_con_30_sesiones(tmp_path):
    _synth_history(str(tmp_path), 30)
    res = PS.study(history_root=str(tmp_path), min_n=30)
    assert res["status"] == "MEASURED" and res["n"] == 30
    b = res["symbols"]["kospi"]["buckets"]
    assert len(b) == PS.N_BUCKETS
    for x in b:
        if x["status"] != "MEASURED":
            continue
        assert 0.0 <= x["wilson_lo"] <= x["p_up"] <= x["wilson_hi"] <= 1.0
        assert x["wilson_lo"] < x["wilson_hi"]
    b0 = b[0]
    assert b0["n"] == 30 and abs(b0["p_up"] - 0.5) < 1e-9
    # la franja de las 00:30 ET = 13:30 KST existe y esta etiquetada en ambas zonas
    et = [x["et"] for x in b]
    assert "00:30" in et and b[[x["et"] for x in b].index("00:30")]["kst"] == "13:30"


def test_wilson_none_si_n_cero():
    assert PS.wilson(0, 0) is None
    lo, hi = PS.wilson(15, 30)
    assert 0.0 < lo < 0.5 < hi < 1.0


def test_pump_study_escritura_atomica(tmp_path):
    _synth_history(str(tmp_path / "hist"), 2)
    res = PS.study(history_root=str(tmp_path / "hist"), min_n=30)
    out = PS.write(res, out=str(tmp_path / "out" / "overnight_pump_study.json"))
    assert json.load(open(out))["status"] == "DATA-INSUFFICIENT"
    assert not any(f.endswith(".tmp") for f in os.listdir(os.path.dirname(out)))
