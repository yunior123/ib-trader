"""intrinio_replay_check.py — valida el camino realtime de Intrinio CON EL MERCADO CERRADO.

El socket de Intrinio se apaga fuera de horario (lo documentan ellos: "the websocket servers are
off for the night"), asi que no se puede probar el camino vivo un domingo. Pero el mismo feed
existe como fichero de replay diario, y su formato es autodelimitado desde el byte 0:

    [tipo(1)][longitud(1)][mensaje(longitud-2)][time_received(8, <Q)]  repetido

=> se puede leer un PREFIJO por HTTP Range y parsearlo con el parser del propio SDK, sin bajar los
~3,2 GB del dia. Eso valida formato, nombres de campo, unidad del timestamp y nuestros callbacks
antes de que abra el mercado, que es cuando no hay tiempo de depurar.

Uso:  ./venv-mit/bin/python scripts/intrinio_replay_check.py [--date YYYY-MM-DD] [--mb 8]
Salida 0 = camino validado. Salida != 0 = algo no cuadra (y dice que).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import types
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API = "https://api-v2.intrinio.com"


def load_key() -> str:
    key = os.environ.get("INTRINIO_API_KEY")
    if not key:
        for line in (REPO / "config" / "feeds.env").read_text().splitlines():
            if line.strip().startswith("INTRINIO_API_KEY="):
                key = line.partition("=")[2].strip()
                break
    if not key:
        raise RuntimeError("INTRINIO_API_KEY ausente en env y en config/feeds.env")
    return key


def ultimo_dia_habil() -> str:
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    if d == date.today():
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d.isoformat()


def url_replay(key: str, dia: str, subsource: str = "equities_edge") -> tuple[str, str]:
    import requests

    r = requests.get(f"{API}/securities/replay",
                     params={"subsource": subsource, "date": dia, "api_key": key}, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"/securities/replay {subsource} {dia} -> HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    return j["url"].replace("\\u0026", "&"), j["name"]


def descargar_prefijo(url: str, mb: int) -> bytes:
    import requests

    n = mb * 1024 * 1024
    r = requests.get(url, headers={"Range": f"bytes=0-{n - 1}"}, timeout=300)
    if r.status_code not in (200, 206):
        raise RuntimeError(f"descarga del prefijo -> HTTP {r.status_code}")
    return r.content


def parsear(data: bytes, on_trade, on_quote) -> dict:
    """Recorre el prefijo con el parser del SDK. Devuelve el conteo REAL, sin estimar."""
    from intriniorealtime.equities_client import EquitiesQuoteHandler

    cliente = types.SimpleNamespace(
        on_trade=on_trade, on_quote=on_quote,
        logger=types.SimpleNamespace(error=lambda *a: None, debug=lambda *a: None),
    )
    handler = EquitiesQuoteHandler(cliente, bypass_parsing=False)

    i, ok, err, tipos = 0, 0, 0, {}
    while i + 2 < len(data):
        mlen = data[i + 1]
        if mlen < 3 or i + mlen + 8 > len(data):
            break
        tipos[data[i]] = tipos.get(data[i], 0) + 1
        try:
            handler.parse_message(data[i:i + mlen], 0, 0)
            ok += 1
        except Exception:
            err += 1
        i += mlen + 8
    return {"ok": ok, "err": err, "tipos": tipos}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (por defecto: ultimo dia habil)")
    ap.add_argument("--mb", type=int, default=8, help="MB de prefijo a leer (default 8)")
    ap.add_argument("--subsource", default="equities_edge")
    args = ap.parse_args()

    dia = args.date or ultimo_dia_habil()
    key = load_key()
    url, nombre = url_replay(key, dia, args.subsource)
    print(f"  fichero   : {nombre}")

    data = descargar_prefijo(url, args.mb)
    print(f"  prefijo   : {len(data) / 1e6:.1f} MB")

    sys.path.insert(0, str(REPO / "mit"))
    os.environ.setdefault("INTRINIO_API_KEY", key)
    from backend.app.config import Settings
    from backend.app.providers.base import ProviderError
    from backend.app.providers.intrinio_realtime import IntrinioRealtimeProvider

    prov = IntrinioRealtimeProvider(Settings())
    prov._ensure_client = lambda: None
    prov._join = lambda s: None

    ts = []

    def on_trade(t, backlog=0):
        ts.append(t.timestamp / 1e9)
        prov._on_trade(t)

    r = parsear(data, on_trade, lambda q, backlog=0: prov._on_quote(q))
    etiquetas = {0: "trade", 1: "quote-ask", 2: "quote-bid"}
    print(f"  mensajes  : {r['ok']:,} parseados, {r['err']:,} fallos")
    for k in sorted(r["tipos"]):
        print(f"    {etiquetas.get(k, f'tipo {k}'):10s} {r['tipos'][k]:>9,}")
    if not ts:
        print("  FALLO: ningun trade con timestamp valido")
        return 2
    print(f"  bolsa     : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min(ts)))}"
          f" -> {time.strftime('%H:%M:%S', time.localtime(max(ts)))} ET")

    if r["err"]:
        print(f"  FALLO: {r['err']} mensajes no parsean — el formato cambio")
        return 3
    if not prov._trades:
        print("  FALLO: el provider no registro ni un tick")
        return 4

    sym = next((s for s in ("SPY", "QQQ", "NVDA", "AAPL") if s in prov._trades), sorted(prov._trades)[0])
    import asyncio

    async def comprobar() -> int:
        try:
            await prov.get_quote(sym)
            print(f"  FALLO: get_quote({sym}) devolvio un precio con un tick de {dia} (deberia levantar)")
            return 5
        except ProviderError as e:
            if e.error_code != "no_tick":
                print(f"  FALLO: levanto {e.error_code}, se esperaba no_tick")
                return 6
        # mismo tick con reloj de ahora -> tiene que salir un Quote coherente
        _, price, size = prov._trades[sym]
        ahora = time.time()
        prov._trades[sym] = (ahora, price, size)
        if sym in prov._quotes:
            prov._quotes[sym] = {k: (v[0], v[1], ahora) for k, v in prov._quotes[sym].items()}
        q = await prov.get_quote(sym)
        if q.bid and q.ask and q.ask < q.bid:
            print(f"  FALLO: spread invertido bid={q.bid} ask={q.ask}")
            return 7
        print(f"  provider  : rancio->levanta OK | fresco->{sym} last={q.last} bid={q.bid} ask={q.ask}")
        return 0

    rc = asyncio.run(comprobar())
    print("  RESULTADO : camino realtime VALIDADO" if rc == 0 else "  RESULTADO : FALLO")
    return rc


if __name__ == "__main__":
    sys.exit(main())
