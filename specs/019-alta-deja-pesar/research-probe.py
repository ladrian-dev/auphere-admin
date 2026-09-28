"""Cuántos campos necesita de verdad cada plantilla para renderizar."""
from nexus_api.services.templating.seed_templates import (
    load_seed_template, render_seed_template, SeedTemplatePlaceholderMissing,
)
import pathlib

seeds = sorted(p.stem for p in pathlib.Path("src/nexus_api/services/templating/seeds").glob("*.yaml"))
base = {"tenant.name": "Prueba", "tenant.timezone": "Europe/Madrid"}
print(f"{'plantilla':24} {'imprescindibles':>16}")
total = 0
for name in seeds:
    tpl = load_seed_template(name)
    needed, values = [], dict(base)
    for _ in range(60):
        try:
            render_seed_template(tpl, placeholders=values)
            break
        except SeedTemplatePlaceholderMissing as e:
            needed.append(e.key)
            values[e.key] = "x"
    else:
        needed.append("(no converge)")
    total += len(needed)
    print(f"{name:24} {len(needed):>16}  {' '.join(needed) if needed else '—'}")
print(f"{'TOTAL':24} {total:>16}")
