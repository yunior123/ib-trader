"""Enrutado de proveedores: el PRINT vivo manda y la fuente viaja con el numero.

Medido el 2026-08-03 en sesion (docs/REALTIME-FUENTES-2026-08-03.md):
  Finnhub WS  -> 0,00-0,04 s contra el reloj de bolsa (TIEMPO REAL), sin libro, cinta muestreada
  Intrinio    -> quote 1.240-1.280 s y barras 997-1.657 s (cboe_one_delayed)
  Databento   -> "A live data license is required" (historico si, vivo no)
Regla que blindan estos tests: ningun precio delayed puede ganar cuando hay print vivo, y
nadie devuelve un numero plausible cuando no sabe.
"""
import importlib.util
import os
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import rt_last  # noqa: E402


def _load(nombre):
    spec = importlib.util.spec_from_file_location(nombre, os.path.join(REPO, "scripts", nombre + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FWB = _load("finnhub_ws_bridge")
# provider_bridge importa la capa mit/ (py3.11+, `datetime.UTC`) y la suite corre en py3.9:
# ahi se salta. La verificacion completa se hace con ./venv-mit/bin/python -m pytest.
PB = _load("provider_bridge") if sys.version_info >= (3, 11) else None
solo_mit = pytest.mark.skipif(PB is None, reason="provider_bridge exige py3.11+ (venv-mit)")


def _cd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)


# ---------------- rt_last: fresh / snapshot ----------------

def test_fresh_devuelve_none_sin_fichero(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    assert rt_last.fresh("SPY") is None          # None, jamas un 0 que parezca precio


def test_fresh_rechaza_rancio(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("SPY", time.time() - 5, 744.27, 1, "finnhub")
    assert rt_last.fresh("SPY", max_age_s=1) is None
    px, ep, src, edad = rt_last.fresh("SPY", max_age_s=60)
    assert px == 744.27 and src == "finnhub" and edad < 60


def test_snapshot_declara_los_mudos(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("QQQ", time.time(), 690.95, 60, "finnhub")
    snap = rt_last.snapshot(["QQQ", "SPY"])
    assert snap["SPY"] is None                   # SPY MUDO se DECLARA, no se rellena
    assert snap["QQQ"]["fuente"] == "finnhub"


# ---------------- resolve_spot: el punto unico de decision ----------------

@solo_mit
def test_print_vivo_gana_al_quote_delayed(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("QQQ", time.time() - 3, 691.35, 60, "finnhub")
    px, src, edad = PB.resolve_spot("QQQ", 690.10, 1200.0)
    assert (px, src) == (691.35, "finnhub") and edad < 10


@solo_mit
def test_quote_gana_si_el_print_esta_rancio(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("QQQ", time.time() - 30, 691.35, 60, "finnhub")
    monkeypatch.setattr(PB, "PRINT_MAX_AGE_S", 10.0)
    px, src, _ = PB.resolve_spot("QQQ", 690.10, 2.0)
    assert (px, src) == (690.10, "intrinio_quote")


@solo_mit
def test_sin_nada_no_inventa(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    assert PB.resolve_spot("SPY", 0.0, -1.0) == (0.0, "ninguna", -1.0)


@solo_mit
def test_fuente_viaja_con_el_numero(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    rt_last.write_if_newer("SPY", time.time(), 750.86, 1, "loquesea")
    assert PB.resolve_spot("SPY", 749.0, 900.0)[1] == "loquesea"


# ---------------- tabla de proveedores: nada se borra ----------------

@solo_mit
def test_ibkr_sigue_declarado_entero():
    """Orden Yunior 2026-08-03: el codigo IBKR se apaga por condicional, JAMAS se borra."""
    ibkr = PB.PROVEEDORES["ibkr"]
    assert {"bars", "nbbo", "chain", "print"} <= set(ibkr["caps"])
    assert ibkr["latencia"] == "tiempo_real" and ibkr["prio"] == 0
    for f in ("scripts/ibkr_bar_bridge.py", "scripts/opt_chain_cache.py", "scripts/ib_mode.py"):
        assert os.path.exists(os.path.join(REPO, f)), f


@solo_mit
def test_tiempo_real_manda_sobre_delayed():
    rt = [n for n, p in PB.PROVEEDORES.items() if p["latencia"] == "tiempo_real"]
    dl = [n for n, p in PB.PROVEEDORES.items() if p["latencia"] != "tiempo_real"]
    assert max(PB.PROVEEDORES[n]["prio"] for n in rt) < min(PB.PROVEEDORES[n]["prio"] for n in dl)


@solo_mit
def test_finnhub_no_declara_libro():
    # Sin libro no hay NBBO: un bid=ask=last daria spread 0,00% y colaria el gate.
    assert "nbbo" not in PB.PROVEEDORES["finnhub"]["caps"]


# ---------------- salud de barras (el hueco de SMH) ----------------

@solo_mit
def test_bar_salud_cuenta_huecos_y_volumen_cero(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    monkeypatch.setattr(PB, "DATA", tmp_path / "data")
    eps = [1785750000, 1785750060, 1785750240, 1785750300]     # un salto de 3 min
    with open("data/bars_smh_ibkr.txt", "w") as f:
        for e in eps:
            f.write(f"{e} 536 536 536 536 0\n")
    edad, huecos, vol0 = PB.bar_salud("SMH")
    assert huecos == 1 and vol0 == 4 and edad > 0


@solo_mit
def test_bar_salud_sin_fichero_devuelve_none(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    monkeypatch.setattr(PB, "DATA", tmp_path / "data")
    assert PB.bar_salud("ZZZZ") == (None, None, None)


# ---------------- cabecera de cadena: procedencia y buffer de opt_quick ----------------

@solo_mit
def test_header_declara_la_fuente_del_spot_y_cabe_en_opt_quick(tmp_path, monkeypatch):
    from datetime import date

    class C:
        def __init__(self):
            self.strike, self.option_type, self.expiration = 690.0, "call", date(2026, 8, 3)
            self.bid, self.ask, self.volume, self.open_interest = 1.0, 1.1, 10, 20
            self.implied_volatility, self.delta, self.gamma = 0.2, 0.5, 0.01

    _cd(tmp_path, monkeypatch)
    monkeypatch.setattr(PB, "DATA", tmp_path / "data")
    PB.write_chain("QQQ", [C()], 691.35, "polygon", "finnhub", 3.0)
    head = open(tmp_path / "data" / "opt_chain_qqq.txt").read().split("\n")
    assert "spot_src finnhub" in head[0] and "spot 691.35" in head[0]
    # opt_quick.cpp lee con `char line[256]`: una cabecera mas larga se parte y la cola
    # entraria como fila de datos basura.
    assert all(len(l) < 240 for l in head[:3])


# ---------------- puente Finnhub: instancia unica y ventana RTH ----------------

def test_lock_de_instancia_unica(tmp_path, monkeypatch):
    _cd(tmp_path, monkeypatch)
    monkeypatch.setattr(FWB, "LOCK", str(tmp_path / "data" / ".finnhub_ws.lock"))
    fh = FWB.tomar_lock()
    assert fh is not None
    import subprocess
    r = subprocess.run([sys.executable, "-c",
                        f"import fcntl;f=open({FWB.LOCK!r},'w');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"],
                       capture_output=True)
    assert r.returncode != 0                     # el segundo NO puede tomarlo


def test_rth_ventana():
    import datetime as dt
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    lunes = dt.datetime(2026, 8, 3, tzinfo=et)
    assert FWB.rth(lunes.replace(hour=10).timestamp()) is True
    assert FWB.rth(lunes.replace(hour=6, minute=45).timestamp()) is False
    assert FWB.rth(lunes.replace(hour=16).timestamp()) is False
    sabado = dt.datetime(2026, 8, 1, 10, tzinfo=et)
    assert FWB.rth(sabado.timestamp()) is False
