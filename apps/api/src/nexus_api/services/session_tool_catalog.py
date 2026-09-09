"""El documento del catálogo de sesión — Requisitos 5.1 y 14.1.

Es lo que la edición pide en cada turno para saber qué herramientas publica. La
forma está fijada en `specs/001-puesto-trabajo-partner/contracts/console-mcp.md`.

**De dónde sale.** Del catálogo **declarativo** del companion — código de Auphere,
donde *«añadir una herramienta es añadir una fila»*—, y **no** de
`agent_config.tools`, que sí edita el partner pero pertenece a su agente de
cliente final. Son dos listas blancas para dos agentes distintos, y confundirlas
era el riesgo que el Requisito 5.4 cierra.

**Qué se declara y qué se calla.** Solo se avala `reaches_network: false` de lo
que se puede avalar: las `console.*` llaman a nuestra propia API y no leen
contenido externo. De todo lo demás se calla — y callarse significa «alcanza la
red» (Requisito 14.2). Un `false` por defecto convertiría el desconocimiento en
permiso, que es exactamente la clase de error que §III existe para evitar.
"""

from __future__ import annotations

from typing import Any

from nexus_api.companion.tools.catalog import ALL_TOOLS

#: Prefijo de lo que llama a nuestra propia API. Es lo único que podemos avalar.
_VOUCHED_PREFIX = "console."


def declared_reach(tool_name: str) -> bool | None:
    """``False`` si podemos avalar que no lee la web; ``None`` si no lo sabemos.

    Nunca devuelve ``True``: si algo alcanza la red, quien lo sepa es quien lo
    declara — aquí lo correcto es callarse, y el consumidor ya trata el silencio
    como el caso peligroso.
    """
    return False if tool_name.startswith(_VOUCHED_PREFIX) else None


def build_session_catalog() -> dict[str, Any]:
    """El documento, con la forma exacta que el contrato fija."""
    tools: list[dict[str, Any]] = []
    for spec in ALL_TOOLS:
        entry: dict[str, Any] = {"name": spec.name}
        reach = declared_reach(spec.name)
        if reach is not None:
            entry["reaches_network"] = reach
        tools.append(entry)
    return {"tools": tools}


__all__ = ["build_session_catalog", "declared_reach"]
