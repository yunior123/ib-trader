#!/usr/bin/env python3
"""x_earnings_post.py — CALENDARIO en PNG de los earnings de la semana que viene + 1 linea de texto.

Fuente unica Finviz Elite export (f=earningsdate_nextweek):
  v=171                        -> Beta ATR SMA20/50/200 52W-hi/lo RSI(14) Gap Price Change Volume
  v=152&c=1,6,30,64,65,68      -> Market Cap, Short Float, Vol relativo, Price, `Earnings Date`
Hora -> sesion: 8:30:00 AM = BMO, 4:30:00 PM = AMC (los dos unicos buckets que sirve Finviz).

DOS ORDENES DISTINTOS, a proposito:
  REJILLA = calendario de "quien reporta" -> **market cap descendente** (flota primero). Ordenarla
    por picardia la llenaba de micro-caps: gap/ATR%/RSI/short float/relvol los maximizan los
    nombres que nadie reconoce, y las grandes caian detras del tile "+N".
  FRANJA de abajo = nuestro EDGE -> score() picaro. Esa si va por picardia.

La rejilla va en la IMAGEN (los tickers dentro del PNG NO cuentan como cashtags) y el texto del
tweet lleva UN cashtag como maximo. La flota de data/fleet.txt sale DESTACADA, y los 3 nombres
mas picaros llevan su escalera 🔴🎯📍🟢🛑 dibujada con niveles medidos (precio±ATR y SMAs).
Sin logos de empresa: solo texto (marca registrada ajena).

Ledger/caps: x_post_common (10 posts/dia compartidos, $4/mes).
SEÑAL-SOLAMENTE. --dry-run es el DEFAULT; publica solo con --post.
Log: x_earnings_post.log
"""
import argparse
import csv
import io
import os
import sys
import time
import urllib.request
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import x_post_common as xc  # noqa: E402

LOG_FILE = os.path.join(REPO, "x_earnings_post.log")
CACHE_171 = os.path.join(REPO, "data", "finviz_earn_nextweek_171.csv")
CACHE_152 = os.path.join(REPO, "data", "finviz_earn_nextweek_152.csv")
FLEET_FILE = os.path.join(REPO, "data", "fleet.txt")
# data/ y no ~/Desktop: launchd no puede leer/escribir en Desktop por TCC (exit 78).
DEFAULT_PNG = os.path.join(REPO, "data", "x_media", "earnings_week.png")
MAX_AGE_S = 6 * 3600
MIN_ROWS = 50                 # 753 tickers el 2026-07-25; <50 = feed roto, no pisar cache
COLS_152 = "1,6,30,64,65,68"    # c=6 es Market Cap: ordena la REJILLA (quien reporta)
MAX_HORIZON_D = 14            # una fecha mas lejana no es "la semana que viene"
BAND_ATR = 2.0                # anclas mas lejas que 2 ATR no son niveles operables
TILES_PER_ROW = 3
TILE_ROWS = 3                 # 9 tiles por seccion; el resto se resume en un tile "+N"
LADDER_ROWS = 4               # cuantos nombres llevan escalera en la franja de abajo

log = xc.make_logger(LOG_FILE)

DOW = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MON = ("", "ene", "feb", "mar", "abr", "may", "jun",
       "jul", "ago", "sep", "oct", "nov", "dic")

QUIPS = [
    "El print del reporte no negocia con tu theta.",
    "La sorpresa la da la empresa; la factura, tu prima.",
    "Aguantar prima comprada a través de un print es donar.",
    "La valla ATR ya te dijo cuánto piensan moverlo.",
    "Los dealers cobran la incertidumbre por adelantado.",
]

# paleta oscura (fondo #0d1117); la flota se distingue por BORDE verde + texto verde
C_BG = "#0d1117"
C_PANEL = "#161b22"
C_TILE = "#21262d"
C_TILE_TXT = "#c9d1d9"
C_FLEET = "#132a1d"
C_FLEET_EDGE = "#3fb950"
C_FLEET_TXT = "#7ee787"
C_MUTED = "#8b949e"
C_HEAD = "#58a6ff"
C_SUN = "#e3b341"
C_MOON = "#a5adba"
# color POR ROL, no por posicion: cuando un peldaño se cae (techo==iman en AAPL) el
# indice se corre y el spot salia pintado de iman. El emoji manda el color.
LADDER_DOTS = {"🔴": "#f85149", "🎯": "#e3b341", "📍": "#ffffff",
               "🟢": "#3fb950", "🛑": "#8b949e"}


# ------------------------------------------------------------------ Finviz
def token():
    """FINVIZ_AUTH3 (env, luego feeds.env). None si no hay — jamas imprimirlo."""
    t = os.environ.get("FINVIZ_AUTH3", "").strip()
    if t:
        return t
    try:
        with open(os.path.join(REPO, "feeds.env")) as f:
            for ln in f:
                ln = ln.strip()
                for k in ("FINVIZ_AUTH3=", "FINVIZ_AUTH="):
                    if ln.startswith(k):
                        return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _fresh(path):
    try:
        return time.time() - os.path.getmtime(path) < MAX_AGE_S
    except OSError:
        return False


def _write_atomic(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(body)
    os.replace(tmp, path)


def fetch_csv(view, cache, auth, cols=None, force=False):
    """CSV crudo de Finviz (o el cache si es fresco). None si falla — nunca ''."""
    if not force and _fresh(cache):
        try:
            with open(cache) as f:
                return f.read()
        except OSError:
            pass
    if not auth:
        log("ROTO sin FINVIZ_AUTH3 (env ni feeds.env)")
        return None
    url = (f"https://elite.finviz.com/export/screener?v={view}"
           f"&f=earningsdate_nextweek&auth={auth}")
    if cols:
        url += f"&c={cols}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        body = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
    except Exception as e:
        log(f"ROTO v={view} fetch fallo ({type(e).__name__})")   # jamas el body: ecoa el token
        return None
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) - 1 < MIN_ROWS or "Ticker" not in lines[0]:
        log(f"ROTO v={view} respuesta invalida ({max(len(lines) - 1, 0)} filas)")
        return None
    _write_atomic(cache, body)
    return body


def parse_csv(body):
    """list[dict] o None. None tambien si el header no trae Ticker."""
    if not body:
        return None
    rows = list(csv.DictReader(io.StringIO(body)))
    if not rows or "Ticker" not in rows[0]:
        return None
    return rows


# ------------------------------------------------------------------ campos
def num(s):
    """float o None. JAMAS 0.0: un cero fabricado convierte 'no sé' en 'sé, y es cero'."""
    if s is None:
        return None
    s = str(s).strip().strip('"').replace("%", "").replace(",", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_earn(s):
    """('YYYY-MM-DD', 'BMO'|'AMC', datetime) desde '7/30/2026 8:30:00 AM'.
    None si no parsea O si viene sin hora: sin hora no hay sesion y no se adivina."""
    if not s:
        return None
    s = str(s).strip().strip('"')
    try:
        dt = datetime.strptime(s, "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return None
    return (dt.strftime("%Y-%m-%d"), "BMO" if dt.hour < 12 else "AMC", dt)


def merge(rows171, rows152, today=None):
    """dict SYM -> fila normalizada. Fila incompleta = fila FUERA (nunca rellenada)."""
    if not rows171 or not rows152:
        return None
    ref = today or datetime.now()
    by152 = {}
    for r in rows152:
        sym = (r.get("Ticker") or "").strip().strip('"').upper()
        if sym:
            by152[sym] = r
    out = {}
    for r in rows171:
        sym = (r.get("Ticker") or "").strip().strip('"').upper()
        b = by152.get(sym)
        if not sym or b is None:
            continue
        e = parse_earn(b.get("Earnings Date"))
        if e is None:
            continue
        date_s, sess, dt = e
        days = (dt.date() - ref.date()).days
        if days < 0 or days > MAX_HORIZON_D:
            continue
        price = num(r.get("Price"))
        atr = num(r.get("Average True Range"))
        d20 = num(r.get("20-Day Simple Moving Average"))
        d50 = num(r.get("50-Day Simple Moving Average"))
        d200 = num(r.get("200-Day Simple Moving Average"))
        rsi = num(r.get("Relative Strength Index (14)"))
        gap = num(r.get("Gap"))
        # `tech` separa las dos exigencias: el TILE solo necesita fecha+sesion (medidas),
        # la ESCALERA necesita los tecnicos completos. SKHY (ADR reciente) llega sin
        # RSI ni Beta: sale en la rejilla, jamas con niveles ni con score inventado.
        tech = (None not in (price, atr, d20, d50, d200, rsi, gap)
                and price > 0 and atr > 0)
        out[sym] = {
            "sym": sym, "date": date_s, "sess": sess, "dt": dt, "tech": tech,
            "price": price, "atr": atr,
            "atr_pct": (atr / price * 100) if tech else None,
            "rsi": rsi, "gap": gap,
            "d20": d20, "d50": d50, "d200": d200,
            "sma20": price / (1 + d20 / 100) if tech else None,
            "sma50": price / (1 + d50 / 100) if tech else None,
            "sma200": price / (1 + d200 / 100) if tech else None,
            "w52h": num(r.get("52-Week High")), "w52l": num(r.get("52-Week Low")),
            "chg": num(r.get("Change")),
            "short_float": num(b.get("Short Float")),
            "relvol": num(b.get("Relative Volume")),
        }
    return out or None


def fleet_syms(path=FLEET_FILE):
    """set de la flota o None si no se puede leer (sin fallback inventado)."""
    try:
        with open(path) as f:
            return {s.upper() for s in f.read().split() if s.strip()}
    except OSError:
        return None


# ------------------------------------------------------------------ picardia
def score(r, fleet):
    """Interes picaro: solo suma lo MEDIDO; lo ausente no puntua ni penaliza.
    Fila sin tecnicos = solo el bono de flota, asi ordena ultima entre las suyas."""
    s = 25.0 if fleet and r["sym"] in fleet else 0.0
    if not r["tech"]:
        return s
    s += min(abs(r["gap"]), 10) * 1.5
    s += (max(0.0, r["rsi"] - 70) + max(0.0, 30 - r["rsi"])) * 1.0
    s += min(r["atr_pct"], 12) * 2.0
    s += min(abs(r["d20"]), 25) * 0.5 + min(abs(r["d50"]), 40) * 0.3
    s += min(abs(r["d200"]), 80) * 0.1
    if r["short_float"] is not None:
        s += min(r["short_float"], 30) * 0.8
    if r["relvol"] is not None and r["relvol"] > 1:
        s += min(r["relvol"] - 1, 4) * 5
    if r["w52h"] is not None and abs(r["w52h"]) <= 2:
        s += 5
    if r["w52l"] is not None and r["w52l"] <= 10:
        s += 5
    return s


def picaro_bits(r):
    """Etiquetas cortas, todas medidas. Lista vacia si al ticker le faltan tecnicos."""
    if not r["tech"]:
        return []
    bits = []
    if r["rsi"] >= 70:
        bits.append(f"RSI {r['rsi']:.0f} recalentado")
    elif r["rsi"] <= 30:
        bits.append(f"RSI {r['rsi']:.0f} en el suelo")
    if abs(r["gap"]) >= 1.5:
        bits.append(f"gap {r['gap']:+.1f}%")
    if r["relvol"] is not None and r["relvol"] >= 1.5:
        bits.append(f"vol rel {r['relvol']:.1f}x")
    if r["short_float"] is not None and r["short_float"] >= 8:
        bits.append(f"short {r['short_float']:.0f}% de leña")
    if abs(r["d20"]) >= 5:
        bits.append(f"{r['d20']:+.0f}% vs SMA20")
    if r["w52h"] is not None and abs(r["w52h"]) <= 2:
        bits.append("pegado al máximo 52s")
    if r["w52l"] is not None and r["w52l"] <= 10:
        bits.append("raspando el mínimo 52s")
    bits.append(f"valla ATR ±{r['atr_pct']:.1f}%")
    return bits


def ladder(r):
    """[(emoji, nivel)] descendente desde anclas MEDIDAS (precio±ATR y SMAs a <=2 ATR).
    Lista VACIA si faltan tecnicos: sin ATR ni SMA no hay escalera que dibujar."""
    if not r["tech"]:
        return []
    p, atr = r["price"], r["atr"]
    band = BAND_ATR * atr
    smas = [r["sma20"], r["sma50"], r["sma200"]]
    above = sorted(x for x in smas if p + 0.01 < x <= p + band)
    below = sorted((x for x in smas if p - band <= x < p - 0.01), reverse=True)
    hi, lo = p + atr, p - atr
    rungs = [("🔴", max([hi] + above)), ("🎯", above[0] if above else hi),
             ("📍", p),
             ("🟢", below[0] if below else lo), ("🛑", min([lo] + below))]
    out = []
    for emo, v in rungs:
        if out and v >= out[-1][1] - 0.005:
            if emo == "📍":                  # el spot no se cae nunca: cae su vecino
                out.pop()
            else:
                continue
        out.append((emo, v))
    return out


def fmt(v):
    return f"{v:.2f}" if v < 1000 else f"{v:.0f}"


def when(r):
    d = r["dt"]
    return f"{DOW[d.weekday()]} {d.day}-{MON[d.month]} {r['sess']}"


def rank_ladders(merged, fleet):
    """Filas con tecnicos completos, flota primero, mas picara delante."""
    tech = [r for r in merged.values() if r["tech"]]
    inf = [r for r in tech if fleet and r["sym"] in fleet]
    return sorted(inf or tech, key=lambda r: -score(r, fleet))


def by_day_session(merged, fleet):
    """{(date, sess): [filas ordenadas flota-primero y luego por score]}."""
    grid = {}
    for r in merged.values():
        grid.setdefault((r["dt"].date(), r["sess"]), []).append(r)
    for key in grid:
        grid[key].sort(key=lambda r: (0 if fleet and r["sym"] in fleet else 1,
                                      -score(r, fleet)))
    return grid


# ------------------------------------------------------------------ imagen
ASPECT = 16 / 9        # el eje va 0-100 en x y en y sobre una figura 16:9 -> hay que
                       # estirar el radio vertical o los circulos salen ovalados


def _dot(ax, x, y, r, color, z=3):
    from matplotlib.patches import Ellipse
    ax.add_patch(Ellipse((x, y), 2 * r, 2 * r * ASPECT, color=color, zorder=z))


def _sun(ax, x, y, r=0.9):
    import math
    _dot(ax, x, y, r * 0.5, C_SUN)
    for i in range(8):
        a = i * math.pi / 4
        ax.plot([x + math.cos(a) * r * 0.75, x + math.cos(a) * r * 1.2],
                [y + math.sin(a) * r * 0.75 * ASPECT, y + math.sin(a) * r * 1.2 * ASPECT],
                color=C_SUN, lw=1.1, zorder=3, solid_capstyle="round")


def _moon(ax, x, y, r=0.9):
    _dot(ax, x, y, r * 0.6, C_MOON)
    _dot(ax, x + r * 0.30, y + r * 0.30 * ASPECT, r * 0.52, C_PANEL, z=4)


def _tile(ax, x, y, w, h, label, is_fleet, muted=False):
    from matplotlib.patches import FancyBboxPatch
    face = C_FLEET if is_fleet else (C_PANEL if muted else C_TILE)
    edge = C_FLEET_EDGE if is_fleet else ("#30363d" if not muted else "#262c36")
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.45",
                                facecolor=face, edgecolor=edge,
                                linewidth=1.6 if is_fleet else 0.8, zorder=2))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=10.5 if len(label) <= 4 else 9.2,
            color=C_FLEET_TXT if is_fleet else (C_MUTED if muted else C_TILE_TXT),
            fontweight="bold" if is_fleet else "normal", zorder=5)


def _ladder_row(ax, x, y, r, fleet):
    """Escalera dibujada: puntos de color en vez de emoji (DejaVu no tiene 🔴/🎯)."""
    rungs = ladder(r)
    ax.text(x, y, f"{r['sym']}  {when(r)}", ha="left", va="center", fontsize=9.5,
            fontweight="bold",
            color=C_FLEET_TXT if fleet and r["sym"] in fleet else C_TILE_TXT, zorder=5)
    cx = x + 17.5
    for emo, v in rungs:
        _dot(ax, cx, y, 0.36, LADDER_DOTS.get(emo, C_MUTED), z=5)
        ax.text(cx + 0.85, y, fmt(v), ha="left", va="center", fontsize=9,
                color=C_TILE_TXT, zorder=5)
        cx += 8.2
    ax.text(x + 60, y, " · ".join(picaro_bits(r)[:3]), ha="left", va="center",
            fontsize=8.8, color=C_MUTED, zorder=5)


def render_calendar(merged, fleet, out_path=DEFAULT_PNG):
    """Escribe el PNG del calendario. Devuelve la ruta, o None si no hay datos."""
    if not merged or not fleet:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    grid = by_day_session(merged, fleet)
    days = sorted({d for d, _ in grid})[:5]
    if not days:
        return None

    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=C_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.axis("off"); ax.set_facecolor(C_BG)

    n_fleet = len([s for s in merged if s in fleet])
    ax.text(2.5, 95.6, "EARNINGS · SEMANA QUE VIENE", fontsize=21, fontweight="bold",
            color="#f0f6fc", va="center")
    ax.text(2.5, 91.6, f"{len(merged)} empresas · {n_fleet} de los {len(fleet)} de la flota "
            f"(borde verde) · niveles medidos: precio±ATR y SMA20/50/200",
            fontsize=10.5, color=C_MUTED, va="center")
    ax.text(97.5, 94.5, "ib-trader", fontsize=12, color=C_HEAD, ha="right",
            va="center", fontweight="bold")

    col_w = 96.0 / len(days)
    tile_w = (col_w - 3.0 - 1.4 * (TILES_PER_ROW - 1)) / TILES_PER_ROW
    tile_h, gap = 4.6, 1.2
    sec_top = {"BMO": 78.0, "AMC": 56.0}

    for di, d in enumerate(days):
        x0 = 2.0 + di * col_w
        ax.add_patch(FancyBboxPatch((x0, 38.0), col_w - 1.2, 48.0,
                                    boxstyle="round,pad=0,rounding_size=0.8",
                                    facecolor=C_PANEL, edgecolor="#21262d",
                                    linewidth=1.0, zorder=1))
        ax.text(x0 + (col_w - 1.2) / 2, 83.2, f"{DOW[d.weekday()]} {d.day}",
                ha="center", va="center", fontsize=14, fontweight="bold",
                color="#f0f6fc", zorder=5)
        for sess, label in (("BMO", "Antes de abrir"), ("AMC", "Tras el cierre")):
            top = sec_top[sess]
            (_sun if sess == "BMO" else _moon)(ax, x0 + 2.2, top + 2.4)
            rows = grid.get((d, sess), [])
            ax.text(x0 + 4.3, top + 2.4, f"{label}  ({len(rows)})", ha="left",
                    va="center", fontsize=9.8, color=C_MUTED, zorder=5)
            cap = TILES_PER_ROW * TILE_ROWS
            shown = rows[:cap] if len(rows) <= cap else rows[:cap - 1]
            for i, r in enumerate(shown):
                tx = x0 + 1.5 + (i % TILES_PER_ROW) * (tile_w + 1.4)
                ty = top - (i // TILES_PER_ROW) * (tile_h + gap) - tile_h
                _tile(ax, tx, ty, tile_w, tile_h, r["sym"], r["sym"] in fleet)
            if len(rows) > cap:
                i = cap - 1
                tx = x0 + 1.5 + (i % TILES_PER_ROW) * (tile_w + 1.4)
                ty = top - (i // TILES_PER_ROW) * (tile_h + gap) - tile_h
                _tile(ax, tx, ty, tile_w, tile_h, f"+{len(rows) - i}", False, muted=True)

    ranked = rank_ladders(merged, fleet)
    ax.add_patch(FancyBboxPatch((2.0, 9.0), 96.0 - 1.2, 25.0,
                                boxstyle="round,pad=0,rounding_size=0.8",
                                facecolor=C_PANEL, edgecolor="#21262d",
                                linewidth=1.0, zorder=1))
    ax.text(3.5, 31.4, "LOS MÁS PÍCAROS DE LA FLOTA  ·  techo · imán · spot · piso · stop "
            "(solo los niveles que existen)",
            fontsize=10.5, fontweight="bold", color=C_HEAD, va="center", zorder=5)
    for i, r in enumerate(ranked[:LADDER_ROWS]):
        _ladder_row(ax, 3.5, 27.0 - i * 4.4, r, fleet)
    # decirlo en la imagen, no callarlo: quien no tiene tecnicos no tiene niveles
    no_tech = sorted(s for s, r in merged.items() if s in fleet and not r["tech"])
    if no_tech:
        ax.text(3.5, 10.6, f"sin niveles ({', '.join(no_tech)}): Finviz sirve la fila "
                f"incompleta — salen en la rejilla, no se les inventa escalera",
                fontsize=8.8, color=C_MUTED, va="center", zorder=5)
    ax.text(3.5, 5.0, "Señal-solamente · niveles Finviz Elite (ATR/SMA/RSI medidos) · "
            "prima comprada NO cruza un print · No es consejo financiero",
            fontsize=9, color=C_MUTED, va="center")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp.png"
    fig.savefig(tmp, facecolor=C_BG)
    plt.close(fig)
    os.replace(tmp, out_path)
    return out_path


# ------------------------------------------------------------------ texto
def build_tweet_text(merged, fleet, quip_seed=None):
    """UNA linea con gancho + <=1 cashtag. None si no hay datos (jamas huecos)."""
    if not merged or not fleet:
        return None
    ranked = rank_ladders(merged, fleet)      # el "mas picaro" exige tecnicos medidos
    if not ranked:
        return None
    in_fleet = [s for s in merged if s in fleet]
    star = ranked[0]
    seed = quip_seed if quip_seed is not None else int(time.strftime("%j"))
    quip = QUIPS[(seed + sum(map(ord, star["sym"]))) % len(QUIPS)]
    n_fleet = len(in_fleet)
    hook = (f"🔥 Semana de earnings bestial: {len(merged)} empresas reportan y "
            f"{n_fleet} son de la flota." if n_fleet else
            f"🔥 Semana de earnings bestial: {len(merged)} empresas reportan.")
    mid = (f"El más pícaro: ${star['sym']} {when(star)}, "
           f"valla ATR ±{star['atr_pct']:.1f}%.")
    img = "Rejilla completa + escaleras en la imagen 👇"
    for parts in ((hook, mid, img, quip), (hook, mid, img), (hook, mid)):
        text = " ".join(parts) + " No es consejo financiero."
        if len(text) <= xc.MAX_CHARS and xc.count_cashtags(text) <= 1:
            return text
    return None


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--post", action="store_true", help="publicar de verdad (sin esto NO publica)")
    ap.add_argument("--out", default=DEFAULT_PNG, help="ruta del PNG del calendario")
    ap.add_argument("--force", action="store_true", help="ignorar el cache de 6h de Finviz")
    a = ap.parse_args()
    dry = not a.post

    auth = token()
    b171 = fetch_csv(171, CACHE_171, auth, force=a.force)
    b152 = fetch_csv(152, CACHE_152, auth, cols=COLS_152, force=a.force)
    merged = merge(parse_csv(b171), parse_csv(b152))
    if not merged:
        log("SKIP sin datos de Finviz — no se genera post")
        return 1
    fleet = fleet_syms()
    if fleet is None:
        log("SKIP sin data/fleet.txt — no se prioriza a ciegas")
        return 1

    text = build_tweet_text(merged, fleet)
    if not text:
        log("SKIP texto no armable — no se postea a medias")
        return 1
    png = render_calendar(merged, fleet, a.out)
    if not png:
        log("SKIP calendario no renderizado — el post sin imagen no es el entregable")
        return 1

    env = xc.load_env()
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN",
                           "X_ACCESS_SECRET") if not env.get(k)]
    if missing and not dry:
        log(f"ERROR faltan credenciales en x.env: {','.join(missing)}")
        return 1
    auth_x = None if (dry or missing) else xc.make_auth(env)

    fl = sorted(s for s in merged if s in fleet)
    log(f"DATA {len(merged)} tickers earnings-nextweek | flota {len(fl)}: {' '.join(fl)}")
    log(f"PNG {png} ({os.path.getsize(png)} bytes) | cashtags texto: "
        f"{xc.count_cashtags(text)}")
    ok = xc.post_text(text, "earnings-calendario", log, dry, auth_x, media_path=png)
    bud = xc.load_budget()
    log(f"DONE {'dry-run' if dry else 'real'} ok={ok} | mes {bud['month']}: "
        f"{bud['posts']} posts ${bud['spent']:.3f}/{xc.MAX_SPEND_PER_MONTH:.2f}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
