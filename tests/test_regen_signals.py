#!/usr/bin/env python3
"""tests/test_regen_signals.py — las tres pruebas que hacen que los 501 dias valgan algo.

1. NO-LOOK-AHEAD: en el instante virtual V ninguna barra del sandbox cumple ts+60 > V.
   Si esto falla, las señales regeneradas son ficcion y todo lo que salga de ahi no vale.
2. `signals` (ledger vivo de 8 daemons) queda INTACTA byte a byte tras una corrida.
3. DETERMINISMO: misma semilla -> mismas señales.
Mas: equivalencia del feeder con ./replay, y que barrier_labels por defecto sigue
apuntando a `signals`/`barrier_outcomes` (el cambio es aditivo, no un cambio de conducta).
"""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
PY = os.path.join(REPO, "venv", "bin", "python")
if not os.path.exists(PY):
    PY = sys.executable
DB = os.path.join(REPO, "trades.db")

import regen_signals as RS                                          # noqa: E402

TEST_RUN = "PYTEST"


def _pick_date():
    c = RS.ro()
    rows = [d for d, _ in RS.sessions(c)]
    c.close()
    if not rows:
        pytest.skip("poly_bars vacia")
    return rows[-2]


def _signals_fingerprint():
    """Huella del contenido de `signals`: si cambia una sola fila, cambia el hash."""
    c = sqlite3.connect("file:" + DB + "?mode=ro", uri=True, timeout=30)
    try:
        n = c.execute("SELECT count(*) FROM signals").fetchone()[0]
        h = hashlib.sha256()
        for row in c.execute("SELECT id,ts_epoch,ts_txt,date,kind,symbol,price,priority,"
                             "source,msg,raw FROM signals ORDER BY id"):
            h.update(repr(row).encode())
        cols = tuple(r[1] for r in c.execute("PRAGMA table_info(signals)"))
    finally:
        c.close()
    return n, h.hexdigest(), cols


# ---------------------------------------------------------------- 1. look-ahead
def test_no_look_ahead_invariant():
    """El invariante, comprobado desde FUERA del feeder: se lee clock.txt y el fichero
    de barras a la vez y se exige ts + 60 <= reloj para TODAS las barras."""
    sys.path.insert(0, RS.SHIM)
    from vclock import VClock, BAR_S
    date = _pick_date()
    c = RS.ro()
    syms = sorted(RS.poly_syms(c) & set(RS.fleet()))[:2]
    t0, t1 = RS.epoch_of(date, "09:30"), RS.epoch_of(date, "16:00")
    bars = {}
    for s in syms:
        b = RS.load_session_bars(c, s, date, t0, t1, warm=200)
        if b:
            bars[s.lower()] = b
    c.close()
    assert bars, "sin barras para %s" % date
    sb = os.path.join(tempfile.mkdtemp(prefix="ibt-nla-"), "sb")
    RS.make_sandbox(sb)
    vc = VClock(sb, t0, t1, bars)
    checks = 0
    v = t0
    while v <= t1:
        vc.t = v
        vc.materialize()
        clk = float(open(vc.clock_path()).read().split()[0])
        assert clk == v
        for s in bars:
            p = os.path.join(sb, "data", "bars_%s_ibkr.txt" % s)
            with open(p) as f:
                for ln in f:
                    ts = int(ln.split()[0])
                    checks += 1
                    assert ts + BAR_S <= clk, (
                        "LOOK-AHEAD: %s barra %d visible en el instante virtual %d" % (s, ts, clk))
        v += 293                       # paso primo: no cae siempre en frontera de barra
    vc.close()
    shutil.rmtree(os.path.dirname(sb), ignore_errors=True)
    assert checks > 1000


def test_bars_are_monotonic_prefix():
    """El sandbox solo CRECE: nunca se reescribe una linea ya publicada (si se reescribiera,
    un generador podria ver un pasado distinto del que vio, y el replay no seria replay)."""
    sys.path.insert(0, RS.SHIM)
    from vclock import VClock
    date = _pick_date()
    c = RS.ro()
    sym = sorted(RS.poly_syms(c) & set(RS.fleet()))[0]
    t0, t1 = RS.epoch_of(date, "09:30"), RS.epoch_of(date, "16:00")
    bars = RS.load_session_bars(c, sym, date, t0, t1, warm=100)
    c.close()
    assert bars
    sb = os.path.join(tempfile.mkdtemp(prefix="ibt-mono-"), "sb")
    RS.make_sandbox(sb)
    vc = VClock(sb, t0, t1, {sym.lower(): bars})
    p = os.path.join(sb, "data", "bars_%s_ibkr.txt" % sym.lower())
    prev = open(p).read()
    v = t0
    while v <= t1:
        vc.t = v
        vc.materialize()
        cur = open(p).read()
        assert cur.startswith(prev), "el sandbox reescribio el pasado"
        prev = cur
        v += 600
    vc.close()
    shutil.rmtree(os.path.dirname(sb), ignore_errors=True)


# ------------------------------------------------------- 2. `signals` intacta
def test_signals_table_untouched_by_a_run():
    date = _pick_date()
    before = _signals_fingerprint()
    p = subprocess.run([PY, os.path.join(REPO, "scripts", "regen_signals.py"), "run",
                        "--dates", date, "--sources", "bots", "--run-id", TEST_RUN],
                       capture_output=True, text=True, cwd=REPO, timeout=900)
    assert p.returncode == 0, p.stderr[-1500:]
    after = _signals_fingerprint()
    assert before == after, "la corrida TOCO `signals` (n/hash/columnas cambiaron)"
    c = sqlite3.connect(DB, timeout=30)
    try:
        n = c.execute("SELECT count(*) FROM signals_regen WHERE run_id=?",
                      (TEST_RUN,)).fetchone()[0]
        assert n > 0, "no se escribio ninguna señal regenerada"
        kinds = {r[0] for r in c.execute(
            "SELECT source_kind FROM signals_regen WHERE run_id=?", (TEST_RUN,))}
        assert kinds == {"regen"}
    finally:
        c.close()


# ----------------------------------------------------------- 3. determinismo
def test_same_seed_same_signals():
    date = _pick_date()
    def run(rid):
        p = subprocess.run([PY, os.path.join(REPO, "scripts", "regen_signals.py"), "run",
                            "--dates", date, "--sources", "bots", "--seed", "7",
                            "--run-id", rid], capture_output=True, text=True,
                           cwd=REPO, timeout=900)
        assert p.returncode == 0, p.stderr[-1500:]
        c = sqlite3.connect("file:" + DB + "?mode=ro", uri=True, timeout=30)
        try:
            return [r for r in c.execute(
                "SELECT ts_epoch,ts_txt,kind,symbol,source,msg FROM signals_regen "
                "WHERE run_id=? ORDER BY ts_epoch,symbol,msg", (rid,))]
        finally:
            c.close()
    a = run(TEST_RUN + "A")
    b = run(TEST_RUN + "B")
    assert a and a == b, "dos corridas con la misma semilla dieron señales distintas"


# ---------------------------------------------------- extra: paridad con replay
@pytest.mark.skipif(not os.path.exists(os.path.join(REPO, "replay")),
                    reason="./replay no compilado")
def test_feeder_matches_replay():
    date = _pick_date()
    c = RS.ro()
    sym = "qqq" if "QQQ" in RS.poly_syms(c) else sorted(RS.poly_syms(c))[0].lower()
    c.close()
    p = subprocess.run([PY, os.path.join(REPO, "scripts", "regen_signals.py"),
                        "verify-replay", "--date", date, "--sym", sym, "--end", "11:00"],
                       capture_output=True, text=True, cwd=REPO, timeout=900)
    assert "EQUIVALENTE a ./replay" in p.stdout, p.stdout + p.stderr[-800:]
    assert p.returncode == 0


# ------------------------------------------ extra: el cambio es ADITIVO de verdad
def test_barrier_labels_default_tables_unchanged():
    import barrier_labels as BL
    assert BL.SIG_TABLE == "signals"
    assert BL.BO_TABLE == "barrier_outcomes"
    BL.use_signals_table("signals_regen")
    assert (BL.SIG_TABLE, BL.BO_TABLE) == ("signals_regen", "barrier_outcomes_regen")
    BL.use_signals_table("signals")
    assert (BL.SIG_TABLE, BL.BO_TABLE) == ("signals", "barrier_outcomes")
    with pytest.raises(SystemExit):
        BL.use_signals_table("signals; DROP TABLE signals")
    BL.use_signals_table("signals")


def test_sandbox_guard_refuses_the_live_repo():
    for bad in (REPO, os.path.join(REPO, "data"), os.path.join(REPO, "scripts"), "/tmp", "/"):
        with pytest.raises(SystemExit):
            RS._sandbox_guard(bad)


def teardown_module(module):
    c = sqlite3.connect(DB, timeout=30)
    try:
        for rid in (TEST_RUN, TEST_RUN + "A", TEST_RUN + "B"):
            c.execute("DELETE FROM signals_regen WHERE run_id=?", (rid,))
            c.execute("DELETE FROM regen_progress WHERE run_id=?", (rid,))
        c.commit()
    finally:
        c.close()
