#!/usr/bin/env python3
"""Puente TA_* (llm.env) -> TRADINGAGENTS_* (lo unico que default_config.py lee).
Sin esto, TA_LLM_PROVIDER/TA_BACKEND_URL/TA_DEEP_MODEL/TA_QUICK_MODEL de llm.env
no gobiernan TradingAgents. Debe correr ANTES de `import tradingagents...`."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MAP = {
    "TA_LLM_PROVIDER": "TRADINGAGENTS_LLM_PROVIDER",
    "TA_BACKEND_URL": "TRADINGAGENTS_LLM_BACKEND_URL",
    "TA_DEEP_MODEL": "TRADINGAGENTS_DEEP_THINK_LLM",
    "TA_QUICK_MODEL": "TRADINGAGENTS_QUICK_THINK_LLM",
}

_PROVIDER_KEYS = {
    "nvidia": "NVIDIA_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def _load_env_file(path):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_provider_key():
    """Load only the selected provider credential from TradingAgents' .env."""
    provider = os.environ.get("TA_LLM_PROVIDER", "").strip().lower()
    key_name = _PROVIDER_KEYS.get(provider)
    if not key_name or os.environ.get(key_name):
        return key_name
    ta_repo = os.getenv("TA_REPO", os.path.expanduser("~/Documents/GitHub/TradingAgents"))
    env_path = os.path.join(ta_repo, ".env")
    if not os.path.exists(env_path):
        return key_name
    for raw in open(env_path):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key_name:
            os.environ.setdefault(key_name, v.strip().strip('"').strip("'"))
            break
    return key_name


def apply(load_llm_env=True):
    """Copia TA_* -> TRADINGAGENTS_* en os.environ (setdefault: no pisa overrides ya puestos)."""
    if load_llm_env:
        _load_env_file(os.path.join(REPO, "config", "llm.env"))
    _load_provider_key()
    for ta_key, tgt_key in _MAP.items():
        v = os.environ.get(ta_key)
        if v:
            os.environ.setdefault(tgt_key, v)


if __name__ == "__main__":
    import shlex
    apply()
    for tgt_key in _MAP.values():
        v = os.environ.get(tgt_key)
        if v:
            print(f"export {tgt_key}={shlex.quote(v)}")
