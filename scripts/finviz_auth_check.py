#!/usr/bin/env python3
"""finviz_auth_check.py — el token de Finviz Elite CADUCA Y NADIE SE ENTERA.

POR QUE EXISTE (Yunior 2026-07-25: "new finviz api till next saturday")
----------------------------------------------------------------------
Yunior renueva el token cada semana. Cuando caduca, el export devuelve 200 con un
CSV vacio o una pagina de login — NO un 401 — asi que los consumidores se quedan
mudos sin error visible:
  scripts/finviz_scout.cpp     (scout premarket + alertas por email)
  scripts/finviz_valuation.py  (snapshot diario de valuacion, solo lee AUTH3)
  scripts/x_whale_bot.cpp      (posts de X)
  scripts/options_hunter.py
  scripts/picaro.sh
Este chequeo convierte ese fallo silencioso en una VOZ.

ORDEN DE TOKENS — importa, y es contraintuitivo
-----------------------------------------------
Todos los consumidores prueban FINVIZ_AUTH3 ANTES que FINVIZ_AUTH
(finviz_scout.cpp:91, x_whale_bot.cpp:366, options_hunter.py:34; finviz_valuation.py
solo lee AUTH3). Medido el 2026-07-25: cambiar unicamente FINVIZ_AUTH en llm.env
NO surte efecto en nadie. Por eso aqui se comprueba el token EFECTIVO — el que de
verdad va a usar la flota — y no "alguno que funcione".

QUE ES UN TOKEN SANO
--------------------
No basta con HTTP 200. Se exige cabecera CSV con "Ticker" y al menos MIN_ROWS filas
para tres simbolos pedidos explicitamente. Un 200 con 0 filas es exactamente el modo
de fallo que queremos cazar.

FAIL-LOUD, y jamas un cero plausible: si no se puede comprobar (sin red, timeout),
se dice "NO SE PUDO COMPROBAR" y se sale 2 — que es distinto de "caducado" (1).
El token NUNCA se imprime: solo sus 4 ultimos caracteres.

SEÑAL-SOLAMENTE: solo lee y avisa. Cero ordenes.

  uso:
    ./venv/bin/python scripts/finviz_auth_check.py            # comprueba y avisa
    ./venv/bin/python scripts/finviz_auth_check.py --quiet    # sin voz (para tests)
    ./venv/bin/python scripts/finviz_auth_check.py --json
  salida: 0 sano | 1 caducado/roto | 2 no se pudo comprobar
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "finviz_auth_health.json")
PROBE_SYMS = "QQQ,SPY,NVDA"
MIN_ROWS = 3
TIMEOUT_S = 25
WARN_DAYS = 2          # avisa 2 dias antes de la fecha declarada de caducidad

# El orden REAL que usan los consumidores. No tocar sin mirar los ficheros citados arriba.
TOKEN_KEYS = ("FINVIZ_AUTH3", "FINVIZ_AUTH")
ENV_FILES = ("feeds.env", "llm.env")


def _env_files():
    """Todas las claves de feeds.env + llm.env. El proceso manda sobre el fichero."""
    vals = {}
    for fn in ENV_FILES:
        path = os.path.join(REPO, fn)
        try:
            with open(path) as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln or ln.startswith("#") or "=" not in ln:
                        continue
                    k, v = ln.split("=", 1)
                    vals.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except OSError:
            continue
    return vals


def effective_token(env=None, files=None):
    """El token que de verdad usara la flota, con el nombre de la clave y de donde sale.

    Devuelve (token, key, origen) o (None, None, None). Pura: se le pueden inyectar
    los dos diccionarios para testearla sin disco.
    """
    env = os.environ if env is None else env
    files = _env_files() if files is None else files
    for k in TOKEN_KEYS:
        v = (env.get(k) or "").strip()
        if v:
            return v, k, "entorno"
        v = (files.get(k) or "").strip()
        if v:
            return v, k, "fichero"
    return None, None, None


def declared_expiry(files=None):
    """FINVIZ_AUTH_EXPIRES si Yunior la dejo escrita. None si no hay — no se inventa."""
    files = _env_files() if files is None else files
    raw = (files.get("FINVIZ_AUTH_EXPIRES") or "").strip()
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def judge(status, body, min_rows=MIN_ROWS):
    """Regla PURA: (status, cuerpo) -> (sano: bool, motivo: str).

    Un 200 con CSV vacio o sin cabecera es el fallo que buscamos: NO cuenta como sano.
    """
    if status is None:
        return False, "sin respuesta"
    if status != 200:
        return False, f"HTTP {status}"
    if not body:
        return False, "HTTP 200 con cuerpo VACIO (token caducado: Finviz no devuelve 401)"
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return False, "HTTP 200 sin lineas"
    if "Ticker" not in lines[0]:
        return False, "HTTP 200 sin cabecera CSV (probable pagina de login)"
    rows = len(lines) - 1
    if rows < min_rows:
        return False, f"HTTP 200 con {rows} filas (<{min_rows}): feed vacio"
    return True, f"{rows} filas"


def probe(token):
    """(status, cuerpo). status None = no se pudo comprobar (red), != no autorizado."""
    url = ("https://elite.finviz.com/export/screener"
           f"?v=111&t={PROBE_SYMS}&auth={token}")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def say(prio, msg):
    """Voz por la cola serializada (scripts/speak.sh). Nunca revienta al llamador."""
    try:
        subprocess.Popen(["/bin/bash", os.path.join(REPO, "scripts", "speak.sh"), prio, msg],
                         cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def write_health(rec):
    """Atomica: tmp + replace. Un lector jamas ve el fichero a medias."""
    tmp = OUT + ".tmp"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1, sort_keys=True)
    os.replace(tmp, OUT)


def main():
    ap = argparse.ArgumentParser(description="chequeo del token de Finviz Elite (senal-solamente)")
    ap.add_argument("--quiet", action="store_true", help="no hablar (tests)")
    ap.add_argument("--json", action="store_true", help="volcar el registro por stdout")
    a = ap.parse_args()

    token, key, origen = effective_token()
    today = dt.date.today()
    exp = declared_expiry()
    days_left = (exp - today).days if exp else None

    rec = {
        "ts": int(dt.datetime.now().timestamp()),
        "fecha": today.isoformat(),
        "clave_efectiva": key,
        "origen": origen,
        "token_cola": token[-4:] if token else None,
        "caduca_declarado": exp.isoformat() if exp else None,
        "dias_restantes": days_left,
        "orden_de_busqueda": list(TOKEN_KEYS),
    }

    if not token:
        rec.update(sano=False, motivo="sin token en entorno ni en feeds.env/llm.env",
                   veredicto="ROTO")
        write_health(rec)
        if not a.quiet:
            say("DANGER", "Finviz sin token. El scout y el bot de X estan ciegos.")
        print("FINVIZ ROTO: sin token (FINVIZ_AUTH3/FINVIZ_AUTH)", file=sys.stderr)
        if a.json:
            print(json.dumps(rec, indent=1, sort_keys=True))
        return 1

    status, body = probe(token)
    if status is None:
        rec.update(sano=None, motivo="sin red o timeout", veredicto="NO SE PUDO COMPROBAR")
        write_health(rec)
        print(f"finviz_auth_check: NO SE PUDO COMPROBAR ({key}, ...{token[-4:]}) — sin red",
              file=sys.stderr)
        if a.json:
            print(json.dumps(rec, indent=1, sort_keys=True))
        return 2

    sano, motivo = judge(status, body)
    rec.update(sano=sano, motivo=motivo, http=status,
               veredicto="SANO" if sano else "CADUCADO")

    if sano and days_left is not None and days_left <= WARN_DAYS:
        rec["veredicto"] = "SANO_POR_POCO"
        rec["aviso"] = f"caduca en {days_left} dia(s) segun FINVIZ_AUTH_EXPIRES"

    write_health(rec)

    if not sano:
        if not a.quiet:
            say("DANGER", "Token de Finviz caducado. Yunior tiene que renovarlo.")
        print(f"FINVIZ CADUCADO ({key} desde {origen}, ...{token[-4:]}): {motivo}", file=sys.stderr)
    elif rec["veredicto"] == "SANO_POR_POCO":
        if not a.quiet:
            say("SIGNAL", f"Token de Finviz caduca en {days_left} dias.")
        print(f"finviz_auth_check: SANO pero caduca en {days_left} dia(s) — {motivo}")
    else:
        extra = f", caduca en {days_left} dias" if days_left is not None else ""
        print(f"finviz_auth_check: SANO ({key} desde {origen}, ...{token[-4:]}) — {motivo}{extra}")

    if a.json:
        print(json.dumps(rec, indent=1, sort_keys=True))
    return 0 if sano else 1


if __name__ == "__main__":
    sys.exit(main())
