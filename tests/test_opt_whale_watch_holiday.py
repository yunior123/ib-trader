"""opt_whale_watch.py:41 — in_session() solo miraba lun-vie, cero calendario de
festivos. Debe reutilizar em_envelope.is_market_day (misma tabla que
fleet_healthcheck.sessions_since) en vez de escribir una lista de festivos aparte."""
import importlib.util
import os
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ib_insync = pytest.importorskip("ib_insync")


def _load_opt_whale_watch():
    # opt_whale_watch.py corre un `while True:` a nivel de modulo (conecta a IB de
    # verdad) SIN guarda `if __name__ == "__main__":` — importarlo entero cuelga el
    # test. Se ejecuta solo el prefijo (imports + in_session + state) cortando ANTES
    # del watchdog: su hilo daemon hacia os._exit(1) DENTRO de pytest a los 300s
    # (mataba la suite entera sin resumen, cazado 2026-07-28).
    path = os.path.join(REPO, "scripts", "opt_whale_watch.py")
    src = open(path).read()
    marker = "\ndef _watchdog"
    idx = src.index(marker)
    prefix = src[:idx]
    ns = {"__name__": "ibt_opt_whale_watch", "__file__": path}
    exec(compile(prefix, path, "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def whale_mod():
    ns = _load_opt_whale_watch()
    return type("Mod", (), ns)


def _struct(year, month, day, hour, minute, wday):
    return time.struct_time((year, month, day, hour, minute, 0, wday, 1, 0))


def test_monday_holiday_labor_day_is_not_session(whale_mod, monkeypatch):
    # 2026-09-07 es Labor Day (festivo NYSE) y ademas lunes -> tm_wday=0 (weekday).
    monkeypatch.setattr(whale_mod.time, "localtime",
                         lambda *a: _struct(2026, 9, 7, 10, 0, 0))
    assert whale_mod.in_session() is False


def test_regular_monday_during_rth_is_session(whale_mod, monkeypatch):
    # 2026-07-27 es lunes normal, sin festivo.
    monkeypatch.setattr(whale_mod.time, "localtime",
                         lambda *a: _struct(2026, 7, 27, 10, 0, 0))
    assert whale_mod.in_session() is True


def test_weekend_is_not_session(whale_mod, monkeypatch):
    monkeypatch.setattr(whale_mod.time, "localtime",
                         lambda *a: _struct(2026, 7, 25, 10, 0, 5))  # sabado
    assert whale_mod.in_session() is False


def test_outside_rth_hours_is_not_session(whale_mod, monkeypatch):
    monkeypatch.setattr(whale_mod.time, "localtime",
                         lambda *a: _struct(2026, 7, 27, 8, 0, 0))
    assert whale_mod.in_session() is False


def test_uses_shared_calendar_source(whale_mod):
    assert whale_mod.em_envelope.is_market_day.__module__.endswith("em_envelope")
