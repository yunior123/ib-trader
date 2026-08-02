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
