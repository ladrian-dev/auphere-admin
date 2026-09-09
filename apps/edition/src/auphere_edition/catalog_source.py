"""La fuente del catálogo: la API, por HTTP — Requisitos 5.1 y 5.3.

La edición corre en la máquina del partner y no comparte proceso con el plano de
control, así que el catálogo se pide por HTTP. Sin dependencias: `urllib` de la
librería estándar basta y evita una lectura de licencia más en una máquina ajena.

**Todo fallo acaba en `CatalogUnavailable`.** Red caída, cuerpo ilegible, documento
con otra forma, una entrada sin nombre: todos significan lo mismo —*no puedo
garantizar qué herramientas tiene esta sesión*— y R5.3 dice qué hacer con eso. Servir
un catálogo a medias sería afirmar algo que no sabemos.

Contrato del documento, en `contracts/console-mcp.md`:

    {"tools": [{"name": "console.clients.list", "reaches_network": false}, ...]}

``reaches_network`` ausente se conserva como ``None`` a propósito: no se rellena con
``False``. Es lo que hace que el Requisito 14.2 muerda — sin declarar cuenta como que
alcanza la red.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from auphere_edition.catalog import CatalogSource, CatalogUnavailable, Tool

DEFAULT_TIMEOUT_SECONDS = 10


def http_catalog_source(
    base_url: str,
    *,
    token: str,
    path: str = "/console/session/tool-catalog",
    opener: Callable[..., Any] = urlopen,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> CatalogSource:
    """Devuelve una fuente que pide el catálogo a la API en cada turno."""

    def fetch() -> list[Tool]:
        request = Request(  # noqa: S310 — el esquema lo fija el llamante, no la red
            f"{base_url.rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        try:
            with opener(request, timeout=timeout) as response:
                document = json.loads(response.read())
        except Exception as exc:  # noqa: BLE001 — cualquier fallo es "no se puede garantizar"
            raise CatalogUnavailable(f"no se pudo pedir el catálogo a la API: {exc}") from exc

        entries = document.get("tools") if isinstance(document, dict) else None
        if not isinstance(entries, list):
            raise CatalogUnavailable("el documento del catálogo no tiene la forma acordada")

        tools: list[Tool] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise CatalogUnavailable("una entrada del catálogo no tiene nombre")
            reach = entry.get("reaches_network", None)
            tools.append(Tool(str(entry["name"]), reach if isinstance(reach, bool) else None))
        return tools

    return fetch


__all__ = ["DEFAULT_TIMEOUT_SECONDS", "http_catalog_source"]
