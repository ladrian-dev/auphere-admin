"""El outbox de avisos al teléfono — spec 031, R8.2 a R8.5 (research D6).

``enqueue`` escribe un ``client_push_events`` **en la transacción del
llamante**: el escalado, el mensaje entrante, el aviso de saldo. El worker
(``push-dispatcher``) solo ve lo confirmado, así que un hecho que se deshace no
avisa de nada (R8.5), y la clave de deduplicación hace que un hecho sea un
evento por mucho que se repita.

**Sin contenido.** Solo referencias: el texto del aviso se compone al repartir,
con los datos de ese momento (``push_texts``).
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import NOTICE_KINDS, ClientPushEvent, Conversation

log = structlog.get_logger(__name__)


async def enqueue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    kind: str,
    dedupe_key: str,
    conversation_id: uuid.UUID | None = None,
    notification_id: uuid.UUID | None = None,
    target_principal_id: str | None = None,
) -> None:
    """Deja el evento. Idempotente por ``(tenant_id, dedupe_key)``.

    ``ON CONFLICT DO NOTHING`` y no un savepoint: un hecho repetido no es un
    error del llamante, y su transacción no puede quedar marcada por ello.
    """
    if kind not in NOTICE_KINDS:  # pragma: no cover - error de programación
        raise ValueError(f"unknown notice kind: {kind!r}")
    stmt = (
        insert(ClientPushEvent)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            kind=kind,
            conversation_id=conversation_id,
            notification_id=notification_id,
            target_principal_id=target_principal_id,
            dedupe_key=dedupe_key[:160],
        )
        .on_conflict_do_nothing(constraint="uq_client_push_events_dedupe")
    )
    await session.execute(stmt)
    log.debug("push_events.enqueued", tenant_id=str(tenant_id), kind=kind)


async def enqueue_message_for_you(
    session: AsyncSession, conversation: Conversation, *, inbound_id: uuid.UUID
) -> bool:
    """R8.3: el contacto escribe en una conversación que **atiende una persona**
    → aviso solo a esa persona. Lo llama el despachador del worker dentro de la
    transacción del entrante. Con el agente atendiendo, o sin nadie asignado,
    no hay a quién avisar. Las burbujas plegadas son un solo entrante: un aviso.
    """
    if conversation.agent_active or not conversation.assigned_user_id:
        return False
    await enqueue(
        session,
        tenant_id=conversation.tenant_id,
        kind="inbox.message_for_you",
        conversation_id=conversation.id,
        target_principal_id=conversation.assigned_user_id,
        dedupe_key=f"inbox.message:{inbound_id}",
    )
    return True


__all__ = ["enqueue", "enqueue_message_for_you"]
