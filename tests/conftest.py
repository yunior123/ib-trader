"""Shared fixtures for the critical-module test suite.

Each target script does `os.chdir(REPO)` at import and only runs main() under
`if __name__ == "__main__"`, so importing is side-effect-safe except for the cwd
change (which lands us in the repo root — exactly where the modules expect to be).
We load each script by absolute path with importlib, cache it session-wide, and
restore the original cwd after the whole session so we never surprise the runner.
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
_ORIG_CWD = os.getcwd()


def _load(name):
    """Load scripts/<name>.py as an importable module object."""
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # runs os.chdir(REPO); main() NOT called
    return mod


@pytest.fixture(scope="session", autouse=True)
def _restore_cwd():
    yield
    os.chdir(_ORIG_CWD)


@pytest.fixture(scope="session")
def calib():
    return _load("calibration_ledger")


@pytest.fixture(scope="session")
def force():
    return _load("force_meter")


@pytest.fixture(scope="session")
def breadth_mod():
    return _load("index_breadth")


@pytest.fixture(scope="session")
def cage():
    return _load("posthours_cage")


@pytest.fixture(scope="session")
def fleet():
    return _load("daily_fleet_plans")
