"""Un cliente con todo lo que el partner NUNCA debe ver, para los barridos de C8.

``test_console_scope`` (C1/C8: cuerpos y teléfonos) y ``test_52`` (además, C9:
costes) llaman a las rutas de ``/console/*`` del partner sobre este mundo y
buscan en cada respuesta las marcas de abajo. Sin datos así en la base, un
barrido de respuestas pasa en falso: una ruta que filtrara cuerpos devolvería
vacío porque no hay cuerpos.

Lo que se siembra en el cliente A de ``console_world``:

- la Bandeja de ``make_inbox`` (dos conversaciones con entrante y respuesta);
- una conversación más con marcas en todo lo que lleva palabras de alguien: el
  cuerpo entrante y el de la respuesta, la transcripción de un audio, la
  llamada a una herramienta y su resultado, la nota interna del contacto, y el
  nombre y el teléfono del cliente final;
- un coste de modelo con dígitos que no salen de ninguna otra cuenta, en el
  mensaje y en ``usage_records`` (lo que le cuesta a Auphere, C9);
- un trabajo (``jobs``) y el agente principal, para que las rutas con
  ``{job_id}`` o ``{agent_id}`` lleguen a un objeto real.

No es un test (empieza por ``_``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa

from nexus_api.db.models import (
    ContactNote,
    Conversation,
    ConversationStatus,
    Customer,
    Job,
    Message,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import make_inbox

from .conftest import seed_active_agent_config

#: Dígitos del coste de modelo sembrado. No salen de ninguna otra cuenta.
COST_DIGITS = "0987654321"
COST_USD = float(f"0.{COST_DIGITS}")


@dataclass(frozen=True)
class Canaries:
    body_in: str
    body_out: str
    transcript: str
    tool: str
    note: str
    name: str
    phone: str
    inbox_bodies: tuple[str, ...]
    inbox_phones: tuple[str, ...]

    def words_and_phones(self) -> dict[str, str]:
        """Lo que C1/C8 prohíben, con una etiqueta para el mensaje de error."""
        out = {
            "cuerpo entrante": self.body_in,
            "cuerpo de la respuesta": self.body_out,
            "transcripción": self.transcript,
            "llamada a herramienta": self.tool,
            "nota interna": self.note,
            "nombre del cliente final": self.name,
            "teléfono del cliente final": self.phone,
            # Sin el «+»: una ruta que lo normalice también filtra.
            "teléfono sin prefijo": self.phone.lstrip("+"),
        }
        for i, body in enumerate(self.inbox_bodies):
            out[f"cuerpo de la Bandeja {i}"] = body
        for i, phone in enumerate(self.inbox_phones):
            out[f"teléfono de la Bandeja {i}"] = phone
        return out


async def partner_world(db_session, console_world) -> dict[str, Any]:
    a = console_world["a"]
    tenant = a["tenant_id"]
    mark = uuid.uuid4().hex[:8].upper()
    cfg = await seed_active_agent_config(
        db_session, tenant_id=tenant, system_prompt="Agente de la tienda A", tools=[]
    )
    inbox = await make_inbox(
        db_session, partner_id=a["partner_id"], tenant_id=tenant, conversations=2
    )
    phones = tuple(
        (
            await db_session.execute(
                sa.select(Customer.identifier).where(Customer.id.in_(inbox["customers"]))
            )
        )
        .scalars()
        .all()
    )
    canaries = Canaries(
        body_in=f"CANARIO-CUERPO-{mark}",
        body_out=f"CANARIO-RESPUESTA-{mark}",
        transcript=f"CANARIO-AUDIO-{mark}",
        tool=f"CANARIO-HERRAMIENTA-{mark}",
        note=f"CANARIO-NOTA-{mark}",
        name=f"CANARIO-NOMBRE-{mark}",
        phone=f"+5491155{uuid.uuid4().int % 10**6:06d}",
        inbox_bodies=("Hola, soy el contacto 0", "Hola contacto 0, ¿en qué te ayudo?"),
        inbox_phones=phones,
    )

    now = datetime.now(UTC)
    customer = Customer(
        id=uuid.uuid4(), tenant_id=tenant, identifier=canaries.phone, name=canaries.name
    )
    db_session.add(customer)
    await db_session.flush()
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant,
        channel_id=inbox["channel_id"],
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
        last_inbound_at=now - timedelta(minutes=1),
        last_message_at=now,
        attended_at=now - timedelta(minutes=1),
        last_attended_inbound_at=now - timedelta(minutes=1),
    )
    db_session.add(conv)
    await db_session.flush()
    inbound = Message(
        id=uuid.uuid4(),
        tenant_id=tenant,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        content=canaries.body_in,
        media_kind="audio",
        media_transcript=canaries.transcript,
        created_at=now - timedelta(minutes=1),
    )
    outbound = Message(
        id=uuid.uuid4(),
        tenant_id=tenant,
        conversation_id=conv.id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.SENT,
        content=canaries.body_out,
        tool_calls=[
            {
                "tool": "client.get_history",
                "args": {"q": canaries.tool},
                "result": {"echo": canaries.tool},
            }
        ],
        actor_kind="agent",
        agent_id=cfg.agent_id,
        cost_usd=COST_USD,
        model="anthropic/claude-sonnet-4-6",
        created_at=now,
    )
    db_session.add_all([inbound, outbound])
    db_session.add(ContactNote(tenant_id=tenant, customer_id=customer.id, body=canaries.note))
    job = Job(
        tenant_id=tenant,
        agent_id=cfg.agent_id,
        kind="agent_draft",
        status="done",
        finished_at=now,
        result={"summary": "borrador listo"},
        cost_micros=int(COST_DIGITS),
        created_by=a["user_id"],
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.execute(
        sa.text(
            "INSERT INTO usage_records (tenant_id, partner_id, occurred_at, meter, quantity, "
            " cost_usd, billable_qty, provider, model, idempotency_key, source, agent_id, "
            " conversation_id) "
            "VALUES (:t, :p, :at, 'llm.output_tokens', 1000, :cost, 1000, 'anthropic', "
            " 'anthropic/claude-sonnet-4-6', :key, 'channel', :agent, :conv)"
        ),
        {
            "t": str(tenant),
            "p": str(a["partner_id"]),
            "at": now,
            "cost": COST_USD,
            "key": f"iso-c9-{mark}",
            "agent": str(cfg.agent_id),
            "conv": str(conv.id),
        },
    )
    await db_session.commit()
    return {
        "ref": a["ref"],
        "headers": a["headers"],
        # La persona del cliente, con Bandeja: el camino legítimo a los cuerpos.
        "client_headers": inbox["headers"],
        "canaries": canaries,
        # Los ``{param}`` de las rutas, hacia objetos reales del cliente A.
        "ids": {
            "channel_id": str(inbox["channel_id"]),
            "conversation_id": str(conv.id),
            "message_id": str(outbound.id),
            "agent_id": str(cfg.agent_id),
            "job_id": str(job.id),
            "id": str(job.id),
        },
    }
