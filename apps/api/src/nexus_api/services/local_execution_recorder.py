"""De una decisión del gate a un asiento de auditoría — Requisito 8.

Existe como módulo aparte del gate por una razón: **el gate decide, esto
recuerda**, y mezclarlos haría que una decisión sin registrar pareciera posible.

La regla que gobierna el reparto: se registra lo que **ocurrió**. Una denegación
ocurrió —alguien lo intentó y se le dijo que no— y por eso deja fila. Una
petición de aprobación todavía no ha ocurrido: inventarle un asiento llenaría la
auditoría de ejecuciones que nunca existieron y haría inútil la pregunta «¿esto
se ejecutó?».
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.local_workstation import LocalExecution
from nexus_api.repositories.local_workstation import LocalExecutionRepository
from nexus_api.services.local_exec_gate import GateDecision


async def record_decision(
    session: AsyncSession, *, decision: GateDecision, device_id: uuid.UUID
) -> LocalExecution | None:
    """Registra la decisión si dejó huella. Devuelve ``None`` si no la dejó.

    ``executable`` se guarda **verbatim**: lo que interesa en un incidente es qué
    se intentó, no qué estaba permitido.
    """
    if decision.outcome != "denegada" or decision.denial_reason is None:
        return None
    return await LocalExecutionRepository(session).record_denial(
        device_id=device_id,
        executable=decision.executable,
        argv_signature=decision.argv_signature,
        denial_reason=decision.denial_reason,
    )
