"""korea_bar_bridge: el puerto se RESUELVE y el fallo GRITA.

TODOS.md 2026-07-26: el bridge tenia 4002 clavado con el Gateway en 4001 -> crash-loop
mudo y 65 h de barras coreanas rancias sin que nada lo dijera (la flota perdio el
adelanto de 13 h de la memoria coreana). Aqui se fija el contrato:
  - resolve_port() sondea candidatos y devuelve el que ACEPTA, o None (jamas un
    puerto plausible que solo sirve para volver a fallar).
  - sin ningun puerto vivo -> grita.
  - barras rancias con KRX abierto -> grita; con KRX cerrado -> callar (el fin de
    semana no es una averia).
Sin red: se monkeypatchea el sondeo TCP y el reloj KRX.
"""
import importlib.util
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(REPO, "scripts", "korea_bar_bridge.py")
    spec = importlib.util.spec_from_file_location("ibt_korea_bar_bridge", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_net(mod, monkeypatch, abiertos, modo="paper"):
    monkeypatch.setattr(mod.ib_mode, "_listening", lambda p: int(p) in abiertos)
    monkeypatch.setattr(mod.ib_mode, "get_mode", lambda: modo)


def _capture_loud(mod, monkeypatch):
    gritos = []
    monkeypatch.setattr(mod, "loud", lambda *a, **k: gritos.append(a))
    return gritos


def test_autodeteccion_elige_4001_cuando_4002_rechaza(monkeypatch):
    """El caso real del 2026-07-26: modo paper (4002 primero) pero el Gateway
    esta en 4001. Debe saltar el que rechaza y quedarse con el que acepta."""
    mod = _load()
    monkeypatch.delenv("IBKR_PORT", raising=False)
    monkeypatch.delenv("IB_PORT", raising=False)
    _fake_net(mod, monkeypatch, abiertos={4001}, modo="paper")
    assert mod.resolve_port() == 4001


def test_ibkr_port_explicito_gana_si_acepta(monkeypatch):
    mod = _load()
    monkeypatch.setenv("IBKR_PORT", "7497")
    _fake_net(mod, monkeypatch, abiertos={4001, 7497}, modo="live")
    assert mod.resolve_port() == 7497


def test_ningun_puerto_acepta_grita_y_devuelve_none(monkeypatch):
    """Nada de 4002 'por defecto': None es la unica respuesta honesta, y no muda."""
    mod = _load()
    monkeypatch.delenv("IBKR_PORT", raising=False)
    monkeypatch.delenv("IB_PORT", raising=False)
    _fake_net(mod, monkeypatch, abiertos=set(), modo="live")
    gritos = _capture_loud(mod, monkeypatch)
    assert mod.resolve_port() is None
    assert gritos, "sin puerto vivo el bridge debe GRITAR, no callar"


def test_barras_rancias_con_krx_abierto_grita(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "krx_market", lambda: True)
    monkeypatch.setattr(mod, "newest_bar_epoch", lambda: 1_000_000.0)
    gritos = _capture_loud(mod, monkeypatch)
    assert mod.freshness_guard(now=1_000_000.0 + mod.STALE_MAX_S + 1) is True
    assert gritos


def test_barras_rancias_con_krx_cerrado_no_grita(monkeypatch):
    """Falso positivo del fin de semana: fuera de sesion las barras viejas son lo normal."""
    mod = _load()
    monkeypatch.setattr(mod, "krx_market", lambda: False)
    monkeypatch.setattr(mod, "newest_bar_epoch", lambda: 1_000_000.0)
    gritos = _capture_loud(mod, monkeypatch)
    assert mod.freshness_guard(now=1_000_000.0 + 65 * 3600) is False
    assert not gritos


def test_barras_frescas_en_sesion_no_gritan(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "krx_market", lambda: True)
    monkeypatch.setattr(mod, "newest_bar_epoch", lambda: 1_000_000.0)
    gritos = _capture_loud(mod, monkeypatch)
    assert mod.freshness_guard(now=1_000_000.0 + 30) is False
    assert not gritos


def test_sin_ningun_fichero_de_barras_grita_en_sesion(tmp_path, monkeypatch):
    """newest_bar_epoch() devuelve None (no 0) cuando no hay nada legible; el guardian
    lo trata como averia, no como 'epoch cero'."""
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(mod, "krx_market", lambda: True)
    gritos = _capture_loud(mod, monkeypatch)
    assert mod.newest_bar_epoch() is None
    assert mod.freshness_guard() is True
    assert gritos


def test_satelite_mudo_no_dispara_el_guardian(tmp_path, monkeypatch):
    """Los satelites HBM son ilíquidos: su silencio NO es averia. Solo CORE manda."""
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(mod, "krx_market", lambda: True)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bars_samsung.txt").write_text("1785110060 1 1 1 1 1\n")
    (tmp_path / "data" / "bars_hanmi.txt").write_text("1785000000 1 1 1 1 1\n")
    gritos = _capture_loud(mod, monkeypatch)
    assert mod.freshness_guard(now=1785110060 + 30) is False
    assert not gritos


def test_newest_bar_epoch_lee_el_ultimo_epoch_escrito(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bars_samsung.txt").write_text(
        "1785110000 100 101 99 100 5\n1785110060 100 102 99 101 7\n")
    (tmp_path / "data" / "bars_kospi.txt").write_text("1785109000 10 10 10 10 1\n")
    assert mod.newest_bar_epoch() == 1785110060.0
