"""El contrato que lee la app Auphere Customers — spec 031, research D14.

Exporta el OpenAPI de la API **filtrado** a lo que usa el teléfono
(``/console/lite/*`` y ``/app/*``) con los esquemas que esas rutas citan, nada
más. La app genera sus tipos de este archivo (``apps/mobile/scripts/
gen-schema.ts``), así que una ruta que cambie de forma rompe el ``tsc`` de la
app el mismo día en vez de en el teléfono de una persona.

Uso:

    uv run python scripts/export_openapi.py            # escribe el archivo
    uv run python scripts/export_openapi.py --check    # falla si difiere

``--check`` es lo que corre ``./scripts/verify.sh``: el JSON confirmado tiene
que ser el que sale de la API de esta rama.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PREFIXES = ("/console/lite", "/app/")
OUT = Path(__file__).resolve().parents[3] / "apps" / "mobile" / "src" / "api" / "openapi.json"
_REF = re.compile(r'"#/components/schemas/([^"]+)"')


def _referenced(doc: dict[str, Any], seeds: set[str]) -> set[str]:
    """Cierre transitivo de los esquemas citados desde ``seeds``."""
    schemas: dict[str, Any] = doc.get("components", {}).get("schemas", {})
    seen: set[str] = set()
    todo = list(seeds)
    while todo:
        name = todo.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        todo.extend(_REF.findall(json.dumps(schemas[name])))
    return seen


def lite_contract() -> dict[str, Any]:
    from nexus_api.main import app

    doc = app.openapi()
    paths = {p: v for p, v in doc["paths"].items() if p.startswith(PREFIXES)}
    names = _referenced(doc, set(_REF.findall(json.dumps(paths))))
    schemas = doc.get("components", {}).get("schemas", {})
    return {
        "openapi": doc["openapi"],
        "info": {"title": "Nexus — Consola Lite (teléfono)", "version": doc["info"]["version"]},
        "paths": dict(sorted(paths.items())),
        "components": {"schemas": {n: schemas[n] for n in sorted(names)}},
    }


def render() -> str:
    return json.dumps(lite_contract(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta el contrato del teléfono.")
    parser.add_argument(
        "--check", action="store_true", help="falla si el archivo confirmado difiere"
    )
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(
                f"{OUT} no es el contrato de esta rama: corre scripts/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"escrito {OUT.relative_to(OUT.parents[3])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
