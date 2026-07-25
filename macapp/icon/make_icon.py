#!/usr/bin/env python3
"""make_icon.py — genera el arte del icono de la .app del Cockpit y el .icns.

DISENO: brujula (aguja bicolor + anillo) sobre fondo oscuro. La flecha-brujula es
el corazon del cockpit, asi que el icono ES la flecha. Sobrio, alto contraste, y
CERO texto: a 16 px un texto es ruido, la aguja diagonal se sigue leyendo.

    <repo>/venv/bin/python macapp/icon/make_icon.py

Salidas (todas junto a este fichero, rutas derivadas de __file__ — jamas
hardcodeadas, que la mudanza a ~/ib-trader ya mato 3 scripts):
    appicon_1024.png
    AppIcon.iconset/   (10 tamanos via sips)
    AppIcon.icns       (via iconutil)

Requiere PIL (esta en el venv del repo) + sips/iconutil (macOS de serie).
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
PNG = HERE / "appicon_1024.png"
ICONSET = HERE / "AppIcon.iconset"
ICNS = HERE / "AppIcon.icns"

S = 1024          # lienzo logico
SS = 4            # supersampling: se dibuja a 4096 y se reduce con LANCZOS
# FULL-BLEED a proposito, MEDIDO el 2026-07-25 en este Mac (macOS 26 / Darwin 25.5)
# renderizando el icono que resuelve LaunchServices (NSWorkspace.icon(forFile:)) para
# cuatro variantes en bundles de prueba:
#   MARGIN=100 r=184 (rejilla Apple clasica) -> macOS 26 lo mete en una BANDEJA CLARA
#                                               y lo encoge: sale "icono dentro de icono"
#   MARGIN=0   r=110                         -> misma bandeja clara (feo)
#   MARGIN=0   r=0  y  MARGIN=0 r=230        -> el sistema lo RECORTA con su squircle: limpio
# Se elige r=230 (no 0) para que en macOS < 26, donde NO hay recorte automatico, el
# icono siga saliendo redondeado en vez de un cuadrado duro.
MARGIN = 0
RADIUS = 230

BG_TOP = (19, 28, 39)
BG_BOT = (7, 11, 17)
BEZEL = (44, 60, 80)
RING = (60, 83, 108)        # claro a proposito: a 16 px el anillo casi se pierde
TICK = (140, 162, 183)
NORTH = (35, 224, 140)      # verde: la mitad que apunta (arriba/derecha = alcista)
SOUTH = (70, 88, 108)       # gris azulado: la cola
HUB_FILL = (10, 15, 21)
HUB_EDGE = (185, 201, 214)

# La aguja apunta arriba-y-a-la-derecha (NE): direccion inequivoca a 16 px.
ANGLE_DEG = 35.0
NEEDLE_TIP = 312.0          # largo de la mitad norte desde el centro
NEEDLE_TAIL = 264.0         # largo de la cola
NEEDLE_HALF_W = 84.0        # semianchura del rombo en el centro


def _px(v: float) -> float:
    return v * SS


def _rounded_rect_mask() -> Image.Image:
    mask = Image.new("L", (S * SS, S * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [_px(MARGIN), _px(MARGIN), _px(S - MARGIN), _px(S - MARGIN)],
        radius=_px(RADIUS), fill=255,
    )
    return mask


def _vertical_gradient(size: int) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT))
    return grad.resize((size, size), Image.BILINEAR)


def build_png() -> Path:
    n = S * SS
    cx = cy = _px(S / 2)

    base = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    body = _vertical_gradient(n).convert("RGBA")
    base.paste(body, (0, 0), _rounded_rect_mask())

    d = ImageDraw.Draw(base)

    # bisel interior: da volumen sin adornos (solo si hay margen que biselar)
    if MARGIN >= 16 and RADIUS >= 16:
        d.rounded_rectangle(
            [_px(MARGIN + 8), _px(MARGIN + 8), _px(S - MARGIN - 8), _px(S - MARGIN - 8)],
            radius=_px(RADIUS - 8), outline=BEZEL + (150,), width=round(_px(4)),
        )

    # anillo de la brujula
    r_ring, w_ring = _px(348), round(_px(22))
    d.ellipse([cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring],
              outline=RING + (255,), width=w_ring)

    # marcas cardinales: 4 barras gruesas cruzando el anillo (sin letras)
    for ang in (0, 90, 180, 270):
        a = math.radians(ang)
        ux, uy = math.sin(a), -math.cos(a)
        r0, r1 = _px(316), _px(380)
        d.line([cx + ux * r0, cy + uy * r0, cx + ux * r1, cy + uy * r1],
               fill=TICK + (255,), width=round(_px(30)))

    # aguja bicolor
    a = math.radians(ANGLE_DEG)
    ux, uy = math.sin(a), -math.cos(a)          # direccion NE
    px_, py_ = -uy, ux                          # perpendicular
    hw = _px(NEEDLE_HALF_W)
    left = (cx + px_ * hw, cy + py_ * hw)
    right = (cx - px_ * hw, cy - py_ * hw)
    tip = (cx + ux * _px(NEEDLE_TIP), cy + uy * _px(NEEDLE_TIP))
    tail = (cx - ux * _px(NEEDLE_TAIL), cy - uy * _px(NEEDLE_TAIL))

    # halo verde detras de la mitad norte (legibilidad a tamano pequeno)
    glow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon([tip, left, right], fill=NORTH + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(_px(16)))
    base = Image.alpha_composite(base, glow)
    d = ImageDraw.Draw(base)

    d.polygon([tail, left, right], fill=SOUTH + (255,))
    d.polygon([tip, left, right], fill=NORTH + (255,))

    # buje central
    r_hub = _px(58)
    d.ellipse([cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub],
              fill=HUB_FILL + (255,), outline=HUB_EDGE + (255,), width=round(_px(10)))

    out = base.resize((S, S), Image.LANCZOS)
    PNG.parent.mkdir(parents=True, exist_ok=True)
    out.save(PNG)
    return PNG


SIZES = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def build_icns() -> Path:
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True)
    for name, size in SIZES:
        dst = ICONSET / name
        subprocess.run(["sips", "-z", str(size), str(size), str(PNG), "--out", str(dst)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)], check=True)
    return ICNS


if __name__ == "__main__":
    png = build_png()
    icns = build_icns()
    print(f"OK  {png}  ({png.stat().st_size} B)")
    print(f"OK  {icns}  ({icns.stat().st_size} B)")
    sys.exit(0)
