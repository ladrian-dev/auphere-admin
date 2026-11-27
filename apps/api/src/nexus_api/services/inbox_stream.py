"""Tiempo real de la Bandeja — spec 030 (plan D17, contrato ``realtime.md``).

Un canal de pub/sub por cliente, ``inbox:{tenant_id}``. Lo escriben quienes
cambian algo que la Bandeja pinta —el worker al guardar un mensaje, el
webhook de Meta al cambiar un estado de entrega, la API en cada acción de la
Bandeja o del admin— y lo lee la SSE lite, **solo** para el cliente de la
sesión.

Los mensajes no llevan cuerpo: dicen qué cambió (``conversation.updated``,
``message.new``, ``message.status``) y la consola vuelve a pedirlo. Así un
canal filtrado no filtra conversaciones, y la Bandeja nunca pinta algo que no
haya leído por su ruta con RLS.

Publicar no falla nunca hacia fuera: el tiempo real es comodidad, no una
frontera; si Redis no está, la consola sondea (y lo dice).

Spec 082: el mismo canal lleva ``reservations.changed`` («algo cambió en
Reservas»), sin ningún dato de la reserva ni del cliente final. Lo publica
``reservations.live`` después del commit de cualquier escritura que deja
historial (``core.add_event``), y la línea solo lo reenvía a quien tiene el
módulo ``reservas``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

EVENTS = frozenset({"conversation.updated", "message.new", "message.status"})
#: Spec 082 (contrato ``realtime-082.md``): un hecho sin datos, del negocio.
RESERVATIONS_EVENT = "reservations.changed"


def inbox_channel(tenant_id: uuid.UUID) -> str:
    return f"inbox:{tenant_id}"


async def publish_inbox_event(
    redis: Redis | None,
    *,
    tenant_id: uuid.UUID,
    event: str,
    conversation_id: uuid.UUID,
    **fields: Any,
) -> None:
    """Publica ``event`` en el canal del cliente. Nunca lanza."""
    if event not in EVENTS:  # pragma: no cover - error de programación
        raise ValueError(f"unknown inbox event: {event!r}")
    if redis is None:
        try:
            from nexus_api.core.redis_client import get_redis

            redis = get_redis()
        except Exception as exc:  # pragma: no cover - defensivo
            log.warning("inbox_stream.no_redis", error=str(exc))
            return
    body: dict[str, Any] = {
        "event": event,
        "conversation_id": str(conversation_id),
        "at": datetime.now(UTC).isoformat(),
    }
    body.update({k: v for k, v in fields.items() if v is not None})
    try:
        await redis.publish(inbox_channel(tenant_id), json.dumps(body, default=str))
    except Exception as exc:
        log.warning("inbox_stream.publish_failed", tenant_id=str(tenant_id), error=str(exc))


async def publish_reservations_changed(redis: Redis | None, *, tenant_id: uuid.UUID) -> None:
    """Spec 082 (1.4, 1.6): «algo cambió en Reservas», en el canal del negocio.
    Sin id de reserva, sin nombre ni teléfono: quien lo oye vuelve a leer por
    sus rutas con RLS. Nunca lanza."""
    if redis is None:
        try:
            from nexus_api.core.redis_client import get_redis

            redis = get_redis()
        except Exception as exc:  # pragma: no cover - defensivo
            log.warning("inbox_stream.no_redis", error=str(exc))
            return
    body = {"event": RESERVATIONS_EVENT, "at": datetime.now(UTC).isoformat()}
    try:
        await redis.publish(inbox_channel(tenant_id), json.dumps(body))
    except Exception as exc:
        log.warning("inbox_stream.publish_failed", tenant_id=str(tenant_id), error=str(exc))


__all__ = [
    "EVENTS",
    "RESERVATIONS_EVENT",
    "inbox_channel",
    "publish_inbox_event",
    "publish_reservations_changed",
]
