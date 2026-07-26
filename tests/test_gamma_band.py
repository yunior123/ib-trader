"""Banda adaptativa del archivador y flip HONESTO del mapa (2026-07-26).

Lo que se fija aqui, con lo que se midio ese dia contra la cadena COMPLETA de CBOE:
  - BAND=0.045 fijo capturaba el 28% de la gamma (mediana de la flota, MU 7,7%) y con
    DTE<=10 el net GEX de QQQ salia -3,29 B $/1% contra los -5,3/-6,0 B de los referees.
    Con banda adaptativa + vencimientos hasta el mensual: -5,2 B.
  - 14 de 25 flips estaban clavados entre 3,7% y 4,6% del spot = el borde del recorte.
    `gex_core._flip` devuelve el EXTREMO del rango cuando el perfil no cambia de signo, y
    ese extremo se mueve con la banda: SKHY daba 207,5 / 230 / 270 / 305 / 390 segun donde
    se cortase la cadena. Un nivel que depende de mi recorte no es un nivel de mercado.
  - Ensanchar la banda hunde el % de contratos con OI>0, asi que el denominador de
    "griegas usables" tiene que contar CANDIDATOS (OI>0), no filas del fichero.
"""
import datetime as dt
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    import sys
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibgb_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = [path]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


@pytest.fixture(scope="module")
def pca():
    return _load("poly_chain_archive")


@pytest.fixture(scope="module")
def gs():
    return _load("gex_snapshot")


# ------------------------------------------------- vencimientos: hasta el mensual
def test_mensual_es_el_tercer_viernes(pca):
    assert pca.next_monthly(dt.date(2026, 7, 26)) == dt.date(2026, 8, 21)
    assert pca.next_monthly(dt.date(2026, 8, 21)) == dt.date(2026, 8, 21)   # el propio dia
    assert pca.next_monthly(dt.date(2026, 8, 22)) == dt.date(2026, 9, 18)   # ya paso
    assert pca.next_monthly(dt.date(2026, 12, 20)) == dt.date(2027, 1, 15)  # salto de año


def test_el_mensual_cubre_mas_que_los_10_dte_viejos(pca):
    """El DTE_MAX=10 fijo dejaba fuera el vencimiento donde vive el OI del mes: es la
    diferencia entre -3,29 B y -5,0 B de net GEX en QQQ."""
    hoy = dt.date(2026, 7, 26)
    assert (pca.next_monthly(hoy) - hoy).days > 10


# ------------------------------------------------------- la banda que dicta la gamma
def _c(strike, gamma, oi, tk=None):
    return {"details": {"ticker": tk or f"O:X{strike}{gamma}{oi}", "strike_price": strike,
                        "expiration_date": "2026-08-21", "contract_type": "call"},
            "greeks": {"gamma": gamma}, "open_interest": oi, "implied_volatility": 0.3}


def _libro(spot, hasta=1.0, paso=0.05, gamma_lejos=1e-9):
    """Libro sintetico: toda la gamma pegada al spot y migajas en las alas."""
    rows = [_c(round(spot * f, 2), 0.05 if abs(f - 1) <= 0.11 else gamma_lejos, 1000)
            for f in [1 + paso * i for i in range(-int(hasta / paso), int(hasta / paso) + 1)]]
    return [r for r in rows if r["details"]["strike_price"] > 0]


def test_para_cuando_la_gamma_marginal_se_agota(pca):
    """Con toda la gamma dentro de +-11% la corona nueva no aporta nada: se para pronto y
    NO se arrastra hasta el techo (el fichero no engorda por gusto)."""
    spot = 100.0
    rows, pages, band, trace = pca.fetch_chain_adaptive(pca.slicer_of(_libro(spot)), spot)
    assert band < pca.BAND_CAP
    assert trace[-1]["convergido"] is True
    assert trace[-1]["ring_share"] < pca.RING_EPS
    assert pages == 0                       # el troceador local no gasta peticiones


def test_ensancha_cuando_hay_gamma_en_las_alas(pca):
    """Si las alas pesan, la banda crece hasta el techo y se DICE que no convergio."""
    spot = 100.0
    libro = _libro(spot, gamma_lejos=0.05)   # gamma plana: la corona siempre aporta
    rows, _, band, trace = pca.fetch_chain_adaptive(pca.slicer_of(libro), spot)
    assert band == pca.BAND_CAP
    assert trace[-1]["convergido"] is False


def test_suelo_y_techo_son_duros(pca):
    spot = 100.0
    for pedido in (0.001, 5.0):
        _, _, band, _ = pca.fetch_chain_adaptive(pca.slicer_of(_libro(spot)), spot,
                                                 band0=pedido)
        assert pca.BAND_FLOOR <= band <= pca.BAND_CAP


def test_banda_fija_del_CLI_desactiva_la_adaptativa(pca):
    spot = 100.0
    rows, _, band, trace = pca.fetch_chain_adaptive(pca.slicer_of(_libro(spot)), spot,
                                                    fixed_band=0.045)
    assert band == 0.045 and trace[-1]["modo"] == "banda_fija"
    assert all(abs(r["details"]["strike_price"] - spot) <= 0.045 * spot + 1e-9 for r in rows)


def test_ningun_contrato_se_cuenta_dos_veces(pca):
    """Las coronas se piden con `strike_price.lt/gt` (estrictos), pero si un contrato
    llegase repetido su gamma se doblaria en el perfil: se indexa por ticker."""
    spot = 100.0
    libro = _libro(spot)
    doble = libro + [dict(r) for r in libro]          # cada contrato dos veces
    rows, _, _, _ = pca.fetch_chain_adaptive(pca.slicer_of(doble), spot)
    tks = [r["details"]["ticker"] for r in rows]
    assert len(tks) == len(set(tks))


def test_arrancar_en_la_banda_guardada_NO_la_hace_crecer_cada_corrida(pca):
    """`start_band` divide por el crecimiento: si arrancase EN la banda guardada, cada
    corrida la multiplicaria x1.5 (trinquete) hasta el techo sin motivo."""
    calib = {"QQQ": {"band": 0.18}}
    assert pca.start_band(calib, "QQQ") == pytest.approx(0.18 / pca.BAND_GROWTH)
    spot = 100.0
    _, _, band, _ = pca.fetch_chain_adaptive(pca.slicer_of(_libro(spot)), spot,
                                             band0=pca.start_band(calib, "QQQ"))
    assert band == pytest.approx(0.18)
    assert pca.start_band({}, "QQQ") is None
    assert pca.start_band({"X": {"band": "roto"}}, "X") is None


def test_gamma_marginal_ignora_lo_que_no_esta_medido(pca):
    """Un contrato sin gamma o sin OI no pesa: no se le inventa masa para justificar
    (ni para evitar) un ensanche."""
    assert pca.gamma_mass([_c(100, None, 500), _c(101, 0.05, 0)]) == 0.0
    assert pca.gamma_mass([_c(100, 0.05, 200)]) == pytest.approx(10.0)


# ------------------------------------------------- flip: raiz medida o None, nunca el borde
def _chain(tmp_path, sym, contratos, spot, meta=None):
    fecha = dt.date.today().isoformat()
    d = tmp_path / "data" / "history" / fecha
    d.mkdir(parents=True, exist_ok=True)
    m = {"sym": sym.upper(), "spot": spot, "snapshot_local": "2026-07-26 16:20:00",
         "band": 0.18, "exp_hasta": "2026-08-21", "greeks": "polygon_directo"}
    m.update(meta or {})
    p = d / f"chain_full_{sym.lower()}.json"
    p.write_text(json.dumps({"meta": m, "results": contratos}))
    return p


def _put(k, oi=900, gamma=0.02, exp="2026-08-21", iv=0.4):
    return {"details": {"strike_price": k, "contract_type": "put", "expiration_date": exp},
            "greeks": {"gamma": gamma}, "open_interest": oi, "implied_volatility": iv}


def _call(k, oi=900, gamma=0.02, exp="2026-08-21", iv=0.4):
    return {"details": {"strike_price": k, "contract_type": "call", "expiration_date": exp},
            "greeks": {"gamma": gamma}, "open_interest": oi, "implied_volatility": iv}


def test_libro_sin_cruce_publica_flip_None_no_el_borde(gs, tmp_path, monkeypatch):
    """Todo puts = gamma negativa a cualquier precio: NO hay flip. Antes se publicaba el
    strike mas alto de la banda, y ese numero cambiaba al cambiar la banda."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = [_put(80.0 + i, iv=0.3 + i * 0.01) for i in range(40)]
    _chain(tmp_path, "SKHY", cs, spot=100.0)
    snap, why = gs.snapshot_sym("SKHY")
    assert why is None and snap is not None, why
    assert snap["flip"] is None
    assert "sin_cruce" in snap["flip_src"]
    ks = [c["details"]["strike_price"] for c in cs]
    assert snap["flip"] not in (min(ks), max(ks))
    # el resto del libro SIGUE medido: no se tira el simbolo por no tener flip
    assert snap["net_gex"] is not None and snap["put_wall"] is not None
    assert snap["abs_wall_kind"] is None       # sin flip no se afirma pin ni trampilla


def test_flip_medido_se_publica_con_su_procedencia(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = []
    for i in range(20):
        k = 90.0 + i
        cs.append(_call(k, oi=1500 if k > 100 else 200, iv=0.35 + i * 0.005))
        cs.append(_put(k, oi=1500 if k < 100 else 200, iv=0.36 + i * 0.005))
    _chain(tmp_path, "QQQ", cs, spot=100.0)
    snap, why = gs.snapshot_sym("QQQ")
    assert why is None, why
    assert snap["flip"] is not None
    assert snap["flip_src"].startswith("recompute")
    assert snap["flip_dist_pct"] is not None


def test_net_gex_publica_tambien_la_escala_de_los_referees(gs, tmp_path, monkeypatch):
    """net_gex va en escala de la casa (x spot); el mundo cita $/1% (x spot^2/100). Sin
    el segundo campo la comparacion con CBOE/TradingFlow sale ~7x corta — la mitad del
    "13x por debajo" del 2026-07-26 era esto, no falta de datos."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = [_call(90.0 + i, iv=0.3 + i * 0.01) for i in range(12)]
    cs += [_put(90.0 + i, iv=0.31 + i * 0.01) for i in range(12)]
    _chain(tmp_path, "SPY", cs, spot=100.0)
    snap, why = gs.snapshot_sym("SPY")
    assert why is None, why
    assert snap["net_gex_dollar1pct"] == pytest.approx(snap["net_gex"] * 100.0 * 0.01)
    assert (snap["net_gex_dollar1pct"] < 0) == (snap["net_gex"] < 0)


def test_denominador_de_griegas_son_los_candidatos_con_OI(gs, tmp_path, monkeypatch):
    """Con banda +-60% medio fichero tiene OI=0: contarlo en el denominador hundia el
    porcentaje y omitia simbolos con el libro perfecto."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = [_call(90.0 + i, iv=0.3 + i * 0.01) for i in range(12)]
    cs += [_put(90.0 + i, iv=0.31 + i * 0.01) for i in range(12)]
    cs += [_call(300.0 + i, oi=0) for i in range(200)]      # alas sin OI: no son candidatos
    p = _chain(tmp_path, "MU", cs, spot=100.0)
    _, _, _, n_cand = gs.contracts_from(str(p))
    assert n_cand == 24
    snap, why = gs.snapshot_sym("MU")
    assert why is None, why
    assert snap["greeks_ok_pct"] == 1.0
