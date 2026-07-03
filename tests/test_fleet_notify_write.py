"""test_fleet_notify_write.py — arnes Python para tests/test_fleet_notify_write.cpp.

Python es SOLO el arnes (ley de la casa): compila el .cpp con ASan/UBSan en un
directorio efimero y corre el binario. El bug (fleet_notify.h:54, lectura fuera del
buffer "line" en write()) se manifiesta como abort de AddressSanitizer; la fix lo
elimina. Cero computo del bug en Python.
"""
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "tests", "test_fleet_notify_write.cpp")

pytestmark = pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ no disponible")


def test_desktop_mirror_no_oob_read_on_truncated_message(tmp_path):
    binp = tmp_path / "fleet_notify_test"
    cc = subprocess.run(
        ["clang++", "-std=c++2c", "-O0", "-g", "-fsanitize=address,undefined",
         "-Wall", "-Wextra", "-o", str(binp), SRC],
        capture_output=True, text=True, timeout=120,
    )
    assert cc.returncode == 0, f"compilacion fallo:\n{cc.stderr}"
    # (el harness solo usa fleet_notify_desktop_mirror; -Wunused-function sobre las
    # otras funciones static del header es ruido del arnes, no del fix bajo prueba)

    sandbox = tmp_path / "sandbox"
    (sandbox / "data").mkdir(parents=True)   # mkdir() del header no es recursivo
    env = dict(os.environ)
    env["HOME"] = str(sandbox)
    r = subprocess.run([str(binp)], cwd=sandbox, capture_output=True, text=True,
                        env=env, timeout=30)
    assert r.returncode == 0, (
        f"crash/ASan abort — probable lectura fuera de 'line' en write():\n{r.stderr}")
    assert "AddressSanitizer" not in r.stderr
    assert "SIN CRASH" in r.stdout

    written = sandbox / "data" / "trading-signals"
    files = list(written.glob("*.txt")) if written.exists() else []
    assert files, "fleet_notify_desktop_mirror no escribio el espejo Desktop"
    # 2 escrituras acotadas a <1200 bytes de "line" cada una (la larga se trunca SIN
    # arrastrar memoria de stack de fuera del buffer, que es lo que el fix impide).
    total = sum(f.stat().st_size for f in files)
    assert total < 2 * 1200, "el fichero crecio mas de lo que 2 escrituras acotadas permiten"
