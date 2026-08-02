"""Contrato de los 3 jobs de impresion (open+5, premarket, post-market).

El script de open+5 existia desde el 2026-07-30 pero NADIE lo programaba y usaba `python3`
del sistema (sin matplotlib) + la raiz clavada: bajo launchd habria muerto en silencio.
Estos tests fijan las 4 cosas que lo habrian cazado: plist valido, script existente y
ejecutable, interprete del venv, raiz derivada. Mas el universo en data/ y el fail-loud.
"""
import os
import plistlib
import re
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")

PLISTS = ["com.ibtrader.printopen5.plist",
          "com.ibtrader.printpremarket.plist",
          "com.ibtrader.printpostmarket.plist"]

# runner -> (fichero de universo, plist que lo dispara)
RUNNERS = {
    "print_open5_spy_aapl.sh": ("data/print_syms_open5.txt", "com.ibtrader.printopen5.plist"),
    "print_premarket_trees.sh": ("data/print_syms_premarket.txt", "com.ibtrader.printpremarket.plist"),
    "print_postmarket_plans.sh": ("data/print_syms_postmarket.txt", "com.ibtrader.printpostmarket.plist"),
}
LOTE = list(RUNNERS) + ["print_plans.sh"]
SYM_FILES = [v[0] for v in RUNNERS.values()]

HARDCODED_ROOT = "/Users/yuniorrodriguezosorio/ib-trader"


def _load_plist(name):
    with open(os.path.join(SCRIPTS, name), "rb") as fh:
        return plistlib.load(fh)


def _scripts_referenced(pl):
    """Rutas scripts/*.sh que aparecen en ProgramArguments (directas o dentro de zsh -lc)."""
    blob = " ".join(pl["ProgramArguments"])
    return re.findall(r"scripts/[A-Za-z0-9_]+\.sh", blob)


@pytest.mark.parametrize("name", PLISTS)
def test_plist_valido_y_label_coincide_con_el_fichero(name):
    pl = _load_plist(name)
    assert pl["Label"] == name[:-len(".plist")]


@pytest.mark.parametrize("name", PLISTS)
def test_plist_apunta_a_un_script_existente_y_ejecutable(name):
    refs = _scripts_referenced(_load_plist(name))
    assert refs, f"{name} no referencia ningun scripts/*.sh"
    for r in refs:
        p = os.path.join(REPO, r)
        assert os.path.isfile(p), f"{name} -> {r} NO existe"
        assert os.access(p, os.X_OK), f"{name} -> {r} no es ejecutable"


@pytest.mark.parametrize("name", PLISTS)
def test_plist_no_corre_al_cargar_y_tiene_horario(name):
    pl = _load_plist(name)
    assert pl.get("RunAtLoad") is False
    cal = pl["StartCalendarInterval"]
    cal = cal if isinstance(cal, list) else [cal]
    assert {c["Weekday"] for c in cal} == {1, 2, 3, 4, 5}
    assert len({(c["Hour"], c["Minute"]) for c in cal}) == 1


@pytest.mark.parametrize("name", LOTE)
def test_ningun_script_usa_el_python3_del_sistema(name):
    txt = open(os.path.join(SCRIPTS, name)).read()
    assert not re.search(r"(?<![/\w])python3\b", txt), \
        f"{name} usa python3 del sistema (sin matplotlib/numpy): debe ser ./venv/bin/python"


@pytest.mark.parametrize("name", LOTE)
def test_ningun_script_clava_la_raiz_del_repo(name):
    txt = open(os.path.join(SCRIPTS, name)).read()
    assert HARDCODED_ROOT not in txt, f"{name} clava la raiz: derivala de ${{0:A:h:h}}"


@pytest.mark.parametrize("rel", SYM_FILES)
def test_universo_en_data_no_vacio_y_solo_tickers(rel):
    syms = open(os.path.join(REPO, rel)).read().split()
    assert syms, f"{rel} vacio"
    for s in syms:
        assert re.fullmatch(r"[A-Z.]+", s), f"{rel}: '{s}' no es un ticker"


@pytest.mark.parametrize("runner,rel", [(k, v[0]) for k, v in RUNNERS.items()])
def test_runner_lee_el_universo_del_fichero(runner, rel):
    txt = open(os.path.join(SCRIPTS, runner)).read()
    assert os.path.basename(rel) in txt, f"{runner} no lee {rel}"
    assert "--syms-file" in txt


@pytest.mark.parametrize("runner", list(RUNNERS))
def test_runner_pasa_el_portero_de_dia_de_mercado_y_el_flag_de_papel(runner):
    """Sin --market-day imprimiria en festivos; sin --print no llegaria al papel."""
    txt = open(os.path.join(SCRIPTS, runner)).read()
    assert "--market-day" in txt
    assert "--print" in txt


def test_open5_y_premarket_imprimen_EL_MISMO_PAR():
    """Yunior 2026-07-30 pidio el mismo par en los dos pases ("do the same for apple", "before
    market open and 5 min after open"). Son dos ficheros porque cada job es dueño de su universo
    y print_premarket_trees.sh esta fuera de este lote; este test es el que GRITA si divergen en
    silencio. Si algun dia se quiere divergir de verdad, se cambia este test a proposito."""
    a = set(open(os.path.join(REPO, "data", "print_syms_open5.txt")).read().split())
    b = set(open(os.path.join(REPO, "data", "print_syms_premarket.txt")).read().split())
    assert a == b, f"open5 {sorted(a)} != premarket {sorted(b)}"


def test_la_valla_la_escribe_solo_el_job_de_la_fence():
    """--envelope a las 09:35 reescribia la valla de SPY/AAPL en los 5 min de spread mas ancho e
    IV mas alta, dejando 2 simbolos con procedencia distinta a los otros 28 de fleet.txt. La
    doctrina (skill expected-move-envelope) captura el straddle <=15:55 y la valla describe el
    DIA: la escribe com.ibtrader.fence (09:12 y 15:56) sobre em_envelope --all, nadie mas."""
    for runner in RUNNERS:
        code = [ln for ln in open(os.path.join(SCRIPTS, runner)).read().splitlines()
                if not ln.lstrip().startswith("#")]
        assert "--envelope" not in " ".join(code), \
            f"{runner} reescribe la valla: la escribe com.ibtrader.fence"
    fence = _load_plist("com.ibtrader.fence.plist")
    blob = " ".join(fence["ProgramArguments"])
    assert "em_envelope.py --all" in blob
    fleet = set(open(os.path.join(REPO, "data", "fleet.txt")).read().split())
    for rel in ("data/print_syms_open5.txt", "data/print_syms_premarket.txt"):
        assert set(open(os.path.join(REPO, rel)).read().split()) <= fleet


def test_postmarket_archiva_su_propia_cadena():
    """GLW/NBIS/BE no estan en data/universe_gamma.txt: nadie les archiva el libro."""
    gamma = set(open(os.path.join(REPO, "data", "universe_gamma.txt")).read().split())
    syms = open(os.path.join(REPO, "data", "print_syms_postmarket.txt")).read().split()
    if set(syms) - gamma:
        txt = open(os.path.join(SCRIPTS, "print_postmarket_plans.sh")).read()
        assert "--archive" in txt


# ------------------------------------------------- nada clavado: impresora e interprete de PDF
def _resolve(var, env):
    """Resuelve de verdad las asignaciones del motor en zsh (no basta con grepearlas)."""
    src = open(os.path.join(SCRIPTS, "print_plans.sh")).read()
    lines = [ln for ln in src.splitlines() if re.match(r"^(PRINTER|CHROME)=", ln)]
    assert len(lines) == 2, f"asignaciones esperadas 2, encontradas {lines}"
    base = {k: v for k, v in os.environ.items()
            if k not in ("PRINTER", "LPDEST", "IBT_PRINTER", "IBT_CHROME")}
    r = subprocess.run(["/bin/zsh", "-c", "\n".join(lines) + f"\nprint -r -- ${var}"],
                       env=dict(base, **env), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_impresora_por_defecto_y_override_por_entorno():
    """IBT_PRINTER gana, luego el PRINTER estandar de CUPS (lpr(1)), luego el HP de casa."""
    assert _resolve("PRINTER", {}) == "HP_OfficeJet_Pro_9120e_Series"
    assert _resolve("PRINTER", {"IBT_PRINTER": "Brother_HL"}) == "Brother_HL"
    assert _resolve("PRINTER", {"PRINTER": "CUPS_DEF"}) == "CUPS_DEF"
    assert _resolve("PRINTER", {"PRINTER": "CUPS_DEF", "IBT_PRINTER": "Brother_HL"}) == "Brother_HL"


def test_chrome_por_defecto_y_override_por_entorno():
    assert _resolve("CHROME", {}) == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert _resolve("CHROME", {"IBT_CHROME": "/opt/chromium/chrome"}) == "/opt/chromium/chrome"


def test_ni_impresora_ni_chrome_clavados_en_otro_sitio():
    src = open(os.path.join(SCRIPTS, "print_plans.sh")).read()
    assert src.count("HP_OfficeJet") == 1, "la impresora solo puede aparecer como default"
    assert src.count("/Applications/") == 1, "la ruta de Chrome solo puede aparecer como default"


def test_motor_no_imprime_por_defecto():
    """IBT_ALLOW_PRINT por defecto 0 (orden Yunior 2026-07-27)."""
    txt = open(os.path.join(SCRIPTS, "print_plans.sh")).read()
    assert "ALLOW_PRINT=${IBT_ALLOW_PRINT:-0}" in txt


def test_motor_aborta_fail_loud_si_ningun_simbolo_tiene_cadena(tmp_path):
    """Ticker inexistente -> exit 4 y CERO PDF: jamas un plan con niveles fabricados."""
    f = tmp_path / "syms.txt"
    f.write_text("ZZINEXISTENTE\n")
    dest = tmp_path / "hoy"
    env = dict(os.environ, IBT_ALLOW_PRINT="0", IBT_DESKTOP_HOY=str(dest))
    r = subprocess.run([os.path.join(SCRIPTS, "print_plans.sh"),
                        "--syms-file", str(f), "--tag", "pytest"],
                       cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 4, r.stdout + r.stderr
    assert "ABORTADO" in r.stdout
    assert not list(dest.rglob("*.pdf"))


def test_motor_rechaza_universo_vacio(tmp_path):
    f = tmp_path / "vacio.txt"
    f.write_text("")
    r = subprocess.run([os.path.join(SCRIPTS, "print_plans.sh"), "--syms-file", str(f)],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert "vacio" in r.stderr
