"""Google Play assets for Auphere Customers 1.3.0 (spec 069).

    uv run --with pillow python apps/mobile/store/play_assets.py <repo root> <raw captures folder>

The raw captures are the emulator's own screenshots (Pixel 9, 1080 × 2424), taken
with the example business, in Spanish, with the Santiago time zone and the
status bar in demo mode (see store/README.md). This script only drops the alpha
channel and checks the size Play accepts; it does not crop or retouch.

Play's rules (Play Console Help, «Add preview assets to showcase your app»):
2 to 8 phone screenshots, JPEG or 24-bit PNG without alpha, each side between
320 and 3840 px, the long side at most 2.3 times the short one; the feature
graphic is 1024 × 500 and the icon 512 × 512, 32-bit PNG.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(sys.argv[1])
raw = Path(sys.argv[2])
mobile = root / "apps/mobile"
out = mobile / "store/play"

# Tokens (packages/ui/src/styles/tokens.css, light): brandGround, highlight, accentSoft.
BG = (3, 34, 33)
INK = (241, 247, 246)
SOFT = (170, 203, 196)
FONTS = mobile / "assets/fonts/helvena"

# Icon: the same image the app installs with.
icon = Image.open(mobile / "assets/images/icon.png").convert("RGBA")
icon.resize((512, 512), Image.Resampling.LANCZOS).save(out / "icon-512.png")

# Feature graphic, one per listing language. Helvena, like the app (069 R1.4);
# never SF Pro, whose licence only covers mock-ups of Apple software.
TAGLINE = {
    "es": ("Las conversaciones y las reservas", "de tu negocio, en el teléfono."),
    "en": ("Your business's conversations", "and bookings, on your phone."),
}
mark = Image.open(mobile / "assets/images/android-icon-foreground.png").convert("RGBA")
mark = mark.crop(mark.getbbox())
h = 200
mark = mark.resize((int(mark.width * h / mark.height), h), Image.Resampling.LANCZOS)
title = ImageFont.truetype(str(FONTS / "Helvena-Semibold.ttf"), 54)
sub = ImageFont.truetype(str(FONTS / "Helvena-Regular.ttf"), 28)
for lang, (line1, line2) in TAGLINE.items():
    fg = Image.new("RGB", (1024, 500), BG)
    fg.paste(mark, (80, (500 - h) // 2), mark)
    d = ImageDraw.Draw(fg)
    x = 80 + mark.width + 48
    d.text((x, 180), "Auphere Customers", font=title, fill=INK)
    d.text((x, 258), line1, font=sub, fill=SOFT)
    d.text((x, 296), line2, font=sub, fill=SOFT)
    name = "feature-1024x500.png" if lang == "es" else f"feature-1024x500-{lang}.png"
    fg.save(out / name)
    print(name, fg.size)

# Phone screenshots, in the order the listing shows them (the same as the App Store's).
SHOTS = [
    "01-inicio",
    "02-bandeja",
    "03-conversacion-espera",
    "04-conversacion-respondes",
    "05-reservas",
    "06-consumo",
    "07-avisos",
]
for old in out.glob("phone-*.png"):
    old.unlink()
for i, name in enumerate(SHOTS, start=1):
    im = Image.open(raw / f"{name}.png").convert("RGB")
    w, hh = im.size
    assert 320 <= min(w, hh) and max(w, hh) <= 3840, (name, im.size)
    assert max(w, hh) / min(w, hh) <= 2.3, (name, im.size)
    im.save(out / f"phone-{i}-{name[3:]}.png", optimize=True)
    print(f"phone-{i}-{name[3:]}.png", im.size)
print("icon", Image.open(out / "icon-512.png").size)
