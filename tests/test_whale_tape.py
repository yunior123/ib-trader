#!/usr/bin/env python3
"""test_whale_tape.py — reparto DELIBERADO de la cinta tick-by-tick y declaracion de CIEGOS.

Contexto medido 2026-07-27 (mercado abierto, flota viva): el cupo tick-by-tick de IBKR es de
5 contratos DISTINTOS POR CUENTA (no por conexion) — el 6o da 10190 venga de donde venga, y un
contrato ya suscrito por otro cliente se concede gratis. Con 30 simbolos y cupo 5, el reparto se
ELIGE (capitanes + mas flujo), y quien queda fuera SALE DECLARADO ciego, no en silencio: un
whale_<sym>.txt de 0 bytes es indistinguible de 'no hay ballenas' (patron prohibido de la casa).
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(argv_syms, daemon=True):
    # produccion resuelve ib_mode porque Python mete el dir del script (scripts/) en sys.path;
    # al cargar por spec hay que anadirlo a mano.
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    argv = ["ibkr_bar_bridge.py"] + (["--daemon"] if daemon else []) + list(argv_syms)
    old = sys.argv
    sys.argv = argv
    try:
        spec = importlib.util.spec_from_file_location(
            "bbridge_tape", os.path.join(REPO, "scripts", "ibkr_bar_bridge.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except ImportError as e:
        pytest.skip(f"ib_async no disponible: {e}")
    finally:
        sys.argv = old


def test_fleet_txt_parsea_por_PALABRAS_no_por_lineas():
    """fleet.txt es UNA linea de 30 palabras. Leer por lineas da 1 token y hace creer que 29
    simbolos no estan en la flota (error medido 2026-07-27). .read().split() = 30."""
    p = os.path.join(REPO, "data", "fleet.txt")
    words = open(p).read().split()
    assert len(words) >= 30, f"fleet.txt no tiene la flota entera: {len(words)}"
    lines = [ln for ln in open(p).read().splitlines() if ln.strip()]
    assert len(lines) == 1, "fleet.txt deberia ser UNA linea (por eso split por palabras)"
    assert len(words) > len(lines), "la trampa: por lineas da 1, por palabras da 30"


def test_dollar_vol_none_sin_barras(tmp_path, monkeypatch):
    """dollar_vol_per_min devuelve None (no 0.0) cuando no hay barras: un 0 plausible mandaria
    al simbolo al fondo del reparto como si no cotizara — ley #3."""
    m = _load(["QQQ", "SPY", "SMH", "NVDA", "MU"])
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    assert m.dollar_vol_per_min("NOPE") is None          # fichero ausente
    open("data/bars_empty_ibkr.txt", "w").close()
    assert m.dollar_vol_per_min("EMPTY") is None          # fichero vacio


def test_dollar_vol_mediano(tmp_path, monkeypatch):
    m = _load(["QQQ", "SPY", "SMH", "NVDA", "MU"])
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    # 3 barras: px*vol = 100*10=1000, 100*30=3000, 100*20=2000 -> mediana 2000
    with open("data/bars_xyz_ibkr.txt", "w") as f:
        f.write("1000 100 100 100 100 10\n")
        f.write("1060 100 100 100 100 30\n")
        f.write("1120 100 100 100 100 20\n")
    assert m.dollar_vol_per_min("XYZ") == 2000.0


def test_tape_order_capitanes_primero_luego_por_flujo(tmp_path, monkeypatch):
    """Capitanes al frente (regla 12); el resto por USD/min MEDIDO desc; los sin-medir al final."""
    syms = ["QQQ", "SPY", "SMH", "MU", "NVDA", "AAPL"]
    m = _load(syms)
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)

    def bars(sym, dv):
        with open(f"data/bars_{sym.lower()}_ibkr.txt", "w") as f:
            f.write(f"1000 100 100 100 100 {dv/100:.0f}\n")

    bars("NVDA", 9_000_000)
    bars("MU", 1_000_000)
    # AAPL sin barras -> sin-medir -> ultimo
    order, dv = m.tape_order(syms)
    assert order[:3] == ["QQQ", "SPY", "SMH"], f"capitanes no primeros: {order}"
    assert order[3] == "NVDA" and order[4] == "MU", f"flujo mal ordenado: {order}"
    assert order[-1] == "AAPL", f"el sin-medir deberia ir ultimo: {order}"
    assert dv["AAPL"] is None


def test_tape_order_es_permutacion(tmp_path, monkeypatch):
    syms = ["QQQ", "SPY", "SMH", "MU", "NVDA", "AAPL", "AMD", "TSLA"]
    m = _load(syms)
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    order, _ = m.tape_order(syms)
    assert sorted(order) == sorted(syms)
    assert len(order) == len(set(order))


def test_declare_blind_escribe_fichero_y_deduplica(tmp_path, monkeypatch):
    """El ciego sale a data/tape_blind.txt con EPOCH SYM MOTIVO; la voz/banner se canta UNA vez
    al dia por simbolo (dedupe), pero el fichero se reescribe siempre con el estado actual."""
    m = _load(["QQQ", "SPY", "SMH", "NVDA", "MU"])
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    # evitar osascript/speak en el test
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: None)
    m.declare_blind(["AAPL", "AMD", "TSM"], "cupo_cuenta_5_contratos")
    assert os.path.exists(m.BLIND_F)
    rows = [ln for ln in open(m.BLIND_F).read().splitlines() if not ln.startswith("#")]
    syms = sorted(r.split()[1] for r in rows)
    assert syms == ["AAPL", "AMD", "TSM"]
    # cada linea: EPOCH (digito) SYM MOTIVO
    for r in rows:
        t = r.split()
        assert t[0].replace(".", "").isdigit() and len(t) >= 3
    # segunda llamada mismo dia: no re-canta (dedupe interno) pero reescribe el fichero
    m.declare_blind(["AAPL"], "cupo_cuenta_5_contratos")
    rows2 = [ln for ln in open(m.BLIND_F).read().splitlines() if not ln.startswith("#")]
    assert sorted(r.split()[1] for r in rows2) == ["AAPL"]


def test_declare_blind_vacio_no_rompe(tmp_path, monkeypatch):
    """Flota entera con cinta (cupo suficiente) -> lista vacia -> ni error ni voz."""
    m = _load(["QQQ", "SPY", "SMH", "NVDA", "MU"])
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    calls = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: calls.append(a))
    m.declare_blind([], "sin_ciegos")
    # fichero escrito (solo cabecera), sin voz
    assert os.path.exists(m.BLIND_F)
    assert calls == []
