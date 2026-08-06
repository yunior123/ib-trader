#!/usr/bin/env python3
"""intrinio_ws_autostart.py — enciende el WebSocket de Intrinio EN EL MISMO INSTANTE
en que el proveedor levanta su cluster, sin que nadie mire.

El problema medido (2026-08-02, todo el domingo, 98 mediciones): los 7 hosts de streaming
(`realtime-mx`, `realtime-delayed-sip`, `realtime-nasdaq-basic`, `cboe-one`, `equities-edge`,
`realtime-options`, `realtime-opra`) completan el TLS con cert `*.intrinio.com` valido pero
NO acuerdan ALPN y cierran a los ~5,13 s sin una sola cabecera HTTP: balanceador vivo, app
Phoenix detras APAGADA. No es nuestra key (el REST responde 200 con la misma), no es la IP
(20 nodos de check-host.net en 4 continentes fallan igual) y no es el host (los de HEAD del
SDK oficial son EXACTAMENTE estos). Es que el vendor los apaga: su propio SDK de C# lo dice
—"when the markets are closed and the websocket servers are off for the night"— y el issue
abierto intrinio-realtime-options-python-sdk#7 (feb-2024) describe que ADEMAS el SDK oficial
no se recupera solo cuando vuelven.

Este demonio resuelve las dos mitades:
  1. sondea `/auth` cada WATCH_S; en cuanto devuelve token, CONECTA de verdad (no se fia del
     auth: abre el socket y espera datos) y GRITA por voz que ya hay tiempo real;
  2. si el socket se cae, vuelve al sondeo — no se queda muerto como el SDK del issue #7.

Escribe en su PROPIO espacio de nombres para no pelearse con `provider_bridge`:
  data/ws_nbbo_<SYM>.txt   "EPOCH BID ASK"     (solo si llega quote con las dos patas)
  data/ws_trade_<SYM>.txt  "EPOCH PRICE SIZE"
  data/intrinio_ws_up.json estado + la PRIMERA transicion abajo->arriba (el horario que
                           el vendor no documenta, medido por nosotros)

Uso: intrinio_ws_autostart.py [--watch 30] [--once]
"""
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

AUTH_HOST = {
    "REALTIME": "realtime-mx", "IEX": "realtime-mx",
    "DELAYED_SIP": "realtime-delayed-sip", "NASDAQ_BASIC": "realtime-nasdaq-basic",
    "CBOE_ONE": "cboe-one", "EQUITIES_EDGE": "equities-edge",
}
PROVIDER = os.environ.get("MIT_INTRINIO_RT_PROVIDER", "EQUITIES_EDGE")
# Only exchange-realtime Intrinio products may write the canonical live print.
# EQUITIES_EDGE is the account's measured 15-minute route: its socket messages arrive
# immediately but carry delayed prices, so freshness-by-arrival cannot make them realtime.
CANONICAL_RT_PROVIDERS = frozenset({"REALTIME", "IEX", "NASDAQ_BASIC", "CBOE_ONE"})
# 60 s y no 20: la doc de Intrinio avisa de que reconectar en cuanto algo falla "agota tu cupo de
# conexiones y degenera en una espiral irresoluble de fallos" (Concurrent Connections, default 2).
# Sondear /auth es HTTP y no gasta conexiones de socket, pero no hay ninguna prisa: el cluster
# vuelve por la mañana y un sondeo por minuto lo detecta con 60 s de retraso como mucho.
WATCH_S = float(os.environ.get("INTRINIO_WS_WATCH_S", "60"))
UP_FILE = os.path.join(ROOT, "data", "intrinio_ws_up.json")
SYMS_FILE = os.path.join(ROOT, "data", "provider_syms.txt")
MAX_SUBS = int(os.environ.get("INTRINIO_WS_MAX_SUBS", "30"))


def provider_is_canonical_realtime(provider):
    return str(provider or "").upper() in CANONICAL_RT_PROVIDERS


def load_key():
    k = (os.environ.get("INTRINIO_API_KEY") or "").strip()
    if k:
        return k
    with open(os.path.join(ROOT, "config", "feeds.env")) as f:
        for ln in f:
            if ln.startswith("INTRINIO_API_KEY="):
                return ln.split("=", 1)[1].strip()
    raise SystemExit("intrinio_ws_autostart ROTO: sin INTRINIO_API_KEY")


def simbolos():
    for p in (SYMS_FILE, os.path.join(ROOT, "data", "fleet.txt")):
        if os.path.exists(p):
            syms = open(p).read().split()
            if syms:
                return syms[:MAX_SUBS]
    raise SystemExit("intrinio_ws_autostart ROTO: sin universo (provider_syms.txt ni fleet.txt)")


def auth_token(key, timeout=10):
    """Token si el cluster esta arriba, o None. Acotado a proposito: el `requests.get` del SDK
    (equities_client.py:262) NO lleva timeout y su connect() reintenta en bucle infinito, asi
    que arrancarlo con el socket apagado deja un hilo girando para siempre."""
    import requests
    host = AUTH_HOST.get(PROVIDER, "equities-edge")
    try:
        r = requests.get(f"https://{host}.intrinio.com/auth",
                         params={"api_key": key},
                         headers={"Client-Information": "IntrinioPythonSDKv6.3.0"},
                         timeout=timeout)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    tok = (r.text or "").strip()
    return (tok, None) if len(tok) > 20 else (None, "token vacio")


def grita(msg, nivel="INFO"):
    print(msg, flush=True)
    # overnight/weekend Intrinio esta APAGADO por el vendor (~70% medido): la voz ahi es
    # crying-wolf a las 3am (Yunior 2026-08-06). Se imprime siempre; se habla solo en sesion.
    try:
        from intrinio_ws_probe import market_phase
        from datetime import datetime
        if market_phase(datetime.now().astimezone()) in ("overnight", "weekend"):
            return
    except Exception:
        pass                                      # sin fase no se calla: mejor ruido que mudo
    try:
        subprocess.Popen(["/bin/bash", os.path.join(ROOT, "scripts", "speak.sh"), nivel, msg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _escribe(path, linea):
    # The SDK invokes trade and quote callbacks on worker threads. Each writer needs
    # an independent temp path before the atomic rename.
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w") as f:
            f.write(linea)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _exchange_epoch(raw):
    """El SDK entrega el timestamp de BOLSA en nanosegundos. Marcar con la hora de LLEGADA
    disfrazaria de vivo un feed retrasado y colaria el gate de frescura."""
    try:
        secs = float(raw) / 1e9
    except (TypeError, ValueError):
        return None
    now = time.time()
    return secs if (now - 7 * 86400) < secs < (now + 3600) else None


def estado(**kw):
    prev = {}
    if os.path.exists(UP_FILE):
        try:
            prev = json.load(open(UP_FILE))
        except (OSError, ValueError):
            prev = {}
    prev.update(kw)
    tmp = UP_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(prev, f, ensure_ascii=False, indent=1)
    os.replace(tmp, UP_FILE)


def stream(key, syms):
    """Abre el socket de verdad y bombea a disco. Devuelve cuando el socket muere."""
    from intriniorealtime.equities_client import IntrinioRealtimeEquitiesClient

    vistos = {"n": 0, "ultimo": 0.0}

    import rt_last

    # El SDK llama al callback con (registro, backlog): con un solo parametro lanza
    # TypeError por CADA tick y el socket queda vivo sin escribir nada (medido 2026-08-03 04:35).
    def on_trade(t, backlog=0):
        sym = getattr(t, "symbol", None)
        ep = _exchange_epoch(getattr(t, "timestamp", None))
        px = getattr(t, "price", None)
        if not sym or ep is None or not px:
            return
        tam = float(getattr(t, "size", 0) or 0)
        _escribe(f"data/ws_trade_{sym.upper()}.txt", f"{ep:.0f} {float(px):.4f} {tam:.0f}\n")
        # Delayed products stay available in ws_trade_* for provenance, but must never
        # overwrite Finnhub's exchange-realtime canonical print.
        if provider_is_canonical_realtime(PROVIDER):
            rt_last.write_if_newer(sym, ep, float(px), tam, "intrinio")
        vistos["n"] += 1
        vistos["ultimo"] = time.time()

    libro = {}

    def on_quote(q, backlog=0):
        sym = getattr(q, "symbol", None)
        ep = _exchange_epoch(getattr(q, "timestamp", None))
        px = getattr(q, "price", None)
        tipo = str(getattr(q, "type", "")).lower()
        if not sym or ep is None or not px:
            return
        lado = libro.setdefault(sym.upper(), {})
        lado["ask" if "ask" in tipo else "bid"] = float(px)
        if "bid" in lado and "ask" in lado and lado["ask"] > lado["bid"] > 0:
            _escribe(f"data/ws_nbbo_{sym.upper()}.txt",
                     f"{ep:.0f} {lado['bid']:.4f} {lado['ask']:.4f}\n")
            vistos["n"] += 1
            vistos["ultimo"] = time.time()

    cfg = {"api_key": key, "provider": PROVIDER}
    cli = IntrinioRealtimeEquitiesClient(cfg, on_trade, on_quote)
    # el SDK añade un handler por instancia -> tras N reconexiones cada ERROR salia x8
    # (medido 2026-08-06: mismos ms repetidos); un solo handler basta
    import logging as _logging
    _lg = _logging.getLogger("intrinio_realtime")
    if len(_lg.handlers) > 1:
        _lg.handlers = _lg.handlers[:1]
    hilo = threading.Thread(target=cli.connect, daemon=True)
    hilo.start()
    time.sleep(5)
    # join(channels) — UN solo argumento. Con `cli.join(syms, True)` (el `tradesonly` de otros
    # SDK) lanza TypeError, el socket queda ABIERTO y suscrito a NADA: el 2026-08-03 el cluster
    # levanto a las 03:47 ET y estuvimos 46 min con la conexion viva y 0 mensajes por esto.
    try:
        cli.join(syms)
    except Exception as e:
        print(f"[intrinio-ws] join fallo: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        estado(arriba=False, error=f"join: {type(e).__name__}: {e}")
        try:
            cli.disconnect()
        except Exception:
            pass
        return

    grita(f"WebSocket de Intrinio ARRIBA con {len(syms)} simbolos. Tiempo real encendido.")
    estado(arriba=True, desde=int(time.time()),
           desde_et=time.strftime("%Y-%m-%d %H:%M:%S"), provider=PROVIDER,
           canonical_print=provider_is_canonical_realtime(PROVIDER),
           simbolos=syms, primera_subida=json.load(open(UP_FILE)).get("primera_subida")
           if os.path.exists(UP_FILE) else None)
    if not (json.load(open(UP_FILE)).get("primera_subida")):
        estado(primera_subida=time.strftime("%Y-%m-%d %H:%M:%S %Z"))

    mudo_desde = time.time()
    while True:
        time.sleep(10)
        estado(mensajes=vistos["n"], ultimo_mensaje=int(vistos["ultimo"] or 0),
               ts=int(time.time()))
        if vistos["ultimo"]:
            mudo_desde = vistos["ultimo"]
        if time.time() - mudo_desde > 300:
            grita("WebSocket de Intrinio sin datos cinco minutos. Vuelvo a vigilar.", "DANGER")
            try:
                cli.disconnect()
            except Exception:
                pass
            estado(arriba=False, caida=int(time.time()))
            return


def main():
    once = "--once" in sys.argv
    if "--watch" in sys.argv:
        globals()["WATCH_S"] = float(sys.argv[sys.argv.index("--watch") + 1])
    key = load_key()
    syms = simbolos()
    print(f"[intrinio-ws] vigilando {AUTH_HOST.get(PROVIDER)}.intrinio.com cada {WATCH_S}s "
          f"para {len(syms)} simbolos", flush=True)
    intentos = 0
    while True:
        tok, err = auth_token(key)
        intentos += 1
        if tok:
            print(f"[intrinio-ws] AUTH OK tras {intentos} sondeos — abriendo socket", flush=True)
            estado(arriba=False, auth_ok=int(time.time()), intentos=intentos)
            try:
                stream(key, syms)
            except Exception as e:
                print(f"[intrinio-ws] socket murio: {type(e).__name__}: {e}",
                      file=sys.stderr, flush=True)
                estado(arriba=False, error=f"{type(e).__name__}: {e}")
            if once:
                return 0
            continue
        estado(arriba=False, ultimo_sondeo=int(time.time()),
               ultimo_sondeo_et=time.strftime("%Y-%m-%d %H:%M:%S"),
               motivo=err, intentos=intentos, provider=PROVIDER)
        if intentos % 20 == 1:
            print(f"[intrinio-ws] {time.strftime('%H:%M:%S')} sigue abajo ({err})", flush=True)
        if once:
            return 1
        time.sleep(WATCH_S)


if __name__ == "__main__":
    raise SystemExit(main())
