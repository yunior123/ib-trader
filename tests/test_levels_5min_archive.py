"""levels_5min_archive: densifica sin pisarse, sin tocar el fichero vivo y sin
inventar densidad (asof/age_s obligatorios). Todo offline sobre tmp_path.
"""
import gzip
import importlib.util
import json
import os
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def l5(tmp_path):
    m = _load("levels_5min_archive")
    m.STATE_PATH = str(tmp_path / "state.json")
    m.HEALTH_PATH = str(tmp_path / "health.json")
    m.HIST = str(tmp_path / "history")
    src = tmp_path / "live"
    src.mkdir()
    m._SRC = str(src / "levels_*.json")
    m._SRCDIR = str(src)
    return m


def _live(mod, sym, asof, extra=None):
    d = {"sym": sym.upper(), "spot": 100.0, "asof": asof, "flip": 101.0,
         "call_wall": 105.0, "put_wall": 95.0, "regime": "NEG",
         "profile": [{"strike": 100.0, "gex": -1.0}]}
    if extra:
        d.update(extra)
    p = os.path.join(mod._SRCDIR, "levels_%s.json" % sym.lower())
    with open(p, "w") as f:
        json.dump(d, f)
    return p


T0 = 1784980800          # 2026-07-25 10:00:00 local (viernes)


def test_archiva_copia_literal_y_no_toca_el_vivo(l5):
    p = _live(l5, "qqq", T0 - 30)
    before = open(p, "rb").read()
    mtime = os.path.getmtime(p)
    h = l5.snapshot(now=T0 + 61, src_glob=l5._SRC)
    assert h["written"] == ["QQQ"]
    # el fichero vivo intacto, byte a byte y sin tocar su mtime
    assert open(p, "rb").read() == before
    assert os.path.getmtime(p) == mtime
    dst = os.path.join(l5.HIST, time.strftime("%Y-%m-%d", time.localtime(T0)),
                       "levels_qqq_%s.json" % time.strftime("%H%M", time.localtime(T0)))
    assert open(dst, "rb").read() == before


def test_slots_de_5min_no_se_pisan(l5):
    _live(l5, "qqq", T0)
    l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    _live(l5, "qqq", T0 + 300)
    h = l5.snapshot(now=T0 + 310, src_glob=l5._SRC)
    day = os.path.join(l5.HIST, time.strftime("%Y-%m-%d", time.localtime(T0)))
    files = sorted(f for f in os.listdir(day) if f.startswith("levels_qqq_"))
    assert len(files) == 2, files
    assert h["rows_today"] == 2
    rows = [json.loads(x) for x in open(os.path.join(day, l5.JSONL_NAME))]
    assert [r["slot"] for r in rows] == sorted(set(r["slot"] for r in rows))


def test_idempotente_dentro_del_mismo_slot(l5):
    _live(l5, "qqq", T0)
    l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    h = l5.snapshot(now=T0 + 20, src_glob=l5._SRC)      # misma ventana de 5 min
    assert h["written"] == [] and h["skipped_already_done"] == ["QQQ"]
    assert h["rows_today"] == 1


def test_rancidez_declarada_no_finge_densidad(l5):
    _live(l5, "qqq", T0 - 4000)                          # generador atascado > 900 s
    h = l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    assert h["stale"] and h["stale"][0]["sym"] == "QQQ"
    day = os.path.join(l5.HIST, time.strftime("%Y-%m-%d", time.localtime(T0)))
    row = json.loads(open(os.path.join(day, l5.JSONL_NAME)).readline())
    assert row["stale"] is True and row["age_s"] > 900


def test_fichero_ilegible_no_produce_linea_ni_ceros(l5):
    p = os.path.join(l5._SRCDIR, "levels_nok.json")
    with open(p, "w") as f:
        f.write("{roto")
    h = l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    assert h["written"] == [] and h["unreadable"] and h["unreadable"][0]["sym"] == "NOK"
    assert h["rows_today"] == 0                          # ni una linea inventada


def test_session_only_no_hace_nada_de_noche(l5):
    _live(l5, "qqq", T0)
    night = time.mktime(time.strptime("2026-07-25 03:00:00", "%Y-%m-%d %H:%M:%S"))
    h = l5.snapshot(now=night, session_only=True, src_glob=l5._SRC)
    assert h.get("skipped") == "fuera_de_sesion"
    assert not os.path.isdir(l5.HIST) or not os.listdir(l5.HIST)


def test_verify_cuenta_huecos(l5):
    _live(l5, "qqq", T0)
    l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    v = l5.verify(time.strftime("%Y-%m-%d", time.localtime(T0)), hist=l5.HIST)
    assert v["syms"]["QQQ"]["slots"] == 1
    assert v["syms"]["QQQ"]["gap_pct"] > 90              # 1 de 78 slots: honesto


def test_retencion_pliega_al_jsonl_y_gzipea_sin_perder_lineas(l5):
    _live(l5, "qqq", T0)
    _live(l5, "spy", T0)
    l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    date = time.strftime("%Y-%m-%d", time.localtime(T0))
    day = os.path.join(l5.HIST, date)
    rows_before = sum(1 for _ in open(os.path.join(day, l5.JSONL_NAME)))
    later = time.strftime("%Y-%m-%d", time.localtime(T0 + 3 * 86400))
    r = l5.retention(apply_=True, today=later, hist=l5.HIST)
    assert not [f for f in os.listdir(day) if f.startswith("levels_qqq_2")]
    assert l5.JSONL_NAME + ".gz" in os.listdir(day)
    assert l5.JSONL_NAME not in os.listdir(day)
    with gzip.open(os.path.join(day, l5.JSONL_NAME + ".gz"), "rt") as f:
        rows_after = sum(1 for _ in f)
    assert rows_after == rows_before
    assert all(a["applied"] for a in r["actions"])
    # el verify sigue leyendo del gz
    v = l5.verify(date, hist=l5.HIST)
    assert v["syms_covered"] == 2


def test_retencion_dry_run_no_toca_nada(l5):
    _live(l5, "qqq", T0)
    l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    day = os.path.join(l5.HIST, time.strftime("%Y-%m-%d", time.localtime(T0)))
    before = sorted(os.listdir(day))
    later = time.strftime("%Y-%m-%d", time.localtime(T0 + 3 * 86400))
    l5.retention(apply_=False, today=later, hist=l5.HIST)
    assert sorted(os.listdir(day)) == before


def test_presupuesto_duro_aborta(l5):
    _live(l5, "qqq", T0)
    l5.snapshot(now=T0 + 10, src_glob=l5._SRC)
    l5.HISTORY_BUDGET_GB = 1e-9
    with pytest.raises(RuntimeError):
        l5.retention(apply_=True, today="2026-08-01", hist=l5.HIST)


def test_ficheros_reales_del_repo_tienen_asof(l5):
    """Si chart_levels dejara de escribir asof, la rancidez seria inauditable."""
    import glob as g
    real = g.glob(os.path.join(REPO, "charts", "data", "levels_*.json"))
    if not real:
        pytest.skip("sin niveles vivos")
    d = json.load(open(real[0]))
    assert "asof" in d and isinstance(d["asof"], (int, float))
