"""truth_lock: cambiar una barra PASADA se detecta; añadir barras al final NO alarma.

Validacion por INYECCION (como pide el doc #9): se reescribe una barra en una copia del
fichero y se afirma la deteccion. Offline puro, sin tocar trades.db real ni disparar banners.
"""
import importlib.util
import json
import os
import sqlite3
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
def tl(tmp_path):
    m = _load("truth_lock")
    m.STATE_PATH = str(tmp_path / "truth_lock.json")
    m.SNAP_DIR = str(tmp_path / "snap")
    m.EVENTS_PATH = str(tmp_path / "events.jsonl")
    m.SIGDIR = str(tmp_path / "signals")
    m.DB = str(tmp_path / "test.db")
    m.BARS_GLOB = str(tmp_path / "data" / "bars_*_ibkr.txt")
    os.makedirs(str(tmp_path / "data"))
    m._DATA = str(tmp_path / "data")
    return m


BASE = T0 - 400 * 60


def _bars(mod, sym, n=130, start=None, mutate=None):
    """Escribe n barras 1m que terminan ANTES de T0 (todas cerradas).

    Los valores son funcion del EPOCH, no del indice: reescribir el fichero con otro
    `start` debe dar exactamente las mismas barras en los epochs compartidos (si no, el
    test mediria su propio generador en vez del detector).
    """
    start = start or (T0 - n * 60)
    rows = []
    for i in range(n):
        ep = start + i * 60
        k = (ep - BASE) // 60
        px = 100.0 + k * 0.05
        rows.append([ep, px, px + 0.10, px - 0.10, px + 0.02, 1000 + (k % 500)])
    if mutate:
        mutate(rows)
    p = os.path.join(mod._DATA, "bars_%s_ibkr.txt" % sym.lower())
    with open(p, "w") as f:
        for r in rows:
            f.write("%d %.4f %.4f %.4f %.4f %.0f\n" % tuple(r))
    return p


# --------------------------------------------------------------- primer candado

def test_primer_chequeo_congela_la_ventana(tl):
    _bars(tl, "nvda")
    r = tl.check(now=T0, notify=False)
    assert r["checked"] == 1 and r["events"] == []
    st = json.load(open(tl.STATE_PATH))["NVDA"]
    assert st["n"] == tl.WINDOW == 120           # 130 barras -> se congelan las ultimas 120
    assert st["adjusted"] == 0 and len(st["bars_sha"]) == 40


def test_barras_nuevas_al_final_no_alarman(tl):
    start = T0 - 130 * 60
    _bars(tl, "nvda", n=130, start=start)
    tl.check(now=T0, notify=False)
    _bars(tl, "nvda", n=140, start=start)        # 10 barras MAS al final, las viejas iguales
    r = tl.check(now=T0 + 700, notify=False)
    assert r["events"] == [], "crecer por el final es lo normal, no una alarma"
    assert r["syms"]["NVDA"]["ok"] is True
    assert json.load(open(tl.STATE_PATH))["NVDA"]["adjusted"] == 0


# --------------------------------------------------------------- inyeccion

def test_cambiar_una_barra_pasada_se_detecta(tl):
    _bars(tl, "nvda")
    tl.check(now=T0, notify=False)

    def repaint(rows):
        rows[60][4] += 0.50                      # close de una barra CERRADA, 50 ticks
    _bars(tl, "nvda", mutate=repaint)
    r = tl.check(now=T0 + 60, notify=False)
    assert len(r["events"]) == 1
    ev = r["events"][0]
    assert ev["sym"] == "NVDA" and ev["n_material"] == 1 and ev["n_missing"] == 0
    assert ev["old_sha"] != ev["new_sha"]
    assert json.load(open(tl.STATE_PATH))["NVDA"]["adjusted"] == 1
    # registro en jsonl y en su propia tabla
    assert sum(1 for _ in open(tl.EVENTS_PATH)) == 1
    c = sqlite3.connect(tl.DB)
    assert c.execute("SELECT COUNT(*) FROM truth_lock_events").fetchone()[0] == 1
    assert c.execute("SELECT sym, n_material FROM truth_lock_events").fetchone() == ("NVDA", 1)
    c.close()


def test_barra_que_desaparece_es_reescritura(tl):
    """warmup_sym trunca y reescribe: si un epoch se va, el pasado cambio."""
    _bars(tl, "mu", n=130)
    tl.check(now=T0, notify=False)
    p = os.path.join(tl._DATA, "bars_mu_ibkr.txt")
    lines = open(p).readlines()
    del lines[70]
    with open(p, "w") as f:
        f.writelines(lines)
    r = tl.check(now=T0 + 60, notify=False)
    assert len(r["events"]) == 1 and r["events"][0]["n_missing"] == 1


def test_cambio_sub_umbral_no_alarma(tl):
    """Filtro de materialidad: <=1 tick de precio y <=1% de volumen es cosmetico."""
    _bars(tl, "spy")
    tl.check(now=T0, notify=False)

    def tiny(rows):
        rows[50][4] += 0.005                     # medio tick
        rows[51][5] += 5                         # 1000 -> 1005 = 0,5%
    _bars(tl, "spy", mutate=tiny)
    r = tl.check(now=T0 + 60, notify=False)
    assert r["events"] == []
    assert r["syms"]["SPY"]["cosmetic"] == 2
    assert json.load(open(tl.STATE_PATH))["SPY"]["adjusted"] == 0


def test_volumen_material_si_pasa_del_uno_por_ciento(tl):
    _bars(tl, "spy")
    tl.check(now=T0, notify=False)

    def vol(rows):
        rows[50][5] *= 1.5
    _bars(tl, "spy", mutate=vol)
    r = tl.check(now=T0 + 60, notify=False)
    assert len(r["events"]) == 1
    assert r["events"][0]["detail"]["material"][0]["dvol_pct"] > 1.0


def test_minuto_en_curso_no_cuenta_como_pasado(tl):
    """La barra del minuto vivo cambia legitimamente: excluirla evita crying wolf."""
    now = T0
    cur = int(now // 60) * 60
    _bars(tl, "qqq", n=130, start=cur - 129 * 60)
    tl.check(now=now, notify=False)
    p = os.path.join(tl._DATA, "bars_qqq_ibkr.txt")
    lines = open(p).readlines()
    t = lines[-1].split()
    t[4] = "%.4f" % (float(t[4]) + 5.0)          # la ULTIMA barra (minuto en curso)
    lines[-1] = " ".join(t) + "\n"
    with open(p, "w") as f:
        f.writelines(lines)
    r = tl.check(now=now + 30, notify=False)
    assert r["events"] == []


def test_relock_limpia_el_sym(tl):
    _bars(tl, "nvda")
    tl.check(now=T0, notify=False)

    def repaint(rows):
        rows[10][2] += 1.0
    _bars(tl, "nvda", mutate=repaint)
    tl.check(now=T0 + 60, notify=False)
    assert json.load(open(tl.STATE_PATH))["NVDA"]["adjusted"] == 1
    assert tl.relock("NVDA") == ["NVDA"]
    st = json.load(open(tl.STATE_PATH))["NVDA"]
    assert st["adjusted"] == 0 and st["relock_ts"] > 0


def test_no_habla_solo_registra(tl, monkeypatch):
    """El doc es explicito: banner + registro, NUNCA voz DANGER (un backfill benigno
    entrenaria a Yunior a ignorar la sirena)."""
    called = []
    monkeypatch.setattr(tl, "banner", lambda t, m: called.append(("banner", t, m)))
    _bars(tl, "nvda")
    tl.check(now=T0, notify=False)

    def repaint(rows):
        rows[60][1] += 1.0                       # dentro de la ventana congelada
    _bars(tl, "nvda", mutate=repaint)
    tl.check(now=T0 + 60, notify=True)
    assert called and called[0][0] == "banner"
    sig = os.path.join(tl.SIGDIR, time.strftime("%Y-%m-%d") + ".txt")
    line = open(sig).read()
    assert "TRUTH-LOCK INFO" in line, "el kind debe llevar INFO -> notify_only, sin voz"
    assert "DANGER" not in line


def test_barra_basura_no_es_barra_de_ceros(tl):
    assert tl.parse_bar("0 0 0 0 0 0\n") is None
    assert tl.parse_bar("basura\n") is None
    assert tl.parse_bar("1784980800 100 101 99 100.5 1000\n")[0] == 1784980800


def test_idempotente_dos_chequeos_seguidos(tl):
    _bars(tl, "nvda")
    tl.check(now=T0, notify=False)
    r = tl.check(now=T0 + 1, notify=False)
    assert r["events"] == []
    assert sum(1 for _ in open(tl.EVENTS_PATH)) if os.path.exists(tl.EVENTS_PATH) else 0 == 0


def test_retencion_de_eventos(tl):
    tl.append_line(tl.EVENTS_PATH, json.dumps({"detected_ts": T0 - 200 * 86400}) + "\n")
    tl.append_line(tl.EVENTS_PATH, json.dumps({"detected_ts": T0}) + "\n")
    r = tl.prune_events(now=T0 + 60)
    assert r == {"kept": 1, "dropped": 1}
    assert sum(1 for _ in open(tl.EVENTS_PATH)) == 1


def test_audit_no_inventa_porcentaje(tl):
    c = sqlite3.connect(tl.DB)
    c.execute("CREATE TABLE signals(id INTEGER PRIMARY KEY, ts_epoch REAL, symbol TEXT)")
    c.execute("INSERT INTO signals(ts_epoch, symbol) VALUES(?,?)", (T0, "NVDA"))
    c.commit()
    c.close()
    a = tl.audit()
    assert a["events"] == 0 and a["signals"] == 1
    assert a["pct_dirty"] is None, "sin eventos NO se publica 0% (eso seria afirmar limpieza)"


def test_context_blob_devuelve_none_no_ceros(tl):
    """Contexto congelado de un sym sin ficheros: todo None, ningun 0 plausible."""
    blob = tl.context_blob("ZZZZ", now=T0)
    assert blob["bars_sha"] is None and blob["spot"] is None
    assert blob["nbbo_bid"] is None and blob["levels"] is None
    assert blob["lock_ts"] == T0


def test_formato_real_de_barras_del_repo(tl):
    """Guarda de contrato con ibkr_bar_bridge: si cambia el formato de barras, muere aqui."""
    import glob as g
    real = [p for p in g.glob(os.path.join(REPO, "data", "bars_*_ibkr.txt"))
            if os.path.getsize(p) > 100]
    if not real:
        pytest.skip("sin barras vivas")
    with open(real[0]) as f:
        assert tl.parse_bar(f.readline()) is not None


def test_ventana_que_rueda_por_retencion_no_es_repintado(tl):
    """El bridge guarda 2 dias rodantes: si la ventana congelada cae por el frente del
    fichero eso es retencion, NO repintado (bug cazado por el test de crecimiento)."""
    start = T0 - 130 * 60
    _bars(tl, "nvda", n=130, start=start)
    tl.check(now=T0, notify=False)
    # el fichero se rehace empezando 100 minutos mas tarde (lo viejo rodo fuera)
    _bars(tl, "nvda", n=130, start=start + 100 * 60)
    r = tl.check(now=T0 + 100 * 60, notify=False)
    assert r["events"] == []
    assert r["syms"]["NVDA"]["rolled_off"] > 0
