"""Spec 082 (requisitos 1.4 a 1.6): ``reservations.changed`` tras el commit.

``core.add_event`` llama a :func:`mark_changed` en cada escritura que deja
historial: crear, mover, cancelar y cada cambio de estado, venga de la consola,
del agente, de la lista de espera o de los automatismos. Así el aviso alcanza a
la API, al MCP y al worker sin tocar sus rutas ni sus herramientas.

- Sale **después** del commit exterior y nunca si se deshace: lo registra
  ``business.writes.after_commit``, que además descarta lo registrado dentro de
  un *savepoint* que se deshace.
- **Una vez por negocio y por transacción.** Se registra en cada llamada y se
  deduplica **al publicar**: si se deduplicara al registrar, un *savepoint*
  deshecho se llevaría el único registro y un cambio posterior de la misma
  transacción quedaría sin aviso.
- La publicación es una tarea del bucle: no retrasa la respuesta y no puede
  tumbarla (``publish_reservations_changed`` nunca lanza).
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

_SENT: Final = "nexus.reservas.changed"


def mark_changed(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Pide el aviso de ``tenant_id`` para cuando la transacción se confirme."""
    from nexus_api.services.business.writes import after_commit

    if tenant_id is None:  # pragma: no cover - una reserva siempre es de un negocio
        return
    sync = session.sync_session
    root = sync.get_transaction()
    entry: tuple[object, set[uuid.UUID]] | None = sync.info.get(_SENT)
    if entry is None or root is None or entry[0] is not root:
        # Una transacción nueva (o ninguna aún): su propio registro de avisos.
        entry = (root, set())
        sync.info[_SENT] = entry
    sent = entry[1]

    async def publish() -> None:
        if tenant_id in sent:
            return
        sent.add(tenant_id)
        from nexus_api.services.inbox_stream import publish_reservations_changed

        await publish_reservations_changed(None, tenant_id=tenant_id)

    after_commit(session, publish)


__all__ = ["mark_changed"]
