#!/usr/bin/env python3
"""iv_regime.py — IV Regime Tracker: where current IV sits vs 60-day percentile.

Input: data/history/<fecha>/chain_full_*.json (Polygon snapshots with IV).
Output: data/iv_regime.json {sym: {iv_current, iv_p10, iv_p50, iv_p90, percentile, regime}}.

Regimes: COMPRESSED (<P10), NORMAL (P10-P90), EXPANDED (>P90).
Corre 4am (auto) o manual: python3 scripts/iv_regime.py
"""
import json, os, sys, glob, time, datetime as dt
from collections import defaultdict
import statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import session_dirs

SENTINEL_MAX = 0.0   # iv <= 0 es el centinela "sin dato" de las cadenas, JAMAS una IV

def load_fleet():
    with open("data/fleet.txt") as f:
        return f.read().split()

def build_iv_history(sym, days=60):
    """IV de los snapshots archivados, ultimas `days` SESIONES (nunca sabado/domingo)."""
    hist_dir = "data/history"
    ivs = []
    cutoff = dt.date.today() - dt.timedelta(days=days)
    for d in session_dirs.session_dirs(hist_dir, reverse=False):
        if dt.date.fromisoformat(d) < cutoff:   # el filtro anterior comparaba YYYYMMDD con epoch/1e6: inerte
            continue
        f = os.path.join(hist_dir, d, f"chain_full_{sym.lower()}.json")
        if not os.path.exists(f):
            continue
        try:
            with open(f) as src:
                data = json.load(src)
        except (OSError, ValueError) as e:
            print(f"[iv_regime] {sym} {d}: snapshot ilegible ({type(e).__name__})", file=sys.stderr)
            continue
        # el archivador de Polygon escribe {'meta','results'} con `implied_volatility` por fila;
        # `rows`/`iv` era el esquema viejo. Leer solo `rows` devolvia [] SIEMPRE (medido 2026-08-03).
        for row in (data.get("results") or data.get("rows") or []):
            iv = row.get("implied_volatility", row.get("iv"))
            if isinstance(iv, (int, float)) and iv > SENTINEL_MAX:
                ivs.append(float(iv))
    return ivs

def current_iv(sym):
    """IV central de la cadena viva: MEDIANA de las filas con IV medida. None si no hay ninguna.

    Antes se tomaba la PRIMERA fila parseable y `if not iv_now` dejaba pasar el centinela -1.0
    (falso solo para 0.0). Medido 2026-08-03: 11 de 26 simbolos publicaban iv_current=-1.0 ->
    percentile 0 -> regime COMPRESSED ("IV barata") con la cadena entera sin griegas. Un
    centinela convertido en veredicto de mercado es el "cero plausible" que la casa prohibe.
    """
    chain_path = f"data/opt_chain_{sym.lower()}.txt"
    vals = []
    with open(chain_path) as f:
        for ln in f:
            if ln.startswith("#"):
                continue
            p = ln.split()
            if len(p) <= 7:
                continue
            try:
                iv = float(p[7])
            except ValueError:
                continue
            if iv > SENTINEL_MAX:
                vals.append(iv)
    return st.median(vals) if vals else None


def compute_regime(sym):
    """IV percentile vs histórico."""
    try:
        iv_now = current_iv(sym)
        if iv_now is None:
            print(f"[iv_regime] {sym}: cadena SIN una sola IV medida — sin regimen (no se inventa)",
                  file=sys.stderr)
            return None

        # Histórico
        ivs = build_iv_history(sym, days=60)
        if len(ivs) < 20:
            return None

        p10 = st.quantiles(ivs, n=10)[0] if len(ivs) > 10 else min(ivs)
        p50 = st.median(ivs)
        p90 = st.quantiles(ivs, n=10)[-1] if len(ivs) > 10 else max(ivs)
        
        pct = sum(1 for x in ivs if x <= iv_now) / len(ivs) * 100
        regime = "COMPRESSED" if pct < 10 else "EXPANDED" if pct > 90 else "NORMAL"
        
        return {
            "iv_current": round(iv_now, 2),
            "iv_p10": round(p10, 2),
            "iv_p50": round(p50, 2),
            "iv_p90": round(p90, 2),
            "percentile": round(pct, 0),
            "regime": regime,
            "n_samples": len(ivs),
            "iv_def": "mediana de las IV MEDIDAS de la cadena viva vs pool de IV de las sesiones archivadas",
        }
    except (OSError, ValueError, st.StatisticsError) as e:
        print(f"[iv_regime] {sym}: sin regimen ({type(e).__name__}: {e})", file=sys.stderr)
        return None

def main():
    out = {}
    for sym in load_fleet():
        r = compute_regime(sym)
        if r:
            out[sym] = r
    tmp = "data/iv_regime.json.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, "data/iv_regime.json")
    print(f"[iv_regime] {len(out)}/{len(load_fleet())} símbolos medidos")

if __name__ == "__main__":
    main()
