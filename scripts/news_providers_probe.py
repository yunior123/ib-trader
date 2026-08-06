#!/usr/bin/env python3
"""news_providers_probe.py — banco de pruebas de proveedores de NOTICIAS. Mide, no opina.

Yunior 2026-08-05: "do tests on providers to see the best ones". Barre los 30 de data/fleet.txt
por cada proveedor y compara con las mismas reglas para todos:

  cobertura   simbolos con >=1 titular en la ventana (los raros mandan: DRAM SPCX SKHY EWY NOK)
  frescura    minutos entre el titular MAS NUEVO de cada simbolo y ahora (mediana y p90)
  ruido       % de titulares que caza el filtro de fleet_news_watch (agregador autogenerado)
  coste       peticiones y segundos para cubrir la flota entera
  APORTE      titulares que ese proveedor trae y NINGUN otro tiene (dedup de news_store)

El APORTE es el numero que decide: un proveedor que solo repite lo que ya trae otro no vale
lo que cuesta. Se calcula quitando cada proveedor del conjunto y viendo que titulares se pierden.

Solo lectura: cero publicacion a Discord, cero escritura en data/news_seen.json.
"""
import argparse
import json
import os
import statistics
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import discord_client as dc          # noqa: E402
import fleet_news_watch as FN        # noqa: E402
import news_store as NS              # noqa: E402

PROVEEDORES = ["alpaca", "uw", "polygon", "finnhub", "gnews"]
RAROS = ("DRAM", "SPCX", "SKHY", "EWY", "NOK", "SNDK", "XLK", "WDC", "STX")


def creds():
    kid, ksec = dc.secret("ALPACA_API_KEY_ID"), dc.secret("ALPACA_API_SECRET_KEY")
    return {"alpaca": (kid, ksec) if (kid and ksec) else None,
            "uw": dc.secret("UW_TOKEN"),
            "polygon": dc.secret("POLYGON_KEY"),
            "finnhub": dc.secret("FINNHUB_KEY"),
            "gnews": True}


def barrer(nombre, syms, ventana_s, cred):
    """(items, reqs, segundos, error). error=None si fue bien. Jamas devuelve items fingidos."""
    t0 = time.time()
    try:
        if nombre == "alpaca":
            items, reqs = FN.src_alpaca(syms, cred, ventana_s), (len(syms) + 49) // 50
        elif nombre == "uw":
            items, reqs = FN.src_uw(syms, cred, ventana_s), 1
        elif nombre == "polygon":
            items, reqs = FN.src_polygon(syms, cred, ventana_s), len(syms)
        elif nombre == "finnhub":
            items, reqs = FN.src_finnhub(syms, cred, ventana_s), len(syms)
        elif nombre == "gnews":
            items, reqs = FN.src_gnews(syms, ventana_s), len(syms)
        else:
            return [], 0, 0.0, "proveedor desconocido"
    except Exception as e:
        return [], 0, time.time() - t0, "%s: %s" % (e.__class__.__name__, str(e)[:100])
    return items, reqs, time.time() - t0, None


def metricas(items, syms, ahora):
    cubiertos = {}
    ruido = 0
    for it in items:
        malo, _ = FN.es_ruido(it)
        if malo:
            ruido += 1
        s = it["sym"]
        cubiertos[s] = max(cubiertos.get(s, 0), it["ts"])
    lags = sorted((ahora - ts) / 60.0 for ts in cubiertos.values())
    return {
        "titulares": len(items),
        "cobertura": len(cubiertos),
        "cobertura_pct": round(100.0 * len(cubiertos) / max(1, len(syms)), 1),
        "sin_cobertura": sorted(set(syms) - set(cubiertos)),
        "raros_cubiertos": sorted(s for s in RAROS if s in cubiertos and s in syms),
        "lag_mediano_min": round(statistics.median(lags), 1) if lags else None,
        "lag_p90_min": round(lags[int(len(lags) * 0.9)] if len(lags) > 1 else lags[0], 1)
                        if lags else None,
        "lag_min_min": round(lags[0], 1) if lags else None,
        "ruido_pct": round(100.0 * ruido / len(items), 1) if items else None,
    }


def claves(items):
    """set de claves de dedup de una lista de titulares (limpios de ruido)."""
    ks = set()
    for it in items:
        if FN.es_ruido(it)[0]:
            continue
        for k in NS.keys(it["title"], it.get("url")):
            ks.add(k)
    return ks


def main():
    ap = argparse.ArgumentParser(description="compara proveedores de noticias (solo lectura)")
    ap.add_argument("--syms", help="coma; por defecto data/fleet.txt entero")
    ap.add_argument("--ventana-h", type=float, default=6.0)
    ap.add_argument("--proveedores", default=",".join(PROVEEDORES))
    ap.add_argument("--json", help="guarda el informe en este fichero")
    a = ap.parse_args()

    syms = ([s.strip().upper() for s in a.syms.split(",") if s.strip()] if a.syms
            else FN.fleet())
    quiere = [p for p in a.proveedores.split(",") if p.strip() in PROVEEDORES]
    cr = creds()
    ahora = time.time()
    print("barriendo %d simbolos, ventana %.0f h, %s\n" % (len(syms), a.ventana_h,
                                                           time.strftime("%Y-%m-%d %H:%M:%S")))
    res = {}
    for p in quiere:
        if not cr.get(p):
            res[p] = {"error": "SIN CREDENCIAL (no medido)"}
            print("%-9s SIN CREDENCIAL — no medido" % p)
            continue
        items, reqs, secs, err = barrer(p, syms, a.ventana_h * 3600, cr[p])
        if err:
            res[p] = {"error": err}
            print("%-9s ROTO: %s" % (p, err))
            continue
        m = metricas(items, syms, ahora)
        m.update({"reqs": reqs, "segundos": round(secs, 1), "_items": items})
        res[p] = m
        print("%-9s %3d titulares · cobertura %2d/%d (%.0f%%) · lag med %s p90 %s min · "
              "ruido %s%% · %d req en %.0fs"
              % (p, m["titulares"], m["cobertura"], len(syms), m["cobertura_pct"],
                 m["lag_mediano_min"], m["lag_p90_min"], m["ruido_pct"], reqs, secs))

    vivos = [p for p in res if "_items" in res[p]]
    print("\nAPORTE UNICO (titulares que solo trae ese proveedor, tras dedup):")
    for p in vivos:
        otros = set()
        for q in vivos:
            if q != p:
                otros |= claves(res[q]["_items"])
        mios = claves(res[p]["_items"])
        solo = mios - otros
        res[p]["aporte_unico_claves"] = len(solo)
        res[p]["aporte_pct"] = round(100.0 * len(solo) / max(1, len(mios)), 1)
        print("  %-9s %4d claves propias · %4d exclusivas (%.0f%% de lo suyo)"
              % (p, len(mios), len(solo), res[p]["aporte_pct"]))

    if vivos:
        union = set()
        for p in vivos:
            union |= claves(res[p]["_items"])
        print("\ncobertura conjunta: %d titulares distintos" % len(union))
        mejor = max(vivos, key=lambda p: (res[p]["cobertura"], -(res[p]["lag_mediano_min"] or 1e9)))
        print("mejor por cobertura+frescura: %s" % mejor)
    faltan = [p for p in quiere if p not in vivos]
    if faltan:
        print("NO MEDIDOS: %s" % ", ".join("%s (%s)" % (p, res[p].get("error")) for p in faltan))

    if a.json:
        limpio = {p: {k: v for k, v in d.items() if not k.startswith("_")}
                  for p, d in res.items()}
        limpio["_meta"] = {"ts": ahora, "simbolos": syms, "ventana_h": a.ventana_h}
        with open(a.json, "w") as f:
            json.dump(limpio, f, indent=1, sort_keys=True)
        print("\ninforme -> %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
