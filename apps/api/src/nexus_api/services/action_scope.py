"""La frontera de aprobación — Requisito 7 (§IV de la constitución).

Hay **dos escaleras** y una línea entre ellas:

* Lo que se queda **dentro de la máquina** del partner —ejecutar un comando en
  su propio directorio— lo resuelve la escalera local del runtime. Es rápida,
  vive en el turno, y con eso basta: el alcance del daño es la máquina de quien
  aprueba.
* Todo lo que **toca a un cliente final** pasa por la aprobación durable de la
  plataforma: caduca, es idempotente y la auditoría nombra a la **persona** que
  decidió, no al agente que ejecutó.

**Lo que hace segura la clasificación no es la lista: es el defecto.** Lo que no
se reconoce cae del lado durable. Una lista de «esto es peligroso» olvida cosas y
falla abierta; una de «esto es inocuo» falla hacia el lado caro, que es el
correcto. Por eso la lista de abajo es minúscula, y hay un test que se queja si
crece — si alguien mueve la frontera, que sea diciéndolo.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from nexus_api.companion.tools.actions import is_stale
from nexus_api.db.models.companion import CompanionAction

#: 15 minutos, como dice §IV. Caducidad perezosa: se evalúa al mirar, no con un
#: reloj que alguien tenga que mantener vivo.
APPROVAL_TTL_SECONDS: float = 15 * 60

#: Herramientas cuyo efecto **empieza y acaba** en la máquina del partner.
#: Deliberadamente diminuta.
MACHINE_SCOPED_TOOLS: frozenset[str] = frozenset({"shell_local"})


class ActionScope(str, enum.Enum):
    """Dónde acaba el efecto de una acción."""

    MACHINE = "machine"
    END_CLIENT = "end_client"


def classify_tool(tool_name: str) -> ActionScope:
    """Clasifica por nombre, y **falla hacia lo durable** si no lo reconoce."""
    return ActionScope.MACHINE if tool_name in MACHINE_SCOPED_TOOLS else ActionScope.END_CLIENT


def requires_durable_approval(tool_name: str) -> bool:
    """¿Necesita la escalera de la plataforma, con `decided_by` en la auditoría?"""
    return classify_tool(tool_name) is ActionScope.END_CLIENT


def decide_pending(action: CompanionAction, *, now: datetime | None = None) -> str:
    """Resuelve una propuesta: ``pendiente`` · ``denegada`` · ``decidida``.

    **Deny-on-silence.** El silencio no aprueba: si nadie contesta dentro del
    plazo, la acción se deniega. Con la regla contraria, dejar de mirar el móvil
    aprobaría — y eso convierte una ausencia en un consentimiento.

    Una acción ya decidida no se vuelve a decidir: caducar no puede revertir un
    sí que ya se dio, porque sería reescribir la historia que la auditoría
    guarda.
    """
    if action.status != "proposed":
        return "decidida"
    if is_stale(action, APPROVAL_TTL_SECONDS, now=now or datetime.now(UTC)):
        return "denegada"
    return "pendiente"


__all__ = [
    "APPROVAL_TTL_SECONDS",
    "MACHINE_SCOPED_TOOLS",
    "ActionScope",
    "classify_tool",
    "decide_pending",
    "requires_durable_approval",
]
