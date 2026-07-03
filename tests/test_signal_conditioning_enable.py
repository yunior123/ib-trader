"""signal_conditioning.py:267 — la clave de apagado en duro debe coincidir con el
formato real de data/signal_enable.json ("source|SYMBOL", source en minusculas tal
cual lo normaliza conditioned_prob). Una celda enabled:false debe bloquear speak."""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_sc():
    path = os.path.join(REPO, "scripts", "signal_conditioning.py")
    spec = importlib.util.spec_from_file_location("ibt_signal_conditioning", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sc():
    return _load_sc()


def test_enable_json_key_format_is_source_pipe_symbol():
    p = os.path.join(REPO, "data", "signal_enable.json")
    d = json.load(open(p))
    assert d, "signal_enable.json vacio, no se puede validar el formato de clave"
    for k in d:
        assert "|" in k
        source, symbol = k.split("|", 1)
        assert source == source.lower()
        assert symbol == symbol.upper()


def test_disabled_cell_blocks_speak(sc, monkeypatch, tmp_path):
    enable = {"bollinger|ZZZ": {"enabled": False, "why": "test-muerta"}}
    p = tmp_path / "signal_enable.json"
    p.write_text(json.dumps(enable))
    monkeypatch.setattr(sc, "_load", lambda path, default: (
        enable if path == "data/signal_enable.json" else default))
    r = sc.conditioned_prob("bollinger", "ZZZ", 1, 80, now_min=600)
    assert r["enabled"] is False
    assert r["speak"] is False
    assert any("apagada" in w for w in r["why"])


def test_enabled_cell_does_not_block(sc, monkeypatch):
    enable = {"bollinger|ZZZ": {"enabled": True, "why": "viva"}}
    monkeypatch.setattr(sc, "_load", lambda path, default: (
        enable if path == "data/signal_enable.json" else default))
    r = sc.conditioned_prob("bollinger", "ZZZ", 1, 80, now_min=600)
    assert r["enabled"] is True


def test_source_case_and_symbol_case_normalized_before_lookup(sc, monkeypatch):
    # Caller pasa "Bollinger"/"zzz": conditioned_prob normaliza antes de construir
    # la clave, asi que debe seguir encontrando la celda "bollinger|ZZZ".
    enable = {"bollinger|ZZZ": {"enabled": False, "why": "test"}}
    monkeypatch.setattr(sc, "_load", lambda path, default: (
        enable if path == "data/signal_enable.json" else default))
    r = sc.conditioned_prob("Bollinger", "zzz", 1, 80, now_min=600)
    assert r["enabled"] is False
