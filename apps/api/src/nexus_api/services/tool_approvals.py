"""«Preguntar antes de escribir» — spec 047, T128 (requisito 35.5; constitución
§IV, aprobación durable).

Una herramienta de escritura de una integración activada con
``ask_before_write`` no se ejecuta a la primera: se le pregunta al dueño por su
canal de avisos (la consulta de ADR-018, ``owner_consultations``) y el turno sigue
sin hacerlo. Cuando el dueño contesta, la conversación se reanuda con su respuesta
(``owner_fanout``) y, si dijo que sí, esa misma acción —la misma herramienta con
los mismos argumentos— se ejecuta **una vez**. Si dijo que no, no se hace.

La aprobación es durable: sobrevive a reinicios y no caduca en memoria.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import OwnerConsultation

Verdict = Literal["allowed", "requested", "pending", "denied"]

APPROVER: Final = "agent:approval"
_YES: Final = frozenset(
    {"si", "sí", "ok", "vale", "dale", "adelante", "aprobado", "apruebo", "confirmo", "yes"}
)
_NO: Final = frozenset({"no", "nop", "rechazo", "rechazado", "cancela", "cancelar"})


def action_hash(tool: str, args: dict[str, Any]) -> str:
    raw = json.dumps({"tool": tool, "args": args}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def verdict_of(row: OwnerConsultation) -> bool | None:
    """``True`` si el dueño aprobó, ``False`` si no, ``None`` si no se entiende."""
    if row.owner_command_kind in {"yes", "no"}:
        return row.owner_command_kind == "yes"
    words = re.findall(r"[a-záéíóúñ]+", (row.owner_response_text or "").lower())
    first = words[0] if words else ""
    if first in _YES:
        return True
    if first in _NO:
        return False
    return None


def _question(tool: str, args: dict[str, Any], agent_name: str | None) -> str:
    shown = ", ".join(f"{k}: {v}" for k, v in list(args.items())[:6] if k != "conversation_id")
    who = f"El agente {agent_name}" if agent_name else "El agente"
    text = f"{who} quiere hacer «{tool}» ({shown}). ¿Lo apruebas? Responde SÍ o NO."
    return text[:1000]


async def gate(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    tool: str,
    args: dict[str, Any],
    tenant_name: str,
    agent_name: str | None = None,
) -> Verdict:
    """Decide si la acción se ejecuta ahora. Dentro de la sesión del cliente."""
    digest = action_hash(tool, args)
    rows = (
        await session.scalars(
            sa.select(OwnerConsultation)
            .where(
                OwnerConsultation.conversation_id == conversation_id,
                OwnerConsultation.created_by == APPROVER,
                OwnerConsultation.template_params_json["action_hash"].astext == digest,
            )
            .order_by(OwnerConsultation.created_at.desc())
            .with_for_update()
        )
    ).all()
    for row in rows:
        if row.status == "answered":
            verdict = verdict_of(row)
            if verdict is True and row.result_applied_at is None:
                row.result_applied_at = datetime.now(UTC)
                await session.flush()
                return "allowed"
            if verdict is False:
                return "denied"
        if row.status in {"pending", "sent"}:
            return "pending"
    from nexus_api.repositories import OwnerConsultationRepository

    question = _question(tool, args, agent_name)
    await OwnerConsultationRepository(session).create(
        conversation_id=conversation_id,
        question_text=question,
        urgency="normal",
        expected_reply_kind="yes_no",
        template_name="auphere_owner_consult",
        template_params={
            "tenant_name": tenant_name,
            "question": question,
            "urgency": "normal",
            "action_hash": digest,
            "tool": tool,
        },
        created_by=APPROVER,
    )
    return "requested"


#: Lo que lee el modelo en cada caso: nunca promete lo que no se hizo.
MESSAGES: Final[dict[str, str]] = {
    "requested": (
        "Esta acción necesita la aprobación del negocio y ya se la pedí. No la "
        "hagas ni digas que está hecha: dile al cliente que se la confirmas en "
        "cuanto el negocio responda."
    ),
    "pending": (
        "Esta acción sigue esperando la aprobación del negocio. No la repitas: dile "
        "al cliente que todavía no hay respuesta."
    ),
    "denied": (
        "El negocio no aprobó esta acción. No la hagas; explícale al cliente que no "
        "es posible y ofrécele pasar con una persona si lo necesita."
    ),
}


__all__ = ["APPROVER", "MESSAGES", "Verdict", "action_hash", "gate", "verdict_of"]
