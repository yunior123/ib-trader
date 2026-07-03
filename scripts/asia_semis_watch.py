#!/usr/bin/env python3
"""asia_semis_watch.py — Taiwán/Japón/China-semis a Discord (#taiwan-japon, #china-semis).

Lote FUERA de camino de señal (Yunior 2026-08-04 #31): titulares Google News RSS.
Publica via notify_short.push -> el embudo enruta por los emojis 🇹🇼🇯🇵🇨🇳 (discord_layout
RULES). Corre por launchd cada 30 min; solo habla en ventana asiática o si hay titular nuevo.
Fail-loud: sin dato no se publica nada (jamás un cero plausible).

Las cotizaciones Yahoo quedaron retiradas: son cierres diarios/delayed y violan la política
de fuentes realtime. QUOTES se conserva como inventario para conectarlo a un feed permitido.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
STATE = os.path.join(REPO, "data", "asia_semis_state.json")

# (yahoo_ticker, nombre, canal_emoji)
QUOTES = [
    ("^TWII", "TAIEX", "🇹🇼"), ("2330.TW", "TSMC-TW", "🇹🇼"),
    ("^N225", "Nikkei", "🇯🇵"), ("8035.T", "TokyoElectron", "🇯🇵"),
    ("6857.T", "Advantest", "🇯🇵"), ("6146.T", "DiscoCorp", "🇯🇵"),
    ("0981.HK", "SMIC", "🇨🇳"), ("1347.HK", "HuaHong", "🇨🇳"),
]
NEWS_Q = [
    ("CXMT OR ChangXin memory", "🇨🇳", ("cxmt", "changxin")),
    ("DRAM spot price", "🇨🇳", ("dram", "memory chip", "memory price")),
    ("TSMC OR TAIEX semiconductor", "🇹🇼", ("tsmc", "taiwan semiconductor", "taiex")),
    ("Tokyo Electron OR Advantest OR Nikkei semiconductor", "🇯🇵",
     ("tokyo electron", "advantest", "nikkei semiconductor")),
]


def _state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {"seen": []}


def _save(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"))
    os.replace(tmp, STATE)


def asia_window(now=None):
    # TWSE 21:00-01:30 ET (dom-jue), TSE 20:00-02:00 ET: ventana comun 19:30-02:30 ET
    t = datetime.fromtimestamp(now or time.time(), ZoneInfo("America/New_York"))
    hm = t.hour * 60 + t.minute
    return hm >= 19 * 60 + 30 or hm <= 2 * 60 + 30


def quotes_block():
    """No publica precios hasta tener un feed realtime permitido para Asia."""
    return {}


def relevant_title(title, required_terms):
    """Google aplica OR de forma amplia; exigimos una entidad concreta en el titular."""
    clean = re.sub(r"\s+", " ", title.lower())
    return any(term in clean for term in required_terms)


def news(query):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
           + "+when:1d&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    root = ElementTree.fromstring(urllib.request.urlopen(req, timeout=20).read())
    items = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        if t:
            items.append(t)
    return items[:5]


def main():
    st = _state()
    seen = set(st.get("seen", []))
    import notify_short
    q = quotes_block()
    if q and asia_window():
        for flag in ("🇹🇼", "🇯🇵", "🇨🇳"):
            hot = [(n, px, pct) for n, (f, px, pct) in q.items() if f == flag and abs(pct) >= MOVE_PCT]
            if hot:
                cuerpo = " · ".join(f"{n} {px:,.0f} {pct:+.1f}%" for n, px, pct in hot)
                notify_short.push(f"{flag} SEMIS ASIA", cuerpo)
                print(f"asia_semis: publicado {flag} {cuerpo}")
    nuevos = 0
    for query, flag, required_terms in NEWS_Q:
        try:
            for t in news(query):
                if not relevant_title(t, required_terms):
                    continue
                key = re.sub(r"\W+", "", t.lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                nuevos += 1
                if nuevos <= 6:  # tope por corrida: canal informativo, no manguera
                    notify_short.push(f"{flag} NOTICIA SEMIS", t[:180])
        except Exception as e:
            print(f"asia_semis: news '{query}' fallo ({type(e).__name__})")
    st["seen"] = list(seen)[-500:]
    _save(st)
    if nuevos:
        print(f"asia_semis: {nuevos} titulares relevantes nuevos")


if __name__ == "__main__":
    main()
