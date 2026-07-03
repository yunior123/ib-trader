import json
import os
import subprocess
import time

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "scripts", "flow_pulse.cpp")


@pytest.fixture(scope="module")
def flow_pulse_bin(tmp_path_factory):
    out = tmp_path_factory.mktemp("flow_pulse_build") / "flow_pulse"
    subprocess.run(
        ["clang++", "-std=c++23", "-O2", "-Wall", "-Wextra", "-o", str(out), SRC],
        check=True, capture_output=True, text=True)
    return out


@pytest.mark.parametrize("side,wording,direction", [
    ("P", "Rebote probable por flujo; Bollinger aun no confirma.", "UP"),
    ("C", "Retroceso probable por flujo; Bollinger aun no confirma.", "DOWN"),
])
def test_real_cpp_path_records_pending_and_never_invents_bb(
        flow_pulse_bin, tmp_path, side, wording, direction):
    (tmp_path / "data").mkdir()
    env = os.environ.copy()
    env.update(FP_TEST_FLOW_BB="1", FP_TEST_FLOW_SIDE=side)

    first = subprocess.run([str(flow_pulse_bin)], cwd=tmp_path, env=env,
                           check=True, capture_output=True, text=True)

    assert wording in first.stdout
    event = json.loads((tmp_path / "data" / "flow_bb_events.jsonl").read_text())
    assert event["source"] == "flow_pulse"
    assert event["volume_scope"] == "aggregate_delta"
    assert event["aggregate_volume"] == 4000
    assert event["dominant_strike"] is None

    # Con BB previa fresca compatible, el mismo camino enriquece y no deja otro pendiente.
    (tmp_path / "data" / "flow_bb_events.jsonl").unlink()
    latest = {
        "NFLX": {
            "id": "bb-1", "ts": time.time(), "sym": "NFLX", "direction": direction,
            "timeframe": "1m", "price": 72.31, "target": 72.24,
            "source": "bollinger_alarm",
        }
    }
    (tmp_path / "data" / "flow_bb_latest.json").write_text(
        json.dumps(latest, separators=(",", ":")))

    second = subprocess.run([str(flow_pulse_bin)], cwd=tmp_path, env=env,
                            check=True, capture_output=True, text=True)

    assert "Bollinger ya son compatibles" in second.stdout
    assert "no prueba causalidad" in second.stdout
    assert not (tmp_path / "data" / "flow_bb_events.jsonl").exists()


def test_captain_override_is_muted_and_never_left_pending(flow_pulse_bin, tmp_path):
    (tmp_path / "data").mkdir()
    env = os.environ.copy()
    env.update(FP_TEST_FLOW_BB="1", FP_TEST_FLOW_SIDE="P", FP_TEST_FLOW_OVERRIDE="1")

    result = subprocess.run([str(flow_pulse_bin)], cwd=tmp_path, env=env,
                            check=True, capture_output=True, text=True)

    assert "Capitan opuesto vigente: esta lectura queda anulada." in result.stdout
    assert "Rebote probable" not in result.stdout
    assert not (tmp_path / "data" / "flow_bb_events.jsonl").exists()
