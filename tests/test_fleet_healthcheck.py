"""fleet_healthcheck: el contrato de salida y el fin del bucle auto-referencial.

Bug cazado el 2026-07-25: el healthcheck salia exit 1 con CUALQUIER aviso 🟡, launchd
lo grababa como job fallido (LastExitStatus=1) y la corrida siguiente auditaba
`launchctl list`, veia su PROPIO exit 1 y lo reportaba como aviso nuevo. Bucle sobre
si mismo: nunca podia volver a verde. Dos arreglos, ambos fijados aqui:
  (a) exit 0 con solo avisos, non-zero SOLO con 🔴 real (no se pierde el fallo duro).
  (b) el propio label launchd queda fuera del audit de exit codes.
"""
import importlib.util
import os
import plistlib

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hc():
    return _load("fleet_healthcheck")


# --- (a) contrato de salida ---------------------------------------------------

def test_verde_sale_cero(hc):
    assert hc.exit_code([], []) == 0


def test_solo_avisos_sale_cero(hc):
    """Un healthcheck que informa de avisos NO ha fallado: launchd no debe verlo rojo."""
    assert hc.exit_code([], ["gexa snapshot: RANCIO 58h", "X ledger: no leible"]) == 0


def test_critico_sale_non_zero(hc):
    """La señal de fallo duro NO se pierde con el fix."""
    assert hc.exit_code(["launchd com.ibtrader.dailyplans: NO CARGADO"], []) != 0


def test_critico_con_avisos_sigue_non_zero(hc):
    assert hc.exit_code(["bar_bridge: MUERTO en horario activo"], ["aviso cualquiera"]) != 0


# --- (b) el healthcheck no se audita a si mismo -------------------------------

def test_audit_excluye_mi_propio_label(hc):
    """El escenario exacto del bucle: yo soy el unico job con exit!=0."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.healthcheck": "1"}
    ok, warn, crit = hc.audit_launchd(ld, "com.ibtrader.healthcheck")
    assert not crit
    assert not any("healthcheck" in w for w in warn), warn
    assert hc.exit_code(crit, warn) == 0  # verde de verdad: el bucle esta roto
    assert len(ok) == 2


def test_audit_sigue_cantando_a_los_demas(hc):
    """Excluirme a mi no debe amordazar el audit del resto de la flota."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.healthcheck": "1", "com.ibtrader.fence": "78"}
    _ok, warn, crit = hc.audit_launchd(ld, "com.ibtrader.healthcheck")
    assert not crit
    assert [w for w in warn if "com.ibtrader.fence" in w and "78" in w], warn
    assert not any("healthcheck" in w for w in warn), warn


def test_audit_job_critico_ausente_es_rojo(hc):
    ld = {"com.ibtrader.postmortem": "0"}
    _ok, _warn, crit = hc.audit_launchd(ld, "com.ibtrader.healthcheck")
    assert any("dailyplans" in c and "NO CARGADO" in c for c in crit), crit
    assert hc.exit_code(crit, []) != 0


def test_audit_sin_label_propio_no_excluye_nada(hc):
    """me_label=None (plist no encontrado) => no se excluye a nadie por error."""
    ld = {"com.ibtrader.dailyplans": "0", "com.ibtrader.postmortem": "0",
          "com.ibtrader.healthcheck": "1"}
    _ok, warn, _crit = hc.audit_launchd(ld, None)
    assert any("healthcheck" in w for w in warn), warn


def test_self_label_derivado_del_plist_no_hardcodeado(hc, tmp_path):
    """self_label() lee el Label del plist cuyos ProgramArguments apuntan a este script."""
    plist = {"Label": "com.ibtrader.renombrado",
             "ProgramArguments": ["/usr/bin/python3", hc.SELF_PATH]}
    with open(tmp_path / "com.ibtrader.renombrado.plist", "wb") as fh:
        plistlib.dump(plist, fh)
    assert hc.self_label(agents_dir=str(tmp_path), me=hc.SELF_PATH) == "com.ibtrader.renombrado"


def test_self_label_none_si_no_aparece(hc, tmp_path):
    """Sin plist propio devuelve None — jamas una cadena inventada que excluiria
    del audit el job de otro."""
    plist = {"Label": "com.ibtrader.otro",
             "ProgramArguments": ["/usr/bin/python3", "/otro/script.py"]}
    with open(tmp_path / "com.ibtrader.otro.plist", "wb") as fh:
        plistlib.dump(plist, fh)
    assert hc.self_label(agents_dir=str(tmp_path), me=hc.SELF_PATH) is None
    assert hc.self_label(agents_dir=str(tmp_path / "no-existe"), me=hc.SELF_PATH) is None


def test_self_label_plist_corrupto_no_mata_el_audit(hc, tmp_path, capsys):
    """Un plist ilegible se CANTA (fail-loud) y se sigue; no aborta el healthcheck."""
    (tmp_path / "roto.plist").write_bytes(b"no soy un plist")
    good = {"Label": "com.ibtrader.healthcheck",
            "ProgramArguments": [hc.SELF_PATH]}
    with open(tmp_path / "zz.plist", "wb") as fh:
        plistlib.dump(good, fh)
    assert hc.self_label(agents_dir=str(tmp_path), me=hc.SELF_PATH) == "com.ibtrader.healthcheck"
    assert "roto.plist" in capsys.readouterr().out


# --- fail-loud: nada de ceros/conjuntos plausibles ---------------------------

def test_canonical_fleet_none_si_falta(hc, monkeypatch):
    """None, no set(): un conjunto vacio saltaba los checks de cobertura en silencio."""
    monkeypatch.setattr(hc.os.path, "exists", lambda p: False)
    assert hc.canonical_fleet() is None


def test_canonical_fleet_real_tiene_la_flota(hc):
    canon = hc.canonical_fleet()
    assert canon is not None and {"QQQ", "SPY", "NVDA"} <= canon


def test_env_none_sin_clave(hc):
    assert hc.env("CLAVE_QUE_NO_EXISTE_JAMAS") is None
