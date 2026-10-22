import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(sys.argv[1])
out = root / "apps/mobile/store/play"
caps = root / "specs/044-la-app-con-reservas/evidence/capturas"
BG = (3, 34, 33)        # brandGround #032221
GREEN = (44, 194, 149)  # primary #2CC295
SOFT = (170, 203, 196)  # accentSoft #AACBC4

icon = Image.open(root / "apps/mobile/assets/images/icon.png").convert("RGBA")
icon.resize((512, 512), Image.LANCZOS).save(out / "icon-512.png")

fg = Image.new("RGB", (1024, 500), BG)
mark = Image.open(root / "apps/mobile/assets/images/android-icon-foreground.png").convert("RGBA")
bbox = mark.getbbox(); mark = mark.crop(bbox)
h = 200; mark = mark.resize((int(mark.width * h / mark.height), h), Image.LANCZOS)
fg.paste(mark, (80, (500 - h) // 2), mark)
font = "/System/Library/Fonts/SFNS.ttf"
title = ImageFont.truetype(font, 54); title.set_variation_by_name("Bold") if hasattr(title, "set_variation_by_name") else None
sub = ImageFont.truetype(font, 28)
d = ImageDraw.Draw(fg)
x = 80 + mark.width + 48
d.text((x, 180), "Auphere Customers", font=title, fill=(241, 247, 246))
d.text((x, 258), "Tus clientes, tus reservas y tu", font=sub, fill=SOFT)
d.text((x, 296), "consumo, estés donde estés.", font=sub, fill=SOFT)
fg.save(out / "feature-1024x500.png")

shots = [
    ("ios26-13-api043-inicio-servicios-claro.png", "1-inicio"),
    ("ios26-13-api043-reservas-servicios-dia-claro.png", "2-reservas-dia"),
    ("ios26-13-reserva-hoja-completa-claro.png", "3-reserva"),
    ("ios26-13-api043-reservas-aforo-dia-claro.png", "4-aforo"),
    ("ios26-13-reserva-nueva-aforo-claro.png", "5-nueva-reserva"),
    ("ios26-13-bandeja-esperan-arriba-claro.png", "6-bandeja"),
    ("ios26-13-conversacion-espera-desde-claro.png", "7-conversacion"),
]
SHEETS = {"3-reserva", "5-nueva-reserva"}  # a sheet starts at the top: keep it, cut the bottom
for src, name in shots:
    im = Image.open(caps / src).convert("RGB")
    w, hh = im.size
    top = 0 if name in SHEETS else 315  # status bar and the dev client's tools button
    im = im.crop((0, top, w, top + round(w * 16 / 9)))  # 9:16, as Play asks
    im.save(out / f"phone-{name}.png")
    print(name, im.size)
print("icon", Image.open(out / "icon-512.png").size, "feature", fg.size)
