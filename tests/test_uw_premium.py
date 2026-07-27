"""test_uw_premium.py — premium neto UW + probe de latencia, SIN RED.

Lo que importa: (1) un fallo de red se PROPAGA (RuntimeError), jamas se convierte en [] ni en 0
premium — un 0 firmado seria "el agresor esta plano", que es una afirmacion; (2) el 401 se nombra
como token caducado y no se confunde con un 403 de ritmo; (3) `latest_feed_age_s` y
`signed_premium` devuelven None sin filas; (4) el probe fuera de sesion NO inventa un numero ni
escribe en el historial, y el veredicto de tiempo-real sale del umbral, no del deseo.
"""
import datetime as dt
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import urllib.error  # noqa: E402
import uw_latency_probe as lp  # noqa: E402
import uw_premium as up  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _seq(monkeypatch, items):
    it = iter(items)

    def fake(req, timeout=None):
        x = next(it)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(up.urllib.request, "urlopen", fake)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(up.time, "sleep", lambda s: None)


TICKS = [{"tape_time": "2026-07-27T13:45:00Z", "net_call_premium": "1000", "net_put_premium": "400"},
         {"tape_time": "2026-07-27T13:50:00Z", "net_call_premium": "-200", "net_put_premium": "300"}]


def test_fetch_devuelve_las_filas(monkeypatch):
    _seq(monkeypatch, [_Resp({"data": TICKS})])
    assert up.fetch_net_prem_ticks("QQQ", "tok") == TICKS


def test_401_se_nombra_como_token_caducado(monkeypatch):
    _seq(monkeypatch, [urllib.error.HTTPError("u", 401, "no", {}, None)])
    with pytest.raises(RuntimeError, match="caducado"):
        up.fetch_net_prem_ticks("QQQ", "tok")


def test_403_se_reintenta_antes_de_rendirse(monkeypatch):
    _seq(monkeypatch, [urllib.error.HTTPError("u", 403, "no", {}, None), _Resp({"data": TICKS})])
    assert len(up.fetch_net_prem_ticks("SPY", "tok")) == 2


def test_fallo_persistente_levanta_no_devuelve_lista_vacia(monkeypatch):
    _seq(monkeypatch, [OSError("timed out")] * up.RETRIES)
    with pytest.raises(RuntimeError, match="fallo tras"):
        up.fetch_net_prem_ticks("QQQ", "tok")


def test_forma_inesperada_levanta(monkeypatch):
    _seq(monkeypatch, [_Resp({"data": {"no": "es lista"}})] * up.RETRIES)
    with pytest.raises(RuntimeError):
        up.fetch_net_prem_ticks("QQQ", "tok")


def test_edad_del_feed_se_mide_contra_el_tape_mas_reciente():
    now = dt.datetime(2026, 7, 27, 13, 50, 42, tzinfo=dt.timezone.utc)
    age, ts = up.latest_feed_age_s(TICKS, now=now)
    assert ts == "2026-07-27T13:50:00Z" and abs(age - 42.0) < 1e-6


def test_sin_filas_no_hay_edad_ni_cero():
    assert up.latest_feed_age_s([]) == (None, None)


def test_signed_premium_sin_filas_es_none_no_cero():
    assert up.signed_premium([]) is None


def test_signed_premium_suma_la_ventana():
    r = up.signed_premium(TICKS, window_min=15)
    assert r["n_buckets"] == 2 and r["signed_premium"] == (1000 - 200) - (400 + 300)


def test_signed_premium_fuera_de_ventana_no_cuenta():
    viejo = [{"tape_time": "2026-07-27T10:00:00Z", "net_call_premium": "9e9",
              "net_put_premium": "0"}] + TICKS
    assert up.signed_premium(viejo, window_min=15)["n_buckets"] == 2


# ---------- probe ----------

def test_probe_fuera_de_sesion_no_mide_ni_escribe(tmp_path, monkeypatch):
    f = tmp_path / "probe.jsonl"
    monkeypatch.setattr(lp, "PROBE_F", str(f))
    monkeypatch.setattr(lp, "in_session", lambda: False)
    monkeypatch.setattr(lp.uw_premium, "fetch_net_prem_ticks",
                        lambda *a: pytest.fail("no debia tocar la red fuera de sesion"))
    assert lp.main() == 1
    assert not f.exists()


def test_probe_en_sesion_escribe_una_linea_por_simbolo(tmp_path, monkeypatch, capsys):
    f = tmp_path / "probe.jsonl"
    monkeypatch.setattr(lp, "PROBE_F", str(f))
    monkeypatch.setattr(lp, "in_session", lambda: True)
    monkeypatch.setattr(lp.uw_premium, "token", lambda: "tok")
    monkeypatch.setattr(lp.time, "sleep", lambda s: None)
    now = dt.datetime.now(dt.timezone.utc)
    reciente = [{"tape_time": now.isoformat().replace("+00:00", "Z"),
                 "net_call_premium": "1", "net_put_premium": "1"}]
    monkeypatch.setattr(lp.uw_premium, "fetch_net_prem_ticks", lambda s, t: reciente)
    assert lp.main() == 0
    lines = [json.loads(x) for x in f.read_text().splitlines()]
    assert [r["sym"] for r in lines] == lp.SYMS
    assert all(r["feed_age_s"] < lp.REALTIME_BAR_S for r in lines)
    assert "CANDIDATO A TIEMPO-REAL" in capsys.readouterr().out


def test_probe_feed_viejo_dice_delayed_no_lo_maquilla(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lp, "PROBE_F", str(tmp_path / "probe.jsonl"))
    monkeypatch.setattr(lp, "in_session", lambda: True)
    monkeypatch.setattr(lp.uw_premium, "token", lambda: "tok")
    monkeypatch.setattr(lp.time, "sleep", lambda s: None)
    viejo = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=15)
    monkeypatch.setattr(lp.uw_premium, "fetch_net_prem_ticks",
                        lambda s, t: [{"tape_time": viejo.isoformat().replace("+00:00", "Z"),
                                       "net_call_premium": "1", "net_put_premium": "1"}])
    assert lp.main() == 0
    assert "DELAYED" in capsys.readouterr().out


def test_probe_endpoint_caido_no_fija_veredicto(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "PROBE_F", str(tmp_path / "probe.jsonl"))
    monkeypatch.setattr(lp, "in_session", lambda: True)
    monkeypatch.setattr(lp.uw_premium, "token", lambda: "tok")
    monkeypatch.setattr(lp.time, "sleep", lambda s: None)

    def boom(sym, tok):
        raise RuntimeError("UW net-prem-ticks caido")
    monkeypatch.setattr(lp.uw_premium, "fetch_net_prem_ticks", boom)
    assert lp.main() == 1


def test_probe_sin_token_no_finge(monkeypatch):
    monkeypatch.setattr(lp, "in_session", lambda: True)
    monkeypatch.setattr(lp.uw_premium, "token", lambda: "")
    assert lp.main() == 1


def test_umbral_de_tiempo_real_es_un_cubo_de_tape():
    assert lp.REALTIME_BAR_S == 60
