import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compass_calibrate", ROOT / "scripts" / "compass_calibrate.py")
CC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CC)


def test_flat_candidate_is_measured_without_becoming_an_operable_direction():
    row = {"dir": "flat", "candidate_dir": "up", "signal_kind": "no_predictive_edge"}
    assert CC.measured_dir(row) == "up"
    assert row["dir"] == "flat"


def test_operable_direction_takes_precedence_and_no_direction_is_excluded():
    assert CC.measured_dir({"dir": "down", "candidate_dir": "up"}) == "down"
    assert CC.measured_dir({"dir": "flat", "candidate_dir": "flat"}) is None
    assert CC.measured_dir({}) is None


def test_correlated_symbols_and_flapping_share_one_effective_market_block():
    cells = {
        "CONTINUACION|pool": {
            "n_raw": 5,
            "blocks": {
                (2026, 210, 19): [(1, 1), (1, 1), (0, 0), (1, 1), (0, 0)],
            },
        },
    }
    r = CC.summarize_cells(cells)["CONTINUACION|pool"]
    assert r["n_raw"] == 5
    assert r["n_eff"] == r["n"] == 1
    assert r["wr30"] == 1.0


def test_non_overlapping_30m_blocks_are_separate_trials():
    cells = {
        "CONTINUACION|f0|NEG": {
            "n_raw": 4,
            "blocks": {
                (2026, 210, 19): [(1, 1), (1, 1)],
                (2026, 210, 20): [(0, 0), (0, 0)],
            },
        },
    }
    r = CC.summarize_cells(cells)["CONTINUACION|f0|NEG"]
    assert r["n_eff"] == 2
    assert r["wr15"] == r["wr30"] == 0.5
    assert r["lo"] < 0.5
