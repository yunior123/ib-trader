import importlib.util
import ast
import os
import sys
import types

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "flow_bb_correlator_test", os.path.join(REPO, "scripts", "flow_bb_correlator.py"))
FBB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FBB)


def corr(tmp_path, window=180):
    return FBB.Correlator(str(tmp_path), window_s=window)


@pytest.mark.parametrize("side,direction,phrase", [
    ("PUTS", "UP", "rebote BB al alza"),
    ("CALLS", "DOWN", "retroceso BB a la baja"),
])
def test_bb_posterior_en_ventana_emite_actualizacion_espejo(tmp_path, side, direction, phrase):
    c = corr(tmp_path)
    assert c.record_flow(ts=1000, sym="NFLX", side=side, source="flow_pulse",
                         volume_scope="aggregate_delta", aggregate_volume=4000) is None

    match = c.record_bb(ts=1072, sym="NFLX", direction=direction,
                        timeframe="1m", price=72.31, target=72.24)

    assert match["age_s"] == 72
    update = FBB.linked_update(match)
    assert phrase in update["short"]
    assert "no prueba causalidad" in update["short"]
    assert "volumen agregado incremental (4,000 contratos)" in update["full"]


def test_bb_previa_fresca_enriquece_el_primer_flujo_sin_inventar_futuro(tmp_path):
    c = corr(tmp_path)
    c.record_bb(ts=1000, sym="AAPL", direction="DOWN", timeframe="5m")

    match = c.record_flow(ts=1045, sym="AAPL", side="CALLS", source="opt_whale_watch",
                          volume_scope="aggregate_strikes", aggregate_volume=9000,
                          dominant_strike=350)

    assert match["age_s"] == 45
    assert "BB fresca ya existente" in FBB.prior_bb_suffix(match)
    assert "no prueba causalidad" in FBB.prior_bb_suffix(match)


def test_bb_futura_jamas_enriquece_flujo_anterior(tmp_path):
    c = corr(tmp_path)
    # Simula un reloj/archivo adelantado: una BB con ts futuro no puede afirmarse al cantar flujo.
    c.record_bb(ts=1100, sym="QQQ", direction="UP", timeframe="1m")
    assert c.record_flow(ts=1000, sym="QQQ", side="PUTS", source="flow_pulse",
                         volume_scope="aggregate_delta") is None


def test_stale_no_correlaciona_en_ninguna_direccion(tmp_path):
    c = corr(tmp_path, window=180)
    c.record_bb(ts=1000, sym="QQQ", direction="UP", timeframe="1m")
    assert c.record_flow(ts=1181, sym="QQQ", side="PUTS", source="flow_pulse",
                         volume_scope="aggregate_delta") is None

    c2 = corr(tmp_path / "other", window=180)
    c2.record_flow(ts=1000, sym="QQQ", side="PUTS", source="flow_pulse",
                   volume_scope="aggregate_delta")
    assert c2.record_bb(ts=1181, sym="QQQ", direction="UP", timeframe="1m") is None


@pytest.mark.parametrize("side,direction", [("PUTS", "DOWN"), ("CALLS", "UP")])
def test_direccion_incompatible_no_correlaciona(tmp_path, side, direction):
    c = corr(tmp_path)
    c.record_flow(ts=1000, sym="NFLX", side=side, source="flow_pulse",
                  volume_scope="aggregate_delta")
    assert c.record_bb(ts=1072, sym="NFLX", direction=direction, timeframe="1m") is None


def test_dedup_una_sola_actualizacion_por_alerta_de_flujo(tmp_path):
    c = corr(tmp_path)
    c.record_flow(ts=1000, sym="NFLX", side="PUTS", source="flow_pulse",
                  volume_scope="aggregate_delta", event_id="flow-1")
    assert c.record_bb(ts=1072, sym="NFLX", direction="UP", timeframe="1m",
                       event_id="bb-1") is not None
    assert c.record_bb(ts=1080, sym="NFLX", direction="UP", timeframe="1m",
                       event_id="bb-2") is None


def test_strike_dominante_no_se_confunde_con_volumen_agregado(tmp_path):
    c = corr(tmp_path)
    c.record_flow(ts=1000, sym="NFLX", side="PUTS", source="opt_whale_watch",
                  volume_scope="aggregate_strikes", aggregate_volume=12000,
                  dominant_strike=70)
    match = c.record_bb(ts=1040, sym="NFLX", direction="UP", timeframe="1m")

    assert FBB.flow_detail(match["flow"]) == (
        "volumen agregado de los strikes escaneados; strike dominante $70")


def test_actualizacion_nflx_hace_push_sin_promover_voz_info(tmp_path, monkeypatch):
    """Ejecuta sólo say(), no importa el daemon top-level ni produce audio/banner real."""
    source = open(os.path.join(REPO, "scripts", "bollinger_alarm.py")).read()
    tree = ast.parse(source)
    say_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "say")
    module = ast.Module(body=[say_node], type_ignores=[])
    ast.fix_missing_locations(module)

    popen_calls, pushes = [], []

    class FakeSubprocess:
        DEVNULL = object()

        @staticmethod
        def Popen(argv, **kwargs):
            popen_calls.append(argv)
            return object()

    notify = types.ModuleType("notify_short")
    notify.push = lambda title, msg: pushes.append((title, msg))
    monkeypatch.setitem(sys.modules, "notify_short", notify)
    fake_script = tmp_path / "scripts" / "bollinger_alarm.py"
    fake_script.parent.mkdir()
    namespace = {
        "os": os, "time": __import__("time"), "subprocess": FakeSubprocess,
        "__file__": str(fake_script),
    }
    exec(compile(module, str(fake_script), "exec"), namespace)

    namespace["say"]("🔗 FLUJO + BB NFLX", "detalle", voice=False, prio="INFO",
                     voice_msg="actualización NFLX", push=True)

    assert pushes == [("🔗 FLUJO + BB NFLX", "actualización NFLX")]
    assert not any("scripts/speak.sh" in call for call in popen_calls)
    assert any(call[0] == "/usr/bin/osascript" for call in popen_calls)
