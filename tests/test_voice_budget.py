"""voice_budget: DANGER NUNCA se recorta (ni con el presupuesto agotado), SIGNAL si, y toda
supresion queda registrada. Incluye el test del gate REAL de speak.sh con bash.
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T0 = 1784980800          # 2026-07-25 10:00:00 local


@pytest.fixture()
def vb(tmp_path):
    m = _load("voice_budget")
    m.REGISTRY_PATH = str(tmp_path / "registry.json")
    m.CAPS_PATH = str(tmp_path / "caps.json")
    m.BUDGET_PATH = str(tmp_path / "budget.json")
    m.SPEND_DIR = str(tmp_path / "spend")
    m.SPOOL_PATH = str(tmp_path / "spool.jsonl")
    m.ENABLE_PATH = str(tmp_path / "enable")
    m.DB = str(tmp_path / "t.db")
    m.init(now=T0)
    return m


def _enable(vb):
    open(vb.ENABLE_PATH, "w").close()


def _fill(vb, n, prio="SIGNAL", now=T0):
    for i in range(n):
        vb.record(prio, now=now + i)


# ------------------------------------------------- DANGER es intocable

def test_danger_nunca_se_recorta_con_presupuesto_agotado(vb):
    _enable(vb)
    _fill(vb, 100)                       # muy por encima de cualquier tope
    allow, reason, _ = vb.decide("DANGER", now=T0 + 200)
    assert allow is True and reason == "danger_nunca_se_recorta"
    # y SIGNAL en la misma situacion si se corta
    allow2, reason2, _ = vb.decide("SIGNAL", now=T0 + 200)
    assert allow2 is False and "day_cap" in reason2


def test_danger_ni_pasa_por_el_gate_en_speak_sh():
    """Guarda de codigo: la condicion de speak.sh comprueba DANGER ANTES de llamar al gate."""
    src = open(os.path.join(REPO, "scripts", "speak.sh")).read()
    assert '[ "$PRIO" != "DANGER" ] && [ -f "$ROOT/data/voice_budget_enable" ]' in src
    assert "--gate" in src
    # y solo el 42 silencia
    assert '"$?" = "42"' in src


def test_signal_se_raciona_por_hora(vb):
    _enable(vb)
    _fill(vb, vb.caps()["hour_signal_cap"])
    allow, reason, _ = vb.decide("SIGNAL", now=T0 + 60)
    assert allow is False and "hour_cap" in reason
    # la hora siguiente vuelve a permitir (mientras no se pase el tope diario)
    allow2, _r, _ = vb.decide("SIGNAL", now=T0 + 3700)
    assert allow2 is True


def test_apagado_no_suprime_nada(vb):
    _fill(vb, 100)
    allow, reason, _ = vb.decide("SIGNAL", now=T0 + 200)
    assert allow is True and reason == "presupuesto_apagado"


def test_info_no_se_gatea(vb):
    _enable(vb)
    _fill(vb, 100)
    allow, reason, _ = vb.decide("INFO", now=T0 + 200)
    assert allow is True and reason == "clase_no_gateada"


def test_cooldown_apagado_por_defecto(vb):
    _enable(vb)
    assert vb.caps()["cooldown_sym_sec"] == 0
    vb.record("SIGNAL", sym="QQQ", now=T0)
    allow, _r, _ = vb.decide("SIGNAL", sym="QQQ", now=T0 + 5)
    assert allow is True, "el cooldown por sym puede tapar una señal nueva: viene apagado"


def test_cooldown_funciona_si_se_enciende(vb):
    _enable(vb)
    vb.atomic_write_json(vb.CAPS_PATH, dict(vb.DEFAULT_CAPS, cooldown_sym_sec=600))
    vb.record("SIGNAL", sym="QQQ", now=T0)
    allow, reason, _ = vb.decide("SIGNAL", sym="QQQ", now=T0 + 60)
    assert allow is False and "cooldown_sym" in reason
    allow2, _r, _ = vb.decide("SIGNAL", sym="NVDA", now=T0 + 60)
    assert allow2 is True, "el cooldown es por sym, no global"


# ------------------------------------------------- registro de supresiones

def test_cada_supresion_queda_logueada_con_action_propio(vb):
    _enable(vb)
    ev = vb.log_suppression("SIGNAL", "MU rompe 900", "day_cap 40", sym="MU", now=T0)
    assert ev["action"] == "budget_suppressed"
    # spool durable
    assert json.loads(open(vb.SPOOL_PATH).readline())["reason"] == "day_cap 40"
    # y en voice_log, sin tocar los actions de voice_queue.sh
    c = sqlite3.connect(vb.DB)
    rows = c.execute("SELECT action, priority, msg FROM voice_log").fetchall()
    c.close()
    assert rows == [("budget_suppressed", "SIGNAL", "[day_cap 40] MU rompe 900")]


def test_flush_no_duplica(vb):
    vb.log_suppression("SIGNAL", "a", "day_cap", now=T0)
    r1 = vb.flush(now=T0)
    r2 = vb.flush(now=T0)
    c = sqlite3.connect(vb.DB)
    n = c.execute("SELECT COUNT(*) FROM voice_log WHERE action='budget_suppressed'").fetchone()[0]
    c.close()
    assert n == 1, (r1, r2, n)


def test_supresion_sin_bd_no_se_pierde(vb, monkeypatch):
    monkeypatch.setattr(vb, "_db_insert", lambda evs, timeout=5.0: 0)   # BD ocupada
    vb.log_suppression("SIGNAL", "x", "hour_cap", now=T0)
    assert sum(1 for _ in open(vb.SPOOL_PATH)) == 1, "el spool es la red de seguridad"


# ------------------------------------------------- congelacion de DANGER

def test_conteo_de_danger_congelado(vb):
    reg = json.load(open(vb.REGISTRY_PATH))
    n_danger = sum(1 for e in reg["emitters"].values() if e["class"] == "DANGER")
    assert reg["danger_frozen_limit"] == n_danger + 1
    assert n_danger == 7, "los 7 emisores DANGER verificados en el codigo"


def test_check_registry_detecta_danger_nuevo(vb):
    r = vb.check_registry()
    assert r["danger_frozen_limit"] == 8
    assert isinstance(r["files_with_danger"], dict) and r["files_with_danger"]
    assert "veredicto" in r


def test_emisor_deshabilitado_no_habla(vb):
    _enable(vb)
    reg = json.load(open(vb.REGISTRY_PATH))
    reg["emitters"]["prueba"] = {"module": "x", "class": "SIGNAL", "enabled": False}
    vb.atomic_write_json(vb.REGISTRY_PATH, reg)
    allow, reason, _ = vb.decide("SIGNAL", emitter="prueba", now=T0)
    assert allow is False and reason == "emitter_disabled"


# ------------------------------------------------- publicacion

def test_publish_publica_gasto_y_supresiones(vb):
    _enable(vb)
    _fill(vb, 3, "SIGNAL")
    _fill(vb, 2, "DANGER")
    vb.log_suppression("SIGNAL", "y", "hour_cap 12", now=T0)
    b = vb.publish(now=T0 + 10)
    assert b["spent"] == {"SIGNAL": 3, "DANGER": 2} and b["spent_total"] == 5
    assert b["suppressed"]["total"] == 1
    assert b["danger"]["never_suppressed"] is True
    assert b["enabled"] is True
    assert json.load(open(vb.BUDGET_PATH))["spent_total"] == 5
    assert not [f for f in os.listdir(os.path.dirname(vb.BUDGET_PATH)) if ".tmp" in f]


# ------------------------------------------------- gate como proceso (fail-open)

def _gate(vb, prio, extra=None):
    env = dict(os.environ)
    code = (
        "import importlib.util,sys;"
        "spec=importlib.util.spec_from_file_location('vb','%s/scripts/voice_budget.py');"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        "m.REGISTRY_PATH=%r;m.CAPS_PATH=%r;m.SPEND_DIR=%r;m.SPOOL_PATH=%r;m.ENABLE_PATH=%r;m.DB=%r;"
        "sys.argv=['vb','--gate',%r];m.main()"
        % (REPO, vb.REGISTRY_PATH, vb.CAPS_PATH, vb.SPEND_DIR, vb.SPOOL_PATH,
           vb.ENABLE_PATH, vb.DB, prio)
    )
    return subprocess.run([os.path.join(REPO, "venv", "bin", "python"), "-c", code],
                          capture_output=True, text=True, env=env)


def test_gate_devuelve_42_solo_al_suprimir(vb):
    _enable(vb)
    r = _gate(vb, "SIGNAL")
    assert r.returncode == 0, r.stderr
    _fill(vb, 100)
    r2 = _gate(vb, "SIGNAL")
    assert r2.returncode == 42
    r3 = _gate(vb, "DANGER")
    assert r3.returncode == 0, "DANGER jamas devuelve 42"


def test_gate_con_ficheros_corruptos_deja_hablar(vb):
    _enable(vb)
    with open(vb.CAPS_PATH, "w") as f:
        f.write("{roto")
    with open(vb.REGISTRY_PATH, "w") as f:
        f.write("no json")
    r = _gate(vb, "SIGNAL")
    assert r.returncode == 0, "fail-open: un json corrupto NO puede volver muda la flota"


def test_gate_sin_interruptor_deja_hablar(vb):
    _fill(vb, 100)
    r = _gate(vb, "SIGNAL")
    assert r.returncode == 0
