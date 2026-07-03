"""test_fleet_keepalive_lock.py — TODOS.md: "fleet_keepalive_start.sh:257 + nvda_keepalive.sh:31
dedup por pgrep contra un keepalive que hace pkill -x: dos arranques concurrentes = bot
asesinado cada 31s". El dedup pgrep-luego-nohup tiene una ventana TOCTOU: si dos instancias
de fleet_keepalive_start.sh corren a la vez, ambas pueden pasar el pgrep antes de que
cualquiera lance nada -> dos keepalives del mismo simbolo peleandose. Fix: mutex mkdir
(atomico, macOS no trae flock) alrededor de todo el cuerpo del script.

Sandbox real (subprocess de verdad, sin red ni bots): copia el script a un ROOT temporal
con un `fleet_hours` stub que dice "fuera de ventana" (rama silenciosa, sin osascript) y
puede dormir para simular una corrida larga.
"""
import os
import shutil
import subprocess
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "fleet_keepalive_start.sh")


def _fleet_esta_viva():
    """Mismo guardian que tests/test_fleet_hours.py:197 — el sandbox no acota `pkill`."""
    p = subprocess.run(["pgrep", "-f", "ib-trader/scripts/.*_keepalive.sh"],
                       capture_output=True, text=True)
    return p.returncode == 0


pytestmark = [
    pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh no disponible"),
    # El stub `fleet_hours` dice "fuera de ventana" -> el script corre fleet_stop_all()/
    # fleet_stop_bridges() (scripts/fleet_keepalive_start.sh:46-88), y sus `pkill` son
    # GLOBALES: matan la flota VIVA del Mac, no la del sandbox. Medido 2026-07-27 00:37
    # y 00:44: la flota cayo de 67 procesos a 8 dos veces por correr este fichero.
    pytest.mark.skipif(_fleet_esta_viva(),
                       reason="la flota esta VIVA: este fichero ejecuta fleet_stop_all "
                              "(pkill GLOBAL) y no vamos a matar una flota en marcha "
                              "desde un test"),
]


def _sandbox(tmp_path, stub_sleep=0):
    root = tmp_path / "sandbox"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    shutil.copy(SCRIPT, root / "scripts" / "fleet_keepalive_start.sh")
    fh = root / "fleet_hours"
    fh.write_text(f"#!/bin/sh\nsleep {stub_sleep}\nexit 1\n")   # 1 = FUERA DE VENTANA (silencioso)
    fh.chmod(0o755)
    return root


def _run(root):
    return subprocess.run(
        ["zsh", str(root / "scripts" / "fleet_keepalive_start.sh")],
        cwd=str(root), capture_output=True, text=True, timeout=30)


def test_dos_instancias_concurrentes_la_segunda_sale_sin_tocar_nada(tmp_path):
    """La corrida lenta (2s) sostiene el lock; la que arranca 0.3s despues debe ver
    el lock FRESCO y salir de inmediato -- nunca las dos deciden lanzar a la vez."""
    root = _sandbox(tmp_path, stub_sleep=2)

    proc_a = subprocess.Popen(["zsh", str(root / "scripts" / "fleet_keepalive_start.sh")],
                               cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.3)
    r_b = _run(root)
    proc_a.wait(timeout=30)

    log = (root / "logs" / "fleet_autostart.log").read_text() if (root / "logs" / "fleet_autostart.log").exists() else ""
    assert "OTRA instancia activa" in log, f"la segunda instancia debio ceder el paso:\n{log}"
    assert not (root / "data" / ".fleet_keepalive_start.lockd").exists(), "el lock debe liberarse siempre (trap EXIT)"


def test_corridas_secuenciales_normales_nunca_ven_lock_ajeno(tmp_path):
    """Sin solape (stub instantaneo), dos corridas seguidas jamas deben pisarse: cada
    una toma el lock, termina, y lo libera antes de que la siguiente lo pida."""
    root = _sandbox(tmp_path, stub_sleep=0)
    r1 = _run(root)
    r2 = _run(root)
    assert r1.returncode == 0 and r2.returncode == 0
    log = (root / "logs" / "fleet_autostart.log").read_text() if (root / "logs" / "fleet_autostart.log").exists() else ""
    assert "OTRA instancia activa" not in log
    assert not (root / "data" / ".fleet_keepalive_start.lockd").exists()


def test_lock_viejo_se_roba_no_se_queda_muerto_para_siempre(tmp_path):
    """Un lock huerfano (instancia anterior murio a medias) no debe dejar la flota
    apagada para siempre: pasados 120s se considera muerto y se toma."""
    root = _sandbox(tmp_path, stub_sleep=0)
    lockdir = root / "data" / ".fleet_keepalive_start.lockd"
    lockdir.mkdir()
    old = time.time() - 200
    os.utime(lockdir, (old, old))
    r = _run(root)
    assert r.returncode == 0
    log = (root / "logs" / "fleet_autostart.log").read_text()
    assert "lock viejo" in log
    assert "OTRA instancia activa" not in log
