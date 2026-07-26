"""test_ta_llm_bridge.py — TA_* (llm.env) debe gobernar TRADINGAGENTS_* (lo que
default_config.py de TradingAgents realmente lee). Antes de este puente, el
framework leia solo TRADINGAGENTS_* y llm.env no tenia efecto: research.py
(screener) caia a defaults NVIDIA NIM cuando TA_* no estaba en el entorno."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
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
