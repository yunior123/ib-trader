"""trace_cube: el eje de tiempo del panel TRACE sale de las fotos de cadena REALES.

Offline: cubo sintetico en tmp_path + una lectura de las 66 fotos reales de SPY del
2026-07-31 que hay en data/history (si el dia sigue en el repo).
"""
import importlib.util
import json
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
def tc():
    return _load("trace_cube")


HDR = "# opt_chain FAKE | epoch %d | %s | spot %.2f | exps 20260731\n" \
      "# strike right exp bid ask vol oi iv delta gamma\n"


def _snap(spot, epoch, greeks=True):
    out = HDR % (epoch, "2026-07-31 09:35:00", spot)
    for strike, oi_c, oi_p, gamma in ((100.0, 500, 300, 0.020), (101.0, 200, 800, 0.015)):
        g = "%.4f" % gamma if greeks else "-1.0000"
        iv = "0.2500" if greeks else "-1.0000"
        out += "%.2f C 20260731 1.00 1.10 10 %d %s 0.5000 %s\n" % (strike, oi_c, iv, g)
        out += "%.2f P 20260731 1.00 1.10 10 %d %s -0.5000 %s\n" % (strike, oi_p, iv, g)
    return out


@pytest.fixture
def hist(tmp_path):
    day = tmp_path / "2026-07-31"
    day.mkdir()
    # 09:35 y 10:35 con griegas, 09:55 SIN griegas (columna de gex vacia). Se escriben
    # desordenadas a proposito: el cubo tiene que ordenarlas por epoch.
    (day / "opt_chain_fake_1035.txt").write_text(_snap(101.5, 1785508500))
    (day / "opt_chain_fake_0935.txt").write_text(_snap(100.5, 1785504900))
    (day / "opt_chain_fake_0955.txt").write_text(_snap(101.0, 1785506100, greeks=False))
    return tmp_path


def test_columns_sorted_by_epoch(tc, hist):
    m = tc.build_cube("FAKE", "2026-07-31", hist_dir=hist)["meta"]
    assert m["epochs"] == sorted(m["epochs"]) == [1785504900, 1785506100, 1785508500]
    assert m["columns"] == 3
    assert m["spots"] == [100.5, 101.0, 101.5]
    assert len(m["labels"]) == 3


def test_snapshot_without_greeks_leaves_an_empty_column_not_zeros(tc, hist):
    cube = tc.build_cube("FAKE", "2026-07-31", hist_dir=hist)
    dead = 1785506100
    gex, netoi = cube["cells"]["gex"], cube["cells"]["netoi"]
    assert not [k for k in gex if k.endswith("|%d" % dead)]          # VACIA, no ceros
    assert [k for k in netoi if k.endswith("|%d" % dead)]            # el OI si esta medido
    assert cube["meta"]["greeks_ok_pct"] == [1.0, 0.0, 1.0]
    assert cube["meta"]["columns_with_gex"] == 2
    # y las columnas vivas si tienen valor, con el signo de la casa (call +, put -)
    assert gex["100|1785504900"] > 0     # 500 calls vs 300 puts en el 100
    assert netoi["101|1785504900"] == 200 - 800


def test_column_values_differ_between_snapshots(tc, hist):
    cube = tc.build_cube("FAKE", "2026-07-31", hist_dir=hist)
    a = cube["cells"]["gex"]["100|1785504900"]
    b = cube["cells"]["gex"]["100|1785508500"]
    assert a != b                                    # el spot cambia -> el GEX cambia
    assert cube["meta"]["intraday_variation"]["gex"] == 1.0
    assert cube["meta"]["intraday_variation"]["netoi"] == 0.0   # el OI de IBKR es T+1


def test_atomic_write(tc, hist, tmp_path, monkeypatch):
    out = tmp_path / "data"
    out.mkdir()
    cube = tc.build_cube("FAKE", "2026-07-31", hist_dir=hist)
    real_replace = os.replace
    seen = {}

    def spy(src, dst):
        seen["tmp"] = src
        assert not os.path.exists(dst)      # el destino aparece de golpe, no a medias
        real_replace(src, dst)

    monkeypatch.setattr(tc.os, "replace", spy)
    path = tc.write_cube(cube, str(out))
    assert seen["tmp"].startswith(path) and seen["tmp"] != path
    assert json.loads(open(path).read())["meta"]["sym"] == "FAKE"
    assert not [p for p in os.listdir(out) if ".tmp." in p]


def test_fail_loud_without_snapshots(tc, tmp_path):
    (tmp_path / "2026-07-31").mkdir()
    with pytest.raises(ValueError):
        tc.build_cube("FAKE", "2026-07-31", hist_dir=tmp_path)
    with pytest.raises(ValueError):
        tc.build_cube("FAKE", "1999-01-01", hist_dir=tmp_path)


def test_snapshot_without_spot_is_dropped(tc, tmp_path):
    day = tmp_path / "2026-07-31"
    day.mkdir()
    (day / "opt_chain_fake_0935.txt").write_text(
        "# opt_chain FAKE | epoch 1785504900 | 2026-07-31 09:35:00\n"
        "# strike right exp bid ask vol oi iv delta gamma\n"
        "100.00 C 20260731 1.00 1.10 10 500 0.2500 0.5000 0.0200\n")
    with pytest.raises(ValueError):     # sin spot no se puede firmar el GEX: nada que servir
        tc.build_cube("FAKE", "2026-07-31", hist_dir=tmp_path)


REAL_DAY = "2026-07-31"


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO, "data", "history", REAL_DAY)),
    reason="dia real fuera del repo (retencion)",
)
def test_real_spy_day_has_a_real_time_axis(tc):
    cube = tc.build_cube("SPY", REAL_DAY)
    m = cube["meta"]
    assert m["columns"] >= 10, m["columns"]
    assert m["epochs"] == sorted(m["epochs"])
    assert len(set(m["epochs"])) == len(m["epochs"])
    assert m["columns_with_gex"] >= 10
    # el GEX se MUEVE de verdad a lo largo del dia (si no, seguiriamos pintando la franja plana)
    assert m["intraday_variation"]["gex"] > 0.2
    live = [k for k, v in cube["cells"]["gex"].items() if v]
    assert len(live) > 100
