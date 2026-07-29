#!/usr/bin/env python3
"""test_level_react.py — arnes de test del primitivo de NIVELES (scripts/level_react.cpp).

Python aqui es SOLO arnes (orden Yunior 2026-07-25: "python solo para test, la computacion en
C++"). Todo el calculo vive en bin/level_react; estos tests le inyectan barras y niveles por stdin
con --ev-stdin y verifican el JSON que devuelve. Cero computo en Python.

LO QUE ESTE FICHERO PROTEGE
  1. PRINT O NADA es MECANICO: sin dos barras CERRADAS cruzando el nivel no hay `printed`, y sin
     `printed` no hay nada operable. Es la red que impide que vuelva el "esta cerca" que hoy
     esta copiado a mano en ~30 signal bots (qqq_signal_bot.cpp:1085).
  2. Solo BOUNCE y RETEST_REJECT son operables. TOUCH es consolidacion y una primera BREAK sin
     retest es la trampa clasica (post-mortem 2026-07-20).
  3. El registro esta TOPADO a 6 tipos. GAP_EDGE/KDE solo entran DESPLAZANDO.
  4. `touch_ord` solo sube tras una EXCURSION real: el chop pegado al nivel no puede fabricar un
     "3er toque, muro exhausto".
  5. Nada devuelve un numero plausible cuando no sabe: sin muestra para el ATR, el binario FALLA
     en vez de inventarse un buffer.

Requiere el binario: ./scripts/build_level_react.sh
"""
import json
import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin", "level_react")

pytestmark = pytest.mark.skipif(
    not os.path.exists(BIN),
    reason="falta el binario bin/level_react — corre ./scripts/build_level_react.sh")


def run(payload, expect_rc=0):
    """Inyecta barras+niveles en el binario C++ y devuelve su veredicto."""
    p = subprocess.run([BIN, "--ev-stdin"], input=json.dumps(payload), capture_output=True,
                       text=True, cwd=REPO, timeout=20)
    assert p.returncode == expect_rc, "rc={} stderr={}".format(p.returncode, p.stderr)
    return json.loads(p.stdout) if expect_rc == 0 else None


def base(bars, levels=None, atr=1.0, half_spread=0.0, tick=0.01):
    return {"sym": "TEST", "atr": atr, "half_spread": half_spread, "tick": tick,
            "levels": levels if levels is not None else [{"type": "ABS_WALL", "px": 100.0}],
            "bars": bars}


def bar(t, o, h, l, c, v=1e6):
    return [t, o, h, l, c, v]


def events(out, kind=None, level_type=None):
    evs = out["events"]
    if kind:
        evs = [e for e in evs if e["event"] == kind]
    if level_type:
        evs = [e for e in evs if e["level_type"] == level_type]
    return evs


# ---------------------------------------------------------------------------------------
# 1. PRINT O NADA — el corazon de la feature
# ---------------------------------------------------------------------------------------

def test_una_sola_barra_cruzando_no_es_print():
    """Una vela que atraviesa el nivel y se va NO es un print. Es exactamente el caso que el
    'esta cerca' de los bots trata como señal."""
    bars = [
        bar(0,   95, 96,  94,  95),     # lejos, por debajo
        bar(60,  95, 101, 94,  95),     # UNA barra straddleando el 100
        bar(120, 95, 96,  94,  95),     # se fue
    ]
    out = run(base(bars))
    assert all(not e["printed"] for e in out["events"]), \
        "una sola barra cruzando no puede marcar printed"


def test_dos_barras_cerradas_cruzando_si_es_print():
    """Dos barras CERRADAS cuyo rango contiene el nivel = las dos lecturas de la doctrina."""
    bars = [
        bar(0,   95,  96,  94,  95),
        bar(60,  99,  101, 98,  99),    # straddle 1
        bar(120, 99,  101, 98,  99),    # straddle 2 -> printed
    ]
    out = run(base(bars))
    assert any(e["printed"] for e in out["events"]), "dos barras cruzando deben dar printed"


def test_sin_print_nada_es_operable():
    """Invariante duro: `tradeable` implica `printed`. Si esto se rompe, el 'esta cerca' volvio."""
    bars = [bar(i * 60, 95 + (i % 3), 101, 94, 95 + (i % 3)) for i in range(12)]
    out = run(base(bars))
    for e in out["events"]:
        if e["tradeable"]:
            assert e["printed"], "un evento operable sin print es el bug que esta feature borra"


# ---------------------------------------------------------------------------------------
# 2. Taxonomia de eventos
# ---------------------------------------------------------------------------------------

def test_break_abre_y_cierra_en_lados_opuestos():
    bars = [
        bar(0,   95,  96,  94,  95),    # abajo
        bar(60,  95,  106, 94,  105),   # abre abajo, cierra arriba -> BREAK
    ]
    out = run(base(bars))
    assert events(out, "BREAK"), "abrir a un lado y cerrar al otro es un BREAK"


def test_touch_no_es_operable_nunca():
    """TOUCH = consolidacion. La ficha y la skill print-o-nada-levels lo prohiben como entrada."""
    bars = [
        bar(0,   95,  96,   94,   95),
        bar(60,  97,  99.9, 96,   97),   # llega a la banda, cierra del lado de origen
        bar(120, 97,  99.9, 96,   97),
    ]
    out = run(base(bars))
    for e in events(out, "TOUCH"):
        assert not e["tradeable"], "un TOUCH jamas puede salir operable"


def test_bounce_es_touch_sin_ruptura_despues():
    """BOUNCE = TOUCH en t y NO BREAK en t+1. Es uno de los dos unicos eventos operables."""
    bars = [
        bar(0,   90,  91,    89,  90),
        bar(60,  97,  100.4, 96,  97),   # TOUCH desde abajo (llega a la banda, cierra debajo)
        bar(120, 97,  98,    95,  96),   # no rompe -> BOUNCE
    ]
    out = run(base(bars))
    assert events(out, "BOUNCE"), "un toque respetado sin ruptura posterior es un BOUNCE"


def test_solo_bounce_y_retest_reject_son_operables():
    """La lista blanca completa. Cualquier otro evento operable seria una regresion."""
    bars = []
    px = 90.0
    for i in range(40):                    # paseo que cruza el nivel varias veces
        px += 1.4 if (i // 5) % 2 == 0 else -1.4
        bars.append(bar(i * 60, px, px + 1.0, px - 1.0, px + 0.2))
    out = run(base(bars))
    for e in out["events"]:
        if e["tradeable"]:
            assert e["event"] in ("BOUNCE", "RETEST_REJECT"), \
                "evento operable no permitido: {}".format(e["event"])


def test_wick_reject_mecha_atraviesa_cuerpo_rechazado():
    bars = [
        bar(0,   95, 96,  94, 95),
        bar(60,  98, 103, 97, 98),   # mecha por encima de 100, cierra debajo, cuerpo pequeño
    ]
    out = run(base(bars))
    assert events(out, "WICK_REJECT"), "mecha a traves con cuerpo rechazado es WICK_REJECT"


# ---------------------------------------------------------------------------------------
# 3. touch_ord: solo cuenta tras una EXCURSION
# ---------------------------------------------------------------------------------------

def test_chop_pegado_al_nivel_no_fabrica_tercer_toque():
    """Sin histeresis, el precio pegado al nivel daria touch_ord 1,2,3,4... en cuatro minutos y
    dispararia el '3er toque = muro exhausto'. La excursion de 0.5*ATR es lo que lo impide."""
    bars = [bar(0, 90, 91, 89, 90)]
    for i in range(1, 10):
        bars.append(bar(i * 60, 99.6, 99.9, 99.2, 99.6))   # chop dentro de medio ATR
    out = run(base(bars, atr=4.0))
    ords = [e["touch_ord"] for e in events(out, "TOUCH")]
    assert not ords or max(ords) <= 1, \
        "chop sin excursion no puede pasar de touch_ord 1, salio {}".format(ords)


def test_excursion_habilita_el_siguiente_toque():
    bars = [
        bar(0,   90, 91,   89,   90),
        bar(60,  97, 99.5, 96,   97),    # toque 1
        bar(120, 90, 91,   89,   90),    # excursion >= 0.5*ATR
        bar(180, 97, 99.5, 96,   97),    # toque 2
    ]
    out = run(base(bars, atr=4.0))
    ords = [e["touch_ord"] for e in events(out, "TOUCH")]
    assert ords and max(ords) >= 2, "tras alejarse, el siguiente toque debe contar: {}".format(ords)


# ---------------------------------------------------------------------------------------
# 4. Registro topado a 6
# ---------------------------------------------------------------------------------------

def test_registro_topado_a_seis():
    levels = [
        {"type": "OI_CALL_WALL", "px": 110}, {"type": "OI_PUT_WALL", "px": 90},
        {"type": "ABS_WALL", "px": 100},     {"type": "FLIP_OPEN", "px": 105},
        {"type": "POC_DOM", "px": 99},       {"type": "ROUND", "px": 100},
        {"type": "GAP_EDGE", "px": 103},     {"type": "KDE", "px": 97},
    ]
    out = run(base([bar(0, 95, 96, 94, 95)], levels=levels))
    assert out["registry_max"] == 6
    assert len(out["registry"]) <= 6, "el tope de 6 tipos es DURO: {}".format(out["registry"])


def test_kde_no_desplaza_a_un_muro_de_oi():
    """Un nivel KDE es una segunda opinion estadistica: cede siempre ante un muro medido."""
    levels = [
        {"type": "OI_CALL_WALL", "px": 110}, {"type": "OI_PUT_WALL", "px": 90},
        {"type": "ABS_WALL", "px": 100},     {"type": "FLIP_OPEN", "px": 105},
        {"type": "POC_DOM", "px": 99},       {"type": "ROUND", "px": 100},
        {"type": "KDE", "px": 97},
    ]
    out = run(base([bar(0, 95, 96, 94, 95)], levels=levels))
    kinds = {r["type"] for r in out["registry"]}
    assert "OI_CALL_WALL" in kinds and "OI_PUT_WALL" in kinds
    assert "KDE" not in kinds, "KDE no puede desplazar a un muro de OI"


# ---------------------------------------------------------------------------------------
# 5. La voz embarca APAGADA
# ---------------------------------------------------------------------------------------

def test_la_voz_embarca_apagada():
    """Condicion NO NEGOCIABLE de la ficha #8. Las celdas ganan voz de una en una via
    null_control, nunca por defecto."""
    out = run(base([bar(0, 95, 96, 94, 95)]))
    assert out["voice"] == "OFF"


def test_el_binario_no_puede_hablar():
    """Ni el header ni el CLI incluyen fleet_notify.h: estructuralmente no hay voz que encender."""
    for f in ("scripts/level_react.h", "scripts/level_react.cpp"):
        src = open(os.path.join(REPO, f), encoding="utf-8").read()
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("#include"):
                assert "fleet_notify" not in s, \
                    "{} no puede incluir el notificador: {}".format(f, s)


# ---------------------------------------------------------------------------------------
# 6. Fail-loud: prohibido el numero plausible
# ---------------------------------------------------------------------------------------

def test_sin_muestra_para_el_atr_falla_en_vez_de_inventarlo():
    """Un ATR inventado -> buffer concreto -> 'no se' convertido en 'se, y es cero'. Prohibido
    por la ley de la casa (CLAUDE.md, los 3 peligros medidos el 2026-07-25)."""
    payload = {"sym": "TEST", "levels": [{"type": "ABS_WALL", "px": 100}],
               "bars": [bar(0, 95, 96, 94, 95), bar(60, 95, 96, 94, 95)]}   # 2 barras: nada
    run(payload, expect_rc=3)


def test_buffer_es_el_maximo_de_los_tres_terminos():
    """s = max(0.15*ATR, medio-spread, 1 tick). Con un spread ancho manda el spread: un 'toque'
    dentro del spread es una cotizacion, no la decision de nadie."""
    bars = [bar(i * 60, 95, 96, 94, 95) for i in range(3)]
    out = run(base(bars, atr=1.0, half_spread=0.9, tick=0.01))
    assert abs(out["buffer"] - 0.9) < 1e-9, out["buffer"]
    out2 = run(base(bars, atr=10.0, half_spread=0.05, tick=0.01))
    assert abs(out2["buffer"] - 1.5) < 1e-9, out2["buffer"]


def test_json_invalido_no_produce_veredicto():
    p = subprocess.run([BIN, "--ev-stdin"], input="{esto no es json",
                       capture_output=True, text=True, cwd=REPO, timeout=20)
    assert p.returncode != 0, "un JSON roto no puede devolver un veredicto"
