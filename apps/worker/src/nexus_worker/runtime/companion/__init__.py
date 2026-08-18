"""Runtime del Companion de la consola de partners (CO-01).

El Companion es el agente que opera la consola por conversación. No es el
agente que atiende a los clientes finales (ese es el pipeline del tenant) y
**no tiene un camino privilegiado**: desde CO-02, sus herramientas llamarán
a los mismos routers ``/console/*`` que la interfaz, con el mismo principal
y los mismos permisos.

Plan de construcción: ``docs/companion/PLAN-CO-01.md``.
"""

from __future__ import annotations

from nexus_worker.runtime.companion.graph import (
    COMPANION_ROLE,
    COMPANION_TENANT_ID,
    build_companion_graph,
)
from nexus_worker.runtime.companion.prompt import (
    COMPANION_THINKING,
    SYSTEM_PROMPT,
    build_messages,
    page_context_message,
)
from nexus_worker.runtime.companion.state import (
    PHASE_LABELS,
    CompanionState,
)

__all__ = [
    "COMPANION_ROLE",
    "COMPANION_TENANT_ID",
    "COMPANION_THINKING",
    "PHASE_LABELS",
    "SYSTEM_PROMPT",
    "CompanionState",
    "build_companion_graph",
    "build_messages",
    "page_context_message",
]
