#!/usr/bin/env python3
"""discord_layout.py — FUENTE UNICA de la estructura del servidor y del enrutado.

La leen discord_setup.py (crea/actualiza el servidor), discord_webhooks.py (un webhook por
canal automatico) y discord_router.py (a que canal va cada alerta). Un solo sitio que tocar.

Cada canal de alerta tiene un PRODUCTOR REAL verificado en el repo — nada de canales muertos.
Las reglas de enrutado salen de la taxonomia MEDIDA de data/notify_push.txt (676 lineas,
2026-08-04): los titulos son los que de verdad emiten los 19 llamadores de notify_short.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- severidad -------------------------------------------------------------------------
CRITICA = "critica"
NORMAL = "normal"
SISTEMA = "sistema"

SEV_COLOR = {CRITICA: 0xE53935, NORMAL: 0x2E7D32, SISTEMA: 0x616161}
BAJISTA_COLOR = 0xC62828
ALCISTA_COLOR = 0x2E7D32
NEUTRO_COLOR = 0x1565C0

# --- estructura del servidor ------------------------------------------------------------
# (clave, nombre visible, topic, privado)
CATEGORIES = [
    ("empieza-aqui", "📍 EMPIEZA AQUÍ", [
        ("bienvenida", "Qué es esta sala de guerra y cómo se lee", False),
        ("guia-alertas", "Qué significa cada alerta y a qué canal va (autogenerada)", False),
        ("estado-flota", "Salud de la flota: procesos vivos, ventana horaria, proveedor", False),
    ]),
    ("alertas-vivo", "🚨 ALERTAS EN VIVO", [
        ("criticas", "🚨 DANGER · TERREMOTO · STOP · order_engine. Solo lo que exige acción YA", False),
        ("senales-flota", "Bollinger, apertura fuera de banda, compass y los 21 signal bots", False),
        ("opciones-contratos", "📅 CONTRATO OPERABLE: strike, vencimiento, límite, spread, OI y "
                              "presupuesto ≤$200. Veredicto GO / CAUTION / NO-GO. Señal-solamente", False),
        ("ballenas-flujo", "🐋 opt_whale_watch + 🚀 spikes de premium + flujo agresor", False),
        ("flujo-uw", "Unusual Whales: flujo avanzado, net premium, sweeps", False),
        ("manada", "🐺 fleet_consensus: ≥3 tickers de la flota alineados", False),
        ("confluencia", "🔗 Dos motores de acuerdo a la vez (flujo + Bollinger). Lo más selectivo", False),
        ("capitanes", "🎖 Regla 12: SPY/QQQ mandan en el mercado, SMH en semis. El capitán anula al nombre", False),
        ("gamma-niveles", "Muros de OI, gamma flip, GEX, imanes y pines", False),
        ("dark-pool", "DESCRIPTIVO — dark pool no es señal (killlist #3). Contexto, nunca gatillo", False),
        ("finviz-screeners", "Buffett · Short Squeeze · Momentum Breakout", False),
        ("corea-overnight", "🇰🇷 KOSPI / Samsung / SK-Hynix — lidera semis ~13 h", False),
        ("earnings-catalizadores", "Earnings, vencimientos que expiran hoy, catalizadores", False),
    ]),
    ("watchlists", "👁️ WATCHLISTS", [
        ("spy-qqq", "Espejo de toda alerta que toque SPY o QQQ (capitanes del mercado)", False),
        ("semis-memoria", "Espejo: SMH NVDA MU AMD TSM ASML SKHY DRAM SNDK WDC STX LRCX", False),
        ("mis-posiciones", "Espejo de los símbolos con posición abierta", False),
    ]),
    ("analisis", "📊 ANÁLISIS", [
        ("planes-premarket", "Planes diarios por ticker (PDF): mapa, escenarios, plan pícaro", False),
        ("arboles-escenarios", "Árboles de horizonte: mañana / viernes / 2 semanas", False),
        ("estrategias", "Estrategias y fichas de orden preparadas la víspera", False),
        ("posicionamiento-dealer", "Régimen gamma, exposición del dealer, GEX por vencimiento", False),
        ("cierre-recap", "Post-mortem del día: qué disparó, qué acertó, qué falló", False),
        ("calendario-economico", "Macro, earnings de la flota, vencimientos", False),
    ]),
    ("sistema", "⚙️ SISTEMA", [
        ("estado-proveedores", "Intrinio/Finnhub/Polygon/IBKR: sockets, cintas ciegas, latencia", True),
        ("senales-rechazadas", "Lo que el filtro descartó — aquí se audita el ruido", True),
        ("backtests", "Informes de backtest y calibración", True),
        ("latencia", "Medidas de latencia por fuente", True),
        ("bot-logs", "Diagnóstico del propio relé de Discord", True),
        ("sin-clasificar", "Alertas que ninguna regla reconoció. Si esto crece, falta una regla", True),
        ("desarrollo", "Trabajo en curso", True),
    ]),
]

# rol -> (color, mencionable, motivo)
ROLES = [
    ("Admin", 0xE67E22, False, "gestiona canales y roles"),
    ("Trader", 0x3498DB, False, "lee todo lo operativo"),
    ("Alertas Premium", 0x9B59B6, True, "se le menciona en las críticas"),
    ("Bot Alertas", 0x1ABC9C, False, "el bot publicador"),
    ("Muted", 0x95A5A6, False, "sin voz"),
]

MENTION_ROLE = "Alertas Premium"          # el unico rol que se menciona, y solo en criticas

# --- enrutado --------------------------------------------------------------------------
# (regex sobre la LINEA COMPLETA, canal, severidad). Primera que casa, gana: el orden importa.
RULES = [
    # sistema primero: 168 de 676 lineas medidas el 2026-08-04 eran infraestructura, no senal
    (r"INTRINIO WS|FINNHUB WS|PROVIDER|PROVEEDOR|socket", "estado-proveedores", SISTEMA),
    (r"🕳|CINTA CIEGA|SIN GATEWAY|BRIDGE CIEGO|feed muerto", "estado-proveedores", SISTEMA),
    (r"LATENCIA|latency", "latencia", SISTEMA),

    # criticas: exigen accion ya
    (r"🚨|🌋|DANGER|TERREMOTO|CAPITULACI", "criticas", CRITICA),
    # STOP solo en MAYUSCULAS: "MU: SELL (STOP)" y "STOP tocado" son criticos, pero el
    # "stop 211" minuscula de una ficha ("compra 212.5 stop 211") es un precio, no un evento.
    (r"\b(?-i:STOP)\b|order_engine|ORDEN ENVIADA|FILL\b", "criticas", CRITICA),
    (r"ALARMA PRECIO", "criticas", CRITICA),          # price_alarm.cpp:260 — el PRINT
    (r"🛑|SCALPER", "criticas", CRITICA),             # scalper_core.h:600-712

    # confluencia y capitanes ANTES que lo generico: "🔗 FLUJO + BB QQQ" lleva "BB" dentro
    # y caeria en senales-flota. Son las dos senales mas selectivas que emite la casa.
    (r"🔗|FLUJO \+ BB|CONFLUENCIA", "confluencia", NORMAL),
    # El veto/read-through COREANO va antes que capitanes: su cuerpo suele nombrar al capitan
    # ("🔪 VETO | capitan coreano en contra") y sin este orden se lo llevaria #capitanes.
    (r"🔪 VETO|READ-?THROUGH|KORU|V ROTA", "corea-overnight", NORMAL),
    (r"🎖|CAPITAN|CAPITÁN", "capitanes", NORMAL),

    # La ficha RECHAZADA va antes que la operable: un NO-GO no es una idea, es una idea MUERTA,
    # y meterla en el canal de contratos lo llena de cosas que no se pueden ejecutar (Spartan
    # publica 11 ideas de opciones al dia, no 11 vetos). Se archiva para poder auditar el veto.
    (r"\bNO-GO\b|OPCIONES VETADAS|OPCIONES s/d|sin cadena — no puedo armar ficha|"
     r"sin bid/ask válido|sin \w+s 0DTE", "senales-rechazadas", SISTEMA),

    # CONTRATO operable antes que el flujo: es lo unico que se puede ejecutar, no contexto.
    # Referencia Spartan Trading, que separa 📅options-ideas de 📈equity-ideas (Yunior 2026-08-04:
    # "make sure we have options alerts separately"). Anclado en los strings EXACTOS que emiten
    # order_ticket.py:129 (veredicto+icono) y optgate.py:106-109 (gate de spread de la regla 4);
    # sin la ficha delante, `🐋 BALLENA CALLS` se llevaria estas por el "CALLS".
    (r"OPCIONES OK|\bCAUTION\b|\bGO\b 0DTE|0DTE @", "opciones-contratos", NORMAL),

    # flujo de opciones
    (r"🐋|BALLENA", "ballenas-flujo", NORMAL),
    (r"🚀 SPIKE|FLUJO AGRESOR|SWEEP|BARRIDO", "ballenas-flujo", NORMAL),
    (r"\bUW\b|UNUSUAL WHALES|NET PREM", "flujo-uw", NORMAL),
    (r"DARK ?POOL", "dark-pool", SISTEMA),

    # manada
    (r"🐺|🐘|MANADA|CONSENSO", "manada", NORMAL),

    # estructura de opciones. X-RAY/RETEST_REJECT/BOUNCE: eventos de NIVEL de qqq_xray.cpp:205 y
    # today_alarm5 — ya empujaban al embudo y caian en #sin-clasificar (auditoria 2026-08-04 R8).
    (r"MURO|WALL|GAMMA FLIP|\bGEX\b|IMAN|IMÁN|\bPIN\b|MAX ?PAIN", "gamma-niveles", NORMAL),
    (r"X-?RAY|RETEST_REJECT|\bBOUNCE\b", "gamma-niveles", NORMAL),

    # screeners (+ R4: screener/state.py:56 y alert_bot.py:39)
    (r"FINVIZ", "finviz-screeners", NORMAL),
    (r"TA BUY|BUY-CONSIDER|BARGAIN", "finviz-screeners", NORMAL),

    # corea (R3 vive arriba, antes de capitanes)
    (r"🇰🇷|KOSPI|KRX|SAMSUNG|SK-?HYNIX|KODEX", "corea-overnight", NORMAL),

    # catalizadores
    (r"⏰|EXPIRA HOY|EARNINGS|RESULTADOS", "earnings-catalizadores", NORMAL),

    # senales de la flota (lo mas generico, al final)
    # R1: los 21 bots C++ ("QQQ: BUY ...", "MU: SELL ..."). Va DESPUES de \bSTOP\b para que
    # "(STOP)" siga siendo critica. R8: dram_guard/memoria-confluencia ya empujaban al embudo.
    (r"^[A-Z0-9]{1,6}: (BUY|SELL)|\bCOMPRAR\b|\bVENDER\b", "senales-flota", NORMAL),
    (r"MEMORIA CONFLUENCIA|DRAM GUARD", "senales-flota", NORMAL),
    (r"🎈|BOLLINGER|BB REBOTE|BB BAND-WALK|%B", "senales-flota", NORMAL),
    (r"🎯|FUERA DE BANDA|RE-ENTRADA|BRUJULA|BRÚJULA|COMPASS|DIP\b", "senales-flota", NORMAL),

    # R7: telemetria de los posters y el healthcheck — sistema, jamas canal de alerta
    (r"^X (POSTED|BUDGET|AUTH FAIL|WHALE BOT)", "bot-logs", SISTEMA),
    (r"🩺|HEALTHCHECK", "estado-flota", SISTEMA),
]

FALLBACK_CHANNEL = "sin-clasificar"       # jamas se descarta una alerta en silencio

# --- PRIVACIDAD (Yunior 2026-08-04: "dont reveal personal info on our personal trades via
# notifications, only via local notification in mac") ------------------------------------
# Lo que describe NUESTRAS operaciones (ordenes, fills, P&L, posiciones, cuenta) se queda en
# el Mac: banner osascript + voz local. Los reles EXTERNOS (ntfy, Resend, Discord) lo saltan.
# OJO: "posicion nueva" del flujo UW es dato de MERCADO (vol/OI del vendor), no nuestro.
PRIVADO = re.compile(
    r"order_engine|ORDEN (ENVIADA|RECHAZADA|LIMITE)|\bFILL\b|realizedPnl|EXPIRA HOY|"
    r"POSICIONES? (ABIERTA|CERRADA|DESCONOCIDAS)|\bU\d{8}\b|comisi[oó]n|ARM_LIVE|CERRAR ",
    re.IGNORECASE)


def is_private(line):
    """True si la linea habla de NUESTRAS operaciones y no puede salir del Mac."""
    return bool(PRIVADO.search(line or ""))

# espejos por simbolo: (canal, conjunto de simbolos)
SPY_QQQ = ("SPY", "QQQ", "SPX", "XSP", "NDX", "DIA", "IWM")
SEMIS = ("SMH", "NVDA", "MU", "AMD", "TSM", "ASML", "SKHY", "DRAM", "SNDK",
         "WDC", "STX", "LRCX", "INTC", "AVGO", "TXN", "QCOM", "XLK")
MIRRORS = [("spy-qqq", SPY_QQQ), ("semis-memoria", SEMIS)]

# canales que reciben alertas automaticas -> necesitan webhook
def alert_channels():
    """Canales a los que el relé publica: destinos de RULES + fallback + espejos."""
    keys = set(ch for _, ch, _ in RULES)
    keys.add(FALLBACK_CHANNEL)
    keys.update(ch for ch, _ in MIRRORS)
    keys.add("mis-posiciones")
    return keys


def analysis_channels():
    """Canales de ANÁLISIS + los estáticos: publican planes, árboles, informes."""
    return {"planes-premarket", "arboles-escenarios", "estrategias",
            "posicionamiento-dealer", "cierre-recap", "calendario-economico",
            "backtests", "estado-flota", "guia-alertas", "bienvenida", "bot-logs",
            "senales-rechazadas"}


def webhook_channels():
    return alert_channels() | analysis_channels()


def all_channel_keys():
    return [ch for _, _, chans in CATEGORIES for ch, _, _ in chans]


IDS = os.path.join(REPO, "data", "discord_channels.json")


def load_ids(path=None):
    """{clave: id_de_canal} cacheado. {} si aun no existe (primer arranque)."""
    import json
    try:
        with open(path or IDS) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def save_ids(ids, path=None):
    """Escritura atomica. Esto NO es un secreto: son ids publicos del servidor."""
    import json
    p = path or IDS
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ids, f, indent=1, sort_keys=True)
    os.replace(tmp, p)


def resolve(key, chans, ids=None, ctype=0):
    """Canal por ID cacheado primero, por nombre despues.

    Casar solo por nombre visible es fragil: el dia que un canal se renombre (a mano o al
    pasar a ingles) el setup no lo reconoceria, crearia uno NUEVO vacio, dejaria el viejo
    huerfano con todo el historial, y el webhook guardado seguiria publicando en el viejo.
    El id no cambia nunca; el nombre si.
    """
    ids = load_ids() if ids is None else ids
    cid = ids.get(key)
    if cid:
        for c in chans:
            if c.get("id") == cid:
                return c
    for c in chans:
        if c.get("name") == key and c.get("type") == ctype:
            return c
    return None


def channel_meta(key):
    """(categoria_key, nombre, topic, privado) o None si la clave no existe."""
    for cat_key, _, chans in CATEGORIES:
        for ch, topic, priv in chans:
            if ch == key:
                return cat_key, ch, topic, priv
    return None


_COMPILED = [(re.compile(pat, re.IGNORECASE), ch, sev) for pat, ch, sev in RULES]


def classify(line):
    """(canal, severidad) para una linea de notify_push.txt. Nunca None: el fallback es un canal."""
    for rx, ch, sev in _COMPILED:
        if rx.search(line):
            return ch, sev
    return FALLBACK_CHANNEL, SISTEMA


def fleet_symbols():
    """Simbolos de data/fleet.txt. Levanta si el fichero falta: sin universo no hay espejo."""
    path = os.path.join(REPO, "data", "fleet.txt")
    with open(path) as f:
        syms = [s.strip().upper() for s in f.read().split() if s.strip()]
    if not syms:
        raise RuntimeError("data/fleet.txt vacio")
    return syms


def symbols_in(line, universe=None):
    """Simbolos del universo presentes en la linea, como palabra suelta (case-insensitive)."""
    uni = universe if universe is not None else set(fleet_symbols()) | set(SPY_QQQ) | set(SEMIS)
    found = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9.\-]{0,6}", line):
        up = tok.upper()
        if up in uni and up not in found:
            found.append(up)
    return found


def mirror_channels(line, universe=None):
    """Canales-espejo que corresponden a los simbolos de la linea (sin duplicar)."""
    syms = set(symbols_in(line, universe))
    return [ch for ch, group in MIRRORS if syms & set(group)]
