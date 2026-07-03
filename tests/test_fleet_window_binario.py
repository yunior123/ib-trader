"""El puente al portero horario debe ENCONTRAR el binario esté donde esté.

Bug medido 2026-08-02 19:08: `fleet_window.BINARIO` apuntaba a `REPO/fleet_hours` pero el binario
vive en `REPO/bin/fleet_hours` desde la mudanza. `live()` devolvía None y el healthcheck cantaba
"portero horario AUSENTE: no revivo daemons a ciegas" — o sea, DEJABA DE REVIVIR LA FLOTA mientras
`./bin/fleet_hours` respondía perfectamente. Es el mismo precedente que ya mató la flota una vez
(mudanza a bin/, 05:15-06:48).
"""
import importlib.util
import os
import stat

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(repo=None):
    path = os.path.join(REPO, "scripts", "fleet_window.py")
    spec = importlib.util.spec_from_file_location("ibt_fleet_window_t", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if repo:
        mod.REPO = repo
        mod.BINARIO = mod._binario()
    return mod


def test_encuentra_el_binario_real_del_repo():
    """En este repo el portero está en bin/: si BINARIO no lo encuentra, el healthcheck se ciega."""
    mod = _load()
    assert os.path.basename(mod.BINARIO) == "fleet_hours"
    assert os.access(mod.BINARIO, os.X_OK), f"{mod.BINARIO} no es ejecutable"


def test_live_no_devuelve_None_con_el_portero_presente():
    """None = 'no se puede saber' y hace que el healthcheck NO revive nada. Con el binario ahí,
    la respuesta tiene que ser True o False, nunca None."""
    mod = _load()
    assert mod.live() in (True, False)


def _falso_portero(d, nombre):
    os.makedirs(os.path.dirname(os.path.join(d, nombre)), exist_ok=True)
    p = os.path.join(d, nombre)
    with open(p, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
    return p


def test_prefiere_bin_pero_acepta_la_raiz(tmp_path):
    raiz = _falso_portero(str(tmp_path), "fleet_hours")
    mod = _load(str(tmp_path))
    assert mod.BINARIO == raiz, "con solo la raíz debe usarla (respaldo)"

    binp = _falso_portero(str(tmp_path), "bin/fleet_hours")
    mod2 = _load(str(tmp_path))
    assert mod2.BINARIO == binp, "con ambos debe ganar bin/"


def test_sin_binario_nombra_bin_al_gritar(tmp_path):
    """El mensaje de 'falta' tiene que decir dónde se espera, o se busca en el sitio viejo."""
    mod = _load(str(tmp_path))
    assert mod.BINARIO.endswith(os.path.join("bin", "fleet_hours"))
    assert mod.live() is None
