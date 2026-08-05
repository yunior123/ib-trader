"""Veto capitan del fade bb-rebote SHORT (regla 12) — solo se cargan las funciones
via AST, jamas el daemon top-level."""
import ast
import json
import os
import subprocess
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "scripts", "bollinger_alarm.py")


def load_veto_ns():
    tree = ast.parse(open(SRC).read())
    wanted = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in ("bars_of", "captain_over_flip"):
            wanted.append(n)
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "CAPTAIN_SEMIS" for t in n.targets):
            wanted.append(n)
    mod = ast.Module(body=wanted, type_ignores=[])
    ast.fix_missing_locations(mod)
    ns = {"os": os, "json": json, "time": time}
    exec(compile(mod, SRC, "exec"), ns)
    assert "captain_over_flip" in ns and "CAPTAIN_SEMIS" in ns
    return ns


def make_repo(tmp_path, spy=772.0, qqq=722.0, smh=566.0, age_s=30, snapshot=True):
    (tmp_path / "data").mkdir(exist_ok=True)
    now = int(time.time()) - age_s
    for sym, px in (("spy", spy), ("qqq", qqq), ("smh", smh)):
        (tmp_path / "data" / f"bars_{sym}_ibkr.txt").write_text(
            f"{now} {px} {px} {px} {px} 100\n")
    if snapshot:
        (tmp_path / "data" / "gex_snapshot.json").write_text(json.dumps({
            "SPY": {"flip": 761.48}, "QQQ": {"flip": 697.4}, "SMH": {"flip": 588.56}}))


def test_flag_apagado_no_veta_nunca(tmp_path, monkeypatch):
    ns = load_veto_ns()
    make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IBT_BB_CAPTAIN_VETO", raising=False)
    assert ns["captain_over_flip"]("aapl") is False


def test_capitan_mercado_sobre_flip_veta_nombre_no_semi(tmp_path, monkeypatch):
    ns = load_veto_ns()
    make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IBT_BB_CAPTAIN_VETO", "1")
    assert ns["captain_over_flip"]("aapl") is True


def test_semi_responde_a_smh_no_a_spy(tmp_path, monkeypatch):
    # SMH bajo su flip: el fade de MU sigue sonando aunque SPY/QQQ esten sobre flip
    ns = load_veto_ns()
    make_repo(tmp_path, smh=566.0)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IBT_BB_CAPTAIN_VETO", "1")
    assert ns["captain_over_flip"]("mu") is False
    make_repo_smh_up = tmp_path / "data" / "bars_smh_ibkr.txt"
    make_repo_smh_up.write_text(f"{int(time.time()) - 30} 590 590 590 590 100\n")
    assert ns["captain_over_flip"]("mu") is True


def test_degradacion_limpia_sin_snapshot_y_sin_barra_fresca(tmp_path, monkeypatch):
    ns = load_veto_ns()
    make_repo(tmp_path, snapshot=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IBT_BB_CAPTAIN_VETO", "1")
    assert ns["captain_over_flip"]("aapl") is False    # sin gex_snapshot.json
    make_repo(tmp_path, age_s=999)                     # barra rancia >240s
    assert ns["captain_over_flip"]("aapl") is False


def test_camino_vetado_es_banner_sin_voz():
    src = open(SRC).read()
    assert 'say("🎈 BB REBOTE [VETO capitan]", msge, voice=False, push=False)' in src
    assert 'side == "up" and captain_over_flip(sym)' in src


def test_backtest_veto_reproduce_dia(tmp_path):
    if not os.path.exists(os.path.join(REPO, "data", "trading-signals", "2026-08-04.txt")):
        pytest.skip("sin registro del 2026-08-04")
    out = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "backtest_bb_captain_veto.py"),
                          "--day", "2026-08-04"], capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0, out.stderr
    assert "bb-rebote SHORT" in out.stdout and "veto sector" in out.stdout
