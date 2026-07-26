"""test_ta_llm_bridge.py — TA_* (llm.env) debe gobernar TRADINGAGENTS_* (lo que
default_config.py de TradingAgents realmente lee). Antes de este puente, el
framework leia solo TRADINGAGENTS_* y llm.env no tenia efecto: research.py
(screener) caia a defaults NVIDIA NIM cuando TA_* no estaba en el entorno."""
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import ta_llm_bridge as bridge  # noqa: E402

_TARGETS = ("TRADINGAGENTS_LLM_PROVIDER", "TRADINGAGENTS_LLM_BACKEND_URL",
            "TRADINGAGENTS_DEEP_THINK_LLM", "TRADINGAGENTS_QUICK_THINK_LLM")


def _clean(monkeypatch):
    for k in list(bridge._MAP) + list(_TARGETS):
        monkeypatch.delenv(k, raising=False)


def test_ta_vars_map_to_tradingagents_vars(monkeypatch):
    _clean(monkeypatch)
    monkeypatch.setenv("TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TA_BACKEND_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("TA_DEEP_MODEL", "deepseek-chat")
    monkeypatch.setenv("TA_QUICK_MODEL", "deepseek-chat")
    bridge.apply(load_llm_env=False)
    assert os.environ["TRADINGAGENTS_LLM_PROVIDER"] == "openai"
    assert os.environ["TRADINGAGENTS_LLM_BACKEND_URL"] == "https://api.deepseek.com/v1"
    assert os.environ["TRADINGAGENTS_DEEP_THINK_LLM"] == "deepseek-chat"
    assert os.environ["TRADINGAGENTS_QUICK_THINK_LLM"] == "deepseek-chat"


def test_existing_tradingagents_var_wins_over_ta(monkeypatch):
    """setdefault: un override explicito rio abajo no se pisa."""
    _clean(monkeypatch)
    monkeypatch.setenv("TA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "already-set")
    bridge.apply(load_llm_env=False)
    assert os.environ["TRADINGAGENTS_LLM_PROVIDER"] == "already-set"


def test_absent_ta_var_leaves_target_unset(monkeypatch):
    _clean(monkeypatch)
    bridge.apply(load_llm_env=False)
    for k in _TARGETS:
        assert k not in os.environ


def test_real_llm_env_file_maps_to_deepseek_not_nim(monkeypatch):
    """llm.env real del repo debe apuntar a DeepSeek; NIM prohibido (orden 2026-07-16)."""
    _clean(monkeypatch)
    bridge.apply(load_llm_env=True)
    provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "")
    backend = os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL", "")
    deep = os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "")
    for banned in ("nvidia", "nim", "kimi"):
        assert banned not in provider.lower()
        assert banned not in backend.lower()
        assert banned not in deep.lower()
    assert "deepseek" in backend.lower()


_TA_PY = os.path.join(REPO, "ta_venv", "bin", "python")
_TA_REPO = os.path.expanduser("~/Documents/GitHub/TradingAgents")

_E2E = """
import json, os, sys
sys.path.insert(0, os.path.join(%r, "scripts"))
from ta_llm_bridge import apply
apply()
sys.path.insert(0, %r)
from tradingagents.default_config import DEFAULT_CONFIG as C
print(json.dumps({k: C[k] for k in
      ("llm_provider", "backend_url", "deep_think_llm", "quick_think_llm")}))
""" % (REPO, _TA_REPO)


@pytest.mark.skipif(not os.path.exists(_TA_PY) or not os.path.exists(_TA_REPO),
                    reason="ta_venv (py3.12) o el repo TradingAgents no estan aqui")
def test_llm_env_really_governs_tradingagents_config():
    """End-to-end: no basta con exportar TRADINGAGENTS_*; el DEFAULT_CONFIG que
    ve el framework debe acabar apuntando a DeepSeek. Corre en ta_venv porque
    TradingAgents pide py3.10+ y el venv principal es 3.9."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("TRADINGAGENTS_")}
    r = subprocess.run([_TA_PY, "-c", _E2E], capture_output=True, text=True,
                       timeout=120, env=env, cwd=REPO)
    assert r.returncode == 0, r.stderr[-500:]
    cfg = json.loads([x for x in r.stdout.splitlines() if x.startswith("{")][-1])
    assert "deepseek" in cfg["backend_url"].lower()
    for key in ("llm_provider", "backend_url", "deep_think_llm", "quick_think_llm"):
        for banned in ("nvidia", "nim", "kimi", "moonshot"):
            assert banned not in str(cfg[key]).lower(), (key, cfg[key])
