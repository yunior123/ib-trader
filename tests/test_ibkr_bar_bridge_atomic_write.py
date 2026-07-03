"""ibkr_bar_bridge.py:147 — el NBBO se escribia con open(...,"w") directo sobre el
destino a 4/s; un lector C++ podia leer un fichero a medias. Debe ser tmp+os.replace
(patron chart_levels.py)."""
import glob
import importlib.util
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def bridge_mod():
    path = os.path.join(REPO, "scripts", "ibkr_bar_bridge.py")
    orig_argv = sys.argv
    sys.argv = ["ibkr_bar_bridge.py"]   # evita que pytest's argv contamine SYMS
    try:
        spec = importlib.util.spec_from_file_location("ibt_ibkr_bar_bridge", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.argv = orig_argv
    return mod


def _fake_tick(bid, ask):
    return types.SimpleNamespace(bid=bid, ask=ask)


def test_nbbo_write_is_atomic_no_leftover_tmp(bridge_mod, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    st = bridge_mod.SymState("NVDA")
    on_tick = bridge_mod.make_on_nbbo(st)
    on_tick(_fake_tick(100.0, 100.10))
    dst = "data/nbbo_nvda.txt"
    assert os.path.exists(dst)
    line = open(dst).read().strip()
    parts = line.split()
    assert len(parts) == 3
    assert float(parts[1]) == pytest.approx(100.0)
    assert float(parts[2]) == pytest.approx(100.10)
    # nada de temporales sueltos tras el replace
    assert glob.glob("data/nbbo_nvda.txt.tmp*") == []


def test_nbbo_write_uses_os_replace(bridge_mod, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    st = bridge_mod.SymState("QQQ")
    st.agg = {}   # evitar la rama de historia QQQ (append separado, no atomico a proposito)
    calls = []
    real_replace = os.replace

    def spy_replace(src, dst_):
        calls.append((src, dst_))
        return real_replace(src, dst_)

    monkeypatch.setattr(bridge_mod.os, "replace", spy_replace)
    on_tick = bridge_mod.make_on_nbbo(st)
    on_tick(_fake_tick(50.0, 50.05))
    assert len(calls) == 1
    src, dst_ = calls[0]
    assert dst_ == "data/nbbo_qqq.txt"
    assert src.startswith(dst_ + ".tmp")
