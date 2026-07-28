#!/usr/bin/env python3
"""bollinger_alarm.py — vigia Bollinger INTRADIA de la flota (2026-07-22,
orden Yunior: "NVDA se paso de la bollinger arriba y reboto, no escuche
alarma — rectifica el sistema").

Cada 30s, toda la flota (data/fleet.txt), barras 1m del bridge:
  1) PIERCE: la vela revienta la banda BB(20,2) 1m (high>sup o low<inf).
  2) RE-ENTRADA: el cierre vuelve dentro -> SIRENA de rebote elastico
     ("espada": reversion corta, chica y segura) SALVO que el 5m tambien
     este reventado en la misma direccion -> entonces canta BAND-WALK
     (continuacion, NO hacer fade) — regla 1 de CLAUDE.md.
Anti crying-wolf: 1 canto por simbolo+lado cada 30 min; solo RTH 9:35-15:55.
SEÑAL-SOLAMENTE. Degradacion limpia por simbolo.
"""
import json, os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
# gate de spread: la cuenta vive en ./gate (gate_core.hpp). Alias porque la variable local
# de mas abajo ya se llama opt_veto.
from optgate import opt_vehicle, opt_veto as opt_veto_of
COOLDOWN_S = 1800

# Probabilidades MEDIDAS por backtest (docs/BACKTEST-BOLLINGER-2026-07.md).
# Fallback limpio: sin el .json el vigia se comporta exactamente como antes.
try:
    PROBS = json.load(open("data/bollinger_probs.json"))
except Exception:
    PROBS = {}

def prob_info(sym, typ):
    """-> (enabled, texto_prob). Sin datos medidos: enabled=True, texto=''."""
    d = PROBS.get(sym.upper(), {}).get(typ)
    if not isinstance(d, dict):
        return True, ""
    p, n = d.get("p_mid30"), d.get("n", 0)
    txt = f" prob medida {round(p * 100)} por ciento (n={n})." if p is not None else ""
    return bool(d.get("enabled", True)), txt

def log_only(title, msg):
    lt = time.localtime()
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")

def fleet():
    try:
        return [s.lower() for s in open("data/fleet.txt").read().split()]
    except Exception:
        return ["qqq", "spy", "nvda", "mu", "smh", "dram"]

VOICE_CORE = {"qqq", "spy", "nvda", "smh", "mu"}   # solo estos hablan; el resto banner+log

def say(title, msg, sound="ProAlert", voice=True, prio="INFO", voice_msg=None):
    # LECCION 12:29 (cola atascada 27 min, 155 mensajes): los elasticos NO
    # pueden inundar la cola de voz — hablan solo los core (prio INFO, ceden
    # el turno a DANGER/SIGNAL de ballenas y price_alarm) o los band-walks.
    # voice_msg: version corta (Yunior 2026-07-28 "sencillo, que un niño pequeño
    # pueda entender"); el banner/log conservan el `msg` tecnico completo.
    corto = voice_msg or msg
    if voice:
        subprocess.Popen(["/bin/bash", "scripts/speak.sh", prio, corto],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import notify_short; notify_short.push(title, corto)
    subprocess.Popen(["/usr/bin/osascript", "-e",
                      f'display notification "{corto}" with title "{title}" sound name "{sound}"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lt = time.localtime()
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading-signals")
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}.txt", "a") as f:
        f.write(f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d} | {title} | {msg}\n")

def bars_of(sym, n=140):
    try:
        rows = [l.split() for l in open(f"data/bars_{sym}_ibkr.txt").readlines()[-n:]]
        return [(int(float(r[0])), float(r[1]), float(r[2]), float(r[3]), float(r[4]))
                for r in rows if len(r) >= 6]
    except Exception:
        return []


# --- contexto de filtros MEDIDOS (estudio complementos 2026-07-22, data/bollinger_plus.json) ---
def bars_vol_of(sym, n=460):
    """como bars_of pero con volumen (para VWAP)."""
    try:
        rows = [l.split() for l in open(f"data/bars_{sym}_ibkr.txt").readlines()[-n:]]
        return [(int(float(r[0])), float(r[4]), float(r[5])) for r in rows if len(r) >= 6]
    except Exception:
        return []

def bb_context(sym, bars):
    """(tags, ok): etiquetas medidas del elastico y si mantiene la voz.
    Degradacion limpia: sin datos suficientes -> ("", True)."""
    try:
        closes = [c for *_, c in bars]
        if len(closes) < 60:
            return "", True
        # bandwidth pctile (ventana 125 como el estudio)
        bws = []
        for i in range(20, len(closes)):
            w = closes[i-20:i]
            m = sum(w)/20; sd = (sum((x-m)**2 for x in w)/20) ** .5
            bws.append(4*sd/m if m else 0)
        cur = bws[-1]; hist = bws[-126:-1]
        bw_pct = 100*sum(1 for b in hist if b <= cur)/len(hist) if len(hist) >= 40 else None
        # RSI(2) Wilder
        gains = losses = 0.0
        for i in range(-3, 0):
            d = closes[i] - closes[i-1]
            gains += max(d, 0); losses += max(-d, 0)
        rsi2 = 100.0 if losses == 0 else 100 - 100/(1 + gains/losses)
        # z-VWAP de la sesion (barras de hoy)
        vb = bars_vol_of(sym)
        day0 = time.time() - time.time() % 86400 + 9.5*3600
        sess = [(c, v) for t, c, v in vb if t >= day0 and v > 0]
        zv = None
        if len(sess) >= 30:
            tv = sum(v for c, v in sess)
            vwap = sum(c*v for c, v in sess)/tv
            var = sum(v*(c-vwap)**2 for c, v in sess)/tv
            zv = (closes[-1]-vwap)/(var ** .5) if var > 0 else None
        lt = time.localtime(); mins = lt.tm_hour*60 + lt.tm_min
        tags, ok = [], True
        squeeze = bw_pct is not None and bw_pct <= 20
        if 840 <= mins <= 930 and squeeze:
            tags.append("CELDA ESTRELLA tarde+squeeze, 85 por ciento medido")
        elif squeeze:
            tags.append("post-squeeze: el fade mejora +11 medido")
        if 585 <= mins < 630:
            tags.append("VETO apertura: peor hora del elastico, 58 por ciento"); ok = False
        if rsi2 is not None and (rsi2 < 10 or rsi2 > 90):
            tags.append("VETO RSI2 extremo: impulso en curso, 53 por ciento"); ok = False
        if zv is not None and abs(zv) >= 1.5:
            tags.append("VETO z-VWAP estirado: dia de tendencia, 55 por ciento"); ok = False
        return (" [" + "; ".join(tags) + "]" if tags else ""), ok
    except Exception:
        return "", True

def bb(closes):
    m = sum(closes) / len(closes)
    sd = (sum((c - m) ** 2 for c in closes) / len(closes)) ** .5
    return m - 2 * sd, m, m + 2 * sd

def agg_tf(bars, secs):
    out = {}
    for t, o, h, l, c in bars:
        k = t - t % secs
        if k not in out: out[k] = [o, h, l, c]
        else:
            out[k][1] = max(out[k][1], h); out[k][2] = min(out[k][2], l); out[k][3] = c
    return sorted(out.items())

def agg5(bars): return agg_tf(bars, 300)
def agg15(bars): return agg_tf(bars, 900)

state = {}    # sym -> {"up": epoch_pierce_activo, "dn": ..., "last_up": ts_canto, "last_dn": ts}
say("🎈 BOLLINGER VIGIA", "Vigia Bollinger intradia arriba: toda la flota, rebotes y band-walks")
while True:
    lt = time.localtime()
    hm = lt.tm_hour * 100 + lt.tm_min
    if hm >= 1555 or lt.tm_wday >= 5:
        break
    if hm < 935:
        time.sleep(30); continue
    now = time.time()
    for sym in fleet():
        bars = bars_of(sym)
        if len(bars) < 25 or now - bars[-1][0] > 240:
            continue
        st = state.setdefault(sym, {})
        closes = [c for *_, c in bars[-21:-1]]
        lo, mid, up = bb(closes)
        t, o, h, l, c = bars[-1]
        # 15m (el marco de Yunior en TradingView): pierce+re-entrada tambien canta
        A15 = agg15(bars_of(sym, 460))
        if len(A15) >= 21:
            cl15 = [v[3] for k, v in A15[-21:-1]]
            lo15, mid15, up15 = bb(cl15)
            h15, l15, c15 = A15[-1][1][1], A15[-1][1][2], A15[-1][1][3]
            for side15, pierced15, band15 in (("up15", h15 > up15, up15), ("dn15", l15 < lo15, lo15)):
                if pierced15:
                    back = c15 < band15 if side15 == "up15" else c15 > band15
                    if not back:
                        st[side15] = t
                    elif st.get(side15) and now - st.get(f"last_{side15}", 0) > COOLDOWN_S:
                        st[f"last_{side15}"] = now; st[side15] = None
                        lado = "ARRIBA" if side15 == "up15" else "ABAJO"
                        en15, pr15 = prob_info(sym, "re15")
                        msg15 = (f"{sym.upper()} reventó la banda 15 minutos {lado} "
                                 f"y re-entró en {c15:.2f} — elastico mayor, digestion probable.{pr15} {opt_vehicle(sym)}")
                        vlado = "bajar un poco" if side15 == "up15" else "subir un poco"
                        if en15:
                            say("🎈 BB 15m RE-ENTRADA", msg15, voice=sym in VOICE_CORE, prio="SIGNAL",
                                voice_msg=f"{sym} puede {vlado}.")
                        else:
                            log_only("🎈 BB 15m RE-ENTRADA [MUTED p<55]", msg15)
                elif st.get(side15) and (now - st[side15]) > 2700:
                    st[side15] = None
        # 5m para distinguir band-walk de rebote
        A5 = agg5(bars)
        walk_up = walk_dn = False
        if len(A5) >= 21:
            cl5 = [v[3] for k, v in A5[-21:-1]]
            lo5, _, up5 = bb(cl5)
            walk_up = A5[-1][1][3] > up5
            walk_dn = A5[-1][1][3] < lo5
        # deteccion por lado
        for side, pierced, band, walk in (("up", h > up, up, walk_up), ("dn", l < lo, lo, walk_dn)):
            if pierced and c is not None:
                back_inside = c < band if side == "up" else c > band
                if not back_inside:
                    st[side] = t                     # pierce activo, aun fuera
                elif st.get(side) and now - st.get(f"last_{side}", 0) > COOLDOWN_S:
                    st[f"last_{side}"] = now
                    st[side] = None
                    lado = "ARRIBA" if side == "up" else "ABAJO"
                    veh = opt_vehicle(sym)
                    # GATE DE VERDAD, no anotacion (fix 2026-07-25). opt_vehicle() solo
                    # PEGABA un texto al mensaje: la señal sonaba igual con "OPCIONES
                    # VETADAS" enterrado dentro. Medido el 24-jul (docs/SIGNALS-REAL-OPTION):
                    # el 75% de las señales apuntaban a contratos INOPERABLES (spread mediano
                    # 9.1%, tope doctrinal 5%), y las que NO pasan el gate rindieron -19.6%
                    # con -9.8%/trade en la opcion real. Seis simbolos no tienen NI UN
                    # contrato operable (ASML 115.8% de spread mediano, SMH 34.5%, LRCX,
                    # WDC, TXN, STX). Si el vehiculo esta vetado, la señal NO grita: baja a
                    # INFO. Sigue emitiendose —vale para acciones/ETF, que es lo que dice el
                    # propio texto— pero deja de competir por la voz con las operables.
                    # TRES ESTADOS, no dos: opt_ok() devuelve False tanto si el spread es
                    # malo como si NO HAY CADENA — usarlo tal cual silenciaria la flota
                    # entera un lunes antes del primer refresco, o si muere el daemon de
                    # cadenas. Solo callamos cuando SABEMOS que el spread es malo; ante
                    # ignorancia, la señal grita (fail-open, no fail-silent).
                    # el umbral NO se compara aqui: optgate.opt_veto() devuelve el veredicto
                    # del binario ./gate (gate_core.hpp), unica frontera del 5% del sistema.
                    opt_veto = opt_veto_of(sym)
                    if walk:
                        enw, prw = prob_info(sym, "bandwalk")
                        msgw = (f"{sym.upper()} camina la banda {lado} tambien en 5 minutos "
                                f"({c:.2f}). Continuacion probable — NO hacer fade.{prw} {veh}")
                        vdir = "subiendo" if lado == "ARRIBA" else "bajando"
                        if enw:
                            say("🎈 BB BAND-WALK" + (" [opt-vetada]" if opt_veto else ""), msgw,
                                "ProChord", voice=not opt_veto, prio="INFO" if opt_veto else "SIGNAL",
                                voice_msg=f"{sym} sigue {vdir} fuerte.")
                        else:
                            log_only("🎈 BB BAND-WALK [MUTED p<55]", msgw)
                    else:
                        rev = "reversion corta hacia la media" if side == "up" else "rebote hacia la media"
                        vrebote = "bajar un poco" if side == "up" else "subir un poco"
                        ene, pre = prob_info(sym, "elastic")
                        ctx, ctx_ok = bb_context(sym, bars)
                        msge = (f"{sym.upper()} reventó la banda {lado} y re-entró en {c:.2f}. "
                                f"Elastico: {rev} {mid:.2f} si imprime — chico y seguro.{pre}{ctx} {veh}")
                        if ene and ctx_ok:
                            # DEGRADADA 2026-07-25 por MEDICION, no por corazonada.
                            # Backtest del 2026-07-24 (docs/BACKTEST-SIGNALS-2026-07-24.md):
                            # BB REBOTE ⭐ = 20% WR [8,42] con n=20 — la UNICA celda cuyo
                            # Wilson SUPERIOR queda por debajo de 50%, y encima tenia voz
                            # garantizada + prioridad SIGNAL. La ⭐ sin estrella (REBOTE
                            # normal) dio 45% y la VETADA 53%: la "estrella" era la peor.
                            # Se SIGUE emitiendo (n=20 es poco y hay que seguir midiendo),
                            # pero pierde el privilegio de voz: pasa a INFO como el resto.
                            # RE-PROMOVER solo si la calibracion medida la devuelve >55%.
                            estrella = "CELDA ESTRELLA" in ctx
                            say("🎈 BB REBOTE" + (" ⭐[degradada]" if estrella else ""), msge,
                                voice=(sym in VOICE_CORE),
                                prio="INFO",
                                voice_msg=f"{sym} puede {vrebote}.")
                        elif ene:
                            log_only("🎈 BB REBOTE [VETO medido]", msge)
                        else:
                            log_only("🎈 BB REBOTE [MUTED p<55]", msge)
            elif st.get(side) and (now - st[side]) > 600:
                st[side] = None                      # pierce viejo sin re-entrada: expira
    time.sleep(30)
say("🎈 BOLLINGER VIGIA", "15:55 — vigia Bollinger fuera hasta mañana")
