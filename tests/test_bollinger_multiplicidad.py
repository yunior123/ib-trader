"""Tests del VETO DE BOLLINGER — el grid que apagaba señales buenas por ruido.

Caso real que los motiva (2026-07-26)
-------------------------------------
`scripts/bollinger_complements.py` seleccionaba celdas `ticker x filtro` con
`n>=15 y |uplift|>=5pts`: un umbral de TAMAÑO DE EFECTO, sin p-valor, sin
correccion por multiplicidad y sobre la n CRUDA. El grid hace ~400 pruebas; con
tantas pruebas ese criterio publica hallazgos que el azar reproduce solo.

Las 70 celdas `veto_filters` resultantes viajan a `data/bollinger_plus.json` y
`engines/bb_engine.cpp` las aplicaba como VETO: apagaban la señal en vivo. Un
veto no es una opinion — no deja rastro auditable, porque la señal que silencia
nunca llega a existir. Daño invisible.

Lo que se prueba aqui:
  1. el criterio VIEJO publica ~110 celdas sobre RUIDO PURO (etiquetas barajadas
     dentro de cada ticker: por construccion no hay nada que descubrir);
  2. el criterio NUEVO (BH-FDR q=0.10 sobre muestra EFECTIVA, ρ̄=0.41 medida)
     publica CERO sobre ese mismo ruido;
  3. nada se publica sin `fdr_ok` + `why` dentro del propio dato;
  4. `bollinger_plus.json` (el fichero VIVO) no lo toca el script;
  5. `bb_engine` no aplica un veto sin `fdr_ok:true`, y quitar vetos solo puede
     AÑADIR señales — jamas invertir el veto (degradacion limpia).
"""
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
RESULTS = os.path.join(REPO, "data", "backtest", "bcomp_results.json")
BB_ENGINE = os.path.join(REPO, "engines", "bb_engine")


def _load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def BC():
    return _load("bollinger_complements")


@pytest.fixture(scope="module")
def reales():
    """Las señales elastic MEDIDAS de la flota (30 tickers, 30 dias)."""
    if not os.path.exists(RESULTS):
        pytest.skip("faltan las señales medidas: correr bollinger_complements.py")
    res = json.load(open(RESULTS))
    return {k: v for k, v in res.items() if not v.get("error")}


def _barajar(results, seed):
    """Rompe TODA relacion filtro->outcome barajando la etiqueta dentro de cada
    ticker. Se conservan n, tasa base y estructura de sesiones: lo unico que
    desaparece es la señal. Lo que el criterio siga 'encontrando' es ruido."""
    rnd = random.Random(seed)
    out = {}
    for sym, r in results.items():
        sigs = [dict(s) for s in r.get("signals", [])]
        for key in ("hit_mid30", "hit_half30"):
            labs = [s[key] for s in sigs]
            rnd.shuffle(labs)
            for s, lab in zip(sigs, labs):
                s[key] = lab
        out[sym] = {"signals": sigs, "n_days": r.get("n_days")}
    return out


def _viejo(grid, BC):
    """Celdas que el criterio ANTERIOR habria publicado."""
    n = 0
    for _sym, g in grid.items():
        for _f, c in g["filters"].items():
            if (c["n"] >= BC.CRITERIO_VIEJO_N and c["uplift"] is not None
                    and abs(c["uplift"]) >= BC.CRITERIO_VIEJO_UPLIFT):
                n += 1
    return n


def _nuevo(grid, BC):
    """Celdas que el criterio ACTUAL publica (BH-FDR ya aplicado en analyze)."""
    n = 0
    for _sym, g in grid.items():
        for _f, c in g["filters"].items():
            if BC.sobrevive(c)[0]:
                n += 1
    return n


# --------------------------------------------------------------------------
# 1-2. La refutacion: el criterio viejo publica ruido; el nuevo no.
# --------------------------------------------------------------------------
def test_criterio_viejo_publica_ruido_puro(BC, reales):
    """Con las etiquetas barajadas NO hay nada que descubrir, y aun asi el
    criterio `n>=15 y |uplift|>=5` publica decenas de celdas. Esa es la medida
    del daño: cada celda de esas apagaba señales en vivo."""
    encontradas = []
    for seed in range(5):
        grid, _fleet, _pooled = BC.analyze(_barajar(reales, seed))
        encontradas.append(_viejo(grid, BC))
    media = sum(encontradas) / len(encontradas)
    assert media >= 50, ("el criterio viejo deberia publicar decenas de celdas "
                         "sobre ruido puro; medido %s" % encontradas)


def test_criterio_nuevo_no_publica_nada_sobre_ruido(BC, reales):
    """El mismo ruido, por la puerta nueva: BH-FDR q=0.10 sobre muestra
    efectiva. Cero celdas. Este test FALLA con el criterio anterior."""
    for seed in range(5):
        grid, _fleet, _pooled = BC.analyze(_barajar(reales, seed))
        assert _nuevo(grid, BC) == 0, (
            "semilla %d: el criterio nuevo publico celdas sobre ruido puro" % seed)


def test_ninguna_celda_real_sobrevive_por_ticker(BC, reales):
    """Sobre los datos REALES: de las ~390 celdas ticker x filtro, ninguna pasa
    BH-FDR. Las 150 que publicaba el criterio viejo (70 veto + 80 best) caen."""
    grid, fleet, _pooled = BC.analyze(reales)
    assert _viejo(grid, BC) == 150, "el criterio viejo publicaba 150 celdas"
    assert _nuevo(grid, BC) == 0
    assert fleet["multiplicidad"]["n_sobreviven_bh"] == 0


# --------------------------------------------------------------------------
# 3-4. Higiene del dato publicado
# --------------------------------------------------------------------------
def test_la_propuesta_no_pisa_el_fichero_vivo(BC, reales, tmp_path):
    """Cambiar lo que la flota VETA hoy lo decide el lead. El script escribe
    `bollinger_plus.PROPUESTO.json` y deja intacto `bollinger_plus.json`."""
    vivo = os.path.join(REPO, "data", "bollinger_plus.json")
    antes = open(vivo, "rb").read() if os.path.exists(vivo) else None
    grid, fleet, _pooled = BC.analyze(reales)
    plus = BC.write_outputs(grid, fleet)
    despues = open(vivo, "rb").read() if os.path.exists(vivo) else None
    assert antes == despues, "el fichero VIVO no se toca desde este script"
    assert os.path.exists(os.path.join(REPO, "data", "bollinger_plus.PROPUESTO.json"))
    assert plus["_meta"]["antes_despues"]["veto_viejo"] == 70
    assert plus["_meta"]["antes_despues"]["veto_nuevo"] == 0


def test_toda_celda_publicada_lleva_fdr_ok_y_why(BC, reales):
    """Patron de data/signal_enable.json: el porqué viaja DENTRO del dato. Y una
    celda descartada explica en su `why` que no pasa BH-FDR."""
    grid, fleet, _pooled = BC.analyze(reales)
    plus = BC.write_outputs(grid, fleet)
    n_desc = 0
    for sym, g in plus.items():
        if sym.startswith("_"):
            continue
        for item in g["best_filters"] + g["veto_filters"]:
            assert item["fdr_ok"] is True and item["why"]
        for item in g["descartadas_por_multiplicidad"]:
            assert item["fdr_ok"] is False
            assert "BH-FDR" in item["why"] or "no testeable" in item["why"]
            n_desc += 1
    assert n_desc == 150


def test_n_eff_es_menor_que_n_cruda(BC, reales):
    """ρ̄=0.41 MEDIDA: varias señales de la misma sesion no son observaciones
    independientes. Si n_eff saliera == n, el Wilson seria anticonservador y
    volveriamos al bug."""
    sigs = reales["qqq"]["signals"]
    ne = BC.n_efectiva(sigs)
    assert ne is not None and ne < len(sigs)
    assert BC.n_efectiva([]) is None, "celda vacia -> None, jamas un 0 plausible"
    una = [s for s in sigs if s["date"] == sigs[0]["date"]][:1]
    assert BC.n_efectiva(una) == pytest.approx(1.0), "una sola señal: n_eff == n"


# --------------------------------------------------------------------------
# 5. El motor C++: sin fdr_ok no hay veto, y quitar vetos solo AÑADE señales
# --------------------------------------------------------------------------
def _plus_json(path, sym, fdr_ok):
    veto = {"filtro": "F6_1030", "n": 40, "p": 50.0, "uplift": -12.0,
            "wilson": [30.0, 70.0], "why": "test"}
    if fdr_ok is not None:
        veto["fdr_ok"] = fdr_ok
    json.dump({sym: {"base": {"n": 100, "p": 60.0, "wilson": [50, 70]},
                     "best_filters": [], "veto_filters": [veto]}},
              open(path, "w"))


def _correr(data_dir, sym, csv, extra=()):
    out = os.path.join(data_dir, "señales.csv")
    r = subprocess.run([BB_ENGINE, "--backtest", csv, "--csv1m", csv, "--sym", sym,
                        "--data-dir", data_dir, "--out", out, *extra],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    filas = [l for l in open(out).read().splitlines()[1:] if l.strip()]
    return filas, r.stderr


@pytest.fixture(scope="module")
def entorno(tmp_path_factory):
    if not os.path.exists(BB_ENGINE):
        pytest.skip("bb_engine sin compilar")
    csv = os.path.join(REPO, "data", "backtest", "bars30d_qqq.csv")
    if not os.path.exists(csv):
        pytest.skip("faltan barras 1m de QQQ")
    d = str(tmp_path_factory.mktemp("bbdata"))
    return d, csv


def test_veto_sin_fdr_ok_no_se_aplica_y_grita(entorno):
    """Fichero anterior a la correccion (vetos sin `fdr_ok`): el motor NO los
    aplica y lo dice por stderr. Antes los aplicaba en silencio."""
    d, csv = entorno
    _plus_json(os.path.join(d, "bollinger_plus.json"), "QQQ", None)
    sin, err = _correr(d, "QQQ", csv)
    assert "SIN campo" in err and "NINGUNO se aplica" in err
    con, _ = _correr(d, "QQQ", csv, ("--legacy-vetos",))
    assert len(sin) > len(con), ("el veto de ruido silenciaba señales: %d vs %d"
                                 % (len(con), len(sin)))


def test_veto_con_fdr_ok_true_si_se_aplica(entorno):
    """Degradacion limpia en la otra direccion: una celda que SI sobrevive al
    BH-FDR sigue vetando exactamente como antes."""
    d, csv = entorno
    _plus_json(os.path.join(d, "bollinger_plus.json"), "QQQ", True)
    con_veto, _ = _correr(d, "QQQ", csv)
    _plus_json(os.path.join(d, "bollinger_plus.json"), "QQQ", False)
    sin_veto, _ = _correr(d, "QQQ", csv)
    assert len(con_veto) < len(sin_veto)
    legacy, _ = _correr(d, "QQQ", csv, ("--legacy-vetos",))
    assert len(legacy) == len(con_veto), "fdr_ok:true == comportamiento legacy"


def test_quitar_un_veto_jamas_invierte_la_señal(entorno):
    """Degradacion limpia: una celda que deja de vetar DEJA DE VETAR — no pasa
    a vetar al reves, ni cambia lado/objetivo/stop de ninguna señal.

    Casi-subconjunto, no subconjunto: el cooldown de bb_core se estampa solo
    cuando la señal se EMITE, asi que un veto que calla una señal deja libre la
    ventana y puede dejar pasar otra posterior ("sombra de cooldown"). Medido en
    QQQ 30d: 1 de 209 (0.5%) frente a 36 desbloqueadas. Es una propiedad previa
    del cooldown, no del cambio; se acota, no se ignora."""
    d, csv = entorno
    _plus_json(os.path.join(d, "bollinger_plus.json"), "QQQ", True)
    con_veto, _ = _correr(d, "QQQ", csv)
    _plus_json(os.path.join(d, "bollinger_plus.json"), "QQQ", False)
    sin_veto, _ = _correr(d, "QQQ", csv)
    con, sin = set(con_veto), set(sin_veto)
    sombra = con - sin
    assert len(sin) > len(con), "quitar el veto tiene que AÑADIR señales"
    assert len(sombra) <= 0.02 * len(con), (
        "demasiadas señales aparecen SOLO con el veto puesto: %s" % sorted(sombra))
    # y ninguna señal cambia de identidad: mismo epoch => misma linea entera
    por_epoch = {l.split(",")[0]: l for l in sin}
    for linea in con:
        gemela = por_epoch.get(linea.split(",")[0])
        assert gemela is None or gemela == linea, (
            "el veto altero la señal en vez de suprimirla: %s vs %s" % (linea, gemela))


# --------------------------------------------------------------------------
# 6. La pregunta de Yunior: "does it break in 1 min AND 15 min?"
# --------------------------------------------------------------------------
def test_exigir_el_15m_no_mejora_el_edge(BC, reales):
    """Yunior (2026-07-25): "with BB, are we making sure it breaks in 1 min and
    15 min? to avoid noise?".

    Medido sobre las 4619 señales elastic: exigir que el 15m TAMBIEN este roto
    deja 352 (8%) y NO mejora el resultado — ni el toque de la media ni la
    triple barrera. El contraste no es significativo. O sea: recorta muestra sin
    comprar edge.

    Y en el brazo band-walk 5m, que es el 2-de-3 REAL de los signal bots
    (`bb_dn_tfs>=2`), la direccion es la CONTRARIA a la intuicion: P(toque) baja
    monotonamente cuantos MAS timeframes esten rotos —
    67.2% (solo 1m) > 49.4% (BB-2TF) > 43.0% (BB-3TF). Romper en mas TF no
    confirma la reversion: la desaconseja (es band-walk). Exigir el 15m no quita
    ruido; el que sobra es el brazo band-walk entero."""
    tf = BC.analizar_tf15(reales)
    todas, roto, no_roto, bot2tf, bot3tf = tf["variantes"]
    assert roto["n"] < todas["n"] * 0.15, "el 15m participa en pocas señales"
    assert roto["p_toque"] <= no_roto["p_toque"], (
        "si el 15m mejorara el toque habria que proponer la regla nueva: "
        "%s vs %s" % (roto["p_toque"], no_roto["p_toque"]))
    assert roto["exp_lb_n_eff"] <= no_roto["exp_lb_n_eff"]
    c = tf["contraste_15m_roto_vs_no"]
    assert c["pval_toque"] > 0.05 and c["pval_barrera"] > 0.05, (
        "el contraste 15m-roto vs 15m-no-roto no llega ni a p<0.05 sin corregir")
    # el 3TF del bot tampoco bate al 2TF: mas TF rotos = peor fade
    assert bot3tf["p_toque"] <= bot2tf["p_toque"] <= no_roto["p_toque"], (
        "monotonia rota: %s / %s / %s"
        % (no_roto["p_toque"], bot2tf["p_toque"], bot3tf["p_toque"]))
    assert tf["contraste_bot_3TF_vs_2TF"]["pval_toque"] > 0.05
