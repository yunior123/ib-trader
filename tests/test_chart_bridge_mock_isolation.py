#!/usr/bin/env python3
"""test_chart_bridge_mock_isolation.py — probar la UI no puede contaminar la muestra.

BUG MEDIDO el 2026-07-25. `_log_structural()` y `_signals_file_line()` escriben a DOS
destinos de PRODUCCION:
  1. la tabla `signals` de `trades.db` (source='structural') = la poblacion del backtest,
  2. `data/trading-signals/<fecha>.txt` = el canal de voz/telefono (notify_relay.sh).
Y lo hacian SIN mirar si el bridge corria con `--mock`.

Consecuencia medida en la BD: de las **89** filas `source='structural'`, **7 eran de un
sabado con el mercado CERRADO** (8% de la poblacion entera) — 4 de QQQ con el precio
congelado repitiendo 694.0, y 3 de NVDA girando ↑34% -> pin -> ↓67% en 30 segundos. Un
backtest no puede etiquetar una señal emitida a mercado cerrado: no existe el retorno
futuro que mediria, asi que la etiqueta que sale es ficcion. Y `structural` es justo la
fuente que habiamos medido con WR alto sobre n=5.

La via documentada para probar el chart sin TWS es `chart_bridge.py --mock`. Probar es
obligatorio; no puede costar ni una fila de muestra ni una llamada al telefono.
"""
import importlib.util
import os
import sqlite3

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def cb():
    spec = importlib.util.spec_from_file_location("cb_mock_iso",
                                                  os.path.join(REPO, "scripts", "chart_bridge.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _FakeState:
    """Lo minimo que tocan las dos funciones."""
    def __init__(self, mock):
        self.mock = mock
        self.sym = "nvda"   # _log_structural gatea por _session_open(state.sym) desde 2026-07-28


SIG = {"kind": "magnet", "sym": "nvda", "price": 212.5, "prob": 67,
       "text": "NVDA se dirige a su imán 212.5 ↓"}


def _sandbox(cb, tmp_path, monkeypatch):
    """Reapunta REPO a un sandbox: si la funcion escribe, escribe AHI y lo vemos."""
    monkeypatch.setattr(cb, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir(exist_ok=True)   # la BD vive en data/ desde la reorg 2026-07-29
    db = tmp_path / "data/trades.db"
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE signals (ts_epoch REAL, ts_txt TEXT, date TEXT, kind TEXT,
                 symbol TEXT, price REAL, priority TEXT, source TEXT, msg TEXT, raw TEXT)""")
    c.commit(); c.close()
    return db


def _rows(db):
    c = sqlite3.connect(db)
    n = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    c.close()
    return n


def _sigfile_lines(tmp_path):
    d = tmp_path / "data" / "trading-signals"
    if not d.exists():
        return []
    return [ln for f in d.iterdir() for ln in f.read_text().splitlines()]


def test_mock_no_escribe_en_la_tabla_signals(cb, tmp_path, monkeypatch):
    """En --mock la poblacion del backtest no crece ni en una fila."""
    db = _sandbox(cb, tmp_path, monkeypatch)
    cb._log_structural(_FakeState(mock=True), SIG)
    assert _rows(db) == 0, "el modo de pruebas metio una fila en la muestra del backtest"


def test_mock_no_escribe_en_el_canal_de_voz(cb, tmp_path, monkeypatch):
    """En --mock no se toca data/trading-signals/<fecha>.txt (voz + telefono)."""
    _sandbox(cb, tmp_path, monkeypatch)
    cb._log_structural(_FakeState(mock=True), SIG)
    assert _sigfile_lines(tmp_path) == [], "el modo de pruebas escribio en el canal de voz"


def test_vivo_si_escribe_ambos_destinos(cb, tmp_path, monkeypatch):
    """CONTROL: sin --mock el camino real sigue registrando en los dos sitios.

    Sin este control el test de arriba pasaria con una funcion que no escribe NUNCA."""
    db = _sandbox(cb, tmp_path, monkeypatch)
    monkeypatch.setattr(cb, "_session_open", lambda sym: True)   # el control no depende de la hora del reloj
    cb._log_structural(_FakeState(mock=False), SIG)
    assert _rows(db) == 1, "el camino vivo dejo de registrar en la BD"
    lines = _sigfile_lines(tmp_path)
    assert len(lines) == 1 and "ESTRUCTURAL" in lines[0] and "NVDA" in lines[0]


def test_zona_en_mock_no_dispara_ficha_a_produccion(cb, tmp_path, monkeypatch):
    """El feed sintetico cruza zonas; la ficha NO puede salir por el canal de voz."""
    _sandbox(cb, tmp_path, monkeypatch)
    monkeypatch.setattr(cb, "MOCK", True)
    cb._signals_file_line("nvda", "compra 212.5 stop 211")
    assert _sigfile_lines(tmp_path) == [], "una zona en modo pruebas disparo ficha real"


def test_zona_viva_si_escribe(cb, tmp_path, monkeypatch):
    """CONTROL del anterior."""
    _sandbox(cb, tmp_path, monkeypatch)
    monkeypatch.setattr(cb, "MOCK", False)
    cb._signals_file_line("nvda", "compra 212.5 stop 211")
    lines = _sigfile_lines(tmp_path)
    assert len(lines) == 1 and "ZONA" in lines[0]


def test_flag_mock_se_propaga_desde_los_argumentos(cb, monkeypatch):
    """`--mock` en la linea de comandos debe fijar el global MOCK.

    La guarda de `_signals_file_line` es por global (la funcion no recibe `state`), asi que
    si `build_state_and_feed` no lo propaga, la guarda no existe en la practica."""
    monkeypatch.setattr(cb, "MOCK", False)

    class Args:
        mock = True
        sym = "qqq"
        interval = 1.0
    monkeypatch.setattr(cb, "load_levels", lambda s: {})
    try:
        cb.build_state_and_feed(Args())
    except Exception:
        pass          # nos da igual si falla mas adelante; lo que se prueba es el global
    assert cb.MOCK is True, "--mock no llego al global: la guarda de zonas no protege nada"
