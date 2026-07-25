"""chain_cube_archive: el lector entiende LOS DOS formatos reales, la retencion
agrupa sin perder una fila y es idempotente, y el -1.00 de TWS NUNCA se rellena.

Offline puro: todo sobre ficheros sinteticos en tmp_path + una lectura del fichero
REAL del repo si existe (para que el test muera si el formato cambia rio arriba).
"""
import gzip
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cube():
    return _load("chain_cube_archive")


REAL_TXT = """# opt_chain QQQ | epoch 1784924179 | 2026-07-24 16:16:19 | spot 684.66 | exps 20260724 20260727
# strike right exp bid ask vol oi iv delta gamma
685.00 C 20260724 -1.00 -1.00 238672 2348 -1.0000 -1.0000 -1.0000
685.00 P 20260724 -1.00 -1.00 370080 26591 -1.0000 -1.0000 -1.0000
684.00 C 20260727 1.20 1.30 143769 155 0.3100 0.5200 0.0210
"""


def _write(p, s):
    with open(p, "w") as f:
        f.write(s)
    return p


# ------------------------------------------------------------------ lector IBKR

def test_lee_formato_real_y_no_rellena_el_sentinela(cube, tmp_path):
    p = _write(str(tmp_path / "opt_chain_qqq_1615.txt"), REAL_TXT)
    snap = cube.read_chain(p)
    assert snap.meta["sym"] == "QQQ"
    assert snap.meta["ts"] == 1784924179
    assert snap.meta["spot"] == 684.66
    assert snap.meta["exps"] == ["20260724", "20260727"]
    assert snap.meta["src"] == "ibkr_tws"
    assert len(snap.rows) == 3
    r = snap.rows[0]
    # el -1.00 NO se convierte en 0: es None, y el crudo se conserva tal cual
    assert r.bid is None and r.ask is None
    assert r.iv is None and r.delta is None and r.gamma is None
    assert r.raw["bid"] == "-1.00" and r.raw["gamma"] == "-1.0000"
    assert set(("bid", "ask", "iv", "delta", "gamma")).issubset(set(r.missing))
    # vol/oi SI son reales fuera de RTH
    assert r.vol == 238672 and r.oi == 2348
    # la fila con cotizacion se lee entera
    q = snap.rows[2]
    assert q.bid == 1.20 and q.ask == 1.30 and q.gamma == 0.0210
    assert q.missing == ()
    assert snap.meta["n_with_quotes"] == 1
    assert snap.meta["n_with_greeks"] == 1


def test_fichero_sin_cabecera_levanta(cube, tmp_path):
    p = _write(str(tmp_path / "roto.txt"), "685.00 C 20260724 -1 -1 1 1 -1 -1 -1\n")
    with pytest.raises(ValueError):
        cube.read_chain(p)


def test_lee_gz_transparente(cube, tmp_path):
    p = str(tmp_path / "chains_qqq_2026-07-24.txt.gz")
    with gzip.open(p, "wt") as f:
        f.write(REAL_TXT)
        f.write(REAL_TXT.replace("epoch 1784924179", "epoch 1784924479"))
    snaps = cube.read_bundle(p)
    assert [s.meta["ts"] for s in snaps] == [1784924179, 1784924479]
    assert sum(len(s.rows) for s in snaps) == 6


# ---------------------------------------------------------------- lector Polygon

POLY = {
    "meta": {"sym": "QQQ", "snapshot_epoch": 1784966926.6, "spot": 685.06,
             "greeks": "polygon_directo", "bid_ask": "NO_ENTITLED"},
    "results": [
        {"details": {"contract_type": "call", "expiration_date": "2026-07-27",
                     "strike_price": 655, "ticker": "O:QQQ260727C00655000"},
         "greeks": {"delta": 0.92, "gamma": 0.00685, "theta": -0.63, "vega": 0.099},
         "implied_volatility": 0.365, "open_interest": 33, "day": {"volume": 1}},
        {"details": {"contract_type": "put", "expiration_date": "2026-07-27",
                     "strike_price": 655, "ticker": "O:QQQ260727P00655000"},
         "implied_volatility": None, "open_interest": 120, "day": {}},
    ],
}


def test_lee_polygon_con_griegas_reales_y_sin_bidask(cube, tmp_path):
    p = str(tmp_path / "chain_full_qqq.json")
    with open(p, "w") as f:
        json.dump(POLY, f)
    snap = cube.read_chain(p)
    assert snap.meta["fmt"] == "polygon_json" and snap.meta["src"] == "polygon_snapshot"
    assert snap.meta["n_rows"] == 2 and snap.meta["n_with_greeks"] == 1
    c, pu = snap.rows
    assert c.gamma == 0.00685 and c.iv == 0.365 and c.oi == 33 and c.exp == 20260727
    assert c.src == "polygon_snapshot"
    # sin entitlement de cotizaciones -> None SIEMPRE (nunca 0)
    assert c.bid is None and c.ask is None and "bid" in c.missing
    # contrato sin griegas: None, no 0, y declarado en missing
    assert pu.gamma is None and pu.iv is None
    assert "gamma" in pu.missing and "iv" in pu.missing and "vol" in pu.missing
    assert pu.oi == 120


def test_el_lector_dice_de_donde_viene_cada_dato(cube, tmp_path):
    t = cube.read_chain(_write(str(tmp_path / "opt_chain_qqq_1615.txt"), REAL_TXT))
    j = str(tmp_path / "chain_full_qqq.json")
    with open(j, "w") as f:
        json.dump(POLY, f)
    pj = cube.read_chain(j)
    assert set(r.src for r in t.rows) == {"ibkr_tws"}
    assert set(r.src for r in pj.rows) == {"polygon_snapshot"}


def test_fichero_real_del_repo_sigue_parseando(cube):
    """Guarda de contrato: si opt_chain_cache cambia el formato, este test muere."""
    p = os.path.join(REPO, "data", "opt_chain_qqq.txt")
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        pytest.skip("no hay foto viva de QQQ")
    snap = cube.read_chain(p)
    assert snap.meta["sym"] == "QQQ"
    assert snap.meta["n_rows"] > 0
    assert snap.meta["bad_rows"] == 0


# ------------------------------------------------------------------- retencion

def _fake_day(cube, tmp_path, date="2026-07-20", n=3):
    hist = tmp_path / "history"
    d = hist / date
    d.mkdir(parents=True)
    for i in range(n):
        _write(str(d / ("opt_chain_qqq_09%02d.txt" % (i * 5))),
               REAL_TXT.replace("epoch 1784924179", "epoch %d" % (1784924179 + i * 300)))
    _write(str(d / "opt_chain_spy_0900.txt"), REAL_TXT.replace("QQQ", "SPY"))
    with open(str(d / "chain_full_qqq.json"), "w") as f:
        json.dump(POLY, f)
    cube.HIST = str(hist)
    cube.INDEX_PATH = str(tmp_path / "chain_cube_index.json")
    cube.HEALTH_PATH = str(tmp_path / "cube_health.json")
    return str(d)


def test_dry_run_no_toca_nada(cube, tmp_path):
    d = _fake_day(cube, tmp_path)
    before = sorted(os.listdir(d))
    h = cube.retention(apply_=False, today="2026-07-25")
    assert sorted(os.listdir(d)) == before
    assert h["applied"] is False
    assert any(a["action"] == "bundle" for a in h["actions"])


def test_retencion_agrupa_sin_perder_filas_y_es_idempotente(cube, tmp_path):
    d = _fake_day(cube, tmp_path)
    rows_before = sum(cube.read_chain(os.path.join(d, f)).meta["n_rows"]
                      for f in os.listdir(d) if f.startswith("opt_chain_"))
    cube.retention(apply_=True, today="2026-07-25")
    # sueltas fuera, bundle dentro, chain_full gzipeado
    assert not [f for f in os.listdir(d) if f.startswith("opt_chain_")]
    bundles = sorted(f for f in os.listdir(d) if f.startswith("chains_"))
    assert bundles == ["chains_qqq_2026-07-20.txt.gz", "chains_spy_2026-07-20.txt.gz"]
    assert "chain_full_qqq.json.gz" in os.listdir(d)
    assert "chain_full_qqq.json" not in os.listdir(d)
    rows_after = sum(s.meta["n_rows"] for b in bundles
                     for s in cube.read_bundle(os.path.join(d, b)))
    assert rows_after == rows_before
    # el chain_full gzipeado sigue leyendose con griegas
    fc = cube.read_chain(os.path.join(d, "chain_full_qqq.json.gz"))
    assert fc.meta["n_with_greeks"] == 1
    # IDEMPOTENCIA: segunda pasada no duplica ni pierde
    cube.retention(apply_=True, today="2026-07-25")
    rows_2 = sum(s.meta["n_rows"] for b in bundles
                 for s in cube.read_bundle(os.path.join(d, b)))
    assert rows_2 == rows_before


def test_retencion_respeta_los_dias_frescos(cube, tmp_path):
    d = _fake_day(cube, tmp_path, date="2026-07-25")
    cube.retention(apply_=True, today="2026-07-25")
    assert [f for f in os.listdir(d) if f.startswith("opt_chain_")], "el dia de hoy no se toca"


def test_presupuesto_duro_aborta(cube, tmp_path):
    _fake_day(cube, tmp_path)
    cube.HISTORY_BUDGET_GB = 1e-9        # cualquier byte pasa el presupuesto
    with pytest.raises(RuntimeError) as e:
        cube.retention(apply_=True, today="2026-07-25")
    assert "ABORTADA" in str(e.value)
    cube.HISTORY_BUDGET_GB = 3.0


# ---------------------------------------------------------------------- indice

def test_indice_publica_cobertura_honesta(cube, tmp_path):
    _fake_day(cube, tmp_path)
    idx = cube.build_index(["2026-07-20"])
    day = idx["days"]["2026-07-20"]
    assert day["snapshots"] == 4
    q = day["syms"]["QQQ"]
    assert q["snaps"] == 3 and q["rows"] == 9
    assert q["rows_with_quotes"] == 3            # 1 de 3 filas por foto tiene bid/ask
    assert q["rows_with_greeks"] == 3
    assert day["full_chains"]["QQQ"]["with_greeks"] == 1
    assert day["full_chains"]["QQQ"]["with_quotes"] == 0
    assert os.path.exists(cube.INDEX_PATH)


def test_escritura_atomica_no_deja_ficheros_a_medias(cube, tmp_path):
    p = str(tmp_path / "x.json")
    cube.atomic_write_json(p, {"a": 1})
    cube.atomic_write_json(p, {"a": 2})
    assert json.load(open(p)) == {"a": 2}
    assert not [f for f in os.listdir(str(tmp_path)) if ".tmp" in f]
