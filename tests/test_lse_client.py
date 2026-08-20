"""Tests del cliente LSE (scripts/lse_client.py).

CERO RED por defecto: la unica salida del modulo es `_http_get`, y aqui se sustituye. Un test
que saliera de verdad gastaria cuota (50 GB/mes) y ademas mentiria en sabado, cuando la bolsa
esta cerrada. El limitador de ritmo y los huecos de concurrencia SI son los reales (usan
ficheros de tmp_path): son codigo de camino critico y hay que ejercitarlo.

El test que SI toca la red esta al final, marcado y saltado salvo IBT_LSE_LIVE=1:
    IBT_LSE_LIVE=1 ./venv/bin/python -m pytest tests/test_lse_client.py -q -k vivo
"""
import datetime as dt
import importlib.util
import json
import os
import sys
import urllib.parse

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


L = _load("lse_client")


# --------------------------------------------------------------------- utilidades de test
class FakeHTTP:
    """Cola de respuestas (status, cabeceras, cuerpo). Registra cada URL pedida."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if not self.queue:
            raise AssertionError("peticion no esperada: " + url)
        r = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(r, Exception):
            raise r
        status, hdrs, body = r
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        return status, hdrs, body

    def qs(self, i=0):
        return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.calls[i]["url"]).query))


def ok(payload, data_bytes=None):
    h = {"content-type": "application/json"}
    if data_bytes is not None:
        h["x-data-bytes"] = str(data_bytes)
    return (200, h, payload)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente con key de mentira, ritmo y huecos REALES pero aislados en tmp_path."""
    monkeypatch.setattr(L.time, "sleep", lambda *_a, **_k: None)   # nada de esperas reales
    lim = L.RateLimiter(n=190, window=62, path=str(tmp_path / "rate.json"))
    slots = L.Slots(n=2, dirpath=str(tmp_path / "slots"), wait_s=2.0)
    return L.LSE(key="TESTKEY", limiter=lim, slots=slots, timeout=5, tries=3)


def wire(monkeypatch, fake):
    monkeypatch.setattr(L, "_http_get", fake)
    return fake


# --------------------------------------------------------------------- clave y auth
def test_sin_key_levanta_jamas_cadena_vacia(monkeypatch):
    monkeypatch.delenv("LSE_API_KEY", raising=False)
    monkeypatch.setattr(L, "_feeds_env", lambda: {})
    with pytest.raises(L.LSEError) as e:
        L.api_key()
    assert "LSE_API_KEY" in str(e.value)


def test_key_del_entorno_gana_a_feeds(monkeypatch):
    monkeypatch.setenv("LSE_API_KEY", "DEL_ENTORNO")
    monkeypatch.setattr(L, "_feeds_env", lambda: {"LSE_API_KEY": "DE_FEEDS"})
    assert L.api_key() == "DEL_ENTORNO"


def test_auth_va_en_la_cabecera_x_api_key_no_en_la_url(client, monkeypatch):
    """Medido: Bearer y ?api_key= dan 401. Si alguien mueve la key a la query, esto cae."""
    f = wire(monkeypatch, FakeHTTP(ok([])))
    client.series("US10Y", limit=1)
    assert f.calls[0]["headers"]["X-API-Key"] == "TESTKEY"
    assert "api_key" not in f.calls[0]["url"] and "TESTKEY" not in f.calls[0]["url"]


def test_redact_tapa_la_key():
    assert L.redact("fallo con abcdefghijkl", key="abcdefghijkl") == "fallo con <LSE_API_KEY>"


# --------------------------------------------------------------------- errores: fail-loud
def test_401_levanta_y_no_reintenta(client, monkeypatch):
    f = wire(monkeypatch, FakeHTTP((401, {}, {"detail": "missing x-api-key"})))
    with pytest.raises(L.LSEError) as e:
        client.candles("SPY", "1d", limit=1)
    assert e.value.status == 401
    assert len(f.calls) == 1, "un 401 reintentado quema cuota sin arreglar nada"


def test_404_desenvuelve_el_detalle_anidado(client, monkeypatch):
    """El vault anida: {"detail":"{\\"detail\\":\\"'ZZZ' has no candle data\\"}"}."""
    body = {"detail": json.dumps({"detail": "'ZZZNOPE' has no candle data; browse /catalog"})}
    wire(monkeypatch, FakeHTTP((404, {}, body)))
    with pytest.raises(L.LSEError) as e:
        client.candles("ZZZNOPE", "1d", limit=1)
    assert "has no candle data" in str(e.value)
    assert '\\"' not in str(e.value)


def test_429_respeta_retry_after_y_reintenta(client, monkeypatch):
    esperas = []
    monkeypatch.setattr(L.time, "sleep", lambda s: esperas.append(s))
    f = wire(monkeypatch, FakeHTTP((429, {"retry-after": "1"}, {"detail": "slow down"}),
                                   ok([{"symbol": "SPY", "date": "2026-08-07", "value": 1.0}])))
    out = client.series("SPY", limit=1)
    assert len(out) == 1 and len(f.calls) == 2
    assert client.stats["http_429"] == 1
    assert esperas and esperas[0] >= 1.0


def test_5xx_reintenta_y_al_final_levanta(client, monkeypatch):
    f = wire(monkeypatch, FakeHTTP((503, {}, "upstream down")))
    with pytest.raises(L.LSEError) as e:
        client.series("SPY", limit=1)
    assert len(f.calls) == client.tries and client.stats["http_5xx"] == client.tries
    assert e.value.status == 0


def test_fallo_de_red_levanta_nunca_lista_vacia(client, monkeypatch):
    f = wire(monkeypatch, FakeHTTP(OSError("connection reset")))
    with pytest.raises(L.LSEError):
        client.options_flow(limit=10)
    assert len(f.calls) == client.tries and client.stats["net_err"] == client.tries


def test_cuerpo_que_no_es_lista_levanta(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok({"detail": "sorpresa"})))
    with pytest.raises(L.LSEError) as e:
        client.candles("SPY", "1d", limit=1)
    assert "se esperaba una lista" in str(e.value)


def test_cuerpo_que_no_es_json_levanta(client, monkeypatch):
    wire(monkeypatch, FakeHTTP((200, {}, "<html>502 bad gateway</html>")))
    with pytest.raises(L.LSEError):
        client.candles("SPY", "1d", limit=1)


# --------------------------------------------------------------------- validacion local
def test_timeframe_invalido_no_gasta_peticion(client, monkeypatch):
    f = wire(monkeypatch, FakeHTTP(ok([])))
    with pytest.raises(L.LSEError) as e:
        client.candles("SPY", "7q", limit=1)
    assert "timeframe" in str(e.value) and not f.calls


def test_order_y_limit_y_type_invalidos_levantan(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([])))
    with pytest.raises(L.LSEError):
        client.candles("SPY", "1d", order="arriba")
    with pytest.raises(L.LSEError):
        client.candles("SPY", "1d", limit=0)
    with pytest.raises(L.LSEError):
        client.options_chain("SPY", kind="lateral", expiry="2026-08-14")


def test_osi_invalido_levanta_y_osi_se_construye_bien(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([])))
    with pytest.raises(L.LSEError):
        client.option_candles("SPY")
    assert client.osi("SPY", 780, "2026-09-25", "put") == "SPY260925P00780000"
    assert client.osi("aapl", 205.5, dt.date(2026, 6, 12), "c") == "AAPL260612C00205500"


def test_limit_se_recorta_al_techo_del_plan(client, monkeypatch):
    f = wire(monkeypatch, FakeHTTP(ok([])))
    client.candles("SPY", "1d", limit=99999)
    assert f.qs()["limit"] == str(L.MAX_ROWS)


def test_parametros_llegan_a_la_query(client, monkeypatch):
    f = wire(monkeypatch, FakeHTTP(ok([])))
    client.options_flow("spy", kind="p", min_premium=250000, max_dte=7,
                        start="2026-08-07", limit=100)
    q = f.qs()
    assert q["underlying"] == "SPY" and q["type"] == "put"
    assert q["min_premium"] == "250000" and q["max_dte"] == "7" and q["start"] == "2026-08-07"


# --------------------------------------------------------------------- normalizacion
def test_ts_a_iso_z_y_ruido_de_flotante_limpiado(client, monkeypatch):
    fila = {"ts": "2026-08-07 00:00:00.000000", "symbol": "SPY", "open": 769.24,
            "close": 773.4, "volume": 31929132}
    wire(monkeypatch, FakeHTTP(ok([fila])))
    out = client.candles("SPY", "1d", limit=1)
    assert out[0]["ts"] == "2026-08-07T00:00:00.000000Z"
    assert "timestamp" not in out[0], "el nombre de cable es `ts`; renombrarlo miente"


def test_strike_con_ruido_binario_se_redondea(client, monkeypatch):
    fila = {"ticker": "SPY260814P00485000", "strike": 484.99999999999994,
            "expiry": "2026-12-31", "underlying_price": 731.5300000000001,
            "last_trade_at": "2026-08-07 20:15:01.832380"}
    wire(monkeypatch, FakeHTTP(ok([fila])))
    out = client.options_chain("SPY", expiry="2026-12-31", limit=10)
    assert out[0]["strike"] == 485.0 and out[0]["underlying_price"] == 731.53


def test_raw_true_devuelve_el_cable_sin_tocar(client, monkeypatch):
    fila = {"ts": "2026-08-07 00:00:00.000000", "close": 773.4000000000001}
    wire(monkeypatch, FakeHTTP(ok([fila])))
    out = client.candles("SPY", "1d", limit=1, raw=True)
    assert out[0]["ts"] == "2026-08-07 00:00:00.000000" and out[0]["close"] == 773.4000000000001


def test_no_se_fabrica_volumen_cuando_el_feed_no_lo_trae(client, monkeypatch):
    """El SDK oficial hace setdefault('volume', 0.0) en FX. Eso es el CERO PLAUSIBLE
    prohibido por la casa: 'sin volumen consolidado' no es 'volumen cero'."""
    wire(monkeypatch, FakeHTTP(ok([{"ts": "2026-08-07 00:00:00", "symbol": "EUR/USD",
                                    "open": 1.1, "close": 1.2}])))
    out = client.candles("EUR/USD", "1d", limit=1)
    assert "volume" not in out[0]


# --------------------------------------------------------------------- truncamiento silencioso
def test_rango_cerrado_truncado_levanta(client, monkeypatch):
    filas = [{"ts": "2026-08-0%d 00:00:00" % (i % 9 + 1)} for i in range(10)]
    wire(monkeypatch, FakeHTTP(ok(filas)))
    with pytest.raises(L.LSEError) as e:
        client.candles("SPY", "1m", start="2026-08-01", end="2026-08-07", limit=10)
    assert "truncado" in str(e.value)


def test_sin_rango_cerrado_el_techo_es_normal(client, monkeypatch):
    filas = [{"ts": "2026-08-07 00:00:00"} for _ in range(10)]
    wire(monkeypatch, FakeHTTP(ok(filas)))
    assert len(client.candles("SPY", "1m", limit=10)) == 10


def test_option_candles_rango_cerrado_truncado_levanta(client, monkeypatch):
    filas = [{"minute": "2026-08-07 20:1%d:00" % i} for i in range(5)]
    wire(monkeypatch, FakeHTTP(ok(filas)))
    with pytest.raises(L.LSEError):
        client.option_candles("SPY260925P00780000", start="2026-08-01", end="2026-08-07", limit=5)


def test_capped_es_honesto():
    assert L.capped([1, 2, 3], 3) and not L.capped([1, 2], 3)
    assert L.capped(list(range(L.MAX_ROWS)), 99999)


# --------------------------------------------------------------------- guardias de la cadena
def _fila_cadena(expiry, strike=780.0):
    return {"ticker": "SPY", "underlying": "SPY", "strike": strike, "expiry": expiry,
            "contract_type": "put", "dte": 7, "underlying_price": 773.25,
            "last_trade_at": "2026-08-07 20:15:01.832380"}


def test_cadena_sin_expiry_y_en_el_techo_levanta(client, monkeypatch):
    """MEDIDO 2026-08-08: SPY sin filtro devolvio 5000/5000 contratos EXPIRADOS."""
    filas = [_fila_cadena("2026-07-02", 400.0 + i) for i in range(20)]
    wire(monkeypatch, FakeHTTP(ok(filas)))
    with pytest.raises(L.LSEError) as e:
        client.options_chain("SPY", limit=20)
    assert "truncada" in str(e.value) and "expiry" in str(e.value)


def test_cadena_entera_expirada_levanta_aunque_no_toque_el_techo(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([_fila_cadena("2026-07-02"), _fila_cadena("2026-07-28")])))
    with pytest.raises(L.LSEError) as e:
        client.options_chain("SPY", expiry="2026-07-02", limit=100)
    assert "EXPIRADA" in str(e.value)


def test_cadena_expirada_pasa_si_se_pide_a_proposito(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([_fila_cadena("2026-07-02")])))
    out = client.options_chain("SPY", expiry="2026-07-02", limit=100, allow_expired=True)
    assert len(out) == 1


def test_cadena_viva_pasa(client, monkeypatch):
    manana = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=7)).isoformat()
    wire(monkeypatch, FakeHTTP(ok([_fila_cadena(manana)])))
    out = client.options_chain("SPY", expiry=manana, limit=100)
    assert out[0]["expiry"] == manana


def test_cadena_vacia_se_devuelve_vacia_sin_inventar(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([])))
    assert client.options_chain("SPY", expiry="2026-08-14", limit=100) == []


def test_flujo_vacio_es_respuesta_legitima(client, monkeypatch):
    """[] del servidor es una MEDICION (no hubo prints), no un fallo: se entrega tal cual."""
    wire(monkeypatch, FakeHTTP(ok([])))
    assert client.options_flow("SPY", limit=10) == []


# --------------------------------------------------------------------- frescura
def test_stale_seconds_levanta_si_falta_el_campo():
    with pytest.raises(L.LSEError):
        L.stale_seconds({"ticker": "SPY260925P00780000"})


def test_stale_seconds_mide_de_verdad():
    ahora = dt.datetime(2026, 8, 8, 12, 0, 0, tzinfo=dt.timezone.utc)
    fila = {"last_trade_at": "2026-08-08T11:00:00.000000Z"}
    assert L.stale_seconds(fila, now=ahora) == pytest.approx(3600.0)


def test_stale_seconds_levanta_con_fecha_ilegible():
    with pytest.raises(L.LSEError):
        L.stale_seconds({"last_trade_at": "ayer por la tarde"})


# --------------------------------------------------------------------- cuota y catalogo
def test_x_data_bytes_se_contabiliza(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([{"ts": "2026-08-07 00:00:00"}], data_bytes=601717)))
    client.candles("SPY", "1m", limit=1)
    assert client.stats["bytes"] == 601717
    assert "MB de cuota" in client.report()


def test_usage_exige_dict(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok([1, 2, 3])))
    with pytest.raises(L.LSEError):
        client.usage()


def test_usage_devuelve_la_cuota(client, monkeypatch):
    wire(monkeypatch, FakeHTTP(ok({"calls_per_minute": 200, "vault_concurrency": 2})))
    assert client.usage()["vault_concurrency"] == 2


def test_catalogo_se_cachea_en_disco_y_no_repite_red(client, monkeypatch, tmp_path):
    cache = str(tmp_path / "cat.json")
    f = wire(monkeypatch, FakeHTTP(ok([{"dataset": "stocks", "symbol": "SPY"},
                                       {"dataset": "options", "symbol": "SPY"}])))
    a = client.catalog(path=cache)
    otro = L.LSE(key="TESTKEY", limiter=client.limiter, slots=client.slots)
    b = otro.catalog(path=cache)
    assert a == b and len(f.calls) == 1
    assert json.load(open(cache))[0]["symbol"] == "SPY"
    assert client.datasets() == {"stocks": 1, "options": 1}


def test_catalogo_vacio_levanta(client, monkeypatch, tmp_path):
    wire(monkeypatch, FakeHTTP(ok([])))
    with pytest.raises(L.LSEError) as e:
        client.catalog(path=str(tmp_path / "cat.json"))
    assert "nunca esta vacio" in str(e.value)


def test_cache_corrupta_se_rebaja_a_la_red(client, monkeypatch, tmp_path):
    cache = tmp_path / "cat.json"
    cache.write_text("{esto no es json")
    f = wire(monkeypatch, FakeHTTP(ok([{"dataset": "fx", "symbol": "EUR/USD"}])))
    assert client.catalog(path=str(cache))[0]["symbol"] == "EUR/USD"
    assert len(f.calls) == 1


def test_cache_caducada_se_rebaja_a_la_red(client, monkeypatch, tmp_path):
    cache = tmp_path / "cat.json"
    cache.write_text(json.dumps([{"dataset": "fx", "symbol": "VIEJO"}]))
    os.utime(str(cache), (0, 0))
    wire(monkeypatch, FakeHTTP(ok([{"dataset": "fx", "symbol": "NUEVO"}])))
    assert client.catalog(path=str(cache), max_age_s=60)[0]["symbol"] == "NUEVO"


# --------------------------------------------------------------------- escritura atomica
def test_atomic_write_no_deja_temporales(tmp_path):
    dest = tmp_path / "sub" / "x.json"
    L.atomic_write(str(dest), '{"a":1}')
    assert json.load(open(dest)) == {"a": 1}
    assert [p.name for p in (tmp_path / "sub").iterdir()] == ["x.json"]


# --------------------------------------------------------------------- ritmo / concurrencia
def test_los_huecos_de_concurrencia_son_finitos(tmp_path):
    """vault_concurrency=2 medido (5 peticiones a la vez -> 2 x 429). Tomados los 2, el
    tercero espera y acaba levantando en vez de disparar un 429 contra el servidor."""
    s = L.Slots(n=2, dirpath=str(tmp_path / "slots"), wait_s=0.3)
    a, b = s.acquire(), s.acquire()
    with pytest.raises(L.LSEError) as e:
        s.acquire()
    assert "concurrencia" in str(e.value)
    L.Slots.release(a)
    L.Slots.release(b)
    L.Slots.release(s.acquire())          # liberados, vuelve a haber hueco


def test_el_ritmo_espera_cuando_se_agota_la_ventana(tmp_path, monkeypatch):
    dormido = []
    monkeypatch.setattr(L.time, "sleep", lambda s: dormido.append(s))
    lim = L.RateLimiter(n=1, window=62, path=str(tmp_path / "rate.json"))
    lim.acquire()
    monkeypatch.setattr(L.time, "sleep", lambda s: (dormido.append(s),
                                                    os.remove(str(tmp_path / "rate.json"))))
    lim.acquire()
    assert dormido and dormido[0] > 0


def test_estado_de_ritmo_corrupto_no_inventa_cuota(tmp_path):
    p = tmp_path / "rate.json"
    p.write_text("no soy json")
    L.RateLimiter(n=2, window=62, path=str(p)).acquire()
    assert json.load(open(p))


# --------------------------------------------------------------------- CLI
def test_cli_reporta_el_fallo_y_devuelve_2(monkeypatch, capsys):
    monkeypatch.setattr(L, "api_key", lambda: "TESTKEY")
    monkeypatch.setattr(L, "_http_get",
                        FakeHTTP((401, {}, {"detail": "missing x-api-key"})))
    monkeypatch.setattr(L.time, "sleep", lambda *_a, **_k: None)
    assert L.main(["--candles", "SPY", "--tf", "1d", "--limit", "5"]) == 2
    assert "LSEError" in capsys.readouterr().err


def test_cli_imprime_filas(monkeypatch, capsys):
    monkeypatch.setattr(L, "api_key", lambda: "TESTKEY")
    monkeypatch.setattr(L, "_http_get",
                        FakeHTTP(ok([{"ts": "2026-08-07 00:00:00", "close": 773.4}])))
    assert L.main(["--candles", "SPY", "--tf", "1d", "--limit", "5"]) == 0
    out = capsys.readouterr().out
    assert "total: 1 filas" in out and "2026-08-07T00:00:00Z" in out


# --------------------------------------------------------------------- red de verdad (opt-in)
@pytest.mark.skipif(os.environ.get("IBT_LSE_LIVE") != "1",
                    reason="toca la red y gasta cuota; correr con IBT_LSE_LIVE=1")
def test_vivo_contra_el_vault():
    """Contrato minimo contra el servidor real. Gasta ~4 peticiones de las 200/min.
    NO afirma frescura: en fin de semana la bolsa esta cerrada y el ultimo tick es del viernes."""
    c = L.LSE()
    u = c.usage()
    assert u["max_rows_per_request"] == L.MAX_ROWS
    assert u["calls_per_minute"] >= 1
    velas = c.candles("SPY", "1d", limit=3, order="desc")
    assert len(velas) == 3
    assert velas[0]["ts"].endswith("Z") and velas[0]["close"] > 0
    with pytest.raises(L.LSEError) as e:
        c.candles("ZZZNOPE", "1d", limit=1)
    assert e.value.status == 404
    flujo = c.options_flow("SPY", limit=5)
    assert isinstance(flujo, list)
    for r in flujo:
        assert "side" not in r and "bid" not in r and "ask" not in r, \
            "el vault EMPEZO a servir lado agresor: actualiza docs/LSE-CLIENTE.md"
