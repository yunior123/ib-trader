"""Tests de scripts/backtest_harness.py — el WR con COSTE.

DEFECTO B (hunt 2026-07-24, `backtest_harness.py:72`):

    ret = (r[0] - entry) / entry * 100 * th
    win = 1 if ret > 0.05 else 0

Retorno a horizonte: sin stop, sin camino y sin coste. Los tests obligatorios:

  1. REFUTACION: un camino donde la definicion VIEJA canta victoria y la triple
     barrera ve el SL tocado primero. Es el bug hecho test.
  2. El coste JAMAS es 0 por defecto: atr/entry invalidos LEVANTAN.
  3. Un TP cuyo k_tp no cubre la friccion NO es una victoria neta.
  4. TIMEOUT -> None (nunca 0, nunca 0.5).
  5. Sin observaciones resueltas -> None y DATA-INSUFFICIENT, no un 0.5 fabricado.
  6. La propuesta se escribe en un .PROPUESTO.json y NUNCA en un fichero vivo.
"""
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
def BH():
    return _load("backtest_harness")


@pytest.fixture(scope="module")
def BL(BH):
    return BH.BL


def bars(*rows):
    """rows: (minuto, o, h, l, c) -> [(ts_s,o,h,l,c)] con base 1_000_000."""
    return [(1_000_000 + m * 60, o, h, l, c) for (m, o, h, l, c) in rows]


def old_horizon_win(path, entry, thesis):
    """La definicion VIEJA, tal cual estaba en la linea 72. Vive aqui, en el
    test, porque es lo que se esta REFUTANDO — ya no existe en el codigo."""
    last_close = path[-1][4]
    ret = (last_close - entry) / entry * 100 * thesis
    return 1 if ret > 0.05 else 0


# ------------------------------------------------------------------ caso 1 ---
def test_refutacion_retorno_a_horizonte_canta_victoria_con_el_stop_tocado(BH, BL):
    """EL TEST DEL DEFECTO B.

    Camino real de 15 minutos: la señal es alcista, entry=100. En el minuto 4 el
    precio cae a 98,6 (por debajo de un SL de 1 ATR = 99,0) y a los 15 minutos
    cierra en 100,3.

      - definicion VIEJA: ret = +0,30% > 0,05%  ->  WIN.
      - triple barrera:   el SL se toco en el minuto 4  ->  label 0 (PERDIDA).

    Con el bracket puesto, o con la put comprada, o con el operador mirando la
    pantalla, esa operacion esta CERRADA en el minuto 4. La definicion vieja
    cobraba una vuelta que ya no estabas para cobrar.
    """
    path = bars((1, 100.0, 100.3, 99.7, 100.1),
                (2, 100.1, 100.2, 99.5, 99.6),
                (3, 99.6, 99.8, 99.2, 99.3),
                (4, 99.3, 99.4, 98.6, 98.7),     # <-- SL 99.0 tocado aqui
                (5, 98.7, 99.6, 98.7, 99.5),
                (10, 99.5, 100.4, 99.4, 100.2),
                (15, 100.2, 100.5, 100.0, 100.3))

    assert old_horizon_win(path, 100.0, +1) == 1, "la definicion vieja canta WIN"

    r = BL.triple_barrier(path, entry=100.0, direction=+1,
                          tp_price=101.0, sl_price=99.0, atr=1.0,
                          entry_ts=1_000_000)
    assert r["label"] == 0, "la triple barrera ve el SL primero: es una PERDIDA"
    assert r["t_touch"] == pytest.approx(4.0)

    # y con coste el pago es aun peor que -1 ATR
    pay = BH.net_payoff(r["label"], 1.0, 1.0, entry=100.0, atr=1.0,
                        friction_pct=BH.FRICTION_PCT["opcion_atm"])
    assert pay < -1.0


def test_el_harness_ya_no_define_win_por_su_cuenta(BH):
    """El fichero no puede volver a tener su propia definicion de victoria en el
    camino de medida: la unica que queda es la de la linea base DEPRECATED, y
    esta detras del subcomando `baseline` y estampada en el dato."""
    src = open(os.path.join(SCRIPTS, "backtest_harness.py")).read()
    code = src.split('"""', 2)[2]          # fuera el docstring, que CITA el bug
    # la unica aparicion viva del umbral 0.05 esta dentro de run_baseline
    body = code.split("def run_baseline", 1)
    assert len(body) == 2, "run_baseline debe existir (la linea base del scoreboard)"
    assert "ret > 0.05" not in body[0], \
        "el camino de medida NO puede tener su propia definicion de win"
    assert "horizon_return_DEPRECATED" in src


# ------------------------------------------------------------------ caso 2 ---
@pytest.mark.parametrize("entry,atr", [(0.0, 1.0), (-1.0, 1.0), (None, 1.0),
                                       (100.0, 0.0), (100.0, -1.0), (100.0, None)])
def test_coste_levanta_ante_datos_invalidos_jamas_devuelve_cero(BH, entry, atr):
    """Regla ~/CLAUDE.md: un coste 0 plausible ES el defecto. Fail-loud."""
    with pytest.raises(ValueError):
        BH.cost_in_atr(entry, atr, BH.FRICTION_PCT["accion"])


def test_coste_en_atr_es_el_cociente_declarado(BH):
    # 0,340% de 200 = 0,68 en precio; con ATR 0,17 son 4 ATR de friccion.
    assert BH.cost_in_atr(200.0, 0.17, 0.340) == pytest.approx(4.0)


# ------------------------------------------------------------------ caso 3 ---
def test_tp_que_no_cubre_la_friccion_no_es_victoria_neta(BH):
    """El caso que mata a las opciones baratas: el precio SI llego al target
    (label=1) pero 1 ATR de barra de 1 minuto no paga el ida y vuelta.

    ATR = 0,10% del precio; friccion de opcion OTM = 0,34% -> 3,4 ATR.
    Ganar 1 ATR y pagar 3,4 ATR es perder 2,4 ATR."""
    pay = BH.net_payoff(1, k_tp=1.0, k_sl=1.0, entry=100.0, atr=0.10,
                        friction_pct=BH.FRICTION_PCT["opcion_otm"])
    assert pay == pytest.approx(1.0 - 3.4)
    assert pay < 0, "un TP tocado puede seguir siendo una perdida neta"


def test_el_coste_solo_puede_empeorar_el_pago(BH):
    gross = BH.net_payoff(1, 1.0, 1.0, 100.0, 1.0, BH.FRICTION_PCT["sin_coste"])
    for f in ("accion", "opcion_atm", "opcion_otm"):
        assert BH.net_payoff(1, 1.0, 1.0, 100.0, 1.0, BH.FRICTION_PCT[f]) < gross


# ------------------------------------------------------------------ caso 4 ---
def test_timeout_es_None_no_cero(BH):
    assert BH.net_payoff(None, 1.0, 1.0, 100.0, 1.0, 0.04) is None


def test_label_invalido_levanta(BH):
    with pytest.raises(ValueError):
        BH.net_payoff(2, 1.0, 1.0, 100.0, 1.0, 0.04)


# ------------------------------------------------------------------ caso 5 ---
def test_net_stats_sin_resueltas_es_None_no_medio(BH):
    obs = [(None, 100.0, 1.0, 1.0, 1.0)] * 20
    assert BH.net_stats(obs, 0.04) is None
    v, why = BH.verdict_of(None)
    assert v == "DATA-INSUFFICIENT"
    assert "sin observaciones" in why


def test_net_stats_excluye_timeouts_del_denominador(BH):
    obs = ([(1, 100.0, 1.0, 1.0, 1.0)] * 6 +
           [(0, 100.0, 1.0, 1.0, 1.0)] * 4 +
           [(None, 100.0, 1.0, 1.0, 1.0)] * 90)
    st = BH.net_stats(obs, BH.FRICTION_PCT["sin_coste"])
    assert st["n"] == 10, "el timeout no entra en el denominador"
    assert st["timeouts"] == 90
    assert st["wins"] == 6
    assert st["wr"] == pytest.approx(0.6)
    assert st["expectancy"] == pytest.approx(0.2)     # (6*1 - 4*1)/10
    assert st["trust"] is False                        # 10 < MIN_N


def test_verdicto_por_expectancia_no_por_win_rate(BH):
    """Skill measured-probability §2: un WR alto con k_tp chico es GEOMETRIA.
    70% de aciertos de 0,5 ATR contra 30% de fallos de 1,5 ATR pierde dinero, y
    el veredicto tiene que decirlo."""
    obs = ([(1, 100.0, 1.0, 0.5, 1.5)] * 70 +
           [(0, 100.0, 1.0, 0.5, 1.5)] * 30)
    st = BH.net_stats(obs, BH.FRICTION_PCT["sin_coste"])
    assert st["wr"] == pytest.approx(0.70)             # win rate estupendo
    assert st["expectancy"] == pytest.approx(-0.10)    # y pierde
    assert BH.verdict_of(st)[0] == "NEGATIVA"


def test_data_insuficiente_por_debajo_de_min_n(BH):
    obs = [(1, 100.0, 1.0, 1.0, 1.0)] * (BH.MIN_N - 1)
    st = BH.net_stats(obs, BH.FRICTION_PCT["sin_coste"])
    assert st["trust"] is False
    assert BH.verdict_of(st)[0] == "DATA-INSUFFICIENT"


# ------------------------------------------------------------------ caso 6 ---
def test_propose_escribe_propuesto_y_no_toca_ficheros_vivos(BH, tmp_path):
    """`data/signal_enable.json` y `data/calibration.json` los conmuta Yunior."""
    vivos = [os.path.join(REPO, "data", f)
             for f in ("signal_enable.json", "calibration.json")]
    antes = [(p, os.path.getmtime(p)) for p in vivos if os.path.exists(p)]

    out = str(tmp_path / "backtest_harness.PROPUESTO.json")
    prop = BH.run_propose(path=out, quiet=True)

    assert os.path.exists(out)
    assert prop["_meta"]["WARNING"].startswith("PROPUESTA")
    assert prop["_meta"]["reference_friction"] in BH.FRICTION_PCT
    # cada friccion declara su derivacion: nada de constantes huerfanas
    assert set(BH.FRICTION_PCT) == set(BH.FRICTION_WHY)
    disco = json.load(open(out))
    assert disco == prop
    for p, mt in antes:
        assert os.path.getmtime(p) == mt, "run_propose toco un fichero VIVO: %s" % p


def test_ninguna_celda_apta_puede_tener_expectancia_negativa(BH):
    res = BH.run_net(quiet=True)
    for name, r in res.items():
        if r["verdict"] != "APTA":
            continue
        assert r[BH.REFERENCE_FRICTION]["expectancy"] > 0, name
