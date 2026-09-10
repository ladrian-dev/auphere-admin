"""Pendientes — lo que los teammates de una persona esperan de ella (spec 003, R5).

Dos cosas viven aquí:

* **La lectura**: las acciones ``proposed`` de hilos con teammate **de esta
  persona**, con su nivel, su tarea y si el rol puede decidirlas. La RLS del
  hilo ya deja fuera lo de los demás; la consulta solo añade «con teammate»,
  que es lo que separa Pendientes del cajón de la consola (supuesto cerrado:
  el Companion web sigue aprobando dentro de su chat).

* **El aviso**: un canal de Redis **por persona**. Decidir en el hilo tiene que
  quitar la tarjeta de la bandeja —y al revés— en menos de dos segundos
  (CE-003), y sondear cada dos segundos con doscientos pendientes es caro y
  llega tarde. El canal no lleva historia: es un aviso, y la verdad sigue
  siendo ``GET /console/teammates/inbox``, que el cliente vuelve a pedir en
  cada (re)conexión.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.companion.tools.actions import STATUS_PROPOSED
from nexus_api.db.models import PartnerTenant, Teammate
from nexus_api.db.models.companion import CompanionAction, CompanionThread

log = structlog.get_logger(__name__)

#: Qué permiso exige aplicar cada tipo de acción. Es el permiso del router que
#: la aplica: la tarjeta dice «no puedes decidir esto» **antes**, en vez de
#: dejar a la persona confirmar y comerse un 403 del backend (§V).
KIND_PERMISSION: dict[str, str] = {
    "client": "clients:write",
    "prompt": "agents:write",
    "policy": "agents:write",
    "tools": "agents:write",
    "skills": "agents:write",
    "publish": "agents:write",
    "channel_role": "channels:write",
    "usage_alerts": "usage:manage",
    "allocation": "usage:write",
    "model": "agents:write",
    "knowledge": "knowledge:write",
    "pack": "agents:write",
    "invite": "team:manage",
    "local_exec": "teammates:use",
}


def inbox_channel(principal_id: str) -> str:
    """El canal de avisos de una persona. Uno por persona, nunca por partner."""
    return f"teammates:inbox:{principal_id}"


async def publish_inbox_changed(
    redis: Redis, *, principal_id: str, action_id: uuid.UUID, decision: str
) -> None:
    """Avisa a las pantallas de esta persona de que una tarjeta ya no espera."""
    payload = {"action_id": str(action_id), "decision": decision, "by": principal_id}
    try:
        await redis.publish(inbox_channel(principal_id), json.dumps(payload))
    except Exception:  # pragma: no cover - un aviso perdido no tumba la decisión
        log.warning("teammates.inbox.publish_failed", action_id=str(action_id))


async def publish_task_state(
    redis: Redis, *, principal_id: str, task_id: uuid.UUID, state: str, cause: str
) -> None:
    """El estado de una tarea, para el roster de las pantallas abiertas."""
    payload = {"task_id": str(task_id), "state": state, "cause": cause}
    try:
        await redis.publish(inbox_channel(principal_id), json.dumps({"task": payload}))
    except Exception:  # pragma: no cover
        log.warning("teammates.task_state.publish_failed", task_id=str(task_id))


#: Cada cuánto se manda un `ping` para que un proxy no cierre la conexión.
PING_SECONDS = 15.0

#: Cada cuánto se pregunta al canal. Corto **y separado del `ping`** a
#: propósito: hay clientes de Redis cuyo ``get_message(timeout=…)`` largo no
#: despierta con la publicación, así que la espera se hace a base de sondeos
#: cortos y el latido se cuenta aparte. Con un solo `get_message` de quince
#: segundos, un aviso podía tardar quince segundos en verse.
POLL_SECONDS = 0.25


async def inbox_events(redis: Redis, principal_id: str) -> AsyncIterator[str]:
    """El flujo SSE de la bandeja de una persona. **Sin historia.**

    Es un aviso, no la verdad: quien lo escucha vuelve a pedir
    ``GET /console/teammates/inbox`` en cada (re)conexión, y por eso un evento
    perdido mientras el proxy cortaba no deja una tarjeta vieja en pantalla.

    El primer `ping` sale **antes** de esperar nada: dice que la suscripción ya
    está hecha, que es lo único que permite a quien escucha saber cuándo puede
    dejar de sondear.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(inbox_channel(principal_id))
    try:
        yield "event: ping\ndata: {}\n\n"
        waited = 0.0
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_SECONDS)
            if message is None:
                waited += POLL_SECONDS
                if waited >= PING_SECONDS:
                    waited = 0.0
                    yield "event: ping\ndata: {}\n\n"
                continue
            waited = 0.0
            raw = message.get("data")
            payload = json.loads(raw if isinstance(raw, str) else raw.decode())
            if "task" in payload:
                yield f"event: task.state\ndata: {json.dumps(payload['task'])}\n\n"
            else:
                yield f"event: inbox.changed\ndata: {json.dumps(payload)}\n\n"
    except asyncio.CancelledError:  # pragma: no cover - el cliente cerró
        raise
    finally:
        await pubsub.unsubscribe(inbox_channel(principal_id))
        # ``aclose`` no está tipado en redis-py; cerrar es obligatorio igual —
        # una suscripción que sobrevive al cliente se lleva una conexión.
        await pubsub.aclose()  # type: ignore[no-untyped-call]


@dataclass(frozen=True)
class InboxItem:
    action_id: uuid.UUID
    task_id: uuid.UUID | None
    thread_id: uuid.UUID
    run_id: uuid.UUID | None
    teammate: dict[str, str]
    title: str
    level: str
    client_ref: str | None
    proposed_at: Any
    can_decide: bool
    kind: str


def _title_of(action: CompanionAction) -> str:
    payload = action.payload or {}
    title = payload.get("title")
    return str(title) if isinstance(title, str) and title else action.kind


async def list_inbox(
    session: AsyncSession, *, partner_id: uuid.UUID, permissions: frozenset[str]
) -> list[InboxItem]:
    """Lo que espera a **esta** persona. La RLS del hilo hace el filtro duro."""
    rows = (
        await session.execute(
            sa.select(CompanionAction, CompanionThread)
            .join(CompanionThread, CompanionThread.id == CompanionAction.thread_id)
            .where(
                CompanionAction.status == STATUS_PROPOSED,
                CompanionThread.teammate_id.isnot(None),
            )
            .order_by(CompanionAction.proposed_at.desc())
        )
    ).all()
    if not rows:
        return []

    teammate_ids = {t.teammate_id for _a, t in rows if t.teammate_id is not None}
    names: dict[uuid.UUID, str] = {
        row.id: row.name
        for row in (
            await session.execute(
                sa.select(Teammate.id, Teammate.name).where(Teammate.id.in_(teammate_ids))
            )
        ).all()
    }
    tenant_ids = {t.tenant_id for _a, t in rows if t.tenant_id is not None}
    refs: dict[uuid.UUID, str] = {}
    if tenant_ids:
        refs = {
            row.tenant_id: row.external_client_ref
            for row in (
                await session.execute(
                    sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref).where(
                        PartnerTenant.partner_id == partner_id,
                        PartnerTenant.tenant_id.in_(tenant_ids),
                    )
                )
            ).all()
        }

    items: list[InboxItem] = []
    for action, thread in rows:
        needed = KIND_PERMISSION.get(action.kind)
        items.append(
            InboxItem(
                action_id=action.id,
                task_id=action.task_id,
                thread_id=thread.id,
                run_id=action.run_id,
                teammate={
                    "id": str(thread.teammate_id),
                    "name": names.get(thread.teammate_id, ""),
                },
                title=_title_of(action),
                level=action.level,
                client_ref=refs.get(thread.tenant_id) if thread.tenant_id else None,
                proposed_at=action.proposed_at,
                can_decide=needed is None or needed in permissions,
                kind=action.kind,
            )
        )
    return items


__all__ = [
    "KIND_PERMISSION",
    "PING_SECONDS",
    "InboxItem",
    "inbox_channel",
    "inbox_events",
    "list_inbox",
    "publish_inbox_changed",
    "publish_task_state",
]
