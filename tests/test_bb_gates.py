"""Tests de los gates del vigía Bollinger (2026-08-05): distancia a la media, RSI Wilder.

Medición que los justifica (8,95 M barras 1m, 83.576 eventos, triple barrera, walk-forward):
  baseline sin gate .................. 42,2% [41,6-42,7] n=82.714
  distancia a la media <= 1,0 ATR14 .. 60,1% [59,2-61,0] n=16.000, corta el 80,7%
  RSI14(1m) >= 80 / <= 20 ............  7,7% [2,1-24,1]  n=26 en DOS AÑOS  <- lo pedido literal
  RSI2 contrario (hoy vetado por error) 49,1% [46,3-52,0] n=1.223
Cero red, cero voz: el módulo se importa sin arrancar el bucle (main() bajo __main__).
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load():
    path = os.path.join(SCRIPTS, "bollinger_alarm.py")
    spec = importlib.util.spec_from_file_location("ibt_bollinger_alarm", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)          # NO arranca el bucle: vive en main()
    return mod


BA = _load()


# --- Wilder, no SMA (el error clasico que desplaza el umbral 80/20) -----------------------
def test_rsi14_es_wilder_no_sma():
    def wilder_ref(cl, n=14):
        g = [max(cl[i] - cl[i - 1], 0) for i in range(1, len(cl))]
        l = [max(cl[i - 1] - cl[i], 0) for i in range(1, len(cl))]
        ag, al = sum(g[:n]) / n, sum(l[:n]) / n
        for i in range(n, len(g)):
            ag = (ag * (n - 1) + g[i]) / n
            al = (al * (n - 1) + l[i]) / n
        return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

    serie = [100.0]
    for i in range(80):
        serie.append(serie[-1] * (1 + (0.004 if i % 3 else -0.007)))
    assert abs(BA.rsi14(serie) - wilder_ref(serie)) < 1e-9


def test_rsi14_extremos_y_datos_cortos():
    assert BA.rsi14([100 + i for i in range(30)]) == 100.0
    assert BA.rsi14([100 - i for i in range(30)]) == 0.0
    assert BA.rsi14([100, 101, 102]) is None, "sin datos devuelve None, jamas un 50 plausible"
    assert BA.rsi14([100.0] * 30) is None, "cinta plana = sin informacion, no un 100 plausible"


def test_atr14_mide_el_rango_y_no_inventa_cero():
    bars = [(i * 60, 10.0, 10.5, 9.5, 10.0) for i in range(30)]
    assert abs(BA.atr14(bars) - 1.0) < 1e-9
    assert BA.atr14(bars[:5]) is None
    planas = [(i * 60, 10.0, 10.0, 10.0, 10.0) for i in range(30)]
    assert BA.atr14(planas) is None, "ATR 0 seria una division por cero disfrazada"


# --- gate de distancia -------------------------------------------------------------------
SYM = "zzz"          # sin data/bars_zzz_ibkr.txt: el contexto no puede leer datos vivos


def _serie(n=140, base=100.0, paso=0.0, rango=0.5, ruido=0.01):
    """Barras 1m sintéticas con ATR ~= rango. `ruido` evita la cinta plana degenerada."""
    out = []
    for i in range(n):
        c = base + paso * i + (ruido if i % 2 else -ruido)
        out.append((1700000000 + i * 60, c, c + rango / 2, c - rango / 2, c))
    return out


def test_veto_si_la_media_esta_lejos():
    bars = _serie()
    precio = bars[-1][4]
    lejos = precio + 5.0                              # 10 ATR de distancia
    ctx, ok = BA.bb_context(SYM, bars, side="up", price=precio, mid=lejos)
    assert not ok and "VETO distancia" in ctx


def test_pasa_si_la_media_esta_cerca():
    bars = _serie()
    precio = bars[-1][4]
    ctx, ok = BA.bb_context(SYM, bars, side="up", price=precio, mid=precio + 0.2)
    assert ok, ctx
    assert "VETO" not in ctx and "distancia" in ctx


def test_umbral_configurable_por_entorno(monkeypatch):
    assert BA.MAX_DIST_ATR == 1.0, "el default medido es 1,0 ATR (60,1%)"


def test_sin_side_no_veta_nada():
    """Llamada antigua (sin side/price/mid): degradacion limpia, no puede silenciar la flota."""
    ctx, ok = BA.bb_context(SYM, _serie())
    assert ok


# --- RSI2 unilateral ---------------------------------------------------------------------
def test_rsi2_veta_solo_a_favor_del_pierce():
    """El RSI2 contrario rinde 49,1% (sobre el baseline) y hasta hoy se silenciaba."""
    subiendo = _serie(paso=0.05, ruido=0.0)            # RSI2 = 100: impulso al alza vivo
    precio = subiendo[-1][4]
    ctx_up, _ = BA.bb_context(SYM, subiendo, side="up", price=precio, mid=precio - 0.1)
    assert "VETO RSI2" in ctx_up, "pierce ARRIBA con impulso alcista vivo: se veta"
    ctx_dn, _ = BA.bb_context(SYM, subiendo, side="dn", price=precio, mid=precio + 0.1)
    assert "VETO RSI2" not in ctx_dn, \
        "el mismo RSI2 alto en un pierce ABAJO es el impulso CONTRARIO: no se veta"


# --- lo que pidio Yunior, literal, tras el aviso ------------------------------------------
def test_rsi_confirm_apagado_por_defecto():
    assert BA.RSI_CONFIRM is False, "el 80/20 literal deja 0,05 alertas/dia: opt-in"


def test_rsi_confirm_activado_exige_80_20(monkeypatch):
    monkeypatch.setattr(BA, "RSI_CONFIRM", True)
    lateral = _serie()                                 # RSI14 ~ 50: no confirma
    precio = lateral[-1][4]
    ctx, ok = BA.bb_context(SYM, lateral, side="up", price=precio, mid=precio - 0.1)
    assert not ok and "no confirma 80/20" in ctx


def test_veto_rsi15_por_defecto_en_80():
    assert BA.RSI15_VETO == 80.0
