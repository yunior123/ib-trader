#!/usr/bin/env python3
"""shock_calibrator.py — calibrador diario de SHOCK cross-simbolo + reversion EMPIRICA.

Para cada simbolo de data/provider_syms.txt: detecta shock del ultimo dia (abs move >=10%/15%
O z-score >= N sigma vs lookback) y mide la probabilidad de REVERSION como fraccion de shocks
pasados COMPARABLES (misma magnitud) que tuvieron ALGUN cierre en direccion opuesta dentro del
horizonte. La prob lleva intervalo Wilson sobre la muestra RESUELTA (no la media cruda) y es
None (fail-loud) si la muestra < piso (REVERSION_MIN_N). Escribe data/shock_snapshot.json atomico.

IMPORTANTE: la prob mide OCURRENCIA de un cierre opuesto dentro del horizonte — NO es first-touch
ni PnL de una operacion. Es una condicion de ALERTA, no una garantia ni una senal de entrada.

Necesita ~756 barras DIARIAS que la flota NO guarda -> corre bajo venv-mit (py3.12) tirando de la
capa de proveedores generica (mit/). SEÑAL-SOLAMENTE: escribe json, no dispara nada.

  ./venv-mit/bin/python scripts/shock_calibrator.py --once
  ./venv-mit/bin/python scripts/shock_calibrator.py --daemon
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc  # py3.9 no trae datetime.UTC (se usa bajo venv py3.9 en tests)
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mit"))

DATA = Path(os.environ.get("IBT_DATA_DIR") or (REPO / "data"))
LOG_PREFIX = "[shock_calibrator]"

REVERSION_MIN_N = int(os.environ.get("IBT_REVERSION_MIN_N", "20"))  # piso: bajo esto -> None
REFRESH_S = float(os.environ.get("IBT_SHOCK_REFRESH_S", "21600"))   # daemon: 6h (dato DIARIO)
MIN_DAILY_BARS = 5  # bajo esto no hay estado de shock fiable


def log(msg: str) -> None:
    print(f"{LOG_PREFIX} {datetime.now(UTC):%H:%M:%S} {msg}", flush=True)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _syms() -> list[str]:
    src = DATA / "provider_syms.txt"
    if not src.exists():
        src = DATA / "fleet.txt"
    return [s.strip().upper() for s in src.read_text().split() if s.strip()]


@dataclass(frozen=True)
class Params:
    shock_pct: float = 10.0
    extreme_shock_pct: float = 15.0
    shock_zscore: float = 2.5
    reversion_lookback_days: int = 756
    reversal_horizon_days: int = 2
    reversion_min_n: int = REVERSION_MIN_N


def wilson(w: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Intervalo Wilson (p, lo, hi) sobre la muestra RESUELTA. n==0 no debe llegar aqui."""
    if n <= 0:
        raise ValueError("wilson: n<=0")
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, (c - m) / d, (c + m) / d


def daily_returns_pct(closes: list[float]) -> list[float | None]:
    """return_pct[i] = (close[i]/close[i-1]-1)*100; index 0 -> None (sin previo). Mismo largo."""
    out: list[float | None] = [None]
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        out.append((closes[i] / prev - 1.0) * 100.0 if prev > 0 else None)
    return out


def reversion_sample(closes: list[float], *, threshold: float, horizon: int) -> tuple[int, int]:
    """Cuenta shocks pasados comparables (abs move >= threshold%) y cuantos tuvieron ALGUN cierre
    opuesto dentro de `horizon` sesiones. Devuelve (wins, n). Espeja shock._historical_reversion.
    Excluye el ultimo indice (no hay futuro que resuelva) — solo shocks RESUELTOS entran a n."""
    rets = daily_returns_pct(closes)
    wins = 0
    n = 0
    for i in range(1, len(closes) - horizon):
        shock = rets[i]
        if shock is None or not math.isfinite(shock) or abs(shock) < threshold:
            continue
        base = closes[i]
        if base <= 0:
            continue
        future = [closes[j] / base - 1.0 for j in range(i + 1, i + horizon + 1)]
        opposite = any(f < 0 for f in future) if shock > 0 else any(f > 0 for f in future)
        n += 1
        wins += 1 if opposite else 0
    return wins, n


def analyze(closes: list[float], p: Params) -> dict:
    """Estado de shock del ultimo dia + reversion empirica. Fail-loud: None (nunca 0.0/0.5)
    donde no hay dato. Solo `closes` (limpios, orden ascendente)."""
    if len(closes) < MIN_DAILY_BARS:
        return {"severity": "INSUFFICIENT_DATA", "change_pct": None, "zscore": None,
                "direction": "NEUTRAL", "reversion_prob": None, "wilson_lo": None,
                "wilson_hi": None, "n": 0, "horizon": p.reversal_horizon_days,
                "threshold_pct": None, "bars": len(closes)}

    rets = [r for r in daily_returns_pct(closes) if r is not None]
    current = rets[-1]
    hist = rets[:-1][-p.reversion_lookback_days:]
    zscore: float | None = None
    if hist:
        mean = sum(hist) / len(hist)
        var = sum((x - mean) ** 2 for x in hist) / len(hist)  # ddof=0, como el ref
        std = math.sqrt(var)
        zscore = (current - mean) / std if std > 0 else None

    absolute = abs(current)
    if absolute >= p.extreme_shock_pct:
        severity = "CRITICAL"
    elif absolute >= p.shock_pct:
        severity = "WARNING"
    elif zscore is not None and abs(zscore) >= p.shock_zscore:
        severity = "WATCH"
    else:
        severity = "INFO"
    direction = "UP" if current > 0 else "DOWN" if current < 0 else "NEUTRAL"

    threshold = min(p.shock_pct, max(absolute, 0.01))
    wins, n = reversion_sample(closes, threshold=threshold, horizon=p.reversal_horizon_days)
    if n < p.reversion_min_n:
        prob = lo = hi = None  # fail-loud: muestra chica no se publica
    else:
        prob, lo, hi = wilson(wins, n)

    return {"severity": severity, "change_pct": current, "zscore": zscore,
            "direction": direction, "reversion_prob": prob, "wilson_lo": lo, "wilson_hi": hi,
            "n": n, "horizon": p.reversal_horizon_days, "threshold_pct": threshold,
            "bars": len(closes)}


def _clean_closes(bars) -> tuple[list[float], str | None]:
    closes: list[float] = []
    asof: str | None = None
    for b in bars:
        c = float(b.close)
        if c <= 0 or not math.isfinite(c):
            continue
        closes.append(c)
        ts = getattr(b, "timestamp", None)
        if ts is not None:
            asof = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    return closes, asof


async def gather_snapshot(providers, syms: list[str], p: Params) -> dict:
    per: dict[str, dict] = {}
    for sym in syms:
        try:
            bars = await providers.market.get_daily_bars(sym, limit=p.reversion_lookback_days)
        except Exception as e:  # fail-loud por simbolo: se registra, NO se fabrica un cero
            log(f"{sym}: DAILY error {type(e).__name__}: {e}")
            per[sym] = {"severity": "ERROR", "error": f"{type(e).__name__}: {e}",
                        "change_pct": None, "reversion_prob": None}
            continue
        closes, asof = _clean_closes(bars)
        row = analyze(closes, p)
        row["asof"] = asof
        per[sym] = row
        log(f"{sym}: {row['severity']} chg={row['change_pct']} n={row['n']} "
            f"prob={row['reversion_prob']}")
    return {
        "epoch": int(time.time()),
        "generated": datetime.now(UTC).isoformat(),
        "horizon_days": p.reversal_horizon_days,
        "reversion_min_n": p.reversion_min_n,
        "metric": "reversion_prob = fraccion de shocks comparables pasados con ALGUN cierre "
                  "opuesto dentro del horizonte (OCURRENCIA, NO first-touch ni PnL). "
                  "Condicion de alerta, no prediccion; None si muestra < piso.",
        "symbols": per,
    }


def write_snapshot(snap: dict) -> None:
    _atomic_write(DATA / "shock_snapshot.json", json.dumps(snap, indent=2))


async def run(syms: list[str], daemon: bool) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    from backend.app.config import get_settings
    from backend.app.providers.registry import build_providers
    settings = get_settings()
    p = Params(
        shock_pct=settings.shock_pct,
        extreme_shock_pct=settings.extreme_shock_pct,
        shock_zscore=settings.shock_zscore,
        reversion_lookback_days=settings.reversion_lookback_days,
        reversal_horizon_days=settings.reversal_horizon_days,
        reversion_min_n=REVERSION_MIN_N,
    )
    providers = build_providers(settings)
    allow_mock = os.environ.get("IBT_ALLOW_MOCK") == "1"  # SOLO tests offline
    if type(providers.market).__name__ in {"MockProvider", "UnavailableProvider"} and not (
        allow_mock and type(providers.market).__name__ == "MockProvider"
    ):
        raise SystemExit(
            f"[shock_calibrator] ABORTO: market resolvio a {type(providers.market).__name__}. "
            f"Configura MIT_MARKET_PROVIDER en config/feeds.env. NO se escribe nada."
        )
    log(f"market={type(providers.market).__name__} syms={len(syms)} min_n={REVERSION_MIN_N}")
    try:
        snap = await gather_snapshot(providers, syms, p)
        write_snapshot(snap)
        log(f"escrito shock_snapshot.json ({len(snap['symbols'])} simbolos)")
        if not daemon:
            return
        while True:
            await asyncio.sleep(REFRESH_S)
            snap = await gather_snapshot(providers, syms, p)
            write_snapshot(snap)
            log(f"refresh shock_snapshot.json ({len(snap['symbols'])} simbolos)")
    finally:
        await providers.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("syms", nargs="*")
    a = ap.parse_args()
    syms = [s.upper() for s in a.syms] or _syms()
    asyncio.run(run(syms, daemon=a.daemon and not a.once))


if __name__ == "__main__":
    main()
