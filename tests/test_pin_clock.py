"""pin_clock: max pain correcto en un perfil SINTETICO hecho a mano, y sin OI -> None.

El max pain de un perfil de juguete se calcula aparte, a mano, en el docstring del test:
si el codigo y la aritmetica no coinciden, el test manda.
"""
import datetime as dt
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


@pytest.fixture()
def pc(tmp_path):
    m = _load("pin_clock")
    m.levels_of = lambda s: None
    m.CUBE.latest_chain = lambda s: None
    m.CUBE.full_chain_path = lambda s, date=None: None
    m._TMP = str(tmp_path)
    return m


def _row(pc, strike, right, exp, oi):
    return pc.CUBE.ChainRow("TEST", 0, exp, strike, right, None, None, None, oi,
                            None, None, None, "polygon_snapshot", ("bid", "ask"), {})


EXP = 20260727


def test_max_pain_de_un_perfil_a_mano(pc):
    """Perfil: calls OI 100 en 90 y 100 en 100; puts OI 100 en 110 y 100 en 100.
      pain(90)  = puts(100)*10*100 + puts(110)*20*100        = 100000 + 200000 = 300000
      pain(100) = calls(90)*10*100 + puts(110)*10*100        = 100000 + 100000 = 200000
      pain(110) = calls(90)*20*100 + calls(100)*10*100       = 200000 + 100000 = 300000
    -> max_pain = 100 (el minimo del dolor)."""
    rows = [_row(pc, 90, "C", EXP, 100), _row(pc, 100, "C", EXP, 100),
            _row(pc, 110, "P", EXP, 100), _row(pc, 100, "P", EXP, 100)]
    mp, prof, call_oi, put_oi = pc.max_pain_of(rows, EXP)
    assert prof[90.0] == 300000
    assert prof[100.0] == 200000
    assert prof[110.0] == 300000
    assert mp == 100.0


def test_max_pain_se_va_al_lado_del_oi_gordo(pc):
    rows = [_row(pc, 100, "C", EXP, 10), _row(pc, 105, "C", EXP, 10),
            _row(pc, 110, "P", EXP, 5000), _row(pc, 105, "P", EXP, 10)]
    mp, prof, _c, _p = pc.max_pain_of(rows, EXP)
    assert mp == 110.0, prof


def test_expiries_posteriores_al_viernes_no_cuentan(pc):
    rows = [_row(pc, 100, "C", EXP, 100), _row(pc, 100, "P", EXP, 100),
            _row(pc, 200, "P", 20261218, 100000)]      # LEAP gigante: fuera
    mp, _prof, _c, _p = pc.max_pain_of(rows, EXP)
    assert mp == 100.0


def test_sin_oi_devuelve_none_no_cero(pc):
    rows = [_row(pc, 100, "C", EXP, None), _row(pc, 100, "P", EXP, 0)]
    mp, prof, _c, _p = pc.max_pain_of(rows, EXP)
    assert mp is None and prof is None


def test_width_es_el_intervalo_modal(pc):
    assert pc.strike_width([100, 105, 110, 115, 116]) == 5.0
    assert pc.strike_width([9.0, 9.5, 10.0]) == 0.5
    assert pc.strike_width([100]) is None
    assert pc.strike_width([]) is None


def test_oi_dentro_de_dos_strikes(pc):
    call_oi = {100.0: 10, 105.0: 20, 130.0: 999}
    put_oi = {95.0: 30, 90.0: 40}
    # centro 100, width 5 -> [90, 110] incluye 90,95,100,105 y NO 130
    assert pc.oi_within(call_oi, put_oi, 100.0, 5.0, 2) == 100


# --------------------------------------------------------- veredicto completo

def _full_chain(pc, tmp_path, rows_spec, spot=100.0, sym="test"):
    results = []
    for strike, right, exp, oi in rows_spec:
        results.append({"details": {"contract_type": "call" if right == "C" else "put",
                                    "expiration_date": "%s-%s-%s" % (str(exp)[:4], str(exp)[4:6], str(exp)[6:]),
                                    "strike_price": strike},
                        "open_interest": oi, "implied_volatility": 0.3,
                        "greeks": {"delta": 0.5, "gamma": 0.05}, "day": {"volume": 1}})
    p = tmp_path / ("chain_full_%s.json" % sym)
    with open(str(p), "w") as f:
        json.dump({"meta": {"sym": sym.upper(), "snapshot_epoch": 1784966926.0, "spot": spot},
                   "results": results}, f)
    pc.CUBE.full_chain_path = lambda s, date=None: str(p)
    return str(p)


FRI = int(dt.date.today().strftime("%Y%m%d"))       # el exp_max lo calcula el modulo


def test_pin_day_solo_con_muro_tipo_pin(pc, tmp_path):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 3000), (100, "C", exp, 3000),
                               (100, "P", exp, 3000), (105, "P", exp, 3000)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "pin"}
    r = pc.pin_clock("TEST")
    assert r["max_pain"] == 100.0 and r["width"] == 5.0
    assert r["pin"] == 100.0 and r["zone"] == [98.75, 101.25]
    assert r["verdict"] == "PIN_DAY"
    assert r["zero_dte_buy_forbidden"] is True       # spot 100 dentro de la zona
    assert r["p_pin"] is None and r["corr_abs_wall_60d"] is None


def test_trampilla_no_es_pin_es_release(pc, tmp_path):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 3000), (100, "C", exp, 3000),
                               (100, "P", exp, 3000), (105, "P", exp, 3000)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "trampilla"}
    r = pc.pin_clock("TEST")
    assert r["verdict"] == "RELEASE"
    assert r["zero_dte_buy_forbidden"] is False


def test_sin_signo_de_muro_no_se_afirma_pin(pc, tmp_path):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 3000), (100, "C", exp, 3000),
                               (100, "P", exp, 3000), (105, "P", exp, 3000)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0}
    r = pc.pin_clock("TEST")
    assert r["abs_wall_sign"] is None
    assert r["verdict"] == "NEUTRAL"


def test_oi_flaco_no_declara_pin(pc, tmp_path):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 10), (100, "C", exp, 10),
                               (100, "P", exp, 10), (105, "P", exp, 10)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "pin"}
    r = pc.pin_clock("TEST")
    assert r["pin"] is None and r["verdict"] == "NEUTRAL"
    assert "OI insuficiente" in r["reason"]


def test_max_pain_lejos_del_muro_no_declara_pin(pc, tmp_path):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 3000), (100, "C", exp, 3000),
                               (100, "P", exp, 3000), (105, "P", exp, 3000)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 140.0, "abs_wall_kind": "pin"}
    r = pc.pin_clock("TEST")
    assert r["pin"] is None and "lejos del abs_wall" in r["reason"]


def test_indice_exige_mas_oi_que_un_nombre(pc, tmp_path):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 500), (100, "C", exp, 500),
                               (100, "P", exp, 500), (105, "P", exp, 500)], sym="qqq")
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "pin"}
    q = pc.pin_clock("QQQ")
    assert q["min_oi_required"] == pc.MIN_OI_INDEX and q["pin"] is None    # 2000 < 5000
    n = pc.pin_clock("NVDA")
    assert n["min_oi_required"] == pc.MIN_OI_NAME and n["pin"] == 100.0    # 2000 >= 1000


def test_sin_cadena_completa_no_usa_la_banda_de_ibkr(pc, tmp_path):
    """La banda de +-1,45% de IBKR empuja el max pain al spot: se publica como diagnostico
    marcado, jamas como max_pain."""
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    live = tmp_path / "opt_chain_test.txt"
    live.write_text(
        "# opt_chain TEST | epoch 1784924179 | x | spot 100.00 | exps {e}\n"
        "# strike right exp bid ask vol oi iv delta gamma\n"
        "99.00 C {e} -1.00 -1.00 10 3000 -1.0000 -1.0000 -1.0000\n"
        "100.00 P {e} -1.00 -1.00 10 3000 -1.0000 -1.0000 -1.0000\n".format(e=exp))
    pc.CUBE.latest_chain = lambda s: str(live)
    pc.CUBE.full_chain_path = lambda s, date=None: None
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "pin"}
    r = pc.pin_clock("TEST")
    assert r["reason"] == "sin_cadena_completa"
    assert r["max_pain"] is None
    assert r["max_pain_ibkr_band"] is not None and r["band_biased"] is True
    assert r["verdict"] == "NEUTRAL" and r["pin"] is None


def test_colinealidad_no_concluye_con_pocos_syms(pc, tmp_path):
    pc.fleet = lambda: ["TEST"]
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 3000), (100, "C", exp, 3000),
                               (100, "P", exp, 3000), (105, "P", exp, 3000)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "pin"}
    c = pc.colinearity()
    assert c["n"] == 1 and c["verdict"] == "DATOS_INSUFICIENTES" and c["rho"] is None


def test_escritura_atomica(pc, tmp_path, monkeypatch):
    exp = int(pc.next_friday().strftime("%Y%m%d"))
    _full_chain(pc, tmp_path, [(95, "C", exp, 3000), (100, "C", exp, 3000),
                               (100, "P", exp, 3000), (105, "P", exp, 3000)])
    pc.levels_of = lambda s: {"spot": 100.0, "abs_wall": 100.0, "abs_wall_kind": "pin"}
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    r = pc.write_pin("TEST")
    assert json.load(open(os.path.join("data", "pin_test.json")))["pin"] == r["pin"]
    assert not [f for f in os.listdir("data") if ".tmp" in f]


def test_proximo_viernes(pc):
    assert pc.next_friday(dt.date(2026, 7, 25)) == dt.date(2026, 7, 31)   # sabado -> viernes 31
    assert pc.next_friday(dt.date(2026, 7, 24)) == dt.date(2026, 7, 24)   # viernes -> hoy
    assert pc.next_friday(dt.date(2026, 7, 27)) == dt.date(2026, 7, 31)   # lunes -> viernes
