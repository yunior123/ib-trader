"""Tests de HONESTIDAD DE CADENA — features minadas #5 chain-honesty, #6 flip-honesty
y #13 next-day-map roll-off (2026-07-25).

Lo que estos tests defienden, con lo que se medio ese dia:
  - En RTH el cache TWS trae griegas en el 100% de las filas (QQQ 80/80, NVDA 40/40 a las
    10:00/12:00/14:00/15:30 de data/history/2026-07-24). A las 16:16, tras el cierre, TODAS
    las filas vienen iv=-1 delta=-1 gamma=-1 y bid/ask=-1.
  - Antes de la feature #5 ese caso caia en `iv=0.3` y se publicaban muros, flip y regimen
    como si fueran medidos. Los planes de las 04:00 leen justamente esa foto.
  - El unico filtro de vencimiento era `exp >= hoy`, asi que el contrato que vencia HOY
    seguia contando de 16:00 a 23:59 y desaparecia a las 00:00:00 -> los muros de la flota
    SALTABAN a medianoche (MANADA a las 00:00:45).
"""
import datetime as dt
import json
import math
import os
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core as G           # noqa: E402


# ---------------------------------------------------------------- utilidades
def _weekday_1100():
    """Epoch de un dia de semana a las 11:00 locales (= ET, reloj de la casa). Los tests de
    inversion de IV necesitan estar DENTRO de RTH: fuera de RTH la inversion esta prohibida
    a proposito (bid/ask valen -1 y el mid seria una mentira convincente)."""
    d = dt.date.today()
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return time.mktime(dt.datetime.combine(d, dt.time(11, 0)).timetuple())


def _saturday_1100():
    d = dt.date.today()
    while d.weekday() != 5:
        d += dt.timedelta(days=1)
    return time.mktime(dt.datetime.combine(d, dt.time(11, 0)).timetuple())


def _chain_file(tmp_path, rows, spot, epoch, exps, name="opt_chain_x.txt"):
    """Escribe una cadena con el formato POSICIONAL de produccion
    (# strike right exp bid ask vol oi iv delta gamma)."""
    p = tmp_path / name
    body = [f"# opt_chain X | epoch {int(epoch)} | ts | spot {spot:.2f} | exps {' '.join(exps)}",
            "# strike right exp bid ask vol oi iv delta gamma"]
    body += rows
    p.write_text("\n".join(body) + "\n")
    return str(p)


def _row(k, right, exp, bid, ask, oi, iv, gamma, vol=100):
    return (f"{k:.2f} {right} {exp} {bid:.2f} {ask:.2f} {vol:.0f} {oi:.0f} "
            f"{iv:.4f} -1.0000 {gamma:.6f}")


# ============================================ 1. inversion de IV: ida y vuelta
@pytest.mark.parametrize("iv", [0.08, 0.1234, 0.25, 0.60, 1.35])
@pytest.mark.parametrize("cp", ["C", "P"])
def test_iv_inversion_recupera_la_sigma(iv, cp):
    """precio BS -> invertir -> recupera la sigma de entrada (tolerancia 1e-4)."""
    S, K, T = 100.0, 103.0, 0.0821
    px = G.bs_price(S, K, T, iv, cp)
    back = G.implied_vol(px, S, K, T, cp)
    assert back is not None
    assert abs(back - iv) < 1e-4


def test_iv_inversion_devuelve_None_no_un_default():
    """Lo que NO se puede invertir vale None. Jamas 0, 0.3, 0.5 ni 50."""
    assert G.implied_vol(0.0, 100, 100, 0.1) is None          # precio nulo
    assert G.implied_vol(1.0, 100, 100, 0.0) is None          # sin tiempo
    assert G.implied_vol(1.0, 100, 100, -0.1) is None         # T negativo
    assert G.implied_vol(1.0, 130, 100, 0.1, "C") is None     # por debajo del intrinseco
    assert G.implied_vol(99.0, 100, 100, 0.1, "C") is None    # fuera del bracket (IV>500%)
    assert G.implied_vol(None, 100, 100, 0.1) is None
    assert G.implied_vol(1.0, 0, 100, 0.1) is None             # sin spot


def test_forward_por_paridad_put_call():
    """F = K + (C-P)e^{rT}: con precios generados desde el mismo S/iv la paridad debe
    devolver EXACTAMENTE el forward S·e^{rT}."""
    S, K, T, iv = 250.0, 245.0, 0.05, 0.28
    c = G.bs_price(S, K, T, iv, "C")
    p = G.bs_price(S, K, T, iv, "P")
    F = G.forward_from_parity(c, p, K, T)
    assert F == pytest.approx(S * math.exp(G.R_FREE * T), rel=1e-9)
    assert G.forward_from_parity(None, p, K, T) is None
    assert G.forward_from_parity(c, p, K, 0.0) is None


# ================== 2. cadena con TODO a -1: o se invierte, o None. Nunca 0.
def test_cadena_sin_griegas_ni_cotizaciones_da_None_no_cero(tmp_path):
    """La foto de las 16:16: iv=-1, gamma=-1, bid=-1, ask=-1. No hay nada que invertir
    (un mid de -1 seria peor que el bug) -> gamma MUTEADA, no un numero derivado de 0.3."""
    now = _weekday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(now + 3 * 86400))
    rows = [_row(k, r, exp, -1, -1, 500, -1, -1)
            for k in (98.0, 99.0, 100.0, 101.0, 102.0) for r in ("C", "P")]
    path = _chain_file(tmp_path, rows, 100.0, now, [exp])
    out = G.from_ibkr_cache(path, 100.0, now=now)

    assert out is not None
    assert out["gamma_ok"] is False
    assert out["greeks_ok_pct"] == 0.0
    for k in ("net_gex", "flip", "flip_open" if "flip_open" in out else "flip_static",
              "call_wall", "put_wall", "abs_wall", "em", "iv_atm", "gross_gex", "hhi"):
        assert out[k] is None, f"{k} deberia ser None y vale {out[k]!r}"
    assert out["regime"] is None
    # el cero plausible prohibido por ~/CLAUDE.md
    assert out["net_gex"] != 0 and out["net_gex"] != 0.0
    assert out["degraded_reason"]
    # el OI SI es dato real y no necesita griegas: los muros por OI sobreviven
    assert out["oi_call_wall"] is not None
    assert out["oi_put_wall"] is not None


def test_inversion_rescata_la_cadena_cuando_hay_mid_en_rth(tmp_path):
    """Mismo caso pero con bid/ask REALES en RTH: la IV se invierte del mid, el perfil se
    reconstruye y el mapa vuelve a ser publicable — con `iv_source='inverted'` visible."""
    now = _weekday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(now + 3 * 86400))
    T = G._T_of(exp, now)
    spot, iv_true = 100.0, 0.27
    rows = []
    for k in (97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0):
        for r in ("C", "P"):
            px = G.bs_price(spot, k, T, iv_true, r)
            rows.append(_row(k, r, exp, px * 0.995, px * 1.005, 500, -1, -1))
    path = _chain_file(tmp_path, rows, spot, now, [exp])
    out = G.from_ibkr_cache(path, spot, now=now)

    assert out["gamma_ok"] is True
    assert out["greeks_ok_pct"] == 1.0
    assert out["iv_source"] == "inverted"
    assert out["n_iv_inverted"] == len(rows)
    assert out["iv_inv_stats"]["forward_paridad"] == len(rows)
    assert out["iv_atm"] == pytest.approx(iv_true, abs=2e-3)   # el mid lleva 0.5% de spread
    assert out["net_gex"] is not None
    assert out["em"] > 0


def test_fuera_de_rth_no_se_invierte_aunque_haya_mid(tmp_path):
    """Guarda explicita: a las 11:00 del SABADO los precios del fichero son del cierre del
    viernes. No se inventa una IV "de ahora" a partir de ellos."""
    sat = _saturday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(sat + 3 * 86400))
    T = G._T_of(exp, sat)
    rows = []
    for k in (99.0, 100.0, 101.0):
        for r in ("C", "P"):
            px = G.bs_price(100.0, k, T, 0.3, r)
            rows.append(_row(k, r, exp, px * 0.99, px * 1.01, 500, -1, -1))
    path = _chain_file(tmp_path, rows, 100.0, sat, [exp])
    out = G.from_ibkr_cache(path, 100.0, now=sat)
    assert out["gamma_ok"] is False
    assert out["n_iv_inverted"] == 0
    assert out["quotes_ok"] is False
    assert out["net_gex"] is None


# ==================================== 3. greeks_ok_pct en cadena mitad y mitad
def test_greeks_ok_pct_en_cadena_mitad_buena_mitad_ausente(tmp_path):
    """8 contratos con gamma medida + 8 sin nada invertible = 0.5 exacto. Y 0.5 NO es
    suficiente por si solo: el umbral es `< MIN_GREEKS_OK` para mutear, asi que 0.5 pasa."""
    now = _weekday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(now + 5 * 86400))
    buenos = [_row(k, r, exp, -1, -1, 400, 0.30, 0.05)
              for k in (99.0, 100.0, 101.0, 102.0) for r in ("C", "P")]
    malos = [_row(k, r, exp, -1, -1, 400, -1, -1)
             for k in (97.0, 97.5, 98.0, 98.5) for r in ("C", "P")]
    path = _chain_file(tmp_path, buenos + malos, 100.0, now, [exp])
    out = G.from_ibkr_cache(path, 100.0, now=now)
    assert out["n_candidates"] == 16
    assert out["n_gamma_ok"] == 8
    assert out["n_no_greeks"] == 8
    assert out["greeks_ok_pct"] == pytest.approx(0.5)
    assert out["gamma_ok"] is True                    # 0.5 no es "< 0.5"

    # un contrato bueno menos -> 7/16 = 0.4375 < 0.5 -> MUTEADO
    path2 = _chain_file(tmp_path, buenos[1:] + malos, 100.0, now, [exp], "opt_chain_y.txt")
    out2 = G.from_ibkr_cache(path2, 100.0, now=now)
    assert out2["greeks_ok_pct"] < G.MIN_GREEKS_OK
    assert out2["gamma_ok"] is False
    assert out2["net_gex"] is None


def test_cabecera_de_cadena_se_publica(tmp_path):
    """La cabecera honesta: banda usada, nº de vencimientos, edad del snapshot, fuente."""
    now = _weekday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(now + 5 * 86400))
    rows = [_row(k, r, exp, -1, -1, 400, 0.3, 0.04)
            for k in (99.0, 100.0, 101.0) for r in ("C", "P")]
    path = _chain_file(tmp_path, rows, 100.0, now - 600, [exp])
    out = G.from_ibkr_cache(path, 100.0, now=now)
    assert out["chain_age_s"] == pytest.approx(600, abs=1)
    assert out["band_used"] == 0.035
    assert out["n_expiries"] == 1
    assert out["rows_total"] == 6
    assert out["chain_src"] == "ibkr_tws"
    assert out["session"] == "rth"
    hdr = G.parse_chain_header(path)
    assert hdr["spot"] == 100.0 and hdr["exps"] == [exp]


def test_cadena_rancia_en_rth_es_emergencia(tmp_path):
    """>45 min de edad DENTRO de RTH = el daemon del cache esta muerto -> mutear.
    (Fuera de RTH la misma edad es normal: el libro del cierre es el libro correcto.)"""
    now = _weekday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(now + 5 * 86400))
    rows = [_row(k, r, exp, -1, -1, 400, 0.3, 0.04)
            for k in (99.0, 100.0, 101.0) for r in ("C", "P")]
    path = _chain_file(tmp_path, rows, 100.0, now - 3 * 3600, [exp])
    out = G.from_ibkr_cache(path, 100.0, now=now)
    assert out["stale"] is True
    assert out["gamma_ok"] is False
    assert "rancia" in out["degraded_reason"]
    assert out["stale_reason"]


# =============================== 8. ROLL-OFF: el vencimiento rueda EN EL CIERRE
def test_expiry_rueda_en_el_cierre_no_a_medianoche():
    """El bug de MANADA de las 00:00:45. `exp_status` es la unica fuente de verdad."""
    hoy = dt.date.today()
    e_hoy = hoy.strftime("%Y%m%d")
    e_manana = (hoy + dt.timedelta(days=3)).strftime("%Y%m%d")
    e_ayer = (hoy - dt.timedelta(days=1)).strftime("%Y%m%d")
    t = lambda h, m: time.mktime(dt.datetime.combine(hoy, dt.time(h, m)).timetuple())

    assert G.exp_status(e_hoy, t(15, 59)) == "vivo"          # antes del cierre: cuenta
    assert G.exp_status(e_hoy, t(16, 0)) == "vencido_hoy"     # al cierre: deja de existir
    assert G.exp_status(e_hoy, t(23, 59)) == "vencido_hoy"    # NO espera a medianoche
    assert G.exp_status(e_manana, t(23, 59)) == "vivo"
    assert G.exp_status(e_ayer, t(10, 0)) == "expirado"


def test_el_mapa_usa_el_expiry_VIVO_cuando_el_frontal_ya_vencio(tmp_path):
    """Cadena con el vencimiento de HOY + el siguiente. A las 15:00 el mapa es del de hoy;
    a las 16:30 rueda al siguiente Y lo DICE (`exp_rolled`, `roll_reason`)."""
    hoy = dt.date.today()
    while hoy.weekday() >= 5:                    # necesitamos RTH para el tramo de las 15:00
        hoy += dt.timedelta(days=1)
    e0 = hoy.strftime("%Y%m%d")
    e1 = (hoy + dt.timedelta(days=7)).strftime("%Y%m%d")
    t = lambda h, m: time.mktime(dt.datetime.combine(hoy, dt.time(h, m)).timetuple())
    rows = []
    for e in (e0, e1):
        for k in (99.0, 100.0, 101.0):
            for r in ("C", "P"):
                rows.append(_row(k, r, e, -1, -1, 700 if e == e0 else 300, 0.30, 0.05))
    path = _chain_file(tmp_path, rows, 100.0, t(14, 55), [e0, e1])

    antes = G.from_ibkr_cache(path, 100.0, now=t(15, 0))
    assert antes["exp"] == e0
    assert antes["exp_rolled"] is False
    assert antes["gamma_ok"] is True

    # misma foto, 90 minutos despues: el frontal ya no existe
    despues = G.from_ibkr_cache(path, 100.0, now=t(16, 30))
    assert despues["exp"] == e1
    assert despues["exp_rolled"] is True
    assert e0 in despues["roll_reason"] and e1 in despues["roll_reason"]
    # y el mapa cambia porque cambia el LIBRO, no porque el reloj pasara de las 23:59
    assert despues["n_candidates"] == 6

    # medianoche: MISMO resultado que a las 16:30 -> no hay salto de medianoche
    manana = t(0, 5) + 86400
    tras_medianoche = G.from_ibkr_cache(path, 100.0, now=manana)
    assert tras_medianoche["exp"] == e1


def test_cadena_entera_vencida_no_inventa_niveles(tmp_path):
    """Todos los contratos expirados -> None en todo, motivo nombrado, sin ceros."""
    hoy = dt.date.today()
    e = (hoy - dt.timedelta(days=2)).strftime("%Y%m%d")
    rows = [_row(k, r, e, -1, -1, 900, 0.3, 0.05)
            for k in (99.0, 100.0, 101.0) for r in ("C", "P")]
    path = _chain_file(tmp_path, rows, 100.0, time.time(), [e])
    out = G.from_ibkr_cache(path, 100.0)
    assert out["gamma_ok"] is False
    assert out["net_gex"] is None
    assert out["exp_rolled"] is True
    assert "muertos" in out["degraded_reason"]


# ================================================ 6/7. flip: raices y congelacion
def _perfil_asimetrico():
    """Libro sintetico ASIMETRICO (puts pesados abajo, calls arriba) = el del autotest de
    gex_core. Un solo cruce, pero sirve para el contrato de claves."""
    demo = []
    for k in range(90, 111):
        demo.append({"strike": float(k), "right": "C", "oi": 400.0 * max(0, k - 100),
                     "gamma": 0.03, "iv": 0.30, "T": 0.02})
        demo.append({"strike": float(k), "right": "P", "oi": 300.0 * max(0, 100 - k),
                     "gamma": 0.03, "iv": 0.30, "T": 0.02})
    return demo


def test_flip_devuelve_TODAS_las_raices_ordenadas_por_cercania():
    """`_flip` daba UNA raiz y se quedaba tan ancho. Con tres cruces reales, la segunda
    por debajo del spot es la TRAMPILLA y hasta hoy se tiraba."""
    prof = {90.0: 5.0, 95.0: -12.0, 100.0: 14.0, 105.0: -20.0}
    roots = G._flip_roots(prof, spot=100.0)
    assert len(roots) == 3, f"tres cruces esperados, salieron {roots}"
    assert roots == sorted(roots, key=lambda r: abs(r - 100.0))
    assert G._flip(prof) in roots        # la unica raiz del contrato viejo es una de estas
    assert G._flip_roots({}, 100.0) == []
    assert G._flip_roots({90.0: 3.0, 95.0: 1.0}, 100.0) == []   # sin cruce, sin raices


def test_build_gex_publica_las_raices():
    g = G.build_gex(_perfil_asimetrico(), 100.0)
    assert isinstance(g["roots"], list)
    assert g["flip"] in g["roots"] or g["roots"] == []
    assert g["flip_static"] is not None


def test_trapdoor_root_exige_escala():
    roots = [104.0, 97.0, 80.0]
    assert G.trapdoor_root(roots, 100.0, em=5.0) == 97.0     # dentro de 1x em
    assert G.trapdoor_root(roots, 100.0, em=1.0) is None     # ninguna lo bastante cerca
    assert G.trapdoor_root(roots, 100.0, em=None) is None    # sin em no se inventa umbral
    assert G.trapdoor_root([], 100.0, em=5.0) is None


def test_flip_open_no_se_mueve_con_el_spot_pero_flip_live_si(tmp_path, monkeypatch):
    """Feature #6: `flip_open` congelado a las 09:35 no cambia intradia; `flip_live` si.
    Un nivel que no puede oscilar no puede dar falsas alarmas."""
    import chart_levels as CL
    monkeypatch.setattr(CL, "OUT", str(tmp_path))

    hoy = time.strftime("%Y-%m-%d")
    # ya congelado hoy -> se mantiene aunque el flip vivo se haya ido a otro sitio
    (tmp_path / "levels_qqq.json").write_text(json.dumps(
        {"flip_open": 660.0, "frozen_day": hoy, "frozen_at": 1}))
    prev_open, prev_day, _at = CL._frozen_flip("qqq")
    assert (prev_open, prev_day) == (660.0, hoy)
    assert CL.freeze_decision(699.0, prev_open, prev_day, hoy, 15 * 60, True) == (660.0, False)

    # sin congelar aun: a las 09:34 NO se congela; a las 09:35 si
    assert CL.freeze_decision(699.0, None, None, hoy, CL.FREEZE_MIN - 1, True) == (None, False)
    assert CL.freeze_decision(699.0, None, None, hoy, CL.FREEZE_MIN, True) == (699.0, True)
    # fin de semana: no hay apertura que congelar
    assert CL.freeze_decision(699.0, None, None, hoy, 12 * 60, False) == (None, False)
    # dia nuevo: el congelado de ayer NO se hereda
    assert CL.freeze_decision(701.0, 660.0, "1999-01-01", hoy, 12 * 60, True) == (701.0, True)
    # sin flip vivo no se congela nada
    assert CL.freeze_decision(None, None, None, hoy, 12 * 60, True) == (None, False)


def test_flip_repriced_gana_y_lo_declara(tmp_path):
    """Antes se pagaba `flip_recompute` y se SOBREESCRIBIA con el estatico, en silencio.
    Ahora el repreciado gana cuando existe y `flip_src` lo dice."""
    now = _weekday_1100()
    exp = time.strftime("%Y%m%d", time.localtime(now + 5 * 86400))
    rows = []
    # OI asimetrico: puts pesados abajo, calls arriba (si no, el perfil neto es 0 en todos
    # los strikes y no hay raiz que repreciar).
    for i, k in enumerate((97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0)):
        iv = 0.20 + 0.02 * i
        rows.append(_row(k, "C", exp, -1, -1, 100 + 400 * i, iv, -1))
        rows.append(_row(k, "P", exp, -1, -1, 2500 - 400 * i, iv, -1))
    path = _chain_file(tmp_path, rows, 100.0, now, [exp])
    out = G.from_ibkr_cache(path, 100.0, now=now)
    assert out["flip_src"] == "repriced"
    assert out["flip"] == out["flip_recompute"]
    assert out["flip_why"]


# ================================================= 9. escritura ATOMICA del mapa
def test_escritura_atomica_ningun_lector_ve_json_invalido(tmp_path, monkeypatch):
    """./compass lee charts/data/levels_<sym>.json cada 0.25 s. Con json.dump directo sobre
    el destino un lector podia leer JSON TRUNCADO. Aqui se escribe 60 veces mientras se lee
    en bucle: cada lectura que abra el fichero DEBE parsear."""
    import chart_levels as CL
    monkeypatch.setattr(CL, "OUT", str(tmp_path))
    dst = tmp_path / "levels_zz.json"
    payload = {"sym": "ZZ", "profile": [{"strike": i, "gex": i * 1.5} for i in range(400)]}
    dst.write_text(json.dumps(payload))

    fallos, parado = [], threading.Event()

    def escritor():
        for i in range(60):
            payload["asof"] = i
            tmp = str(dst) + f".tmp{os.getpid()}"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=1)
            os.replace(tmp, str(dst))
        parado.set()

    th = threading.Thread(target=escritor)
    th.start()
    lecturas = 0
    while not parado.is_set() or lecturas < 50:
        try:
            with open(dst) as f:
                json.load(f)
            lecturas += 1
        except ValueError as e:
            fallos.append(str(e))
        except OSError:
            pass
        if lecturas > 4000:
            break
    th.join()
    assert not fallos, f"{len(fallos)} lecturas vieron JSON invalido: {fallos[:2]}"
    assert lecturas >= 50
    # y el generador real usa os.replace, no json.dump al destino
    src = open(os.path.join(REPO, "scripts", "chart_levels.py")).read()
    assert "os.replace(tmp, dst)" in src


# ============================================== 10. CONTRATO de build_gex / levels
CLAVES_PREVIAS_BUILD_GEX = {
    "profile", "call_gex", "put_gex", "net_gex", "regime", "flip", "flip_static",
    "flip_recompute", "spot", "scale", "call_wall", "put_wall", "abs_wall",
    "oi_call_wall", "oi_put_wall",
    "call_wall_net", "call_wall_regime", "call_wall_kind",
    "put_wall_net", "put_wall_regime", "put_wall_kind",
    "abs_wall_net", "abs_wall_regime", "abs_wall_kind",
}


def test_contrato_build_gex_conserva_todas_las_claves():
    g = G.build_gex(_perfil_asimetrico(), 100.0)
    faltan = CLAVES_PREVIAS_BUILD_GEX - set(g)
    assert not faltan, f"build_gex perdio claves que ya consumia alguien: {faltan}"


CLAVES_PREVIAS_LEVELS = {
    "sym", "spot", "asof", "exp", "dte", "scope", "net_vex", "vex_peak", "vex_profile",
    "pressure", "pressure_lab", "iv_atm", "em", "net_gex", "regime", "flip", "flip_static",
    "call_wall", "put_wall", "abs_wall", "poc_dom", "call_wall_gex", "put_wall_gex",
    "abs_wall_gex", "oi_call_wall", "oi_put_wall", "near_call_wall", "near_put_wall",
    "near_flip", "profile", "call_wall_kind", "call_wall_regime", "call_wall_net",
    "put_wall_kind", "put_wall_regime", "put_wall_net",
    "abs_wall_kind", "abs_wall_regime", "abs_wall_net",
}


def test_contrato_levels_json_solo_crece():
    """./compass (C++, cada 0.25 s), chart_bridge.py, fleet_consensus.{py,cpp} leen este
    JSON por nombre de clave. Se AÑADE, no se renombra ni se quita."""
    import chart_levels as CL
    for sym in ("qqq", "nok", "spy", "nvda"):
        p = os.path.join(REPO, CL.OUT, f"levels_{sym}.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        faltan = CLAVES_PREVIAS_LEVELS - set(d)
        assert not faltan, f"levels_{sym}.json perdio claves: {faltan}"
        # y la cabecera de honestidad esta presente
        for k in ("gamma_ok", "greeks_ok_pct", "chain_src", "flip_live", "flip_src",
                  "flip_open", "roots", "exp_rolled", "band_used", "n_expiries"):
            assert k in d, f"levels_{sym}.json sin la clave de honestidad {k}"


def test_gamma_muteada_nunca_publica_un_cero_en_levels():
    """Si gamma_ok es false, las claves gamma del JSON son null. Un 0 ahi seria leido como
    'regimen neutro medido' por la brujula."""
    import chart_levels as CL
    for sym in ("qqq", "nok", "spy", "nvda", "mu"):
        p = os.path.join(REPO, CL.OUT, f"levels_{sym}.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        if d.get("gamma_ok"):
            continue
        for k in ("net_gex", "flip", "call_wall", "put_wall", "abs_wall", "pressure",
                  "em", "iv_atm", "gross_gex", "hhi", "bifurcation"):
            assert d.get(k) is None, f"levels_{sym}.json muteado pero {k}={d.get(k)!r}"
