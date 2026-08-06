#!/usr/bin/env python3
"""test_compass.py — arnes de test de la BRUJULA (scripts/compass.cpp).

Python aqui es SOLO arnes de test (orden Yunior 2026-07-25: "python solo para test, la
computacion en C++"). El calculo vive entero en el binario bin/compass; estos tests le inyectan
evidencia por stdin con --ev-stdin y verifican el JSON que devuelve. Cero computo en Python.

El test #1 es el escenario literal de Yunior: SPY tocando el Muro put 740 con flujo masivo de
puts -> la flecha debe ir ARRIBA. La media ponderada anterior daba ABAJO 61% por construccion;
este archivo es la red que impide que vuelva a pasar.

Requiere el binario: ./scripts/build_compass.sh
"""
import json
import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.environ.get("COMPASS_TEST_BIN", os.path.join(REPO, "bin", "compass"))

S_REV = "REVERSION EN EXTREMO"
S_CONT = "CONTINUACION"
S_APPR = "APROXIMANDO"
S_BOX = "CAJA / PIN"
S_NONE = "SIN LECTURA"
DOCTRINE_CAP = 78

pytestmark = pytest.mark.skipif(
    not os.path.exists(BIN), reason="falta el binario bin/compass — corre ./scripts/build_compass.sh")


def run(ev):
    """Inyecta evidencia en el binario C++ y devuelve su veredicto."""
    p = subprocess.run([BIN, "--ev-stdin"], input=json.dumps(ev), capture_output=True,
                       text=True, cwd=REPO, timeout=20)
    assert p.returncode == 0, "compass fallo ({}): {}".format(p.returncode, p.stderr)
    return json.loads(p.stdout)


def test_unknown_cli_option_fails_loud():
    p = subprocess.run([BIN, "--definitely-unknown"], capture_output=True, text=True,
                       cwd=REPO, timeout=20)
    assert p.returncode == 2
    assert "opcion desconocida" in p.stderr


def test_calibration_consumer_prefers_effective_sample_size():
    src = open(os.path.join(REPO, "scripts", "compass.cpp")).read()
    assert src.count('jnum(sec, "n_eff")') >= 2


def bars_touching(level, n=3, spot=None):
    """n barras 1m cuyo rango CONTIENE el nivel (= n lecturas / prints)."""
    spot = spot if spot is not None else level
    return [[i * 60, level + 0.4, level + 0.6, level - 0.3, spot, 1e6] for i in range(n)]


def ev_put_wall(**over):
    """El escenario de Yunior: SPY cayendo al Muro put 740, puts inundando, %B en el suelo."""
    ev = {
        "sym": "SPY", "spot": 740.6, "em": 8.0, "regime": "POS", "flip": 748.0,
        "levels": [{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1}],
        "bars": bars_touching(740.0, 3, 740.6),
        "r6": -0.62, "r15": -0.90, "z6": -2.6,
        "pctb_1m": 0.04, "pctb_15m": 0.08,
        "flow": 1.0, "force_phase": "AGOTAMIENTO", "now_min": 600,
    }
    ev.update(over)
    return ev


def ev_call_wall(**over):
    """Simetrico: subiendo al Muro call 690 con calls inundando (techo)."""
    ev = {
        "sym": "QQQ", "spot": 689.5, "em": 7.0, "regime": "POS", "flip": 682.0,
        "levels": [{"price": 690.0, "kind": "Muro call", "wall_kind": "pin", "touch_idx": 1}],
        "bars": bars_touching(690.0, 3, 689.5),
        "r6": 0.55, "r15": 0.80, "z6": 2.4,
        "pctb_1m": 0.95, "pctb_15m": 0.90,
        "flow": -1.0, "force_phase": "AGOTAMIENTO", "now_min": 600,
    }
    ev.update(over)
    return ev


# --------------------------------------------------------------------------- 1 y 2
def test_yunior_spy_put_wall_arrow_points_up():
    """EL test: Muro put impreso + flujo de puts + %B extremo -> ARRIBA."""
    r = run(ev_put_wall())
    assert r["state"] == S_REV
    assert r["dir"] == "up", "la brujula debe GIRAR al alza en un piso impreso con puts inundando"
    assert r["prob"] > 50
    assert r["families"] >= 2
    assert any("COMBUSTIBLE" in f for f in r["fading"]), "el momentum bajista es combustible, no se esconde"


def test_call_wall_arrow_points_down():
    r = run(ev_call_wall())
    assert r["state"] == S_REV
    assert r["dir"] == "down"


# ------------------------------------------- la flecha VUELVE a girar en el rebote
def test_rebound_into_call_wall_turns_the_arrow_again():
    """Yunior 2026-07-25: "la flecha tambien se mueve si choca un call wall en rebote".
    Clave: a mitad del rebote r6 SIGUE negativo (la ventana de 6 barras aun incluye la
    caida), asi que el nivel se elige por TOQUE, no por procedencia."""
    ev = ev_put_wall(
        spot=745.8,
        levels=[{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1},
                {"price": 746.0, "kind": "Muro call", "wall_kind": "pin", "touch_idx": 1}],
        bars=bars_touching(746.0, 3, 745.8),
        r6=-0.20,                 # todavia negativo: la caida sigue dentro de la ventana
        pctb_1m=0.93, pctb_15m=0.88,
        flow=-0.9,                # ahora entran calls: techo
    )
    r = run(ev)
    assert r["level"]["kind"] == "Muro call", "debe evaluar el Muro que esta TOCANDO, no el de origen"
    assert r["state"] == S_REV
    assert r["dir"] == "down", "al chocar el techo en el rebote la flecha vuelve a girar"


def test_touching_level_beats_direction_of_travel():
    """Un nivel EN CONTACTO manda sobre el 'lado del que viene el precio'."""
    ev = ev_put_wall(
        spot=745.9,
        levels=[{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1},
                {"price": 746.0, "kind": "Muro call", "wall_kind": "pin", "touch_idx": 0}],
        bars=bars_touching(746.0, 2, 745.9), r6=-0.30)
    assert run(ev)["level"]["price"] == 746.0


def test_no_contact_uses_direction_of_travel():
    """Sin toque, se evalua el nivel al que el precio SE DIRIGE."""
    ev = ev_put_wall(
        spot=744.0,
        levels=[{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1},
                {"price": 752.0, "kind": "Muro call", "wall_kind": "pin", "touch_idx": 0}],
        bars=[[i * 60, 744.2, 744.4, 743.8, 744.0, 1e6] for i in range(3)], r6=-0.5)
    assert run(ev)["level"]["kind"] == "Muro put"


# ----------------------------------------------------------------------------- vetos
def test_veto_bandwalk_blocks_the_fade():
    """Regla 1: banda reventada en >=2 TF A FAVOR = band-walk = continuacion, no rebote."""
    r = run(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1))
    assert r["state"] == S_CONT
    assert r["dir"] == "down"
    assert any("band-walk" in w for w in r["state_why"])
    assert any("NO fadear" in w for w in r["state_why"])


def test_veto_trapdoor_blocks_the_fade():
    """Muro TRAMPILLA (gamma acumulada NEG en el nivel) no es piso: prohibido fadear."""
    r = run(ev_put_wall(levels=[{"price": 740.0, "kind": "Muro put",
                                 "wall_kind": "trampilla", "touch_idx": 1}]))
    assert r["state"] == S_CONT
    assert any("TRAMPILLA" in w for w in r["state_why"])


def test_veto_below_vol_trigger_blocks_the_fade():
    r = run(ev_put_wall(vt=745.0))
    assert r["state"] == S_CONT
    assert any("VT" in w for w in r["state_why"])


def test_veto_third_touch_blocks_the_fade():
    """Protocolo imanes: 3+ toques = muro exhausto -> lado de la ruptura, no fade."""
    r = run(ev_put_wall(levels=[{"price": 740.0, "kind": "Muro put",
                                 "wall_kind": "pin", "touch_idx": 3}]))
    assert r["state"] == S_CONT
    assert any("toque" in w for w in r["state_why"])


def test_veto_negative_regime_without_pin():
    """Memoria negative-gamma-whipsaw: en NEG el nivel no es piso, es acelerador."""
    r = run(ev_put_wall(regime="NEG",
                        levels=[{"price": 740.0, "kind": "Muro put", "touch_idx": 1}]))
    assert r["state"] == S_CONT
    assert any("NEG" in w for w in r["state_why"])


def test_veto_leader_catalyst():
    """Excepcion explicita de la regla 11: con catalizador del lider la ballena continua."""
    assert run(ev_put_wall(leader_catalyst=True))["state"] == S_CONT


def test_negative_regime_WITH_printed_pin_still_reverses():
    """El veto NEG no debe ser una manta: con un pin impreso la reversion sigue viva."""
    r = run(ev_put_wall(regime="NEG"))
    assert r["state"] == S_REV and r["dir"] == "up"


# ------------------------------------------------------------------- PRINT O NADA
def test_approaching_without_print_is_not_a_confident_arrow():
    """Sin 2 lecturas el estado es APROXIMANDO: se ve venir, no se afirma."""
    r = run(ev_put_wall(bars=bars_touching(740.0, 1, 740.6)))
    assert r["state"] == S_APPR
    assert r["pending_print"] is True
    assert r["dir"] == "flat", "un candidato sin print no puede verse como flecha verde operable"
    assert r["candidate_dir"] == "up"
    assert r["signal_kind"] == "countertrend_pullback_candidate"
    assert any("esperando print" in w for w in r["state_why"])


def test_second_reading_promotes_to_reversal():
    one = run(ev_put_wall(bars=bars_touching(740.0, 1, 740.6)))
    two = run(ev_put_wall(bars=bars_touching(740.0, 2, 740.6)))
    assert one["state"] == S_APPR and one["pending_print"] is True
    assert two["state"] == S_REV and two["pending_print"] is False


def test_approaching_prob_is_lower_than_printed():
    assert run(ev_put_wall(bars=bars_touching(740.0, 1, 740.6)))["prob"] is None
    assert run(ev_put_wall())["prob"] is not None


# ------------------------------------------------------------------- familias
def test_one_family_is_not_enough():
    r = run(ev_put_wall(pctb_1m=0.5, pctb_15m=0.5, force_phase="", candle_bias=0))
    assert r["families"] == 1
    assert r["state"] != S_REV


def test_families_are_counted_and_named():
    r = run(ev_put_wall())
    assert r["families"] == 3
    assert len(r["families_why"]) == 3
    assert any("puts=piso" in f for f in r["families_why"])


def test_pctb_extreme_needs_both_timeframes():
    """BOLLINGER-SIEMPRE es 1m Y 15m: un solo TF extremo no cuenta como familia."""
    assert not any("%B" in f for f in run(ev_put_wall(pctb_15m=0.5))["families_why"])


# ------------------------------------------- momentum como combustible + amplitud
def test_momentum_is_fuel_not_a_vote():
    """A igual escenario, MAS momentum en contra -> MAS prob, no menos. Lo contrario de
    lo que hacia la media ponderada."""
    soft = run(ev_put_wall(r6=-0.15, z6=-0.5))
    hard = run(ev_put_wall(r6=-1.20, z6=-3.4))
    assert soft["state"] == hard["state"] == S_REV
    assert hard["prob"] > soft["prob"], "el latigazo es mas elastico cuanto mas fuerte cayo"


def test_overnight_modulates_arrow_without_becoming_a_family():
    base = run(ev_put_wall(leg_pct=-0.3, bb_mid=741.5, levels=L2))
    agree = run(ev_put_wall(leg_pct=-0.3, bb_mid=741.5, levels=L2,
                            overnight_score=0.8, overnight_nq=0.8))
    disagree = run(ev_put_wall(leg_pct=-0.3, bb_mid=741.5, levels=L2,
                               overnight_score=-0.8, overnight_nq=-0.8))
    assert agree["families"] == disagree["families"] == base["families"]
    assert agree["overnight_context"]["coef"] == 1.25
    assert disagree["overnight_context"]["coef"] == 0.75
    assert agree["mag"] > base["mag"] > disagree["mag"]
    assert agree["prob"] > base["prob"] > disagree["prob"]


def test_overnight_does_not_relabel_measured_probability():
    r = run(ev_put_wall(calib_lo=0.61, calib_n=120, overnight_score=0.9))
    assert r["prob_source"] == "medido"
    assert r["prob"] == 61


L2 = [{"price": 740.0, "kind": "Muro put", "wall_kind": "pin", "touch_idx": 1},
      {"price": 752.0, "kind": "Muro call", "wall_kind": "pin", "touch_idx": 0}]


def test_amplitude_big_leg_with_room_is_a_whip():
    a = run(ev_put_wall(leg_pct=-1.6, bb_mid=748.0, levels=L2))["amplitude"]
    assert a["grade"] == "LATIGAZO"
    assert a["amp_pct"] > 0.5


def test_amplitude_capped_by_wall_above_is_a_scalp():
    """Doctrina imanes: jamas contar con atravesar un Muro intermedio."""
    ev = ev_put_wall(leg_pct=-1.6, bb_mid=748.0,
                     levels=[L2[0], {"price": 742.0, "kind": "Muro call",
                                     "wall_kind": "pin", "touch_idx": 0}])
    r = run(ev)
    assert r["level"]["kind"] == "Muro put", "el Muro call solo recorta el recorrido, no es el nivel a prueba"
    a = r["amplitude"]
    assert a["grade"] == "SCALP"
    assert a["binding"] == "room"
    assert a["amp_price"] <= 742.0


def test_amplitude_capped_by_remaining_expected_move():
    a = run(ev_put_wall(leg_pct=-1.6, bb_mid=748.0, em_used_pct=0.95, levels=L2))["amplitude"]
    assert a["binding"] == "em_left"


def test_amplitude_scales_the_arrow():
    """`mag` 0..1 es lo que escala la flecha en el chart: mas amplitud, flecha mas grande."""
    small = run(ev_put_wall(leg_pct=-0.3, bb_mid=740.9, levels=L2))
    big = run(ev_put_wall(leg_pct=-1.6, bb_mid=748.0, levels=L2))
    assert big["mag"] > small["mag"]
    assert 0.0 <= small["mag"] <= 1.0 and 0.0 <= big["mag"] <= 1.0


def test_amplitude_publishes_measured_retrace_separately():
    """El retroceso 50% MEDIDO se publica en amplitude, y NO como prob de la flecha:
    condiciona en 'hubo un impulso', no en 'hubo NUESTRO setup'."""
    r = run(ev_put_wall(leg_pct=-1.6, bb_mid=748.0, levels=L2))
    a = r["amplitude"]
    if a.get("retrace_prob") is not None:
        assert a["retrace_n"] >= 30
        assert r["prob_source"] == "doctrina", "una medida de otra poblacion no puede inflar la flecha"


def test_box_and_none_have_no_amplitude():
    for ev in (ev_put_wall(book_label="THIN"), ev_put_wall(regime="")):
        r = run(ev)
        assert r["amplitude"] is None and r["mag"] == 0.0 and r["target"] is None


def test_qqq_countertrend_pullback_is_candidate_not_green_up():
    """Replay semántico del bug 2026-07-29: r6 rebota dentro de tendencia 15m bajista.
    Puede ser pullback real; no equivale a edge alcista ni debe colorear la flecha."""
    r = run({
        "sym": "QQQ", "spot": 667.44, "em": 8.0, "regime": "NEG", "flip": 680.0,
        "levels": [{"price": 675.0, "kind": "Muro call", "wall_kind": "trampilla"}],
        "bars": [[i * 60, 667.4, 667.6, 667.2, 667.44, 1e6] for i in range(4)],
        "r6": 0.08, "r15": -0.72, "z6": 0.18,
        "calib_lo": 0.62, "calib_n": 120,
    })
    assert r["state"] == S_CONT
    assert r["candidate_dir"] == "up"
    assert r["dir"] == "flat"
    assert r["prob"] is None and r["prob_source"] == "sin_edge"
    assert r["signal_kind"] == "countertrend_pullback_candidate"


def test_replay_qqq_20260729_1136_up50_has_no_predictive_edge():
    """Caso exacto: QQQ 11:36 UP@50; +5m=-0.129%, +15m=-0.112%, +30m=-0.508%.
    r6/r15 estaban apenas verdes, pero la celda NEG tenía Wilson-lo 46.48%."""
    r = run({
        "sym": "QQQ", "spot": 667.56, "em": 8.0, "regime": "NEG",
        "levels": [{"price": 675.0, "kind": "Muro call", "wall_kind": "trampilla"}],
        "bars": [[i * 60, 667.5, 667.7, 667.3, 667.56, 1e6] for i in range(4)],
        "r6": 0.09296, "r15": 0.02997, "z6": 0.18,
        "calib_lo": 0.4648, "calib_wr30": 0.4955, "calib_n": 1009,
    })
    assert r["candidate_dir"] == "up"
    assert r["dir"] == "flat" and r["prob"] is None
    assert r["prob_source"] == "sin_edge"


def test_measured_wilson_at_or_below_chance_is_not_clamped_to_green_50():
    """Caso real CONT|f0|NEG: lo=46.48%; antes clamp(50,90) => UP/DOWN 50 'medido'."""
    r = run({
        "sym": "GENERIC", "spot": 100.0, "em": 2.0, "regime": "NEG",
        "levels": [{"price": 95.0, "kind": "Muro put", "wall_kind": "trampilla"}],
        "bars": [[i * 60, 100.0, 100.1, 99.9, 100.0, 1e6] for i in range(4)],
        "r6": -0.45, "r15": -0.90, "z6": -1.2,
        "calib_lo": 0.4648, "calib_n": 1009,
    })
    assert r["candidate_dir"] == "down"
    assert r["dir"] == "flat"
    assert r["prob"] is None and r["prob_source"] == "sin_edge"
    assert r["signal_kind"] == "no_predictive_edge"


def test_rule_is_general_not_a_semiconductor_whitelist():
    r = run({
        "sym": "UNLISTED", "spot": 50.0, "em": 1.0, "regime": "NEG",
        "levels": [{"price": 55.0, "kind": "Muro call", "wall_kind": "trampilla"}],
        "bars": [[i * 60, 50.0, 50.1, 49.9, 50.0, 1e6] for i in range(4)],
        "r6": 0.20, "r15": -0.80, "z6": 0.4,
    })
    assert r["candidate_dir"] == "up" and r["dir"] == "flat"
    assert r["signal_kind"] == "countertrend_pullback_candidate"


def test_opposite_bandwalk_overrides_r6_blip():
    """Doctrina 2026-08-06: band-walk 3 TF abajo con blip r6 +0.12% (z 0.3 = ruido) es
    TENDENCIA FUERTE abajo, no pullback candidato. Regla 1: band-walk = continuacion."""
    r = run({
        "sym": "QQQ", "spot": 667.0, "em": 8.0, "regime": "NEG", "flip": 680.0,
        "levels": [{"price": 675.0, "kind": "Muro call", "wall_kind": "trampilla"}],
        "bars": [[i * 60, 667.0, 667.2, 666.8, 667.0, 1e6] for i in range(4)],
        "r6": 0.12, "r15": -0.70, "z6": 0.3,
        "bandwalk_tf": 3, "bandwalk_dir": -1,
    })
    assert r["dir"] == "down"
    assert r["signal_kind"] == "continuation_multitf"


# ------------------------------------------------------------------- histeresis
def test_hysteresis_needs_two_consecutive_computes():
    """Regla 3: una barra aislada NO cambia el estado; dos barras distintas sí."""
    a = run(dict(ev_put_wall(), use_hist=True))
    assert a["state"] == S_REV
    h = a["hist"]
    flip1 = run(dict(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1), use_hist=True,
                     hist_state=h["state"], hist_dir=h["dir"],
                     hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                     hist_cand_bar=h["cand_bar"]))
    assert flip1["state"] == S_REV, "el primer computo discrepante no cambia el estado"
    assert flip1["state_pending"] == S_CONT
    h = flip1["hist"]
    flip2 = run(dict(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1,
                                 bars=bars_touching(740.0, 4, 740.6)), use_hist=True,
                     hist_state=h["state"], hist_dir=h["dir"],
                     hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                     hist_cand_bar=h["cand_bar"]))
    assert flip2["state"] == S_CONT, "el segundo consecutivo si cambia"


def test_hysteresis_resets_on_flapping():
    """Si el candidato cambia, el contador se reinicia (no acumula estados distintos)."""
    a = run(dict(ev_put_wall(), use_hist=True))
    h = a["hist"]
    b = run(dict(ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1), use_hist=True,
                 hist_state=h["state"], hist_dir=h["dir"],
                 hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                 hist_cand_bar=h["cand_bar"]))
    h = b["hist"]
    c = run(dict(ev_put_wall(regime=""), use_hist=True,
                 hist_state=h["state"], hist_dir=h["dir"],
                 hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                 hist_cand_bar=h["cand_bar"]))
    assert c["state"] == S_REV
    assert c["hist"]["n"] == 1, "el candidato nuevo empieza en 1; no hereda el anterior"


def test_hysteresis_covers_direction_inside_same_state():
    """Bug real: la histéresis sólo miraba el estado CONTINUACION; UP/DOWN podía alternar
    cada minuto sin pasar por HYST_N."""
    def trend(r, n=4):
        return {
            "sym": "QQQ", "spot": 667.0, "em": 8.0, "regime": "NEG",
            "levels": [{"price": 680.0, "kind": "Muro call", "wall_kind": "trampilla"}],
            "bars": [[i * 60, 667, 667.2, 666.8, 667, 1e6] for i in range(n)],
            "r6": r, "r15": r * 2, "z6": 1.2 if r > 0 else -1.2,
            "calib_lo": 0.53, "calib_wr30": 0.58, "calib_n": 100, "use_hist": True,
        }
    down = run(trend(-0.3))
    assert down["state"] == S_CONT and down["dir"] == "down"
    h = down["hist"]
    up1 = run(dict(trend(0.3), hist_state=h["state"], hist_dir=h["dir"],
                   hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                   hist_cand_bar=h["cand_bar"]))
    assert up1["state"] == S_CONT and up1["dir"] == "flat"
    assert up1["candidate_dir"] == "up"
    h = up1["hist"]
    same_bar = run(dict(trend(0.3), hist_state=h["state"], hist_dir=h["dir"],
                        hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                        hist_cand_bar=h["cand_bar"]))
    assert same_bar["dir"] == "flat"
    assert same_bar["hist"]["n"] == h["n"], "el loop 250ms no confirma dos veces el mismo bar"
    h = same_bar["hist"]
    up2 = run(dict(trend(0.3, n=5), hist_state=h["state"], hist_dir=h["dir"],
                   hist_cand=h["cand"], hist_cand_dir=h["cand_dir"], hist_n=h["n"],
                   hist_cand_bar=h["cand_bar"]))
    assert up2["state"] == S_CONT and up2["dir"] == "up"
    assert up2["prob"] == 58, "se muestra WR puntual; Wilson-lo sólo es gate"


# ----------------------------------------------------------- degradacion limpia
def test_thin_book_is_sin_lectura_not_an_arrow():
    r = run(ev_put_wall(book_label="THIN"))
    assert r["state"] == S_NONE and r["dir"] == "flat" and r["prob"] is None
    assert any("THIN" in w for w in r["state_why"])


def test_bar_gap_is_sin_lectura():
    """El hueco real de feed (07-24 13:15->13:31) no puede pasar por momentum de 6 min."""
    r = run(ev_put_wall(bars_contig=False))
    assert r["state"] == S_NONE
    assert any("contigu" in w for w in r["state_why"])


def test_no_map_is_sin_lectura():
    assert run(ev_put_wall(regime=""))["state"] == S_NONE
    assert run(ev_put_wall(levels=[]))["state"] == S_NONE


def test_missing_vt_and_wall_stats_degrade_cleanly():
    """Sin VT y sin touch_idx la brujula sigue funcionando (no explota, no inventa)."""
    r = run(ev_put_wall(levels=[{"price": 740.0, "kind": "Muro put", "wall_kind": "pin"}]))
    assert r["state"] == S_REV and r["dir"] == "up"


def test_empty_evidence_never_crashes():
    r = run({"sym": "ZZZZ"})
    assert r["state"] == S_NONE and r["dir"] == "flat"


# --------------------------------------------------- honestidad de la probabilidad
def test_prob_source_is_doctrina_without_own_calibration():
    r = run(ev_put_wall())
    assert r["prob_source"] == "doctrina"
    assert r["prob"] <= DOCTRINE_CAP, "un prior doctrinal no puede presentarse como medida alta"


def test_prob_source_is_medido_with_enough_n():
    r = run(ev_put_wall(calib_lo=0.58, calib_n=120))
    assert r["prob_source"] == "medido" and r["prob"] == 58


def test_thin_calibration_cell_falls_back_to_doctrine():
    assert run(ev_put_wall(calib_lo=0.70, calib_n=4))["prob_source"] == "doctrina"


# --------------------------------------------------------------- Muro con mayuscula
def test_level_labels_use_capital_muro():
    joined = " ".join(run(ev_put_wall())["state_why"])
    assert "Muro put" in joined and "muro put" not in joined


def test_contract_keys_always_present():
    """Contrato de salida: los consumidores (direction_view, chart, prob_profit) no pueden
    encontrarse una clave ausente segun el estado."""
    for ev in (ev_put_wall(), ev_put_wall(bandwalk_tf=3, bandwalk_dir=-1),
               ev_put_wall(bars=bars_touching(740.0, 1, 740.6)), ev_put_wall(regime=""),
               {"sym": "X"}):
        r = run(ev)
        for k in ("sym", "state", "state_pending", "dir", "candidate_dir", "signal_kind",
                  "prob", "prob_source",
                  "pending_print", "families", "families_why", "vetoes", "fading",
                  "state_why", "level", "amplitude", "mag", "target", "grade", "ts"):
            assert k in r, "falta la clave {} en estado {}".format(k, r.get("state"))
        assert "overnight_context" in r
        assert r["dir"] in ("up", "down", "flat")
        assert r["prob"] is None or 51 <= r["prob"] <= 90


# --------------------------------------------------------- calibracion: contexto, no prob
def test_calib_context_no_se_convierte_en_probabilidad():
    """null_control mide la senal CRUDA (n=1154 = pool de bollinger), no ESTE setup
    (nivel impreso + >=2 familias + sin vetos). Su veredicto se publica como contexto y
    la prob sigue siendo doctrinal: usarlo de probabilidad es la misma falacia que el
    codigo ya rechaza con prob_retroceso_50."""
    r = run(ev_put_wall(calib_source="bollinger"))
    assert r["prob_source"] == "doctrina", "una fuente sin calibrar NO puede decir 'medido'"
    assert r["prob"] is not None and 50 <= r["prob"] <= 90
    if r.get("calib_context"):
        assert "fdr_ok=0" in r["calib_context"], "bollinger no pasa BH-FDR: hay que decirlo"


def test_calib_context_ausente_si_la_fuente_no_esta_medida():
    r = run(ev_put_wall(calib_source="fuente_que_no_existe"))
    assert r.get("calib_context") is None, "lo que no se ha medido no se anuncia"


def test_prob_medida_solo_con_calibracion_del_propio_setup():
    """La unica via a 'medido' es la celda del propio setup, inyectada por --ev-stdin."""
    r = run(ev_put_wall(calib_lo=0.71, calib_n=140))
    assert r["prob_source"] == "medido"
    assert r["prob"] == 71, "sin WR inyectado, el arnés conserva lo como estimación compatible"


def _ev_box_far(**kw):
    """POS, muro call a +3% (ni near ni approaching): la vieja caja."""
    ev = {
        "sym": "GENERIC", "spot": 100.0, "em": 2.0, "regime": "POS",
        "levels": [{"price": 103.0, "kind": "Muro call"}],
        "bars": [[i * 60, 100.0, 100.1, 99.9, 100.0, 1e6] for i in range(4)],
    }
    ev.update(kw)
    return ev


def test_strong_downtrend_beats_the_box():
    """Bug 2026-08-05: INTC -1.7% en 53min con band-walk y la caja decia flat."""
    r = run(_ev_box_far(r6=-0.60, r15=-1.10, z6=-2.4, bandwalk_tf=3, bandwalk_dir=-1))
    assert r["state"] == S_CONT
    assert r["dir"] == "down"
    assert r["signal_kind"] == "continuation_multitf"
    assert any("tendencia fuerte" in w for w in r["state_why"])


def test_zimpulse_with_captain_flow_paints_trend_flow():
    """Impulso 2-sigma persistente + flujo capitan del mismo signo = flecha roja."""
    r = run(_ev_box_far(r6=-0.60, r15=-1.10, z6=-2.4, flow=-0.8))
    assert r["state"] == S_CONT
    assert r["dir"] == "down"
    assert r["signal_kind"] == "trend_flow"


def test_zimpulse_with_net_prem_paints_trend_flow():
    """Prima neta firmada del dia (UW) del mismo signo tambien confirma."""
    r = run(_ev_box_far(r6=-0.60, r15=-1.10, z6=-2.4, net_prem=-450000.0))
    assert r["dir"] == "down"
    assert r["signal_kind"] == "trend_flow"


def test_zimpulse_without_whales_stays_flat():
    """Sin ballena que confirme, el impulso solo NO colorea (honestidad OOS intacta)."""
    r = run(_ev_box_far(r6=-0.60, r15=-1.10, z6=-2.4))
    assert r["state"] == S_CONT
    assert r["dir"] == "flat"
    assert r["candidate_dir"] == "down"
    assert r["signal_kind"] == "no_predictive_edge"


def test_net_prem_calderilla_does_not_confirm():
    """|signed| < 100k = calderilla: no confirma nada."""
    r = run(_ev_box_far(r6=-0.60, r15=-1.10, z6=-2.4, net_prem=-40000.0))
    assert r["dir"] == "flat"


def test_weak_drift_still_a_box():
    """Deriva floja sin band-walk ni z-impulso: la caja sigue siendo caja."""
    r = run(_ev_box_far(r6=-0.10, r15=-0.15, z6=-0.4))
    assert r["state"] == S_BOX
    assert r["dir"] == "flat"


def test_box_below_forward_flip_says_so():
    """Leccion INTC 2026-08-05: caja con spot BAJO el flip del libro que sobrevive la
    semana = colchon con fecha de caducidad. Se DICE (contexto), el estado no cambia."""
    r = run(_ev_box_far(flip_fwd=106.19, gamma_die_week=58.8))
    assert r["state"] == S_BOX
    assert any("flip FORWARD 106.19" in w and "59%" in w or "58" in w for w in r["state_why"])


def test_box_above_forward_flip_stays_quiet():
    r = run(_ev_box_far(flip_fwd=97.0))
    assert r["state"] == S_BOX
    assert not any("FORWARD" in w for w in r["state_why"])
