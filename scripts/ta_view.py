#!/usr/bin/env python3
"""ta_view.py SYM — SALIDA de TradingAgents hacia la casa (SEÑAL-SOLAMENTE).

Corre el framework en su ta_venv (py3.12) con el arsenal de la casa inyectado
como contexto (barras IBKR, muros de la cadena, régimen de levels_<sym>.json +
dataflows.ibtrader) y escribe data/ta_view_<sym>.json (tmp+rename).
Timeout o crash -> {ts, sym, error} y rc!=0; jamás un veredicto plausible."""
import json
import os
import re
import subprocess
import sys
import time

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SCRIPTS)
DATA = os.path.join(REPO, "data")
TA_REPO = os.getenv("TA_REPO", os.path.expanduser("~/Documents/GitHub/TradingAgents"))
_TA_PY = os.path.join(REPO, "ta_venv", "bin", "python")
TA_PYTHON = os.getenv("TA_PYTHON", _TA_PY if os.path.exists(_TA_PY) else sys.executable)
TIMEOUT = int(os.getenv("TA_VIEW_TIMEOUT", "300"))

_RATING2VIEW = {"buy": "bull", "overweight": "bull", "hold": "neutral",
                "underweight": "bear", "sell": "bear"}


def _load_env_file(name):
    p = os.path.join(REPO, "config", name)
    if not os.path.exists(p):
        return
    for line in open(p):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------- contexto de la casa (corre en el hijo, py3.12, stdlib) ----------
def _house_bars(sym):
    p = os.path.join(DATA, f"bars_{sym.lower()}_ibkr.txt")
    if not os.path.exists(p):
        return None
    rows = []
    for line in open(p):
        f = line.split()
        if len(f) >= 6:
            rows.append((int(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[4]), int(f[5])))
    if not rows:
        return None
    day = rows[-390:]
    o, c = day[0][1], day[-1][4]
    hi = max(r[2] for r in day)
    lo = min(r[3] for r in day)
    age_h = (time.time() - rows[-1][0]) / 3600
    return (f"barras 1m IBKR ({p}, ultima hace {age_h:.1f}h): "
            f"ult close {c:.2f}, sesion open {o:.2f} ({(c - o) / o * 100:+.2f}%), "
            f"rango {lo:.2f}-{hi:.2f}, {len(day)} barras")


def _house_walls(sym):
    p = os.path.join(DATA, f"opt_chain_{sym.lower()}.txt")
    if not os.path.exists(p):
        return None
    calls, puts = {}, {}
    header = ""
    for line in open(p):
        if line.startswith("#"):
            header = header or line.strip()
            continue
        f = line.split()
        if len(f) < 7:
            continue
        try:
            k, oi = float(f[0]), int(f[6])
        except ValueError:
            continue
        d = calls if f[1] == "C" else puts
        d[k] = d.get(k, 0) + oi
    if not calls and not puts:
        return None
    top = lambda d: " ".join(f"{k:g}({oi / 1000:.1f}k)" for k, oi in
                             sorted(d.items(), key=lambda x: -x[1])[:4])
    return (f"muros OI cadena TWS ({p}; {header}): "
            f"CALLS {top(calls) or 'ninguno'} | PUTS {top(puts) or 'ninguno'}")


def _house_regime(sym):
    p = os.path.join(REPO, "charts", "data", f"levels_{sym.lower()}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    keys = ("spot", "regime", "flip", "net_gex", "call_wall", "put_wall", "abs_wall",
            "abs_wall_kind", "em", "pressure_lab", "stale", "chain_src")
    return f"regimen gamma casa ({p}): " + json.dumps({k: d[k] for k in keys if k in d})


def _house_context(sym):
    lines = [f"## Datos de la casa ib-trader — {sym} (solo lectura, cada linea con su fuente)"]
    for name, fn in (("barras", _house_bars), ("muros", _house_walls), ("regimen", _house_regime)):
        try:
            s = fn(sym)
        except Exception as e:
            s = f"{name}: ERROR leyendo fuente ({e!r})"
        lines.append(f"- {s if s else name + ': AUSENTE'}")
    return "\n".join(lines)


# ---------- hijo: `ta_view.py _run SYM DATE` bajo ta_venv ----------
def _run(sym, date_str):
    _load_env_file("llm.env")
    _load_env_file("feeds.env")
    ds = os.environ.get("DEEPSEEK_API_KEY", "")
    if not ds:
        raise SystemExit("SIN DEEPSEEK_API_KEY y NIM prohibido (orden 2026-07-16) — no hay LLM")
    os.environ["OPENAI_API_KEY"] = ds
    sys.path.insert(0, SCRIPTS)
    from ta_llm_bridge import apply as apply_ta_bridge
    apply_ta_bridge()
    sys.path.insert(0, TA_REPO)
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG as C
    cfg = dict(C)
    cfg["max_debate_rounds"] = int(os.getenv("TA_DEBATE_ROUNDS", "1"))
    cfg["max_risk_discuss_rounds"] = int(os.getenv("TA_RISK_ROUNDS", "1"))
    analysts = [a.strip() for a in os.getenv("TA_ANALYSTS", "market").split(",") if a.strip()]
    ta = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=cfg)

    house = _house_context(sym)
    try:
        from tradingagents.dataflows.ibtrader import format_ibtrader_context
        house += "\n\n" + format_ibtrader_context(sym)
    except Exception as e:
        house += f"\n\n## ib-trader arsenal\nAUSENTE (import/lectura fallo: {e!r})"

    base = ta.resolve_instrument_context
    ta.resolve_instrument_context = lambda t, a="stock": base(t, a) + "\n\n" + house

    _, rating = ta.propagate(sym, date_str)
    final = ta.curr_state.get("final_trade_decision", "")
    print("TA_VIEW_JSON " + json.dumps({"sym": sym, "rating": str(rating), "final": final[:8000]}))


# ---------- padre ----------
def _atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")
    os.rename(tmp, path)


def _tesis(final):
    m = re.search(r"\*\*Executive Summary\*\*:\s*(.+?)(?:\n\n|\Z)", final, re.S)
    txt = (m.group(1) if m else final).strip().replace("\n", " ")
    sents = re.split(r"(?<=[.!?])\s+", txt)
    return " ".join(sents[:3])[:600]


def _niveles(final):
    out = []
    for lab, tipo in (("Price Target", "target"), ("Entry Price", "entrada"), ("Stop Loss", "stop")):
        m = re.search(rf"\*\*{lab}\*\*:\s*\$?([0-9]+(?:\.[0-9]+)?)", final)
        if m:
            out.append({"tipo": tipo, "nivel": float(m.group(1))})
    return out


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "_run":
        _run(sys.argv[2].upper(), sys.argv[3])
        return 0
    if len(sys.argv) < 2:
        print("uso: ta_view.py SYM [YYYY-MM-DD]", file=sys.stderr)
        return 2
    sym = sys.argv[1].upper()
    date_str = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%Y-%m-%d")
    out_path = os.path.join(DATA, f"ta_view_{sym.lower()}.json")
    t0 = time.time()
    err = None
    try:
        r = subprocess.run([TA_PYTHON, os.path.abspath(__file__), "_run", sym, date_str],
                           capture_output=True, text=True, timeout=TIMEOUT, cwd=REPO)
        lines = [l for l in r.stdout.splitlines() if l.startswith("TA_VIEW_JSON ")]
        if r.returncode != 0 or not lines:
            err = f"rc={r.returncode} sin veredicto; stderr: {(r.stderr or '').strip()[-400:]}"
        else:
            obj = json.loads(lines[-1][len("TA_VIEW_JSON "):])
            rating = obj["rating"].strip().lower()
            veredicto = _RATING2VIEW.get(rating)
            if veredicto is None:
                err = f"rating no reconocido: {obj['rating']!r}"
            else:
                _atomic_write(out_path, {
                    "ts": int(time.time()), "sym": sym, "veredicto": veredicto,
                    "rating": obj["rating"],
                    "prob": None,  # el framework no emite probabilidad numerica; no se inventa
                    "tesis": _tesis(obj["final"]), "niveles": _niveles(obj["final"]),
                    "latency_s": round(time.time() - t0, 1), "fuente": "tradingagents"})
                print(f"{sym}: {veredicto} ({obj['rating']}) en {time.time() - t0:.0f}s -> {out_path}")
                return 0
    except subprocess.TimeoutExpired:
        err = f"timeout {TIMEOUT}s"
    except Exception as e:
        err = repr(e)[:400]
    _atomic_write(out_path, {"ts": int(time.time()), "sym": sym, "error": err})
    print(f"{sym}: ERROR {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
