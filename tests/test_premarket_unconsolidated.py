"""Tests del archivador premarket no consolidado y de su calibrador.

Los scripts de descarga corren con ./venv-mit (databento); estos tests corren con ./venv,
por eso el import de databento es PEREZOSO dentro de _hist() y el modulo se importa sin el
paquete instalado.
"""
import datetime as dt
import importlib.util
import json
import os
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
def pu():
    return _load("premarket_unconsolidated")


@pytest.fixture(scope="module")
def pc():
    return _load("premarket_calibrate")


def _ts(hh, mm):
    """Epoch de una hora ET del 2026-08-05 (dentro del premarket)."""
    from zoneinfo import ZoneInfo
    return dt.datetime(2026, 8, 5, hh, mm, tzinfo=ZoneInfo("America/New_York")).timestamp()


# ------------------------------------------------------------------ 1. Lee-Ready

def test_lee_ready_encima_del_mid_es_comprador(pu):
    assert pu.classify_lee_ready([{"price": 100.06, "bid": 100.00, "ask": 100.10}]) == [1]


def test_lee_ready_debajo_del_mid_es_vendedor(pu):
    assert pu.classify_lee_ready([{"price": 100.02, "bid": 100.00, "ask": 100.10}]) == [-1]


def test_lee_ready_en_el_mid_usa_tick_test(pu):
    rows = [
        {"price": 99.99, "bid": 99.98, "ask": 100.02},    # debajo del mid (100.00) -> vendedor
        {"price": 100.05, "bid": 100.00, "ask": 100.10},  # EN el mid, sube vs 99.99 -> comprador
        {"price": 100.05, "bid": 100.02, "ask": 100.08},  # EN el mid y precio repetido: zero-tick
        {"price": 100.00, "bid": 99.95, "ask": 100.05},   # EN el mid, baja vs 100.05 -> vendedor
    ]
    signs = pu.classify_lee_ready(rows)
    assert signs[0] == -1
    assert signs[1] == 1, "tick test al alza tras 99.99"
    # tercer trade: precio igual al anterior -> zero-tick contra el ultimo precio DISTINTO
    assert signs[2] == 1
    assert signs[3] == -1, "tick test a la baja"


def test_lee_ready_en_el_mid_sin_referencia_previa_no_se_clasifica(pu):
    assert pu.classify_lee_ready([{"price": 100.05, "bid": 100.00, "ask": 100.10}]) == [None]


def test_lee_ready_sin_quote_no_clasifica_ni_reparte(pu):
    rows = [
        {"ts": _ts(5, 0), "price": 100.06, "size": 100, "bid": 100.00, "ask": 100.10},
        {"ts": _ts(5, 1), "price": 100.06, "size": 500, "bid": None, "ask": None},
        {"ts": _ts(5, 2), "price": 100.06, "size": 300, "bid": 0.0, "ask": 0.0},
    ]
    assert pu.classify_lee_ready(rows) == [1, None, None]
    tramos, total = pu.build_tape(rows)
    assert len(tramos) == 1
    b = tramos[0]
    assert b["n_sin_clasificar"] == 2
    assert b["vol_sin_clasificar"] == 800
    assert b["buy_vol"] == 100 and b["sell_vol"] == 0, "el volumen sin quote NO se reparte"
    assert b["signed_vol"] == 100
    assert b["vol"] == 900, "el volumen total SI incluye los no clasificados"
    assert total["n_sin_clasificar"] == 2 and total["signed_vol"] == 100


def test_build_tape_agrupa_en_tramos_de_5_min(pu):
    rows = [
        {"ts": _ts(4, 1), "price": 10.0, "size": 10, "bid": 9.9, "ask": 10.1},
        {"ts": _ts(4, 4), "price": 10.2, "size": 10, "bid": 9.9, "ask": 10.1},
        {"ts": _ts(4, 6), "price": 10.0, "size": 20, "bid": 9.9, "ask": 10.1},
        {"ts": _ts(10, 0), "price": 10.0, "size": 99, "bid": 9.9, "ask": 10.1},  # fuera: RTH
    ]
    tramos, total = pu.build_tape(rows)
    assert [b["t"] for b in tramos] == ["04:00", "04:05"]
    assert total["n_trades"] == 3 and total["vol"] == 40
    assert total["last_px"] == 10.0


# --------------------------------------------------------- 2. imbalance_ratio

def test_imbalance_ratio_denominador_cero_es_none(pu):
    assert pu.imbalance_ratio(0, 0) is None
    assert pu.imbalance_ratio(0, 0) is not False
    assert pu.imbalance_ratio(None, 10) is None
    assert pu.imbalance_ratio(10, None) is None


def test_imbalance_ratio_normal(pu):
    assert pu.imbalance_ratio(90, 10) == pytest.approx(0.10)


def test_reduce_imbalance_deja_el_ultimo_de_cada_minuto(pu):
    rows = [
        {"ts": _ts(9, 28), "ref_price": 1.0, "paired_qty": 100, "total_imbalance_qty": 10, "side": "B"},
        {"ts": _ts(9, 28) + 30, "ref_price": 2.0, "paired_qty": 0, "total_imbalance_qty": 0, "side": "A"},
        {"ts": _ts(9, 29), "ref_price": 3.0, "paired_qty": 50, "total_imbalance_qty": 50, "side": "B"},
    ]
    out = pu.reduce_imbalance(rows)
    assert [p["hhmm"] for p in out] == ["09:28", "09:29"]
    assert out[0]["ref_price"] == 2.0, "gana el ULTIMO del minuto"
    assert out[0]["imbalance_ratio"] is None, "denominador 0 -> None, jamas 0.0"
    assert out[1]["imbalance_ratio"] == pytest.approx(0.5)


# ------------------------------------------- 5. gate de coste ANTES de descargar

class _FakeMetadata:
    def __init__(self, cost):
        self.cost = cost
        self.llamadas = 0

    def get_cost(self, **kw):
        self.llamadas += 1
        return self.cost


class _FakeTimeseries:
    def __init__(self):
        self.llamadas = 0

    def get_range(self, **kw):
        self.llamadas += 1
        raise AssertionError("se descargo pese a superar el tope de coste")


class _FakeHist:
    def __init__(self, cost):
        self.metadata = _FakeMetadata(cost)
        self.timeseries = _FakeTimeseries()


def test_gate_aborta_antes_de_descargar_si_supera_max_cost(pu):
    hist = _FakeHist(cost=5.0)
    gate = pu.CostGate(hist, max_cost=0.50)
    with pytest.raises(pu.PremarketError) as exc:
        pu.fetch_symbol(hist, gate, "SPY", dt.date(2026, 8, 5), "ARCX.PILLAR")
    assert "ABORTADO ANTES DE DESCARGAR" in str(exc.value)
    assert hist.timeseries.llamadas == 0, "no se pidio ni un byte"
    assert gate.spent == 0.0


def test_gate_acumula_y_corta_en_el_limite(pu):
    hist = _FakeHist(cost=0.20)
    gate = pu.CostGate(hist, max_cost=0.50)
    gate.check("a", dataset="X")
    gate.check("b", dataset="X")
    assert gate.spent == pytest.approx(0.40)
    with pytest.raises(pu.PremarketError):
        gate.check("c", dataset="X")


def test_gate_fail_loud_si_get_cost_revienta(pu):
    class _Boom:
        class metadata:
            @staticmethod
            def get_cost(**kw):
                raise RuntimeError("entitlement")
    gate = pu.CostGate(_Boom(), max_cost=0.50)
    with pytest.raises(pu.PremarketError) as exc:
        gate.check("x", dataset="X")
    assert "entitlement" in str(exc.value)


# -------------------------------------------------------- 3 y 4. el calibrador

def _doc(sym, fecha, signed_vol, vol, last_px, prev_close, op, px30, ratio, side):
    return {
        "meta": {"sym": sym, "fecha": fecha, "dataset": "XNAS.ITCH",
                 "clase_dato": "unconsolidated_direct"},
        "tape": [],
        "tape_total": {"vol": vol, "signed_vol": signed_vol, "last_px": last_px},
        "imbalance": [{"ts": 0, "hhmm": "09:28", "ref_price": op, "paired_qty": 100,
                       "total_imbalance_qty": 10, "side": side, "imbalance_ratio": ratio}],
        "resultado": {"open": op, "px_30m": px30, "prev_close": prev_close,
                      "fuente": "XNAS.ITCH ohlcv-1m", "nota": None},
    }


def _muestra_pequena():
    docs = []
    for si, sym in enumerate(["A", "B", "C", "D", "E", "F"]):
        for di, fecha in enumerate(["2026-08-03", "2026-08-04", "2026-08-05"]):
            sv = (di + 1) * 1000 * (1 if si % 2 == 0 else -1)
            docs.append(_doc(sym, fecha, sv, 100000, 100.0 + di, 99.0,
                             100.0, 100.5 if si % 2 == 0 else 99.5,
                             0.05 + 0.01 * di, "B" if si % 2 == 0 else "A"))
    return docs


def test_calibrador_marca_medido_false_por_debajo_de_30(pc):
    out = pc.calibrate(_muestra_pequena())
    assert out["_meta"]["n_dias"] == 3
    assert out["_meta"]["n_simbolos"] == 6
    assert out["buckets"], "con datos debe salir al menos un bucket"
    for k, b in out["buckets"].items():
        assert b["n_eff"] < pc.MIN_NEFF
        assert b["medido"] is False, "%s no puede publicarse como medido" % k
        assert 0.0 <= b["wr"] <= 1.0
        assert 0.0 <= b["lo"] <= 1.0
        assert b["lo"] <= b["wr"] + 1e-9


def test_calibrador_contrato_de_claves(pc):
    out = pc.calibrate(_muestra_pequena())
    assert set(out) == {"_meta", "buckets"}
    assert set(out["_meta"]) == {"ts", "n_dias", "n_simbolos", "fuente", "clase_dato", "metodo"}
    assert out["_meta"]["clase_dato"] == "unconsolidated_direct"
    for k, b in out["buckets"].items():
        feat, bucket = k.split("|")
        assert feat in pc.FEATURES
        assert bucket in ("q1", "q2", "q3", "q4", "q5")
        assert set(b) == {"n", "n_eff", "wr", "lo", "mean_bps", "medido"}


def test_calibrador_sin_dias_escribe_n_dias_cero(pc, tmp_path):
    out_path = tmp_path / "premarket_calib.json"
    hist = tmp_path / "history"
    hist.mkdir()
    assert pc.main(["--hist-dir", str(hist), "--out", str(out_path)]) == 0
    doc = json.loads(out_path.read_text())
    assert doc["_meta"]["n_dias"] == 0
    assert doc["_meta"]["n_simbolos"] == 0
    assert doc["buckets"] == {}


def test_calibrador_no_cuenta_observaciones_sin_etiqueta(pc):
    docs = _muestra_pequena()
    for d in docs:
        d["resultado"]["px_30m"] = None       # sin etiqueta -> el dia no entra
    out = pc.calibrate(docs)
    assert out["buckets"] == {}


def test_imbalance_signed_firma_por_side(pc):
    doc = _doc("A", "2026-08-05", 1, 1, 1.0, 1.0, 1.0, 1.0, 0.2, "B")
    assert pc.imbalance_signed(doc) == pytest.approx(0.2)
    doc["imbalance"][0]["side"] = "A"
    assert pc.imbalance_signed(doc) == pytest.approx(-0.2)
    doc["imbalance"][0]["side"] = "?"
    assert pc.imbalance_signed(doc) is None, "lado desconocido no se firma a ojo"
    doc["imbalance"][0]["side"] = "B"
    doc["imbalance"][0]["hhmm"] = "09:29"
    assert pc.imbalance_signed(doc) is None, "09:29 ya no es 'antes de 09:29'"


def test_n_effective_sin_rho_es_el_numero_de_fechas(pc):
    assert pc.n_effective(n=30, n_dates=3, rho=None) == 3.0
    assert pc.n_effective(n=30, n_dates=3, rho=0.0) == pytest.approx(30.0)
    assert pc.n_effective(n=30, n_dates=3, rho=1.0) == pytest.approx(3.0)
    assert pc.n_effective(n=0, n_dates=0, rho=None) == 0.0
