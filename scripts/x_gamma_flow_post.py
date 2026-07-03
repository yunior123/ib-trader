#!/usr/bin/env python3
"""x_gamma_flow_post.py — ONE X post (PNG + short EN tweet) = DEALER POSITIONING
(walls/magnets/flip/regime, measured Polygon greeks, Fri close) + WEEKLY WHALE FLOW.

Two posts from one script via --universe:
  indices = SPY QQQ SPX NDX DIA IWM   (market captains + broad indices, fixed order)
  fleet   = data/fleet.txt (30), sorted by |signed_premium| desc (most whale action first)

Read-only sources already on disk:
  data/gex_snapshot.json  via gex_snapshot.load()  — FAIL LOUD if stale/missing (no invent)
  data/whale_week.json    (whale_week_agg.py)       — DEGRADE cleanly if absent (drop whale col)

Post plumbing via x_post_common (shared 10/day + $4/mo ledger, EN guard, cashtag sanitize,
275-char cap, media upload). --dry-run is the DEFAULT; publishes only with --post.
SEÑAL-SOLAMENTE. Never claims realtime. Log: x_gamma_flow_post.log
"""
import argparse
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import x_post_common as xc  # noqa: E402
import gex_snapshot  # noqa: E402

LOG_FILE = os.path.join(REPO, "x_gamma_flow_post.log")
FLEET_FILE = os.path.join(REPO, "data", "fleet.txt")
GEX_JSON = os.path.join(REPO, "data", "gex_snapshot.json")
WHALE_FILE = os.path.join(REPO, "data", "whale_week.json")
KIND_EN = {"pin": "PIN", "trampilla": "trap", "trapdoor": "trap"}   # imagen en ingles
DEFAULT_DIR = os.path.join(REPO, "data", "x_media")
INDICES = ["SPY", "QQQ", "SPX", "NDX", "DIA", "IWM"]

log = xc.make_logger(LOG_FILE)

# paleta oscura (misma de x_earnings_post.py)
C_BG = "#0d1117"
C_PANEL = "#161b22"
C_TILE = "#21262d"
C_TXT = "#c9d1d9"
C_MUTED = "#8b949e"
C_HEAD = "#58a6ff"
C_WHITE = "#f0f6fc"
C_GREEN = "#3fb950"
C_RED = "#f85149"
C_GOLD = "#e3b341"
C_NEG_TINT = "#3a1d20"      # regime NEGATIVE = whipsaw
C_POS_TINT = "#12331f"      # regime POSITIVE = trend

FONTS = [("/System/Library/Fonts/Menlo.ttc", 0, 1),
         ("/System/Library/Fonts/Monaco.ttf", 0, 0)]


def _font(size, bold=False):
    from PIL import ImageFont
    for path, ri, bi in FONTS:
        try:
            return ImageFont.truetype(path, size, index=bi if bold else ri)
        except OSError:
            continue
    return ImageFont.load_default()


# ------------------------------------------------------------------ datos
def fleet_syms(path=FLEET_FILE):
    """list de la flota o None si no se puede leer (sin fallback inventado)."""
    try:
        with open(path) as f:
            return [s.upper() for s in f.read().split() if s.strip()]
    except OSError:
        return None


def load_whale(path=WHALE_FILE):
    """dict {SYM:{...}, _meta:{...}} o None si falta/roto — degrade limpio, no crash."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def load_gex(force):
    """Mapa gamma medido. None si rancio/ausente (fail-loud arriba), salvo --force."""
    g = gex_snapshot.load()
    if g is None and force:
        g = gex_snapshot.load(max_age_h=10 ** 6)   # --force: ignora la guarda de edad
    return g


def gex_meta_raw(path=GEX_JSON):
    """_meta del fichero crudo (load() lo despoja): solo para el sello asof_local."""
    try:
        with open(path) as f:
            m = json.load(f).get("_meta")
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def whale_row(whale, sym):
    """Fila de flujo del sym o None (index sin flujo -> columna vacia, no inventada)."""
    if not isinstance(whale, dict):
        return None
    d = whale.get(sym) or whale.get(sym.upper())
    return d if isinstance(d, dict) else None


def order_syms(universe, gex, whale):
    """indices en orden fijo; fleet por |signed_premium| desc (mas flujo primero).
    Solo syms con mapa gamma (sin gamma no hay fila que dibujar)."""
    if universe == "indices":
        base = [s for s in INDICES if isinstance(gex.get(s), dict)]
        return base
    fl = fleet_syms()
    if fl is None:
        return None
    have = [s for s in fl if isinstance(gex.get(s), dict)]

    def key(s):
        w = whale_row(whale, s)
        return abs(w["signed_premium"]) if w and w.get("signed_premium") is not None else -1.0
    return sorted(have, key=key, reverse=True)


# ------------------------------------------------------------------ imagen
def _tri(draw, cx, cy, s, color, up=True):
    """Triangulo (flecha whale) dibujado, no glifo: evita tofu de fuente."""
    if up:
        pts = [(cx, cy - s), (cx - s, cy + s), (cx + s, cy + s)]
    else:
        pts = [(cx, cy + s), (cx - s, cy - s), (cx + s, cy - s)]
    draw.polygon(pts, fill=color)


def _fmtp(v):
    if v is None:
        return "-"
    return f"{v:,.2f}" if v < 1000 else f"{v:,.0f}"


def render(universe, rows, gex, whale, gex_meta, whale_meta, out_path):
    """Escribe el PNG de la tabla. Devuelve ruta o None si no hay filas."""
    from PIL import Image, ImageDraw
    if not rows:
        return None

    W = 1300
    pad = 30
    title_h = 96
    head_h = 44
    row_h = 34
    foot_h = 66
    H = title_h + head_h + len(rows) * row_h + foot_h

    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)

    f_title = _font(30, bold=True)
    f_sub = _font(15)
    f_head = _font(15, bold=True)
    f_sym = _font(19, bold=True)
    f_cell = _font(18)
    f_small = _font(14)
    f_foot = _font(13)

    # columnas (x-left)
    X = {"sym": 34, "spot": 128, "flip": 236, "walls": 430, "magnet": 720,
         "regime": 902, "whale": 1094}

    label = "INDICES" if universe == "indices" else "FLEET"
    d.text((pad, 26), f"DEALER POSITIONING + WEEKLY WHALE FLOW", font=f_title, fill=C_WHITE)
    d.text((pad, 64), f"{label} · {len(rows)} names · into the Aug 3-7 week from Friday's close",
           font=f_sub, fill=C_MUTED)
    d.text((W - pad, 30), "ib-trader", font=f_head, fill=C_HEAD, anchor="ra")

    # cabecera de tabla
    hy = title_h + 12
    d.line([(pad, title_h + head_h - 2), (W - pad, title_h + head_h - 2)], fill="#30363d", width=1)
    for key, txt in (("sym", "SYM"), ("spot", "SPOT"), ("flip", "FLIP (dist)"),
                     ("walls", "PUT ◄ SPOT ► CALL"), ("magnet", "MAGNET"),
                     ("regime", "REGIME"), ("whale", "WHALE (wk net $)")):
        d.text((X[key], hy), txt, font=f_head, fill=C_MUTED)

    y0 = title_h + head_h
    for i, sym in enumerate(rows):
        g = gex[sym]
        y = y0 + i * row_h
        cy = y + row_h // 2
        if i % 2:
            d.rectangle([(pad - 6, y), (W - pad + 6, y + row_h)], fill=C_PANEL)

        d.text((X["sym"], cy), sym, font=f_sym, fill=C_WHITE, anchor="lm")
        d.text((X["spot"], cy), _fmtp(g.get("spot")), font=f_cell, fill=C_TXT, anchor="lm")

        # flip + dist%: below spot (dist<0) = supportive green, above = resistance red
        flip = g.get("flip")
        dist = g.get("flip_dist_pct")
        fcol = C_MUTED if dist is None else (C_GREEN if dist < 0 else C_RED)
        d.text((X["flip"], cy), _fmtp(flip), font=f_cell, fill=C_TXT, anchor="lm")
        if dist is not None:
            d.text((X["flip"] + 78, cy), f"{dist:+.2f}%", font=f_small, fill=fcol, anchor="lm")

        # PUT wall ◄ spot ► CALL wall
        pw, cw, sp = g.get("put_wall"), g.get("call_wall"), g.get("spot")
        d.text((X["walls"], cy), _fmtp(pw), font=f_cell, fill=C_RED, anchor="lm")
        d.text((X["walls"] + 78, cy), "◄", font=f_cell, fill=C_MUTED, anchor="lm")
        d.text((X["walls"] + 104, cy), _fmtp(sp), font=f_cell, fill=C_TXT, anchor="lm")
        d.text((X["walls"] + 182, cy), "►", font=f_cell, fill=C_MUTED, anchor="lm")
        d.text((X["walls"] + 208, cy), _fmtp(cw), font=f_cell, fill=C_GREEN, anchor="lm")

        # magnet (abs_wall + kind); pin marcado distinto (dot gold + label gold)
        aw = g.get("abs_wall")
        kind = (g.get("abs_wall_kind") or "").strip()
        is_pin = kind == "pin"
        mcol = C_GOLD if is_pin else C_TXT
        d.text((X["magnet"], cy), _fmtp(aw), font=f_cell, fill=mcol, anchor="lm")
        if kind:
            klbl = KIND_EN.get(kind, kind)     # imagen en ingles (data trae 'trampilla')
            if is_pin:
                d.ellipse([(X["magnet"] + 90, cy - 4), (X["magnet"] + 98, cy + 4)], fill=C_GOLD)
                d.text((X["magnet"] + 104, cy), klbl, font=f_small, fill=C_GOLD, anchor="lm")
            else:
                d.text((X["magnet"] + 92, cy), klbl, font=f_small, fill=C_MUTED, anchor="lm")

        # regime pill: NEGATIVE red tint = whipsaw, POSITIVE green tint = trend
        reg = (g.get("regime") or "").upper()
        if reg in ("NEGATIVE", "POSITIVE"):
            tint = C_NEG_TINT if reg == "NEGATIVE" else C_POS_TINT
            rcol = C_RED if reg == "NEGATIVE" else C_GREEN
            d.rounded_rectangle([(X["regime"], cy - 12), (X["regime"] + 116, cy + 12)],
                                radius=6, fill=tint)
            d.text((X["regime"] + 58, cy), reg, font=f_small, fill=rcol, anchor="mm")
        else:
            d.text((X["regime"], cy), "-", font=f_cell, fill=C_MUTED, anchor="lm")

        # whale: arrow (calls up/green, puts down/red, mixed grey dash) + net premium $M
        w = whale_row(whale, sym)
        if w and w.get("signed_premium") is not None:
            sp_m = w["signed_premium"] / 1e6
            wb = (w.get("bias") or "").lower()
            if wb == "calls":
                wcol = C_GREEN
                _tri(d, X["whale"] + 8, cy, 6, wcol, up=True)
            elif wb == "puts":
                wcol = C_RED
                _tri(d, X["whale"] + 8, cy, 6, wcol, up=False)
            else:
                wcol = C_MUTED
                d.line([(X["whale"] + 2, cy), (X["whale"] + 14, cy)], fill=wcol, width=3)
            d.text((X["whale"] + 24, cy), f"{sp_m:+,.1f}M", font=f_cell, fill=wcol, anchor="lm")
        elif whale is not None:
            d.text((X["whale"] + 8, cy), "—", font=f_cell, fill=C_MUTED, anchor="lm")

    # footer honesty stamp (REQUIRED, muted) — nunca "realtime"
    gx = gex_meta.get("asof_local", "?") if isinstance(gex_meta, dict) else "?"
    if isinstance(whale_meta, dict):
        ws = whale_meta.get("week_start", "?")
        we = whale_meta.get("week_end", "?")
        wtag = f" · whale flow: Unusual Whales trial (delayed) week {ws}→{we}"
    else:
        wtag = " · whale flow: unavailable (file missing — column omitted)"
    stamp = (f"gamma: measured Polygon greeks, Fri close {gx}{wtag} · signal-only, not advice")
    d.line([(pad, H - foot_h + 6), (W - pad, H - foot_h + 6)], fill="#30363d", width=1)
    d.text((pad, H - foot_h + 22), stamp, font=f_foot, fill=C_MUTED)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp.png"
    img.save(tmp)
    os.replace(tmp, out_path)
    return out_path


# ------------------------------------------------------------------ texto
def _premium_phrase(sym, w):
    # signed_premium = net_call_premium - net_put_premium (UW "net premium"): el signo
    # es el sesgo, NO afirma que la prima de CALLS sea +m (en SPY net_call era negativa).
    m = w["signed_premium"] / 1e6
    side = "call-tilted" if m >= 0 else "put-tilted"
    return f"{sym} {m:+,.0f}M net premium ({side})"


def build_tweet(universe, rows, gex, whale):
    """<=270 chars, EN, prefer ZERO cashtags (no $ before letters). Compuesto del dato."""
    label = "indices" if universe == "indices" else "the fleet"
    # standouts: los 2 mayores flujos por |signed_premium|
    wl = [(s, whale_row(whale, s)) for s in rows]
    wl = [(s, w) for s, w in wl if w and w.get("signed_premium") is not None]
    wl.sort(key=lambda t: abs(t[1]["signed_premium"]), reverse=True)
    flow = "; ".join(_premium_phrase(s, w) for s, w in wl[:2]) if wl else ""

    # pin/flip notable: primer pin (mag) o flip mas cercano
    pins = [s for s in rows if (gex[s].get("abs_wall_kind") or "") == "pin"
            and gex[s].get("abs_wall") is not None]
    struct = ""
    if pins:
        s = pins[0]
        struct = f"{s} pinned at {_fmtp(gex[s]['abs_wall'])}"
    else:
        cand = [(s, gex[s].get("flip_dist_pct")) for s in rows
                if gex[s].get("flip_dist_pct") is not None and gex[s].get("flip") is not None]
        if cand:
            s, dd = min(cand, key=lambda t: abs(t[1]))
            struct = f"{s} flip {_fmtp(gex[s]['flip'])} ({dd:+.1f}%)"

    tag = "measured gamma + UW flow (delayed) · signal-only"
    head = f"How dealers sit into Aug 3-7 across {label}, from Fri's close:"
    for body in ((flow, struct), (flow,), (struct,)):
        mid = ". ".join(p for p in body if p)
        text = f"{head} {mid}. {tag}" if mid else f"{head} {tag}"
        if len(text) <= 270 and xc.count_cashtags(text) <= 1:
            return text
    fallback = f"{head} {tag}"
    return fallback if len(fallback) <= 270 else fallback[:270]


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True, choices=["indices", "fleet"])
    ap.add_argument("--out", default=None, help="ruta del PNG")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True)
    g.add_argument("--post", action="store_true", help="publicar de verdad (sin esto NO publica)")
    ap.add_argument("--force", action="store_true", help="ignorar la guarda de edad del mapa gamma")
    a = ap.parse_args()
    dry = not a.post
    out_path = a.out or os.path.join(DEFAULT_DIR, f"gamma_flow_{a.universe}.png")

    gex = load_gex(a.force)
    if not isinstance(gex, dict):
        log("SKIP mapa gamma ausente/rancio — no se inventa posicionamiento")
        return 1
    gex_meta = gex_meta_raw()      # load() despoja _meta; el asof sale del fichero crudo

    whale = load_whale()                       # None -> degrade limpio (sin columna whale)
    whale_meta = whale.get("_meta") if isinstance(whale, dict) else None
    if whale is None:
        log("WARN whale_week.json ausente — se renderiza sin columna de flujo")

    rows = order_syms(a.universe, gex, whale)
    if not rows:
        log(f"SKIP sin simbolos con mapa gamma para {a.universe}")
        return 1

    text = build_tweet(a.universe, rows, gex, whale)
    if not text:
        log("SKIP texto no armable")
        return 1
    png = render(a.universe, rows, gex, whale, gex_meta, whale_meta, out_path)
    if not png:
        log("SKIP PNG no renderizado — el post sin imagen no es el entregable")
        return 1

    env = xc.load_env()
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN",
                           "X_ACCESS_SECRET") if not env.get(k)]
    if missing and not dry:
        log(f"ERROR faltan credenciales en x.env: {','.join(missing)}")
        return 1
    auth = None if (dry or missing) else xc.make_auth(env)

    log(f"DATA {a.universe} rows={len(rows)}: {' '.join(rows)}")
    log(f"PNG {png} ({os.path.getsize(png)} bytes) | cashtags texto: {xc.count_cashtags(text)} "
        f"| len {len(text)}")
    ok = xc.post_text(text, f"gamma-flow-{a.universe}", log, dry, auth, media_path=png)
    bud = xc.load_budget()
    log(f"DONE {'dry-run' if dry else 'real'} ok={ok} | mes {bud['month']}: "
        f"{bud['posts']} posts ${bud['spent']:.3f}/{xc.MAX_SPEND_PER_MONTH:.2f}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
