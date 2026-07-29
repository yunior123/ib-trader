#!/usr/bin/env python3
"""test_fleet_consensus.py — arnes de test de la alarma de MANADA (scripts/fleet_consensus.cpp).

Python aqui es SOLO arnes (orden Yunior 2026-07-25: "python solo para test, la computacion en
C++"). El calculo vive entero en el binario bin/fleet_consensus; estos tests le inyectan un
snapshot de flota por stdin con --ev-stdin y verifican su veredicto JSON. Cero computo en Python.

El test #1 es el BUG HISTORICO del 2026-07-25: 21 abajo + 4 simbolos sin datos + 5 arriba.
Con el denominador fabricado (21/26 = 80.8%) la alarma disparo 3 veces; sobre la flota completa
son 21/30 = 70% y NO debe disparar. Este archivo es la red que impide que vuelva a pasar.

Requiere el binario: ./scripts/build_fleet_consensus.sh
"""
import json
import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin", "fleet_consensus")
FLEET = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
CAPS = ["SPY", "QQQ", "SMH"]
NF = len(FLEET)

pytestmark = pytest.mark.skipif(
    not os.path.exists(BIN),
    reason="falta el binario bin/fleet_consensus — corre ./scripts/build_fleet_consensus.sh")


def run(ev, binary=None):
    """Inyecta el snapshot en el binario C++ y devuelve su veredicto."""
    p = subprocess.run([binary or BIN, "--ev-stdin"], input=json.dumps(ev),
                       capture_output=True, text=True, cwd=REPO, timeout=60)
    assert p.returncode == 0, "fleet_consensus fallo ({}): {}".format(p.returncode, p.stderr)
    return json.loads(p.stdout)


def sym(s, side, mom=None, **over):
    """Un simbolo votando `side` ('UP'/'DN'): el voto es el lado del flip."""
    up = side == "UP"
    d = {"sym": s, "spot": 100.0, "flip": 99.0 if up else 101.0,
         "mom": (0.5 if up else -0.5) if mom is None else mom, "bar_age": 10}
    d.update(over)
    return d


def snapshot(dn=0, up=0, dead=0, caps_side="DN", now_min=600, **top):
    """Reparte la flota: `dn` abajo, `up` arriba, `dead` sin datos. Los 3 capitanes votan
    `caps_side` (van dentro de la cuota correspondiente)."""
    pool = [s for s in FLEET if s not in CAPS]
    syms, i = [], 0
    want = {"DN": dn, "UP": up}
    for c in CAPS:
        if want[caps_side] <= 0:
            raise AssertionError("cuota insuficiente para los capitanes")
        want[caps_side] -= 1
        syms.append(sym(c, caps_side))
    for side in ("DN", "UP"):
        for _ in range(want[side]):
            syms.append(sym(pool[i], side)); i += 1
    for _ in range(dead):
        syms.append({"sym": pool[i], "have_bars": False}); i += 1
    ev = {"syms": syms, "now_min": now_min}
    ev.update(top)
    return ev


# ---------------------------------------------------------------- 1. el bug historico
def test_bug_historico_21_de_30_no_dispara():
    r = run(snapshot(dn=21, up=5, dead=4))
    assert r["dn"] == 21 and r["up"] == 5 and r["n"] == 26
    assert r["consensus"] is None, "21/30 = 70% JAMAS debe dar consenso"
    assert r["fired"] is False
    assert "cobertura" in r["why"], r["why"]
    assert "26/30" in r["why"] and "min 27" in r["why"], r["why"]


# ---------------------------------------------------------------- 2. el caso que SI dispara
def test_24_de_30_con_cobertura_y_capitanes_dispara():
    ev = snapshot(dn=24, up=3, dead=3)
    r = run(ev)
    assert r["n"] == 27 and r["dn"] == 24
    assert r["consensus"] == "DN", r["why"]
    assert "24/30 = 80%" in r["why"], r["why"]
    assert r["fired"] is False, "primer ciclo: histeresis"
    # segundo ciclo consecutivo -> disparo
    ev2 = dict(ev, pending="DN", pend_cnt=1)
    assert run(ev2)["fired"] is True


# ---------------------------------------------------------------- 3. cobertura 26/30 = FEED
def test_cobertura_26_es_feed_no_direccion():
    r = run(snapshot(dn=26, up=0, dead=4))
    assert r["n"] == 26
    assert r["consensus"] is None
    assert "FEED" in r["why"] and "no direccion" in r["why"], r["why"]


# ---------------------------------------------------------------- 4. barras rancias
def test_barras_rancias_no_votan_y_salen_en_skipped():
    ev = snapshot(dn=27, up=0, dead=0)
    victima = ev["syms"][5]["sym"]
    ev["syms"][5]["bar_age"] = 900          # 15 min > MAX_BAR_AGE 180 s
    r = run(ev)
    assert victima in r["skipped"], r["skipped"]
    assert "rancias" in r["skipped"][victima], r["skipped"][victima]
    assert r["n"] == 26, "la barra rancia no vota, pero el denominador sigue siendo 30"
    assert r["consensus"] is None and "cobertura" in r["why"]


# ---------------------------------------------------------------- 5. capitanes divididos
def test_capitanes_divididos_sin_consenso():
    ev = snapshot(dn=30, up=0)
    for s in ev["syms"]:
        if s["sym"] == "SMH":
            s.update(sym("SMH", "UP"))
    r = run(ev)
    assert r["n"] == 30 and r["dn"] == 29
    assert r["consensus"] is None
    assert r["why"] == "capitanes divididos", r["why"]
    assert r["fired"] is False


# ---------------------------------------------------------------- 6. falta un capitan
def test_falta_un_capitan_sin_consenso():
    ev = snapshot(dn=30, up=0)
    for s in ev["syms"]:
        if s["sym"] == "SMH":
            s.clear(); s.update({"sym": "SMH", "have_bars": False})
    r = run(ev)
    assert r["n"] == 29 and len(r["caps"]) == 2
    assert r["consensus"] is None
    assert "faltan capitanes (2/3)" == r["why"], r["why"]


# ---------------------------------------------------------------- 7. fuera de ventana
def test_fuera_de_ventana_no_dispara():
    ev = snapshot(dn=30, up=0, now_min=0)      # 00:00 — el artefacto de rollover de fecha
    r = run(ev)
    assert r["consensus"] == "DN", "el consenso existe..."
    assert r["in_window"] is False
    assert r["fired"] is False, "...pero fuera de 09:25-16:05 no se dispara"
    # con la misma flota dentro de ventana y un ciclo previo, si dispara
    r2 = run(dict(snapshot(dn=30, up=0, now_min=600), pending="DN", pend_cnt=1))
    assert r2["fired"] is True


# ---------------------------------------------------------------- 8. histeresis
def test_histeresis_dos_ciclos_y_rearme():
    ev = snapshot(dn=30, up=0)
    c1 = run(ev)
    assert c1["fired"] is False
    assert c1["hyst"] == {"last": None, "pending": "DN", "pend_cnt": 1}
    c2 = run(dict(ev, pending=c1["hyst"]["pending"], pend_cnt=c1["hyst"]["pend_cnt"]))
    assert c2["fired"] is True, "2 ciclos consecutivos = disparo"
    assert c2["hyst"]["last"] == "DN" and c2["hyst"]["pend_cnt"] == 0
    # ya disparada: no repite mientras el consenso siga siendo el mismo
    c3 = run(dict(ev, last="DN"))
    assert c3["fired"] is False
    # consenso roto -> se re-arma (last/pending a cero)
    roto = snapshot(dn=15, up=15)
    c4 = run(dict(roto, last="DN", pending="DN", pend_cnt=1))
    assert c4["consensus"] is None and c4["fired"] is False
    assert c4["hyst"] == {"last": None, "pending": None, "pend_cnt": 0}
    # y desde cero vuelve a necesitar 2 ciclos
    c5 = run(ev)
    assert c5["fired"] is False
    assert run(dict(ev, pending="DN", pend_cnt=1))["fired"] is True


# ---------------------------------------------------------------- 9. mapa GEX corrupto
def test_levels_json_truncado_va_a_skipped_sin_crash(tmp_path):
    bueno = tmp_path / "levels_ok.json"
    bueno.write_text('{\n "sym": "X",\n "spot": 100.0,\n "flip": 99.0\n}')
    malo = tmp_path / "levels_trunc.json"
    malo.write_text('{\n "sym": "X",\n "spot": 100.0,\n "fl')      # json.dump a medias
    ev = snapshot(dn=30, up=0)
    ev["syms"][3].pop("flip"); ev["syms"][3]["levels_file"] = str(bueno)
    ev["syms"][4].pop("flip"); ev["syms"][4]["levels_file"] = str(malo)
    ev["syms"][5].pop("flip"); ev["syms"][5]["levels_file"] = str(tmp_path / "no_existe.json")
    victima, ausente = ev["syms"][4]["sym"], ev["syms"][5]["sym"]
    r = run(ev)
    assert "flip" in r["skipped"][victima], r["skipped"][victima]
    assert "mapa GEX" in r["skipped"][ausente], r["skipped"][ausente]
    assert r["no_levels"] == 2
    assert r["n"] == 28, "el mapa bueno si vota"
    # el que leyo el mapa bueno voto ARRIBA (spot 100 >= flip 99)
    lados = {v["sym"]: v["side"] for v in r["votes"]}
    assert lados[ev["syms"][3]["sym"]] == 1


def test_levels_ausentes_en_mas_del_10_por_ciento_es_feed(tmp_path):
    """(c) del contrato: mapa GEX ausente/rancio en >10% de la flota = sin veredicto."""
    ev = snapshot(dn=30, up=0)
    for s in ev["syms"][:4]:
        s.pop("flip"); s["levels_file"] = str(tmp_path / "no_existe.json")
    r = run(dict(ev, **{}))
    assert r["no_levels"] == 4
    assert r["consensus"] is None
    assert "FEED" in r["why"], r["why"]


# ---------------------------------------------------------------- 10. snapshot vacio
def test_snapshot_vacio_sin_crash_y_sin_veredicto():
    r = run({"syms": [], "now_min": 600})
    assert r["n"] == 0 and r["up"] == 0 and r["dn"] == 0
    assert r["consensus"] is None and r["fired"] is False
    assert len(r["skipped"]) == NF, "los 30 ausentes tienen nombre y motivo"
    assert "cobertura insuficiente 0/{}".format(NF) in r["why"]


def test_json_basura_no_crashea():
    p = subprocess.run([BIN, "--ev-stdin"], input="{{{ esto no es json ]]]",
                       capture_output=True, text=True, cwd=REPO, timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert r["consensus"] is None and r["fired"] is False


# ------------------------------------------------- camino de PRODUCCION (ficheros reales)
def test_produccion_lee_ficheros_y_dispara(tmp_path):
    """Ejercita el camino real: data/fleet.txt + data/bars_<sym>_ibkr.txt + el mapa GEX de
    charts/data/levels_<sym>.json, con dos ciclos de 1 s (histeresis) y FLEET_CONS_DRY=1 para no
    hablar ni notificar. Es lo que --ev-stdin NO cubre: I/O, frescura por mtime y fire()."""
    import time
    (tmp_path / "data").mkdir()
    (tmp_path / "charts" / "data").mkdir(parents=True)
    (tmp_path / "data" / "fleet.txt").write_text("SPY QQQ SMH\n")
    t0 = int(time.time()) - 600
    for s in ("spy", "qqq", "smh"):
        # 8 barras cayendo: cierre final 99.2, momentum negativo
        rows = ["{} 100 100 100 {:.2f} 1000".format(t0 + i * 60, 100.0 - i * 0.1) for i in range(8)]
        (tmp_path / "data" / "bars_{}_ibkr.txt".format(s)).write_text("\n".join(rows) + "\n")
        (tmp_path / "charts" / "data" / "levels_{}.json".format(s)).write_text(
            '{\n "sym": "%s",\n "spot": 100.0,\n "flip": 101.0\n}' % s.upper())
    env = dict(os.environ, FLEET_CONS_DRY="1",
               FLEET_CONS_WIN_OPEN="0", FLEET_CONS_WIN_CLOSE="1440")
    p = subprocess.Popen([BIN, "--daemon", "--loop", "1"], cwd=str(tmp_path), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2.5)
    p.terminate()
    out = p.communicate(timeout=10)[0]
    assert "flota 0↑/3↓ de 3" in out, out
    assert "consenso=DN [3/3 = 100%]" in out, out
    assert "[DRY] VOZ | Manada bajista: la flota se puso de acuerdo. Comprar puts." in out, out
    assert "🐘 MANADA BAJISTA 📉: 3/3 de la flota alineados ABAJO del flip" in out, out
    assert "comprar PUTS" in out and "optgate" in out
    assert "[consensus] DISPARADA DN: 3/3" in out, out
    assert out.count("[DRY] BANNER") == 1, "una sola vez: solo en la TRANSICION a consenso"
    # la linea del ledger lleva los marcadores que filtra notify_relay.sh (🐘 / MANADA)
    ledger = [l for l in out.splitlines() if l.startswith("[DRY] LEDGER")][0]
    assert "🐘" in ledger and "MANADA" in ledger
    cuerpo = ledger.split("| ", 1)[1]
    assert len(cuerpo.encode()) < 512, "la linea debe caber en PIPE_BUF (append atomico)"


def test_universo_mapa_no_se_cuela_en_el_denominador_de_manada(tmp_path):
    """El bug del 25-jul fue un denominador FABRICADO (21/26 en vez de 21/30). El riesgo
    gemelo, ahora que existe `data/universe_gamma.txt` (35 = flota + SPX/XSP/NDX/DIA/IWM,
    docs/UNIVERSOS.md), es que ese fichero se cuele como fuente del denominador de MANADA y
    lo INFLE al reves: 3/8 en vez de 3/3. `load_fleet` de fleet_consensus.cpp solo conoce
    `data/fleet.txt` — este test lo deja escrito: los 5 simbolos del universo-mapa (con
    barras y mapa GEX propios, para que SI pudieran votar si se colasen) jamas aparecen en
    la flota, el denominador ni los votos."""
    import time
    (tmp_path / "data").mkdir()
    (tmp_path / "charts" / "data").mkdir(parents=True)
    (tmp_path / "data" / "fleet.txt").write_text("SPY QQQ SMH\n")
    (tmp_path / "data" / "universe_gamma.txt").write_text(
        "SPY QQQ SMH SPX XSP NDX DIA IWM\n")
    t0 = int(time.time()) - 600
    solo_mapa = ("spx", "xsp", "ndx", "dia", "iwm")
    for s in ("spy", "qqq", "smh") + solo_mapa:
        rows = ["{} 100 100 100 {:.2f} 1000".format(t0 + i * 60, 100.0 - i * 0.1) for i in range(8)]
        (tmp_path / "data" / "bars_{}_ibkr.txt".format(s)).write_text("\n".join(rows) + "\n")
        (tmp_path / "charts" / "data" / "levels_{}.json".format(s)).write_text(
            '{\n "sym": "%s",\n "spot": 100.0,\n "flip": 101.0\n}' % s.upper())
    p = subprocess.run([BIN, "--once"], cwd=str(tmp_path), capture_output=True, text=True,
                       env=dict(os.environ, FLEET_CONS_DRY="1",
                                FLEET_CONS_WIN_OPEN="0", FLEET_CONS_WIN_CLOSE="1440"),
                       timeout=20)
    assert p.returncode == 0, p.stderr
    assert "flota 0↑/3↓ de 3" in p.stdout, p.stdout
    assert "consenso=DN [3/3 = 100%]" in p.stdout, p.stdout
    for sym in ("SPX", "XSP", "NDX", "DIA", "IWM"):
        assert sym not in p.stdout, (
            f"{sym} (universo del mapa) se colo en el veredicto de MANADA:\n{p.stdout}")


def test_produccion_mapa_gex_rancio_no_vota(tmp_path):
    """Mapa GEX viejo = flip calculado a otro spot -> ese simbolo no vota (gate (b))."""
    import os as _os
    import time
    (tmp_path / "data").mkdir()
    (tmp_path / "charts" / "data").mkdir(parents=True)
    (tmp_path / "data" / "fleet.txt").write_text("SPY QQQ SMH\n")
    t0 = int(time.time()) - 600
    for s in ("spy", "qqq", "smh"):
        rows = ["{} 100 100 100 {:.2f} 1000".format(t0 + i * 60, 100.0 - i * 0.1) for i in range(8)]
        (tmp_path / "data" / "bars_{}_ibkr.txt".format(s)).write_text("\n".join(rows) + "\n")
        lp = tmp_path / "charts" / "data" / "levels_{}.json".format(s)
        lp.write_text('{\n "flip": 101.0\n}')
        if s == "smh":                              # mapa de hace 1 h
            viejo = time.time() - 3600
            _os.utime(str(lp), (viejo, viejo))
    p = subprocess.run([BIN, "--once"], cwd=str(tmp_path), capture_output=True, text=True,
                       env=dict(os.environ, FLEET_CONS_DRY="1"), timeout=20)
    assert p.returncode == 0, p.stderr
    assert "SMH=mapa GEX rancio (60min)" in p.stdout, p.stdout
    assert "flota 0↑/2↓ de 3" in p.stdout, p.stdout
    # el gate (c) manda antes que el de capitanes: 1/3 sin mapa es >10% de la flota
    assert "mapa GEX ausente/rancio en 1/3 (>10%) — esto es FEED, no direccion" in p.stdout
    assert "consenso=no" in p.stdout and "[DRY]" not in p.stdout


# ------------------------------------------------- ASan: memoria limpia con basura y vacio
ASAN = os.path.join(REPO, "bin", "fleet_consensus_asan")


@pytest.mark.skipif(not os.path.exists(ASAN), reason="falta bin/fleet_consensus_asan")
@pytest.mark.parametrize("payload", ["", "{}", "{{{ basura ]]]", '{"syms":[{"sym":"QQQ"}]}'])
def test_asan_sin_errores(payload):
    p = subprocess.run([ASAN, "--ev-stdin"], input=payload, capture_output=True,
                       text=True, cwd=REPO, timeout=120)
    assert p.returncode == 0, p.stderr
    assert "ERROR: AddressSanitizer" not in p.stderr
    assert "runtime error" not in p.stderr


@pytest.mark.skipif(not os.path.exists(ASAN), reason="falta bin/fleet_consensus_asan")
def test_asan_con_el_bug_historico():
    r = run(snapshot(dn=21, up=5, dead=4), binary=ASAN)
    assert r["consensus"] is None
