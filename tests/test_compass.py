#!/usr/bin/env python3
"""test_compass.py — la BRUJULA (scripts/compass.py).

El test #1 es el escenario literal de Yunior (2026-07-25): SPY tocando el Muro put 740 con
flujo masivo de puts -> la flecha debe ir ARRIBA. Con la media ponderada anterior daba
ABAJO 61% por construccion; este archivo es la red que impide que vuelva a pasar.

Todo con barras sinteticas y niveles inyectados: no toca red, no necesita mercado abierto.
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import compass as C  # noqa: E402


def bars_touching(level, n=3, spot=None):
    """n barras 1m cuyo rango CONTIENE el nivel (= n lecturas / prints)."""
    spot = spot if spot is not None else level
    return [(i * 60, level + 0.4, level + 0.6, level - 0.3, spot, 1e6) for i in range(n)]


def ev_put_wall(**over):
    """El escenario de Yunior: SPY cayendo al Muro put 740, puts inundando, %B en el suelo."""
    ev = C.blank_evidence("SPY", 740.6)
    ev.update({
        "em": 8.0, "regime": "POS", "flip": 748.0,
        "levels": [{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1}],
        "bars": bars_touching(740.0, 3, 740.6),
        "r6": -0.62, "r15": -0.90, "z6": -2.6,
        "pctb_1m": 0.04, "pctb_15m": 0.08,
        "flow": 1.0, "force_phase": "AGOTAMIENTO",
    })
    ev.update(over)
    return ev


def ev_call_wall(**over):
    """Simetrico: subiendo al Muro call 690 con calls inundando (techo)."""
    ev = C.blank_evidence("QQQ", 689.5)
    ev.update({
        "em": 7.0, "regime": "POS", "flip": 682.0,
        "levels": [{"price": 690.0, "kind": "Muro call", "wall_kind": "pin", "touch_idx": 1}],
        "bars": bars_touching(690.0, 3, 689.5),
        "r6": 0.55, "r15": 0.80, "z6": 2.4,
        "pctb_1m": 0.95, "pctb_15m": 0.90,
        "flow": -1.0, "force_phase": "AGOTAMIENTO",
    })
    ev.update(over)
    return ev


# --------------------------------------------------------------------------- 1 y 2
def test_yunior_spy_put_wall_arrow_points_up():
    """EL test: Muro put impreso + flujo de puts + %B extremo -> ARRIBA."""
    r = C.classify(ev_put_wall())
    assert r["state"] == C.S_REV
    assert r["dir"] == "up", "la brujula debe GIRAR al alza en un piso impreso con puts inundando"
    assert r["prob"] > 50
    assert r["families"] >= 2
    # y debe DECIR que el momentum bajista es combustible, no esconderlo
    assert any("COMBUSTIBLE" in f for f in r["fading"])


def test_call_wall_arrow_points_down():
    r = C.classify(ev_call_wall())
    assert r["state"] == C.S_REV
    assert r["dir"] == "down"


# ----------------------------------------------------------------------------- vetos
def test_veto_bandwalk_blocks_the_fade():
    """Regla 1: banda reventada en >=2 TF A FAVOR = band-walk = continuacion, no rebote."""
    r = C.classify(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1))
    assert r["state"] == C.S_CONT
    assert r["dir"] == "down"
    assert any("band-walk" in w for w in r["state_why"])
    assert any("NO fadear" in w for w in r["state_why"])


def test_veto_trapdoor_blocks_the_fade():
    """Muro TRAMPILLA (gamma acumulada NEG en el nivel) no es piso: prohibido fadear."""
    r = C.classify(ev_put_wall(levels=[{"price": 740.0, "kind": "Muro put",
                                        "wall_kind": "trampilla", "touch_idx": 1}]))
    assert r["state"] == C.S_CONT
    assert any("TRAMPILLA" in w for w in r["state_why"])


def test_veto_below_vol_trigger_blocks_the_fade():
    r = C.classify(ev_put_wall(vt=745.0))
    assert r["state"] == C.S_CONT
    assert any("VT" in w for w in r["state_why"])


def test_veto_third_touch_blocks_the_fade():
    """Protocolo imanes: 3+ toques = muro exhausto -> lado de la ruptura, no fade."""
    r = C.classify(ev_put_wall(levels=[{"price": 740.0, "kind": "Muro put",
                                        "wall_kind": "pin", "touch_idx": 3}]))
    assert r["state"] == C.S_CONT
    assert any("toque" in w for w in r["state_why"])


def test_veto_negative_regime_without_pin():
    """Memoria negative-gamma-whipsaw: en NEG el nivel no es piso, es acelerador."""
    r = C.classify(ev_put_wall(regime="NEG",
                               levels=[{"price": 740.0, "kind": "Muro put",
                                        "wall_kind": None, "touch_idx": 1}]))
    assert r["state"] == C.S_CONT
    assert any("NEG" in w for w in r["state_why"])


def test_veto_leader_catalyst():
    """Excepcion explicita de la regla 11: con catalizador del lider la ballena continua."""
    r = C.classify(ev_put_wall(leader_catalyst=True))
    assert r["state"] == C.S_CONT


def test_negative_regime_WITH_printed_pin_still_reverses():
    """El veto NEG no debe ser una manta: con un pin impreso la reversion sigue viva."""
    r = C.classify(ev_put_wall(regime="NEG"))   # wall_kind='pin' por defecto
    assert r["state"] == C.S_REV
    assert r["dir"] == "up"


# ------------------------------------------------------------------- PRINT O NADA
def test_approaching_without_print_is_not_a_confident_arrow():
    """Sin 2 lecturas el estado es APROXIMANDO: se ve venir, no se afirma."""
    ev = ev_put_wall(bars=bars_touching(740.0, 1, 740.6))
    r = C.classify(ev)
    assert r["state"] == C.S_APPR
    assert r["pending_print"] is True
    assert r["dir"] == "up", "senala el rebote PENDIENTE, pero marcado como no impreso"
    assert any("esperando print" in w for w in r["state_why"])


def test_second_reading_promotes_to_reversal():
    one = C.classify(ev_put_wall(bars=bars_touching(740.0, 1, 740.6)))
    two = C.classify(ev_put_wall(bars=bars_touching(740.0, 2, 740.6)))
    assert one["state"] == C.S_APPR and one["pending_print"] is True
    assert two["state"] == C.S_REV and two["pending_print"] is False


def test_approaching_prob_is_lower_than_printed():
    appr = C.classify(ev_put_wall(bars=bars_touching(740.0, 1, 740.6)))
    rev = C.classify(ev_put_wall())
    assert appr["prob"] < rev["prob"]


# ------------------------------------------------------------------- familias
def test_one_family_is_not_enough():
    """Una sola familia no gira la brujula (senal marginal != decisiva)."""
    ev = ev_put_wall(pctb_1m=0.5, pctb_15m=0.5, force_phase=None, candle_bias=0)
    r = C.classify(ev)
    assert r["families"] == 1
    assert r["state"] != C.S_REV


def test_families_are_counted_and_named():
    r = C.classify(ev_put_wall())
    assert r["families"] == 3
    assert len(r["families_why"]) == 3
    assert any("puts=piso" in f for f in r["families_why"])


def test_pctb_extreme_needs_both_timeframes():
    """BOLLINGER-SIEMPRE es 1m Y 15m: un solo TF extremo no cuenta como familia."""
    r = C.classify(ev_put_wall(pctb_15m=0.5))
    assert not any("%B" in f for f in r["families_why"])


# ------------------------------------------------------- momentum como combustible
def test_momentum_is_fuel_not_a_vote():
    """A igual escenario de reversion, MAS momentum en contra -> MAS prob, no menos.
    Esto es lo contrario de lo que hacia la media ponderada."""
    soft = C.classify(ev_put_wall(r6=-0.15, z6=-0.5))
    hard = C.classify(ev_put_wall(r6=-1.20, z6=-3.4))
    assert soft["state"] == hard["state"] == C.S_REV
    assert hard["prob"] > soft["prob"], "el latigazo es mas elastico cuanto mas fuerte cayo"


# ------------------------------------------------------------------- histeresis
def test_hysteresis_needs_two_consecutive_computes():
    """Regla 3: un computo aislado NO cambia el estado; dos consecutivos si."""
    hist = {"state": None, "cand": None, "n": 0}
    C.classify(ev_put_wall(), hist=hist)                       # entra en REVERSION
    assert hist["state"] == C.S_REV
    flip1 = C.classify(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1), hist=hist)
    assert flip1["state"] == C.S_REV, "el primer computo discrepante no debe cambiar el estado"
    assert flip1["state_pending"] == C.S_CONT
    flip2 = C.classify(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1), hist=hist)
    assert flip2["state"] == C.S_CONT, "el segundo consecutivo si cambia"


def test_hysteresis_resets_on_flapping():
    """Si el candidato cambia, el contador se reinicia (no acumula estados distintos)."""
    hist = {"state": None, "cand": None, "n": 0}
    C.classify(ev_put_wall(), hist=hist)
    C.classify(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1), hist=hist)   # cand=CONT
    r = C.classify(ev_put_wall(spot=None), hist=hist)                    # cand=SIN LECTURA
    assert r["state"] == C.S_REV
    assert hist["n"] == 0


def test_classify_sym_uses_module_history():
    C.reset_hist("SPY")
    a = C.classify_sym(ev_put_wall())
    assert a["state"] == C.S_REV
    b = C.classify_sym(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1))
    assert b["state"] == C.S_REV and b["state_pending"] == C.S_CONT
    C.reset_hist("SPY")


# ----------------------------------------------------------- degradacion limpia
def test_thin_book_is_sin_lectura_not_an_arrow():
    r = C.classify(ev_put_wall(book_label="THIN"))
    assert r["state"] == C.S_NONE
    assert r["dir"] == "flat" and r["prob"] == 50
    assert any("THIN" in w for w in r["state_why"])


def test_bar_gap_is_sin_lectura():
    """El hueco real de feed (07-24 13:15->13:31) no puede pasar por momentum de 6 min."""
    r = C.classify(ev_put_wall(bars_contig=False))
    assert r["state"] == C.S_NONE
    assert any("contigu" in w for w in r["state_why"])


def test_no_map_is_sin_lectura():
    assert C.classify(ev_put_wall(regime=None))["state"] == C.S_NONE
    assert C.classify(ev_put_wall(levels=[]))["state"] == C.S_NONE


def test_missing_vt_and_wall_stats_degrade_cleanly():
    """Sin VT y sin touch_idx la brujula sigue funcionando (no explota, no inventa)."""
    r = C.classify(ev_put_wall(vt=None,
                               levels=[{"price": 740.0, "kind": "Muro put",
                                        "wall_kind": "pin", "touch_idx": None}]))
    assert r["state"] == C.S_REV
    assert r["dir"] == "up"


def test_blank_evidence_never_crashes():
    r = C.classify(C.blank_evidence())
    assert r["state"] == C.S_NONE and r["dir"] == "flat"


# --------------------------------------------------- honestidad de la probabilidad
def test_prob_source_is_doctrina_without_calibration():
    r = C.classify(ev_put_wall())
    assert r["prob_source"] == "doctrina"
    assert r["prob"] <= C.DOCTRINE_CAP, "un prior doctrinal no puede presentarse como medida alta"


def test_prob_source_is_medido_with_enough_n():
    r = C.classify(ev_put_wall(calib={"p": 0.66, "n": 120, "lo": 0.58}))
    assert r["prob_source"] == "medido"
    assert r["prob"] == 58


def test_thin_calibration_cell_falls_back_to_doctrine():
    r = C.classify(ev_put_wall(calib={"p": 0.9, "n": 4, "lo": 0.7}))
    assert r["prob_source"] == "doctrina"


# --------------------------------------------------------------- Muro con mayuscula
def test_level_labels_use_capital_muro():
    r = C.classify(ev_put_wall())
    joined = " ".join(r["state_why"])
    assert "Muro put" in joined
    assert "muro put" not in joined


@pytest.mark.parametrize("state", [C.S_REV, C.S_CONT, C.S_APPR, C.S_BOX, C.S_NONE])
def test_contract_keys_always_present(state):
    """Contrato de salida: los consumidores (direction_view, chart, prob_profit) no pueden
    encontrarse una clave ausente segun el estado."""
    for ev in (ev_put_wall(), ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1),
               ev_put_wall(bars=bars_touching(740.0, 1, 740.6)),
               ev_put_wall(spot=None)):
        r = C.classify(ev)
        for k in ("sym", "state", "state_pending", "dir", "prob", "prob_source",
                  "pending_print", "families", "families_why", "vetoes", "fading",
                  "state_why", "level"):
            assert k in r
        assert r["dir"] in ("up", "down", "flat")
        assert 50 <= r["prob"] <= 90
