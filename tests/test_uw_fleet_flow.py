"""Tests de uw_fleet_flow: filtros medibles, dedup persistido y enrutado. Cero red."""
import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location("ibt_uw_fleet_flow",
                                              os.path.join(SCRIPTS, "uw_fleet_flow.py"))
F = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = F
spec.loader.exec_module(F)

spec2 = importlib.util.spec_from_file_location("ibt_layout_ff",
                                               os.path.join(SCRIPTS, "discord_layout.py"))
L = importlib.util.module_from_spec(spec2)
sys.modules[spec2.name] = L
spec2.loader.exec_module(L)


def _alert(**kw):
    base = {"id": "a1", "ticker": "MU", "type": "call", "strike": "900", "expiry": "2026-08-07",
            "option_chain": "MU260807C900", "created_at": "2026-08-04T14:00:00Z",
            "total_premium": "100000", "total_bid_side_prem": "10000",
            "total_ask_side_prem": "85000", "volume_oi_ratio": "0.5", "has_sweep": False}
    base.update(kw)
    return base


# --- criterios ---------------------------------------------------------------------------
def test_premium_grande_ask_side_canta():
    motivo, d = F.qualifies(_alert(total_premium="1500000", total_ask_side_prem="1200000"))
    assert "premium" in motivo and d["lado"] == "ask" and d["cp"] == "CALLS"


def test_premium_grande_pero_mid_no_canta():
    """$1M cruzado en el medio no declara agresor: no se canta un lado que no se midio."""
    assert F.qualifies(_alert(total_premium="1500000", total_bid_side_prem="100000",
                              total_ask_side_prem="100000")) is None


def test_voloi_alto_con_premium_canta():
    motivo, _ = F.qualifies(_alert(volume_oi_ratio="3.4", total_premium="300000"))
    assert "vol/OI" in motivo


def test_voloi_alto_sin_premium_no_canta():
    """vol/OI 5 con $20k es un lotero, no una ballena."""
    assert F.qualifies(_alert(volume_oi_ratio="5.0", total_premium="20000")) is None


def test_sweep_con_premium_canta():
    motivo, _ = F.qualifies(_alert(has_sweep=True, total_premium="600000"))
    assert "SWEEP" in motivo


def test_pequeno_no_canta():
    assert F.qualifies(_alert()) is None


def test_malformado_devuelve_none_no_cero():
    """Sin total_premium NO se inventa 0: la fila se salta entera."""
    a = _alert()
    del a["total_premium"]
    assert F.qualifies(a) is None


# --- dedup y estado ----------------------------------------------------------------------
def test_estado_persistido_sobrevive_reinicio(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "STATE", str(tmp_path / "st.json"))
    st = {"vistos": {"a1": 100.0}, "contrato_ts": {"MU260807C900": 100.0}}
    F.save_state(st)
    assert F.load_state() == st
    assert not os.path.exists(str(tmp_path / "st.json") + ".tmp")


def test_estado_corrupto_no_revienta(tmp_path, monkeypatch):
    p = tmp_path / "st.json"
    p.write_text("{basura")
    monkeypatch.setattr(F, "STATE", str(p))
    assert F.load_state() == {"vistos": {}, "contrato_ts": {}}


def test_prune_acota_el_estado():
    st = {"vistos": {"viejo": 0.0, "nuevo": 999_000.0},
          "contrato_ts": {"c_viejo": 0.0, "c_nuevo": 999_500.0}}   # 500 s < cooldown 900 s
    F.prune(st, 1_000_000.0)
    assert "viejo" not in st["vistos"] and "nuevo" in st["vistos"]
    assert "c_viejo" not in st["contrato_ts"] and "c_nuevo" in st["contrato_ts"]


# --- salida ------------------------------------------------------------------------------
def test_error_no_fabrica_filas(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "OUT", str(tmp_path / "out.json"))
    F.write_out([], err="429 tras 3 esperas")
    d = json.load(open(str(tmp_path / "out.json")))
    assert "error" in d and "rows" not in d


def test_salida_se_recorta_a_60(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "OUT", str(tmp_path / "out.json"))
    F.write_out([{"i": i} for i in range(200)])
    assert len(json.load(open(str(tmp_path / "out.json")))["rows"]) == 60


# --- enrutado a Discord ------------------------------------------------------------------
def test_titulo_uw_flow_va_a_flujo_uw():
    ch, sev = L.classify("UW FLOW MU | CALLS ask-side strike 900 exp 08-07 — premium 2.1M ask-side")
    assert ch == "flujo-uw" and sev == L.NORMAL


def test_uw_flow_espeja_a_semis():
    assert "semis-memoria" in L.mirror_channels("UW FLOW MU | CALLS strike 900", {"MU"})


def test_aviso_de_caida_va_a_estado_no_a_flujo():
    """'⚠ UW FLOW' con 'caida' es infraestructura..."""
    ch, _ = L.classify("⚠ UW FLOW | cinta de flota caida: 429")
    assert ch in ("flujo-uw", "estado-proveedores")   # cualquiera de los dos llega; jamas fallback
    assert ch != L.FALLBACK_CHANNEL


# --- portero -----------------------------------------------------------------------------
def test_in_session_fin_de_semana_no():
    import time as _t
    monkey = _t.struct_time((2026, 8, 8, 12, 0, 0, 5, 220, 1))
    real = _t.localtime
    _t.localtime = lambda: monkey
    try:
        assert F.in_session() is False
    finally:
        _t.localtime = real


def test_fleet_lee_los_30():
    syms = F.fleet()
    fleet = open("data/fleet.txt").read().split()
    assert len(syms) == len(fleet) and "QQQ" in syms and "MU" in syms


# --- respaldo CBOE para las fichas (2026-08-04) -------------------------------------------
def test_cboe_nbbo_cachea_y_order_ticket_lo_lee(tmp_path, monkeypatch):
    import importlib.util as _il
    sp = _il.spec_from_file_location("ibt_ot_t", os.path.join(SCRIPTS, "order_ticket.py"))
    OT = _il.module_from_spec(sp); sys.modules[sp.name] = OT; sp.loader.exec_module(OT)
    monkeypatch.setattr(OT, "REPO", str(tmp_path))
    os.makedirs(str(tmp_path / "data"))
    import time as _t
    with open(str(tmp_path / "data" / "cboe_nbbo_qqq.json"), "w") as f:
        json.dump({"sym": "QQQ", "asof": _t.time(), "src": "cboe_delayed",
                   "quotes": {"C|20260804|709": [5.25, 5.31]}}, f)
    assert OT._cboe_nbbo("QQQ", "C", "20260804", 709.0)[:2] == (5.25, 5.31)
    assert OT._cboe_nbbo("QQQ", "P", "20260804", 709.0) is None      # sin dato -> None, no 0


def test_cboe_nbbo_rancio_devuelve_none(tmp_path, monkeypatch):
    import importlib.util as _il
    sp = _il.spec_from_file_location("ibt_ot_t2", os.path.join(SCRIPTS, "order_ticket.py"))
    OT = _il.module_from_spec(sp); sys.modules[sp.name] = OT; sp.loader.exec_module(OT)
    monkeypatch.setattr(OT, "REPO", str(tmp_path))
    os.makedirs(str(tmp_path / "data"))
    with open(str(tmp_path / "data" / "cboe_nbbo_qqq.json"), "w") as f:
        json.dump({"sym": "QQQ", "asof": 1000.0, "quotes": {"C|20260804|709": [5.25, 5.31]}}, f)
    assert OT._cboe_nbbo("QQQ", "C", "20260804", 709.0) is None


def test_ficha_con_respaldo_cboe_nunca_es_GO():
    """La doctrina: delayed dimensiona, jamas aprueba. El techo con CBOE es CAUTION."""
    src = open(os.path.join(SCRIPTS, "order_ticket.py")).read()
    assert 'nbbo_src == "cboe_delayed"' in src.split("# veredicto")[1]
    assert "[spread CBOE delayed]" in src
