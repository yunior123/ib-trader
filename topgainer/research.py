#!/usr/bin/env python3
"""TradingAgents research layer — runs the local multi-agent framework on the
top candidates before the open (the 6 AM step, like Yunior's friend).

It is subprocess-isolated and timeout-guarded: TradingAgents is a long LLM chain,
so a hang or crash (or a missing LLM key) must NEVER block the scanner. If it
can't run, research_ticker() returns None and the scanner proceeds on its own
selective ranking. When it does run, it returns BUY/HOLD/SELL + the raw decision
so Claude can weight the trade.

Enable via env for the 6 AM job:
  TA_RESEARCH=1  TA_RESEARCH_TOPN=3  TA_TIMEOUT=360
  (plus whatever LLM keys TradingAgents needs, e.g. OPENAI_API_KEY)
"""
import json
import os
import subprocess
import sys

TA_REPO = os.getenv("TA_REPO", os.path.expanduser("~/Documents/GitHub/TradingAgents"))
TIMEOUT = int(os.getenv("TA_TIMEOUT", "360"))
# TradingAgents needs Python 3.10+ (our main venv is 3.9), so it runs in its own
# py3.12 venv. research_ticker() invokes _run through this interpreter.
_TA_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ta_venv", "bin", "python")
TA_PYTHON = os.getenv("TA_PYTHON", _TA_PY if os.path.exists(_TA_PY) else sys.executable)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env_file(name):
    p = os.path.join(REPO_ROOT, name)
    if not os.path.exists(p):
        return
    for line in open(p):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _configure_llm_env():
    """Point TradingAgents at the research LLM (OpenAI-compatible). MANDATORY layer.
    Prefers DeepSeek (Yunior's choice), falls back to NVIDIA NIM if only that key
    is present. langchain ChatOpenAI (provider 'openai') reads OPENAI_API_KEY."""
    _load_env_file("llm.env")
    _load_env_file("feeds.env")
    ds = os.environ.get("DEEPSEEK_API_KEY", "")
    nv = os.environ.get("NVIDIA_API_KEY", "")
    if ds:
        os.environ["OPENAI_API_KEY"] = ds
    elif nv:
        os.environ["OPENAI_API_KEY"] = nv
    # FinnHub tool key (data layer)
    if os.environ.get("FINNHUB_KEY") and not os.environ.get("FINNHUB_API_KEY"):
        os.environ["FINNHUB_API_KEY"] = os.environ["FINNHUB_KEY"]


# ---- subprocess entrypoint: `python research.py _run SYM DATE` ----
def _run(sym, date_str):
    _configure_llm_env()
    sys.path.insert(0, TA_REPO)
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG as C
    cfg = dict(C)
    cfg["llm_provider"] = os.getenv("TA_LLM_PROVIDER", "openai")
    cfg["backend_url"] = os.getenv("TA_BACKEND_URL", "https://integrate.api.nvidia.com/v1")
    cfg["deep_think_llm"] = os.getenv("TA_DEEP_MODEL", "meta/llama-3.3-70b-instruct")
    cfg["quick_think_llm"] = os.getenv("TA_QUICK_MODEL", "meta/llama-3.1-8b-instruct")
    cfg["max_debate_rounds"] = int(os.getenv("TA_DEBATE_ROUNDS", "1"))
    cfg["max_risk_discuss_rounds"] = int(os.getenv("TA_RISK_ROUNDS", "1"))
    cfg["online_tools"] = True
    # trim analysts to keep the 6 AM run tractable on 8GB / NIM latency
    analysts = os.getenv("TA_ANALYSTS", "market,news").split(",")
    ta = TradingAgentsGraph(selected_analysts=[a.strip() for a in analysts if a.strip()],
                            debug=False, config=cfg)
    _, decision = ta.propagate(sym, date_str)
    print(json.dumps({"sym": sym, "decision": str(decision)}))


def research_ticker(sym, date_str, timeout=None):
    """Best-effort. Returns {'sym','action','decision'} or None."""
    timeout = timeout or TIMEOUT
    try:
        r = subprocess.run([TA_PYTHON, os.path.abspath(__file__), "_run", sym, date_str],
                           capture_output=True, text=True, timeout=timeout,
                           cwd=os.path.dirname(os.path.abspath(__file__)))
        line = [l for l in r.stdout.splitlines() if l.strip().startswith("{")]
        if not line:
            print(f"[research] {sym}: no decision ({(r.stderr or '')[:80]})", file=sys.stderr)
            return None
        obj = json.loads(line[-1])
        dec = obj.get("decision", "")
        up = dec.upper()
        action = "BUY" if "BUY" in up else "SELL" if "SELL" in up else "HOLD"
        return {"sym": sym, "action": action, "decision": dec[:400]}
    except subprocess.TimeoutExpired:
        print(f"[research] {sym}: timeout {timeout}s — skipping", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[research] {sym}: {repr(e)[:100]}", file=sys.stderr)
        return None


def enrich_candidates(cands, date_str, topn=None):
    """Attach a TradingAgents note to the top-N candidates; leave the rest as-is.
    Only runs if TA_RESEARCH=1 (so the default fast path is untouched)."""
    if os.getenv("TA_RESEARCH") != "1":
        return cands
    topn = topn or int(os.getenv("TA_RESEARCH_TOPN", "3"))
    for c in cands[:topn]:
        note = research_ticker(c["sym"], date_str)
        if note:
            c["ta_action"] = note["action"]
            c["ta_note"] = note["decision"]
            print(f"[research] {c['sym']} -> {note['action']}", file=sys.stderr)
    return cands


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "_run":
        _run(sys.argv[2], sys.argv[3])
    else:
        sym = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
        date = sys.argv[2] if len(sys.argv) > 2 else "2024-05-10"
        print(research_ticker(sym, date))
