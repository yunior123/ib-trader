#!/usr/bin/env python3
"""finnhub_ws_bridge.py — WebSocket de trades US en TIEMPO REAL (el PRINT que faltaba).

Por que: con IBKR fuera esta semana, todo lo que alimentaba a la flota era REST con retraso
(Polygon declara ~15 min) y el WebSocket de Intrinio esta APAGADO del lado del vendor —
medido el 2026-08-02 en los 7 hosts: TLS con cert `*.intrinio.com` valido, ALPN sin acordar y
cierre a los 5,13 s sin una sola cabecera HTTP. Probados los otros sockets con nuestras keys
el mismo dia: Polygon responde `auth_failed "Your plan doesn't include websocket access"`, y
Unusual Whales acepta el TCP en `/api/socket` pero corta al instante y `/api/socket` REST
devuelve `{"data":[]}` (sin canales). **El unico WebSocket que nuestras keys abren y que
acepta suscripciones es el de Finnhub** (verificado: conecta, admite los simbolos y late).

Escribe `data/rt_last_<SYM>.txt` via `rt_last.write_if_newer` (un solo dueño por fichero: solo
pisa quien trae un tick mas nuevo, para que convivan varios streams). NO toca `bars_*` ni
`nbbo_*`: de esos ya hay un escritor (`provider_bridge`) y dos escritores en el mismo fichero
es corrupcion silenciosa.

Finnhub gratis = trades de acciones US. No trae libro -> no hay bid/ask -> no se escribe NBBO
(un `bid=ask=last` daria spread 0,00% y colaria el gate: prohibido el cero plausible).

Uso: finnhub_ws_bridge.py [--syms A B C] [--seconds N]
"""
import asyncio
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import rt_last  # noqa: E402

URL = "wss://ws.finnhub.io?token={key}"
FUENTE = "finnhub"
STATUS = os.path.join(ROOT, "data", "ws_finnhub_status.json")
MAX_SUBS = int(os.environ.get("FINNHUB_WS_MAX_SUBS", "50"))
BACKOFF_MAX_S = 60.0


def load_key():
    k = (os.environ.get("FINNHUB_KEY") or "").strip()
    if k:
        return k
    with open(os.path.join(ROOT, "config", "feeds.env")) as f:
        for ln in f:
            if ln.startswith("FINNHUB_KEY="):
                return ln.split("=", 1)[1].strip()
    raise SystemExit("finnhub_ws_bridge ROTO: sin FINNHUB_KEY (entorno ni feeds.env)")


def simbolos(argv):
    if "--syms" in argv:
        i = argv.index("--syms") + 1
        out = [a.upper() for a in argv[i:] if not a.startswith("--")]
        if out:
            return out[:MAX_SUBS]
    for p in ("data/provider_syms.txt", "data/fleet.txt"):
        if os.path.exists(p):
            syms = open(p).read().split()
            if syms:
                return syms[:MAX_SUBS]
    raise SystemExit("finnhub_ws_bridge ROTO: sin universo")


def estado(**kw):
    prev = {}
    if os.path.exists(STATUS):
        try:
            prev = json.load(open(STATUS))
        except (OSError, ValueError):
            prev = {}
    prev.update(kw)
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(prev, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATUS)


def grita(msg, nivel="DANGER"):
    print(msg, file=sys.stderr, flush=True)
    try:
        subprocess.Popen(["/bin/bash", os.path.join(ROOT, "scripts", "speak.sh"), nivel, msg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


async def sesion(key, syms, hasta=None):
    """Una conexion. Devuelve (n_trades, motivo_de_salida)."""
    import websockets

    n = 0
    ultimo = 0.0
    async with websockets.connect(URL.format(key=key), open_timeout=15,
                                  close_timeout=5, ping_interval=20) as ws:
        for s in syms:
            await ws.send(json.dumps({"type": "subscribe", "symbol": s}))
        estado(conectado=True, desde=int(time.time()), simbolos=syms, fuente=FUENTE,
               nbbo=None, nbbo_motivo="Finnhub gratis no trae libro: no se escribe nbbo_*")
        print(f"[finnhub-ws] conectado, {len(syms)} simbolos suscritos", flush=True)
        while hasta is None or time.time() < hasta:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                estado(ts=int(time.time()), trades=n, ultimo_trade=int(ultimo))
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") != "trade":
                continue
            for d in msg.get("data") or []:
                sym, px, ts = d.get("s"), d.get("p"), d.get("t")
                if not sym or not px or not ts:
                    continue
                # `t` es el reloj de BOLSA en ms. Marcar con la hora de llegada disfrazaria
                # de vivo un tick retrasado y colaria el gate de frescura.
                if rt_last.write_if_newer(sym, float(ts) / 1000.0, float(px),
                                          float(d.get("v") or 0), FUENTE):
                    n += 1
                    ultimo = time.time()
            estado(ts=int(time.time()), trades=n, ultimo_trade=int(ultimo))
    return n, "fin"


async def main():
    key = load_key()
    syms = simbolos(sys.argv)
    hasta = None
    if "--seconds" in sys.argv:
        hasta = time.time() + float(sys.argv[sys.argv.index("--seconds") + 1])
    print(f"[finnhub-ws] {len(syms)} simbolos: {' '.join(syms)}", flush=True)
    espera = 2.0
    caidas = 0
    while True:
        try:
            n, _ = await sesion(key, syms, hasta)
            print(f"[finnhub-ws] sesion cerrada con {n} trades", flush=True)
            espera = 2.0
            caidas = 0
        except Exception as e:
            caidas += 1
            estado(conectado=False, error=f"{type(e).__name__}: {e}", ts=int(time.time()),
                   caidas=caidas)
            print(f"[finnhub-ws] caida {caidas}: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            if caidas == 5:
                grita("Puente Finnhub caido cinco veces seguidas. Sin print en tiempo real.")
        if hasta is not None and time.time() >= hasta:
            return 0
        await asyncio.sleep(espera)
        espera = min(BACKOFF_MAX_S, espera * 2)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
