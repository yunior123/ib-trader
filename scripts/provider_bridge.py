#!/usr/bin/env python3
"""provider_bridge.py — puente TONTO: mueve bytes de la capa de proveedores genericos
(mit/, market_intelligence_terminal) a los MISMOS ficheros que ya lee la flota C++, para
correr la flota SIN IBKR. CERO computo de senal (doctrina: los puentes mueven bytes).

Escribe, por simbolo de data/fleet.txt:
  data/bars_<sym>_ibkr.txt   "EPOCH O H L C V"  (min-alineado, epoch estrictamente creciente)
  data/nbbo_<sym>.txt        "EPOCH BID ASK"    (atomico, epoch = wall-clock, como ibkr_bar_bridge)
  data/opt_chain_<sym>.txt   3 cabeceras + filas (atomico, mismo contrato que opt_quick.cpp)

Fuentes seleccionables por CAPACIDAD via feeds.env / env (el DEFAULT del codigo es 'mock';
feeds.env pone intrinio/polygon). Si resuelve a mock, el puente ABORTA (no inyecta sintetico):
  MIT_MARKET_PROVIDER   -> barras + quote   (feeds.env: intrinio)
  MIT_OPTIONS_PROVIDER  -> cadena de opciones (feeds.env: polygon)
El nombre del fichero conserva el sufijo _ibkr porque 21 bots lo tienen cableado; la
PROCEDENCIA real va en data/opt_chain header + data/provider_status.json (nada miente).

Fail-loud: un error de una capacidad de un simbolo se registra y se sigue; JAMAS se escribe
un cero/valor plausible en lugar de "no se". Uso:
  ./venv-mit/bin/python scripts/provider_bridge.py --daemon [SYM ...]
  ./venv-mit/bin/python scripts/provider_bridge.py --once SPY QQQ    (una pasada, para test)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mit"))

from backend.app.config import get_settings  # noqa: E402
from backend.app.domain import OptionContract, Quote  # noqa: E402
from backend.app.providers.registry import build_providers  # noqa: E402

DATA = Path(os.environ.get("IBT_DATA_DIR") or (REPO / "data"))
LOG_PREFIX = "[provider_bridge]"

# 30 simbolos x (barras+quote) por ciclo: a 20s son ~180 req/min a Intrinio. AFINAR el lunes
# midiendo el rate-limit real del plan (si sobra margen, bajar; si 429, subir o escalonar).
# Con nbbo a 20s, el gate de spread de los bots (frescura 10s) puede fallar-cerrado -> las
# senales disparan sin confirmacion de spread (aceptable con dato delayed, señal-solamente).
BARS_REFRESH_S = 20.0   # barras/nbbo
CHAIN_REFRESH_S = 180.0  # cadena de opciones (como opt_chain_cache)
WARMUP_BARS = 1600       # ~2 sesiones RTH de 1m


def log(msg: str) -> None:
    print(f"{LOG_PREFIX} {datetime.now(UTC):%H:%M:%S} {msg}", flush=True)


def _scrub(e: Exception) -> str:
    # httpx HTTPStatusError incrusta la URL COMPLETA con api_key/apiKey en la query.
    # NUNCA logear la key: se redacta antes de escribir a disco (logs/ no se commitea, pero
    # una key en claro en disco viola la doctrina 'ninguna key a logs').
    msg = re.sub(r"(api_?key=)[^&\s'\"]+", r"\1***", str(e), flags=re.IGNORECASE)
    return f"{type(e).__name__}: {msg}"


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _fleet_syms() -> list[str]:
    # provider_syms.txt = cobertura del proveedor (subconjunto de fleet.txt; excluye
    # tematicos/iliquidos como DRAM/SPCX/SKHY/EWY mientras IBKR esta OFF). Fallback a fleet.txt.
    src = DATA / "provider_syms.txt"
    if not src.exists():
        src = DATA / "fleet.txt"
    return [s.strip().upper() for s in src.read_text().split() if s.strip()]


def _bar_line(ep: int, o: float, h: float, l: float, c: float, v: float) -> str:
    return f"{ep:.0f} {o:.4f} {h:.4f} {l:.4f} {c:.4f} {v:.0f}\n"


def _minute_epoch(ts: datetime) -> int:
    ep = int(ts.timestamp())
    return ep - ep % 60


# ---------------- BARS (data/bars_<sym>_ibkr.txt) ----------------

async def warmup_bars(market, sym: str, last_ep: dict[str, int]) -> None:
    """Reescribe el fichero entero con historia 1m (solo minutos COMPLETOS, ascendente)."""
    bars = await market.get_bars(sym, interval="1m", limit=WARMUP_BARS)
    now = time.time()
    lines, prev = [], 0
    for b in bars:
        ep = _minute_epoch(b.timestamp)
        if ep + 60 > now:      # minuto en curso: incompleto
            continue
        if ep <= prev or b.close <= 0:
            continue
        lines.append(_bar_line(ep, b.open, b.high, b.low, b.close, b.volume))
        prev = ep
    if not lines:
        raise RuntimeError(f"{sym}: warmup sin barras completas")
    _atomic_write(DATA / f"bars_{sym.lower()}_ibkr.txt", "".join(lines))
    last_ep[sym] = prev
    log(f"{sym}: warmup {len(lines)} barras 1m -> bars_{sym.lower()}_ibkr.txt (ultimo ep {prev})")


async def append_bars(market, sym: str, last_ep: dict[str, int]) -> None:
    bars = await market.get_bars(sym, interval="1m", limit=60)
    now = time.time()
    path = DATA / f"bars_{sym.lower()}_ibkr.txt"
    new = []
    prev = last_ep.get(sym, 0)
    for b in bars:
        ep = _minute_epoch(b.timestamp)
        if ep + 60 > now or ep <= prev or b.close <= 0:
            continue
        new.append(_bar_line(ep, b.open, b.high, b.low, b.close, b.volume))
        prev = ep
    if new:
        with open(path, "a") as fh:
            fh.write("".join(new))
        last_ep[sym] = prev
        log(f"{sym}: +{len(new)} barras (ep {prev})")


# ---------------- NBBO (data/nbbo_<sym>.txt) ----------------

def write_nbbo(sym: str, q: Quote, exch_ts: dict[str, str]) -> bool:
    bid, ask = float(q.bid), float(q.ask)
    if not (ask > bid > 0):   # fail-loud: quote invalido -> NO escribir cero plausible
        log(f"{sym}: NBBO invalido bid={bid} ask={ask} (no se escribe)")
        return False
    # epoch = tiempo REAL de bolsa (q.timestamp), NO wall-clock: asi el gate de frescura de
    # los bots (now-ep<=10s, aapl_signal_bot.cpp:176) falla-cerrado con dato delayed en vez de
    # tratar un spread de hace 15 min como vivo. Con feed realtime pasa; con delayed se rechaza.
    ep = int(q.timestamp.timestamp())
    _atomic_write(DATA / f"nbbo_{sym.lower()}.txt", f"{ep:.0f} {bid:.4f} {ask:.4f}\n")
    exch_ts[sym] = q.timestamp.isoformat()
    return True


# ---------------- OPTION CHAIN (data/opt_chain_<sym>.txt) ----------------

def _num(x: float | None) -> float:
    return -1.0 if x is None else float(x)


BAND_PCT = 0.15   # ±15% del spot, como el contrato de opt_chain_cache (evita meter LEAPS)
NEAR_EXPS = 2     # 2 vencimientos mas cercanos (P/C y muros de opt_quick se calculan sobre esto)


def _band_chain(chain: list[OptionContract], spot: float) -> list[OptionContract]:
    """Recorta a los 2 vencimientos cercanos + strikes ±BAND_PCT del spot. Sin banda si no
    hay spot fiable (spot<=0): se devuelve la cadena entera y el header lo declara (band -1)."""
    exps = sorted({c.expiration for c in chain})[:NEAR_EXPS]
    out = [c for c in chain if c.expiration in exps]
    if spot > 0:
        lo, hi = spot * (1 - BAND_PCT), spot * (1 + BAND_PCT)
        out = [c for c in out if lo <= c.strike <= hi]
    return out or [c for c in chain if c.expiration in exps]  # nunca devolver vacio por banda


def write_chain(sym: str, chain: list[OptionContract], spot: float, source: str) -> int:
    if not chain:
        raise RuntimeError(f"{sym}: cadena vacia")
    banded = _band_chain(chain, spot)
    exps = sorted({c.expiration for c in banded})
    exps_ymd = [e.strftime("%Y%m%d") for e in exps]
    greeks_ok = sum(1 for c in banded if c.gamma is not None) / len(banded)
    ba_ok = sum(1 for c in banded if c.bid > 0 or c.ask > 0) / len(banded)
    band = BAND_PCT if spot > 0 else -1
    ep = int(time.time())
    rows = []
    for c in banded:
        right = "C" if c.option_type == "call" else "P"
        rows.append(
            f"{c.strike:.2f} {right} {c.expiration:%Y%m%d} "
            f"{_num(c.bid if c.bid else None):.2f} {_num(c.ask if c.ask else None):.2f} "
            f"{c.volume:.0f} {c.open_interest:.0f} "
            f"{_num(c.implied_volatility):.4f} {_num(c.delta):.4f} {_num(c.gamma):.6f}"
        )
    header = (
        f"# opt_chain {sym.upper()} | epoch {ep} | {datetime.now():%Y-%m-%d %H:%M:%S} "
        f"| spot {spot:.2f} | exps {' '.join(exps_ymd[:2])}\n"
        f"# fuente {source} | band {band:.4f} | max_strikes {len(rows)} | narrow 0 "
        f"| vencimientos {len(exps)} | rows {len(rows)} "
        f"| greeks_ok_pct {greeks_ok:.4f} | bidask_ok_pct {ba_ok:.4f}\n"
        f"# strike right exp bid ask vol oi iv delta gamma\n"
    )
    _atomic_write(DATA / f"opt_chain_{sym.lower()}.txt", header + "\n".join(rows) + "\n")
    return len(rows)


# ---------------- provenance sidecar ----------------

def write_status(settings, exch_ts: dict[str, str], entitlement: list[str]) -> None:
    status = {
        "epoch": int(time.time()),
        "market_provider": settings.market_provider,
        "options_provider": settings.options_provider,
        "entitlement_messages": entitlement,
        "last_exchange_ts": exch_ts,
        "note": "epoch de bars/nbbo = tiempo REAL de bolsa; comparar last_exchange_ts vs now para latencia",
    }
    if settings.market_provider == "intrinio":  # sources solo aplican a intrinio
        status["intrinio_stock_source"] = settings.intrinio_stock_source
        status["intrinio_interval_source"] = settings.intrinio_interval_source
    _atomic_write(DATA / "provider_status.json", json.dumps(status, indent=2))


# ---------------- loop ----------------

async def one_pass(providers, settings, syms, last_ep, exch_ts, do_warmup, do_chain, entitlement):
    for sym in syms:
        try:
            if do_warmup:
                await warmup_bars(providers.market, sym, last_ep)
            else:
                await append_bars(providers.market, sym, last_ep)
        except Exception as e:  # per-capability degradation, fail-loud (key redactada)
            log(f"{sym}: BARS error {_scrub(e)}")
        spot = 0.0
        try:
            q = await providers.market.get_quote(sym)
            spot = float(q.last or (q.bid + q.ask) / 2)
            write_nbbo(sym, q, exch_ts)
            if not entitlement:
                entitlement.extend(getattr(q, "_messages", []) or [])
        except Exception as e:
            log(f"{sym}: QUOTE error {_scrub(e)}")
        if do_chain:
            # Un ReadTimeout puntual dejaba al simbolo SIN cadena toda la sesion (medido
            # 2026-08-02: NFLX/GLD/XLK sin opt_chain_*.txt mientras Polygon si los servia).
            # Un simbolo de la flota sin mapa de opciones no es un error transitorio: es un
            # ticker mudo. Se reintenta una vez antes de darlo por perdido.
            for intento in (1, 2):
                try:
                    chain = await providers.options.get_option_chain(sym)
                    n = write_chain(sym, chain, spot or _spot_from_chain(chain),
                                    settings.options_provider)
                    log(f"{sym}: cadena {n} filas -> opt_chain_{sym.lower()}.txt"
                        + (f" (intento {intento})" if intento > 1 else ""))
                    break
                except Exception as e:
                    if intento == 1:
                        log(f"{sym}: CHAIN fallo 1/2 {_scrub(e)} — reintentando")
                        await asyncio.sleep(2)
                    else:
                        log(f"{sym}: CHAIN error tras 2 intentos {_scrub(e)} — SIN MAPA DE OPCIONES")
    write_status(settings, exch_ts, entitlement)


def _spot_from_chain(chain: list[OptionContract]) -> float:
    # spot honesto o -1: JAMAS fabricar (chain[0].strike seria el strike mas bajo, spot falso).
    # write_chain escribe spot -1; opt_quick.cpp ya guarda spot>0 para marcadores ATM/muros.
    atm = [c for c in chain if c.delta is not None and 0.3 < abs(c.delta) < 0.7]
    return atm[len(atm) // 2].strike if atm else -1.0


async def run(syms: list[str], daemon: bool) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    providers = build_providers(settings)
    # GUARD anti-mock: si la config resuelve a Mock/Unavailable, ABORTAR — jamas inyectar datos
    # sinteticos en los ficheros que lee la flota (doctrina: nada de datos fabricados en señal).
    allow_mock = os.environ.get("IBT_ALLOW_MOCK") == "1"  # SOLO tests offline; produccion jamas
    for cap, prov in (("market", providers.market), ("options", providers.options)):
        bad = type(prov).__name__ in {"MockProvider", "UnavailableProvider"}
        if bad and not (allow_mock and type(prov).__name__ == "MockProvider"):
            raise SystemExit(
                f"[provider_bridge] ABORTO: capacidad '{cap}' resolvio a {type(prov).__name__}. "
                f"Configura MIT_{cap.upper()}_PROVIDER en config/feeds.env (market=intrinio, options=polygon). "
                f"NO se escribe nada — un feed mock en la flota es dato fabricado."
            )
    log(f"market={type(providers.market).__name__} options={type(providers.options).__name__} syms={len(syms)}")
    last_ep: dict[str, int] = {}
    exch_ts: dict[str, str] = {}
    entitlement: list[str] = []
    # primera pasada: warmup barras + cadena
    await one_pass(providers, settings, syms, last_ep, exch_ts, True, True, entitlement)
    if not daemon:
        await providers.close()
        return
    last_chain = time.time()
    try:
        while True:
            await asyncio.sleep(BARS_REFRESH_S)
            do_chain = time.time() - last_chain >= CHAIN_REFRESH_S
            if do_chain:
                last_chain = time.time()
            await one_pass(providers, settings, syms, last_ep, exch_ts, False, do_chain, entitlement)
    finally:
        await providers.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("syms", nargs="*")
    a = ap.parse_args()
    syms = [s.upper() for s in a.syms] or _fleet_syms()
    asyncio.run(run(syms, daemon=a.daemon and not a.once))


if __name__ == "__main__":
    main()
