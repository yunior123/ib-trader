"""Arnes E2E (scripts/e2e_smoke.sh): higiene del script + parser del informe.

NO ejecuta el arnes completo (arranca uvicorn, corre las dos suites y tarda minutos): eso es
verificacion manual. Aqui se cierra lo que si es determinista y barato: que el script no viole
las reglas duras de la casa (rutas del home clavadas, `python3` a pelo, git destructivo, pkill
de la flota) y que su modo `--summary` cuente PASS/FAIL/SKIPPED bien y salga != 0 si hay FAIL.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "e2e_smoke.sh"


def _src():
    return SCRIPT.read_text()


def test_script_existe_y_es_ejecutable():
    assert SCRIPT.exists(), f"{SCRIPT} no existe"
    assert SCRIPT.stat().st_mode & 0o111, "e2e_smoke.sh no tiene bit de ejecucion"
    assert _src().splitlines()[0].startswith("#!/bin/zsh")


def test_raiz_derivada_y_sin_rutas_del_home():
    src = _src()
    assert "${0:A:h}" in src, "la raiz debe derivarse de ${0:A:h}, no clavarse"
    # /Applications/... (Chrome del sistema) esta permitido; lo prohibido es el home de nadie.
    prohibidas = re.findall(r"(/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|~/ib-trader)", src)
    assert not prohibidas, f"rutas de home clavadas: {sorted(set(prohibidas))}"


def test_sin_python3_a_pelo():
    # todo interprete sale de ./venv/bin/python o ./venv-mit/bin/python
    src = _src()
    sueltos = [
        ln for ln in src.splitlines()
        if re.search(r"(?<![-./\w])python3?\s", ln)
        and "venv" not in ln
        and not ln.lstrip().startswith("#")
    ]
    assert not sueltos, f"interprete no anclado a un venv: {sueltos}"
    assert "./venv/bin/python" in src and "./venv-mit/bin/python" in src


def test_sin_git_destructivo_ni_pkill_de_la_flota():
    src = _src()
    destructivo = re.findall(r"git\s+(revert|checkout|reset|stash|clean)", src)
    assert not destructivo, f"git destructivo en el arnes: {destructivo}"
    assert "pkill" not in src, "pkill puede matar la flota: cerrar solo por PID propio"
    assert "killall" not in src
    # tampoco puede reescribir los interruptores de modo
    for prohibido in ("data/ib_mode.txt", "data/market_source.txt"):
        assert f"> {prohibido}" not in src and f">{prohibido}" not in src


def test_guarda_de_ventana_live_y_escritura_atomica():
    src = _src()
    assert "bin/fleet_hours" in src, "falta el portero horario"
    assert "--force" in src, "falta la escotilla --force del guard LIVE"
    assert "os.replace(tmp, out_path)" in src, "el informe debe escribirse tmp + os.replace"


def test_cubre_los_pasos_del_lote():
    src = _src()
    for pieza in ("provider_syms.txt", "opt_quick", "reversal_router.py",
                  "shock_calibrator.py", "gex_heatmap", "/api/trace/",
                  "IBT_ALLOW_MOCK", "pytest tests/", "mit/backend/tests"):
        assert pieza in src, f"el arnes no cubre {pieza}"


def _run_summary(report_path):
    zsh = shutil.which("zsh")
    if not zsh:
        pytest.skip("zsh no disponible")
    return subprocess.run(
        [zsh, str(SCRIPT), "--summary", str(report_path)],
        capture_output=True, text=True, timeout=120,
    )


def _report(steps):
    n = {"PASS": 0, "FAIL": 0, "SKIPPED": 0}
    for s in steps:
        n[s["status"]] += 1
    return {
        "generated_epoch": 1785600000,
        "generated": "2026-08-02T02:00:00-0400",
        "market_state": "DEAD",
        "steps": steps,
        "summary": {"pass": n["PASS"], "fail": n["FAIL"], "skipped": n["SKIPPED"], "total": len(steps)},
    }


def _write(tmp_path, steps):
    p = tmp_path / "e2e_report.json"
    p.write_text(json.dumps(_report(steps), indent=2))
    return p


def test_parser_cuenta_bien_y_sale_cero_sin_fallos(tmp_path):
    steps = [
        {"id": "1", "name": "portero", "status": "PASS", "evidence": "state=DEAD"},
        {"id": "2", "name": "contrato", "status": "PASS", "evidence": "26 syms"},
        {"id": "3", "name": "opt_quick", "status": "SKIPPED", "evidence": "sin cadena"},
    ]
    r = _run_summary(_write(tmp_path, steps))
    assert "RESUMEN e2e: PASS=2 FAIL=0 SKIPPED=1 TOTAL=3" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 0, r.stdout + r.stderr


def test_parser_sale_distinto_de_cero_si_hay_fail(tmp_path):
    steps = [
        {"id": "1", "name": "portero", "status": "PASS", "evidence": "state=DEAD"},
        {"id": "2", "name": "contrato", "status": "FAIL", "evidence": "QQQ:7 campos=5"},
        {"id": "3", "name": "opt_quick", "status": "SKIPPED", "evidence": "sin cadena"},
        {"id": "4", "name": "reversal", "status": "FAIL", "evidence": "estado INVENTADO"},
    ]
    r = _run_summary(_write(tmp_path, steps))
    assert "RESUMEN e2e: PASS=1 FAIL=2 SKIPPED=1 TOTAL=4" in r.stdout, r.stdout + r.stderr
    assert r.returncode != 0
    assert "QQQ:7 campos=5" in r.stdout


def test_parser_no_traga_estado_inventado(tmp_path):
    # un estado fuera del vocabulario no puede contarse como PASS silencioso (fail-loud)
    steps = [{"id": "1", "name": "portero", "status": "OKISH", "evidence": "?"}]
    p = tmp_path / "e2e_report.json"
    p.write_text(json.dumps({"steps": steps}))
    r = _run_summary(p)
    assert r.returncode != 0
    assert "estados desconocidos: 1" in r.stdout


def test_parser_falla_alto_con_informe_roto(tmp_path):
    p = tmp_path / "e2e_report.json"
    p.write_text("{ esto no es json")
    r = _run_summary(p)
    assert r.returncode != 0
    assert "ilegible" in r.stdout

    p2 = tmp_path / "sin_steps.json"
    p2.write_text(json.dumps({"summary": {"pass": 9}}))
    r2 = _run_summary(p2)
    assert r2.returncode != 0
    assert "steps" in r2.stdout
