#!/usr/bin/env python3
"""fleet_news_watch.py — noticias de los 30 simbolos de data/fleet.txt a Discord (#noticias-flota).

Orden de Yunior (2026-08-05): "add news for all fleet in discord, but make sure they dont get
repeated, no need to store them more than 24 h".

DOS DECISIONES DE ARQUITECTURA, las dos medidas:
1. Publica DIRECTO por webhook, NO por el embudo data/notify_push.txt. El embudo tiene cap
   1/5 s y ley de frescura 45 s (discord_relay.py:39-42): una tanda de 20 titulares se perderia
   casi entera — es exactamente lo que le pasa hoy a asia_semis_watch. Ademas el embudo dispara
   ntfy + email + voz, y una noticia no es una alarma.
2. Un mensaje por corrida con un embed por simbolo (Discord admite 10 embeds/mensaje), no un
   mensaje por titular: 30 simbolos caben en 3 POST en vez de 60.

Lote FUERA del camino de senal (regla PYTHON ES PELIGROSO): mueve bytes de RSS/REST a Discord.
Cero computo de senal. Fail-loud: la fuente que falla se DICE y no aporta; jamas un cero plausible.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import discord_client as dc          # noqa: E402  (solo secret(): lee config/feeds.env)
import discord_layout as L           # noqa: E402
import discord_send as S             # noqa: E402
import discord_webhooks as W         # noqa: E402
import news_store as NS              # noqa: E402

CANAL = "noticias-flota"
LOG = os.path.join(REPO, "logs", "fleet_news.log")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ib-trader-news/1.0"
TIMEOUT_S = 15
MAX_POR_SIMBOLO = 3          # por corrida: es un canal informativo, no una manguera
MAX_EMBEDS_MSG = 10          # tope de Discord
VENTANA_H = 3                # titular mas viejo que esto no se publica aunque sea nuevo para el store

# --- ruido: publishers de contenido autogenerado (medido 2026-08-05) --------------------
PUB_NEGRO = {"chartmill", "tradingkey", "simply wall st", "zacks", "marketbeat",
             "investorplace", "stocktwits", "insider monkey", "gurufocus", "24/7 wall st",
             "the globe and mail", "benzinga insights", "investing.com studio"}
# titulares plantilla: los rellena un robot con el ticker del dia y no dicen NADA.
# Cada patron sale de un titular REAL del corpus medido el 2026-08-05 (365 titulares
# finnhub+gnews, ventana 6 h): ese dia el 42% de lo que pasaba el primer filtro era esto.
TITULO_NEGRO = re.compile(
    r"top (movers|gainers|losers)|biggest (stock )?movers|what (investors|you) need to know|"
    r"moved (up|down) by|stocks? to watch|here'?s (why|how|what)|\b\d+ (reasons|things|stocks|words)\b|"
    r"should you (buy|sell|invest)|is (it|now) (finally )?(time|worth) (to )?(buy|invest)|"
    r"(daily|weekly|monthly) (review|recap|wrap)|shares (up|down) [\d.]+%$|"
    r"trading (higher|lower) (today|wednesday|tuesday|monday|thursday|friday)|"
    r"(pre-?market|after-?hours) (movers|gainers|losers)|options? alert|unusual options|"
    r"if you invested \$?[\d,]+|prediction:|could be worth|how much it'?d be worth|"
    r"outperforming (other|its)|which .{0,30}(stock|etf) is a better|which is the better|"
    r"\bvs\.?\s+[\w.\- ]{2,25}:\s|best .{0,30}stocks? (to buy|for)|top .{0,25}stocks \d{4}|"
    r"portfolio (activity|update)|\bq[1-4] \d{4} (portfolio|commentary|letter)|"
    r"(strategy|fund) q[1-4]|zacks (rank|analyst blog)|\bmotley fool\b|"
    r"(is|are) .{0,40}\b(a|the) (buy|sell)\b|could .{0,45}(be|become) the (most|biggest)|"
    r"stock (looks|is) ready for|based on wall street'?s|analyst (estimates|ratings) (say|suggest)|"
    r"overtook the \d+-day|moving average\b.*\b(cross|overtook)|will .{0,40}go up/?down|"
    r"live polymarket|securities fraud (class action|lawsuit)|lead plaintiff|"
    r"investors who lost|deadline:.{0,30}investors|\bclass action\b",
    re.IGNORECASE)

# --- relevancia: el titular tiene que hablar DEL simbolo ----------------------------------
# Medido 2026-08-05: Finnhub etiqueta con `related` notas donde el nombre solo sale de pasada
# ("Zoox to start charging for robotaxi rides" -> AMZN; "Who Might Buy Snap" -> META). Sin este
# filtro el canal se llena de wire genérico. Alias = como lo escribe la prensa, no el ticker.
ALIAS = {
    "QQQ": ("invesco qqq", "nasdaq 100", "nasdaq-100"), "SPY": ("s&p 500", "spdr s&p"),
    "NVDA": ("nvidia",), "TSLA": ("tesla",), "MU": ("micron",),
    "SMH": ("vaneck semiconductor", "semiconductor etf"), "AMD": ("advanced micro",),
    "AAPL": ("apple",), "MSFT": ("microsoft", "azure"), "META": ("meta ", "facebook", "instagram",
    "zuckerberg"), "AMZN": ("amazon",), "GOOGL": ("google", "alphabet", "gemini"),
    "INTC": ("intel",), "TSM": ("tsmc", "taiwan semiconductor"), "ASML": ("asml",),
    "TXN": ("texas instruments",), "QCOM": ("qualcomm",), "AVGO": ("broadcom",),
    "NFLX": ("netflix",), "NOK": ("nokia",), "GLD": ("gold ", "bullion"),
    "XLK": ("technology select", "tech sector etf"), "EWY": ("korea etf", "msci korea", "kospi"),
    "DRAM": ("dram",), "SPCX": ("spacex", "starship", "starlink"),
    "SKHY": ("sk hynix", "sk-hynix"), "LRCX": ("lam research",), "SNDK": ("sandisk",),
    "WDC": ("western digital",), "STX": ("seagate",), "HOOD": ("robinhood",),
    "PLTR": ("palantir",), "MSTR": ("microstrategy", "strategy inc"), "COIN": ("coinbase",),
    "CRWV": ("coreweave",), "RKLB": ("rocket lab",),
}
MAX_TICKERS_TAG = 4      # una nota etiquetada con 5+ tickers es un repaso de mercado, no una noticia


def es_relevante(item):
    """True si el titular habla del simbolo: ticker suelto, alias de prensa, o etiqueta estrecha.

    El ticker se busca en MAYUSCULAS a proposito: "COIN" es Coinbase, "Coin Stock" era spam de
    criptobasura; "GLD" es el ETF, "gld" no existe. Los alias si van sin distinguir mayusculas.
    """
    sym = (item.get("sym") or "").upper()
    title = item.get("title") or ""
    if re.search(r"\b%s\b" % re.escape(sym), title):
        return True
    for a in ALIAS.get(sym, ()):
        if a in title.lower():
            return True
    tk = item.get("tickers") or []
    return 0 < len(tk) <= MAX_TICKERS_TAG and sym in [t.upper() for t in tk]


# catalizador real: lo que de verdad mueve un precio
CATALIZADOR = re.compile(
    r"\bearnings\b|\bguidance\b|\bupgrade[sd]?\b|\bdowngrade[sd]?\b|\bhalt(ed)?\b|\bSEC\b|"
    r"\bsubpoena\b|\blawsuit\b|\brecall\b|\bFDA\b|\bacquisition\b|\bacquires?\b|\bmerger\b|"
    r"\bbuyback\b|\bdividend\b|\bsplit\b|\blayoffs?\b|\bCEO\b|\bCFO\b|\bresign\b|\bexport "
    r"control\b|\btariff\b|\bsanction\b|\bcontract\b|\bdeal\b|\bpartnership\b|\binvestigation\b|"
    r"\bbankrupt\b|\boutage\b|\brevenue\b|\bforecast\b|\bwarns?\b|\bbeats?\b|\bmisses\b",
    re.IGNORECASE)


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), dc.redact(str(msg))))
    except OSError:
        pass


def fleet():
    """Los 30 de data/fleet.txt. Levanta si falta: sin universo no hay noticias que buscar."""
    with open(os.path.join(REPO, "data", "fleet.txt")) as f:
        syms = [s.strip().upper() for s in f.read().split() if s.strip()]
    if not syms:
        raise RuntimeError("data/fleet.txt vacio")
    return syms


def _get(url, headers=None, timeout=TIMEOUT_S):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_json(url, headers=None):
    return json.loads(_get(url, headers).decode("utf-8", "replace"))


# --- fuentes ----------------------------------------------------------------------------
# Cada fuente devuelve [{sym,title,url,source,ts}] o levanta. Nunca devuelve [] fingiendo exito.

def src_polygon(syms, key, ventana_s):
    """Polygon /v2/reference/news: trae `tickers` (multi-simbolo) y publisher. 1 req/simbolo."""
    ahora = time.time()
    out = []
    for sym in syms:
        url = ("https://api.polygon.io/v2/reference/news?ticker=%s&order=desc&limit=10&apiKey=%s"
               % (urllib.parse.quote(sym), key))
        try:
            d = _get_json(url)
        except Exception as e:
            log("polygon %s FALLO: %s" % (sym, e.__class__.__name__))
            continue
        for it in (d.get("results") or []):
            ts = _iso_ts(it.get("published_utc"))
            if ts is None or ahora - ts > ventana_s:
                continue
            out.append({"sym": sym, "title": (it.get("title") or "").strip(),
                        "url": it.get("article_url"), "ts": ts,
                        "source": (it.get("publisher") or {}).get("name") or "Polygon",
                        "tickers": it.get("tickers") or [sym]})
    return out


def src_alpaca(syms, cred, ventana_s):
    """Alpaca /v1beta1/news: hasta 50 simbolos en UNA peticion, fuente Benzinga, tiempo real.

    cred = (key_id, secret). Alpaca se purgo del repo el 2026-07-15 ("no alpaca all over") como
    fuente de PRECIO; esto es solo el feed de titulares (Yunior 2026-08-05 "try alpaca for news
    too"). Sin claves no se inventa nada: recolectar() lo marca "sin credencial".
    """
    ahora = time.time()
    kid, sec = cred
    out = []
    for i in range(0, len(syms), 50):
        lote = syms[i:i + 50]
        url = ("https://data.alpaca.markets/v1beta1/news?symbols=%s&limit=50&sort=desc"
               % urllib.parse.quote(",".join(lote)))
        d = _get_json(url, {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec,
                            "Accept": "application/json"})
        for it in (d.get("news") or []):
            ts = _iso_ts(it.get("created_at"))
            title = (it.get("headline") or "").strip()
            if ts is None or ahora - ts > ventana_s or not title:
                continue
            tk = [t.strip().upper() for t in (it.get("symbols") or []) if t]
            for sym in [t for t in tk if t in set(lote)] or []:
                out.append({"sym": sym, "title": title, "url": it.get("url"), "ts": ts,
                            "source": it.get("source") or "Alpaca", "tickers": tk})
    return out


def src_finnhub(syms, key, ventana_s):
    """Finnhub company-news: 1 req/simbolo, rango de fechas obligatorio."""
    ahora = time.time()
    hoy = time.strftime("%Y-%m-%d")
    ayer = time.strftime("%Y-%m-%d", time.localtime(ahora - 86400))
    out = []
    for sym in syms:
        url = ("https://finnhub.io/api/v1/company-news?symbol=%s&from=%s&to=%s&token=%s"
               % (urllib.parse.quote(sym), ayer, hoy, key))
        try:
            d = _get_json(url)
        except Exception as e:
            log("finnhub %s FALLO: %s" % (sym, e.__class__.__name__))
            continue
        for it in (d if isinstance(d, list) else [])[:20]:
            ts = it.get("datetime")
            if not isinstance(ts, (int, float)) or ahora - ts > ventana_s:
                continue
            out.append({"sym": sym, "title": (it.get("headline") or "").strip(),
                        "url": it.get("url"), "ts": float(ts),
                        "source": it.get("source") or "Finnhub",
                        "tickers": [t.strip().upper() for t in
                                    (it.get("related") or sym).split(",") if t.strip()]})
    return out


def src_uw(syms, token, ventana_s):
    """UW /news/headlines: UNA peticion para todo el mercado; trae sentiment e is_major."""
    ahora = time.time()
    universo = set(syms)
    d = _get_json("https://api.unusualwhales.com/api/news/headlines?limit=100",
                  {"Authorization": "Bearer " + token, "Accept": "application/json"})
    out = []
    for it in (d.get("data") or []):
        ts = _iso_ts(it.get("created_at"))
        title = (it.get("headline") or "").strip()
        if ts is None or ahora - ts > ventana_s or not title:
            continue
        tk = [t.strip().upper() for t in (it.get("tickers") or []) if t]
        hit = [t for t in tk if t in universo]
        if not hit:
            hit = [s for s in universo if re.search(r"\b%s\b" % re.escape(s), title)]
        for sym in hit:
            out.append({"sym": sym, "title": title, "url": it.get("url"), "ts": ts,
                        "source": it.get("source") or "UW", "tickers": tk or [sym],
                        "major": bool(it.get("is_major")),
                        "sentiment": it.get("sentiment")})
    return out


def src_gnews(syms, ventana_s):
    """Google News RSS: sin clave, cobertura de los raros (DRAM/SPCX/SKHY). 1 req/simbolo."""
    ahora = time.time()
    out = []
    for sym in syms:
        q = "%s stock" % sym
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "+when:1d&hl=en-US&gl=US&ceid=US:en")
        try:
            root = ElementTree.fromstring(_get(url))
        except Exception as e:
            log("gnews %s FALLO: %s" % (sym, e.__class__.__name__))
            continue
        for it in list(root.iter("item"))[:8]:
            title = (it.findtext("title") or "").strip()
            ts = _rfc822_ts(it.findtext("pubDate"))
            if not title or ts is None or ahora - ts > ventana_s:
                continue
            src = (it.findtext("source") or "").strip() or None
            if not src and " - " in title:
                src = title.rsplit(" - ", 1)[-1]
            out.append({"sym": sym, "title": title, "url": it.findtext("link"), "ts": ts,
                        "source": src or "Google News", "tickers": [sym]})
    return out


def _iso_ts(s):
    """ISO-8601 UTC -> epoch. None si no se puede leer (jamas 'ahora' por defecto)."""
    if not s or not isinstance(s, str):
        return None
    t = s.strip().replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            import datetime
            d = datetime.datetime.strptime(t, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return d.timestamp()
        except ValueError:
            continue
    return None


def _rfc822_ts(s):
    if not s:
        return None
    try:
        import email.utils
        d = email.utils.parsedate_to_datetime(s)
        return d.timestamp() if d else None
    except (TypeError, ValueError):
        return None


# --- filtro de ruido ---------------------------------------------------------------------
def es_ruido(item):
    """(True, motivo) si el titular es relleno de agregador o no habla del simbolo."""
    src = (item.get("source") or "").lower()
    for mal in PUB_NEGRO:
        if mal in src:
            return True, "publisher %s" % src
    if TITULO_NEGRO.search(item.get("title") or ""):
        return True, "titulo plantilla"
    if len((item.get("title") or "").split()) < 5:
        return True, "titular vacio"
    if not es_relevante(item):
        return True, "tangencial (el titular no nombra al simbolo)"
    return False, ""


def impacto(item):
    """🔴 catalizador declarado · 📰 normal. No es una senal: es una etiqueta de lectura."""
    if item.get("major"):
        return "🔴"
    return "🔴" if CATALIZADOR.search(item.get("title") or "") else "📰"


# --- publicacion --------------------------------------------------------------------------
def edad_txt(ts, ahora):
    m = max(0, int((ahora - ts) / 60))
    return "%dm" % m if m < 90 else "%.1fh" % (m / 60.0)


def build_embeds(por_sym, ahora, max_sym=MAX_POR_SIMBOLO):
    """Un embed por simbolo, lineas ordenadas de mas nueva a mas vieja."""
    embeds = []
    for sym in sorted(por_sym):
        lineas = []
        for it in sorted(por_sym[sym], key=lambda x: -x["ts"])[:max_sym]:
            titulo = re.sub(r"\s+[-–—]\s+[^-–—]{2,40}$", "", it["title"]).strip()
            txt = "%s %s" % (impacto(it), titulo[:220])
            if it.get("url"):
                txt = "%s [%s](%s)" % (impacto(it), titulo[:220], it["url"])
            lineas.append("%s\n`%s · %s`" % (txt, it.get("source") or "?",
                                             edad_txt(it["ts"], ahora)))
        if lineas:
            embeds.append(S.build_embed("📰 %s" % sym, "\n".join(lineas), L.NORMAL,
                                        source="fleet_news_watch", ts=ahora))
    return embeds


def _embed_len(e):
    """Caracteres que Discord cuenta de un embed (title + description + footer)."""
    return (len(e.get("title") or "") + len(e.get("description") or "")
            + len((e.get("footer") or {}).get("text") or ""))


def lotes(embeds, max_n=MAX_EMBEDS_MSG, max_chars=5800):
    """Trocea por NUMERO y por TAMANO. Discord: 10 embeds/mensaje y 6000 chars en TOTAL —
    el segundo limite no esta en la doc del webhook y lo devolvio en vivo como 400."""
    out, cur, n = [], [], 0
    for e in embeds:
        le = _embed_len(e)
        if cur and (len(cur) >= max_n or n + le > max_chars):
            out.append(cur)
            cur, n = [], 0
        cur.append(e)
        n += le
    if cur:
        out.append(cur)
    return out


def publicar(embeds, hooks, dry=False):
    """Manda en tandas que respetan los dos topes de Discord. (enviados, fallos)."""
    url = hooks.get(CANAL)
    if not url and not dry:
        return 0, ["sin webhook para #%s (corre discord_webhooks.py)" % CANAL]
    env, fallos = 0, []
    for lote in lotes(embeds):
        if dry:
            env += len(lote)
            continue
        body = json.dumps({"embeds": lote,
                           "allowed_mentions": {"parse": [], "roles": []}}).encode("utf-8")
        ok, err = S._post(url + "?wait=true", body,
                          {"Content-Type": "application/json", "User-Agent": S.UA})
        if ok:
            env += len(lote)
        else:
            fallos.append(err)
        time.sleep(1.0)
    return env, fallos


def recolectar(syms, ventana_s, fuentes):
    """[(items, nombre_fuente_fallida)] -> items normalizados de todas las fuentes vivas."""
    items, rotas = [], []
    key_poly = dc.secret("POLYGON_KEY")
    key_fh = dc.secret("FINNHUB_KEY")
    tok_uw = dc.secret("UW_TOKEN")
    kid, ksec = dc.secret("ALPACA_API_KEY_ID"), dc.secret("ALPACA_API_SECRET_KEY")
    alp = (kid, ksec) if (kid and ksec) else None
    plan = [("alpaca", lambda: src_alpaca(syms, alp, ventana_s), alp),
            ("uw", lambda: src_uw(syms, tok_uw, ventana_s), tok_uw),
            ("polygon", lambda: src_polygon(syms, key_poly, ventana_s), key_poly),
            ("finnhub", lambda: src_finnhub(syms, key_fh, ventana_s), key_fh),
            ("gnews", lambda: src_gnews(syms, ventana_s), True)]
    for nombre, fn, cred in plan:
        if nombre not in fuentes:
            continue
        if not cred:
            rotas.append("%s: sin credencial" % nombre)
            continue
        t0 = time.time()
        try:
            got = fn()
        except Exception as e:
            rotas.append("%s: %s %s" % (nombre, e.__class__.__name__, str(e)[:80]))
            continue
        log("%s: %d titulares en %.1fs" % (nombre, len(got), time.time() - t0))
        items += got
    return items, rotas


def main():
    ap = argparse.ArgumentParser(description="noticias de la flota -> Discord")
    ap.add_argument("--dry-run", action="store_true", help="imprime, no publica ni marca vistos")
    ap.add_argument("--fuentes", default="alpaca,uw,polygon,finnhub,gnews",
                    help="coma: alpaca,uw,polygon,finnhub,gnews")
    ap.add_argument("--ventana-h", type=float, default=VENTANA_H)
    ap.add_argument("--max-sym", type=int, default=MAX_POR_SIMBOLO)
    ap.add_argument("--syms", help="coma: limita el universo (pruebas)")
    a = ap.parse_args()

    syms = ([s.strip().upper() for s in a.syms.split(",") if s.strip()] if a.syms else fleet())
    fuentes = {s.strip() for s in a.fuentes.split(",") if s.strip()}
    ahora = time.time()
    items, rotas = recolectar(syms, a.ventana_h * 3600, fuentes)
    for r in rotas:
        print("FUENTE ROTA %s" % r, file=sys.stderr)
        log("FUENTE ROTA %s" % r)
    if not items and rotas:
        print("todas las fuentes fallaron: no se publica nada", file=sys.stderr)
        return 1

    limpios, ruido = [], 0
    for it in items:
        malo, _ = es_ruido(it)
        if malo:
            ruido += 1
            continue
        limpios.append(it)
    limpios.sort(key=lambda x: -x["ts"])

    store = NS.Store()
    # Se marca vista TODA la ventana evaluada, no solo lo que sale. Publicar solo los N mas
    # nuevos por simbolo y dejar el resto sin marcar hacia que el barrido siguiente goteara
    # titulares viejos (medido en vivo: 2a corrida = 56 noticias rancias). Lo que no entra en
    # el corte es, por construccion, lo MAS VIEJO de su simbolo: para el proximo barrido ya
    # no es noticia.
    if a.dry_run:
        vistos = set(store.load(ahora))
        nuevos = []
        for it in limpios:
            ks = NS.keys(it["title"], it.get("url"))
            if not ks or any(k in vistos for k in ks):
                continue
            vistos.update(ks)
            nuevos.append(it)
    else:
        nuevos = [p[2] for p in store.filter_new(
            [(it["title"], it.get("url"), it) for it in limpios])]
    por_sym = {}                                # limpios ya viene de mas nuevo a mas viejo
    for it in nuevos:
        por_sym.setdefault(it["sym"], []).append(it)
    embeds = build_embeds(por_sym, ahora, a.max_sym)

    hooks = {} if a.dry_run else W.load()
    env, fallos = publicar(embeds, hooks, a.dry_run)
    resumen = ("fleet_news: %d titulares brutos · %d ruido · %d nuevos · %d simbolos · "
               "%d embeds %s" % (len(items), ruido, len(nuevos), len(por_sym), env,
                                 "(dry)" if a.dry_run else "publicados"))
    print(resumen)
    log(resumen)
    if a.dry_run:
        for sym in sorted(por_sym):
            for it in sorted(por_sym[sym], key=lambda x: -x["ts"])[:a.max_sym]:
                print("  %-6s %s %s [%s %s]" % (sym, impacto(it), it["title"][:90],
                                                it.get("source"), edad_txt(it["ts"], ahora)))
    # Un canal apagado A PROPOSITO no es una averia. Con data/notify_off puesto, no poder
    # publicar es el resultado esperado: se deja escrito y se sale 0. Cualquier OTRO fallo de
    # publicacion sigue siendo fallo duro.
    apagado = os.path.exists(os.path.join(REPO, "data", "notify_off"))
    for f in fallos:
        if apagado:
            log("publicacion omitida (data/notify_off): %s" % f)
        else:
            print("FALLO publicando: %s" % f, file=sys.stderr)
            log("FALLO publicando: %s" % f)
    return 1 if (fallos and not apagado) else 0


if __name__ == "__main__":
    sys.exit(main())
