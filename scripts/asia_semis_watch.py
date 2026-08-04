#!/usr/bin/env python3
"""asia_semis_watch.py — Taiwán/Japón/China-semis a Discord (#taiwan-japon, #china-semis).

Lote FUERA de camino de señal (Yunior 2026-08-04 #31): datos yfinance + titulares Google News
RSS. Publica via notify_short.push -> el embudo enruta por los emojis 🇹🇼🇯🇵🇨🇳 (discord_layout
RULES). Corre por launchd cada 30 min; solo habla en ventana asiática o si hay titular nuevo.
Fail-loud: sin dato no se publica nada (jamás un cero plausible).
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
NEWS_Q = [("CXMT OR ChangXin memory", "🇨🇳"), ("DRAM spot price", "🇨🇳"),
          ("TSMC OR TAIEX semiconductor", "🇹🇼"), ("Tokyo Electron OR Advantest OR Nikkei semiconductor", "🇯🇵")]
MOVE_PCT = 1.0   # solo se canta un quote si |%| del dia supera esto (anti-ruido)


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
    try:
        import yfinance as yf
    except ImportError:
        print("asia_semis: SIN yfinance en este venv — quotes omitidos (fail-loud)")
        return {}
    out = {}
    for tk, name, flag in QUOTES:
        try:
            h = yf.Ticker(tk).history(period="2d", interval="1d")
            if len(h) < 2:
                continue
            prev, last = float(h["Close"].iloc[-2]), float(h["Close"].iloc[-1])
            out[name] = (flag, last, (last / prev - 1) * 100)
        except Exception as e:
            print(f"asia_semis: {name} sin dato ({type(e).__name__}) — no se publica")
    return out


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
    for query, flag in NEWS_Q:
        try:
            for t in news(query):
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
    print(f"asia_semis: {len(q)} quotes, {nuevos} titulares nuevos")


if __name__ == "__main__":
    main()
