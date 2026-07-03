"""Tests de la COLA del cap del relé (2026-08-05): una ráfaga ya no se tira, se agrupa.

Antes, `if now - lastsent < CAP_S: continue` descartaba el 18-21% del embudo (200 de 909 en
34,5 h medidas, 44 de ellas en la ventana de oro 09:00-10:00). Estos tests clavan que:
  - nada se pierde por el cap mientras quepa en la ventana de frescura
  - lo que espera MÁS de FRESH_S sí se descarta (una alerta tardía miente)
  - las críticas y las 3 señales más selectivas saltan la cola
Cero red: S.send / S.send_many monkeypatcheados.
"""
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load("discord_relay")
L = _load("discord_layout")
S = _load("discord_send")


@pytest.fixture
def espia(monkeypatch):
    """Registra lo publicado sin tocar la red."""
    reg = {"uno": [], "muchos": []}
    monkeypatch.setattr(R.S, "send",
                        lambda ch, emb=None, *a, **k: (reg["uno"].append((ch, emb)), (True, None))[1])
    monkeypatch.setattr(R.S, "send_many",
                        lambda ch, embs, *a, **k: (reg["muchos"].append((ch, embs)), (True, None))[1])
    monkeypatch.setattr(R, "log", lambda m: None)
    return reg


def _item(ts, ch="senales-flota", sev=L.NORMAL, title="🎈 BB REBOTE", mirrors=()):
    return {"ts": ts, "ch": ch, "sev": sev, "title": title, "mirrors": list(mirrors),
            "emb": {"title": title, "description": "x"}}


def test_la_rafaga_no_se_pierde_se_agrupa(espia):
    ahora = 1000.0
    estado = {"lastsent": ahora - 10, "cola": [_item(ahora - 1) for _ in range(7)]}
    n = R.drenar(estado, {}, {}, ahora=ahora)
    assert n == 7, "las 7 tenían que salir, no descartarse"
    assert len(espia["muchos"]) == 1, "un solo POST para las 7"
    assert len(espia["muchos"][0][1]) == 7
    assert estado["cola"] == []


def test_mas_de_diez_se_parten_en_lotes_de_diez(espia):
    ahora = 1000.0
    estado = {"lastsent": ahora - 10, "cola": [_item(ahora - 1) for _ in range(23)]}
    assert R.drenar(estado, {}, {}, ahora=ahora) == 23
    assert [len(e) for _, e in espia["muchos"]] == [10, 10, 3]


def test_la_ley_de_frescura_sigue_mandando_en_la_cola(espia):
    """Lo que esperó más de FRESH_S no se publica: una alerta tardía miente."""
    ahora = 1000.0
    estado = {"lastsent": ahora - 10,
              "cola": [_item(ahora - R.FRESH_S - 1), _item(ahora - 1)]}
    assert R.drenar(estado, {}, {}, ahora=ahora) == 1
    assert len(espia["muchos"][0][1]) == 1


def test_no_drena_antes_de_que_venza_el_cap(espia):
    ahora = 1000.0
    estado = {"lastsent": ahora - 1, "cola": [_item(ahora)]}
    assert R.drenar(estado, {}, {}, ahora=ahora) == 0
    assert espia["muchos"] == [] and len(estado["cola"]) == 1


def test_agrupa_por_canal_no_mezcla(espia):
    ahora = 1000.0
    estado = {"lastsent": ahora - 10,
              "cola": [_item(ahora, ch="senales-flota"), _item(ahora, ch="flujo-uw"),
                       _item(ahora, ch="senales-flota")]}
    R.drenar(estado, {}, {}, ahora=ahora)
    canales = {ch: len(embs) for ch, embs in espia["muchos"]}
    assert canales == {"senales-flota": 2, "flujo-uw": 1}


def test_los_espejos_tambien_salen_desde_la_cola(espia):
    ahora = 1000.0
    estado = {"lastsent": ahora - 10,
              "cola": [_item(ahora, ch="senales-flota", mirrors=["spy-qqq"])]}
    R.drenar(estado, {}, {}, ahora=ahora)
    assert {ch for ch, _ in espia["muchos"]} == {"senales-flota", "spy-qqq"}


def test_la_critica_menciona_una_sola_vez_en_el_lote(espia):
    ahora = 1000.0
    estado = {"lastsent": ahora - 10,
              "cola": [_item(ahora, ch="criticas", sev=L.CRITICA),
                       _item(ahora, ch="criticas", sev=L.CRITICA)]}
    R.drenar(estado, {}, {}, ahora=ahora)
    assert len(espia["muchos"]) == 1, "un POST, una mención — no dos pings"


def test_prioridad_incluye_las_tres_selectivas():
    """confluencia 🔗, manada 🐺🐘 y capitán 🎖 saltaban el cap y se perdían."""
    for emoji in ("🔗", "🐺", "🐘", "🎖"):
        assert R.PRIORIDAD.search(emoji + " algo"), "%s no salta el cap" % emoji
    for txt in ("MU: SELL (STOP)", "🚨 DANGER", "🌋 TERREMOTO"):
        assert R.PRIORIDAD.search(txt)
    assert not R.PRIORIDAD.search("🎈 BB REBOTE | AAPL reventó la banda")


def test_cola_llena_tira_la_mas_vieja_y_lo_dice():
    """Una tormenta no puede comerse la memoria: se acota y se registra la pérdida."""
    assert R.COLA_MAX >= 30
    assert R.COLA_MAX <= 200
