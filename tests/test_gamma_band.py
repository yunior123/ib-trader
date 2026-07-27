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
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gex_core as G  # noqa: E402


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


def _chain_txt(tmp_path, sym, filas, spot, band):
    """Cadena en formato de PRODUCCION (el que lee gex_core.from_ibkr_cache / chart_levels)."""
    import time
    exp = (dt.date.today() + dt.timedelta(days=4)).strftime("%Y%m%d")
    p = tmp_path / f"opt_chain_{sym.lower()}.txt"
    ln = [f"# opt_chain {sym.upper()} | epoch {time.time():.0f} | spot {spot:.2f} | exps {exp}",
          f"# fuente polygon_snapshot_v3 | band {band:.4f} vencimientos 1"]
    for k, right, oi, iv, gamma in filas:
        ln.append(f"{k:.2f} {right} {exp} -1.00 -1.00 -1 {oi} {iv:.4f} 0.50 {gamma:.6f}")
    p.write_text("\n".join(ln) + "\n")
    return str(p)


def test_camino_VIVO_libro_sin_cruce_publica_flip_None_no_el_borde(tmp_path):
    """El MISMO defecto que `honest_flip` arregla en el lote, pero en el camino que leen el
    chart y ./compass: `from_ibkr_cache` -> `build_gex` -> `_flip`.

    Medido el 2026-07-27 sobre las cadenas archivadas del 26: EWY publicaba flip 260,0 con
    spot 163,49 (banda 0,6 -> borde 261,58: a 0,97 pp) y SNDK 2300,0 con spot 1440,88
    (borde 2305,41: 0,38 pp). Los dos son el techo del recorte, no un nivel; y de ahi salen
    los tres `*_kind` = trampilla, que es VETO DURO (compass.cpp:630, book_quality:317)."""
    spot, band = 100.0, 0.6
    # todo puts con IV DISPERSA: el barrido se ejecuta (>=3 IVs) y no encuentra raiz,
    # asi que la decision recae en el estatico -- que es donde vivia el borde.
    filas = [(60.0 + 2 * i, "P", 900, 0.30 + 0.01 * i, 0.02) for i in range(40)]
    g = G.from_ibkr_cache(_chain_txt(tmp_path, "EWY", filas, spot, band), spot)
    assert g["gamma_ok"] is True and g["net_gex"] < 0
    ks = sorted(g["profile"])
    assert g["flip_static"] is None, "el estatico volvio a devolver el extremo del rango"
    assert g["flip"] is None and g["flip_src"] == "none"
    assert g["flip"] not in (ks[0], ks[-1])
    assert g["roots"] == []
    for key in ("call_wall", "put_wall", "abs_wall"):
        assert g[key + "_kind"] is None, f"{key}: pin/trampilla afirmado sin flip"
    # el resto del libro SIGUE medido: no se tira el simbolo por no tener flip
    assert g["put_wall"] is not None and g["oi_put_wall"] is not None


def test_camino_VIVO_con_cruce_real_el_flip_sigue_saliendo(tmp_path):
    """El fix no puede comerse el flip de un libro normal."""
    spot, band = 100.0, 0.6
    filas = []
    for i in range(30):
        k = 85.0 + i
        filas.append((k, "C", 1500 if k > 100 else 150, 0.30 + 0.005 * i, 0.02))
        filas.append((k, "P", 1500 if k < 100 else 150, 0.31 + 0.005 * i, 0.02))
    g = G.from_ibkr_cache(_chain_txt(tmp_path, "QQQ", filas, spot, band), spot)
    assert g["flip"] is not None and g["flip_src"] == "repriced"
    assert g["abs_wall_kind"] in ("pin", "trampilla")


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


# ------------------- coherencia de PARIDAD: gamma_call == gamma_put al mismo (K,exp)
def _pc(k, right, gamma, oi=1000, exp="20260821"):
    return {"strike": k, "right": right, "gamma": gamma, "oi": oi, "exp": exp, "iv": 0.3,
            "T": 0.07}


def test_paridad_no_toca_un_libro_COHERENTE():
    """Con gamma_C == gamma_P las dos lecturas legales son la misma: reparar es un no-op.
    Medido: CBOE cumple la paridad en el 72-78% de sus pares y el neto se mueve <3%."""
    cs = []
    for i in range(12):
        k = 90.0 + i
        g = 0.02 + 0.001 * i
        cs += [_pc(k, "C", g, oi=1500 if k > 100 else 200), _pc(k, "P", g, oi=1500 if k < 100 else 200)]
    p = G.parity_audit(cs, 100.0)
    assert p["parity_ok_pct"] == 1.0
    assert p["net_parity_lo"] == pytest.approx(p["net_parity_hi"])
    assert p["signo_firme"] is True and p["regime_parity"] in ("POS", "NEG")


def test_paridad_CORRIGE_el_signo_cuando_las_griegas_la_violan():
    """El caso REAL de SPY el 2026-07-27 08:30: Polygon premercado cumplia la paridad en el
    2% de 927 pares (mediana gamma_C/gamma_P = 0,243) y el neto crudo salia POSITIVO cuando
    las dos lecturas legales y CBOE decian NEGATIVO. POS licencia el fade, NEG lo PROHIBE."""
    cs = []
    for i in range(12):
        k = 90.0 + i
        g = 0.02 + 0.001 * i
        # calls con gamma INFLADA x4 y puts con la real: el crudo se va a POS.
        # OI ASIMETRICO (mas puts) para que las lecturas legales sean NEG de verdad: con OI
        # simetrico reparar la paridad anula el neto y 0 NO es un signo.
        cs += [_pc(k, "C", g * 4.0, oi=600), _pc(k, "P", g, oi=1400)]
    crudo = G.build_gex(cs, 100.0, scale="dollar1pct")
    p = G.parity_audit(cs, 100.0)
    assert crudo["regime"] == "POS"                      # lo que publicabamos
    assert p["parity_ok_pct"] == 0.0
    assert p["signo_firme"] is True and p["regime_parity"] == "NEG"
    assert p["net_parity_lo"] < 0 and p["net_parity_hi"] < 0


def test_paridad_declara_INDETERMINADO_en_vez_de_elegir():
    """Si las dos lecturas legales discrepan en signo, el dato NO determina el regimen:
    None y el motivo, jamas la que quede mas bonita."""
    # Las dos lecturas legales tienen que salir con signo OPUESTO: donde el OI se carga en
    # calls la gamma alta esta en la pata call, y donde se carga en puts esta en la put ->
    # forzar el par a una pata u otra invierte el neto.
    cs = [_pc(100.0, "C", 0.05, oi=1000), _pc(100.0, "P", 0.001, oi=200),
          _pc(105.0, "C", 0.001, oi=200), _pc(105.0, "P", 0.05, oi=1000)]
    p = G.parity_audit(cs, 100.0)
    assert (p["net_parity_lo"] > 0) != (p["net_parity_hi"] > 0)
    assert p["signo_firme"] is False
    assert p["regime_parity"] is None and p["net_parity_conservador"] is None


def test_paridad_sin_un_solo_par_devuelve_None_no_un_cero():
    assert G.parity_audit([_pc(100.0, "C", 0.05)], 100.0) is None
    assert G.parity_audit([], 100.0) is None


def test_snapshot_publica_el_regimen_de_la_PARIDAD_y_dice_que_lo_cambio(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = []
    for i in range(12):
        k = 90.0 + i
        g = 0.02 + 0.001 * i
        cs.append(_call(k, oi=600, gamma=g * 4.0, iv=0.30 + 0.01 * i))
        cs.append(_put(k, oi=1400, gamma=g, iv=0.31 + 0.01 * i))
    _chain(tmp_path, "SPY", cs, spot=100.0)
    snap, why = gs.snapshot_sym("SPY")
    assert why is None, why
    assert snap["regime_raw"] == "POS" and snap["regime_short"] == "NEG"
    assert snap["regime"] == "NEGATIVE"
    assert "CONTRADICHO por la paridad" in snap["regime_why"]
    assert snap["parity_ok_pct"] == 0.0
    assert snap["net_gex_parity_lo"] < 0 and snap["net_gex_parity_hi"] < 0
    assert snap["bias"] == "PUT"          # el sesgo tambien sale de las patas reparadas


# ------------------ fuente: IBKR PRIMARIO, Polygon RESPALDO (orden Yunior 2026-07-27)
def test_ibkr_primario_solo_si_su_libro_DA_LA_TALLA(gs):
    """"IBKR primario" NO puede ser "IBKR aunque venga vacio": fuera de RTH su cadena trae 0%
    de griegas y eso apagaria la gamma de la flota entera (bug que este repo ya se comio).
    Las dos piernas del gate son constantes YA medidas del repo, no nuevas."""
    import book_quality
    assert gs.BAND_FLOOR == 0.10                       # poly_chain_archive, medido en 5a6a34e
    assert book_quality.MIN_GREEKS_SRC == 0.5          # == gex_core.MIN_GREEKS_OK
    assert book_quality.usable_greeks(0.0) is False    # el caso real de premercado
    assert book_quality.usable_greeks(None) is False   # n/d no es aprobado
    assert book_quality.usable_greeks(0.94) is True


def test_la_procedencia_del_regimen_va_DENTRO_del_dato(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = []
    for i in range(12):
        k = 90.0 + i
        cs.append(_call(k, oi=1500 if k > 100 else 200, iv=0.30 + 0.01 * i))
        cs.append(_put(k, oi=1500 if k < 100 else 200, iv=0.31 + 0.01 * i))
    _chain(tmp_path, "QQQ", cs, spot=100.0)
    snap, why = gs.snapshot_sym("QQQ")               # sin cache TWS en tmp_path -> respaldo
    assert why is None, why
    assert snap["chain_src"] and "RESPALDO" in snap["source_why"]
    assert "sin cache TWS" in snap["source_why"]
    assert snap["scope"] == "ALL"                     # el scope, declarado


def test_el_signo_lo_fija_UNA_definicion_para_los_dos_caminos(tmp_path):
    """`gex_snapshot` (lote) y `from_ibkr_cache` (vivo) publicaban regimenes OPUESTOS del mismo
    libro (QQQ NEGATIVE vs POS) porque solo el lote tenia el guardian de paridad."""
    spot, band = 100.0, 0.6
    filas = []
    for i in range(12):
        k = 90.0 + i
        g = 0.02 + 0.001 * i
        filas.append((k, "C", 1000, 0.30 + 0.01 * i, g * 4.0))   # calls con gamma inflada
        filas.append((k, "P", 1400, 0.31 + 0.01 * i, g))
    g = G.from_ibkr_cache(_chain_txt(tmp_path, "QQQ", filas, spot, band), spot,
                          scale="dollar1pct", all_exp=True)
    assert g["gamma_ok"] is True
    assert g["regime_raw"] == "POS" and g["regime"] == "NEG"
    assert "CONTRADICHO por la paridad" in g["regime_why"]
    assert g["parity_ok_pct"] == 0.0
    # y es la MISMA funcion que usa el lote
    reg, why, par = G.regime_by_parity(
        [{"strike": k, "right": r, "oi": oi, "gamma": gm, "iv": iv, "exp": "20260821", "T": 0.07}
         for k, r, oi, iv, gm in filas], spot, "POS")
    assert reg == "NEG" and par["parity_ok_pct"] == 0.0


def test_si_el_0DTE_no_firma_el_signo_lo_firma_el_LIBRO_ENTERO(tmp_path, monkeypatch):
    """Un solo vencimiento puede no tener signo firme sin que el libro deje de tenerlo, y
    `compass.cpp:824` trata el regimen vacio como S_NONE — o sea que perdia tambien el flip y
    los muros, que SI estan medidos. Hoy pasaba en QQQ, SPY e INTC (3 de 30)."""
    import chart_levels as CL
    exp0 = (dt.date.today() + dt.timedelta(days=1)).strftime("%Y%m%d")
    exp1 = (dt.date.today() + dt.timedelta(days=30)).strftime("%Y%m%d")
    spot, band = 100.0, 0.6
    ln = [f"# opt_chain ZZ | epoch {__import__('time').time():.0f} | spot {spot:.2f} | "
          f"exps {exp0} {exp1}",
          f"# fuente polygon_snapshot_v3 | band {band:.4f} vencimientos 2"]
    # 0DTE: OI simetrico -> reparar la paridad anula el neto -> signo NO firme
    for i in range(12):
        k = 94.0 + i
        for r in ("C", "P"):
            g = (0.02 + 0.001 * i) * (4.0 if r == "C" else 1.0)
            ln.append(f"{k:.2f} {r} {exp0} -1.00 -1.00 -1 1000 {0.3 + 0.01 * i:.4f} 0.50 {g:.6f}")
    # el vencimiento largo mete puts pesados: el LIBRO ENTERO si tiene signo
    for i in range(12):
        k = 94.0 + i
        ln.append(f"{k:.2f} C {exp1} -1.00 -1.00 -1 100 {0.3 + 0.01 * i:.4f} 0.50 0.020000")
        ln.append(f"{k:.2f} P {exp1} -1.00 -1.00 -1 9000 {0.31 + 0.01 * i:.4f} -0.50 0.020000")
    p = tmp_path / "opt_chain_zz.txt"
    p.write_text("\n".join(ln) + "\n")
    g0 = G.from_ibkr_cache(str(p), spot, scale="dollar1pct")
    assert g0["regime"] is None, "el fixture del 0DTE deberia salir sin signo firme"
    assert g0["call_wall"] is not None, "los muros SI estan medidos: eso es lo que no se pierde"

    monkeypatch.setattr(CL, "OUT", str(tmp_path / "out"))
    monkeypatch.setattr(CL, "poly_chain_path", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    os.replace(str(p), str(tmp_path / "data" / "opt_chain_zz.txt"))
    out = CL.gen("ZZ", write=False)
    assert out["regime"] is not None and out["regime_scope"] == "ALL"
    assert "LIBRO ENTERO" in out["regime_why"]
    assert out["call_wall"] is not None and out["put_wall"] is not None
