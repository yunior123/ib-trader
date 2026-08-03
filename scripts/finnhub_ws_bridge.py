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

MEDIDO 2026-08-03 (sesion viva, ver docs/REALTIME-FUENTES-2026-08-03.md):
  * latencia del tick = 0,00-0,04 s contra el reloj de bolsa. Es TIEMPO REAL de verdad.
  * plan gratis = UN socket por key. Con dos puentes vivos (06:49 ET, pids 82516/84238) el
    vendor expulsa a uno y otro y el log acumulo 9 `ConnectionClosedError: no close frame`.
    -> lockfile obligatorio, y cualquier sonda debe PARAR el puente antes de conectar.
  * la cinta es un MUESTREO, no la consolidada: QQQ 2 trades / 120 acciones en 150 s de
    premarket, y SPY/SMH/NOK MUDOS. Por eso hay contador por simbolo en el status: un
    simbolo sin print se DECLARA, no se rellena con el ultimo precio de otra fuente.
  * REST no sustituye: /quote devuelve el cierre del viernes (t=1785528000, 2,6 dias) y
    /stock/candle da 403 en este plan.

Uso: finnhub_ws_bridge.py [--syms A B C] [--seconds N]
"""
import asyncio
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import rt_last  # noqa: E402

URL = "wss://ws.finnhub.io?token={key}"
FUENTE = "finnhub"
STATUS = os.path.join(ROOT, "data", "ws_finnhub_status.json")
LOCK = os.path.join(ROOT, "data", ".finnhub_ws.lock")
MAX_SUBS = int(os.environ.get("FINNHUB_WS_MAX_SUBS", "50"))
BACKOFF_MAX_S = 60.0
# Plan gratis = UN socket por key: al abrir el segundo, el vendor mata uno de los dos y los
# procesos se turnan a expulsarse. Medido 2026-08-03 06:49 ET con dos puentes vivos (pids
# 82516/84238): 9 `ConnectionClosedError: no close frame` en el log y el print parpadeando.
MUDO_S = float(os.environ.get("FINNHUB_WS_MUDO_S", "300"))   # RTH sin un solo trade = GRITA
STATUS_CADA_S = 1.0      # el status se reescribe como mucho 1/s: en RTH llegan rafagas de ticks
SESION_SANA_S = 120.0    # sesion que aguanta esto = sana: resetea backoff y contador de caidas
ET = ZoneInfo("America/New_York")


def rth(ahora=None):
    """True dentro de 09:30-16:00 ET de un dia laborable (la ventana donde callar es un fallo)."""
    t = datetime.fromtimestamp(ahora or time.time(), ET)
    return t.weekday() < 5 and 9 * 60 + 30 <= t.hour * 60 + t.minute < 16 * 60


def tomar_lock():
    """Instancia unica. Sin esto dos puentes comparten la key y se expulsan en bucle."""
    fh = open(LOCK, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(f"finnhub_ws_bridge ABORTA: ya hay otra instancia ({LOCK}). "
                         "Finnhub gratis admite UN socket por key: dos puentes se matan entre si.")
    fh.write(f"{os.getpid()}\n")
    fh.flush()
    return fh                     # se mantiene abierto mientras viva el proceso


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
    # fleet.txt (30) antes que provider_syms.txt (26): el socket admite 50 suscripciones y los
    # 4 que Intrinio no cubre (DRAM SPCX SKHY EWY) no tienen NINGUN precio vivo sin esto.
    for p in ("data/fleet.txt", "data/provider_syms.txt"):
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


def _publica(n, ultimo, por_sym, mudo, abierta):
    # `sin_print` mira el fichero canonico, NO el contador de esta sesion: al reconectar el
    # contador vuelve a 0 y SMH aparecia como mudo aunque hubiese impreso hace 2 min (paso el
    # 2026-08-03 07:32). Un simbolo escaso no es un simbolo sin cobertura.
    ahora = time.time()
    edades = {}
    for s in por_sym:
        r = rt_last.read(s)
        edades[s] = None if r is None else round(ahora - r[0], 1)
    estado(ts=int(ahora), latido=int(ahora), trades=n, ultimo_trade=int(ultimo),
           mudo_s=round(mudo, 1), mudo=mudo > MUDO_S and rth(), rth=rth(),
           sesion_s=round(ahora - abierta, 1), por_simbolo=por_sym, print_edad_s=edades,
           sin_print=sorted(s for s, e in edades.items() if e is None),
           print_rancio=sorted(s for s, e in edades.items()
                               if e is not None and e > rt_last.MAX_AGE_S))


async def sesion(key, syms, hasta=None):
    """Una conexion. Devuelve (n_trades, segundos_vivo)."""
    import websockets

    n, ultimo = 0, 0.0
    abierta = time.time()
    # contador por simbolo: sin esto no se puede distinguir "el socket esta mudo" de
    # "ese simbolo no imprime en esta fuente" (SPY MUDO 25 min el 2026-08-03 en premarket).
    por_sym = {s: {"n": 0, "ultimo": 0, "px": None, "vol": 0.0} for s in syms}
    publicado = 0.0
    async with websockets.connect(URL.format(key=key), open_timeout=15, close_timeout=5,
                                  ping_interval=20, ping_timeout=20) as ws:
        for s in syms:
            await ws.send(json.dumps({"type": "subscribe", "symbol": s}))
        estado(conectado=True, desde=int(abierta), simbolos=syms, fuente=FUENTE,
               nbbo=None, nbbo_motivo="Finnhub gratis no trae libro: no se escribe nbbo_*")
        print(f"[finnhub-ws] conectado, {len(syms)} simbolos suscritos", flush=True)
        while hasta is None or time.time() < hasta:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                raw = None
            if raw is not None:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    msg = {}
                if msg.get("type") == "trade":
                    for d in msg.get("data") or []:
                        sym, px, ts = d.get("s"), d.get("p"), d.get("t")
                        if not sym or not px or not ts:
                            continue
                        # `t` es el reloj de BOLSA en ms. Marcar con la hora de llegada
                        # disfrazaria de vivo un tick retrasado y colaria el gate de frescura.
                        if rt_last.write_if_newer(sym, float(ts) / 1000.0, float(px),
                                                  float(d.get("v") or 0), FUENTE):
                            n += 1
                            ultimo = time.time()
                            g = por_sym.setdefault(sym, {"n": 0, "ultimo": 0, "px": None, "vol": 0.0})
                            g["n"] += 1
                            g["ultimo"] = int(float(ts) / 1000.0)
                            g["px"] = float(px)
                            g["vol"] += float(d.get("v") or 0)
            mudo = time.time() - (ultimo or abierta)
            # Socket vivo pero mudo en RTH = los rt_last_* envejecen con pinta de vivos.
            if mudo > MUDO_S and rth():
                # A connected-but-silent socket is not healthy. The old loop only spoke
                # every ten minutes and remained wedged for hours; reconnect so Finnhub
                # resubscribes and resumes exchange prints automatically.
                raise RuntimeError(
                    f"socket conectado pero mudo {mudo / 60:.1f} min en RTH; reconectando")
            if time.time() - publicado >= STATUS_CADA_S:
                publicado = time.time()
                _publica(n, ultimo, por_sym, mudo, abierta)
    return n, time.time() - abierta


async def main():
    lock = tomar_lock()          # noqa: F841 — vive lo que vive el proceso
    key = load_key()
    syms = simbolos(sys.argv)
    hasta = None
    if "--seconds" in sys.argv:
        hasta = time.time() + float(sys.argv[sys.argv.index("--seconds") + 1])
    print(f"[finnhub-ws] {len(syms)} simbolos: {' '.join(syms)}", flush=True)
    # arranque limpio: `estado()` fusiona con lo anterior y el error/caidas del proceso muerto
    # se quedaba pegado haciendo pasar por roto un puente sano.
    estado(pid=os.getpid(), arranque=int(time.time()), caidas=0, error=None, conectado=False)
    espera = 2.0
    caidas = 0
    while True:
        vivo = 0.0
        try:
            n, vivo = await sesion(key, syms, hasta)
            print(f"[finnhub-ws] sesion cerrada con {n} trades ({vivo:.0f}s)", flush=True)
        except Exception as e:
            caidas += 1
            vivo = 0.0
            estado(conectado=False, error=f"{type(e).__name__}: {e}", ts=int(time.time()),
                   caidas=caidas)
            print(f"[finnhub-ws] caida {caidas}: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            # `caidas == 5` gritaba UNA sola vez en toda la vida del proceso: pasadas las 5, un
            # socket en bucle de reconexion se quedaba callado para siempre. Ahora cada 5.
            if caidas % 5 == 0:
                grita(f"Puente Finnhub caido {caidas} veces seguidas. Sin print en tiempo real.")
        if vivo >= SESION_SANA_S:     # aguanto: la caida anterior fue transitoria
            espera, caidas = 2.0, 0
        if hasta is not None and time.time() >= hasta:
            estado(conectado=False, ts=int(time.time()), motivo_fin="--seconds")
            return 0
        await asyncio.sleep(espera)
        espera = min(BACKOFF_MAX_S, espera * 2)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
