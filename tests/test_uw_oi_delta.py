"""test_uw_oi_delta.py — volumen vs ΔOI dia-sobre-dia (sin red).

Lo que importa: (1) el OI es el CIERRE DE AYER, asi que dos snapshots con la misma fecha as-of
LEVANTAN en vez de devolver ΔOI=0 ("no hubo aperturas" seria mentira); (2) las etiquetas
NUEVA/SALIDA/CHURN son las de la regla V≈+ΔOI / V≈−ΔOI / V>>|ΔOI|; (3) volumen insuficiente da
N/D, nunca CHURN por defecto; (4) un contrato ausente del snapshot previo se OMITE (OI_prev
ausente != 0) y un fichero vacio levanta en vez de pasar por "ese dia no hubo cambios".
"""
import datetime as dt
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import uw_oi_delta as od  # noqa: E402


# ---------- fecha as-of del OI (el corazon del asunto) ----------

def test_asof_snapshot_de_cierre_es_la_vispera():
    # lunes 16:20: el OI del propio lunes lo publica la OCC el martes -> as-of = viernes
    assert od.oi_asof(dt.datetime(2026, 7, 27, 16, 20)) == dt.date(2026, 7, 24)


def test_asof_premarket_del_dia_siguiente_ya_trae_el_cierre_anterior():
    assert od.oi_asof(dt.datetime(2026, 7, 28, 8, 45)) == dt.date(2026, 7, 27)


def test_asof_fin_de_semana_se_queda_en_el_viernes():
    assert od.oi_asof(dt.datetime(2026, 7, 25, 16, 20)) == dt.date(2026, 7, 24)
    assert od.oi_asof(dt.datetime(2026, 7, 26, 16, 20)) == dt.date(2026, 7, 24)


def test_asof_antes_de_las_siete_aun_no_tiene_el_cierre_de_ayer():
    assert od.oi_asof(dt.datetime(2026, 7, 28, 3, 51)) == dt.date(2026, 7, 24)


# ---------- etiquetas ----------

def test_volumen_igual_a_delta_oi_es_posicion_nueva():
    assert od.classify(9800, 10000)[0] == "NUEVA"


def test_volumen_igual_a_menos_delta_oi_es_salida():
    lab, r = od.classify(-9800, 10000)
    assert lab == "SALIDA" and r < 0


def test_volumen_muy_mayor_que_delta_oi_es_churn():
    # el caso real de la killlist: QQQ 0DTE, vol 238.672 vs ΔOI 2.348
    assert od.classify(2348, 238672)[0] == "CHURN"


def test_zona_intermedia_es_mixto_no_se_fuerza_a_un_lado():
    assert od.classify(3500, 10000)[0] == "MIXTO"


def test_volumen_insuficiente_es_nd_jamas_churn():
    lab, _ = od.classify(1, 10)
    assert lab == "N/D"


def test_sin_delta_oi_es_nd_no_cero():
    assert od.classify(None, 10000) == ("N/D", None)


def test_parse_contract_occ():
    assert od.parse_contract("QQQ260731P00644000") == ("QQQ", dt.date(2026, 7, 31), "P", 644.0)
    assert od.parse_contract("O:QQQ260727C00605000")[3] == 605.0


def test_parse_contract_basura_es_none_no_adivina():
    assert od.parse_contract("QQQ-JULY-644-PUT") is None


# ---------- fuente uw ----------

def _uw_doc(rows):
    return {"_meta": {"fuente": "unusual_whales_trial"}, "payload": {"data": rows}}


def _row(**kw):
    r = {"option_symbol": "MU260731P00550000", "curr_date": "2026-07-24", "volume": 14462,
         "oi_diff_plain": 10172, "curr_oi": 10420, "last_oi": 248,
         "prev_ask_volume": 9000, "prev_bid_volume": 1000, "prev_total_premium": "2289185.00"}
    r.update(kw)
    return r


def test_uw_etiqueta_con_el_oi_de_ayer(tmp_path, monkeypatch):
    d = tmp_path / "2026-07-27"
    d.mkdir()
    (d / "uw_oi_change_mu.json").write_text(json.dumps(_uw_doc([_row()])))
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    rows = od.from_uw("MU", "2026-07-27")
    assert len(rows) == 1
    r = rows[0]
    assert r["session"] == "2026-07-24" and r["oi_prev"] == 248
    assert r["delta_oi"] == 10172 and r["label"] == "NUEVA"
    assert abs(r["ratio"] - 10172 / 14462) < 1e-9
    assert abs(r["ask_share"] - 0.9) < 1e-9


def test_uw_fichero_vacio_levanta_no_devuelve_lista_vacia(tmp_path, monkeypatch):
    d = tmp_path / "2026-07-27"
    d.mkdir()
    (d / "uw_oi_change_mu.json").write_text(json.dumps(_uw_doc([])))
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    with pytest.raises(RuntimeError, match="0 filas"):
        od.from_uw("MU", "2026-07-27")


def test_uw_fila_sin_volumen_se_omite_no_se_rellena(tmp_path, monkeypatch):
    d = tmp_path / "2026-07-27"
    d.mkdir()
    (d / "uw_oi_change_mu.json").write_text(json.dumps(_uw_doc([_row(volume=None), _row()])))
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    assert len(od.from_uw("MU", "2026-07-27")) == 1


# ---------- fuente polygon ----------

def _chain(snap_local, contracts):
    return {"meta": {"sym": "QQQ", "snapshot_local": snap_local},
            "results": [{"details": {"ticker": t, "contract_type": ct, "strike_price": k,
                                     "expiration_date": exp},
                         "open_interest": oi, "day": {"volume": vol}}
                        for t, ct, k, exp, oi, vol in contracts]}


def _write_pair(tmp_path, snap_a, snap_b, ca, cb):
    for date_s, snap, cs in ((snap_a[:10], snap_a, ca), (snap_b[:10], snap_b, cb)):
        d = tmp_path / date_s
        d.mkdir(exist_ok=True)
        (d / "chain_full_qqq.json").write_text(json.dumps(_chain(snap, cs)))


def test_polygon_delta_oi_dia_sobre_dia(tmp_path, monkeypatch):
    # snapshot lunes 16:20 (vol del lunes + OI del viernes) vs martes 08:45 (OI del lunes)
    ca = [("O:QQQ260814C00700000", "call", 700, "2026-08-14", 5000, 9500)]
    cb = [("O:QQQ260814C00700000", "call", 700, "2026-08-14", 14200, 120)]
    _write_pair(tmp_path, "2026-07-27T16:20:00", "2026-07-28T08:45:00", ca, cb)
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    rows = od.from_polygon("QQQ", "2026-07-27", "2026-07-28")
    assert len(rows) == 1
    assert rows[0]["session"] == "2026-07-27"
    assert rows[0]["delta_oi"] == 9200 and rows[0]["volume"] == 9500
    assert rows[0]["label"] == "NUEVA"


def test_polygon_dos_snapshots_del_mismo_oi_levantan(tmp_path, monkeypatch):
    # sabado y domingo traen los DOS el OI del viernes: ΔOI=0 seria una mentira
    c = [("O:QQQ260814C00700000", "call", 700, "2026-08-14", 5000, 9500)]
    _write_pair(tmp_path, "2026-07-25T16:20:00", "2026-07-26T16:20:00", c, c)
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    with pytest.raises(RuntimeError, match="no son sesiones consecutivas"):
        od.from_polygon("QQQ", "2026-07-25", "2026-07-26")


def test_polygon_contrato_ausente_del_snapshot_previo_se_omite(tmp_path, monkeypatch):
    ca = [("O:QQQ260814C00700000", "call", 700, "2026-08-14", 5000, 9500)]
    cb = [("O:QQQ260814C00700000", "call", 700, "2026-08-14", 14200, 120),
          ("O:QQQ260814C00900000", "call", 900, "2026-08-14", 700, 700)]
    _write_pair(tmp_path, "2026-07-27T16:20:00", "2026-07-28T08:45:00", ca, cb)
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    rows = od.from_polygon("QQQ", "2026-07-27", "2026-07-28")
    assert [r["contract"] for r in rows] == ["O:QQQ260814C00700000"]


def test_polygon_vencido_en_la_sesion_se_excluye(tmp_path, monkeypatch):
    ca = [("O:QQQ260727C00700000", "call", 700, "2026-07-27", 5000, 90000)]
    cb = [("O:QQQ260727C00700000", "call", 700, "2026-07-27", 0, 0)]
    _write_pair(tmp_path, "2026-07-27T16:20:00", "2026-07-28T08:45:00", ca, cb)
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    with pytest.raises(RuntimeError, match="ningun contrato comparable"):
        od.from_polygon("QQQ", "2026-07-27", "2026-07-28")


def test_polygon_sin_snapshot_local_levanta(tmp_path, monkeypatch):
    d = tmp_path / "2026-07-27"
    d.mkdir()
    doc = _chain("2026-07-27T16:20:00", [("O:QQQ260814C00700000", "call", 700, "2026-08-14", 1, 1)])
    del doc["meta"]["snapshot_local"]
    (d / "chain_full_qqq.json").write_text(json.dumps(doc))
    monkeypatch.setattr(od, "HIST", str(tmp_path))
    with pytest.raises(RuntimeError, match="snapshot_local"):
        od._load_chain("2026-07-27", "QQQ")
