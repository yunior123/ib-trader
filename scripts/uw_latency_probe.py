#!/usr/bin/env python3
"""uw_latency_probe.py — MEDIR (no suponer) la latencia real de Unusual Whales
en sesion viva, condicion dura de ~/CLAUDE.md antes de fiarse de una fuente
("ningun nivel que dispare una orden viene de fuente delayed"). Correr manual
en horas de mercado: ./venv/bin/python scripts/uw_latency_probe.py
Fuera de horas dice por que no midio, jamas finge un numero (2026-07-26,
domingo con mercado cerrado: NO se pudo medir hoy, queda listo para el lunes).
Escribe data/uw_latency_probe.jsonl (historial acumulado). SEÑAL-SOLAMENTE.

--rth-measure (TODOS 8a+8b, 2026-08-05): corrida topada a MAX_REQ peticiones que compara
el tape_time de UW contra (a) el reloj y (b) el ultimo print de finnhub
(data/rt_last_<SYM>.txt), y ademas re-prueba el websocket en RTH (8b). Sin IBKR esta
semana, finnhub es el proxy del disparador; el contraste definitivo contra
data/bars_<SYM>.txt sigue pendiente en TODOS 8f."""
import argparse
import base64
import datetime as dt
import json
import os
import socket
import ssl
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import em_envelope
import uw_premium

PROBE_F = os.path.join(REPO, "data", "uw_latency_probe.jsonl")
OUT_JSON = os.path.join(REPO, "data", "uw_latency.json")
SYMS = ["SPY", "QQQ"]
REALTIME_BAR_S = 60   # 1 bucket de tape: mas viejo que esto ya no es "tiempo real"

BASE = "https://api.unusualwhales.com"
WS_HOST = "api.unusualwhales.com"
UA = "ib-trader/1.0 (uw_latency_probe senal-solamente)"
MAX_REQ = 10          # tope duro de peticiones UW por corrida (orden de Yunior)


def in_session():
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def probe_darkpool(sym, tok, now):
    """Edad del print de bloque mas reciente. El dato NO se toca: solo se mide."""
    import uw_darkpool
    rows, err = uw_darkpool.fetch_darkpool(sym, tok)
    if rows is None:
        return {"sym": sym, "endpoint": "darkpool", "error": err}
    lat = uw_darkpool.latency(uw_darkpool.clean(rows), now=now.timestamp())
    if lat is None:
        return {"sym": sym, "endpoint": "darkpool", "error": "sin prints utilizables"}
    return {"sym": sym, "endpoint": "darkpool", "feed_ts": lat["newest_iso"],
            "feed_age_s": lat["feed_age_s"], "trf_lag_med_s": lat["trf_lag_med_s"],
            "n_rows": len(rows)}


def probe_gex_expiry(sym, tok, now):
    """Sello EOD de greek-exposure/expiry. Se espera DIARIO, no segundos: se mide en dias."""
    import uw_gex_expiry
    rows, err = uw_gex_expiry.fetch_expiry(sym, tok)
    if rows is None:
        return {"sym": sym, "endpoint": "greek-exposure/expiry", "error": err}
    s = uw_gex_expiry.summarize(sym, rows)
    if "error" in s:
        return {"sym": sym, "endpoint": "greek-exposure/expiry", "error": s["error"]}
    stamp = s["asof_date"]
    age = (now.date() - dt.date.fromisoformat(stamp)).days
    return {"sym": sym, "endpoint": "greek-exposure/expiry", "feed_ts": stamp,
            "feed_age_days": age, "n_rows": len(rows)}


# --------------------------------------------------------------------------------------
# 8a: latencia contra el reloj Y contra el print de finnhub
# --------------------------------------------------------------------------------------

class Quota:
    """Ultimo x-uw-daily-req-count visto. Sirve para MEDIR si el websocket consume cupo."""
    used = None
    limit = None
    n_req = 0


def get_json(path, tok):
    """(payload, net_ms). Levanta con el motivo: un fallo jamas se convierte en numero."""
    if Quota.n_req >= MAX_REQ:
        raise RuntimeError("tope de %d peticiones alcanzado: no se pide mas" % MAX_REQ)
    req = urllib.request.Request(BASE + path, headers={
        "Authorization": "Bearer " + tok, "Accept": "application/json", "User-Agent": UA})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=15) as r:
        ms = (time.monotonic() - t0) * 1000.0
        raw = r.read().decode("utf-8", "replace")
        Quota.n_req += 1
        h = r.headers
        if h.get("x-uw-daily-req-count"):
            try:
                Quota.used = int(h["x-uw-daily-req-count"])
            except ValueError:
                pass
        if h.get("x-uw-token-req-limit"):
            try:
                Quota.limit = int(h["x-uw-token-req-limit"])
            except ValueError:
                pass
    return json.loads(raw), round(ms, 1)


def finnhub_print(sym):
    """(epoch, precio) del ultimo print de finnhub. None si falta o no parsea: nunca 0."""
    p = os.path.join(REPO, "data", "rt_last_%s.txt" % sym.upper())
    try:
        with open(p) as f:
            t = f.read().split()
        return float(t[0]), float(t[1])
    except (OSError, IndexError, ValueError):
        return None


def one_pass(sym, tok, now):
    """net-prem-ticks + stock-state de un simbolo. 2 peticiones."""
    rec = {"sym": sym, "ts": now.isoformat()}
    try:
        rows, ms = get_json("/api/stock/%s/net-prem-ticks" % sym, tok)
        rows = rows.get("data") if isinstance(rows, dict) else rows
        age_s, feed_ts = uw_premium.latest_feed_age_s(rows, now=now)
        rec["net_prem_ticks"] = {"feed_ts": feed_ts, "feed_age_s": age_s, "n_rows": len(rows),
                                 "net_ms": ms,
                                 "cube_lag": None if age_s is None else int(age_s // 60)}
    except Exception as e:
        rec["net_prem_ticks"] = {"error": "%s: %s" % (type(e).__name__, str(e)[:120])}
    try:
        d, ms = get_json("/api/stock/%s/stock-state" % sym, tok)
        st = d.get("data") if isinstance(d, dict) else None
        if not isinstance(st, dict) or "tape_time" not in st:
            raise ValueError("stock-state sin tape_time")
        tt = st["tape_time"]
        age = (now - dt.datetime.fromisoformat(tt.replace("Z", "+00:00"))).total_seconds()
        rec["stock_state"] = {"feed_ts": tt, "feed_age_s": round(age, 2),
                              "market_time": st.get("market_time"), "net_ms": ms,
                              "close": st.get("close"), "volume": st.get("volume")}
    except Exception as e:
        rec["stock_state"] = {"error": "%s: %s" % (type(e).__name__, str(e)[:120])}

    fp = finnhub_print(sym)
    if fp is None:
        rec["finnhub"] = {"error": "sin data/rt_last_%s.txt utilizable" % sym.upper()}
    else:
        ep, px = fp
        f_age = now.timestamp() - ep
        rec["finnhub"] = {"print_epoch": ep, "print_px": px, "print_age_s": round(f_age, 2)}
        ss = rec.get("stock_state", {})
        if ss.get("feed_age_s") is not None:
            # >0 = UW va POR DETRAS del print de finnhub. Es el desfase contra el disparador.
            rec["finnhub"]["uw_menos_finnhub_s"] = round(ss["feed_age_s"] - f_age, 2)
            if ss.get("close") is not None:
                try:
                    rec["finnhub"]["px_gap"] = round(float(ss["close"]) - px, 4)
                except (TypeError, ValueError):
                    pass
    return rec


# --------------------------------------------------------------------------------------
# 8b: websocket en RTH
# --------------------------------------------------------------------------------------

def ws_try(path, tok, send=None, wait_s=8.0, label=""):
    """Handshake WS crudo (sin dependencias) y lectura hasta EOF/timeout. El error ES el dato."""
    out = {"label": label, "path": path, "envio": send}
    key = base64.b64encode(os.urandom(16)).decode()
    url = path + ("&" if "?" in path else "?") + "token=" + tok
    hs = ("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
          "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nOrigin: https://unusualwhales.com\r\n"
          "User-Agent: %s\r\n\r\n" % (url, WS_HOST, key, UA))
    t0 = time.monotonic()
    try:
        raw = socket.create_connection((WS_HOST, 443), timeout=10)
        s = ssl.create_default_context().wrap_socket(raw, server_hostname=WS_HOST)
        s.sendall(hs.encode())
        s.settimeout(wait_s)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            b = s.recv(4096)
            if not b:
                break
            head += b
        out["t_handshake_s"] = round(time.monotonic() - t0, 4)
        line = head.split(b"\r\n", 1)[0].decode("latin1") if head else ""
        out["status_line"] = line
        out["upgraded"] = "101" in line
        if send is not None and out["upgraded"]:
            payload = json.dumps(send).encode()
            mask = os.urandom(4)
            ln = len(payload)
            hdr = bytes([0x81]) + (bytes([0x80 | ln]) if ln < 126
                                   else bytes([0x80 | 126, ln >> 8, ln & 0xFF]))
            s.sendall(hdr + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))
        body = head.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in head else b""
        t1 = time.monotonic()
        try:
            while time.monotonic() - t1 < wait_s:
                b = s.recv(4096)
                if not b:
                    out["eof"] = True
                    break
                body += b
        except socket.timeout:
            out["eof"] = False
        out["t_cierre_s"] = round(time.monotonic() - t0, 4)
        out["bytes_datos"] = len(body)
        out["close_frame"] = bool(body) and body[0] & 0x0F == 0x08
        out["muestra"] = body[:200].decode("latin1") if body else ""
        s.close()
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:120])
        out["t_cierre_s"] = round(time.monotonic() - t0, 4)
    return out


def ws_suite(tok):
    """Los 3 casos que decidian el veredicto de madrugada, repetidos en RTH."""
    return [
        ws_try("/api/socket", tok, send=None, label="sin enviar nada"),
        ws_try("/api/socket", tok, send=["flow-alerts", "join"], label="join lista"),
        ws_try("/api/socket", tok, send={"channel": "flow-alerts", "msg_type": "join"},
               label="join objeto"),
    ]


def rth_measure(tok, pausa_s, forzar):
    now0 = dt.datetime.now(dt.timezone.utc)
    sesion = in_session()
    if not sesion and not forzar:
        print("FUERA DE SESION: la latencia de UW no es medible ahora (la edad del sello seria "
              "el tiempo desde el cierre). Probe NO ejecutado — usa --force solo para etiquetar "
              "una medicion de premarket como tal.", file=sys.stderr)
        return 1

    rep = {"generado_utc": now0.isoformat(), "en_rth": sesion, "forzado": forzar,
           "tope_peticiones": MAX_REQ, "pasadas": [], "websocket": None,
           "nota_disparador": "sin IBKR esta semana: el proxy del disparador es el print de "
                              "finnhub (data/rt_last_<SYM>.txt); TODOS 8f sigue pendiente"}

    for i in range(2):
        now = dt.datetime.now(dt.timezone.utc)
        pasada = {"n": i + 1, "ts": now.isoformat(), "syms": []}
        for sym in SYMS:
            r = one_pass(sym, tok, now)
            pasada["syms"].append(r)
            npt, ss, fh = r.get("net_prem_ticks", {}), r.get("stock_state", {}), r.get("finnhub", {})
            print("[%d/2] %-4s net-prem-ticks edad=%s cubos=%s | stock-state edad=%s (%s) | "
                  "finnhub edad=%ss  UW-finnhub=%ss"
                  % (i + 1, sym, npt.get("feed_age_s"), npt.get("cube_lag"),
                     ss.get("feed_age_s"), ss.get("market_time"),
                     fh.get("print_age_s"), fh.get("uw_menos_finnhub_s")), file=sys.stderr)
            with open(PROBE_F, "a") as f:
                f.write(json.dumps(r, separators=(",", ":"), default=str) + "\n")
        rep["pasadas"].append(pasada)
        if i == 0:
            q_antes = Quota.used
            rep["websocket"] = {"casos": ws_suite(tok), "cupo_antes": q_antes}
            time.sleep(max(0.0, pausa_s))

    # ¿el 101 del websocket consume cupo? Se mide con el salto del contador, no se supone.
    try:
        d, _ = get_json("/api/socket", tok)
        rep["socket_get"] = {"canales_declarados": d.get("data") if isinstance(d, dict) else d,
                             "cupo_despues": Quota.used}
    except Exception as e:
        rep["socket_get"] = {"error": "%s: %s" % (type(e).__name__, str(e)[:120])}

    rep["cupo"] = {"usado_hoy": Quota.used, "limite": Quota.limit,
                   "peticiones_de_esta_corrida": Quota.n_req}

    edades, edades_ss, desfases = [], [], []
    for p in rep["pasadas"]:
        for r in p["syms"]:
            a = r.get("net_prem_ticks", {}).get("feed_age_s")
            if a is not None:
                edades.append(a)
            b = r.get("stock_state", {}).get("feed_age_s")
            if b is not None:
                edades_ss.append(b)
            c = r.get("finnhub", {}).get("uw_menos_finnhub_s")
            if c is not None:
                desfases.append(c)
    rep["resumen"] = {
        "net_prem_ticks_edad_s": {"min": min(edades), "max": max(edades),
                                  "mediana": sorted(edades)[len(edades) // 2]} if edades else None,
        "stock_state_edad_s": {"min": min(edades_ss), "max": max(edades_ss),
                               "mediana": sorted(edades_ss)[len(edades_ss) // 2]} if edades_ss else None,
        "uw_menos_finnhub_s": {"min": min(desfases), "max": max(desfases),
                               "mediana": sorted(desfases)[len(desfases) // 2]} if desfases else None,
        "veredicto_stock_state": (None if not edades_ss else
                                  ("CANDIDATO A TIEMPO-REAL" if max(edades_ss) < REALTIME_BAR_S
                                   else "DELAYED — no dispara")),
        "veredicto_net_prem_ticks": (None if not edades else
                                     ("CANDIDATO A TIEMPO-REAL" if max(edades) < REALTIME_BAR_S
                                      else "DELAYED — no dispara")),
    }
    ws = rep.get("websocket") or {}
    casos = ws.get("casos") or []
    rep["resumen"]["websocket_entrega_datos"] = any(
        c.get("bytes_datos", 0) > 0 and not c.get("close_frame") for c in casos)

    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, indent=1, default=str)
    os.replace(tmp, OUT_JSON)
    print("\n-> %s" % OUT_JSON, file=sys.stderr)
    print(json.dumps(rep["resumen"], indent=1, default=str))
    write_doc(rep)
    return 0


def write_doc(rep):
    """docs/UW-LATENCIA-RTH-<fecha>.md con los numeros medidos. Sin numero no se escribe fila."""
    hoy = dt.date.today().isoformat()
    doc = os.path.join(REPO, "docs", "UW-LATENCIA-RTH-%s.md" % hoy)
    r = rep["resumen"]
    L = []
    L.append("# UW — latencia medida en sesion (%s)\n" % hoy)
    L.append("Generado por `scripts/uw_latency_probe.py --rth-measure`. "
             "TODOS 8a (latencia) + 8b (websocket).\n")
    L.append("- Corrida: %s UTC · en_rth=%s%s · peticiones UW=%s (tope %s) · cupo %s/%s\n"
             % (rep["generado_utc"], rep["en_rth"], " **FORZADA**" if rep.get("forzado") else "",
                rep["cupo"]["peticiones_de_esta_corrida"], rep["tope_peticiones"],
                rep["cupo"]["usado_hoy"], rep["cupo"]["limite"]))
    L.append("- %s\n" % rep["nota_disparador"])
    L.append("\n## 8a — edad del feed y desfase contra el disparador\n")
    L.append("| medida | min | mediana | max |")
    L.append("|---|---|---|---|")
    for k, nom in (("stock_state_edad_s", "`stock-state.tape_time` vs reloj (s)"),
                   ("net_prem_ticks_edad_s", "`net-prem-ticks.tape_time` vs reloj (s)"),
                   ("uw_menos_finnhub_s", "UW − print finnhub (s, >0 = UW detras)")):
        v = r.get(k)
        if v:
            L.append("| %s | %.2f | %.2f | %.2f |" % (nom, v["min"], v["mediana"], v["max"]))
    L.append("\n**Veredicto** (umbral de la casa: <60 s = candidato a tiempo real):")
    L.append("- `stock-state`: **%s**" % r.get("veredicto_stock_state"))
    L.append("- `net-prem-ticks`: **%s**" % r.get("veredicto_net_prem_ticks"))
    L.append("\nPrediccion registrada de antemano en TODOS 8a: **30-90 s**.\n")
    L.append("\n## 8b — websocket en RTH\n")
    L.append("| caso | status | handshake s | cierre s | bytes | close-frame |")
    L.append("|---|---|---|---|---|---|")
    for c in ((rep.get("websocket") or {}).get("casos") or []):
        L.append("| %s | %s | %s | %s | %s | %s |"
                 % (c.get("label"), c.get("status_line", c.get("error", "?"))[:40],
                    c.get("t_handshake_s"), c.get("t_cierre_s"), c.get("bytes_datos"),
                    c.get("close_frame")))
    sg = rep.get("socket_get") or {}
    L.append("\n`GET /api/socket` canales declarados: `%s`" % (sg.get("canales_declarados"),))
    L.append("\n**El socket entrega datos en RTH: %s**"
             % ("SI — el veredicto de madrugada QUEDA REVOCADO"
                if r.get("websocket_entrega_datos") else
                "NO — se mantiene el veredicto: no se construye consumidor"))
    coli = os.path.join(REPO, "data", "uw_colinealidad.json")
    if os.path.isfile(coli):
        try:
            with open(coli) as f:
                c = json.load(f)
            L.append("\n## 8c — colinealidades (killlist test 1: |rho|>0,9 = muere ya)\n")
            c1 = c["coli_1_vega_vs_signed_premium"]
            L.append("**(1) `dir_vega_flow` vs `signed_premium`** — rho_pooled=**%s** "
                     "(n=%s minutos, %s dias, %s syms); per-sym min/mediana/max = %s / %s / %s"
                     % (_r(c1["rho_pooled"]), c1["n_minutos"], c1["dias"], c1["syms"],
                        _r(c1["rho_per_sym_min"]), _r(c1["rho_per_sym_mediana"]),
                        _r(c1["rho_per_sym_max"])))
            cd = c1["control_delta"]
            L.append("- control `dir_delta_flow` vs `net_delta` (precedente rho=1,0): rho=**%s**, "
                     "byte-identicos %s/%s" % (_r(cd["rho"]), cd["byte_identicos"], cd["comparados"]))
            c2 = c["coli_2_capitan_vs_manada_barras"]
            L.append("\n**(2) `senal_capitan` vs `fleet_consensus` (manada sobre BARRAS)** — %d dias:"
                     % len(c2["dias"]))
            L.append("\n| capitan | rho | n | acuerdo de signo |")
            L.append("|---|---|---|---|")
            for cap, v in c2["capitanes"].items():
                L.append("| %s | %s | %s | %s%% |"
                         % (cap, _r(v["rho"]), v["n_buckets"], v["acuerdo_signo_pct"]))
            c3 = c["coli_3_maxpain_vs_abswall"]
            L.append("\n**(3) `max_pain` (UW/OI) vs `abs_wall` (gex)** — rho=**%s** (n=%s sym-dias, "
                     "%d dias); strike identico en **%s%%**; mediana |max_pain−abs_wall|/spot = **%s%%**"
                     % (_r(c3["rho"]), c3["n_sym_dias"], len(c3["dias"]),
                        c3["strike_identico_pct"], c3["mediana_dist_pct"]))
            L.append("\nAvisos que NO se pueden omitir al leer estos numeros: la muestra de (2) son "
                     "buckets SOLAPADOS de pocas sesiones (n_eff mucho menor que n) y el signo de "
                     "(1) cambia entre dias. Sobrevivir la colinealidad NO es tener edge: "
                     "publicar probabilidad sigue bloqueado en TODOS 8e.")
        except (ValueError, KeyError) as e:
            L.append("\n## 8c — colinealidades\n\nNO LEIDO: %s" % e)
    with open(doc, "w") as f:
        f.write("\n".join(L) + "\n")
    print("-> %s" % doc, file=sys.stderr)


def _r(x):
    return "n/d" if x is None else ("%.4f" % x if isinstance(x, float) else str(x))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="+ darkpool y greek-exposure/expiry")
    ap.add_argument("--rth-measure", action="store_true",
                    help="TODOS 8a+8b: latencia vs reloj y vs finnhub + websocket (tope %d req)"
                         % MAX_REQ)
    ap.add_argument("--pausa", type=float, default=120.0, help="segundos entre las 2 pasadas")
    ap.add_argument("--force", action="store_true",
                    help="mide fuera de RTH y lo ETIQUETA como forzado (jamas lo oculta)")
    ap.add_argument("--doc-only", action="store_true",
                    help="reescribe el .md desde data/uw_latency.json sin pedir nada")
    # argv=None -> sin banderas. Los tests llaman main() con el argv de pytest aun en sys.argv;
    # dejar que argparse lea sys.argv daria SystemExit 2. El CLI pasa sys.argv[1:] explicito.
    a = ap.parse_args([] if argv is None else argv)

    if a.doc_only:
        with open(OUT_JSON) as f:
            write_doc(json.load(f))
        return 0

    if a.rth_measure:
        tok = uw_premium.token()
        if not tok:
            print("SIN UW_TOKEN: no se puede medir", file=sys.stderr)
            return 1
        return rth_measure(tok, a.pausa, a.force)

    if not in_session():
        print("FUERA DE SESION (fin de semana, festivo o fuera de 09:30-16:00): "
              "no se puede medir latencia real hoy — probe NO ejecutado", file=sys.stderr)
        return 1
    tok = uw_premium.token()
    if not tok:
        print("SIN UW_TOKEN: no se puede medir", file=sys.stderr)
        return 1

    now = dt.datetime.now(dt.timezone.utc)
    results = []
    for sym in SYMS:
        try:
            rows = uw_premium.fetch_net_prem_ticks(sym, tok)
            age_s, feed_ts = uw_premium.latest_feed_age_s(rows, now=now)
            rec = {"ts": now.isoformat(), "sym": sym, "endpoint": "net-prem-ticks",
                   "feed_ts": feed_ts, "feed_age_s": age_s, "n_rows": len(rows)}
        except Exception as e:
            rec = {"ts": now.isoformat(), "sym": sym, "endpoint": "net-prem-ticks",
                   "error": str(e)}
        results.append(rec)
        print(json.dumps(rec))
        with open(PROBE_F, "a") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        time.sleep(0.6)

    # Endpoints de los widgets nuevos: se miden APARTE porque su unidad no es la misma
    # (darkpool en segundos, greek-exposure/expiry en DIAS) y mezclarlos daria un veredicto falso.
    if a.all:
        for sym in SYMS:
            for fn in (probe_darkpool, probe_gex_expiry):
                r = dict(fn(sym, tok, now), ts=now.isoformat())
                print(json.dumps(r))
                with open(PROBE_F, "a") as f:
                    f.write(json.dumps(r, separators=(",", ":")) + "\n")
                time.sleep(0.6)

    fails = [r for r in results if "error" in r]
    if fails:
        print(f"-> {len(fails)}/{len(results)} FALLARON, no se puede fijar veredicto", file=sys.stderr)
        return 1
    ages = [r["feed_age_s"] for r in results if r.get("feed_age_s") is not None]
    if not ages:
        print("-> sin feed_age_s en ninguna fila: no se puede fijar veredicto", file=sys.stderr)
        return 1
    veredicto = "CANDIDATO A TIEMPO-REAL" if max(ages) < REALTIME_BAR_S else "DELAYED — no dispara"
    print(f"-> UW feed_age_s min={min(ages):.1f}s max={max(ages):.1f}s -> {veredicto}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
