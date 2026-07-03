"""overnight_pump_study — modo US (futuros NQ/ES).

Yunior preguntó por el pump de las ~00:30 ET del overnight US, que el propio TODOS.md marca como
DISTINTO del agotamiento KRX. Lo que se protege aqui es que el estudio NO publique un numero con
una muestra de 4 noches.
"""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(REPO, "scripts", "overnight_pump_study.py")
    spec = importlib.util.spec_from_file_location("ibt_overnight_pump_study", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --- Fuente unica: universo y horario KRX vienen de data/ y de overnight_feed, no duplicados ---

def test_universo_krx_viene_de_data_no_de_una_tupla_duplicada():
    """SYMS duplicaba korea_bar_bridge.CORE: dos listas que pueden divergir en silencio."""
    assert not hasattr(M, "SYMS")
    core = open(os.path.join(REPO, "data", "korea_core.txt")).read().split()
    assert list(M.core_syms()) == core and core


def test_core_syms_sin_fichero_levanta(tmp_path):
    """Sin universo NO se inventa uno: lote fuera de sesion, fail-loud."""
    with pytest.raises(RuntimeError):
        M.core_syms(path=str(tmp_path / "no-existe.txt"))


def test_apertura_krx_y_franjas_derivadas_del_horario_unico():
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import overnight_feed as OF
    assert (M.OPEN_H, M.OPEN_M) == (OF.KRX_OPEN_H, OF.KRX_OPEN_M)
    assert M.N_BUCKETS == 13          # 09:00->15:30 KST en franjas de 30 min


# --- DST: la misma franja KST no cae siempre a la misma hora ET -------------------------------

def _sesion(root, day_iso, n=391):
    import datetime as dt
    from zoneinfo import ZoneInfo
    base = dt.datetime.fromisoformat(day_iso).replace(
        hour=9, minute=0, tzinfo=ZoneInfo("Asia/Seoul")).timestamp()
    d = os.path.join(root, day_iso, "bars")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "kospi_krx.txt"), "w") as f:
        for i in range(n):
            c = 100.0 + i * 0.01
            f.write(f"{base + i * 60:.0f} {c:.4f} {c:.4f} {c:.4f} {c:.4f} 10\n")


def test_etiqueta_et_declara_la_ambiguedad_de_dst(tmp_path):
    """13:30 KST son las 00:30 ET en verano y las 23:30 en invierno: con una sola etiqueta
    (la del ultimo dia) la muestra de marzo se leia como si toda fuera de las 00:30."""
    root = str(tmp_path / "hist")
    _sesion(root, "2026-03-05")        # EST
    _sesion(root, "2026-03-16")        # EDT (DST desde el 8-mar)
    res = M.study(history_root=root, min_n=30, syms_list=("kospi",))
    b9 = res["symbols"]["kospi"]["buckets"][9]
    assert b9["kst"] == "13:30"
    assert b9["et"] == "00:30" and b9["et_variants"] == ["00:30", "23:30"]
    assert b9["et_dst_ambiguo"] is True
    b0 = res["symbols"]["kospi"]["buckets"][0]
    assert b0["et_variants"] == ["19:00", "20:00"] and b0["et_dst_ambiguo"] is True


def test_sin_dst_en_la_muestra_no_hay_ambiguedad(tmp_path):
    root = str(tmp_path / "hist")
    _sesion(root, "2026-07-30")
    _sesion(root, "2026-07-31")
    res = M.study(history_root=root, min_n=30, syms_list=("kospi",))
    for b in res["symbols"]["kospi"]["buckets"]:
        assert b["et_dst_ambiguo"] is False and b["et_variants"] == [b["et"]]


# --- Modo US (futuros NQ/ES): el patron que preguntó Yunior, no el agotamiento KRX -----------

def _linea(ts, nq=None, es=None):
    return json.dumps({"ts": ts, "nq_pct": nq, "es_pct": es}) + "\n"


def test_us_no_publica_probabilidad_con_pocas_noches(tmp_path):
    """4 noches no miden un patron: tiene que decir cuantas faltan, no dar un p_up."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Toronto")
    ctx = tmp_path / "ctx.jsonl"
    txt = ""
    for d in range(4):
        base = dt.datetime(2026, 7, 6 + d, 20, 5, tzinfo=TZ).timestamp()
        txt += _linea(base, nq=0.1) + _linea(base + 1500, nq=0.4)
    ctx.write_text(txt)
    r = M.study_us(ctx=str(ctx), feed_log=str(tmp_path / "no-existe.log"))
    assert r["status"] == "DATA-INSUFFICIENT"
    assert r["n_noches"] == 4 and r["faltan_noches"] == 26
    assert all(b["p_up"] is None for b in r["buckets"])


def test_us_la_franja_de_las_0030_existe_y_es_la_correcta():
    """La pregunta es literalmente sobre las 00:30 ET: esa franja tiene que estar en la rejilla."""
    r = M.study_us(ctx="/no/existe", feed_log="/no/existe")
    ets = [b["et"] for b in r["buckets"]]
    assert ets[0] == "20:00" and ets[-1] == "03:30"
    assert "00:30" in ets


def test_us_una_sola_lectura_en_la_franja_no_cuenta():
    """Con un solo tick no hay retorno: contarlo como 'up' fabricaria una muestra."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Toronto")
    import tempfile, os as _os
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    base = dt.datetime(2026, 7, 6, 0, 35, tzinfo=TZ).timestamp()
    _os.write(fd, _linea(base, nq=0.5).encode())
    _os.close(fd)
    r = M.study_us(ctx=path, feed_log="/no/existe")
    assert sum(b["n"] for b in r["buckets"]) == 0
    _os.unlink(path)


def test_us_fila_sin_futuros_se_descarta():
    """hynix_pct sin nq/es no es una observacion del overnight US."""
    import tempfile, os as _os, json as _json
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    _os.write(fd, (_json.dumps({"ts": 1785500000, "nq_pct": None, "es_pct": None}) + "\n").encode())
    _os.close(fd)
    assert M.load_futures_rows(ctx=path, feed_log="/no/existe") == []
    _os.unlink(path)


def test_us_dedup_por_ts_entre_las_dos_fuentes():
    """ctx.jsonl y el log se solapan: contar dos veces el mismo tick infla la muestra."""
    import tempfile, os as _os
    fd1, p1 = tempfile.mkstemp(suffix=".jsonl"); _os.write(fd1, _linea(1785500000, nq=0.2).encode()); _os.close(fd1)
    fd2, p2 = tempfile.mkstemp(suffix=".log");   _os.write(fd2, _linea(1785500000, nq=0.2).encode()); _os.close(fd2)
    assert len(M.load_futures_rows(ctx=p1, feed_log=p2)) == 1
    _os.unlink(p1); _os.unlink(p2)
