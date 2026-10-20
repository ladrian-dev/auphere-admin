"""Un reintento nunca manda dos WhatsApp — spec 031, R6.4 (research D9).

La app manda cada mensaje que la persona compone con una ``Idempotency-Key``
(un UUID) que reutiliza en cada reintento. La clave se guarda en
``messages.idempotency_key`` —el índice único por tenant de la migración 0053—
y un segundo intento con la misma clave **no crea otra fila**:

* si el envío anterior existe y no falló → se devuelve tal cual (200). Va
  primero porque no envía nada, así que vale aunque la ventana de 24 h se haya
  cerrado después;
* si falló → se reintenta **la misma fila**, como ``direct_messages``, y el
  llamante comprueba antes las precondiciones, porque esta vez sí envía;
* dos peticiones a la vez → la segunda choca con el índice dentro de un
  savepoint y responde como un replay. Nunca un 500 (el precedente de
  ``direct_messages`` no lo cubría).
"""

from __future__ import annotations

import uuid
from typing import Literal

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Message, MessageStatus

#: Lo que cabe en ``messages.idempotency_key``.
MAX_KEY_LENGTH = 80


def parse_key(raw: str | None) -> str | None:
    """``None`` sin cabecera. Con cabecera, tiene que ser un UUID: 400 si no."""
    if raw is None:
        return None
    value = raw.strip()
    try:
        if len(value) > MAX_KEY_LENGTH:
            raise ValueError
        return str(uuid.UUID(value))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "idempotency_key_invalid"}
        ) from None


async def prior_send(
    session: AsyncSession, *, key: str, conversation_id: uuid.UUID
) -> Message | None:
    """El envío anterior con esta clave, si lo hay. La RLS lo limita al cliente.

    La misma clave en **otra** conversación es un error de la app (reutilizó
    una clave), y responder con el envío de otra conversación sería peor que
    rechazar: 422.
    """
    found = await session.scalar(sa.select(Message).where(Message.idempotency_key == key).limit(1))
    if found is not None and found.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "idempotency_key_reused"},
        )
    return found


def classify(prior: Message) -> Literal["replay", "revive"]:
    return "revive" if prior.status is MessageStatus.FAILED else "replay"


def revive(prior: Message) -> None:
    """Vuelve a poner en cola **la misma fila**, con todo el presupuesto de
    reintentos (``attempts = 0``). ``created_at`` no se toca: el despachador
    envía primero lo más antiguo, y un reintento va al principio."""
    prior.status = MessageStatus.PENDING
    prior.attempts = 0
    prior.failed_at = None
    prior.failure_code = None
    prior.last_error = None


__all__ = ["MAX_KEY_LENGTH", "classify", "parse_key", "prior_send", "revive"]
