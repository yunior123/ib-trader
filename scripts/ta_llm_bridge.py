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


def _load_env_file(path):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def apply(load_llm_env=True):
    """Copia TA_* -> TRADINGAGENTS_* en os.environ (setdefault: no pisa overrides ya puestos)."""
    if load_llm_env:
        _load_env_file(os.path.join(REPO, "llm.env"))
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
