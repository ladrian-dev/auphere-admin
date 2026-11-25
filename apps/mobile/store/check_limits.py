"""Check the store texts against the stores' length limits.

    python3 apps/mobile/store/check_limits.py

Every heading of `app-store/ficha.md` and `play/ficha.md` that ends in «(N)»
declares the limit of the text under it, up to the next heading. The App Store
counts characters (name 30, subtitle 30, promotional text 170, description
4000, keywords 100); Play too (name 30, short description 80, full
description 4000, release notes 500). Exits 1 if any text is over its limit.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
HEADING = re.compile(r"^#{2,4} (.+?) \((\d+)\)\s*$")
APP_NAME_WORDS = {"auphere", "customers"}

failed = False
for ficha in (HERE / "app-store/ficha.md", HERE / "play/ficha.md"):
    lines = ficha.read_text(encoding="utf-8").splitlines()
    section = ""
    for i, line in enumerate(lines):
        if line.startswith("## ") and not HEADING.match(line):
            section = line[3:].strip()
        m = HEADING.match(line)
        if not m:
            continue
        title, limit = m.group(1), int(m.group(2))
        body: list[str] = []
        for nxt in lines[i + 1 :]:
            if nxt.startswith("#"):
                break
            body.append(nxt)
        text = "\n".join(body).strip()
        n = len(text)
        ok = 0 < n <= limit
        failed |= not ok
        print(f"{'ok ' if ok else 'MAL'} {ficha.parent.name}/{ficha.name} · {section} · {title}: {n}/{limit}")
        if title.lower().startswith(("palabras clave", "keywords")):
            words = text.split(",")
            if any(w != w.strip() for w in words):
                failed = True
                print("    MAL: espacios junto a las comas; Apple los cuenta")
            repeated = APP_NAME_WORDS & {w.strip().lower() for w in words}
            if repeated:
                failed = True
                print(f"    MAL: {sorted(repeated)} ya está en el nombre; Apple no lo necesita")
sys.exit(1 if failed else 0)
