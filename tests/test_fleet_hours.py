#!/usr/bin/env python3
"""test_fleet_hours.py — arnes de test del PORTERO de la flota (scripts/fleet_hours.cpp).

Python aqui es SOLO arnes (ley de la casa 2026-07-25: "python solo para test, la computacion
en C++"). El calculo de la ventana vive entero en bin/fleet_hours; estos tests le inyectan
instantes con --at y verifican el veredicto. Cero computo de horario en Python — si el test
calculase la ventana por su cuenta, estariamos testeando el test.

La ley: la flota vive de DOMINGO 20:00 a VIERNES 20:00, hora de America/Toronto.
Orden de Yunior 2026-07-25: "fuera de ese horario todo muerto, salvo para testing,
backtesting, fixes, improvments".

Requiere el binario: ./scripts/build_fleet_hours.sh
"""
import json
import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin", "fleet_hours")
START_SH = os.path.join(REPO, "scripts", "fleet_keepalive_start.sh")

LIVE, DEAD = 0, 1

pytestmark = pytest.mark.skipif(
    not os.path.exists(BIN),
    reason="falta el binario bin/fleet_hours — corre ./scripts/build_fleet_hours.sh")


def run(at, *flags, env=None):
    """Corre el portero en un instante dado. Devuelve (returncode, stdout, stderr)."""
    e = dict(os.environ)
    # Limpiamos el escape para que el entorno del que corre pytest no falsee el veredicto.
    e.pop("FLEET_FORCE", None)
    if env:
        e.update(env)
    p = subprocess.run([BIN, "--at", at, *flags], capture_output=True, text=True,
                       cwd=REPO, timeout=20, env=e)
    return p.returncode, p.stdout, p.stderr


def verdict(at, *flags, env=None):
    rc, out, err = run(at, *flags, env=env)
    assert rc in (LIVE, DEAD), "codigo inesperado {}: {} {}".format(rc, out, err)
    # El estado tiene que ir tambien en la primera palabra de stdout, no solo en el exit code:
    # el shell lee el codigo, pero el humano lee el log.
    word = out.split()[0]
    assert word == ("LIVE" if rc == LIVE else "DEAD"), \
        "el exit code ({}) y stdout ({}) se contradicen".format(rc, word)
    return rc, out


# --- los 6 bordes de la ventana ----------------------------------------------------------
# 2026-07-25 es sabado; 07-26 domingo; 07-27 lunes; 07-31 viernes.

def test_1_sabado_medio_dia_muerto():
    """El caso que provoco todo esto: sabado 11:15 con la flota entera arriba."""
    rc, out = verdict("2026-07-25 11:15")
    assert rc == DEAD, out
    assert "sab" in out


def test_2_domingo_1959_todavia_muerto():
    """Un minuto antes de la apertura NO se arranca. El borde es cerrado por abajo."""
    rc, out = verdict("2026-07-26 19:59")
    assert rc == DEAD, out


def test_3_domingo_2000_arranca():
    """Domingo 20:00 EN PUNTO ya es ventana (>= , no >)."""
    rc, out = verdict("2026-07-26 20:00")
    assert rc == LIVE, out


def test_4_lunes_madrugada_vivo():
    """Lunes 03:00: Corea abierta, la flota tiene que estar despierta (lidera ~13h)."""
    rc, out = verdict("2026-07-27 03:00")
    assert rc == LIVE, out


def test_5_viernes_1959_ultimo_minuto_vivo():
    rc, out = verdict("2026-07-31 19:59")
    assert rc == LIVE, out


def test_6_viernes_2000_se_cierra():
    """Viernes 20:00 EN PUNTO ya esta muerto (borde abierto por arriba)."""
    rc, out = verdict("2026-07-31 20:00")
    assert rc == DEAD, out
    assert "faltan" in out  # cuenta atras al proximo domingo


# --- DST: la ventana es en hora LOCAL, y el offset NO esta hardcodeado --------------------

def test_7_miercoles_de_enero_es_EST():
    """Invierno: Toronto en EST (-5). Si alguien hardcodease -4 esto lo caza."""
    rc, out = verdict("2026-01-07 14:00")
    assert rc == LIVE, out
    assert "EST" in out, out
    _, j, _ = run("2026-01-07 14:00", "--json")
    assert json.loads(j)["utc_offset_sec"] == -5 * 3600


def test_7b_verano_es_EDT():
    """Verano: EDT (-4). El par EST/EDT prueba que la zona es real, no un offset fijo."""
    _, j, _ = run("2026-07-22 14:00", "--json")
    d = json.loads(j)
    assert d["tz_abbr"] == "EDT"
    assert d["utc_offset_sec"] == -4 * 3600


def test_7c_los_bordes_aguantan_el_cambio_de_horario():
    """Domingo del cambio a EDT (2026-03-08): el borde de las 20:00 sigue siendo 20:00
    LOCAL. 19:59 muerto / 20:00 vivo aunque ese dia solo tenga 23 horas."""
    assert verdict("2026-03-08 19:59")[0] == DEAD
    assert verdict("2026-03-08 20:00")[0] == LIVE
    _, j, _ = run("2026-03-08 20:00", "--json")
    assert json.loads(j)["tz_abbr"] == "EDT"


# --- el escape de testing: nunca silencioso ----------------------------------------------

def test_8_fleet_force_fuerza_live_y_lo_dice():
    """Yunior pidio escape "para testing, backtesting, fixes". Forzar es legitimo;
    forzar EN SILENCIO no lo es: la salida tiene que gritar FORZADO."""
    rc, out = verdict("2026-07-25 11:15", env={"FLEET_FORCE": "1"})
    assert rc == LIVE, out
    assert "FORZADO" in out, "un LIVE forzado que no se anuncia es un LIVE mentiroso: " + out


def test_8b_fleet_force_json_distingue_forzado_de_ventana():
    """El JSON tiene que dejar ver que la VENTANA decia DEAD aunque el estado sea LIVE."""
    _, j, _ = run("2026-07-25 11:15", "--json", env={"FLEET_FORCE": "1"})
    d = json.loads(j)
    assert d["state"] == "LIVE" and d["live"] is True
    assert d["window_live"] is False, "no se puede perder que la ventana real decia DEAD"
    assert d["forced"] is True and "FLEET_FORCE" in d["forced_reason"]


def test_8c_fleet_force_en_cero_no_fuerza():
    """FLEET_FORCE=0 no es forzar. Si no, un export olvidado deja la flota viva siempre."""
    rc, out = verdict("2026-07-25 11:15", env={"FLEET_FORCE": "0"})
    assert rc == DEAD, out
    assert "FORZADO" not in out


def test_8d_fichero_data_fleet_force(tmp_path):
    """El otro escape: data/FLEET_FORCE junto al binario. Se prueba con una COPIA del
    binario en un arbol de pega, para no ensuciar el data/ real del repo."""
    fake = tmp_path / "fleet_hours"
    shutil.copy2(BIN, fake)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "FLEET_FORCE").write_text("test\n")
    p = subprocess.run([str(fake), "--at", "2026-07-25 11:15"], capture_output=True,
                       text=True, cwd=str(tmp_path), timeout=20,
                       env={k: v for k, v in os.environ.items() if k != "FLEET_FORCE"})
    assert p.returncode == LIVE, p.stdout + p.stderr
    assert "FORZADO" in p.stdout and "FLEET_FORCE" in p.stdout


# --- contrato de salida ------------------------------------------------------------------

def test_9_json_parsea_y_trae_el_contrato():
    _, j, _ = run("2026-07-25 11:15", "--json")
    d = json.loads(j)  # si no parsea, revienta aqui
    for k in ("state", "live", "window_live", "forced", "zone", "now", "tz_abbr",
              "utc_offset_sec", "min_of_week", "seconds_to_boundary", "window", "detail"):
        assert k in d, "falta la clave {} en el JSON".format(k)
    assert d["zone"] == "America/Toronto"
    assert d["window"] == "dom20:00-vie20:00"
    assert d["state"] == "DEAD" and d["live"] is False
    # sabado 11:15 -> domingo 20:00 son 32h45m
    assert d["seconds_to_boundary"] == (32 * 3600 + 45 * 60)


def test_9b_why_explica_sin_cambiar_el_veredicto():
    rc_plain, _ = verdict("2026-07-25 11:15")
    rc_why, out = verdict("2026-07-25 11:15", "--why")
    assert rc_why == rc_plain
    assert "motivo:" in out and "Toronto" in out


# --- fail-loud: ante la duda, DEAD ------------------------------------------------------

@pytest.mark.parametrize("bad", ["no-es-fecha", "2026-13-01 10:00", "2026-07-25 99:99", ""])
def test_fail_loud_at_invalido_es_dead(bad):
    """Nunca un valor plausible: un --at ilegible NO puede caer en LIVE."""
    rc, out, err = run(bad)
    assert rc == DEAD, "un --at invalido devolvio LIVE: " + out
    assert "FALLO" in err, "el fallo tiene que GRITAR por stderr, no morir callado"


# --- rama fail-loud del shell: sin portero, la flota NO arranca -------------------------

def _fleet_esta_viva():
    p = subprocess.run(["pgrep", "-f", "ib-trader/scripts/.*_keepalive.sh"],
                       capture_output=True, text=True)
    return p.returncode == 0


@pytest.mark.skipif(_fleet_esta_viva(),
                    reason="la flota esta VIVA: este test llama a fleet_stop_all (pkill) y no "
                           "vamos a matar una flota en marcha desde un test")
def test_10_sin_binario_el_shell_no_arranca_la_flota(tmp_path):
    """Si bin/fleet_hours no existe, fleet_keepalive_start.sh tiene que FALLAR RUIDOSO y no
    arrancar nada. Degradar a "pues arranco" es el bug original con otra cara.

    No borramos el binario real: montamos un arbol de pega con el script y SIN portero.
    """
    (tmp_path / "scripts").mkdir()
    (tmp_path / "data").mkdir()
    shutil.copy2(START_SH, tmp_path / "scripts" / "fleet_keepalive_start.sh")
    # Pre-creado para que el test no dispare la notificacion de escritorio.
    (tmp_path / "data" / "FLEET_HOURS_MISSING").write_text("test\n")
    assert not (tmp_path / "fleet_hours").exists()

    p = subprocess.run(["zsh", str(tmp_path / "scripts" / "fleet_keepalive_start.sh")],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, "el guardian sale limpio, no revienta: " + p.stderr

    # logs viven en logs/ desde la reorg 2026-07-29 (el test apuntaba a la raiz, rancio)
    log = (tmp_path / "logs" / "fleet_autostart.log")
    assert log.exists(), "sin portero tiene que quedar rastro en logs/fleet_autostart.log"
    txt = log.read_text()
    assert "PORTERO AUSENTE" in txt, txt
    assert "lanzado" not in txt, "arranco algo sin portero: " + txt
    # Y nada de la flota quedo en marcha por culpa de esa ejecucion.
    assert not _fleet_esta_viva(), "el shell arranco keepalives sin portero"
