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

PUNTO UNICO DE DECISION DE PROVEEDOR (orden Yunior 2026-08-03): la tabla `PROVEEDORES` de
este fichero declara capacidades y clase de latencia de cada uno (ibkr incluido, apagado por
condicional pero con su codigo intacto en scripts/ibkr_bar_bridge.py y opt_chain_cache.py) y
`resolve_spot()` elige el precio vivo por FRESCURA medida. Añadir/quitar un proveedor se hace
aqui; ningun consumidor cambia. El interruptor sigue siendo data/market_source.txt.

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
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mit"))
sys.path.insert(0, str(REPO / "scripts"))

import rt_last  # noqa: E402  el PRINT en tiempo real (Finnhub WS), fuera de la capa mit/

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
WARMUP_BARS = 1440       # 24h de 1m: tope de display (Yunior 2026-08-04); backtest vive en poly_bars/history
BARS_PRUNE_LINES = 2880  # al doblar el tope se poda el fichero a WARMUP_BARS (lectores lo releen entero)


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
        try:
            lines = path.read_text().splitlines(keepends=True)
            if len(lines) > BARS_PRUNE_LINES:
                _atomic_write(path, "".join(lines[-WARMUP_BARS:]))
                log(f"{sym}: poda {len(lines)}->{WARMUP_BARS} barras (tope display 24h)")
        except OSError as e:
            log(f"{sym}: poda fallo {e}")


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
# 8 y no 2 (Yunior 2026-08-03: "data for options net, gex for next weeks, at least 2-3 from now,
# whole agoust"): con 2 los 0DTE se comian el fichero y QQQ/SPY publicaban UN solo vencimiento.
# El mapa GEX por defecto NO cambia: gex_core.py:1121 filtra al vencimiento mas cercano vivo.
NEAR_EXPS = int(os.environ.get("IBT_NEAR_EXPS", "8"))
HDR_EXPS = 7      # opt_quick.cpp lee `%63[0-9 ]`: 7 fechas (62 chars) es el tope sin truncar


def _band_chain(chain: list[OptionContract], spot: float) -> list[OptionContract]:
    """Recorta a los 2 vencimientos cercanos + strikes ±BAND_PCT del spot. Sin banda si no
    hay spot fiable (spot<=0): se devuelve la cadena entera y el header lo declara (band -1)."""
    exps = sorted({c.expiration for c in chain})[:NEAR_EXPS]
    out = [c for c in chain if c.expiration in exps]
    if spot > 0:
        lo, hi = spot * (1 - BAND_PCT), spot * (1 + BAND_PCT)
        out = [c for c in out if lo <= c.strike <= hi]
    return out or [c for c in chain if c.expiration in exps]  # nunca devolver vacio por banda


def write_chain(sym: str, chain: list[OptionContract], spot: float, source: str,
                spot_src: str = "?", spot_age: float = -1.0) -> int:
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
        # spot_src/spot_age: opt_quick.cpp busca "spot " CON espacio, asi que "spot_src" no
        # colisiona; y la linea sigue muy por debajo de su buffer de 256.
        f"# opt_chain {sym.upper()} | epoch {ep} | {datetime.now():%Y-%m-%d %H:%M:%S} "
        f"| spot {spot:.2f} | spot_src {spot_src} | spot_age {spot_age:.0f} "
        f"| exps {' '.join(exps_ymd[:HDR_EXPS])}\n"
        f"# fuente {source} | band {band:.4f} | max_strikes {len(rows)} | narrow 0 "
        f"| vencimientos {len(exps)} | rows {len(rows)} "
        f"| greeks_ok_pct {greeks_ok:.4f} | bidask_ok_pct {ba_ok:.4f}\n"
        f"# strike right exp bid ask vol oi iv delta gamma\n"
    )
    _atomic_write(DATA / f"opt_chain_{sym.lower()}.txt", header + "\n".join(rows) + "\n")
    return len(rows)


# ---------------- provenance sidecar ----------------

PRINT_MAX_AGE_S = float(os.environ.get("IBT_PRINT_MAX_AGE_S", "120"))

# ---------------- ENRUTADO DE PROVEEDORES: EL UNICO PUNTO DE DECISION -------------------
# Orden Yunior 2026-08-03: "put conditionals per data provider, remember to have all generic
# to avoid deleting code, and modifying preferably just one service file". Cada proveedor
# DECLARA sus capacidades y su clase de latencia; nadie se borra — IBKR sigue entero (sus
# puentes viven en scripts/ibkr_bar_bridge.py y scripts/opt_chain_cache.py, y los lanza
# fleet_keepalive_start.sh cuando data/market_source.txt == "ibkr"). Añadir/quitar proveedor
# = tocar esta tabla, jamas un consumidor.
#   prio: menor = manda cuando el dato es igual de fresco. 'tiempo_real' medido, no de la doc.
PROVEEDORES = {
    "ibkr":     {"caps": ["bars", "nbbo", "chain", "print"], "latencia": "tiempo_real",
                 "prio": 0, "activo_si": "market_source==ibkr",
                 "nota": "OFF esta semana por orden de Yunior; codigo intacto"},
    "finnhub":  {"caps": ["print"], "latencia": "tiempo_real", "prio": 1,
                 "activo_si": "data/rt_last_<SYM>.txt fresco",
                 "nota": "WS gratis: 0,00-0,04 s medido; sin libro y cinta MUESTREADA"},
    "intrinio": {"caps": ["bars", "nbbo", "quote"], "latencia": "delayed_15m", "prio": 8,
                 "activo_si": "market_source==intrinio", "nota": "cboe_one_delayed: ~1.100 s medido"},
    "polygon":  {"caps": ["chain"], "latencia": "delayed_15m", "prio": 9,
                 "activo_si": "MIT_OPTIONS_PROVIDER==polygon", "nota": "griegas y OI reales"},
}


def _print_vivo(sym: str):
    """(precio, epoch, fuente, edad_s) del PRINT en tiempo real, o None. Generico: la fuente
    la declara el propio fichero, asi que manana lo puede escribir IBKR sin tocar nada aqui."""
    return rt_last.fresh(sym, PRINT_MAX_AGE_S)


def resolve_spot(sym: str, q_last: float, q_age: float):
    """(spot, fuente, edad_s) — resolvedor GENERICO de precio vivo, punto unico de decision.
    Manda el candidato mas FRESCO y, a igualdad, el de menor `prio` (tiempo real antes que
    delayed). La fuente viaja SIEMPRE con el numero; (0.0,'ninguna',-1) = no se sabe."""
    cands = []
    p = _print_vivo(sym)
    if p is not None:
        cands.append((p[3], PROVEEDORES.get(p[2], {}).get("prio", 5), p[0], p[2]))
    if q_last > 0:
        activo = os.environ.get("MIT_MARKET_PROVIDER", "intrinio")
        cands.append((q_age if q_age >= 0 else 1e9,
                      PROVEEDORES.get(activo, {}).get("prio", 5), q_last, f"{activo}_quote"))
    if not cands:
        return (0.0, "ninguna", -1.0)
    edad, _prio, px, src = min(cands)
    return (px, src, edad)


def bar_salud(sym: str):
    """(edad_ultima_barra_s, huecos_en_las_ultimas_30, vol_cero_en_las_ultimas_30) o (None,..).
    El cockpit cantaba 'SIN LECTURA - barras no contiguas' sin decir de donde salia el hueco:
    aqui se MIDE y se publica. None y no 0: un 0 seria 'recien salida y perfecta'."""
    p = DATA / f"bars_{sym.lower()}_ibkr.txt"
    try:
        with open(p, "rb") as fh:
            fh.seek(max(0, os.path.getsize(p) - 4000))
            lines = fh.read().decode(errors="ignore").strip().split("\n")[-30:]
        eps = [int(float(x.split()[0])) for x in lines if x.split()]
        vols = [float(x.split()[5]) for x in lines if len(x.split()) > 5]
        huecos = sum(1 for a, b in zip(eps, eps[1:]) if b - a != 60)
        return (round(time.time() - eps[-1], 1), huecos, sum(1 for v in vols if v == 0))
    except (OSError, ValueError, IndexError):
        return (None, None, None)


# Mismos nombres de env que lee fleet_consensus.py:41-42, para que el veredicto sea el SUYO y no
# una copia que se desincronice. Aqui solo se MIDE y se DECLARA; el gate sigue siendo suyo.
CONS_MAX_BAR_AGE = float(os.environ.get("FLEET_CONS_MAX_BAR_AGE", "180"))
CONS_MIN_COVER = float(os.environ.get("FLEET_CONS_MIN_COVER", "0.90"))


def veredicto_manada(lat: dict) -> dict:
    """¿Puede votar la MANADA con este feed? Con barras delayed la respuesta es NO, y el
    silencio no vale: fleet_consensus falla cerrado ('cobertura insuficiente') sin decir que
    la causa es el FEED, no el mercado. Aqui se dice, con numeros."""
    edades = {s: v["bar_s"] for s, v in lat.items() if v["bar_s"] is not None}
    votan = [s for s, e in edades.items() if e <= CONS_MAX_BAR_AGE]
    need = int(len(lat) * CONS_MIN_COVER)
    med = sorted(edades.values())[len(edades) // 2] if edades else None
    return {
        "operativa": len(votan) >= need,
        "votan": len(votan), "need": need, "universo": len(lat),
        "max_bar_age_s": CONS_MAX_BAR_AGE, "bar_age_mediana_s": med,
        "motivo": (None if len(votan) >= need else
                   (f"barras a {med:.0f} s de mediana" if med is not None else "SIN barras")
                   + f" contra un tope de {CONS_MAX_BAR_AGE:.0f} s: "
                   f"solo {len(votan)}/{len(lat)} pueden votar (hacen falta {need}). "
                   f"Es el FEED ({', '.join(n for n, p in PROVEEDORES.items() if 'bars' in p['caps'] and p['latencia'] != 'tiempo_real')} "
                   f"va delayed), no el mercado."),
    }


def _rth(ahora=None) -> bool:
    t = datetime.fromtimestamp(ahora or time.time(), ZoneInfo("America/New_York"))
    return t.weekday() < 5 and 9 * 60 + 30 <= t.hour * 60 + t.minute < 16 * 60


_grito_manada = 0.0


_GRITO_MANADA_F = REPO / "data" / ".manada_muda_grito"


def _grito_manada_reciente(ventana_s: float = 1800.0) -> bool:
    """Throttle por MTIME de un side-file: sobrevive reinicios del puente.

    En memoria, cada relanzamiento de com.ibtrader.fleet (StartInterval 300) reseteaba el
    throttle: un crash-loop en RTH convertia "1 aviso/30 min" en 1 por relanzamiento.
    """
    try:
        return time.time() - _GRITO_MANADA_F.stat().st_mtime < ventana_s
    except OSError:
        return False


def grita_si_manada_muda(v: dict) -> None:
    """Una MANADA inoperante en RTH tiene que DOLER: es la alarma de rebaño apagada."""
    global _grito_manada
    if v["operativa"] or not _rth() or time.time() - _grito_manada < 1800 \
            or _grito_manada_reciente():
        return
    _grito_manada = time.time()
    try:
        _GRITO_MANADA_F.touch()
    except OSError:
        pass
    med = v["bar_age_mediana_s"]
    msg = (f"Alarma de manada inoperante: solo {v['votan']} de {v['universo']} simbolos "
           + (f"pueden votar. Las barras llegan con {med:.0f} segundos." if med is not None
              else "pueden votar. No hay barras."))
    print(f"{LOG_PREFIX} MANADA MUDA — {v['motivo']}", flush=True)
    try:
        subprocess.Popen(["/bin/bash", str(REPO / "scripts" / "speak.sh"), "DANGER", msg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    # embudo (ntfy + Discord): el denominador fabricado ya disparo un DANGER falso
    # (21/26 = 80,8% cuando era 21/30 = 70%). Fuera del Mac esto era mudo.
    # Con guarda: este es el UNICO feed de la flota esta semana; un aviso jamas lo tumba.
    try:
        import notify_short
        notify_short.push("🕳 MANADA MUDA",
                          f"Manada inoperante: solo {v['votan']} de {v['universo']} pueden votar.")
    except Exception as e:
        print(f"{LOG_PREFIX} push MANADA MUDA fallo: {e}", flush=True)


def write_status(settings, exch_ts: dict[str, str], entitlement: list[str],
                 lat: dict | None = None) -> None:
    status = {
        "epoch": int(time.time()),
        "market_provider": settings.market_provider,
        "options_provider": settings.options_provider,
        "proveedores": PROVEEDORES,
        "print_file": "data/rt_last_<SYM>.txt",
        "entitlement_messages": entitlement,
        "last_exchange_ts": exch_ts,
        "latencia": lat or {},
        "note": "epoch de bars/nbbo = tiempo REAL de bolsa; comparar last_exchange_ts vs now para latencia",
    }
    if lat:
        # Lo que un consumidor necesita de un vistazo: quien manda en el spot y cuanto sobra.
        rt = {n for n, p in PROVEEDORES.items() if p["latencia"] == "tiempo_real"}
        status["spot_delayed"] = sorted(s for s, v in lat.items()
                                        if v["spot_src"].split("_")[0] not in rt)
        edades = [v["bar_s"] for v in lat.values() if v["bar_s"] is not None]
        status["bar_age_max_s"] = max(edades) if edades else None
        status["bar_huecos"] = sorted(s for s, v in lat.items() if v["bar_huecos"])
        status["manada"] = veredicto_manada(lat)
        grita_si_manada_muda(status["manada"])
    if settings.market_provider == "intrinio":  # sources solo aplican a intrinio
        status["intrinio_stock_source"] = settings.intrinio_stock_source
        status["intrinio_interval_source"] = settings.intrinio_interval_source
    _atomic_write(DATA / "provider_status.json", json.dumps(status, indent=2))


# ---------------- loop ----------------

async def _chain_once(providers, settings, sym, spot, spot_src, spot_age) -> None:
    # Un ReadTimeout puntual dejaba al simbolo SIN cadena toda la sesion (medido
    # 2026-08-02: NFLX/GLD/XLK sin opt_chain_*.txt mientras Polygon si los servia).
    # Un simbolo de la flota sin mapa de opciones no es un error transitorio: es un
    # ticker mudo. Se reintenta una vez antes de darlo por perdido.
    for intento in (1, 2):
        try:
            chain = await providers.options.get_option_chain(sym)
            n = write_chain(sym, chain, spot or _spot_from_chain(chain),
                            settings.options_provider,
                            spot_src if spot else "chain_atm", spot_age)
            log(f"{sym}: cadena {n} filas -> opt_chain_{sym.lower()}.txt"
                + (f" (intento {intento})" if intento > 1 else ""))
            break
        except Exception as e:
            if intento == 1:
                log(f"{sym}: CHAIN fallo 1/2 {_scrub(e)} — reintentando")
                await asyncio.sleep(2)
            else:
                log(f"{sym}: CHAIN error tras 2 intentos {_scrub(e)} — SIN MAPA DE OPCIONES")


async def chain_loop(providers, settings, syms, last_q: dict) -> None:
    """Cadenas en tarea PROPIA: 26 cadenas Polygon x ~8 s = ~3,5 min que antes iban EN SERIE
    con barras/nbbo — el camino vivo quedaba rehen y cada simbolo se refrescaba cada ~4 min
    (medido 2026-08-04: '+4 barras' de golpe). El spot viene del ultimo quote del bucle vivo."""
    while True:
        t0 = time.time()
        for sym in syms:
            px, qa, med = last_q.get(sym, (0.0, -1.0, 0.0))
            q_age = (qa + (time.time() - med)) if px > 0 else -1.0
            spot, spot_src, spot_age = resolve_spot(sym, px, q_age)
            await _chain_once(providers, settings, sym, spot, spot_src, spot_age)
        await asyncio.sleep(max(1.0, CHAIN_REFRESH_S - (time.time() - t0)))


async def one_pass(providers, settings, syms, last_ep, exch_ts, do_warmup, do_chain,
                   entitlement, last_q: dict | None = None):
    lat: dict[str, dict] = {}
    for sym in syms:
        try:
            if do_warmup:
                await warmup_bars(providers.market, sym, last_ep)
            else:
                await append_bars(providers.market, sym, last_ep)
        except Exception as e:  # per-capability degradation, fail-loud (key redactada)
            log(f"{sym}: BARS error {_scrub(e)}")
        q_last, q_age = 0.0, -1.0
        try:
            q = await providers.market.get_quote(sym)
            q_last = float(q.last or (q.bid + q.ask) / 2)
            q_age = round(time.time() - q.timestamp.timestamp(), 1)
            write_nbbo(sym, q, exch_ts)
            if not entitlement:
                entitlement.extend(getattr(q, "_messages", []) or [])
        except Exception as e:
            log(f"{sym}: QUOTE error {_scrub(e)}")
        if last_q is not None and q_last > 0:
            last_q[sym] = (q_last, q_age, time.time())
        spot, spot_src, spot_age = resolve_spot(sym, q_last, q_age)
        edad_bar, huecos, vol0 = bar_salud(sym)
        # `ts`: la pasada recorre 26 simbolos y dura de 30 s a 8 min (warmup). Sin el instante
        # de medida, una edad de este bloque se leeria como si fuese de ahora mismo.
        lat[sym] = {"ts": int(time.time()), "bar_s": edad_bar, "bar_huecos": huecos,
                    "bar_vol0": vol0, "quote_s": q_age if q_last > 0 else None,
                    "spot": spot or None, "spot_src": spot_src, "spot_s": spot_age}
        if do_chain:
            await _chain_once(providers, settings, sym, spot, spot_src, spot_age)
    write_status(settings, exch_ts, entitlement, lat)


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
    last_q: dict[str, tuple] = {}
    # primera pasada: warmup de barras SIN cadena (la cadena la trae chain_loop en paralelo;
    # en --once si va inline para que el contrato de una pasada quede completo)
    await one_pass(providers, settings, syms, last_ep, exch_ts, True, not daemon, entitlement, last_q)
    if not daemon:
        await providers.close()
        return
    chains = asyncio.create_task(chain_loop(providers, settings, syms, last_q))
    try:
        while True:
            await asyncio.sleep(BARS_REFRESH_S)
            if chains.done():  # fail-loud: sin cadenas la flota se queda sin mapa de muros
                exc = chains.exception()
                log(f"CHAIN LOOP MUERTO ({_scrub(exc) if exc else 'sin excepcion'}) — relanzando")
                chains = asyncio.create_task(chain_loop(providers, settings, syms, last_q))
            await one_pass(providers, settings, syms, last_ep, exch_ts, False, False, entitlement, last_q)
    finally:
        chains.cancel()
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
