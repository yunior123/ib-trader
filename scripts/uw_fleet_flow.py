#!/usr/bin/env python3
"""uw_fleet_flow.py — alertas de flujo UW para la FLOTA entera. SEÑAL-SOLAMENTE, DESCRIPTIVO.

Sustituto UW del vigía de ballenas mientras IBKR está prohibido (opt_flow.txt congelado desde
el 07-31: opt_whale_watch es ib_insync). UNA request a /api/option-trades/flow-alerts (global,
37 campos medidos en el recon 2026-08-04) filtrada a data/fleet.txt: 60 s de cadencia =
~390 req/sesión, 1,3% del cupo — contra 30 req/min de la vía por-símbolo.

QUÉ CANTA (hechos MEDIDOS por UW, cero probabilidad inventada — las 3 alertas con edge
plausible del recon esperan su colinealidad; esto es la cinta descriptiva):
  - premium total >= $1M con lado agresor dominante
  - vol/OI >= 2 con premium >= $250k (posicion NUEVA, no rolo)
  - sweep con premium >= $500k (agresor con prisa)
Titulo "UW FLOW <SYM>" -> regla `\\bUW\\b` de discord_layout -> #flujo-uw (+ espejos).

Anti-ruido de nacimiento: dedup por id de alerta PERSISTIDO (data/uw_fleet_flow_state.json),
cooldown 15 min por contrato, tope 3 pushes/min (el resto se registra, no se canta).
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uw_premium import token  # noqa: E402
import em_envelope  # noqa: E402
import notify_short  # noqa: E402

BASE = "https://api.unusualwhales.com"
UA = "ib-trader/1.0 (uw_fleet_flow senal-solamente)"
OUT = os.path.join(REPO, "data", "uw_fleet_flow.json")
STATE = os.path.join(REPO, "data", "uw_fleet_flow_state.json")
POLL_S = 60.0
LIMIT = 100
TIMEOUT_S = 20
BACKOFF_S = (5, 15, 40)

MIN_PREM_GRANDE = 1_000_000.0     # premium total con lado dominante
MIN_PREM_VOLOI = 250_000.0        # con vol/OI alto (posicion nueva)
MIN_VOLOI = 2.0
MIN_PREM_SWEEP = 500_000.0
COOLDOWN_CONTRATO_S = 900.0       # el mismo contrato no se repite en 15 min
MAX_PUSH_MIN = 3                  # tope de voz al embudo; el resto solo al json

# ---- CONVICCION FUERTE (Yunior 2026-08-07: "lets make them less annoying ... filter out
# irrelevant whales based on total volume of shares or whales that are not backed by other
# whales, we only need strong conviction").
# Ritmo MEDIDO antes de esto: 1093 pushes en 4 sesiones = ~273/sesion, uno cada 85 s de RTH.
# Los umbrales salen del archivo real (6.000 alertas de data/history/*/uw_flow_alerts_*.json,
# ADV en dolares de 20 sesiones de poly_bars), no de una opinion:
#   notional controlado / ADV$  ->  p50 0,059%  p75 0,161%  p90 0,357%  p99 1,20%
#   de las 644 que hoy pasan el gate, sobreviven 51% con rel>=0,20% y 14% si ademas exigimos
#   respaldo K=2 en 20 min  ->  ~38 pushes/sesion antes del presupuesto de voz.
# (El archivo es una foto de 100 alertas por simbolo, no la sesion entera: el respaldo real
# sera algo MAS frecuente que ese 14%. Se dice, no se esconde.)
MIN_REL_ADV = 0.0020              # p75 medido: la ballena tiene que pesar en SU subyacente
RESPALDO_VENTANA_S = 1200.0       # 20 min
RESPALDO_MIN_CONTRATOS = 2        # 2 contratos DISTINTOS del mismo sesgo, o no es conviccion
MAX_PUSH_SYM_HORA = 2             # ninguna corneta repite mas de esto por simbolo y hora
MAX_PUSH_SESION = 14              # presupuesto total de voz por sesion
ADV_CACHE = os.path.join(REPO, "data", "uw_adv_dolares.json")
ADV_MIN_SESIONES = 10
STREAM_DIR = os.path.join(REPO, "data", "history")   # candidatas archivadas para poder GRADUARLO


def fleet():
    syms = open(os.path.join(REPO, "data", "fleet.txt")).read().split()
    if not syms:
        raise RuntimeError("data/fleet.txt vacio")
    return set(s.upper() for s in syms)


def in_session():
    lt = time.localtime()
    if lt.tm_wday >= 5 or not (930 <= lt.tm_hour * 100 + lt.tm_min < 1600):
        return False
    return em_envelope.is_market_day(dt.date(lt.tm_year, lt.tm_mon, lt.tm_mday))


def load_adv():
    """ADV en DOLARES por simbolo (20 sesiones de poly_bars). Simbolo sin muestra suficiente
    NO entra: sin denominador no hay relevancia, y un denominador inventado es peor que nada."""
    import sqlite3
    try:
        with open(ADV_CACHE) as f:
            c = json.load(f)
        if time.time() - c.get("asof", 0) < 20 * 3600 and c.get("adv"):
            return c["adv"]
    except (OSError, ValueError):
        pass
    adv = {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % os.path.join(REPO, "data", "trades.db"), uri=True)
        for (sym,) in con.execute("select distinct sym from poly_bars"):
            rows = con.execute(
                "select date(ts/1000,'unixepoch') d, sum(v*c) from poly_bars "
                "where sym=? group by d order by d desc limit 20", (sym,)).fetchall()
            vals = [v for _, v in rows if v]
            if len(vals) >= ADV_MIN_SESIONES:
                adv[sym.upper()] = sum(vals) / len(vals)
        con.close()
    except Exception as e:                       # noqa: BLE001 — se DICE y se sigue sin gate
        print("uw_fleet_flow: ADV no disponible (%s): sin gate de relevancia" % e, file=sys.stderr)
        return {}
    tmp = ADV_CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"asof": time.time(), "adv": adv}, f)
    os.replace(tmp, ADV_CACHE)
    return adv


def archiva_candidata(fila):
    """Toda candidata (cantada o no) al JSONL del dia: sin este registro la conviccion
    jamas se podra GRADUAR contra el precio, y seria una regla no medible para siempre."""
    day = time.strftime("%Y-%m-%d")
    d = os.path.join(STREAM_DIR, day)
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "uw_fleet_flow_stream.jsonl"), "a") as f:
            f.write(json.dumps(fila, separators=(",", ":")) + "\n")
    except OSError as e:
        print("uw_fleet_flow: no pude archivar la candidata (%s)" % e, file=sys.stderr)


def fetch(tok):
    """(rows, None) o (None, motivo). Nunca [] fingido."""
    req = urllib.request.Request(
        "%s/api/option-trades/flow-alerts?limit=%d" % (BASE, LIMIT),
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json",
                 "User-Agent": UA})
    n_throttle = 0
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                payload = json.loads(r.read().decode("utf-8", "replace"))
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return None, "forma inesperada: %s" % type(payload).__name__
            return rows, None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return None, "401 token caducado"
            if e.code in (403, 429):
                if n_throttle < len(BACKOFF_S):
                    time.sleep(BACKOFF_S[n_throttle])
                    n_throttle += 1
                    continue
                return None, "%d tras %d esperas" % (e.code, n_throttle)
            last = "error %d" % e.code
        except Exception as e:
            last = "%s: %s" % (e.__class__.__name__, str(e)[:60])
        if attempt < 3:
            time.sleep(1.5)
    return None, last


def _f(r, k):
    """Campo numerico obligatorio. Levanta si falta: jamas un 0 plausible."""
    v = r.get(k)
    if v is None:
        raise KeyError(k)
    return float(v)


def side(r):
    """Lado agresor dominante por premiums POR LADO (UW no trae `side`; patron uw_flow_tape)."""
    total, bid, ask = _f(r, "total_premium"), _f(r, "total_bid_side_prem"), _f(r, "total_ask_side_prem")
    mid = max(total - bid - ask, 0.0)
    return max((bid, "bid"), (ask, "ask"), (mid, "mid"))[1]


def qualifies(r, adv=None):
    """(motivo, dict_datos) si el alert merece cantarse; None si no. Malformado -> None y se salta.

    Al mid NO se canta NUNCA (antes solo lo exigia la regla del premium): sin lado agresor no
    hay direccion que afirmar. Y la ballena tiene que PESAR en su propio subyacente: el
    notional que controla frente al ADV en dolares, no dolares absolutos (un $1M en SPY es
    ruido de fondo y en NOK es el dia entero)."""
    try:
        prem = _f(r, "total_premium")
        voloi = _f(r, "volume_oi_ratio")
        sweep = bool(r.get("has_sweep"))
        lado = side(r)
        sym = r["ticker"].upper()
        size = int(r.get("total_size") or 0)
        under = float(r.get("underlying_price") or 0)
        datos = {"sym": sym, "cp": "CALLS" if r["type"] == "call" else "PUTS",
                 "strike": float(r["strike"]), "exp": str(r["expiry"]),
                 "prem": prem, "voloi": voloi, "sweep": sweep, "lado": lado,
                 "size": size, "oi": int(r.get("open_interest") or 0),
                 "chain": r.get("option_chain") or "%s|%s|%s" % (r["ticker"], r["strike"], r["expiry"]),
                 "id": r.get("id") or "%s|%s" % (r.get("option_chain"), r.get("created_at"))}
    except (KeyError, TypeError, ValueError):
        return None
    if lado == "mid":
        return None
    # relevancia: notional controlado / ADV$. Sin ADV del simbolo -> None, jamas un 0 plausible
    datos["notional"] = size * 100 * under if (size and under) else None
    base = (adv or {}).get(sym)
    datos["rel"] = (datos["notional"] / base) if (base and datos["notional"]) else None
    if datos["rel"] is None:
        datos["rel_motivo"] = "sin ADV de %s: relevancia no calculable" % sym
    elif datos["rel"] < MIN_REL_ADV:
        return None

    if prem >= MIN_PREM_GRANDE:
        return "premium %.1fM %s-side" % (prem / 1e6, lado), datos
    if voloi >= MIN_VOLOI and prem >= MIN_PREM_VOLOI:
        return "vol/OI %.1f (posicion nueva) $%.0fk" % (voloi, prem / 1e3), datos
    if sweep and prem >= MIN_PREM_SWEEP:
        return "SWEEP $%.0fk" % (prem / 1e3), datos
    return None


def respaldo(historial, sym, sesgo, chain, now):
    """Contratos DISTINTOS del mismo simbolo y sesgo dentro de la ventana. Una ballena sola
    no canta: 'whales that are not backed by other whales' se quedan en el banner."""
    vivos = [h for h in historial if now - h["ts"] <= RESPALDO_VENTANA_S]
    historial[:] = vivos
    return {h["chain"] for h in vivos
            if h["sym"] == sym and h["sesgo"] == sesgo and h["chain"] != chain}


def load_state():
    try:
        with open(STATE) as f:
            st = json.load(f)
        if isinstance(st, dict):
            return st
    except (OSError, ValueError):
        pass
    return {"vistos": {}, "contrato_ts": {}}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, separators=(",", ":"))
    os.replace(tmp, STATE)


# Sesgo del flujo (Yunior 2026-08-05: "UW notifications should say bearish or bullish").
# Doctrina de la casa: signed_premium = net_call - net_put -> VENDER UN PUT ES ALCISTA y
# VENDER UNA CALL es techo. El lado agresor (ask=compra, bid=venta) fija el signo.
_SESGO = {("CALLS", "ask"): ("BULLISH", "🟢", "compradas"),
          ("CALLS", "bid"): ("BEARISH", "🔴", "vendidas"),
          ("PUTS", "ask"): ("BEARISH", "🔴", "compradas"),
          ("PUTS", "bid"): ("BULLISH", "🟢", "vendidas")}


def _sesgo(cp, lado):
    """(sesgo, icono, verbo). Al mid NO se afirma direccion: se dice 'al mid' y sin sesgo."""
    return _SESGO.get((cp, lado), ("", "", "al mid"))


def prune(st, now):
    """El estado no crece sin techo: ids >6h y cooldowns vencidos fuera."""
    st["vistos"] = {k: v for k, v in st["vistos"].items() if now - v < 6 * 3600}
    st["contrato_ts"] = {k: v for k, v in st["contrato_ts"].items()
                         if now - v < COOLDOWN_CONTRATO_S}


def write_out(rows_cantadas, err=None):
    obj = {"asof": round(time.time(), 1)}
    if err is not None:
        obj["error"] = err          # sin `rows`: un error jamas fabrica filas
    else:
        obj["rows"] = rows_cantadas[-60:]
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, OUT)


def main():
    ap = argparse.ArgumentParser(description="alertas de flujo UW para la flota (descriptivo)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignora el portero de sesion (pruebas)")
    ap.add_argument("--dry-run", action="store_true", help="imprime, no empuja al embudo")
    a = ap.parse_args()

    tok = token()
    if not tok:
        sys.exit("uw_fleet_flow ROTO: sin UW_TOKEN")
    flota = fleet()
    st = load_state()
    adv = load_adv()
    historial = []            # candidatas recientes para el respaldo entre ballenas
    voz_sym = {}              # (sym, hora) -> pushes
    voz_sesion = [0, None]    # [contador, dia]
    cantadas = []
    fail_streak = 0
    print("uw_fleet_flow: %d syms de flota, poll %.0fs, dedup en %s | conviccion: rel>=%.2f%% "
          "del ADV$, respaldo %d contratos en %d min, voz <=%d/sym-hora y <=%d/sesion "
          "(ADV disponible para %d syms)"
          % (len(flota), POLL_S, os.path.relpath(STATE, REPO), MIN_REL_ADV * 100,
             RESPALDO_MIN_CONTRATOS, int(RESPALDO_VENTANA_S // 60), MAX_PUSH_SYM_HORA,
             MAX_PUSH_SESION, len(adv)))
    while True:
        if not a.force and not a.once and not in_session():
            time.sleep(60)
            continue
        rows, err = fetch(tok)
        now = time.time()
        if rows is None:
            fail_streak += 1
            print("uw_fleet_flow: %s (racha %d)" % (err, fail_streak), file=sys.stderr)
            if fail_streak >= 5:
                write_out([], err=err)
            if fail_streak == 5:
                notify_short.push("⚠ UW FLOW", "cinta de flota caida: %s" % str(err)[:80])
            if "401" in (err or ""):
                time.sleep(600)
        else:
            fail_streak = 0
            prune(st, now)
            pushes_este_min = 0
            for r in rows:
                if not isinstance(r, dict) or str(r.get("ticker", "")).upper() not in flota:
                    continue
                q = qualifies(r, adv)
                if q is None:
                    continue
                motivo, d = q
                if d["id"] in st["vistos"]:
                    continue
                st["vistos"][d["id"]] = now
                sesgo, icono, verbo = _sesgo(d["cp"], d["lado"])
                peers = respaldo(historial, d["sym"], sesgo, d["chain"], now)
                historial.append({"ts": now, "sym": d["sym"], "sesgo": sesgo, "chain": d["chain"]})
                fila = dict(d, motivo=motivo, ts=round(now, 1), sesgo=sesgo,
                            respaldo=len(peers) + 1)
                cantadas.append(fila)
                archiva_candidata(fila)
                en_cooldown = now - st["contrato_ts"].get(d["chain"], 0) < COOLDOWN_CONTRATO_S
                st["contrato_ts"][d["chain"]] = now
                titulo = "UW FLOW %s%s" % (d["sym"], (" %s %s" % (icono, sesgo)) if sesgo else "")
                rel_txt = ("%.2f%% del ADV" % (d["rel"] * 100)) if d.get("rel") else "relevancia n/d"
                cuerpo = "%s %s %g exp %s · %s · %d ballenas · %s" % (
                    d["cp"], verbo, d["strike"], d["exp"][5:], motivo, len(peers) + 1, rel_txt)
                # el presupuesto de voz se cuenta por SESION y por (sym,hora)
                dia = time.strftime("%Y-%m-%d")
                if voz_sesion[1] != dia:
                    voz_sesion[0], voz_sesion[1] = 0, dia
                    voz_sym.clear()
                clave_h = (d["sym"], time.strftime("%Y-%m-%d %H"))
                sin_respaldo = len(peers) + 1 < RESPALDO_MIN_CONTRATOS
                if a.dry_run:
                    print("[dry] %s | %s%s" % (titulo, cuerpo, "  (NO cantaria: %s)" % (
                        "cooldown" if en_cooldown else "sola, sin respaldo" if sin_respaldo else "")
                        if (en_cooldown or sin_respaldo) else ""))
                    continue
                freno = ("cooldown" if en_cooldown
                         else "sola: %d/%d ballenas" % (len(peers) + 1, RESPALDO_MIN_CONTRATOS)
                         if sin_respaldo
                         else "tope/min" if pushes_este_min >= MAX_PUSH_MIN
                         else "tope %d/sym-hora" % MAX_PUSH_SYM_HORA
                         if voz_sym.get(clave_h, 0) >= MAX_PUSH_SYM_HORA
                         else "presupuesto de sesion %d agotado" % MAX_PUSH_SESION
                         if voz_sesion[0] >= MAX_PUSH_SESION else None)
                if freno:
                    print("silencio (%s): %s | %s" % (freno, titulo, cuerpo))
                    continue
                voz_sym[clave_h] = voz_sym.get(clave_h, 0) + 1
                voz_sesion[0] += 1
                if pushes_este_min:
                    time.sleep(5.5)   # el rele descarta rafagas (cap 1/5s): espaciar salva la 2a y 3a
                pushes_este_min += 1
                notify_short.push(titulo, cuerpo)
                print("CANTADA %s | %s" % (titulo, cuerpo))
            if not a.dry_run:
                write_out(cantadas)
                save_state(st)
        if a.once:
            print("uw_fleet_flow --once: %d candidatas acumuladas" % len(cantadas))
            return 0 if rows is not None else 1
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
