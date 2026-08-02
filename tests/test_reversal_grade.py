"""Tests de scripts/reversal_grade.py — GRADUA el reversal_router, NO lo cablea.

Cubre: equivalencia del refactor evaluate/state_at vs _compute, no-repaint del replay
(estado en la barra i == estado con la historia truncada en i), fail-loud por debajo de
min_n (sin probabilidad publicada), Wilson identico al de event_study (no reimplementado),
escritura atomica, guarda anti-cableado (ni fleet_notify/fleet_consensus/order_engine ni voz)
y el par plist+runner del cron de shock_calibrator.
"""
import ast
import json
import os
import plistlib
import sqlite3
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import event_study as es  # noqa: E402
import reversal_grade as rg  # noqa: E402
import reversal_router as rr  # noqa: E402

ET = ZoneInfo("America/New_York")


# ------------------------------------------------------------------ fixtures sinteticas
def _sessions(n, start=datetime(2026, 3, 2)):
    out, d = [], start.date()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _trend_bars(n_sessions=20, seed=3, drift=0.0004):
    """Barras 1m sinteticas en tendencia limpia (dispara CONTINUATION_ACTIVE_DO_NOT_FADE)."""
    rows = []
    price, prev = 100.0, None
    rng = np.random.default_rng(seed)
    for d in _sessions(n_sessions):
        for m in range(390):
            price *= (1 + drift + rng.normal(0, 0.00012))
            o = prev if prev is not None else price
            hi = max(o, price) + abs(price) * 0.004
            lo = min(o, price) - abs(price) * 0.004
            e = int((datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
                     + timedelta(minutes=m)).timestamp())
            rows.append((e, o, hi, lo, price, 1000.0))
            prev = price
    return np.asarray(rows, dtype=float)


def _write_bars_file(data_dir, sym, bars):
    path = os.path.join(data_dir, "bars_%s_ibkr.txt" % sym.lower())
    with open(path, "w") as f:
        for e, o, h, l, c, v in bars:
            f.write("%d %.4f %.4f %.4f %.4f %.0f\n" % (int(e), o, h, l, c, v))
    return path


def _mini_db(path, sym, bars):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE poly_bars (sym TEXT, ts INTEGER, o REAL, h REAL, l REAL,"
                " c REAL, v REAL, PRIMARY KEY (sym, ts))")
    con.executemany("INSERT INTO poly_bars VALUES (?,?,?,?,?,?,?)",
                    [(sym, int(e) * 1000, o, h, l, c, v) for e, o, h, l, c, v in bars])
    con.commit()
    con.close()
    return path


# ------------------------------------------------------------------ 1) equivalencia del refactor
def test_evaluate_matches_compute(tmp_path, monkeypatch):
    bars = _trend_bars()
    monkeypatch.setattr(rr, "DATA", str(tmp_path))
    _write_bars_file(str(tmp_path), "TREND", bars)
    via_file = rr._compute("TREND")
    direct = rr.evaluate(bars)
    assert via_file["symbol"] == "TREND"
    assert direct["state"] == "CONTINUATION_ACTIVE_DO_NOT_FADE"
    assert {k: v for k, v in via_file.items() if k != "symbol"} == direct


def test_state_at_last_equals_evaluate():
    bars = _trend_bars()
    f = rr.features(bars)
    assert rr.state_at(f, len(f["base"]["c"]) - 1) == rr.evaluate(bars)


def test_replay_is_no_repaint():
    """El estado en la barra i debe ser el mismo con la historia TRUNCADA en i."""
    bars = _trend_bars()
    f = rr.features(bars)
    n = len(f["base"]["c"])
    for i in (n - 1, n - 7, rr.REQUIRED_5M_BARS + 3):
        cut = int(f["base"]["epoch"][i])
        truncated = bars[bars[:, 0] <= cut]
        assert rr.state_at(f, i) == rr.evaluate(truncated), i


def test_replay_events_emits_transitions_only():
    bars = _trend_bars()
    evs = rg.replay_events(bars)
    assert evs, "la tendencia limpia debe disparar al menos una transicion"
    for e in evs:
        assert e["state"] in rg.GRADED_STATES
        assert e["direction"] in (1, -1)
    epochs = [e["ts"] for e in evs]
    assert epochs == sorted(epochs)
    f = rr.features(bars)
    # cada evento es una TRANSICION: la barra anterior no estaba en ese estado
    for e in evs:
        i = e["bar_index"]
        if i > 0:
            assert rr.state_at(f, i - 1)["state"] != e["state"]


# ------------------------------------------------------------------ 2) fail-loud bajo min_n
def _fake_resolved(n_fav, n_adv, state="REVERSAL_CONFIRMED", year=2025):
    out = [dict(outcome="favorable", state=state, year=year, mfe_gt_mae=True)
           for _ in range(n_fav)]
    out += [dict(outcome="adverse", state=state, year=year, mfe_gt_mae=False)
            for _ in range(n_adv)]
    return out


def test_below_min_n_is_data_insufficient_without_probability():
    b = rg.bucket_grade(_fake_resolved(10, 9), min_n=30)
    assert b["verdict"] == "DATA-INSUFFICIENT"
    assert b["n_resolved"] == 19
    for forbidden in ("win_rate", "wilson_lo", "wilson_hi", "mfe_gt_mae_pct"):
        assert forbidden not in b, forbidden


def test_empty_bucket_is_data_insufficient_not_zero():
    b = rg.bucket_grade([], min_n=30)
    assert b["verdict"] == "DATA-INSUFFICIENT"
    assert b["n_resolved"] == 0
    assert "win_rate" not in b


# ------------------------------------------------------------------ 3) Wilson = event_study
def test_wilson_and_win_rate_match_event_study():
    fav, adv = 40, 20
    b = rg.bucket_grade(_fake_resolved(fav, adv), min_n=30)
    p, lo, hi = es.wilson(fav, fav + adv)
    assert b["n_resolved"] == fav + adv
    assert b["win_rate"] == round(p, 4)
    assert b["wilson_lo"] == round(lo, 4)
    assert b["wilson_hi"] == round(hi, 4)
    assert b["verdict"] == ("PASS" if round(lo, 4) > rg.NULL_P else "FAIL")


def test_verdict_fail_when_ci_includes_coin_flip():
    b = rg.bucket_grade(_fake_resolved(16, 15), min_n=30)
    assert b["wilson_lo"] <= rg.NULL_P
    assert b["verdict"] == "FAIL"


def test_verdict_pass_only_when_ci_excludes_coin_flip():
    b = rg.bucket_grade(_fake_resolved(45, 5), min_n=30)
    assert b["wilson_lo"] > rg.NULL_P
    assert b["verdict"] == "PASS"


# ------------------------------------------------------------------ 4) end-to-end + escritura atomica
def test_run_end_to_end_atomic_write(tmp_path, monkeypatch):
    bars = _trend_bars()
    db = _mini_db(str(tmp_path / "mini.db"), "TREND", bars)
    monkeypatch.setattr(rg, "DB", db)
    out = str(tmp_path / "reversal_grade.json")
    rep = rg.run(["TREND"], horizon=30, atr_frac=1.0, atr_period=14, min_n=30, out=out)
    assert rep["wired"] is False
    assert rep["symbols"] == ["TREND"]
    assert set(rep["buckets"]) == {"ALL"} | set(rg.GRADED_STATES)
    assert os.path.exists(out)
    assert not os.path.exists(out + ".tmp")
    with open(out) as f:
        loaded = json.load(f)          # levantaria si se colara un tipo numpy
    assert loaded["wired"] is False
    assert loaded["buckets"]["ALL"]["verdict"] in ("PASS", "FAIL", "DATA-INSUFFICIENT")


def test_load_poly_1m_missing_symbol_is_none(tmp_path):
    db = _mini_db(str(tmp_path / "mini2.db"), "TREND", _trend_bars(2))
    con = rg.open_db(db)
    try:
        assert rg.load_poly_1m("NOPE", con) is None
        arr = rg.load_poly_1m("TREND", con)
        assert arr is not None and arr.shape[1] == 6
        assert arr[0, 0] < 2e9      # epoch en SEGUNDOS, no ms
    finally:
        con.close()


# ------------------------------------------------------------------ 5) guarda anti-cableado
FORBIDDEN_MODULES = {"fleet_notify", "fleet_consensus", "order_engine", "subprocess"}
FORBIDDEN_STRINGS = {"say", "osascript", "afplay", "voice_queue"}


@pytest.mark.parametrize("name", ["reversal_router.py", "reversal_grade.py"])
def test_no_wiring_to_fleet_or_voice(name):
    """El router es SOMBRA: ni vota, ni notifica, ni habla. AST (no grep) para no tropezar
    con la propia cabecera que enumera lo prohibido."""
    src = open(os.path.join(REPO, "scripts", name)).read()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & FORBIDDEN_MODULES), imported & FORBIDDEN_MODULES
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value.strip() not in FORBIDDEN_STRINGS, node.value
        if isinstance(node, ast.Call):
            fn = node.func
            nm = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            assert nm not in ("system", "popen", "Popen"), nm


# ------------------------------------------------------------------ 6) cron shock_calibrator
def test_shockcalib_plist_and_runner():
    plist = os.path.join(REPO, "scripts", "com.ibtrader.shockcalib.plist")
    with open(plist, "rb") as f:
        d = plistlib.load(f)
    assert d["Label"] == "com.ibtrader.shockcalib"
    args = d["ProgramArguments"]
    script = args[-1]
    assert script.endswith("scripts/shock_snapshot_run.sh")
    assert os.path.exists(script), script
    assert os.access(script, os.X_OK), "el runner debe ser ejecutable"
    sched = d["StartCalendarInterval"]
    assert isinstance(sched, list) and len(sched) == 5      # lun-vie
    assert {s["Weekday"] for s in sched} == {1, 2, 3, 4, 5}
    assert all(s["Hour"] == 16 and s["Minute"] == 40 for s in sched)
    assert d["RunAtLoad"] is False


def test_shock_runner_screams_when_snapshot_not_refreshed(tmp_path):
    """Raiz falsa + python que falla: el runner debe salir !=0 y dejar el grito en el log."""
    import shutil
    import subprocess
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "venv-mit" / "bin").mkdir(parents=True)
    shutil.copy(os.path.join(REPO, "scripts", "shock_snapshot_run.sh"), root / "scripts")
    (root / "data" / "provider_syms.txt").write_text("QQQ SPY\n")
    py = root / "venv-mit" / "bin" / "python"
    py.write_text("#!/bin/sh\nexit 1\n")
    py.chmod(0o755)
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "osascript").write_text("#!/bin/sh\nexit 0\n")   # sin notificacion real en tests
    (stub / "osascript").chmod(0o755)
    env = dict(os.environ, PATH="%s:%s" % (stub, os.environ["PATH"]))
    p = subprocess.run(["/bin/zsh", str(root / "scripts" / "shock_snapshot_run.sh")],
                       env=env, capture_output=True, text=True)
    assert p.returncode == 1, p.stderr
    log = (root / "logs" / "shock_calibrator.log").read_text()
    assert "NO actualizado" in log


def test_shock_runner_shape():
    src = open(os.path.join(REPO, "scripts", "shock_snapshot_run.sh")).read()
    assert "${0:A:h}" in src                     # raiz derivada, no hardcodeada
    assert "/Users/" not in src
    assert "PYTHONPATH=" in src and "mit" in src
    assert "venv-mit/bin/python" in src
    assert "shock_calibrator.py --once" in src
    assert "logs/shock_calibrator.log" in src
    assert "osascript" in src                    # grita si el snapshot no se refresco
    assert "provider_syms.txt" in src
