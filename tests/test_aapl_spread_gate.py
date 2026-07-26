"""test_aapl_spread_gate.py — el gate de spread debe fallar CERRADO.

BUG (2026-07-26): nbbo_spread_pct() en los 24 *_signal_bot.cpp devolvia 0 cuando
no habia NBBO vivo (fichero ausente/corrupto/stale >10s). 0 <= cualquier SPREAD_MAX
positivo, asi que la AUSENCIA de dato pasaba el gate en vez de bloquearlo. Fix:
la funcion devuelve <0 ("sin dato") y el gate bloquea si sp<0 O sp>max.

Arnes Python que compila y conduce el BINARIO REAL (aapl_signal_bot --test-nbbo-spread,
un hook de 6 lineas que reproduce el if() exacto de las lineas 1758-1761/1858-1860)
contra un data/nbbo_aapl.txt sintetico en un sandbox aislado. Cero computo del gate
en Python; el parche es identico byte a byte en los 24 bots (ver commit).
"""
import os
import subprocess
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "aapl_signal_bot.cpp")

pytestmark = pytest.mark.skipif(not os.path.exists(SRC), reason="falta aapl_signal_bot.cpp")


def _wait_clang(timeout=600):
    import shutil
    if not shutil.which("pgrep"):
        return
    waited = 0
    while waited < timeout:
        r = subprocess.run(["pgrep", "-x", "clang++"], capture_output=True, text=True)
        if r.returncode != 0:
            return
        time.sleep(5)
        waited += 5


@pytest.fixture(scope="module")
def binp(tmp_path_factory):
    _wait_clang()
    out = tmp_path_factory.mktemp("bin") / "aapl_signal_bot_test"
    arch = "-march=native" if os.uname().machine == "x86_64" else "-mcpu=native"
    cc = subprocess.run(
        ["clang++", "-std=c++2c", "-O3", arch, "-Wall", "-Wextra", "-o", str(out), SRC],
        capture_output=True, text=True, timeout=180,
    )
    assert cc.returncode == 0, f"compilacion fallo:\n{cc.stderr}"
    assert cc.stderr.strip() == "", f"warnings no permitidos:\n{cc.stderr}"
    return out


def _run(binp, sandbox, nbbo_line=None, spread_max="0.5"):
    data = sandbox / "data"
    data.mkdir(exist_ok=True)
    nbbo = data / "nbbo_aapl.txt"
    if nbbo_line is None:
        if nbbo.exists():
            nbbo.unlink()
    else:
        nbbo.write_text(nbbo_line)
    env = dict(os.environ)
    if spread_max is not None:
        env["AAPL_SPREAD_MAX"] = spread_max
    else:
        env.pop("AAPL_SPREAD_MAX", None)
    r = subprocess.run([str(binp), "--test-nbbo-spread"], cwd=sandbox,
                        capture_output=True, text=True, env=env, timeout=10)
    assert r.returncode == 0, r.stderr
    out = dict(kv.split("=") for kv in r.stdout.split())
    return float(out["sp"]), int(out["blocked"])


def test_missing_nbbo_file_blocks(tmp_path, binp):
    sp, blocked = _run(binp, tmp_path, nbbo_line=None)
    assert sp < 0
    assert blocked == 1, "sin NBBO debe fallar CERRADO (bloquear), no abierto"


def test_stale_nbbo_blocks(tmp_path, binp):
    stale_epoch = int(time.time()) - 3600
    sp, blocked = _run(binp, tmp_path, nbbo_line=f"{stale_epoch} 100.00 100.10\n")
    assert sp < 0
    assert blocked == 1


def test_corrupt_nbbo_ask_below_bid_blocks(tmp_path, binp):
    now = int(time.time())
    sp, blocked = _run(binp, tmp_path, nbbo_line=f"{now} 100.00 99.00\n")
    assert sp < 0
    assert blocked == 1


def test_fresh_narrow_spread_passes(tmp_path, binp):
    now = int(time.time())
    sp, blocked = _run(binp, tmp_path, nbbo_line=f"{now} 100.00 100.10\n")
    assert sp == pytest.approx(0.0999, abs=1e-3)
    assert blocked == 0


def test_fresh_wide_spread_blocks(tmp_path, binp):
    now = int(time.time())
    sp, blocked = _run(binp, tmp_path, nbbo_line=f"{now} 100.00 102.00\n")
    assert sp > 0.5
    assert blocked == 1


def test_gate_disabled_when_spread_max_zero(tmp_path, binp):
    # SPREAD_MAX<=0 (default, feature off) -> gate no aplica, jamas bloquea
    sp, blocked = _run(binp, tmp_path, nbbo_line=None, spread_max=None)
    assert blocked == 0
