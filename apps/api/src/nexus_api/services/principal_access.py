"""Retirar todo el acceso de una persona — spec 012, Requisito 1.

**Por qué esto es un módulo y no una función dentro de otro.** Retirar el acceso
de alguien no es una operación de identidad ni de puesto de trabajo: **las
cruza**. Sus sesiones viven en `console_auth` y las gobierna
``console_identity``; sus máquinas viven en `partner_devices` y las gobierna el
repositorio del puesto de trabajo. Meterla en cualquiera de los dos la habría
atado al lado equivocado, y la spec 011 —donde restablecer la contraseña
revoca también las máquinas— habría heredado esa atadura.

**Por qué es una sola transacción y no dos operaciones seguidas.** El estado que
no puede existir es «sesiones cerradas, máquinas vivas»: alguien cree que ha
echado a una persona y lo que ha hecho es quitarle el navegador y dejarle la
ejecución local durante las doce horas que vive la credencial. Las dos tablas
están en el mismo Postgres —``console_auth`` es un esquema, mismo engine—, así
que una transacción las cubre y el `ROLLBACK` deshace las dos.

**Por qué corre con el rol dueño.** Es mantenimiento de plataforma, igual que ya
lo era archivar las máquinas de quien pierde la pertenencia. La consecuencia hay
que decirla en voz alta: **la RLS no protege esta operación**. Lo único que
impide que alcance a otra persona es el ``WHERE`` por ``principal_id`` de las dos
mitades, y por eso eso tiene su propio test de aislamiento
(``tests/isolation/test_38_principal_access_revocation_scope.py``).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog
from nexus_api.db.models.local_workstation import REVOKED_ARCHIVADA_CONSOLA
from nexus_api.repositories.local_workstation import PartnerDeviceRepository
from nexus_api.services import console_identity

log = structlog.get_logger(__name__)

#: La acción que queda en la auditoría.
AUDIT_ACTION = "principal.access_revoked"


async def revoke_all_access(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID,
    reason: str,
    actor: str,
) -> dict[str, int]:
    """Deja fuera a una persona: sus sesiones y sus máquinas, de una vez.

    **No hace commit.** El llamante abre la transacción, porque es él quien sabe
    qué más va dentro — en la spec 011, restablecer la contraseña irá en la misma.
    Que la atomicidad dependa de la transacción del llamante es deliberado: la
    alternativa, abrir una aquí, impediría componer esto con nada.

    Devuelve cuántas sesiones y cuántas máquinas se retiraron. El recuento es
    para el asiento, no para decidir: retirar el acceso de alguien que ya no
    tenía nada abierto **no es un error**.
    """
    sessions_closed = await console_identity.end_all_sessions(session, principal_id)

    machines_archived = await PartnerDeviceRepository(session).archive_all_for_principal(
        str(principal_id), reason=REVOKED_ARCHIVADA_CONSOLA
    )

    after: dict[str, Any] = {
        "reason": reason,
        "sessions_closed": sessions_closed,
        "machines_archived": machines_archived,
    }
    session.add(
        AuditLog(
            # Fila de plataforma: una persona no es de ningún tenant.
            tenant_id=None,
            actor=actor,
            action=AUDIT_ACTION,
            target=f"principal:{principal_id}",
            after_json=after,
        )
    )
    await session.flush()

    log.info(
        "principal.access_revoked",
        principal_id=str(principal_id),
        sessions_closed=sessions_closed,
        machines_archived=machines_archived,
    )
    return {"sessions_closed": sessions_closed, "machines_archived": machines_archived}


__all__ = ["AUDIT_ACTION", "revoke_all_access"]
