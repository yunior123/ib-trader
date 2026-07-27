"""flip_migration_trail (gex_core) + flip_history (gex_snapshot) -- TODOS.md "buildeable ya":
polilinea del flip archivado cada 5min, forma horizontal/inclinada/dentada. MEDIDO antes de
construir: 0 hits de migration/flip_trail en scripts/ y charts/.

Lo que se fija aqui: <3 puntos validos NUNCA se etiqueta con una forma (insuficiente_datos,
no un shape fabricado); los umbrales de forma son CONVENCION declarada, no medidos; y
flip_history nunca revienta si falta el fichero de un dia (fin de semana, dia sin cron).
"""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core as G           # noqa: E402


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gs():
    return _load("gex_snapshot")


def test_menos_de_3_puntos_es_insuficiente_no_una_forma():
    r = G.flip_migration_trail([(0, 700.0), (300, 701.0)])
    assert r["status"] == "insuficiente_datos"
    assert r["shape"] is None
    assert r["n"] == 2


def test_cero_puntos():
    r = G.flip_migration_trail([])
    assert r == {"n": 0, "trail": [], "shape": None, "status": "insuficiente_datos"}


def test_flip_nulo_se_filtra_no_cuenta_como_punto():
    pts = [(0, 700.0), (300, None), (600, 701.0)]
    r = G.flip_migration_trail(pts)
    assert r["n"] == 2
    assert r["status"] == "insuficiente_datos"


def test_horizontal_flip_estable():
    pts = [(i * 300, 700.0 + (0.05 if i % 2 == 0 else -0.05)) for i in range(10)]
    r = G.flip_migration_trail(pts)
    assert r["shape"] == "horizontal"
    assert r["status"] == "ok"
    assert r["range_pct"] < 0.15


def test_inclinada_deriva_monotona():
    pts = [(i * 300, 700.0 + i * 0.6) for i in range(10)]
    r = G.flip_migration_trail(pts)
    assert r["shape"] == "inclinada"
    assert r["drift_pct"] > 0


def test_dentada_zigzag_regimen_no_fiable():
    pts = [(i * 300, 700.0 + (3 if i % 2 == 0 else -3)) for i in range(10)]
    r = G.flip_migration_trail(pts)
    assert r["shape"] == "dentada"
    assert r["reversal_rate"] > 0.5


def test_trail_ordenado_por_ts_aunque_llegue_desordenado():
    pts = [(600, 705.0), (0, 700.0), (300, 702.0)]
    r = G.flip_migration_trail(pts)
    assert [t for t, _ in r["trail"]] == [0, 300, 600]


def test_flip_history_sin_fichero_de_ningun_dia_da_lista_vacia(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    assert gs.flip_history("QQQ") == []


def test_flip_history_filtra_por_simbolo_y_descarta_stale(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    d = tmp_path / "data" / "history" / "2026-07-25"
    d.mkdir(parents=True)
    rows = [
        {"sym": "QQQ", "ts": 100, "stale": False, "levels": {"flip": 700.0}},
        {"sym": "SPY", "ts": 100, "stale": False, "levels": {"flip": 740.0}},
        {"sym": "QQQ", "ts": 400, "stale": True, "levels": {"flip": 701.0}},
        {"sym": "QQQ", "ts": 700, "stale": False, "levels": {"flip": None}},
        {"sym": "QQQ", "ts": 1000, "stale": False, "levels": {"flip": 702.0}},
    ]
    (d / "levels_5m.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = gs.flip_history("QQQ")
    assert out == [(100, 700.0), (1000, 702.0)]


def test_flip_history_ignora_linea_corrupta(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    d = tmp_path / "data" / "history" / "2026-07-25"
    d.mkdir(parents=True)
    good = {"sym": "QQQ", "ts": 100, "stale": False, "levels": {"flip": 700.0}}
    (d / "levels_5m.jsonl").write_text("{esto no es json\n" + json.dumps(good) + "\n")
    assert gs.flip_history("QQQ") == [(100, 700.0)]
