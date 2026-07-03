#!/usr/bin/env python3
"""Pulso RSI/BB del panel arriba-izquierda del cockpit.

Valores de REFERENCIA externos (no self-consistency):
  · RSI(14) Wilder — serie canonica de Wilder ("New Concepts in Technical Trading
    Systems", 1978) reproducida en StockCharts: sus 33 cierres dan 70.53 / 66.32 /
    … / 37.77. Verificado ademas contra pandas `ewm(alpha=1/14, adjust=False)`
    (implementacion independiente): identico a 2 decimales en toda la serie.
  · BB(20,2) con desviacion POBLACION (÷N) — la misma que usan las bandas dibujadas
    (compute_indicators) y bollinger_alarm.py. Se comprueba contra numeros calculados
    a mano sobre series construidas para tener media y sd exactas.
"""
import importlib.util
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def cb():
    spec = importlib.util.spec_from_file_location(
        "cb_pulse", os.path.join(REPO, "scripts", "chart_bridge.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _bars(closes, t0=1_700_000_000, step=60):
    """[ts,o,h,l,c,v] con o=h=l=c: aisla el indicador de la forma de la vela."""
    return [[t0 + i * step, c, c, c, c, 1000.0] for i, c in enumerate(closes)]


# serie canonica de Wilder (33 cierres) usada por StockCharts para documentar RSI(14)
WILDER = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245,
          45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028,
          46.0328, 46.4116, 46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515,
          45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672, 43.4205, 42.6628,
          43.1314]


# ------------------------------- RSI ----------------------------------------
def test_rsi14_contra_serie_de_wilder(cb):
    import confluence_engine as ce
    r = ce.rsi_series(WILDER, 14)
    assert round(r[14], 2) == 70.53     # primera lectura (media simple de 14)
    assert round(r[15], 2) == 66.32     # ya suavizada a lo Wilder
    assert round(r[-1], 2) == 37.77     # cola de la serie canonica


def test_rsi_extremos_conocidos(cb):
    import confluence_engine as ce
    subida = [100 + i for i in range(40)]          # solo ganancias -> RSI -> 100
    bajada = [200 - i for i in range(40)]          # solo perdidas  -> RSI -> 0
    assert round(ce.rsi_series(subida, 14)[-1], 6) == 100.0
    assert round(ce.rsi_series(bajada, 14)[-1], 6) == 0.0


def test_rsi_none_sin_warmup(cb):
    """n<=14 no da RSI: el panel debe recibir None, no un 50 plausible."""
    import confluence_engine as ce
    assert ce.rsi_series([100.0] * 14, 14) == [None] * 14


# ------------------------------- %B -----------------------------------------
def test_pctb_valores_calculados_a_mano(cb):
    # 19 cierres a 100 + el ultimo a 110 -> media = 100.5, sd(pobl) = sqrt(9.5*10) ...
    closes = [100.0] * 19 + [110.0]
    m = sum(closes) / 20
    sd = (sum((c - m) ** 2 for c in closes) / 20) ** 0.5
    up, lo = m + 2 * sd, m - 2 * sd
    bb = cb.bb_state(closes)
    assert bb is not None
    assert abs(bb["pctb"] - (110.0 - lo) / (up - lo)) < 1e-12
    assert abs(bb["upper"] - up) < 1e-9 and abs(bb["lower"] - lo) < 1e-9
    assert round(bb["pctb"], 4) == 1.5897   # el outlier SI revienta la banda superior


def test_pctb_centro_exacto(cb):
    """Serie simetrica: el ultimo cierre en la media -> %B = 0.5 EXACTO (calculado, no default)."""
    closes = [98.0, 102.0] * 9 + [100.0, 100.0]   # media exacta 100, ultimo cierre = media
    bb = cb.bb_state(closes)
    assert abs(bb["pctb"] - 0.5) < 1e-9


def test_pctb_fuera_de_banda_arriba_y_abajo(cb):
    arriba = [100.0] * 19 + [200.0]
    abajo = [100.0] * 19 + [1.0]
    assert cb.bb_state(arriba)["pctb"] > 1.0
    assert cb.bb_state(abajo)["pctb"] < 0.0


def test_bb_none_sin_20_cierres_y_sin_varianza(cb):
    assert cb.bb_state([100.0] * 19) is None        # falta warmup
    assert cb.bb_state([100.0] * 20) is None        # sd=0: banda degenerada, no 0.5


def test_bb_paridad_con_las_bandas_dibujadas(cb):
    """bb_state NO puede contradecir a compute_indicators (mismas bandas en pantalla)."""
    closes = [100.0 + (i % 7) * 0.9 - (i % 3) * 1.3 for i in range(60)]
    ind = cb.compute_indicators(_bars(closes))
    bb = cb.bb_state(closes)
    assert abs(bb["upper"] - ind["bbUpper"][-1]) < 1e-9
    assert abs(bb["lower"] - ind["bbLower"][-1]) < 1e-9
    assert abs(bb["mid"] - ind["bbMid"][-1]) < 1e-9


# ------------------------------ filas ---------------------------------------
def test_row_fail_loud_pocas_barras(cb):
    r = cb.pulse_row("1m", _bars([100.0] * 12))
    assert r["rsi"] is None and r["pctb"] is None
    assert "hay 12" in r["why"]


def test_row_rsi_sin_bb_declara_el_motivo(cb):
    """18 cierres: alcanza para RSI(14) pero NO para BB(20). Cada indicador con su warmup:
    el que falta se declara, el que hay se publica — nunca se apaga la fila entera."""
    closes = [100.0 + i * 0.1 for i in range(18)]
    r = cb.pulse_row("1m", _bars(closes))
    assert r["rsi"] is not None
    assert r["pctb"] is None and "BB(20) exige 20, hay 18" in r["why"]


def test_row_completa(cb):
    closes = [100.0 + i * 0.05 for i in range(60)]
    r = cb.pulse_row("15m", _bars(closes), active=True)
    assert r["tf"] == "15m" and r["active"] is True and r["n"] == 60
    assert 0.0 <= r["pctb"] <= 1.2 and 0.0 <= r["rsi"] <= 100.0
    assert r["ts"] == 1_700_000_000 + 59 * 60
    assert r["why"] is None


# ----------------------------- veredicto ------------------------------------
def _row(tf, pctb):
    return {"tf": tf, "n": 60, "active": False, "rsi": 50.0, "pctb": pctb,
            "bw": 1.0, "ts": 1, "why": None}


def test_veredicto_bandwalk_arriba_es_alcista(cb):
    v = cb.pulse_verdict([_row("1m", 1.2), _row("15m", 1.05)])
    assert v["label"] == "ALCISTA" and v["kind"] == "bandwalk"
    assert v["tfs"] == ["1m", "15m"]


def test_veredicto_bandwalk_abajo_es_bajista(cb):
    v = cb.pulse_verdict([_row("1m", -0.1), _row("15m", -0.02), _row("5m", 0.4)])
    assert v["label"] == "BAJISTA" and v["kind"] == "bandwalk"


def test_veredicto_elastico_invierte_el_signo(cb):
    """Doctrina de la casa: reventada en UN solo marco = rebote elastico -> sesgo CONTRARIO."""
    arriba = cb.pulse_verdict([_row("1m", 1.3), _row("15m", 0.6)])
    assert arriba["label"] == "BAJISTA" and arriba["kind"] == "elastico"
    abajo = cb.pulse_verdict([_row("1m", -0.2), _row("15m", 0.4)])
    assert abajo["label"] == "ALCISTA" and abajo["kind"] == "elastico"


def test_veredicto_neutro_dentro_de_bandas(cb):
    v = cb.pulse_verdict([_row("1m", 0.55), _row("15m", 0.42)])
    assert v["label"] == "NEUTRO" and v["tfs"] == []


def test_veredicto_sin_datos_nunca_neutro(cb):
    """PROHIBIDO el neutro por defecto: sin %B en ninguna fila se dice SIN DATOS + motivo."""
    v = cb.pulse_verdict([{"tf": "1m", "pctb": None, "why": "n=3 · BB(20) exige 20"},
                          {"tf": "15m", "pctb": None, "why": "n=0 · BB(20) exige 20"}])
    assert v["label"] == "SIN DATOS" and v["kind"] == "nodata"
    assert "n=3" in v["why"] and "n=0" in v["why"]


def test_veredicto_ignora_filas_sin_pctb(cb):
    v = cb.pulse_verdict([_row("1m", 1.4), {"tf": "15m", "pctb": None, "why": "n=2"}])
    assert v["label"] == "BAJISTA" and v["kind"] == "elastico"   # solo vota la fila con dato


# ------------------------------ compute_pulse -------------------------------
def test_compute_pulse_tf_activo_sale_de_las_velas_del_chart(cb, monkeypatch):
    """El tf activo NO puede venir del fichero: si contradice las bandas dibujadas, miente."""
    monkeypatch.setattr(cb, "pulse_bars_1m", lambda s, max_age_s=1.0: [])
    view = _bars([100.0 + i * 0.03 for i in range(80)])
    p = cb.compute_pulse("qqq", view, "1m")
    assert p["sym"] == "QQQ" and p["tf"] == "1m"
    fila1m = [r for r in p["rows"] if r["tf"] == "1m"][0]
    assert fila1m["active"] is True and fila1m["n"] == 80
    fila15 = [r for r in p["rows"] if r["tf"] == "15m"][0]
    assert fila15["pctb"] is None and "bars_qqq_ibkr.txt" in fila15["why"]


def test_compute_pulse_tercera_fila_para_tf_no_estandar(cb, monkeypatch):
    monkeypatch.setattr(cb, "pulse_bars_1m",
                        lambda s, max_age_s=1.0: _bars([100.0 + i * 0.01 for i in range(600)]))
    p = cb.compute_pulse("mu", _bars([100.0] * 40), "5m")
    assert [r["tf"] for r in p["rows"]] == ["1m", "15m", "5m"]
    assert p["rows"][2]["active"] is True
    assert p["rows"][0]["active"] is False and p["rows"][1]["active"] is False
    assert p["rows"][1]["n"] == 41      # 600 barras 1m -> 41 buckets de 15m (el 1º parcial)


def test_compute_pulse_sin_barras_dice_sin_datos(cb, monkeypatch):
    monkeypatch.setattr(cb, "pulse_bars_1m", lambda s, max_age_s=1.0: [])
    p = cb.compute_pulse("nvda", [], "1m")
    assert p["verdict"]["label"] == "SIN DATOS"
    assert p["ts"] is None


def test_frames_llevan_pulse(cb, monkeypatch):
    """Contrato con el front: history y bar traen `pulse` (aditivo, sin romper lo existente)."""
    monkeypatch.setattr(cb, "pulse_bars_1m", lambda s, max_age_s=1.0: [])
    bars = _bars([100.0 + (i % 5) * 0.4 for i in range(60)])
    hf = cb.history_frame(bars, {}, "1m", sym="qqq")
    bf = cb.bar_frame(bars, {}, "1m", sym="qqq")
    for f in (hf, bf):
        assert f["pulse"]["sym"] == "QQQ"
        assert f["pulse"]["verdict"]["label"] in ("ALCISTA", "BAJISTA", "NEUTRO", "SIN DATOS")
    assert "indicators" in hf and "bars" in hf      # nada de lo anterior se perdio
