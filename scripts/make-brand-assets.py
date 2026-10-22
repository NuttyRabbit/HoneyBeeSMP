#!/usr/bin/env python3
"""make-brand-assets.py - draw the social card and the icons.

The site points at five images it did not have: the Open Graph card that
Discord and the like show when a link is pasted, and the icons browsers
ask for. They are generated rather than hand-made so the wording on the
card cannot drift from the site's own.

Run it from the repo root after changing the tagline:

    python3 scripts/make-brand-assets.py

Needs Pillow, and a sans font. Adjust FONT_* below if the paths differ.
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

OUT = Path(__file__).resolve().parent.parent / "website" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

HONEY = (255, 193, 7)
BG = (11, 9, 6)
INK = (233, 228, 216)
MUTED = (168, 159, 140)

# First match wins; any reasonable sans-serif will do.
BOLD_CANDIDATES = [
    "/usr/share/fonts/google-carlito-fonts/Carlito-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
]
REG_CANDIDATES = [
    "/usr/share/fonts/google-carlito-fonts/Carlito-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
]
BOLD = next((p for p in BOLD_CANDIDATES if Path(p).exists()), BOLD_CANDIDATES[-1])
REG = next((p for p in REG_CANDIDATES if Path(p).exists()), REG_CANDIDATES[-1])


def font(path, size):
    return ImageFont.truetype(path, size)


def hexagon(draw, cx, cy, r, fill=None, outline=None, width=2):
    pts = [
        (cx + r * math.cos(math.radians(60 * i - 30)),
         cy + r * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]
    draw.polygon(pts, fill=fill, outline=outline, width=width)


# --- social card -----------------------------------------------------------
W, H = 1200, 630
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# A large, quiet hexagon on the right, cropped by the edge.
hexagon(d, 980, 315, 300, outline=(60, 48, 20), width=6)
hexagon(d, 980, 315, 210, outline=(90, 70, 20), width=4)
hexagon(d, 980, 315, 60, fill=HONEY)

d.text((80, 96), "HoneyBeeSMP", font=font(BOLD, 78), fill=HONEY)
d.text((82, 196), "Create & automation", font=font(REG, 40), fill=INK)
d.text((82, 246), "Minecraft server", font=font(REG, 40), fill=INK)
d.line([(82, 330), (430, 330)], fill=(70, 58, 30), width=3)
d.text((82, 366), "Minecraft 1.21.1  ·  NeoForge  ·  20 slots  ·  UK",
       font=font(REG, 26), fill=MUTED)
d.text((82, 470), "play.honeybeesmp.co.uk", font=font(BOLD, 34), fill=INK)
img.save(OUT / "og-image.png", optimize=True)

# --- icons -----------------------------------------------------------------
def icon(size, opaque_bg=False):
    im = Image.new("RGB" if opaque_bg else "RGBA", (size, size),
                   BG if opaque_bg else (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    stroke = max(2, size // 16)
    hexagon(dr, size / 2, size / 2, size * 0.44,
            fill=HONEY if size <= 64 else None,
            outline=HONEY, width=stroke)
    if size > 64:
        hexagon(dr, size / 2, size / 2, size * 0.26,
                outline=HONEY, width=max(2, size // 32))
        hexagon(dr, size / 2, size / 2, size * 0.10, fill=HONEY)
    else:
        hexagon(dr, size / 2, size / 2, size * 0.22,
                fill=BG if opaque_bg else (11, 9, 6, 255))
    return im


icon(512).save(OUT / "icon-512.png", optimize=True)
icon(180, opaque_bg=True).save(OUT / "icon-180.png", optimize=True)
icon(32).save(OUT / "favicon-32.png", optimize=True)
print("wrote", *(p.name for p in sorted(OUT.glob("*.png"))))
