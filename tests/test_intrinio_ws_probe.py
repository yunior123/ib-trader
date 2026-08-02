"""Sonda del WebSocket de Intrinio: la fase de mercado y el fail-loud son lo que da valor a la serie.

Si market_phase() se equivoca, la fila queda mal etiquetada y la pregunta que la sonda existe para
responder ("¿cae porque el mercado esta cerrado?") se contesta con basura.
"""
import importlib.util
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo("America/New_York")


def _load():
    path = os.path.join(REPO, "scripts", "intrinio_ws_probe.py")
    spec = importlib.util.spec_from_file_location("ibt_intrinio_ws_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = _load()


@pytest.mark.parametrize(
    "iso,esperado",
    [
        ("2026-08-02 02:16:00", "weekend"),    # domingo (la medicion original)
        ("2026-08-01 11:00:00", "weekend"),    # sabado, aunque sea hora de RTH
        ("2026-08-03 03:59:00", "overnight"),  # lunes antes de premarket
        ("2026-08-03 04:00:00", "premarket"),
        ("2026-08-03 09:29:00", "premarket"),
        ("2026-08-03 09:30:00", "rth"),
        ("2026-08-03 15:59:00", "rth"),
        ("2026-08-03 16:00:00", "afterhours"),
        ("2026-08-03 19:59:00", "afterhours"),
        ("2026-08-03 20:00:00", "overnight"),
    ],
)
def test_market_phase(iso, esperado):
    dt = datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
    assert probe.market_phase(dt) == esperado


def test_hosts_son_los_7_del_sdk():
    """Si el SDK cambia de hosts, la sonda tiene que enterarse: no puede medir hosts fantasma."""
    assert set(probe.HOSTS) == {
        "realtime-mx", "realtime-delayed-sip", "realtime-nasdaq-basic",
        "cboe-one", "equities-edge", "realtime-options", "options-edge",
    }


def test_load_key_levanta_sin_key(tmp_path, monkeypatch):
    """Sin key se LEVANTA. Devolver '' dejaria filas que parecen medidas y no lo son."""
    monkeypatch.delenv("INTRINIO_API_KEY", raising=False)
    monkeypatch.setattr(probe, "REPO", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "feeds.env").write_text("OTRA=cosa\n")
    with pytest.raises(RuntimeError):
        probe.load_key()


def test_probe_auth_registra_el_fallo_sin_inventar(monkeypatch):
    """Un host caido produce ok=False con el error EXACTO, nunca un token plausible."""
    class _Boom:
        def get(self, *a, **k):
            raise ConnectionError("Remote end closed connection without response")

    monkeypatch.setitem(__import__("sys").modules, "requests", _Boom())
    r, token = probe.probe_auth("equities-edge", "k")
    assert r["ok"] is False
    assert r["http"] is None
    assert "ConnectionError" in r["err"]
    assert token is None          # jamas se inventa un token
    assert "token" not in r


def test_probe_auth_no_marca_ok_con_cuerpo_corto(monkeypatch):
    """Un 200 con cuerpo vacio/corto NO es un token: marcarlo ok arrancaria el puente en falso."""
    class _Resp:
        status_code = 200
        text = "ok"

    class _Sess:
        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setitem(__import__("sys").modules, "requests", _Sess())
    r, token = probe.probe_auth("equities-edge", "k")
    assert r["ok"] is False and token is None


def test_record_escribe_jsonl_y_status_atomico(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "JSONL", tmp_path / "p.jsonl")
    monkeypatch.setattr(probe, "STATUS", tmp_path / "s.json")
    monkeypatch.setattr(probe, "UP_FLAG", tmp_path / "UP")
    row = {"epoch": 1, "et": "2026-08-02 02:00:00", "phase": "weekend",
           "auth": {}, "tls_idle": {}, "controls": {}, "any_up": []}
    probe.record(row)
    assert json.loads((tmp_path / "p.jsonl").read_text().strip())["phase"] == "weekend"
    assert json.loads((tmp_path / "s.json").read_text())["epoch"] == 1
    assert not (tmp_path / "UP").exists()

    row2 = dict(row, epoch=2, any_up=["equities-edge"])
    probe.record(row2)
    assert (tmp_path / "UP").exists()          # levanta la bandera cuando revive
    assert len((tmp_path / "p.jsonl").read_text().strip().splitlines()) == 2

    probe.record(dict(row, epoch=3))
    assert not (tmp_path / "UP").exists()      # y la retira si vuelve a caer


def test_el_token_nunca_llega_al_disco(tmp_path, monkeypatch):
    """El token es una credencial: se usa en el acto y no se escribe. Solo su longitud."""
    monkeypatch.setattr(probe, "JSONL", tmp_path / "p.jsonl")
    monkeypatch.setattr(probe, "STATUS", tmp_path / "s.json")
    monkeypatch.setattr(probe, "UP_FLAG", tmp_path / "UP")
    secreto = "TOKEN-SECRETO-" + "x" * 40

    class _Resp:
        status_code = 200
        text = secreto

    class _Sess:
        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setitem(__import__("sys").modules, "requests", _Sess())
    r, token = probe.probe_auth("equities-edge", "k")
    assert r["ok"] is True and token == secreto
    assert r["body_head"] == "<token>"
    probe.record({"epoch": 1, "et": "x", "phase": "rth", "auth": {"equities-edge": r},
                  "tls_idle": {}, "controls": {}, "any_up": ["equities-edge"], "socket_ok": []})
    escrito = (tmp_path / "p.jsonl").read_text() + (tmp_path / "s.json").read_text() + (tmp_path / "UP").read_text()
    assert secreto not in escrito


def test_socket_solo_se_intenta_con_token(monkeypatch):
    """Sin token no se llama al socket: probar wss con token vacio da un falso negativo."""
    llamadas = []
    monkeypatch.setattr(probe, "probe_auth", lambda h, k: ({"ok": False}, None))
    monkeypatch.setattr(probe, "probe_socket", lambda h, t: llamadas.append(h) or {})
    monkeypatch.setattr(probe, "probe_tls", lambda h: {})
    monkeypatch.setattr(probe, "probe_controls", lambda k: {})
    row = probe.run_once("k")
    assert llamadas == []
    assert row["socket_ok"] == [] and row["any_up"] == []


def test_socket_ok_solo_si_abre(monkeypatch):
    """auth OK con socket caido NO puede contar como 'websockets funcionando'."""
    monkeypatch.setattr(probe, "probe_auth", lambda h, k: ({"ok": True}, "tok"))
    monkeypatch.setattr(probe, "probe_socket", lambda h, t: {"opened": h == "equities-edge"})
    monkeypatch.setattr(probe, "probe_tls", lambda h: {})
    monkeypatch.setattr(probe, "probe_controls", lambda k: {})
    row = probe.run_once("k")
    assert row["socket_ok"] == ["equities-edge"]
    assert len(row["any_up"]) == len(probe.HOSTS)


def _serie(tmp_path, monkeypatch, filas):
    p = tmp_path / "p.jsonl"
    p.write_text("".join(json.dumps(f) + "\n" for f in filas))
    monkeypatch.setattr(probe, "JSONL", p)


def test_resumen_sin_mediciones(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, "JSONL", tmp_path / "no-existe.jsonl")
    assert probe.resumen() == 1
    assert "sin mediciones" in capsys.readouterr().out


def test_resumen_todo_abajo_no_inventa_subida(tmp_path, monkeypatch, capsys):
    _serie(tmp_path, monkeypatch, [
        {"et": "2026-08-02 02:16:02", "phase": "weekend", "socket_ok": []},
        {"et": "2026-08-02 02:26:02", "phase": "weekend", "socket_ok": []},
    ])
    assert probe.resumen() == 1
    out = capsys.readouterr().out
    assert "NO ha estado arriba" in out
    assert "PRIMERA SUBIDA" not in out


def test_resumen_localiza_la_primera_subida_y_su_fase(tmp_path, monkeypatch, capsys):
    """Esta es LA medicion: si la primera subida cae en premarket, la causa era horaria."""
    _serie(tmp_path, monkeypatch, [
        {"et": "2026-08-03 03:40:00", "phase": "overnight", "socket_ok": []},
        {"et": "2026-08-03 03:50:00", "phase": "overnight", "socket_ok": []},
        {"et": "2026-08-03 04:00:00", "phase": "premarket", "socket_ok": ["equities-edge"]},
        {"et": "2026-08-03 04:10:00", "phase": "premarket", "socket_ok": ["equities-edge"]},
    ])
    assert probe.resumen() == 0
    out = capsys.readouterr().out
    assert "PRIMERA SUBIDA: 2026-08-03 04:00:00 ET, fase=premarket" in out
    assert "equities-edge" in out


def test_resumen_auth_ok_sin_socket_no_cuenta_como_arriba(tmp_path, monkeypatch, capsys):
    """Un token no es un socket: si el WS no abre, la serie no puede decir que revivio."""
    _serie(tmp_path, monkeypatch, [
        {"et": "2026-08-03 04:00:00", "phase": "premarket", "any_up": ["cboe-one"], "socket_ok": []},
    ])
    assert probe.resumen() == 1
    assert "NO ha estado arriba" in capsys.readouterr().out
