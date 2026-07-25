"""Tests de scripts/barrier_labels.py — el etiquetado que arregla el denominador.

Los casos obligatorios de la ficha #1 (docs/FEATURES-MINED-2026-07-25.md):
  1. TP antes que SL -> 1 ; SL antes -> 0 ; ninguno -> None (TIMEOUT NO ES VICTORIA)
  2. Barra con TP y SL a la vez -> SL primero y contada en ambig
  3. MFE/MAE correctos en un camino sintetico calculado A MANO
  4. Purga/embargo: NINGUNA observacion de train solapa la ventana de test
  8. Idempotencia: dos corridas no duplican filas
  9. Nada de 0/0.5 fabricado ante datos insuficientes -> None o excepcion
"""
import importlib.util
import os
import sqlite3
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")


def _load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def BL():
    return _load("barrier_labels")


def bars(*rows):
    """rows: (minute, o, h, l, c) -> [(ts_s,o,h,l,c)] con ts base 1_000_000."""
    return [(1_000_000 + m * 60, o, h, l, c) for (m, o, h, l, c) in rows]


# ---------------------------------------------------------------- caso 1 -----
def test_tp_primero_es_1(BL):
    path = bars((1, 100, 100.5, 99.8, 100.2),
                (2, 100.2, 102.0, 100.0, 101.9))   # toca TP=101
    r = BL.triple_barrier(path, 100.0, +1, 101.0, 99.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] == 1
    assert r["ambig"] == 0
    assert r["t_touch"] == pytest.approx(2.0)


def test_sl_primero_es_0(BL):
    path = bars((1, 100, 100.4, 99.5, 99.6),
                (2, 99.6, 99.8, 98.5, 98.7))       # toca SL=99
    r = BL.triple_barrier(path, 100.0, +1, 101.0, 99.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] == 0
    assert r["ambig"] == 0
    assert r["t_touch"] == pytest.approx(2.0)


def test_timeout_es_None_no_victoria(BL):
    """EL BUG QUE ARREGLA LA FICHA: si no toca nada, NO es una victoria."""
    path = bars((1, 100, 100.4, 99.6, 100.3),
                (2, 100.3, 100.9, 99.2, 100.8))    # nunca 101 ni 99
    r = BL.triple_barrier(path, 100.0, +1, 101.0, 99.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] is None, "el timeout JAMAS puede etiquetarse como 1"
    assert r["t_touch"] is None
    # y aunque el precio final este arriba (el viejo etiquetado lo daria ganado):
    assert path[-1][4] > 100.0


def test_direccion_bajista_simetrica(BL):
    """dir=-1: TP por debajo, SL por encima."""
    path = bars((1, 100, 100.2, 98.5, 98.6))       # toca TP=99 (baja)
    r = BL.triple_barrier(path, 100.0, -1, 99.0, 101.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] == 1
    path2 = bars((1, 100, 101.5, 99.8, 101.4))     # toca SL=101 (sube)
    r2 = BL.triple_barrier(path2, 100.0, -1, 99.0, 101.0, atr=1.0, entry_ts=1_000_000)
    assert r2["label"] == 0


# ---------------------------------------------------------------- caso 2 -----
def test_barra_ambigua_resuelve_SL_y_se_cuenta(BL):
    """Una sola barra que contiene TP y SL: sin ruta sub-minuto se resuelve SL."""
    path = bars((1, 100, 101.5, 98.5, 100.0))
    r = BL.triple_barrier(path, 100.0, +1, 101.0, 99.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] == 0, "conservador: SL primero"
    assert r["ambig"] == 1, "y la ambiguedad se PUBLICA, no se esconde"


def test_ambigua_bajista_tambien_SL(BL):
    path = bars((1, 100, 101.5, 98.5, 100.0))
    r = BL.triple_barrier(path, 100.0, -1, 99.0, 101.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] == 0 and r["ambig"] == 1


# ---------------------------------------------------------------- caso 3 -----
def test_mfe_mae_calculados_a_mano(BL):
    """Camino: entry=100, ATR=2.
       m1 h=100.8 l=99.0  -> fav +0.8  adv +1.0
       m2 h=103.0 l=100.5 -> fav +3.0  (toca TP=102) adv 0
       MFE = 3.0/2 = 1.5 ATR ; MAE = 1.0/2 = 0.5 ATR ; t_touch = 2 min
    """
    path = bars((1, 100.0, 100.8, 99.0, 100.6),
                (2, 100.6, 103.0, 100.5, 102.8))
    r = BL.triple_barrier(path, 100.0, +1, 102.0, 96.0, atr=2.0, entry_ts=1_000_000)
    assert r["label"] == 1
    assert r["mfe"] == pytest.approx(1.5)
    assert r["mae"] == pytest.approx(0.5)
    assert r["t_touch"] == pytest.approx(2.0)


def test_mfe_mae_no_miran_mas_alla_del_toque(BL):
    """La barra 3 tiene una excursion enorme pero llega DESPUES del SL: no cuenta."""
    path = bars((1, 100.0, 100.2, 98.9, 99.0),     # toca SL=99
                (2, 99.0, 110.0, 98.0, 109.0))
    r = BL.triple_barrier(path, 100.0, +1, 105.0, 99.0, atr=1.0, entry_ts=1_000_000)
    assert r["label"] == 0
    assert r["mfe"] == pytest.approx(0.2), "solo la barra resolutoria (incluida)"
    assert r["mae"] == pytest.approx(1.1)


# ---------------------------------------------------------------- caso 9 -----
def test_atr_invalido_levanta_no_devuelve_medio(BL):
    path = bars((1, 100, 101.5, 99.0, 100.0))
    for bad in (None, 0.0, -1.0):
        with pytest.raises(ValueError):
            BL.triple_barrier(path, 100.0, +1, 101.0, 99.0, atr=bad)
    with pytest.raises(ValueError):
        BL.triple_barrier(path, 100.0, 0, 101.0, 99.0, atr=1.0)


def test_atr_insuficiente_devuelve_None(BL):
    b = bars(*[(m, 100, 100.5, 99.5, 100) for m in range(5)])
    assert BL.atr_at(b, 4) is None, "menos de 14 barras: None, jamas un ATR inventado"
    assert BL.atr_at(b, 99) is None
    assert BL.atr_at([], 0) is None


def test_cell_stats_sin_resueltas_es_None(BL):
    assert BL.cell_stats([None, None, None], 1.0, 1.0) is None, \
        "todo timeout => no hay probabilidad, y no se fabrica 0.5"


def test_wilder_atr_valores_conocidos(BL):
    """14 barras de rango constante 1.0 sin huecos -> ATR = 1.0 exacto."""
    b = bars(*[(m, 100, 100.5, 99.5, 100.0) for m in range(14)])
    a = BL.wilder_atr(b, period=14)
    assert a[:13] == [None] * 13, "sin 14 TRs no hay ATR"
    assert a[13] == pytest.approx(1.0)


def test_true_range_ignora_close_previo_tras_hueco(BL):
    prev = (1_000_000, 100, 100.2, 99.8, 100.0)
    nxt_gap = (1_000_000 + 3600, 200, 200.5, 199.5, 200.0)   # 1h de hueco
    assert BL.true_range(nxt_gap, prev) == pytest.approx(1.0), \
        "tras un hueco el close previo no es comparable (no inflar el ATR x100)"
    nxt_ok = (1_000_000 + 60, 100.4, 100.6, 100.3, 100.5)
    assert BL.true_range(nxt_ok, prev) == pytest.approx(0.6)


# ---------------------------------------------------------------- caso 4 -----
def test_purga_y_embargo_sin_solape(BL):
    starts = [1_000_000 + i * 600 for i in range(60)]   # una cada 10 min
    folds = BL.purged_folds(starts, horizon_min=30, n_folds=5)
    assert len(folds) == 5
    assert BL.folds_are_clean(starts, folds), "train solapando test = contaminado"
    for fd in folds:
        life = 30 * 60
        for i in fd["train"]:
            s, e = starts[i], starts[i] + life
            assert not (e >= fd["t0"] and s <= fd["t1"]), "solape explicito"
            assert not (fd["t1"] < s <= fd["t1"] + 30 * 60), "embargo violado"
        assert not (set(fd["train"]) & set(fd["test"]))
    # la purga TIENE que costar observaciones, si no no se esta aplicando
    total = len(starts)
    dropped = [total - len(f["test"]) - len(f["train"]) for f in folds]
    assert sum(dropped) > 0, "si no se purga nada, la purga no esta activa"


def test_purga_mas_agresiva_con_horizonte_mayor(BL):
    starts = [1_000_000 + i * 600 for i in range(60)]
    d30 = sum(60 - len(f["test"]) - len(f["train"])
              for f in BL.purged_folds(starts, 30, 5))
    d120 = sum(60 - len(f["test"]) - len(f["train"])
               for f in BL.purged_folds(starts, 120, 5))
    assert d120 > d30, "H mayor => mas vida solapada => mas purga"


def test_purged_folds_degrada_sin_datos(BL):
    assert BL.purged_folds([], 30, 5) == []
    assert BL.purged_folds([1, 2, 3], 30, 1) == []


# ---------------------------------------------------------------- caso 8 -----
def test_idempotencia_write_rows(BL, tmp_path):
    db = str(tmp_path / "t.db")
    c = sqlite3.connect(db)
    row = (1, "QQQ", "bollinger", "2026-07-24", 1.0, 1, 100.0, 0.5,
           1.0, 1.0, 30, BL.MODE, 1, 1.2, 0.3, 4.0, 0)
    assert BL.write_rows(c, [row], 111.0) == 1
    assert BL.write_rows(c, [row], 222.0) == 1
    n = c.execute("SELECT COUNT(*) FROM barrier_outcomes").fetchone()[0]
    assert n == 1, "dos corridas NO duplican filas"
    run = c.execute("SELECT run_ts FROM barrier_outcomes").fetchone()[0]
    assert run == 222.0, "la fila se REEMPLAZA con el run nuevo"
    c.close()


def test_pk_separa_celdas_distintas(BL, tmp_path):
    db = str(tmp_path / "t2.db")
    c = sqlite3.connect(db)
    base = [1, "QQQ", "bollinger", "2026-07-24", 1.0, 1, 100.0, 0.5,
            1.0, 1.0, 30, BL.MODE, 1, 1.2, 0.3, 4.0, 0]
    other = list(base); other[10] = 60          # H distinto
    other2 = list(base); other2[8] = 1.5        # k_tp distinto
    BL.write_rows(c, [tuple(base), tuple(other), tuple(other2)], 1.0)
    assert c.execute("SELECT COUNT(*) FROM barrier_outcomes").fetchone()[0] == 3
    c.close()


# --------------------------------------------- extension de calibration -----
def test_calibrate_barrier_es_aditivo_y_honesto():
    CL = _load("calibration_ledger")
    e = CL.wilson_lb_expectancy(6, 10, k_tp=1.0, k_sl=1.0)
    assert e["p"] == pytest.approx(0.6)
    assert e["exp"] == pytest.approx(0.2)
    assert e["exp_lo"] < e["exp"] < e["exp_hi"]
    # un WR alto con k_tp chico y k_sl grande puede ser PERDEDOR: por eso se
    # elige por expectancia y no por win rate
    bad = CL.wilson_lb_expectancy(60, 100, k_tp=0.5, k_sl=1.0)
    assert bad["exp"] < 0
    assert CL.wilson_lb_expectancy(0, 0, 1.0, 1.0) is None
    # BD ausente -> LEVANTA (fail-loud). Jamas un {} silencioso que se lea como
    # "no hay edge": eso es el bug del denominador encogido otra vez.
    with pytest.raises(sqlite3.OperationalError):
        CL.calibrate_barrier(db="/nonexistent-xyz.db")


def test_calibrate_barrier_excluye_timeouts(tmp_path):
    CL = _load("calibration_ledger")
    db = str(tmp_path / "b.db")
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE barrier_outcomes(
        signal_id INTEGER, sym TEXT, source TEXT, date TEXT, ts_epoch REAL,
        direction INTEGER, entry REAL, atr REAL, k_tp REAL, k_sl REAL, H INTEGER,
        mode TEXT, label INTEGER, mfe REAL, mae REAL, t_touch REAL, ambig INTEGER,
        run_ts REAL)""")
    rows = ([(i, "QQQ", "x", "d", 0, 1, 1, 1, 1.0, 1.0, 30, "conservative",
              1, 0, 0, 1, 0, 0) for i in range(6)] +
            [(100 + i, "QQQ", "x", "d", 0, 1, 1, 1, 1.0, 1.0, 30, "conservative",
              0, 0, 0, 1, 0, 0) for i in range(4)] +
            [(200 + i, "QQQ", "x", "d", 0, 1, 1, 1, 1.0, 1.0, 30, "conservative",
              None, 0, 0, None, 0, 0) for i in range(90)])
    c.executemany("INSERT INTO barrier_outcomes VALUES(%s)" % ",".join("?" * 18), rows)
    c.commit(); c.close()
    out = str(tmp_path / "cal.json")
    res = CL.calibrate_barrier(db=db, out=out)
    k = "barrier:x|1.0/1.0/30"
    assert res[k]["n"] == 10, "solo las RESUELTAS entran en el denominador"
    assert res[k]["timeouts"] == 90
    assert res[k]["rate"] == pytest.approx(0.6)
    assert res[k]["verdict"] == "DATA-INSUFFICIENT", "n=10 < 50: no se publica"
    assert os.path.exists(out)
