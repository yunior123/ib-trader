#!/usr/bin/env python3
"""test_premarket_arrow.py — arnes del binario C++ scripts/premarket_arrow.cpp.

Python aqui es SOLO arnes (el calculo vive entero en bin/premarket_arrow). Los tests montan un
repo de mentira en tmp_path con data/bars_<sym>.txt + data/overnight_ctx.json y corren el
binario ahi con cwd=tmp_path, que es como lee sus rutas.

Lo que estos tests protegen:
 - que NUNCA salga un numero plausible cuando no hay dato (regla #3 de la casa),
 - que la etiqueta de fuente diga la verdad: en vivo NO es no-consolidado,
 - que los porteros (cinta fina, barra rancia, fichero de otra sesion) apaguen la flecha.

Requiere el binario: ./scripts/build_premarket_arrow.sh
"""
import datetime
import json
import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.environ.get("PREMKT_TEST_BIN", os.path.join(REPO, "bin", "premarket_arrow"))

pytestmark = pytest.mark.skipif(
    not os.path.exists(BIN),
    reason="falta bin/premarket_arrow — corre ./scripts/build_premarket_arrow.sh")


def _et(y, m, d, hh, mm):
    """Epoch de una hora LOCAL (el binario usa localtime_r, igual que compass)."""
    return int(datetime.datetime(y, m, d, hh, mm).timestamp())


def _repo(tmp_path, bars, ctx=None, calib=None, sym="spy"):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / f"bars_{sym}.txt").write_text(
        "".join(f"{t} {o:.4f} {h:.4f} {lo:.4f} {c:.4f} {v:.0f}\n" for t, o, h, lo, c, v in bars))
    if ctx is not None:
        (d / "overnight_ctx.json").write_text(json.dumps(ctx))
    if calib is not None:
        (d / "premarket_calib.json").write_text(json.dumps(calib))
    return tmp_path


# Reloj congelado en un martes a las 08:30 ET: asi los tests valen a cualquier hora del dia.
AHORA = int(datetime.datetime(2026, 8, 4, 8, 30).timestamp())


def run(tmp_path, sym="SPY", ahora=None):
    env = dict(os.environ, PREMKT_NOW=str(ahora if ahora is not None else AHORA))
    p = subprocess.run([BIN, sym, "--stdout"], capture_output=True, text=True,
                       cwd=str(tmp_path), timeout=20, env=env)
    assert p.returncode == 0, f"rc={p.returncode} err={p.stderr}"
    return json.loads(p.stdout)


def _hoy():
    return datetime.date.fromtimestamp(AHORA)


def _premarket_bars(n=60, first=770.0, last=772.0, prints=40):
    """n barras de 1m que arrancan a las 04:00 de HOY y terminan pegadas a AHORA."""
    hoy = _hoy()
    ini = _et(hoy.year, hoy.month, hoy.day, 4, 0)
    ahora = AHORA
    paso = (last - first) / max(n - 1, 1)
    out = []
    for i in range(n):
        t = ahora - (n - 1 - i) * 60          # la ultima barra es de hace <1 min
        if t < ini:
            t = ini + i * 60
        c = first + paso * i
        out.append((t, c, c + 0.1, c - 0.1, c, prints))
    return out


def _rth_ayer(close=765.0):
    ayer = _hoy() - datetime.timedelta(days=1)
    t = _et(ayer.year, ayer.month, ayer.day, 15, 59)
    return [(t, close, close, close, close, 1000)]


# ------------------------------------------------------------------ honestidad de la fuente
def test_jamas_dice_que_lo_vivo_es_no_consolidado(tmp_path):
    _repo(tmp_path, _rth_ayer() + _premarket_bars())
    o = run(tmp_path)
    assert o["unconsolidated_live"] is False
    assert o["clase_dato"] == "equities_edge_1m"
    assert "licencia live" in o["unconsolidated_live_why"]


def test_declara_que_el_volumen_premarket_no_existe(tmp_path):
    _repo(tmp_path, _rth_ayer() + _premarket_bars())
    o = run(tmp_path)
    assert "trade_count" in o["volumen_no_disponible"]


# ------------------------------------------------------------------ regla #3: nada de ceros
def test_sin_barras_no_inventa_score(tmp_path):
    (tmp_path / "data").mkdir()
    o = run(tmp_path)
    assert o["usable"] is False and o["score"] is None and o["dir"] == "flat"
    assert o["unusable_reason"] == "sin barras"
    for k in ("gap_pct", "drift_pct", "nq_pct", "es_pct", "prob"):
        assert o[k] is None, f"{k} deberia ser null, no un cero plausible"


def test_sin_overnight_ctx_los_futuros_caen_del_denominador_diciendo_por_que(tmp_path):
    _repo(tmp_path, _rth_ayer() + _premarket_bars())
    o = run(tmp_path)
    comps = {c["nombre"]: c for c in o["componentes"]}
    assert comps["nq"]["valor"] is None and comps["nq"]["ausente_por"] == "sin overnight_ctx"
    assert comps["gap"]["valor"] is not None      # el gap si se puede medir
    assert o["score"] is not None                  # ...y por tanto el score existe


def test_overnight_ctx_rancio_no_entra(tmp_path):
    viejo = {"ts": AHORA - 4000, "nq_pct": -2.0, "es_pct": -2.0}
    _repo(tmp_path, _rth_ayer() + _premarket_bars(), ctx=viejo)
    o = run(tmp_path)
    comps = {c["nombre"]: c for c in o["componentes"]}
    assert comps["nq"]["valor"] is None and comps["nq"]["ausente_por"] == "overnight_ctx rancio"
    assert o["nq_pct"] is None


# ------------------------------------------------------------------ porteros
def test_cinta_demasiado_fina_apaga_la_flecha(tmp_path):
    _repo(tmp_path, _rth_ayer() + _premarket_bars(n=60, prints=1))     # 60 prints < 200
    o = run(tmp_path)
    assert o["usable"] is False and o["dir"] == "flat"
    assert "cinta premarket demasiado fina" in o["unusable_reason"]
    assert o["score"] is not None      # el score se calcula y se publica; lo que se apaga es la FLECHA


def test_barra_rancia_apaga_la_flecha(tmp_path):
    """Barras que paran a las 04:59 vistas a las 08:30 = 3+ h de silencio: cinta muerta."""
    hoy = _hoy()
    ini = _et(hoy.year, hoy.month, hoy.day, 4, 0)
    bars = [(ini + i * 60, 770.0, 770.1, 769.9, 770.0 + i * 0.02, 40) for i in range(60)]
    _repo(tmp_path, _rth_ayer() + bars)
    o = run(tmp_path)
    assert o["bars_age_s"] > 600
    assert o["usable"] is False and "ultima barra" in o["unusable_reason"]


def test_pocos_minutos_con_barra_apaga_la_flecha(tmp_path):
    _repo(tmp_path, _rth_ayer() + _premarket_bars(n=5, prints=500))
    o = run(tmp_path)
    assert o["usable"] is False and "minutos con barra" in o["unusable_reason"]


# ------------------------------------------------------------------ direccion y probabilidad
def test_gap_al_alza_apunta_arriba(tmp_path):
    _repo(tmp_path, _rth_ayer(close=760.0) + _premarket_bars(first=770.0, last=772.0))
    o = run(tmp_path)
    assert o["usable"] is True and o["dir"] == "up" and o["score"] > 0


def test_sin_calibracion_la_probabilidad_es_doctrina_topada(tmp_path):
    _repo(tmp_path, _rth_ayer(close=700.0) + _premarket_bars(first=770.0, last=790.0))
    o = run(tmp_path)
    assert o["prob_source"] in ("sin_calibracion", "sin_celda", "sin_medir")
    assert o["prob"] is None or o["prob"] <= 65, "una probabilidad NO medida no puede pasar de 65"
    assert o["prob_n"] is None                  # sin n medido no se publica n


def test_celda_sin_medir_no_se_publica_como_medida(tmp_path):
    calib = {"_meta": {"clase_dato": "unconsolidated_direct", "n_dias": 3},
             "buckets": {"SIGNED_VOL|q1": {"n": 4, "n_eff": 4, "wr": 0.99, "lo": 0.2,
                                           "medido": False}}}
    _repo(tmp_path, _rth_ayer(close=769.0) + _premarket_bars(first=770.0, last=770.4),
          calib=calib)
    o = run(tmp_path)
    assert o["prob_source"] != "medido"
    assert o["prob"] is None or o["prob"] <= 65
    assert o["calib_clase"] == "unconsolidated_direct"   # dice CON QUE se calibro


# ------------------------------------------------------------------ contrato con compass
def test_compass_ignora_un_fichero_de_otra_sesion():
    src = open(os.path.join(REPO, "scripts", "compass.cpp")).read()
    assert 'jstr(j, "session_date")' in src, "compass debe comprobar la sesion del fichero"
    assert "premarket_arrow_" in src
    i = src.index("load_premarket")
    assert 'o.dir = ' not in src[i:i + 1200], "la flecha premarket no puede tocar `dir`"


def test_compass_solo_toca_candidate_dir():
    src = open(os.path.join(REPO, "scripts", "compass.cpp")).read()
    i = src.index("o.pm_usable && o.pm_dir")
    trozo = src[i:i + 400]
    assert "o.candidate_dir = o.pm_dir" in trozo
    assert 'o.dir == "flat"' in trozo, "solo se rellena cuando la brujula no tiene direccion"
