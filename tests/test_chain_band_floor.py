"""BAND_FLOOR: la cadena IBKR debe cruzar el suelo de ancho por si sola.

Medido el 2026-08-02 sobre data/opt_chain_*.txt: META 0.0247, MSFT 0.0296, AVGO 0.0354,
AMZN 0.0507 — los 4 NARROW por debajo de BAND_FLOOR (0.10), asi que chart_levels._map_insuficiente
DESCARTABA siempre su cadena TWS (griegas 100%, 3 min) y el mapa se servia de Polygon (15 min).
Causa: los NARROW no tenian ola lejana (`if rest and not narrow`).

Las escaleras de strikes son REALES: data/history/2026-07-31/chain_full_<sym>.json (Polygon).
"""
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import opt_chain_cache as OC            # noqa: E402
from poly_chain_archive import BAND_FLOOR   # noqa: E402  UNA definicion, no se redefine

DAY = os.path.join(REPO, "data", "history", "2026-07-31")
OBJETIVO = 0.12          # margen sobre BAND_FLOOR: el fallo anterior fue por 0.21pp


def _ladder(sym):
    """(strikes ordenados, spot, n_exps del frontal+siguiente) de la cadena archivada."""
    p = os.path.join(DAY, f"chain_full_{sym.lower()}.json")
    if not os.path.exists(p):
        pytest.skip(f"sin cadena archivada para {sym}")
    d = json.load(open(p))
    spot = d["meta"]["spot"]
    res = d["results"]
    strikes = sorted({float(r["details"]["strike_price"]) for r in res})
    exps = sorted({r["details"]["expiration_date"] for r in res})[:2]
    return strikes, spot, len(exps)


def _half_span(ks, spot):
    return (max(ks) - min(ks)) / 2 / spot if ks else None


def _select(sym, strikes, spot):
    narrow = sym.upper() in OC.NARROW
    band = OC.NARROW_BAND if narrow else OC.PCT_BAND
    max_ks = OC.NARROW_MAX_STRIKES if narrow else OC.MAX_STRIKES
    return OC.select_strikes(strikes, spot, band, max_ks, narrow)


# ============================================ 1-2. los 4 NARROW cruzan BAND_FLOOR
@pytest.mark.parametrize("sym", ["MSFT", "META", "AVGO", "AMZN"])
def test_narrow_cruza_band_floor_con_escalera_real(sym):
    strikes, spot, _n = _ladder(sym)
    near, far = _select(sym, strikes, spot)
    assert far, f"{sym}: los NARROW deben tener ola lejana (antes era []) "
    span = _half_span(near + far, spot)
    assert span >= BAND_FLOOR, f"{sym}: half-span {span:.4f} < BAND_FLOOR {BAND_FLOOR}"
    assert span >= OBJETIVO, f"{sym}: half-span {span:.4f} sin margen sobre {OBJETIVO}"


def test_narrow_antes_del_arreglo_no_llegaba(monkeypatch):
    """Prueba de que el test 1 mide lo que dice: con far_max_ks=0 (el comportamiento viejo,
    `if rest and not narrow`) MSFT se queda en su banda ATM y NO cruza el suelo."""
    strikes, spot, _n = _ladder("MSFT")
    near, far = OC.select_strikes(strikes, spot, OC.NARROW_BAND,
                                  OC.NARROW_MAX_STRIKES, True, far_max_ks=0)
    assert far == []
    assert _half_span(near, spot) < BAND_FLOOR


# ================================= 3. regresion no-narrow: el caso QQQ 0DTE de b87067e2
def test_no_narrow_qqq_sigue_cruzando():
    strikes, spot, _n = _ladder("QQQ")
    near, far = _select("QQQ", strikes, spot)
    span = _half_span(near + far, spot)
    assert span >= BAND_FLOOR and span >= OBJETIVO, f"QQQ half-span {span:.4f}"


def test_muestreo_con_bordes_gana_al_stride_viejo():
    """El bug de b87067e2: `rest[::stride]` arrancaba en el minimo y el ultimo paso NO
    llegaba al maximo (QQQ 0DTE: 0.0979 contra BAND_FLOOR 0.10, fallaba por 0.21pp)."""
    strikes, spot, _n = _ladder("QQQ")
    near, far = _select("QQQ", strikes, spot)
    rest = sorted(set(k for k in strikes if abs(k - spot) / spot <= OC.PCT_BAND) - set(near))
    stride = max(1, len(rest) // OC.MAX_STRIKES)
    viejo = rest[::stride][:OC.MAX_STRIKES]
    assert max(far) == max(rest), "el borde alto debe entrar SIEMPRE"
    assert min(far) == min(rest), "el borde bajo debe entrar SIEMPRE"
    assert max(viejo) < max(rest), "el muestreo viejo se quedaba corto por arriba"
    assert _half_span(near + far, spot) > _half_span(near + viejo, spot)
    assert len(far) <= OC.MAX_STRIKES


# ============================================ 4. los DOS bordes siempre entran
@pytest.mark.parametrize("narrow", [True, False])
def test_los_dos_bordes_de_la_banda_estan_siempre(narrow):
    """Escalera IRREGULAR (paso denso al centro, grueso en las alas) — el muestreo debe
    conservar el minimo y el maximo de la banda lejana, que son los que fijan el span."""
    spot = 100.0
    alas_bajas = [70.0 + 2.5 * i for i in range(0, 8)]        # 70..87.5
    centro = [88.0 + 0.5 * i for i in range(0, 49)]           # 88..112
    alas_altas = [114.0 + 3.0 * i for i in range(0, 8)]       # 114..135
    strikes = sorted(set(alas_bajas + centro + alas_altas))
    band = OC.NARROW_BAND if narrow else OC.PCT_BAND
    max_ks = OC.NARROW_MAX_STRIKES if narrow else OC.MAX_STRIKES
    near, far = OC.select_strikes(strikes, spot, band, max_ks, narrow)
    far_band = OC.PCT_BAND
    pool = [k for k in strikes if abs(k - spot) / spot <= far_band]
    sel = set(near) | set(far)
    assert min(pool) in sel, f"borde bajo {min(pool)} fuera de la seleccion"
    assert max(pool) in sel, f"borde alto {max(pool)} fuera de la seleccion"
    assert _half_span(sorted(sel), spot) >= BAND_FLOOR


def test_bordes_con_pool_mas_corto_que_el_cap():
    """Si el resto cabe entero no se muestrea nada: entra tal cual. Y la ola lejana de un
    narrow se toma sobre la banda ANCHA aunque la ola ATM sea diminuta."""
    spot = 50.0
    strikes = [45.0, 47.5, 50.0, 52.5, 55.0]
    near, far = OC.select_strikes(strikes, spot, 0.02, 1, True, far_band=0.15, far_max_ks=10)
    assert near == [50.0]
    assert far == [45.0, 47.5, 52.5, 55.0]
    # sin banda lejana propia (no-narrow) el resto se queda dentro de la banda ATM
    assert OC.select_strikes(strikes, spot, 0.02, 1, False) == ([50.0], [])


# ============================================ 5. presupuesto de lineas TWS
@pytest.mark.parametrize("sym", ["MSFT", "META", "AVGO", "AMZN",
                                 "QQQ", "SPY", "NVDA", "NOK", "MU"])
def test_presupuesto_de_lineas_por_simbolo(sym):
    strikes, spot, n_exps = _ladder(sym)
    near, far = _select(sym, strikes, spot)
    narrow = sym in OC.NARROW
    cap = OC.NARROW_MAX_LINES_PER_EXP if narrow else OC.MAX_LINES_PER_EXP
    lineas = (len(near) + len(far)) * 2 * n_exps
    assert (len(near) + len(far)) * 2 <= cap, f"{sym}: {len(near)+len(far)} strikes > cap"
    assert lineas <= cap * n_exps
    if narrow:
        assert cap == 44 and lineas <= 88     # 12 ATM + 10 lejanos, 2 rights, 2 exps


def test_caps_declarados_coinciden_con_las_constantes():
    assert OC.NARROW_MAX_LINES_PER_EXP == 2 * (OC.NARROW_MAX_STRIKES + OC.NARROW_FAR_MAX_STRIKES)
    assert OC.MAX_LINES_PER_EXP == 2 * (OC.MAX_STRIKES + OC.MAX_STRIKES)


# ============================ 6. nada fuera de banda, nada duplicado
@pytest.mark.parametrize("sym", ["MSFT", "META", "AVGO", "AMZN", "QQQ", "SPY", "NOK"])
def test_ni_duplicados_ni_strikes_fuera_de_banda(sym):
    strikes, spot, _n = _ladder(sym)
    near, far = _select(sym, strikes, spot)
    todos = near + far
    assert len(todos) == len(set(todos)), f"{sym}: strikes duplicados"
    assert not (set(near) & set(far)), f"{sym}: near y far se solapan"
    for k in todos:
        assert abs(k - spot) / spot <= OC.PCT_BAND + 1e-12, f"{sym}: {k} fuera de ±15%"
        assert k in set(strikes)
    for k in near:
        band = OC.NARROW_BAND if sym in OC.NARROW else OC.PCT_BAND
        assert abs(k - spot) / spot <= band + 1e-12, f"{sym}: near {k} fuera de la banda ATM"


def test_select_strikes_degrada_sin_inventar():
    assert OC.select_strikes([], 100.0, 0.15, 20, False) == ([], [])
    assert OC.select_strikes([100.0], None, 0.15, 20, False) == ([], [])
    assert OC.select_strikes([100.0], 0.0, 0.15, 20, False) == ([], [])
    # spot fuera de toda la escalera: nada en banda, y no se rellena con lo mas cercano
    assert OC.select_strikes([10.0, 11.0], 100.0, 0.15, 20, False) == ([], [])


def test_near_son_los_mas_cercanos_al_atm():
    spot = 100.0
    strikes = [float(k) for k in range(90, 111)]
    near, _far = OC.select_strikes(strikes, spot, 0.15, 5, False)
    assert near == [98.0, 99.0, 100.0, 101.0, 102.0]


# ==================== 7. punta a punta: el gate de chart_levels deja de rechazar
def _fila(k, right, exp, iv=0.30, gamma=0.05, oi=500):
    return f"{k:.2f} {right} {exp} 1.00 1.10 100 {oi} {iv:.4f} -1.0000 {gamma:.6f}"


@pytest.mark.parametrize("sym", ["MSFT", "META", "AVGO", "AMZN"])
def test_cadena_construida_con_la_seleccion_nueva_pasa_el_gate(sym, tmp_path):
    """Se escribe un opt_chain_<sym>.txt con el formato de produccion usando la seleccion
    NUEVA sobre la escalera real, y se comprueba que gex_core.from_ibkr_cache publica
    strike_span_pct >= BAND_FLOOR (que es lo que mira chart_levels._map_insuficiente)."""
    import datetime as dt
    import time

    import gex_core as G

    strikes, spot, _n = _ladder(sym)
    near, far = _select(sym, strikes, spot)
    ks = sorted(set(near + far))

    d = dt.date.today()
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    now = time.mktime(dt.datetime.combine(d, dt.time(11, 0)).timetuple())
    exp = time.strftime("%Y%m%d", time.localtime(now + 3 * 86400))

    atm_band = OC.NARROW_BAND if sym in OC.NARROW else OC.PCT_BAND
    band = OC.PCT_BAND                       # banda EXTERIOR: la que gex_core usa de filtro
    max_ks = OC.NARROW_MAX_STRIKES if sym in OC.NARROW else OC.MAX_STRIKES
    rows = [_fila(k, r, exp) for k in ks for r in ("C", "P")]
    span = _half_span(ks, spot)
    p = tmp_path / f"opt_chain_{sym.lower()}.txt"
    p.write_text(
        f"# opt_chain {sym} | epoch {int(now)} | ts | spot {spot:.2f} | exps {exp}\n"
        f"# fuente ibkr_tws | band {band:.4f} | max_strikes {max_ks} | narrow 1 | "
        f"vencimientos 1 | rows {len(rows)} | greeks_ok_pct 1.0000 | "
        f"bidask_ok_pct 1.0000 | band_atm {atm_band:.4f} | "
        f"far_max_strikes {OC.NARROW_FAR_MAX_STRIKES} | span_pct {span:.4f}\n"
        "# strike right exp bid ask vol oi iv delta gamma\n"
        + "\n".join(rows) + "\n")

    out = G.from_ibkr_cache(str(p), spot, now=now)
    assert out["gamma_ok"] is True
    assert out["strike_span_pct"] >= BAND_FLOOR, \
        f"{sym}: strike_span_pct {out['strike_span_pct']:.4f} < {BAND_FLOOR}"
    assert out["strike_span_pct"] >= OBJETIVO
    # y la cabecera nueva sigue siendo parseable sin romper los campos previos
    hdr = G.parse_chain_header(str(p))
    assert hdr["spot"] == pytest.approx(spot) and hdr["exps"] == [exp]
    assert hdr["band"] == pytest.approx(band) and hdr["max_strikes"] == max_ks
    assert hdr["greeks_ok_pct"] == 1.0
