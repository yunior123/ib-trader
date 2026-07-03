"""Portero de CONVICCION de uw_fleet_flow (Yunior 2026-08-07: "less annoying ... only
strong conviction"). Se prueba contra el ARCHIVO real (data/history/*/uw_flow_alerts_*.json),
no contra fixtures inventadas: si el archivo no esta, el test se salta y lo DICE."""
import glob
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def uw():
    return _load("uw_fleet_flow")


@pytest.fixture(scope="module")
def archivo():
    rows = []
    for f in glob.glob(os.path.join(REPO, "data", "history", "*", "uw_flow_alerts_*.json")):
        try:
            with open(f) as fh:
                rows.extend(json.load(fh)["payload"]["data"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if len(rows) < 500:
        pytest.skip("archivo de flow-alerts insuficiente (%d filas)" % len(rows))
    return rows


def test_mid_nunca_canta(uw, archivo):
    """Sin lado agresor no hay direccion: al mid jamas se canta (antes solo lo exigia
    la regla del premium)."""
    for r in archivo:
        q = uw.qualifies(r, {})
        if q is not None:
            assert q[1]["lado"] != "mid"


def test_relevancia_veta_las_pequeñas(uw, archivo):
    """Con ADV enorme ninguna ballena pesa: el gate de relevancia tiene que vaciar la cinta."""
    adv_gigante = {r["ticker"].upper(): 1e15 for r in archivo}
    assert all(uw.qualifies(r, adv_gigante) is None for r in archivo)


def test_relevancia_deja_pasar_cuando_pesa(uw, archivo):
    """Con ADV minusculo el gate no puede ser el que bloquea: debe pasar lo mismo que
    sin gate de relevancia (el resto de reglas manda)."""
    adv_minimo = {r["ticker"].upper(): 1.0 for r in archivo}
    con = sum(1 for r in archivo if uw.qualifies(r, adv_minimo))
    sin = sum(1 for r in archivo if uw.qualifies(r, {}))
    assert con == sin > 0


def test_sin_adv_no_inventa_relevancia(uw, archivo):
    """Simbolo sin ADV: `rel` es None y se explica. Jamas un 0 ni un 1 plausible."""
    vistos = 0
    for r in archivo:
        q = uw.qualifies(r, {})
        if q is None:
            continue
        vistos += 1
        assert q[1]["rel"] is None
        assert "sin ADV" in q[1]["rel_motivo"]
    assert vistos > 0


def test_respaldo_cuenta_contratos_distintos(uw):
    """Respaldo = otras ballenas del mismo sesgo, contrato DISTINTO, dentro de la ventana.
    El mismo contrato repetido no se respalda a si mismo."""
    hist = [{"ts": 1000.0, "sym": "SPY", "sesgo": "BULLISH", "chain": "A"},
            {"ts": 1010.0, "sym": "SPY", "sesgo": "BULLISH", "chain": "A"},
            {"ts": 1020.0, "sym": "SPY", "sesgo": "BEARISH", "chain": "B"},
            {"ts": 1030.0, "sym": "QQQ", "sesgo": "BULLISH", "chain": "C"}]
    assert uw.respaldo(list(hist), "SPY", "BULLISH", "A", 1040.0) == set()
    assert uw.respaldo(list(hist), "SPY", "BULLISH", "D", 1040.0) == {"A"}
    # fuera de la ventana no respalda nada, y el historial se poda
    h = list(hist)
    assert uw.respaldo(h, "SPY", "BULLISH", "D", 1000.0 + uw.RESPALDO_VENTANA_S + 60) == set()
    assert h == []


def test_reduccion_de_ruido_medida(uw, archivo):
    """La reduccion tiene que ser REAL y se publica: es la razon de ser del cambio."""
    import sqlite3
    adv = {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % os.path.join(REPO, "data", "trades.db"), uri=True)
        for (sym,) in con.execute("select distinct sym from poly_bars"):
            v = [x for _, x in con.execute(
                "select date(ts/1000,'unixepoch') d, sum(v*c) from poly_bars where sym=? "
                "group by d order by d desc limit 20", (sym,)).fetchall() if x]
            if len(v) >= 10:
                adv[sym.upper()] = sum(v) / len(v)
        con.close()
    except Exception:                                     # noqa: BLE001
        pytest.skip("poly_bars no disponible para el ADV")
    if not adv:
        pytest.skip("sin ADV medible")

    def gate_viejo(r):
        try:
            prem = float(r["total_premium"])
            voloi = float(r["volume_oi_ratio"])
            lado = uw.side(r)
        except (KeyError, TypeError, ValueError):
            return False
        return ((prem >= uw.MIN_PREM_GRANDE and lado != "mid")
                or (voloi >= uw.MIN_VOLOI and prem >= uw.MIN_PREM_VOLOI)
                or (bool(r.get("has_sweep")) and prem >= uw.MIN_PREM_SWEEP))

    viejo = sum(1 for r in archivo if gate_viejo(r))
    nuevo = sum(1 for r in archivo if uw.qualifies(r, adv))
    assert viejo > 0
    print("\nconviccion: %d -> %d candidatas (%.0f%% del ruido fuera) sobre %d alertas"
          % (viejo, nuevo, 100 * (1 - nuevo / viejo), len(archivo)))
    assert nuevo < viejo * 0.75          # el gate tiene que MORDER, o no sirve de nada
