#!/usr/bin/env python3
"""overnight_structure.py — factor OVERNIGHT para la flecha (NQ + Corea).
Lee overnight_ctx.json (escrito por overnight_feed.py): NQ/ES (futures), Corea pcts
(bars locales), sentimiento X. Coeficiente multiplicativo como peer_structure (1.25/1.0/0.75).
Solo actúa FUERA de RTH US. SEÑAL-SOLAMENTE."""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

CTX_F = os.path.join(REPO, "data", "overnight_ctx.json")
CTX_MAX_AGE_S = 300  # 5 min
STRONG = 0.5
KOREA_LEAD = {"MU", "SKHY", "DRAM", "SMH", "NVDA", "TSM", "ASML", "AMD", "INTC",
              "AVGO", "TXN", "QCOM", "EWY", "LRCX", "SNDK", "WDC", "STX"}
WEIGHTS = {"nq": 0.6, "korea": 0.3, "sent": 0.1}


def compute(sym):
    """score del overnight para `sym`. -> dict {score, nq, korea, sent, ts, why} o None."""
    sym = sym.upper()
    try:
        ctx = json.load(open(CTX_F))
    except Exception:
        return None
    ts = ctx.get("ts") or 0
    if time.time() - ts > CTX_MAX_AGE_S:
        return None
    try:
        import gex_core
        if gex_core.in_rth():
            return None
    except Exception:
        return None
    nq = ctx.get("nq_pct")
    korea = korea_score(sym, ctx) if sym in KOREA_LEAD else None
    sent = sentiment_score(ctx.get("sent"))
    num, den, reasons = 0.0, 0.0, []
    if nq is not None:
        num += nq * WEIGHTS["nq"]
        den += WEIGHTS["nq"]
    if korea is not None:
        num += korea * WEIGHTS["korea"]
        den += WEIGHTS["korea"]
        reasons.append(f"corea {korea:+.2f}")
    if sent is not None:
        num += sent * WEIGHTS["sent"]
        den += WEIGHTS["sent"]
    if den <= 0:
        return None
    score = num / den
    return {"score": round(score, 3), "nq": None if nq is None else round(nq, 3),
            "korea": None if korea is None else round(korea, 3),
            "sent": None if sent is None else round(sent, 3), "ts": ts,
            "why": f"overnight nq {nq:+.2f}" + (f" + {'; '.join(reasons)}" if reasons else "")}


def korea_score(sym, ctx):
    """Media ponderada de SKHynix + Samsung + KOSPI. None si faltan todas."""
    items = [("hynix_pct", 0.4), ("samsung_pct", 0.35), ("kospi_pct", 0.25)]
    num, den = 0.0, 0.0
    for key, w in items:
        v = ctx.get(key)
        if v is not None:
            num += v * w
            den += w
    return None if den <= 0 else num / den


def sentiment_score(sent):
    """Balanza de pos/neg de x_sentiment, None si falta."""
    if not isinstance(sent, dict) or not sent.get("n"):
        return None
    p, n = sent.get("pos", 0), sent.get("neg", 0)
    if p + n == 0:
        return None
    return round((p - n) / (p + n), 3)


def overnight_coef(sym, local_dir):
    """Coeficiente overnight sobre fleet/components (multiplicativo, cuantizado 1.25/1.0/0.75).
    local_dir: signo del factor fleet/components ya calculado. -> (coef, why|None)"""
    d = compute(sym)
    if d is None or not local_dir or abs(d["score"]) < STRONG:
        return 1.0, None
    agree = (d["score"] > 0) == (local_dir > 0)
    coef = 1.25 if agree else 0.75
    return coef, (f"overnight NQ ×{coef:.2f} ({d['why']})")


def apply_overnight(weights, coef):
    """Escala fleet/components (copia, no muta). Patrón de apply_peer."""
    w = dict(weights)
    for k in ("fleet", "components"):
        if k in w:
            w[k] = round(w[k] * coef, 3)
    return w


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["QQQ", "NVDA"]):
        d = compute(s)
        print(s.upper(), json.dumps(d) if d else "None")
