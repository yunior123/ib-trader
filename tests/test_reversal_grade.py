"""Tests de scripts/reversal_grade.py — BARRIDO que gradua el reversal_router, NO lo cablea.

Cubre: equivalencia del refactor evaluate/state_at vs _compute, no-repaint del replay, y —lo
nuevo tras la retirada del veredicto FAIL de un solo punto— que el ATR se calcula sobre el
TIMEFRAME del router, que el resolvedor vectorizado es IDENTICO a event_study.resolve_event,
que Wilson va sobre n_eff corregida por correlacion, que hay null de entrada aleatoria + BH-FDR,
y que el veredicto agregado dice "SENSIBLE AL PARAMETRO" en cuanto depende del parametro.
Mas la guarda anti-cableado y el par plist+runner del cron de shock_calibrator (cobertura).
"""
import ast
import json
import os
import plistlib
import sqlite3
import subprocess
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


# ------------------------------------------------------------------ 2) ATR en el TF del router
def test_wilder_atr_series_equals_event_study_bar_by_bar():
    """La serie O(n) debe dar EXACTAMENTE lo que event_study.wilder_atr_at da por barra."""
    bars = _trend_bars(6)
    h, l, c = bars[:, 2], bars[:, 3], bars[:, 4]
    a = rg.wilder_atr_series(h, l, c, es.ATR_PERIOD)
    assert np.isnan(a[:es.ATR_PERIOD]).all()          # sin ATR inventado antes de period
    for i in (14, 15, 40, 300, len(c) - 1):
        assert a[i] == pytest.approx(es.wilder_atr_at(h, l, c, i, es.ATR_PERIOD), rel=1e-12)


def test_atr_tf1_is_the_1m_atr_and_tf5_is_bigger():
    """El bug del veredicto retirado: ±1xATR14 de 1m es MICROESTRUCTURA. Al pasar al
    timeframe base del router (5m) la barrera crece — y es la barrera lo que ata el WR."""
    bars = _trend_bars(8)
    do, mi = rg.et_fields(bars[:, 0])
    a1 = rg.atr_map_1m(bars, do, mi, 1)
    a5 = rg.atr_map_1m(bars, do, mi, 5)
    a60 = rg.atr_map_1m(bars, do, mi, 60)
    h, l, c = bars[:, 2], bars[:, 3], bars[:, 4]
    i = len(c) - 1
    assert a1[i] == pytest.approx(es.wilder_atr_at(h, l, c, i, es.ATR_PERIOD), rel=1e-12)
    fin = np.isfinite(a1) & np.isfinite(a5) & np.isfinite(a60)
    assert np.nanmedian(a5[fin]) > np.nanmedian(a1[fin])
    assert np.nanmedian(a60[fin]) > np.nanmedian(a5[fin])


def test_atr_map_is_causal():
    """El ATR del timeframe agregado en el indice i solo puede venir de buckets CERRADOS <= i."""
    bars = _trend_bars(8)
    do, mi = rg.et_fields(bars[:, 0])
    a30 = rg.atr_map_1m(bars, do, mi, 30)
    end_idx, H, L, C = rg.agg_tf(bars, do, mi, 30)
    atr_agg = rg.wilder_atr_series(H, L, C, es.ATR_PERIOD)
    for i in (500, 1200, len(bars) - 1):
        j = int(np.searchsorted(end_idx, i, side="right")) - 1
        assert end_idx[j] <= i
        if np.isfinite(atr_agg[j]):
            assert a30[i] == pytest.approx(atr_agg[j], rel=1e-12)
    # truncar la historia despues de i no cambia el ATR en i
    cut = int(end_idx[40])
    tr = bars[bars[:, 0] <= bars[cut, 0]]
    do2, mi2 = rg.et_fields(tr[:, 0])
    a30t = rg.atr_map_1m(tr, do2, mi2, 30)
    if np.isfinite(a30[cut]):
        assert a30t[cut] == pytest.approx(a30[cut], rel=1e-12)
    else:
        assert np.isnan(a30t[cut])


# ------------------------------------------------------------------ 3) resolvedor == event_study
@pytest.mark.parametrize("direction", [1, -1])
def test_resolve_batch_matches_event_study(direction):
    """El resolvedor vectorizado NO puede inventar una semantica propia: se prueba contra
    event_study.resolve_event evento a evento (incluido el empate y el timeout)."""
    rng = np.random.default_rng(11)
    c = 100 * np.cumprod(1 + rng.normal(0, 0.001, 4000))
    idx = np.arange(50, 3800, 37)
    entry = c[idx]
    atr = np.full(len(idx), 0.15)
    for mult, H in ((1.0, 30), (4.0, 120), (20.0, 60)):
        up = entry + mult * atr
        dn = entry - mult * atr
        d = np.full(len(idx), direction)
        out, mg = rg.resolve_batch(c, idx, entry, d, up, dn, H)
        for k in range(len(idx)):
            ref = es.resolve_event(c, int(idx[k]), direction, up[k], dn[k], H,
                                   entry=float(entry[k]))
            want = {"favorable": 1, "adverse": 0, "unresolved": -1}[ref["outcome"]]
            assert int(out[k]) == want, (mult, H, k, ref)
            assert bool(mg[k]) == bool(ref["mfe_gt_mae"])


def test_resolve_batch_timeout_is_unresolved_not_win():
    c = np.full(200, 100.0)
    out, _ = rg.resolve_batch(c, np.array([10]), np.array([100.0]), np.array([1]),
                              np.array([110.0]), np.array([90.0]), 30)
    assert int(out[0]) == -1


# ------------------------------------------------------------------ 4) n_eff + Wilson + null
def _fake_cell(n_fav, n_adv, n_dates=40, year=2025):
    n = n_fav + n_adv
    outcome = np.array([1] * n_fav + [0] * n_adv, dtype=np.int8)
    mfe = np.array([True] * n_fav + [False] * n_adv)
    years = np.full(n, year, dtype=np.int64)
    dates = np.array([739000 + (i % n_dates) for i in range(n)], dtype=np.int64)
    return outcome, mfe, years, dates


def test_n_eff_shrinks_the_sample_and_widens_wilson():
    """rho>0 debe MORDER: n_eff < n y el CI se ensancha. Si no muerde, no se esta aplicando."""
    o, m, y, d = _fake_cell(300, 300)
    crudo = rg.cell_stats(o, m, y, d, rho=0.0, min_n=30)
    corr = rg.cell_stats(o, m, y, d, rho=0.41, min_n=30)
    assert crudo["n_eff"] > corr["n_eff"]
    assert corr["n_eff"] < corr["n_resolved"]
    ancho_crudo = crudo["wilson_hi"] - crudo["wilson_lo"]
    ancho_corr = corr["wilson_hi"] - corr["wilson_lo"]
    assert ancho_corr > ancho_crudo


def test_wilson_uses_event_study_not_a_reimplementation():
    o, m, y, d = _fake_cell(40, 20)
    st = rg.cell_stats(o, m, y, d, rho=0.41, min_n=30)
    p, lo, hi = es.wilson(40, 60)
    assert st["win_rate"] == round(p, 4)
    assert st["wilson_lo_crudo"] == round(lo, 4)
    assert st["wilson_hi_crudo"] == round(hi, 4)
    ne = rg.n_effective(60, set(d.tolist()), 0.41)
    _, loe, hie = es.wilson(p * ne, ne)
    assert st["wilson_lo"] == round(loe, 4) and st["wilson_hi"] == round(hie, 4)


def test_below_min_n_is_none_no_probability_published():
    o, m, y, d = _fake_cell(10, 9)
    assert rg.cell_stats(o, m, y, d, rho=0.41, min_n=30) is None
    assert rg.cell_verdict(None) == "DATA-INSUFFICIENT"


def test_cell_verdict_needs_effective_sample_not_raw():
    """n cruda enorme pero n_eff por debajo del piso => DATA-INSUFFICIENT, no PASS."""
    o, m, y, d = _fake_cell(400, 100, n_dates=2)   # solo 2 sesiones: casi toda la n es 1 dia
    st = rg.cell_stats(o, m, y, d, rho=0.9, min_n=30)
    assert st["n_resolved"] == 500 and st["n_eff"] < rg.MIN_N_EFF
    assert rg.cell_verdict(st) == "DATA-INSUFFICIENT"


def test_edge_is_none_without_the_null_never_zero():
    o, m, y, d = _fake_cell(40, 20)
    st = rg.cell_stats(o, m, y, d, rho=0.41, min_n=30)
    assert rg._edge(st, None) == dict(edge=None, edge_p=None)
    assert rg._edge(None, st) == dict(edge=None, edge_p=None)


def test_fdr_is_applied_over_the_whole_grid():
    cells = [dict(edge=0.02, edge_p=p, verdict_moneda="PASS") for p in
             (0.001, 0.02, 0.04, 0.2, 0.5, 0.9)]
    rg._apply_fdr(cells)
    qs = [c["fdr_q"] for c in cells]
    assert qs == sorted(qs)                      # monotono
    assert all(q >= p for q, p in zip(qs, (0.001, 0.02, 0.04, 0.2, 0.5, 0.9)))
    assert cells[0]["fdr_pass"] is True and cells[-1]["fdr_pass"] is False


# ------------------------------------------------------------------ 5) veredicto agregado HONESTO
def _cell(v):
    return dict(verdict_moneda=v)


def test_aggregate_says_sensible_when_the_verdict_depends_on_the_parameter():
    v, why = rg.aggregate_verdict([_cell("PASS"), _cell("FAIL"), _cell("UNPROVEN")])
    assert v == "SENSIBLE AL PARAMETRO — no concluyente"
    assert "CAMBIA" in why


def test_aggregate_never_emits_a_bare_pass_or_fail():
    for vs, want in ((["PASS", "PASS"], "PASS-CONSISTENTE"),
                     (["FAIL", "FAIL"], "FAIL-CONSISTENTE"),
                     (["UNPROVEN"], "UNPROVEN-CONSISTENTE")):
        v, _ = rg.aggregate_verdict([_cell(x) for x in vs])
        assert v == want
        assert v not in ("PASS", "FAIL")


def test_aggregate_all_insufficient():
    v, why = rg.aggregate_verdict([_cell("DATA-INSUFFICIENT")] * 4)
    assert v == "DATA-INSUFFICIENT" and "n_eff" in why


# ------------------------------------------------------------------ 6) end-to-end + atomica
def test_run_sweep_end_to_end(tmp_path, monkeypatch):
    bars = _trend_bars(24)
    db = _mini_db(str(tmp_path / "mini.db"), "TREND", bars)
    monkeypatch.setattr(rg, "DB", db)
    out = str(tmp_path / "reversal_grade.json")
    rep = rg.run(["TREND"], horizons=(30, 120), mults=(1.0, 4.0), atr_tfs=(1, 5),
                 null_draws=200, out=out, quiet=True, nota="fixture sintetica de 1 simbolo")
    assert rep["wired"] is False and rep["shadow"] is True
    assert rep["symbols"] == ["TREND"]
    assert rep["veredicto_agregado"] not in ("PASS", "FAIL")
    assert rep["limitaciones"] and all(isinstance(x, str) for x in rep["limitaciones"])
    assert rep["nota"] == "fixture sintetica de 1 simbolo"
    # la rejilla existe y CADA celda anota sus parametros
    assert len(rep["celdas"]) == 2 * 2 * 2 * len(rg.GROUPS) or rep["celdas"]
    for c in rep["celdas"]:
        assert set(c["params"]) == {"atr_tf_min", "atr_mult", "horizon_min", "atr_period"}
        assert c["verdict_moneda"] in ("PASS", "FAIL", "UNPROVEN", "DATA-INSUFFICIENT")
    assert any(c["es_punto_original"] for c in rep["celdas"])
    assert os.path.exists(out) and not os.path.exists(out + ".tmp")
    with open(out) as f:
        loaded = json.load(f)        # levantaria si se colara un tipo numpy
    assert loaded["veredicto_agregado"] == rep["veredicto_agregado"]
    assert loaded["params"]["rho"] is not None


def test_run_declares_the_symbol_subset(tmp_path, monkeypatch):
    """No se puede llamar 'todos' a un subconjunto: symbols + nota viajan en el JSON."""
    bars = _trend_bars(24)
    db = _mini_db(str(tmp_path / "mini2.db"), "TREND", bars)
    monkeypatch.setattr(rg, "DB", db)
    out = str(tmp_path / "g.json")
    rep = rg.run(["TREND"], horizons=(30,), mults=(1.0,), atr_tfs=(1,), null_draws=50,
                 out=out, quiet=True)
    assert rep["symbols"] == ["TREND"]
    assert str(len(rep["symbols"])) in rep["nota"]


def test_load_poly_1m_missing_symbol_is_none(tmp_path):
    db = _mini_db(str(tmp_path / "mini3.db"), "TREND", _trend_bars(2))
    con = rg.open_db(db)
    try:
        assert rg.load_poly_1m("NOPE", con) is None
        arr = rg.load_poly_1m("TREND", con)
        assert arr is not None and arr.shape[1] == 6
        assert arr[0, 0] < 2e9      # epoch en SEGUNDOS, no ms
    finally:
        con.close()


def test_null_entries_match_the_time_of_day_bucket():
    bars = _trend_bars(24)
    evs = rg.replay_events(bars)
    prep, _ = rg.prepare_symbol("TREND", bars, evs, atr_tfs=(1,), atr_period=14,
                                null_draws=300, seed=7)
    assert prep is not None and len(prep["r_idx"]) > 0
    _, mi = rg.et_fields(bars[:, 0])
    sig_b = sorted({int(mi[i]) // rg.TOD_BUCKET_MIN for i in prep["idx"]})
    nul_b = sorted({int(mi[i]) // rg.TOD_BUCKET_MIN for i in prep["r_idx"]})
    assert set(nul_b) <= set(sig_b)          # nunca en una hora en la que la señal no dispara
    assert set(prep["r_dir"].tolist()) <= set(prep["dir"].tolist())


def test_null_is_reproducible_with_the_seed():
    bars = _trend_bars(24)
    evs = rg.replay_events(bars)
    a, _ = rg.prepare_symbol("TREND", bars, evs, atr_tfs=(1,), atr_period=14,
                             null_draws=120, seed=7)
    b, _ = rg.prepare_symbol("TREND", bars, evs, atr_tfs=(1,), atr_period=14,
                             null_draws=120, seed=7)
    c, _ = rg.prepare_symbol("TREND", bars, evs, atr_tfs=(1,), atr_period=14,
                             null_draws=120, seed=8)
    assert np.array_equal(a["r_idx"], b["r_idx"])
    assert not np.array_equal(a["r_idx"], c["r_idx"])


# ------------------------------------------------------------------ 7) el JSON publicado
def test_published_json_has_no_bare_verdict():
    """data/reversal_grade.json es lo que lee un humano: no puede llevar un FAIL/PASS seco."""
    p = os.path.join(REPO, "data", "reversal_grade.json")
    if not os.path.exists(p):
        pytest.skip("todavia no generado")
    d = json.load(open(p))
    assert d["wired"] is False
    assert d["veredicto_agregado"] not in ("PASS", "FAIL")
    assert d["limitaciones"], "el JSON debe declarar lo que NO implementa"
    assert d["symbols"] and d["nota"]
    assert d["celdas"], "sin rejilla no hay barrido"
    for c in d["celdas"]:
        assert c["params"]["atr_tf_min"] in d["params"]["atr_tfs_min"]
    assert "verdict" not in d and "buckets" not in d   # el punto unico esta RETIRADO


# ------------------------------------------------------------------ 8) guarda anti-cableado
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


# ------------------------------------------------------------------ 9) cron shock_calibrator
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


def _fake_root(tmp_path, provider_syms="QQQ SPY NVDA MU\n", py_body=None):
    """Raiz falsa con el runner + shock_calibrator reales. `py_body` define que hace el
    ./venv-mit/bin/python de mentira cuando lo invoca el runner (el `-c` de resolucion de
    universo/cobertura se delega SIEMPRE al python real)."""
    import shutil
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "venv-mit" / "bin").mkdir(parents=True)
    shutil.copy(os.path.join(REPO, "scripts", "shock_snapshot_run.sh"), root / "scripts")
    shutil.copy(os.path.join(REPO, "scripts", "shock_calibrator.py"), root / "scripts")
    (root / "data" / "provider_syms.txt").write_text(provider_syms)
    py = root / "venv-mit" / "bin" / "python"
    py.write_text("#!/bin/sh\n"
                  'case "$1" in -c) exec %s "$@";; esac\n' % sys.executable
                  + (py_body or "exit 1\n"))
    py.chmod(0o755)
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "osascript").write_text("#!/bin/sh\nexit 0\n")   # sin notificacion real en tests
    (stub / "osascript").chmod(0o755)
    env = dict(os.environ, PATH="%s:%s" % (stub, os.environ["PATH"]))
    return root, env


def _run_runner(root, env):
    return subprocess.run(["/bin/zsh", str(root / "scripts" / "shock_snapshot_run.sh")],
                          env=env, capture_output=True, text=True)


def test_shock_runner_screams_when_snapshot_not_refreshed(tmp_path):
    root, env = _fake_root(tmp_path)
    p = _run_runner(root, env)
    assert p.returncode == 1, p.stderr
    log = (root / "logs" / "shock_calibrator.log").read_text()
    assert "NO actualizado" in log


def test_shock_runner_fails_on_partial_coverage(tmp_path):
    """El bug: snapshot TRUNCADO (2 de 4) con rc=0 y mtime nuevo — el runner lo daba por
    bueno porque solo miraba N==0. Ahora compara N contra el universo PEDIDO."""
    body = ("python_dir=$(dirname \"$0\")\n"
            "printf '%s' '{\"symbols\": {\"QQQ\": {}, \"SPY\": {}}}' "
            "> \"$python_dir/../../data/shock_snapshot.json\"\n"
            "exit 0\n")
    root, env = _fake_root(tmp_path, py_body=body)
    p = _run_runner(root, env)
    assert p.returncode == 1, p.stdout + p.stderr
    log = (root / "logs" / "shock_calibrator.log").read_text()
    assert "NO actualizado" in log
    assert "2/4" in log, log
    assert "MU" in log and "NVDA" in log, "debe nombrar los simbolos que faltan"


def test_shock_runner_ok_on_full_coverage(tmp_path):
    body = ("python_dir=$(dirname \"$0\")\n"
            "printf '%s' '{\"symbols\": {\"QQQ\": {}, \"SPY\": {}, \"NVDA\": {}, \"MU\": {}}}'"
            " > \"$python_dir/../../data/shock_snapshot.json\"\n"
            "exit 0\n")
    root, env = _fake_root(tmp_path, py_body=body)
    p = _run_runner(root, env)
    assert p.returncode == 0, p.stdout + p.stderr
    log = (root / "logs" / "shock_calibrator.log").read_text()
    assert "ok: 4/4" in log, log


def test_shock_runner_aborts_when_universe_unresolvable(tmp_path):
    """Sin universo no se corre nada: fail-loud, jamas un universo inventado."""
    root, env = _fake_root(tmp_path, provider_syms="\n")
    (root / "data" / "provider_syms.txt").unlink()
    p = _run_runner(root, env)
    assert p.returncode == 1
    log = (root / "logs" / "shock_calibrator.log").read_text()
    assert "universo" in log.lower()


def test_shock_runner_shape():
    src = open(os.path.join(REPO, "scripts", "shock_snapshot_run.sh")).read()
    assert "${0:A:h}" in src                     # raiz derivada, no hardcodeada
    assert "/Users/" not in src
    assert "PYTHONPATH=" in src and "mit" in src
    assert "venv-mit/bin/python" in src
    assert "shock_calibrator.py --once" in src
    assert "logs/shock_calibrator.log" in src
    # Grita si el snapshot no se refresco. El banner pasa por scripts/osa_gate (portero que
    # se calla con data/notify_off), no por osascript directo.
    assert "$IBT_OSA" in src and "osa_gate" in src
    # el universo NO se duplica: se resuelve con shock_calibrator._syms()
    assert "shock_calibrator" in src and "_syms()" in src
    assert "provider_syms.txt" not in src, "hardcodear el fichero duplica la resolucion"
