"""Refresco continuo del mapa: cadencia por fase, enrutado de proveedor y EDAD del dato.

Lo que se fija aqui es lo que costo dinero: (a) que la fase 'cerrado' gane cuando el portero
no responde -- jamas trabajar a ciegas; (b) que el VIX no invente un numero cuando la fuente
cae; (c) que la EDAD viaje con el dato y no se confunda con un epoch; (d) que la estructura
VX no se construya con los semanales muertos cuyo `settlement` viene clonado del monthly.
"""
import importlib.util
import json
import os
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def vf():
    return _load("vix_feed")


@pytest.fixture(scope="module")
def dae():
    return _load("levels_refresh_daemon")


@pytest.fixture(scope="module")
def gc():
    return _load("gex_core")


# ----------------------------- VIX: proveedor y honestidad -----------------------------

def test_banda_vix_igual_que_compass(vf):
    """CALM <16 / ELEVADO 16-24 / ALTO >24 — la particion de compass.cpp:101, sin drift."""
    assert vf.band(15.99) == "CALM"
    assert vf.band(16.0) == "ELEVADO"
    assert vf.band(24.0) == "ELEVADO"
    assert vf.band(24.01) == "ALTO"
    assert vf.band(None) is None


def test_registro_de_proveedores_conserva_ibkr(vf):
    """El camino IBKR NO se borra: queda declarado, con prioridad 0 y su escritor."""
    assert "ibkr" in vf.PROVEEDORES and "cboe" in vf.PROVEEDORES
    assert vf.PROVEEDORES["ibkr"]["prio"] < vf.PROVEEDORES["cboe"]["prio"]
    assert vf.PROVEEDORES["ibkr"]["latencia"] == "tiempo_real"
    assert "chart_bridge" in vf.PROVEEDORES["ibkr"]["escribe"]


def test_fuente_caida_no_inventa_vix(vf, monkeypatch):
    """Fail-loud: si CBOE no responde, (None, motivo). Jamas un 15.0 plausible."""
    monkeypatch.setattr(vf, "_ibkr_owns", lambda: False)
    monkeypatch.setattr(vf, "_get_json", lambda url: (_ for _ in ()).throw(OSError("boom")))
    d, why = vf.resolve()
    assert d is None and "cboe" in why


def test_current_price_cero_no_pasa(vf, monkeypatch):
    monkeypatch.setattr(vf, "_ibkr_owns", lambda: False)
    monkeypatch.setattr(vf, "_get_json", lambda url: {"data": {"current_price": 0}})
    d, why = vf.resolve()
    assert d is None and "current_price" in why


def _row(sym, exp, last, sett, vol, oi):
    return {"symbol": sym, "expiration": exp, "last_price": last, "settlement": sett,
            "volume": vol, "prev_open_int": oi}


def test_vx_term_descarta_semanales_con_settlement_clonado(vf, monkeypatch):
    """Medido 2026-08-03: VX31/Q6 (OI 0) y VX32/Q6 (OI 10) traen el settlement del monthly.
    Coger 'los tres primeros por vencimiento' los mete delante del front que SI cotiza."""
    rows = [_row("VX31/Q6", "08/05/2026", 0.0, 18.1046, 0, 0),
            _row("VX32/Q6", "08/12/2026", 0.0, 18.1046, 0, 10),
            _row("VX/Q6", "08/19/2026", 17.88, 18.1046, 6388, 158740),
            _row("VX/U6", "09/16/2026", 18.97, 19.2499, 3731, 96018)]
    monkeypatch.setattr(vf, "_get_json", lambda url: {"data": rows})
    out, why = vf.vx_term()
    assert why is None
    assert [x["sym"] for x in out] == ["VX/Q6", "VX/U6"]
    assert out[0]["px"] == 17.88 and out[0]["px_src"] == "last"


def test_vx_term_sin_estructura_devuelve_motivo(vf, monkeypatch):
    monkeypatch.setattr(vf, "_get_json", lambda url: {"data": [
        _row("VX31/Q6", "08/05/2026", 0.0, 18.1, 0, 0)]})
    out, why = vf.vx_term()
    assert out is None and "sin estructura" in why


def test_vix_state_es_tri_estado_y_la_edad_es_la_del_dato(vf, monkeypatch):
    """`ts` es la edad del FICHERO (gate de 90 s de compass); `data_age_s` la del NUMERO.
    Confundirlos es fingir frescura: un tick del viernes escrito ahora no es de ahora."""
    ayer = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 30 * 3600))
    monkeypatch.setattr(vf, "_ibkr_owns", lambda: False)
    monkeypatch.setattr(vf, "_get_json", lambda url: (
        {"data": {"current_price": 15.92, "last_trade_time": ayer, "prev_day_close": 15.99}}
        if "quotes" in url else {"data": []}))
    d, why = vf.resolve()
    assert why is None
    assert d["vix_state"] == "close" and d["vix_live"] == 0
    assert d["data_age_s"] > 3600 and abs(d["ts"] - time.time()) < 30
    assert d["band"] == "CALM" and d["latencia"] == "delayed_15m"


def test_cede_el_fichero_a_ibkr_cuando_ibkr_escribe(vf, monkeypatch, tmp_path):
    """Condicional por proveedor: si TWS esta escribiendo data/vix.json en tiempo real, el
    respaldo delayed NO lo pisa (regla 4: nada delayed disfrazado de vivo)."""
    p = tmp_path / "vix.json"
    p.write_text(json.dumps({"vix": 15.5, "vix_live": 1, "ts": int(time.time())}))
    monkeypatch.setattr(vf, "OUT", str(p))
    monkeypatch.setattr(vf, "market_source", lambda: "ibkr")
    assert vf._ibkr_owns() is True
    d, why = vf.resolve()
    assert d is None and "ibkr" in why
    # y con otro proveedor activo el fichero es nuestro
    monkeypatch.setattr(vf, "market_source", lambda: "intrinio")
    assert vf._ibkr_owns() is False


def test_no_cede_a_un_ibkr_rancio(vf, monkeypatch, tmp_path):
    p = tmp_path / "vix.json"
    p.write_text(json.dumps({"vix": 15.5, "vix_live": 1, "ts": int(time.time()) - 10000}))
    monkeypatch.setattr(vf, "OUT", str(p))
    monkeypatch.setattr(vf, "market_source", lambda: "ibkr")
    assert vf._ibkr_owns() is False


def test_escritura_atomica_del_vix(vf, tmp_path):
    p = tmp_path / "vix.json"
    vf.write({"vix": 16.0, "ts": 1}, str(p))
    assert json.loads(p.read_text())["vix"] == 16.0
    assert not list(tmp_path.glob("*.tmp*"))


# ----------------------------- cadencia y portero -----------------------------

def test_cadencia_cubre_todas_las_fases_y_tareas(dae):
    for fase in ("premarket", "rth", "afterhours", "noche", "cerrado"):
        for tarea in ("levels", "gex", "vix"):
            assert tarea in dae.CADENCIA[fase]
    # RTH es la fase mas rapida de las que trabajan, y nunca por debajo del escritor de la
    # cadena (~60 s): mas rapido no da frescura, procesa las mismas entradas.
    assert dae.CADENCIA["rth"]["levels"] >= 60
    assert dae.CADENCIA["rth"]["gex"] >= 60
    assert dae.CADENCIA["rth"]["gex"] <= dae.CADENCIA["premarket"]["gex"]
    assert dae.CADENCIA["afterhours"]["gex"] > dae.CADENCIA["rth"]["gex"]
    assert all(v is None for v in dae.CADENCIA["cerrado"].values())


def test_cadencia_por_debajo_del_gate_de_fleet_consensus(dae):
    """fleet_consensus.cpp:97 tira un levels de mas de 180 s. La cadencia de RTH tiene que
    dejar margen para el barrido entero de la flota, no ir justa."""
    assert dae.CADENCIA["rth"]["levels"] * 2 < 180


def test_cadencia_env_override(dae, monkeypatch):
    monkeypatch.setenv("IBT_REFRESH_GEX_RTH_S", "30")
    assert dae._cad("rth", "gex") == 30
    monkeypatch.setenv("IBT_REFRESH_GEX_RTH_S", "off")
    assert dae._cad("rth", "gex") is None


def test_portero_ausente_no_trabaja(dae, monkeypatch):
    """Precedente de la casa: el consumidor que no encuentra al portero NO revive nada."""
    monkeypatch.setattr(dae.fleet_window, "live", lambda: None)
    fase, why = dae.fase_ahora()
    assert fase == "cerrado" and "portero" in why.lower()
    assert dae._cad(fase, "gex") is None


def test_portero_dead_no_trabaja(dae, monkeypatch):
    monkeypatch.setattr(dae.fleet_window, "live", lambda: False)
    monkeypatch.setattr(dae.fleet_window, "why", lambda: "fuera de ventana")
    assert dae.fase_ahora()[0] == "cerrado"


def test_fases_por_reloj(dae, monkeypatch):
    monkeypatch.setattr(dae.fleet_window, "live", lambda: True)
    hoy = time.localtime()
    def t(h, m):
        return time.mktime((hoy.tm_year, hoy.tm_mon, hoy.tm_mday, h, m, 0, 0, 0, -1))
    esperado = {(3, 0): "noche", (7, 5): "premarket", (9, 29): "premarket",
                (9, 30): "rth", (15, 59): "rth", (16, 0): "afterhours",
                (19, 59): "afterhours", (20, 0): "noche"}
    if time.localtime().tm_wday >= 5:
        pytest.skip("fin de semana: la fase es 'noche' por definicion")
    for (h, m), fase in esperado.items():
        assert dae.fase_ahora(t(h, m))[0] == fase, f"{h:02d}:{m:02d}"


# ----------------------------- EDAD del mapa gamma -----------------------------

def test_cabecera_de_cadena_declara_procedencia_del_spot(gc, tmp_path):
    """El spot de la cabecera tiene reloj PROPIO (finnhub en tiempo real dentro de una cadena
    Polygon delayed). Sin spot_src/spot_age el consumidor no puede distinguirlos."""
    p = tmp_path / "opt_chain_qqq.txt"
    p.write_text("# opt_chain QQQ | epoch 1785754890 | spot 690.71 | spot_src finnhub | "
                 "spot_age 37 | exps 20260803\n"
                 "# fuente polygon | band 0.1500 | greeks_ok_pct 0.5556 | bidask_ok_pct 0.0000\n"
                 "# strike right exp bid ask vol oi iv delta gamma\n")
    h = gc.parse_chain_header(str(p))
    assert h["spot_src"] == "finnhub" and h["spot_age"] == 37.0
    assert h["fuente"] == "polygon" and h["bidask_ok_pct"] == 0.0
    assert h["spot"] == 690.71


def test_chain_age_es_una_edad_no_un_epoch():
    """El campo se llamaba chain_age_s y guardaba el epoch crudo: cualquier consumidor que lo
    leyera como segundos veia 1.785 millones de segundos de antiguedad."""
    p = os.path.join(REPO, "data", "gex_snapshot.json")
    if not os.path.exists(p):
        pytest.skip("sin mapa gamma en disco")
    d = json.load(open(p))
    edades = [v["chain_age_s"] for k, v in d.items()
              if k != "_meta" and isinstance(v, dict) and v.get("chain_age_s") is not None]
    if not edades:
        pytest.skip("ningun simbolo desde cache vivo")
    assert max(edades) < 30 * 86400, "chain_age_s parece un epoch, no una edad"


def test_meta_del_mapa_publica_edad_y_clase_de_retraso():
    p = os.path.join(REPO, "data", "gex_snapshot.json")
    if not os.path.exists(p):
        pytest.skip("sin mapa gamma en disco")
    m = json.load(open(p))["_meta"]
    assert "asof" in m and "chain_age_max_s" in m and "delay_classes" in m
