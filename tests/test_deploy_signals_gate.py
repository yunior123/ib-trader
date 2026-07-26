"""deploy_signals_to_data.sh — portero de ventana (Yunior 2026-07-26): pkill sin
guarda mataba la flota en sesion viva. Ejecuta el script REAL en un repo temporal
con fleet_hours/pkill/nohup/sleep/clang++ stubeados (cero riesgo de matar procesos
reales o compilar nada) y verifica el gate."""
import os
import shutil
import stat
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY_SCRIPT = os.path.join(REPO, "scripts", "deploy_signals_to_data.sh")

pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh no disponible")


def _make_exec(path, content):
    with open(path, "w") as f:
        f.write(content)
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _scaffold(tmp_path, fleet_hours_exit):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "data" / "trading-signals").mkdir(parents=True)
    shutil.copy(DEPLOY_SCRIPT, root / "scripts" / "deploy_signals_to_data.sh")
    _make_exec(str(root / "fleet_hours"), f"#!/bin/sh\nexit {fleet_hours_exit}\n")
    binp = tmp_path / "stubbin"
    binp.mkdir()
    for name in ("pkill", "nohup", "sleep", "python3", "clang++"):
        _make_exec(str(binp / name), "#!/bin/sh\nexit 0\n")
    return root, binp


def _run(root, binp, args=()):
    env = dict(os.environ)
    env["PATH"] = f"{binp}:{env['PATH']}"
    return subprocess.run(
        ["zsh", "scripts/deploy_signals_to_data.sh", *args],
        cwd=root, env=env, capture_output=True, text=True, timeout=30,
    )


def test_live_window_aborts_without_force(tmp_path):
    root, binp = _scaffold(tmp_path, fleet_hours_exit=0)  # 0 = LIVE
    r = _run(root, binp)
    assert r.returncode == 1
    assert "ABORTADO" in r.stdout
    assert "recompilando" not in r.stdout  # nunca llega al pkill/compile


def test_live_window_proceeds_with_force(tmp_path):
    root, binp = _scaffold(tmp_path, fleet_hours_exit=0)
    r = _run(root, binp, args=("--force",))
    assert r.returncode == 0
    assert "recompilando" in r.stdout
    assert "ABORTADO" not in r.stdout


def test_dead_window_proceeds_without_force(tmp_path):
    root, binp = _scaffold(tmp_path, fleet_hours_exit=1)  # 1 = DEAD
    r = _run(root, binp)
    assert r.returncode == 0
    assert "recompilando" in r.stdout
    assert "ABORTADO" not in r.stdout


def test_missing_portero_aborts_loud(tmp_path):
    root, binp = _scaffold(tmp_path, fleet_hours_exit=0)
    os.remove(root / "fleet_hours")
    r = _run(root, binp)
    assert r.returncode == 1
    assert "no se puede verificar" in r.stdout
