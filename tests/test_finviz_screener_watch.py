import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts" / "finviz_screener_watch.cpp"


@pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ no disponible")
def test_cpp_selftest_parsea_weather_y_perfiles(tmp_path):
    out = tmp_path / "finviz_screener_watch"
    subprocess.run([
        "clang++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-pedantic",
        "-o", str(out), str(SRC), "-lcurl",
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    run = subprocess.run([str(out), "--selftest"], cwd=ROOT, check=True,
                         capture_output=True, text=True)
    assert "selftest OK" in run.stdout


def test_tres_instancias_estan_cableadas_en_la_flota():
    fleet = (ROOT / "scripts" / "fleet_keepalive_start.sh").read_text()
    keep = (ROOT / "scripts" / "finviz_screener_keepalive.sh").read_text()
    for screen in ("buffett", "squeeze", "momentum"):
        assert screen in fleet
        assert screen in keep
    assert "finviz_screener_watch --screen" in fleet or "finviz_screener_keepalive.sh" in fleet


def test_motor_es_signal_only_y_token_no_hardcodeado():
    src = SRC.read_text()
    assert "FINVIZ_AUTH3" in src
    assert "placeOrder" not in src and "order_engine" not in src
    assert "ta_newhigh" in src
    assert "fa_roe_o15" in src
    assert "sh_short_o15" in src
