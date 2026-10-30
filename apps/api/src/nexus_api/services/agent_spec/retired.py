"""Las herramientas retiradas y su sustituta — spec 048 (requisitos 2 y 3).

``booking.*`` escribe en ``appointments``, una agenda que el negocio no ve. Se
retira en dos pasos: ahora nadie puede añadirla (el validador la rechaza con
``tool_retired`` y propone su sustituta) y «Pasar a Reservas» la cambia por
``reservas.*`` en el borrador de cada agente; el borrado final llega cuando
ninguna versión la nombre (requisito 5). Hasta entonces el runtime la sigue
ejecutando para quien la tiene.

Aquí vive solo lo puro —el mapa y la reescritura de textos—, sin base ni
modelos, para que lo compartan el validador, el paso a Reservas y las pruebas.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final

#: Cada herramienta retirada → la de Reservas que hace lo mismo.
RETIRED_TOOLS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "booking.check_availability": "reservas.find_slots",
        "booking.create_appointment": "reservas.create",
        "booking.modify_appointment": "reservas.reschedule",
        "booking.cancel_appointment": "reservas.cancel",
        "booking.get_appointments": "reservas.list_mine",
    }
)
RETIRED_PREFIX: Final = "booking."

#: Un nombre de herramienta retirada dentro de un texto, entero (no
#: ``policies.booking.x``), o la familia escrita como ``booking.*``.
_MENTION: Final = re.compile(
    r"(?<![\w.])(" + "|".join(re.escape(n) for n in RETIRED_TOOLS) + r"|booking\.\*)(?![\w])"
)


def replacement(name: str) -> str | None:
    """La sustituta de ``name`` si está retirada; ``None`` si no lo está."""
    return RETIRED_TOOLS.get(name)


def names_retired(tools: Iterable[str]) -> bool:
    return any(t in RETIRED_TOOLS for t in tools)


def mentions_retired(text: str | None) -> bool:
    return bool(text and _MENTION.search(text))


def rewrite_text(text: str) -> str:
    """El texto con cada herramienta retirada cambiada por su sustituta."""

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        return "reservas.*" if name == "booking.*" else RETIRED_TOOLS[name]

    return _MENTION.sub(sub, text)


def rewrite_tools(tools: Iterable[str]) -> list[str]:
    """La lista con cada retirada cambiada por su sustituta, sin repetir y en
    el mismo orden."""
    return list(dict.fromkeys(RETIRED_TOOLS.get(t, t) for t in tools))


def rewrite_doc(node: Any) -> Any:
    """Un documento JSON (el AgentSpec) con las retiradas cambiadas en cada
    texto; una lista de nombres que cambió, sin repetir (``reservas.create``
    ya podía estar). Devuelve una copia."""
    if isinstance(node, str):
        return rewrite_text(node)
    if isinstance(node, Mapping):
        return {key: rewrite_doc(value) for key, value in node.items()}
    if isinstance(node, list):
        items = [rewrite_doc(value) for value in node]
        if items != node and all(isinstance(i, str) for i in items):
            return list(dict.fromkeys(items))
        return items
    return node


def doc_names_retired(node: Any) -> bool:
    """¿Nombra el documento alguna herramienta retirada, en una lista o en un
    texto?"""
    if isinstance(node, str):
        return node in RETIRED_TOOLS or mentions_retired(node)
    if isinstance(node, Mapping):
        return any(doc_names_retired(v) for v in node.values())
    if isinstance(node, list):
        return any(doc_names_retired(v) for v in node)
    return False


__all__ = [
    "RETIRED_PREFIX",
    "RETIRED_TOOLS",
    "doc_names_retired",
    "mentions_retired",
    "names_retired",
    "replacement",
    "rewrite_doc",
    "rewrite_text",
    "rewrite_tools",
]
