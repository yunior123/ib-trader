"""provider_bridge escribe EXACTAMENTE los contratos de fichero que lee la flota C++.

Corre el puente en modo mock (venv-mit, py3.12) hacia un dir temporal y valida el
formato byte a byte contra lo que parsean nvda_signal_bot.cpp (bars 6 campos, epoch
creciente min-alineado), aapl_signal_bot.cpp (nbbo 3 campos ask>bid>0) y opt_quick.cpp
(cadena: 3 cabeceras, tokens epoch/spot/exps en L1, filas >=7 campos, right C|P).

Se lanza por subprocess con venv-mit porque la capa mit/ exige py3.11+ y la suite corre
en py3.9. Si venv-mit no existe, se salta (skip), no falla.
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VENV_MIT = REPO / "venv-mit" / "bin" / "python"
BRIDGE = REPO / "scripts" / "provider_bridge.py"


@pytest.fixture(scope="module")
def mock_output(tmp_path_factory):
    if not VENV_MIT.exists():
        pytest.skip("venv-mit no existe (crear con python3.12 -m venv venv-mit)")
    data = tmp_path_factory.mktemp("data")
    env = dict(os.environ)
    env.update(
        MIT_MARKET_PROVIDER="mock",
        MIT_OPTIONS_PROVIDER="mock",
        IBT_ALLOW_MOCK="1",  # escotilla de test: el guard anti-mock bloquea mock en produccion
        IBT_DATA_DIR=str(data),
        PYTHONPATH=str(REPO / "mit"),
    )
    r = subprocess.run(
        [str(VENV_MIT), str(BRIDGE), "--once", "SPY"],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, f"bridge fallo: {r.stderr}\n{r.stdout}"
    return data


def test_bars_contract(mock_output):
    lines = (mock_output / "bars_spy_ibkr.txt").read_text().splitlines()
    assert lines, "bars vacio"
    eps = []
    for ln in lines:
        f = ln.split()
        assert len(f) == 6, f"bars necesita 6 campos: {ln!r}"
        eps.append(int(f[0]))
        [float(x) for x in f[1:]]  # todos numericos
    assert all(e % 60 == 0 for e in eps), "epochs deben ser minuto-alineados"
    assert all(eps[i] < eps[i + 1] for i in range(len(eps) - 1)), "epochs estrictamente crecientes"


def test_nbbo_contract(mock_output):
    f = (mock_output / "nbbo_spy.txt").read_text().split()
    assert len(f) == 3, "nbbo: EPOCH BID ASK"
    ep, bid, ask = int(f[0]), float(f[1]), float(f[2])
    assert ask > bid > 0, "nbbo debe cumplir ask>bid>0 (gate de spread de los bots)"


def test_chain_contract(mock_output):
    txt = (mock_output / "opt_chain_spy.txt").read_text().splitlines()
    assert txt[0].startswith("# opt_chain SPY")
    # opt_quick.cpp busca por substring en L1:
    for tok in ("epoch ", "spot ", "exps "):
        assert tok in txt[0], f"L1 debe llevar el token {tok!r} (opt_quick usa strstr)"
    assert txt[1].startswith("# fuente ")
    # opt_quick usa strstr: los tokens de L1 NO pueden aparecer en L2
    for tok in ("epoch ", "spot ", "exps "):
        assert tok not in txt[1], f"L2 no debe contener {tok!r}"
    assert txt[2].startswith("# strike right exp")
    rows = [l for l in txt[3:] if l.strip()]
    assert rows, "cadena sin filas"
    for ln in rows[:20]:
        f = ln.split()
        assert len(f) >= 7, f"fila necesita >=7 campos: {ln!r}"
        assert f[1] in ("C", "P"), f"right debe ser C|P: {ln!r}"
        float(f[0])  # strike numerico
