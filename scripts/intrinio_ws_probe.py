"""intrinio_ws_probe.py — sonda del WebSocket realtime de Intrinio.

Pregunta que responde (Yunior 2026-08-02: "verify if the error is due to the market not open yet"):
los 7 hosts de streaming del SDK oficial aceptan TCP+TLS y cierran a los ~5,2 s sin un solo byte.
Eso no se puede resolver discutiendo: hay que MEDIRLO cruzando la frontera fin-de-semana -> lunes.
Cada corrida escribe una fila etiquetada con la fase de mercado; si el socket revive exactamente al
abrir premarket, la causa es horaria; si revive un domingo, no lo es.

Controles en cada corrida para no confundir "Intrinio caido" con "aqui no hay internet":
  - REST api-v2.intrinio.com (misma cuenta, misma key, siempre arriba)
  - WebSocket de Polygon (vendor distinto: su socket SI responde con el mercado cerrado, medido)

Fail-loud: sin key -> levanta. Un host que falla se registra con su error exacto; jamas se inventa
un token ni se rellena un hueco con un valor plausible.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
JSONL = REPO / "data" / "intrinio_ws_probe.jsonl"
STATUS = REPO / "data" / "intrinio_ws_status.json"
UP_FLAG = REPO / "data" / "INTRINIO_WS_UP"
ET = ZoneInfo("America/New_York")

# Hosts exactos de intriniorealtime 6.3.0 (equities_client.auth_url / options_client).
HOSTS = {
    "realtime-mx": "REALTIME|IEX",
    "realtime-delayed-sip": "DELAYED_SIP",
    "realtime-nasdaq-basic": "NASDAQ_BASIC",
    "cboe-one": "CBOE_ONE",
    "equities-edge": "EQUITIES_EDGE",
    "realtime-options": "OPRA",
    "options-edge": "OPTIONS_EDGE",
}
CLIENT_INFO = "IntrinioPythonSDKv6.3.0"
TIMEOUT = 20


def load_key() -> str:
    key = os.environ.get("INTRINIO_API_KEY")
    if not key:
        for line in (REPO / "config" / "feeds.env").read_text().splitlines():
            line = line.strip()
            if line.startswith("INTRINIO_API_KEY="):
                key = line.partition("=")[2].strip()
                break
    if not key:
        raise RuntimeError("INTRINIO_API_KEY ausente en env y en config/feeds.env")
    return key


def market_phase(now: datetime) -> str:
    """Fase de la sesion US en hora de Nueva York. Es la etiqueta que da sentido a la serie."""
    if now.weekday() >= 5:
        return "weekend"
    hm = now.hour * 60 + now.minute
    if hm < 4 * 60:
        return "overnight"
    if hm < 9 * 60 + 30:
        return "premarket"
    if hm < 16 * 60:
        return "rth"
    if hm < 20 * 60:
        return "afterhours"
    return "overnight"


def probe_auth(host: str, key: str) -> tuple[dict, str | None]:
    """GET https://<host>/auth?api_key=... tal cual lo hace el SDK.
    Devuelve (hecho medido, token). El token se usa en el acto y NUNCA se escribe a disco."""
    import requests

    url = f"https://{host}.intrinio.com/auth?api_key={key}"
    t0 = time.monotonic()
    try:
        r = requests.get(url, headers={"Client-Information": CLIENT_INFO}, timeout=TIMEOUT)
        body = (r.text or "").strip()
        ok = r.status_code == 200 and len(body) > 20
        return (
            {
                "ok": ok,
                "http": r.status_code,
                "body_len": len(body),
                "body_head": body[:80] if r.status_code != 200 else "<token>",
                "secs": round(time.monotonic() - t0, 3),
            },
            body if ok else None,
        )
    except Exception as e:  # se registra el error EXACTO; no hay valor por defecto
        return (
            {
                "ok": False,
                "http": None,
                "err": f"{type(e).__name__}: {str(e)[:160]}",
                "secs": round(time.monotonic() - t0, 3),
            },
            None,
        )


def probe_socket(host: str, token: str) -> dict:
    """Con token en mano, abrir el WebSocket DE VERDAD. Un token no prueba nada por si solo:
    'websockets funcionando' = el socket abre y el servidor acepta el join."""
    import json as _json

    try:
        import websocket
    except ImportError:
        return {"err": "websocket-client no instalado"}

    url = f"wss://{host}.intrinio.com/socket/websocket?vsn=1.0.0&token={token}"
    t0 = time.monotonic()
    try:
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        opened = round(time.monotonic() - t0, 3)
        ws.send(_json.dumps({
            "topic": "iex:securities:SPY", "event": "phx_join", "payload": {}, "ref": 1,
        }))
        ws.settimeout(10)
        frames, first = 0, None
        try:
            while frames < 3:
                m = ws.recv()
                frames += 1
                if first is None:
                    first = str(m)[:120]
        except Exception:
            pass
        ws.close()
        return {"opened": True, "open_secs": opened, "frames": frames, "first": first}
    except Exception as e:
        return {"opened": False, "err": f"{type(e).__name__}: {str(e)[:160]}",
                "secs": round(time.monotonic() - t0, 3)}


def probe_tls(host: str) -> dict:
    """Caracteriza el cierre: ¿cuanto aguanta el socket OCIOSO tras el handshake, sin enviar nada?
    ~5 s constante = timeout del servidor (nunca llega a leer la peticion)."""
    t0 = time.monotonic()
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((f"{host}.intrinio.com", 443), timeout=TIMEOUT) as raw:
            with ctx.wrap_socket(raw, server_hostname=f"{host}.intrinio.com") as s:
                handshake = round(time.monotonic() - t0, 3)
                s.settimeout(TIMEOUT)
                try:
                    data = s.recv(4096)  # sin enviar nada: esperamos a que cierre el
                    closed = round(time.monotonic() - t0, 3)
                    return {"handshake": handshake, "idle_close": closed, "bytes": len(data)}
                except Exception as e:
                    return {
                        "handshake": handshake,
                        "idle_close": round(time.monotonic() - t0, 3),
                        "recv_err": f"{type(e).__name__}",
                    }
    except Exception as e:
        return {"err": f"{type(e).__name__}: {str(e)[:120]}"}


def probe_controls(key: str) -> dict:
    """Controles: si estos caen tambien, el problema es nuestro, no de Intrinio."""
    import requests

    out = {}
    t0 = time.monotonic()
    try:
        r = requests.get(
            "https://api-v2.intrinio.com/securities/SPY/prices/realtime",
            params={"source": "equities_edge", "api_key": key},
            timeout=TIMEOUT,
        )
        j = r.json() if r.status_code == 200 else {}
        out["intrinio_rest"] = {
            "http": r.status_code,
            "last_time": j.get("last_time"),
            "source": j.get("source"),
            "has_bid": j.get("bid_price") is not None,
            "secs": round(time.monotonic() - t0, 3),
        }
    except Exception as e:
        out["intrinio_rest"] = {"err": f"{type(e).__name__}: {str(e)[:120]}"}

    t0 = time.monotonic()
    try:
        import websocket

        ws = websocket.create_connection("wss://socket.polygon.io/stocks", timeout=15)
        hello = ws.recv()
        ws.close()
        out["polygon_ws"] = {"connects": True, "hello": hello[:90], "secs": round(time.monotonic() - t0, 3)}
    except Exception as e:
        out["polygon_ws"] = {"connects": False, "err": f"{type(e).__name__}: {str(e)[:120]}"}
    return out


def run_once(key: str) -> dict:
    now = datetime.now(ET)
    auth, sockets = {}, {}
    for h in HOSTS:
        auth[h], token = probe_auth(h, key)
        if token:  # solo se intenta el socket si hay token: encadenar prueba lo que importa
            sockets[h] = probe_socket(h, token)
    return {
        "epoch": int(time.time()),
        "et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "phase": market_phase(now),
        "auth": auth,
        "socket": sockets,
        "tls_idle": probe_tls("equities-edge"),
        "controls": probe_controls(key),
        "any_up": sorted(h for h, r in auth.items() if r.get("ok")),
        "socket_ok": sorted(h for h, r in sockets.items() if r.get("opened")),
    }


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def record(row: dict) -> None:
    # El estado ANTERIOR se lee antes de reemplazarlo. En la versión vieja se hacía push en
    # CADA sonda con auth OK aunque el socket siguiera caído: dos mensajes obsoletos cada
    # ~10 min y una bandera UP falsa. Sólo una transición real del SOCKET merece alerta.
    previous = None
    if STATUS.exists():
        try:
            previous = json.loads(STATUS.read_text())
        except (OSError, ValueError):
            previous = None
    was_socket_up = bool((previous or {}).get("socket_ok"))
    socket_up = bool(row.get("socket_ok"))
    JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(JSONL, "a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    write_atomic(STATUS, json.dumps(row, indent=1))

    if socket_up:
        socks = row.get("socket_ok") or []
        write_atomic(UP_FLAG, f"{row['et']} socket={' '.join(socks)}\n")
    elif UP_FLAG.exists():
        UP_FLAG.unlink()

    # push SOLO en fases donde el servicio se espera vivo: overnight/weekend el vendor lo
    # apaga (~70% medido, memoria intrinio-websocket-off-overnight).
    # NOTIFICACIONES MUERTAS (orden Yunior 2026-08-06 "shut up intrinio alert websocket"):
    # ni push ni voz, en ninguna fase. La serie completa sigue en el jsonl y en el status.
    if previous is not None and socket_up != was_socket_up:
        print(f"[intrinio-ws] transicion a {'ARRIBA' if socket_up else 'CAIDO'} "
              f"en {row['phase']} (notificaciones muertas por orden)", file=sys.stderr)


def resumen() -> int:
    """Lee la serie y responde la pregunta: ¿en que fase de sesion revive el socket?
    No opina: cuenta filas por fase y localiza la PRIMERA transicion abajo->arriba."""
    if not JSONL.exists():
        print("  sin mediciones todavia")
        return 1
    filas = [json.loads(l) for l in JSONL.read_text().splitlines() if l.strip()]
    por_fase: dict[str, list[int]] = {}
    for f in filas:
        arriba = bool(f.get("socket_ok"))
        por_fase.setdefault(f["phase"], [0, 0])
        por_fase[f["phase"]][0 if arriba else 1] += 1

    print(f"  {len(filas)} mediciones | {filas[0]['et']} -> {filas[-1]['et']} ET")
    print(f"  {'fase':<12} {'socket ARRIBA':>14} {'socket abajo':>13}")
    for fase in ("weekend", "overnight", "premarket", "rth", "afterhours"):
        if fase in por_fase:
            arr, aba = por_fase[fase]
            print(f"  {fase:<12} {arr:>14} {aba:>13}")

    prev = False
    for f in filas:
        ahora = bool(f.get("socket_ok"))
        if ahora and not prev:
            print(f"\n  PRIMERA SUBIDA: {f['et']} ET, fase={f['phase']}, hosts={','.join(f['socket_ok'])}")
            return 0
        prev = ahora
    print("\n  el socket NO ha estado arriba en ninguna medicion todavia")
    return 1


def main() -> int:
    if "--summary" in sys.argv:
        return resumen()
    # timeout duro < StartInterval 600s: un probe colgado (156 y 307 min medidos) bloquea
    # a launchd hasta que muera; SIGALRM lo mata y el siguiente ciclo corre limpio
    import signal
    signal.alarm(540)
    key = load_key()
    row = run_once(key)
    record(row)
    up = ",".join(row["any_up"]) if row["any_up"] else "NINGUNO"
    ctl = row["controls"]
    sk = ",".join(row.get("socket_ok") or []) or "NINGUNO"
    print(
        f"{row['et']} ET [{row['phase']}] auth_up={up} socket_ok={sk} | "
        f"rest={ctl.get('intrinio_rest', {}).get('http')} "
        f"polygon_ws={ctl.get('polygon_ws', {}).get('connects')} | "
        f"tls_idle_close={row['tls_idle'].get('idle_close')}s"
    )
    return 0 if row["any_up"] else 1


if __name__ == "__main__":
    sys.exit(main())
