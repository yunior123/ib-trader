#!/usr/bin/env python3
"""uw_archive.py — SALVAR el historico de Unusual Whales ANTES de que caduque el trial.

POR QUE EXISTE, Y POR QUE CORRE YA
----------------------------------
Yunior consiguio un trial de 7 dias (token en feeds.env UW_TOKEN, emitido 2026-07-25,
caduca ~2026-08-01) y dijo: "esta semana podemos conectar unusual whales, si es bueno
extendemos trial".

La decision correcta NO es cablearlo a la flota. Es ARCHIVAR su historico mientras
dura, porque:
  (1) Lo historico es IRRECUPERABLE. `/greek-exposure` da 250 dias (UN ANO) de gamma,
      delta, charm y vanna de dealer por dia. Si el trial se apaga sin haberlo bajado,
      ese ano no vuelve ni pagando despues — y es justo lo que desbloquea condicionar
      señales sobre el regimen gamma historico, hoy parado esperando 40 sesiones.
  (2) Una fuente de PAGO con reloj NO puede ser dependencia de una señal. Es la
      leccion de gexa.ai: murio de un dia para otro y se llevo 8 consumidores.
      Primero se archiva, luego se MIDE contra lo nuestro, y solo lo que sobreviva
      a barrera+null+BH-FDR llega a tener voz.

QUE ARCHIVA (medido el 2026-07-26, los 6 endpoints responden 200)
-----------------------------------------------------------------
  greek_exposure         250 filas/sym  UN ANO de call/put gamma-delta-charm-vanna diario
  greek_exposure_strike  530 filas/sym  el MAPA DE DELTA por strike (no lo tenemos: gex_core
                                        no calcula delta, ver designs-menthorq #9 / spotgamma #12)
  net_prem_ticks         406 filas/sym  net_call_premium, net_delta y volumen por LADO
                                        (ask/bid) en cubos intradia = el HIRO que
                                        docs/HIRO-2026-07-25.md daba por bloqueado
  spot_exposures_strike   50 filas/sym  gamma/vanna/charm por strike desglosado
                                        oi / vol / ask / bid
  max_pain                33 filas/sym  max pain por vencimiento
  vol_term_structure      33 filas/sym  implied move por vencimiento
  oi_change               50 filas/sym  cambio de OI por contrato
  flow_alerts             50 filas/sym  sweeps y alertas de flujo
  market_tide (global)    81 filas      la marea FIRMADA del mercado en cubos de 5 min

HONESTIDAD DEL DATO
-------------------
Cada fichero lleva su `_meta` con: endpoint exacto, epoch de descarga, y
`fuente: "unusual_whales_trial"`. La procedencia va DENTRO del dato para que nadie
mezcle sus griegas con las de Polygon sin saberlo (~/CLAUDE.md: "jamas mezclar
reconstruido con medido sin decirlo en la cabecera").

Escritura ATOMICA (tmp + rename) e IDEMPOTENTE por (fecha, endpoint, sym): re-correrlo
el mismo dia no re-descarga lo ya salvado salvo --force.

FAIL-LOUD: si el token caduca, UW devuelve 401/403 y el script SALE CON CODIGO 1
nombrando el endpoint. Jamas escribe un fichero vacio ni un [] que luego parezca
"ese dia no hubo datos".

SEÑAL-SOLAMENTE: solo lee y guarda. Cero ordenes, cero voz, cero consumidores.

  uso:
    ./venv/bin/python scripts/uw_archive.py                 # flota completa
    ./venv/bin/python scripts/uw_archive.py --syms QQQ SPY  # subconjunto
    ./venv/bin/python scripts/uw_archive.py --dry-run       # que haria, sin red
    ./venv/bin/python scripts/uw_archive.py --force         # re-descarga lo de hoy
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://api.unusualwhales.com"
TIMEOUT_S = 45
# MEDIDO el 2026-07-26: con 0,35 s entre peticiones UW devuelve 403 al cabo de unas
# pocas. NO es el token: los mismos endpoints responden 200 con 2 s de pausa. UW usa
# 403 tanto para "no autorizado" como para "vas demasiado rapido", asi que la primera
# version de este script aborto gritando "TOKEN MUERTO" con el token perfectamente
# vivo. Un fallo transitorio jamas debe presentarse como permanente.
PAUSE_S = 0.6
RETRIES = 4
BACKOFF_403_S = (5, 15, 40)   # si el 403 sobrevive a esto, entonces si es el token

# endpoint -> plantilla. {sym} se sustituye; los que no lo llevan son globales.
ENDPOINTS = {
    "greek_exposure":        "/api/stock/{sym}/greek-exposure",
    "greek_exposure_strike": "/api/stock/{sym}/greek-exposure/strike",
    "net_prem_ticks":        "/api/stock/{sym}/net-prem-ticks",
    "spot_exposures_strike": "/api/stock/{sym}/spot-exposures/strike",
    "max_pain":              "/api/stock/{sym}/max-pain",
    "vol_term_structure":    "/api/stock/{sym}/volatility/term-structure",
    "oi_change":             "/api/stock/{sym}/oi-change",
    "flow_alerts":           "/api/stock/{sym}/flow-alerts",
}
GLOBAL_ENDPOINTS = {
    "market_tide":  "/api/market/market-tide",
    "market_oi_change": "/api/market/oi-change",
    "sector_etfs":  "/api/market/sector-etfs",
}


def token():
    """UW_TOKEN: entorno primero, luego feeds.env. Nunca se imprime entero."""
    t = (os.environ.get("UW_TOKEN") or "").strip()
    if t:
        return t
    try:
        with open(os.path.join(REPO, "feeds.env")) as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith("UW_TOKEN="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def fleet():
    """La flota canonica. LEVANTA si no se puede leer: archivar media flota en
    silencio es peor que no archivar (nadie se enteraria del hueco)."""
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        syms = f.read().split()
    if not syms:
        raise RuntimeError("data/fleet.txt VACIA")
    return [s.upper() for s in syms]


def fetch(path, tok):
    """(payload, error). payload None + error != None si no se pudo. Nunca [] fingido."""
    # El User-Agent NO es cosmetico: MEDIDO el 2026-07-26, UW devuelve 403 al
    # `Python-urllib/3.9` por defecto y 200 al mismo endpoint, con el mismo token y
    # en el mismo segundo, en cuanto se declara uno. Perseguir esto como si fuera un
    # token caducado costo dos diagnosticos equivocados: el 403 de UW significa
    # "no me gustas", no necesariamente "no tienes permiso".
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json",
                 "User-Agent": "ib-trader/1.0 (archivador senal-solamente)"})
    last = None
    n_403 = 0
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return json.loads(r.read().decode("utf-8", "replace")), None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return None, "HTTP 401 NO AUTORIZADO (token caducado)"
            if e.code in (403, 429):
                # UW usa 403 TAMBIEN para limitar el ritmo. Se espera de verdad antes
                # de acusar al token: solo si sobrevive a los tres backoffs se declara
                # muerto. Distinguir transitorio de permanente es el trabajo.
                if n_403 < len(BACKOFF_403_S):
                    time.sleep(BACKOFF_403_S[n_403])
                    n_403 += 1
                    continue
                return None, f"HTTP {e.code} NO AUTORIZADO tras {n_403} esperas (token caducado)"
            last = f"HTTP {e.code}"
        except Exception as e:
            last = f"{e.__class__.__name__}: {str(e)[:60]}"
        if attempt < RETRIES - 1:
            time.sleep(1.5 * (attempt + 1))
    return None, last


def rows_of(payload):
    """Cuenta filas sin suponer la forma. -1 = forma desconocida (se dice, no se finge)."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        d = payload.get("data")
        if isinstance(d, list):
            return len(d)
        return -1
    return -1


def write_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def archive_one(name, path, tok, outdir, sym=None, force=False, dry=False):
    """(estado, n_filas, motivo). estado: ok | saltado | FALLO."""
    fn = f"uw_{name}_{sym.lower()}.json" if sym else f"uw_{name}.json"
    dest = os.path.join(outdir, fn)
    if os.path.exists(dest) and not force:
        return "saltado", None, "ya archivado hoy"
    if dry:
        return "ok", None, f"(dry) {path}"
    payload, err = fetch(path, tok)
    if payload is None:
        return "FALLO", None, err
    n = rows_of(payload)
    if n == 0:
        # 0 filas puede ser legitimo (fin de semana, sin alertas). Se archiva DICIENDOLO,
        # nunca se descarta: un hueco silencioso luego parece "no habia dato".
        pass
    write_atomic(dest, {
        "_meta": {
            "fuente": "unusual_whales_trial",
            "endpoint": path,
            "sym": sym,
            "descargado_epoch": time.time(),
            "descargado_local": dt.datetime.now().isoformat(timespec="seconds"),
            "n_filas": n,
            "aviso": ("trial con reloj: token emitido 2026-07-25, caduca ~2026-08-01. "
                      "Griegas de UW, NO mezclar con las de Polygon sin declararlo."),
        },
        "payload": payload,
    })
    return "ok", n, ""


def main():
    ap = argparse.ArgumentParser(description="archiva el historico de Unusual Whales (senal-solamente)")
    ap.add_argument("--syms", nargs="*", help="simbolos (default: data/fleet.txt)")
    ap.add_argument("--force", action="store_true", help="re-descarga lo ya archivado hoy")
    ap.add_argument("--dry-run", action="store_true", help="no toca la red")
    ap.add_argument("--only", nargs="*", help="solo estos endpoints por nombre")
    a = ap.parse_args()

    tok = token()
    if not tok:
        print("uw_archive ROTO: sin UW_TOKEN (entorno ni feeds.env)", file=sys.stderr)
        return 1

    syms = [s.upper() for s in a.syms] if a.syms else fleet()
    hoy = dt.date.today().isoformat()
    outdir = os.path.join(REPO, "data", "history", hoy)
    eps = {k: v for k, v in ENDPOINTS.items() if not a.only or k in a.only}
    geps = {k: v for k, v in GLOBAL_ENDPOINTS.items() if not a.only or k in a.only}

    print(f"uw_archive {hoy} | {len(syms)} simbolos x {len(eps)} endpoints "
          f"+ {len(geps)} globales -> data/history/{hoy}/")
    ok = skip = 0
    fallos = []
    total_rows = 0

    for name, tpl in geps.items():
        st, n, why = archive_one(name, tpl, tok, outdir, force=a.force, dry=a.dry_run)
        if st == "ok":
            ok += 1
            total_rows += max(n or 0, 0)
            print(f"  {name:24s} {'' if n is None else str(n)+' filas'}")
        elif st == "saltado":
            skip += 1
        else:
            fallos.append((name, None, why))
            print(f"  {name:24s} FALLO {why}", file=sys.stderr)
            if "NO AUTORIZADO" in (why or ""):
                print("TOKEN MUERTO: abortando para no llenar el disco de errores", file=sys.stderr)
                return 1
        time.sleep(PAUSE_S)

    for i, sym in enumerate(syms, 1):
        got = []
        for name, tpl in eps.items():
            st, n, why = archive_one(name, tpl.format(sym=sym), tok, outdir,
                                     sym=sym, force=a.force, dry=a.dry_run)
            if st == "ok":
                ok += 1
                total_rows += max(n or 0, 0)
                got.append(f"{name.split('_')[0]}:{n}")
            elif st == "saltado":
                skip += 1
            else:
                fallos.append((name, sym, why))
                if "NO AUTORIZADO" in (why or ""):
                    print(f"TOKEN MUERTO en {sym}/{name}: abortando", file=sys.stderr)
                    return 1
            time.sleep(PAUSE_S)
        print(f"  [{i:2d}/{len(syms)}] {sym:6s} {' '.join(got) if got else '(todo saltado)'}")

    print(f"-> {ok} ficheros nuevos, {skip} ya estaban, {total_rows:,} filas totales")
    if fallos:
        print(f"-> {len(fallos)} FALLOS:", file=sys.stderr)
        for name, sym, why in fallos[:12]:
            print(f"   {sym or '-':6s} {name:24s} {why}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
