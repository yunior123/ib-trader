#!/usr/bin/env python3
"""test_poly_backfill_opts.py — arnes del backfill de barras diarias de opciones.

SIN RED. Toda respuesta HTTP esta mockeada. Lo que se comprueba es exactamente lo que
puede arruinar un backtest sin que nadie se entere:

  1. el parseo de una respuesta de /v2/aggs produce las filas esperadas;
  2. un 429 dispara backoff y REINTENTO, no un salto silencioso;
  3. un contrato que falla queda REGISTRADO como fallo — jamas "0 filas, todo bien";
  4. el progreso es reanudable: relanzar no duplica (PK otk,ts) y retoma donde iba.

El peligro que persiguen los tests 3 y 4 es el mismo de siempre en esta casa: un cero
plausible. Un descargador que se traga un fallo entrega un dataset con huecos que
parece completo, y encima de ese dataset se calibran probabilidades.
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.error

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import poly_backfill_opts as bf          # noqa: E402
import poly_client                        # noqa: E402
from poly_client import PolygonError      # noqa: E402

EXP = dt.date(2026, 5, 15)
META = {"ticker": "O:QQQ260515C00500000", "strike": 500.0, "right": "call"}


def codigo_sin_comentarios():
    """Fuente del script SIN comentarios ni docstrings (MAYUSCULAS), para auditar lo
    que se EJECUTA y no lo que se explica."""
    import io
    import tokenize
    src = open(os.path.join(REPO, "scripts", "poly_backfill_opts.py")).read()
    out = []
    prev = tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev in (tokenize.INDENT, tokenize.NEWLINE,
                                                    tokenize.NL, tokenize.DEDENT):
            continue                                  # docstring suelto
        out.append(tok.string)
        if tok.type not in (tokenize.NL, tokenize.COMMENT):
            prev = tok.type
    return " ".join(out).upper()


def agg_payload(n=3, t0=1767589200000):
    """Respuesta realista de /v2/aggs/ticker/O:.../range/1/day (forma MEDIDA)."""
    return {"ticker": META["ticker"], "status": "OK", "resultsCount": n,
            "results": [{"v": 10 + i, "vw": 129.0 + i, "o": 129.0 + i, "c": 130.0 + i,
                         "h": 131.0 + i, "l": 128.0 + i, "t": t0 + i * 86400000,
                         "n": 5} for i in range(n)]}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """BD temporal con el esquema EXACTO de poly_opt_bars. Nunca se toca trades.db."""
    monkeypatch.setattr(bf, "DB_PATH", str(tmp_path / "t.db"))
    c = bf.db()
    yield c
    c.close()


class FakePoly:
    """Cliente falso: devuelve lo que le digan, y cuenta las peticiones."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.responses.pop(0) if self.responses else None
        if isinstance(r, Exception):
            raise r
        return r


# ------------------------------------------------------------------ 1. parseo
def test_parseo_produce_las_filas_esperadas():
    rows = bf.parse_agg_rows(META["ticker"], "QQQ", "2026-05-15", 500.0, "call",
                             agg_payload(3))
    assert len(rows) == 3
    otk, sym, exp, strike, right, ts, o, h, l, c, v = rows[0]
    assert (otk, sym, exp, strike, right) == (META["ticker"], "QQQ", "2026-05-15",
                                              500.0, "call")
    assert ts == 1767589200000                     # ms, medianoche ET (no segundos)
    assert (o, h, l, c, v) == (129.0, 131.0, 128.0, 130.0, 10.0)
    # las 3 barras son 3 dias distintos y consecutivos
    assert [r[5] for r in rows] == [1767589200000, 1767675600000, 1767762000000]


def test_barra_malformada_levanta_no_devuelve_cero():
    mala = agg_payload(2)
    del mala["results"][1]["c"]
    with pytest.raises(PolygonError):
        bf.parse_agg_rows(META["ticker"], "QQQ", "2026-05-15", 500.0, "call", mala)


def test_sin_results_es_lista_vacia_no_excepcion():
    assert bf.parse_agg_rows(META["ticker"], "QQQ", "2026-05-15", 500.0, "call",
                             {"status": "OK", "resultsCount": 0}) == []


# --------------------------------------------------------- 2. 429 -> reintento
def test_429_dispara_backoff_y_reintento(monkeypatch, tmp_path):
    """El 429 NO puede saldarse con un salto silencioso: se espera y se reintenta.
    Se mockea urlopen (cero red) y time.sleep (cero espera real)."""
    monkeypatch.setattr(poly_client, "RATE_STATE", str(tmp_path / "rate.json"))
    slept = []
    monkeypatch.setattr(poly_client.time, "sleep", lambda s: slept.append(s))

    intentos = {"n": 0}

    class R:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=None):
        intentos["n"] += 1
        if intentos["n"] <= 2:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)
        return R(json.dumps(agg_payload(1)).encode())

    monkeypatch.setattr(poly_client.urllib.request, "urlopen", fake_urlopen)
    p = poly_client.Polygon(key="X",
                            limiter=poly_client.RateLimiter(path=str(tmp_path / "r2.json")))
    out = p.get("https://api.polygon.io/v2/aggs/ticker/O:X/range/1/day/a/b")

    assert out is not None and out["resultsCount"] == 1   # reintento -> exito
    assert intentos["n"] == 3                             # 2 fallos + 1 bueno
    assert p.stats["http_429"] == 2
    assert slept and max(slept) > 0                       # hubo backoff de verdad


def test_403_levanta_no_se_disfraza_de_vacio(monkeypatch, tmp_path):
    """/v3/trades/O: da 403 MEDIDO. Un 403 debe LEVANTAR, no volverse {}."""
    monkeypatch.setattr(poly_client.time, "sleep", lambda s: None)

    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 403, "NOT_AUTHORIZED", None, None)

    monkeypatch.setattr(poly_client.urllib.request, "urlopen", fake_urlopen)
    p = poly_client.Polygon(key="X",
                            limiter=poly_client.RateLimiter(path=str(tmp_path / "r3.json")))
    with pytest.raises(PolygonError):
        p.get("https://api.polygon.io/v3/trades/O:QQQ260515C00500000")


# ----------------------------------------------- 3. el fallo se REGISTRA como fallo
def test_contrato_fallido_se_registra_como_failed(conn):
    poly = FakePoly([None])                     # peticion abandonada tras reintentos
    ins, state, err = bf.download_contract(poly, conn, "QQQ", EXP, META, 0,
                                           dt.date(2026, 2, 2), EXP)
    assert (ins, state) == (0, "failed") and err
    row = conn.execute("SELECT state, rows, err FROM poly_opt_bf_progress "
                       "WHERE otk=?", (META["ticker"],)).fetchone()
    assert row[0] == "failed" and row[1] == 0 and row[2]
    assert conn.execute("SELECT COUNT(*) FROM poly_opt_bars").fetchone()[0] == 0


def test_fallo_no_se_cuenta_como_exito_con_cero_filas(conn):
    """La trampa exacta: 'done' con 0 filas seria indistinguible de un dia sin datos."""
    for resp in (None, PolygonError("403"), {"status": "OK", "results": [{"t": 1}]}):
        conn.execute("DELETE FROM poly_opt_bf_progress")
        conn.commit()
        poly = FakePoly([resp])
        ins, state, err = bf.download_contract(poly, conn, "QQQ", EXP, META, 0,
                                               dt.date(2026, 2, 2), EXP)
        assert state == "failed", f"{resp!r} deberia ser failed, fue {state}"
        assert err
    assert conn.execute("SELECT COUNT(*) FROM poly_opt_bf_progress "
                        "WHERE state='done'").fetchone()[0] == 0


def test_empty_es_estado_propio_distinto_de_failed(conn):
    """Un contrato que existe pero nunca cotizo NO es un fallo — y tampoco un exito
    con datos. Tiene su propio estado y sale en el informe."""
    poly = FakePoly([{"status": "OK", "resultsCount": 0, "results": []}])
    ins, state, err = bf.download_contract(poly, conn, "QQQ", EXP, META, 0,
                                           dt.date(2026, 2, 2), EXP)
    assert (ins, state, err) == (0, "empty", None)
    assert conn.execute("SELECT state FROM poly_opt_bf_progress").fetchone()[0] == "empty"


# ------------------------------------------------------------ 4. reanudable
def test_relanzar_no_duplica_filas(conn):
    poly = FakePoly([agg_payload(5), agg_payload(5)])
    ins1, st1, _ = bf.download_contract(poly, conn, "QQQ", EXP, META, 0,
                                        dt.date(2026, 2, 2), EXP)
    ins2, st2, _ = bf.download_contract(poly, conn, "QQQ", EXP, META, 0,
                                        dt.date(2026, 2, 2), EXP)
    assert (ins1, st1) == (5, "done")
    assert (ins2, st2) == (0, "done")           # INSERT OR IGNORE: PK(otk, ts)
    assert conn.execute("SELECT COUNT(*) FROM poly_opt_bars").fetchone()[0] == 5


def test_done_set_retoma_donde_iba_y_reintenta_los_fallidos(conn):
    bf.mark(conn, "O:A", "QQQ", "2026-05-15", 1.0, "call", 0, "done", 3, None)
    bf.mark(conn, "O:B", "QQQ", "2026-05-15", 2.0, "call", 0, "empty", 0, None)
    bf.mark(conn, "O:C", "QQQ", "2026-05-15", 3.0, "call", 0, "failed", 0, "boom")
    ya = bf.done_set(conn)
    assert ya == {"O:A", "O:B"}                 # los fallidos NO se dan por hechos
    assert "O:C" not in ya


def test_barras_diarias_no_pisan_las_5m_preexistentes(conn):
    """Las 114.337 filas de 5m que ya existian deben seguir intactas: la barra diaria
    lleva ts de medianoche ET y la PK(otk, ts) no colisiona."""
    conn.execute("INSERT INTO poly_opt_bars VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 (META["ticker"], "QQQ", "2026-05-15", 500.0, "call",
                  1767589200000 + 13 * 3600000, 1, 1, 1, 1, 1))   # barra de 5m
    conn.commit()
    poly = FakePoly([agg_payload(3)])
    ins, state, _ = bf.download_contract(poly, conn, "QQQ", EXP, META, 0,
                                         dt.date(2026, 2, 2), EXP)
    assert (ins, state) == (3, "done")
    assert conn.execute("SELECT COUNT(*) FROM poly_opt_bars").fetchone()[0] == 4


# ------------------------------------------------------------ catalogo / rejilla
def test_catalogo_vacio_levanta_no_devuelve_lista_vacia(tmp_path, monkeypatch):
    """'Polygon no me contesto' != 'no existen contratos'."""
    monkeypatch.setattr(bf, "CONTRACT_CACHE", str(tmp_path / "cc"))

    class P:
        def paginate(self, url, max_pages=6):
            yield {"results": []}

    with pytest.raises(PolygonError):
        bf.contracts_for(P(), "QQQ", EXP)


def test_catalogo_se_cachea_y_no_repite_peticiones(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "CONTRACT_CACHE", str(tmp_path / "cc"))
    llamadas = {"n": 0}

    class P:
        def paginate(self, url, max_pages=6):
            llamadas["n"] += 1
            yield {"results": [{"ticker": "O:QQQ260515C00500000",
                                "strike_price": 500, "contract_type": "call"}]}

    a = bf.contracts_for(P(), "QQQ", EXP)
    b = bf.contracts_for(P(), "QQQ", EXP)
    assert a == b and llamadas["n"] == 1
    assert os.path.exists(os.path.join(str(tmp_path / "cc"), "QQQ_2026-05-15.json"))


def test_pick_toma_el_otm_del_lado_correcto():
    cats = [{"ticker": f"O:X{k}{r[0].upper()}", "strike": float(k), "right": r}
            for k in (450, 475, 500, 525, 550) for r in ("call", "put")]
    assert bf.pick(cats, 500.0, 0.0, "call")["strike"] == 500.0
    assert bf.pick(cats, 500.0, -0.10, None)["right"] == "put"     # abajo -> put
    assert bf.pick(cats, 500.0, -0.10, None)["strike"] == 450.0
    assert bf.pick(cats, 500.0, 0.10, None)["right"] == "call"     # arriba -> call
    assert bf.pick(cats, 500.0, 0.10, None)["strike"] == 550.0
    assert bf.pick([], 500.0, 0.0, "call") is None


def test_spot_sin_barras_locales_levanta(conn):
    """Sin spot no hay rejilla. Un spot inventado seria el cero plausible de manual."""
    conn.execute("""CREATE TABLE IF NOT EXISTS poly_bars(
        sym TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
        PRIMARY KEY(sym, ts))""")
    conn.commit()
    with pytest.raises(PolygonError):
        bf.ref_spot(conn, "QQQ", EXP)


def test_spot_usa_milisegundos_y_devuelve_la_mediana(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS poly_bars(
        sym TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
        PRIMARY KEY(sym, ts))""")
    base = dt.datetime(2026, 4, 1, 15, 0)
    for i, px in enumerate((100.0, 200.0, 300.0)):
        ts = int((base + dt.timedelta(days=i)).timestamp() * 1000)   # MILISEGUNDOS
        conn.execute("INSERT INTO poly_bars VALUES(?,?,?,?,?,?,?)",
                     ("QQQ", ts, px, px, px, px, 1))
    conn.commit()
    assert bf.ref_spot(conn, "QQQ", EXP) == 200.0


# ------------------------------------------------------------------ informe
def test_informe_publica_el_span_real_y_los_fallos(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "REPORT_PATH", str(tmp_path / "rep.json"))
    monkeypatch.setattr(bf, "SYMS", ["QQQ"])
    poly = FakePoly([agg_payload(4)])
    bf.download_contract(poly, conn, "QQQ", EXP, META, 0, dt.date(2026, 2, 2), EXP)
    bf.mark(conn, "O:BOOM", "QQQ", "2026-05-15", 9.0, "put", 1, "failed", 0, "boom")
    rep = bf.write_report(conn)
    assert rep["syms"]["QQQ"]["rows"] == 4
    assert rep["syms"]["QQQ"]["sessions"] == 4
    assert rep["span_real"]["sessions_max"] == 4
    assert rep["span_real"]["target_met"] is False        # 4 < 60, y lo dice
    assert any(f["otk"] == "O:BOOM" for f in rep["failed"])
    assert json.load(open(str(tmp_path / "rep.json")))["syms"]["QQQ"]["contracts"] == 1


def test_no_se_altera_ni_se_borra_el_esquema_de_poly_opt_bars(conn):
    """Ley del encargo: mismo esquema, ni ALTER ni DROP ni VACUUM."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='poly_opt_bars'"
                       ).fetchone()[0]
    cols = [r[1] for r in conn.execute("PRAGMA table_info(poly_opt_bars)")]
    assert cols == ["otk", "sym", "exp", "strike", "right", "ts",
                    "o", "h", "l", "c", "v"]
    assert "PRIMARY KEY(otk, ts)" in sql.replace("\n", " ").replace("  ", " ")
    # se mira el CODIGO, no los comentarios (el docstring nombra 'VACUUM' para prohibirlo)
    for prohibido in ("VACUUM", "ALTER TABLE POLY_OPT_BARS", "DROP TABLE",
                      "DELETE FROM POLY_OPT_BARS"):
        assert prohibido not in codigo_sin_comentarios(), \
            f"el script contiene {prohibido}"


def test_no_hay_ceros_plausibles_en_los_except():
    """Ley de la casa: en un except solo None o levantar. Nunca 0/0.0/0.5/{}."""
    src = open(os.path.join(REPO, "scripts", "poly_backfill_opts.py")).read()
    bloques = src.split("except ")[1:]
    for b in bloques:
        cuerpo = b.split("\n\n")[0]
        for malo in ("return 0\n", "return 0.0", "return 0.5", "return {}",
                     "return []", "except: pass"):
            assert malo not in cuerpo, f"except devuelve {malo!r}"
