"""iv_regime: el centinela -1 de las cadenas JAMAS puede salir como "IV comprimida".

Medido 2026-08-03 en data/iv_regime.json (generado el 29-jul): 11 de 26 simbolos publicaban
iv_current=-1.0 -> percentile 0 -> regime COMPRESSED, servido por el cockpit
(chart_bridge.py:3108 whitelist). Causa: se tomaba la PRIMERA fila parseable de
opt_chain_<sym>.txt y el guard era `if not iv_now` (falso solo para 0.0).
Segundo fallo del mismo fichero: build_iv_history leia data["rows"], pero el archivador de
Polygon escribe {"meta","results"} con implied_volatility -> devolvia [] SIEMPRE.
"""
import importlib.util
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mod(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    spec = importlib.util.spec_from_file_location(
        "iv_regime_mod", os.path.join(REPO, "scripts", "iv_regime.py"))
    m = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(os, "chdir", lambda p: None)  # el modulo hace chdir(REPO) al importar
    spec.loader.exec_module(m)
    return m


HEAD = ("# opt_chain X | epoch 1 | 2026-08-03 06:00:00 | spot 100 | exps 20260803\n"
        "# fuente polygon\n"
        "# strike right exp bid ask vol oi iv delta gamma\n")


def test_cadena_toda_centinela_no_da_regimen(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    (tmp_path / "data" / "opt_chain_zzz.txt").write_text(
        HEAD + "95.00 C 20260803 -1.00 -1.00 0 0 -1.0000 -1.0000 -1.000000\n"
             + "105.00 P 20260803 -1.00 -1.00 0 0 -1.0000 -1.0000 -1.000000\n")
    assert m.current_iv("ZZZ") is None
    assert m.compute_regime("ZZZ") is None


def test_ignora_centinela_y_usa_la_mediana_de_las_medidas(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    (tmp_path / "data" / "opt_chain_zzz.txt").write_text(
        HEAD + "90.00 C 20260803 -1 -1 0 0 -1.0000 -1 -1\n"
             + "100.00 C 20260803 1 2 0 0 0.2000 0.5 0.01\n"
             + "110.00 C 20260803 1 2 0 0 0.4000 0.3 0.01\n")
    assert m.current_iv("ZZZ") == 0.30000000000000004 or abs(m.current_iv("ZZZ") - 0.30) < 1e-9


def test_historia_lee_el_esquema_results_implied_volatility(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    hist = tmp_path / "data" / "history" / "2026-07-31"
    hist.mkdir(parents=True)
    (hist / "chain_full_zzz.json").write_text(json.dumps({
        "meta": {"sym": "ZZZ"},
        "results": [{"implied_volatility": 0.5}, {"implied_volatility": -1}, {"greeks": {}}],
    }))
    assert m.build_iv_history("ZZZ") == [0.5]


def test_historia_ignora_carpeta_de_domingo(tmp_path, monkeypatch):
    m = _mod(tmp_path, monkeypatch)
    base = tmp_path / "data" / "history"
    for d, iv in (("2026-07-31", 0.5), ("2026-08-02", 9.9)):   # 08-02 = domingo
        (base / d).mkdir(parents=True)
        (base / d / "chain_full_zzz.json").write_text(
            json.dumps({"results": [{"implied_volatility": iv}]}))
    assert m.build_iv_history("ZZZ") == [0.5]
