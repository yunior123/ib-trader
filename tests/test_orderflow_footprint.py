"""Motor C++ de footprint: el test conduce el binario real, no reimplementa la lógica."""
import json
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def footprint_bin(tmp_path_factory):
    out = tmp_path_factory.mktemp("footprint_bin") / "orderflow_footprint"
    subprocess.run([
        "clang++", "-std=c++23", "-O2", "-Wall", "-Wextra",
        str(ROOT / "scripts/orderflow_footprint.cpp"), "-o", str(out),
    ], check=True)
    return out


def run_engine(binp, tmp_path, rows):
    tape = tmp_path / "footprint_tape_qqq.txt"
    tape.write_text("\n".join(rows) + "\n")
    p = subprocess.run(
        [str(binp), "--input", str(tape), "--sym", "QQQ", "--out", "-"],
        check=True, text=True, capture_output=True,
    )
    return json.loads(p.stdout)


def row(t, px, size, side, bid=None, ask=None):
    bid = px - 0.01 if bid is None else bid
    ask = px + 0.01 if ask is None else ask
    return f"{t:.6f} {px:.6f} {size:.6f} {side} {bid:.6f} {ask:.6f}"


def kinds(bar):
    return {(p["kind"], p["side"], p["status"]) for p in bar["patterns"]}


def test_bid_ask_delta_unknown_and_closed_contract(footprint_bin, tmp_path):
    base = int(time.time() // 60) * 60 - 180
    data = run_engine(footprint_bin, tmp_path, [
        row(base + 1, 100.00, 12, -1),
        row(base + 2, 100.01, 20, 1),
        row(base + 3, 100.01, 7, 0),
    ])
    bar = data["timeframes"]["60"]["bars"][-1]
    assert data["source"] == "normalized execution tape"
    assert data["quality"] == "FULL_EXECUTION_TAPE"
    assert data["side_provenance"] == "INFERRED"
    assert data["native_side_pct"] == 0
    assert data["unknown_pct"] == pytest.approx(100 * 7 / 39, abs=0.01)
    assert bar["bid"] == 12 and bar["ask"] == 20 and bar["unknown"] == 7
    assert bar["delta"] == 8 and bar["volume"] == 39 and bar["closed"] is True
    assert data["classification_pct"] == pytest.approx(100 * 32 / 39, abs=0.01)


def test_three_adjacent_diagonal_imbalances_form_stack(footprint_bin, tmp_path):
    base = int(time.time() // 60) * 60 - 180
    rows = [row(base + i, 100.00 + i * 0.01, 30, 1) for i in range(1, 4)]
    bar = run_engine(footprint_bin, tmp_path, rows)["timeframes"]["60"]["bars"][-1]
    assert ("STACKED_IMBALANCE", "BULLISH", "BAR_CLOSED") in kinds(bar)
    marked = [c for c in bar["cells"] if c["buy_imb"]]
    assert len(marked) == 3


def test_delta_flip_is_forming_intrabar_then_closed(footprint_bin, tmp_path):
    minute = int(time.time() // 60) * 60
    # Precio sube, pero vendedores agresivos dominan: cambio de delta bajista.
    rows = [row(minute + 1, 100.00, 80, -1), row(minute + 2, 100.02, 5, 1)]
    forming = run_engine(footprint_bin, tmp_path, rows)["timeframes"]["60"]["bars"][-1]
    assert ("DELTA_FLIP", "BEARISH", "FORMING") in kinds(forming)
    # El mismo patrón en una vela pasada queda sellado como BAR_CLOSED.
    past = [r.replace(str(minute + 1), str(minute - 119), 1)
              .replace(str(minute + 2), str(minute - 118), 1) for r in rows]
    closed = run_engine(footprint_bin, tmp_path, past)["timeframes"]["60"]["bars"][-1]
    assert ("DELTA_FLIP", "BEARISH", "BAR_CLOSED") in kinds(closed)


def test_absorption_and_multiple_hvn_use_adaptive_closed_rules(footprint_bin, tmp_path):
    base = int(time.time() // 60) * 60 - 12 * 60
    rows = []
    # Baseline local pequeño; dos POC consecutivos exactamente en 100.00.
    for b in range(8):
        t = base + b * 60
        rows += [row(t + 1, 99.99, 5, -1), row(t + 2, 100.00, 10, -1),
                 row(t + 3, 100.00, 10, 1)]
    # En el extremo superior aparecen AMBOS lados enormes y el cierre no progresa.
    t = base + 8 * 60
    rows += [row(t + 1, 100.00, 5, 1), row(t + 2, 100.02, 500, -1),
             row(t + 3, 100.02, 500, 1), row(t + 4, 100.01, 1, -1)]
    data = run_engine(footprint_bin, tmp_path, rows)["timeframes"]["60"]["bars"]
    assert any(p["kind"] == "DOUBLE_HVN" for b in data for p in b["patterns"])
    assert ("ABSORPTION", "BEARISH", "BAR_CLOSED") in kinds(data[-1])


def test_no_tape_is_not_reported_as_zero_flow(footprint_bin, tmp_path):
    tape = tmp_path / "footprint_tape_qqq.txt"
    tape.write_text("")
    p = subprocess.run(
        [str(footprint_bin), "--input", str(tape), "--sym", "QQQ", "--out", "-"],
        text=True, capture_output=True,
    )
    assert p.returncode == 2
    data = json.loads(p.stdout)
    assert data["asof"] == 0
    assert data["classification_pct"] == 0
    assert data["timeframes"]["60"]["bars"] == []


def test_native_side_provenance_is_preserved(footprint_bin, tmp_path):
    base = int(time.time() // 60) * 60 - 180
    rows = [f"{base + 1} 100.00 12 -1 99.99 100.01 N",
            f"{base + 2} 100.01 20 1 100.00 100.02 N"]
    tape = tmp_path / "footprint_tape_qqq.txt"
    tape.write_text("\n".join(rows) + "\n")
    p = subprocess.run([
        str(footprint_bin), "--input", str(tape), "--sym", "QQQ", "--out", "-",
        "--source", "Databento direct", "--quality", "DIRECT_PROP_FEED",
    ], check=True, text=True, capture_output=True)
    data = json.loads(p.stdout)
    assert data["source"] == "Databento direct"
    assert data["quality"] == "DIRECT_PROP_FEED"
    assert data["side_provenance"] == "NATIVE"
    assert data["native_side_pct"] == 100


def test_signed_perpetual_tape_is_native_and_never_disguised_as_equity(footprint_bin, tmp_path):
    now_ms = (int(time.time() // 60) * 60 - 180) * 1000
    tape = tmp_path / "qqq.txt"
    tape.write_text(
        f"{now_ms + 1000} t1 725.10 2.5 sell\n"
        f"{now_ms + 2000} t2 725.11 4.0 buy\n"
    )
    p = subprocess.run([
        str(footprint_bin), "--input", str(tape), "--sym", "QQQ", "--out", "-",
        "--format", "perp", "--sym-suffix", "USDT",
        "--source", "OKX signed perpetual tape",
        "--quality", "VENUE_NATIVE_SIDE_THIN_PERP",
        "--instrument-kind", "TOKENIZED_STOCK_PERPETUAL",
    ], check=True, text=True, capture_output=True)
    data = json.loads(p.stdout)
    bar = data["timeframes"]["60"]["bars"][-1]
    assert data["sym"] == "QQQUSDT" and data["proxy_for"] == "QQQ"
    assert data["instrument_kind"] == "TOKENIZED_STOCK_PERPETUAL"
    assert data["side_provenance"] == "NATIVE" and data["native_side_pct"] == 100
    assert bar["bid"] == 2.5 and bar["ask"] == 4.0 and bar["delta"] == 1.5
