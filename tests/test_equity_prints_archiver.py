"""equity_prints_archiver: archiva la cinta ANTES del trim de 900 s del bridge, rota por
dia segun el epoch de cada linea, es idempotente y NO toca el fichero vivo.

Simula el bridge sobre tmp_path: append de prints + prune a 900 s (misma logica que
ibkr_bar_bridge.prune_whales) y comprueba que no se pierde ni se duplica ni una linea.
"""
import gzip
import importlib.util
import json
import os
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T0 = 1784980800          # 2026-07-25 10:00:00 local


@pytest.fixture()
def ep(tmp_path):
    m = _load("equity_prints_archiver")
    m.STATE_PATH = str(tmp_path / "state.json")
    m.COVERAGE_PATH = str(tmp_path / "coverage.json")
    m.OUT_DIR = str(tmp_path / "prints")
    m.SRC_GLOB = str(tmp_path / "live" / "whale_*.txt")
    os.makedirs(str(tmp_path / "live"))
    m._LIVE = str(tmp_path / "live")
    return m


def _bridge_append(mod, sym, rows):
    """El bridge appendea 'EPOCH PX USD DIR'."""
    p = os.path.join(mod._LIVE, "whale_%s.txt" % sym.lower())
    with open(p, "a") as f:
        for ep_, px, usd, d in rows:
            f.write("%d %.4f %.0f %d\n" % (ep_, px, usd, d))
    return p


def _bridge_prune(mod, sym, now):
    """prune_whales(): deja solo los ultimos 900 s (tmp + os.replace, como el original)."""
    p = os.path.join(mod._LIVE, "whale_%s.txt" % sym.lower())
    cut = now - 900
    keep = [ln for ln in open(p) if float(ln.split()[0]) >= cut]
    with open(p + ".tmp", "w") as f:
        f.writelines(keep)
    os.replace(p + ".tmp", p)
    return len(keep)


def _archived(mod, day, sym):
    p = os.path.join(mod.OUT_DIR, day, "%s.txt" % sym.lower())
    if not os.path.exists(p):
        return []
    return [ln for ln in open(p) if ln.strip()]


DAY = time.strftime("%Y-%m-%d", time.localtime(T0))


# ------------------------------------------------- lo esencial: se archiva antes del trim

def test_archiva_antes_del_trim_y_no_pierde_nada(ep):
    _bridge_append(ep, "nvda", [(T0 + i, 200 + i, 60000, 1) for i in range(5)])
    r = ep.archive_once(now=T0 + 10)
    assert r["rows"] == 5
    # llegan mas prints y el bridge PODA lo viejo: ya estaba archivado
    _bridge_append(ep, "nvda", [(T0 + 1000 + i, 210 + i, 70000, -1) for i in range(3)])
    kept = _bridge_prune(ep, "nvda", T0 + 1010)
    assert kept == 3, "el prune se comio los 5 primeros (eso es el bug que arregla esto)"
    ep.archive_once(now=T0 + 1010)
    lines = _archived(ep, DAY, "nvda")
    assert len(lines) == 8                       # 5 que ya no existen en vivo + 3 nuevos
    assert lines[0].startswith(str(T0))


def test_no_toca_el_fichero_vivo(ep):
    p = _bridge_append(ep, "tsla", [(T0, 400.0, 90000, 0)])
    before, mtime = open(p, "rb").read(), os.path.getmtime(p)
    ep.archive_once(now=T0 + 5)
    assert open(p, "rb").read() == before
    assert os.path.getmtime(p) == mtime


def test_idempotente_dos_corridas_no_duplican(ep):
    _bridge_append(ep, "nvda", [(T0, 200.0, 60000, 1), (T0, 200.5, 55000, -1)])
    ep.archive_once(now=T0 + 1)
    ep.archive_once(now=T0 + 2)
    ep.archive_once(now=T0 + 3)
    assert len(_archived(ep, DAY, "nvda")) == 2


def test_dedupe_en_la_frontera_del_mismo_epoch(ep):
    """Dos prints en el MISMO segundo: el segundo llega despues y no se pierde ni duplica."""
    _bridge_append(ep, "nvda", [(T0, 200.0, 60000, 1)])
    ep.archive_once(now=T0 + 1)
    _bridge_append(ep, "nvda", [(T0, 200.5, 55000, -1)])      # mismo epoch, print distinto
    ep.archive_once(now=T0 + 2)
    lines = _archived(ep, DAY, "nvda")
    assert len(lines) == 2
    assert "55000" in lines[1]


def test_rota_por_dia_segun_el_epoch_de_la_linea(ep):
    """Un print de las 23:59 no puede acabar en el fichero del dia siguiente."""
    late = time.mktime(time.strptime("2026-07-24 23:59:30", "%Y-%m-%d %H:%M:%S"))
    early = time.mktime(time.strptime("2026-07-25 00:00:30", "%Y-%m-%d %H:%M:%S"))
    _bridge_append(ep, "spcx", [(int(late), 10.0, 60000, 1), (int(early), 10.1, 61000, -1)])
    ep.archive_once(now=early + 5)
    assert len(_archived(ep, "2026-07-24", "spcx")) == 1
    assert len(_archived(ep, "2026-07-25", "spcx")) == 1


def test_truncado_diario_del_bridge_no_reinicia_el_archivo(ep):
    _bridge_append(ep, "nok", [(T0, 9.0, 60000, 1)])
    ep.archive_once(now=T0 + 1)
    # el bridge trunca con modo "w" al cambiar de dia
    p = os.path.join(ep._LIVE, "whale_nok.txt")
    with open(p, "w") as f:
        f.write("%d 9.5000 70000 -1\n" % (T0 + 86400))
    ep.archive_once(now=T0 + 86401)
    day2 = time.strftime("%Y-%m-%d", time.localtime(T0 + 86400))
    assert len(_archived(ep, DAY, "nok")) == 1
    assert len(_archived(ep, day2, "nok")) == 1


def test_fichero_de_0_bytes_se_declara_no_se_inventa(ep):
    open(os.path.join(ep._LIVE, "whale_aapl.txt"), "w").close()
    r = ep.archive_once(now=T0)
    assert r["syms"]["AAPL"] == {"rows": 0, "zero_byte": True}
    cov = ep.coverage()
    assert cov["syms"]["AAPL"]["zero_byte"] is True
    assert cov["syms"]["AAPL"]["sessions"] == 0
    assert cov["syms"]["AAPL"]["absorption_ready"] is False


def test_linea_basura_no_se_convierte_en_print_de_cero(ep):
    p = os.path.join(ep._LIVE, "whale_mu.txt")
    with open(p, "w") as f:
        f.write("basura sin sentido\n0 0 0 0\n%d 100.0 60000 1\n" % T0)
    r = ep.archive_once(now=T0 + 1)
    assert r["syms"]["MU"]["rows"] == 1
    assert ep.parse_line("0 0 0 0\n") is None
    assert ep.parse_line("basura\n") is None


def test_hueco_solo_si_estuvimos_fuera_mas_que_la_ventana(ep):
    _bridge_append(ep, "nvda", [(T0, 200.0, 60000, 1)])
    ep.archive_once(now=T0 + 1)
    # prints espaciados pero el archivador al dia: NO es hueco
    _bridge_append(ep, "nvda", [(T0 + 300, 201.0, 60000, 1)])
    r = ep.archive_once(now=T0 + 301)
    assert r["gaps"] == []
    # ahora el archivador estuvo caido > 900 s y el prune se llevo lo de en medio
    _bridge_append(ep, "nvda", [(T0 + 4000, 202.0, 60000, 1)])
    _bridge_prune(ep, "nvda", T0 + 4001)
    r = ep.archive_once(now=T0 + 4001)
    assert r["gaps"] == ["NVDA"]
    assert json.load(open(ep.STATE_PATH))["NVDA"]["gaps"] == 1


def test_cobertura_es_honesta_no_redondea_hacia_arriba(ep):
    _bridge_append(ep, "nvda", [(T0 + 60 * i, 200.0, 60000, 1) for i in range(10)])
    ep.archive_once(now=T0 + 700)
    cov = ep.coverage()
    s = cov["syms"]["NVDA"]
    assert s["sessions"] == 1 and s["rows"] == 10
    d = s["days"][DAY]
    assert d["minutes_with_print"] == 10
    assert d["pct_of_session_covered"] == round(100.0 * 10 / 390, 1)   # ~2,6%, no 100
    assert s["absorption_ready"] is False                              # <20 sesiones
    assert cov["whale_min_usd"] == 50000.0


def test_retencion_gzipea_y_borra_con_paridad(ep):
    _bridge_append(ep, "nvda", [(T0 + i, 200.0, 60000, 1) for i in range(50)])
    ep.archive_once(now=T0 + 60)
    later = time.strftime("%Y-%m-%d", time.localtime(T0 + 3 * 86400))
    r = ep.retention(apply_=False, today=later)
    assert [a["action"] for a in r["actions"]] == ["gzip"] and not r["actions"][0]["applied"]
    r = ep.retention(apply_=True, today=later)
    d = os.path.join(ep.OUT_DIR, DAY)
    assert os.listdir(d) == ["nvda.txt.gz"]
    with gzip.open(os.path.join(d, "nvda.txt.gz"), "rt") as f:
        assert sum(1 for _ in f) == 50
    # y la cobertura sigue leyendo del gz
    assert ep.coverage()["syms"]["NVDA"]["rows"] == 50
    # borrado a los 180 dias
    far = time.strftime("%Y-%m-%d", time.localtime(T0 + 200 * 86400))
    r = ep.retention(apply_=True, today=far)
    assert any(a["action"] == "delete_day" and a["applied"] for a in r["actions"])
    assert not os.path.exists(d)


def test_escritura_de_estado_atomica(ep):
    _bridge_append(ep, "nvda", [(T0, 200.0, 60000, 1)])
    ep.archive_once(now=T0 + 1)
    assert json.load(open(ep.STATE_PATH))["NVDA"]["last_ep"] == T0
    assert not [f for f in os.listdir(os.path.dirname(ep.STATE_PATH)) if ".tmp" in f]


def test_formato_real_del_repo_parsea(ep):
    """Guarda de contrato con ibkr_bar_bridge: si cambia el formato de la cinta, muere aqui."""
    import glob as g
    real = [p for p in g.glob(os.path.join(REPO, "data", "whale_*.txt"))
            if os.path.getsize(p) > 0]
    if not real:
        pytest.skip("sin cinta viva")
    with open(real[0]) as f:
        first = f.readline()
    assert ep.parse_line(first) is not None, first
