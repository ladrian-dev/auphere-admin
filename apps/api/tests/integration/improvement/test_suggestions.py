"""Spec 047, T173 — rendimiento y sugerencias (historia 31; requisito 51).

- **Rendimiento**: los últimos 30 días del agente, con su gráfica por días:
  conversaciones, resueltas sin persona, pasadas a una persona, gasto y gasto
  medio por conversación (a precio, nunca coste: C9).
- **Conversaciones**: solo metadatos (fecha, canal, duración, mensajes,
  resultado, motivo del traspaso y gasto); ni cuerpos ni datos del cliente final
  (C1 y C8).
- **Sugerencias**: agrupan al menos 5 conversaciones de al menos 5 contactos, con
  una paráfrasis sin datos personales y una propuesta con su diff y su prueba.
- **Aceptar**: el cambio y su prueba van al borrador y pasan la puerta al guardar.
- **Descartar**: pide el motivo y no vuelve en 30 días.
- **Dónde se generan**: en el worker, dentro del cliente (RLS y contexto), una
  llamada por agente; a la API solo sale lo agregado.
- **Medidor**: la partida «Construcción y pruebas» (``source = suggestions``).

El modelo es de mentira (:class:`FakeModel`): agrupa lo que se le pida y anota
sus tokens por el mismo punto de paso que el proveedor de verdad.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import get_current_tenant, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AgentSuggestion,
    AuditLog,
    ConsoleNotification,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Partner,
    PartnerAllocation,
    UsageRecord,
)
from nexus_api.services.improvement import suggestions as svc
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business
from ..clients._client_world import add_agent

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

RULE = "Si preguntan por el aparcamiento, di que hay un parking público en la calle de atrás."
PARKING_TEST = {
    "name": "Pregunta por el aparcamiento",
    "persona": "Cliente que viene en coche",
    "first_message": "¿Hay sitio para aparcar cerca?",
    "plan": "Pregunta una vez y da las gracias.",
    "criteria": [{"key": "parking", "text": "Dice dónde se puede aparcar."}],
}


def parking(refs: list[str], **changes: Any) -> dict[str, Any]:
    """Un tema bien hecho: la paráfrasis, el parche y la prueba."""
    topic: dict[str, Any] = {
        "key": "aparcamiento",
        "topic": "Preguntaron por el aparcamiento y el agente no supo responder.",
        "summary": "Que el agente sepa dónde se aparca",
        "conversations": refs,
        "ops": [{"op": "add", "path": "/rules/-", "value": RULE}],
        "test": dict(PARKING_TEST),
    }
    topic.update(changes)
    return topic


@dataclass
class FakeModel:
    """El modelo de las sugerencias. ``topics`` recibe las referencias de las
    conversaciones que le llegaron (``c1``, ``c2``…) y devuelve los temas."""

    topics: Callable[[list[str]], list[dict[str, Any]]] = field(
        default=lambda refs: [parking(refs)]
    )
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    tenants: list[uuid.UUID | None] = field(default_factory=list)
    #: El partner atado al proxy en cada llamada: con el proxy obligatorio
    #: (staging), sin él la llamada no sale.
    partners: list[uuid.UUID | None] = field(default_factory=list)

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        from nexus_worker.metering.collector import record_llm_usage

        from nexus_api.core.llm_proxy import current_llm_proxy_partner

        self.calls.append(messages)
        self.tenants.append(get_current_tenant())
        self.partners.append(current_llm_proxy_partner())
        record_llm_usage(
            model="anthropic/claude-haiku-5-5",
            provider="anthropic",
            usage={"prompt_tokens": 4000, "completion_tokens": 600},
            task="summarize",
        )
        refs = re.findall(r'title="(c\d+)"', self.prompt)
        return json.dumps({"suggestions": self.topics(refs)})

    @property
    def prompt(self) -> str:
        assert self.calls, "nadie llamó al modelo"
        return "\n".join(m["content"] for m in self.calls[-1])


@dataclass
class World:
    biz: Biz
    agent_id: uuid.UUID
    channel_id: uuid.UUID
    sibling_id: uuid.UUID
    sibling_channel_id: uuid.UUID

    def url(self, agent_id: uuid.UUID | None = None) -> str:
        return f"/console/clients/{self.biz.ref}/agents/{agent_id or self.agent_id}"


@pytest.fixture
async def world(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> World:
    biz = await new_business(client, db_session, console_world, name="Clínica Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    mine = await add_agent(db_session, biz.tenant_id, "Recepción")
    sibling = await add_agent(db_session, biz.tenant_id, "Ventas")
    await db_session.commit()
    assert mine["channel_id"] is not None and sibling["channel_id"] is not None
    return World(
        biz=biz,
        agent_id=mine["agent_id"],  # type: ignore[arg-type]
        channel_id=mine["channel_id"],
        sibling_id=sibling["agent_id"],  # type: ignore[arg-type]
        sibling_channel_id=sibling["channel_id"],
    )


@dataclass
class Seeded:
    conversations: list[uuid.UUID]
    names: list[str]
    phones: list[str]
    bodies: list[str]


async def seed(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    at: datetime,
    contacts: int,
    per_contact: int = 1,
    escalated: bool = True,
    agent_id: uuid.UUID | None = None,
    mark: str = "",
) -> Seeded:
    """``contacts`` clientes finales, cada uno con ``per_contact`` conversaciones:
    una pregunta (con su marca) y la respuesta del agente un minuto después."""
    out = Seeded([], [], [], [])
    # Solo letras: una marca con siete cifras seguidas se taparía como un teléfono.
    tag = mark or "".join(chr(ord("A") + int(c, 16) % 26) for c in uuid.uuid4().hex[:6])
    async with tenant_scoped_session(db_session, tenant_id):
        for i in range(contacts):
            name = f"Mariela{tag}{i} Quintanilla"
            phone = f"+5491166{uuid.uuid4().int % 10**6:06d}"
            customer = Customer(id=uuid.uuid4(), tenant_id=tenant_id, identifier=phone, name=name)
            db_session.add(customer)
            await db_session.flush()
            out.names.append(name)
            out.phones.append(phone)
            for j in range(per_contact):
                started = at + timedelta(minutes=10 * (i * per_contact + j))
                conv = Conversation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    customer_id=customer.id,
                    status=ConversationStatus.ESCALATED if escalated else ConversationStatus.CLOSED,
                    waiting_reason="escalated" if escalated else None,
                    created_at=started,
                    last_inbound_at=started,
                    last_message_at=started + timedelta(minutes=1),
                )
                db_session.add(conv)
                await db_session.flush()
                body = f"CUERPO-{tag}-{i}-{j}: ¿dónde puedo aparcar? soy {name}, {phone}"
                db_session.add_all(
                    [
                        Message(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            conversation_id=conv.id,
                            direction=MessageDirection.INBOUND,
                            status=MessageStatus.DELIVERED,
                            content=body,
                            origin="customer",
                            created_at=started,
                        ),
                        Message(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            conversation_id=conv.id,
                            direction=MessageDirection.OUTBOUND,
                            status=MessageStatus.SENT,
                            content=f"RESPUESTA-{tag}: no lo sé, te paso con el equipo.",
                            actor_kind="agent",
                            agent_id=agent_id,
                            origin="agent",
                            created_at=started + timedelta(minutes=1),
                        ),
                    ]
                )
                out.conversations.append(conv.id)
                out.bodies.append(body)
        await db_session.flush()
    return out


async def spend(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    *,
    cost_usd: float,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    source: str = "channel",
    at: datetime | None = None,
) -> None:
    await db_session.execute(
        sa.text(
            "INSERT INTO usage_records (tenant_id, partner_id, occurred_at, meter, quantity, "
            " cost_usd, billable_qty, provider, model, idempotency_key, source, agent_id, "
            " conversation_id) VALUES (:t, :p, :at, 'llm.output_tokens', 1000, :cost, 1000, "
            " 'anthropic', 'anthropic/claude-haiku-5-5', :key, :source, :agent, :conv)"
        ),
        {
            "t": str(tenant_id),
            "p": str(partner_id),
            "at": at or datetime.now(UTC) - timedelta(days=2),
            "cost": cost_usd,
            "key": f"t173-{uuid.uuid4().hex}",
            "source": source,
            "agent": str(agent_id),
            "conv": str(conversation_id) if conversation_id else None,
        },
    )
    await db_session.commit()


def last_week(now: datetime) -> datetime:
    """Un momento dentro de la semana que lee la pasada de ``now``."""
    _week, since, _until = svc.analyzed_week(now)
    return since + timedelta(days=2, hours=10)


async def generate(model: FakeModel, *, now: datetime | None = None) -> int:
    """La pasada semanal del worker, con el modelo de mentira."""
    from nexus_worker.streams.weekly_suggestions_cron import suggestions_tick

    return await suggestions_tick(complete_factory=lambda _tenant: model, now=now)


async def suggestions_of(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> list[AgentSuggestion]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = list(
            (
                await session.scalars(
                    sa.select(AgentSuggestion)
                    .where(AgentSuggestion.agent_id == agent_id)
                    .order_by(AgentSuggestion.created_at)
                )
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


# ── Rendimiento: 30 días ────────────────────────────────────────────────────


async def test_performance_shows_the_last_30_days_of_this_agent(
    client: Any, db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    handed = await seed(
        db_session, tenant, world.channel_id, at=now - timedelta(days=2), contacts=1
    )
    solved = await seed(
        db_session,
        tenant,
        world.channel_id,
        at=now - timedelta(days=5),
        contacts=2,
        escalated=False,
    )
    # Fuera: de hace 40 días, y las del hermano.
    await seed(db_session, tenant, world.channel_id, at=now - timedelta(days=40), contacts=1)
    sibling = await seed(
        db_session, tenant, world.sibling_channel_id, at=now - timedelta(days=1), contacts=2
    )
    await db_session.commit()
    partner = world.biz.partner_id
    await spend(
        db_session,
        tenant,
        partner,
        cost_usd=0.5,
        agent_id=world.agent_id,
        conversation_id=handed.conversations[0],
    )
    await spend(
        db_session,
        tenant,
        partner,
        cost_usd=0.25,
        agent_id=world.agent_id,
        conversation_id=solved.conversations[0],
    )
    # No son conversaciones: el constructor, y el gasto del hermano.
    await spend(
        db_session,
        tenant,
        partner,
        cost_usd=9.0,
        agent_id=world.agent_id,
        conversation_id=None,
        source="builder",
    )
    await spend(
        db_session,
        tenant,
        partner,
        cost_usd=7.0,
        agent_id=world.sibling_id,
        conversation_id=sibling.conversations[0],
    )

    resp = await client.get(f"{world.url()}/performance", headers=world.biz.headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"] == 30
    assert body["conversations"] == 3
    assert body["handed_to_person"] == 1
    assert body["resolved_without_person"] == 2
    # 0,75 US$ de coste a 2,2 = 1,65 US$, en cien milésimas.
    assert body["spent"] == {"amount_micros": 165_000, "currency": "USD"}
    assert body["spend_per_conversation"] == {"amount_micros": 55_000, "currency": "USD"}
    assert len(body["series"]) == 30
    assert sum(d["conversations"] for d in body["series"]) == 3
    assert sum(d["handed_to_person"] for d in body["series"]) == 1
    assert sum(d["spent"]["amount_micros"] for d in body["series"]) == 165_000
    assert "cost" not in resp.text

    week = await client.get(
        f"{world.url()}/performance", params={"days": 3}, headers=world.biz.headers()
    )
    assert week.status_code == 200
    assert week.json()["conversations"] == 1 and len(week.json()["series"]) == 3


# ── Conversaciones: solo metadatos ──────────────────────────────────────────


async def test_the_conversations_list_carries_only_metadata(
    client: Any, db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    handed = await seed(
        db_session, tenant, world.channel_id, at=now - timedelta(hours=5), contacts=1
    )
    solved = await seed(
        db_session,
        tenant,
        world.channel_id,
        at=now - timedelta(hours=8),
        contacts=2,
        escalated=False,
    )
    sibling = await seed(
        db_session, tenant, world.sibling_channel_id, at=now - timedelta(hours=1), contacts=1
    )
    await db_session.commit()
    await spend(
        db_session,
        tenant,
        world.biz.partner_id,
        cost_usd=0.5,
        agent_id=world.agent_id,
        conversation_id=handed.conversations[0],
    )

    first = await client.get(
        f"{world.url()}/conversations", params={"limit": 2}, headers=world.biz.headers()
    )
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = await client.get(
        f"{world.url()}/conversations",
        params={"limit": 2, "cursor": page["next_cursor"]},
        headers=world.biz.headers(),
    )
    assert rest.status_code == 200, rest.text
    items = page["items"] + rest.json()["items"]
    assert rest.json()["next_cursor"] is None
    ids = [uuid.UUID(i["id"]) for i in items]
    expected = [handed.conversations[0], *reversed(solved.conversations)]
    assert ids == expected, "de la más reciente a la más antigua"

    newest = items[0]
    assert newest["channel_type"] == "whatsapp"
    assert newest["messages_count"] == 2
    assert newest["duration_seconds"] == 60
    assert newest["outcome"] == "handed_to_person"
    assert newest["handoff_reason"] == "escalated"
    assert newest["spent"] == {"amount_micros": 110_000, "currency": "USD"}
    assert items[1]["outcome"] == "resolved_without_person"
    assert items[1]["handoff_reason"] is None and items[1]["spent"] is None

    text = first.text + rest.text
    for word in [*handed.bodies, *solved.bodies, *handed.names, *handed.phones, *solved.phones]:
        assert word not in text, f"la lista de conversaciones devuelve {word!r}"
    assert "RESPUESTA-" not in text
    assert str(sibling.conversations[0]) not in text, "la del hermano no es de este agente"


# ── Sugerencias: ≥ 5 conversaciones de ≥ 5 contactos ───────────────────────


async def test_a_suggestion_groups_five_conversations_of_five_contacts(
    db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    # Cinco contactos con una conversación y, un día después, uno que escribió
    # tres veces: el modelo las recibe en orden (``c1``…``c5`` y ``c6``…``c8``).
    await seed(db_session, tenant, world.channel_id, at=last_week(now), contacts=5)
    await seed(
        db_session,
        tenant,
        world.channel_id,
        at=last_week(now) + timedelta(days=1),
        contacts=1,
        per_contact=3,
    )
    await db_session.commit()

    def topics(refs: list[str]) -> list[dict[str, Any]]:
        assert refs == [f"c{n}" for n in range(1, 9)], refs
        return [
            # Las ocho: seis contactos distintos.
            parking(refs),
            # Cinco conversaciones, pero de tres contactos.
            parking(refs[3:], key="horario", topic="Preguntaron por el horario de agosto."),
            # Cuatro conversaciones de cuatro contactos.
            parking(refs[:4], key="precios", topic="Preguntaron por los precios."),
            # Lo que el modelo diga contar no cuenta: se cuentan las referencias.
            {**parking([], key="todas", topic="Todos preguntaron algo."), "conversations": "c1-c8"},
            # Una referencia que no se le dio no existe.
            parking(["c1", "c2", "c3", "c90", "c91"], key="inventadas", topic="Otra cosa."),
        ]

    model = FakeModel(topics=topics)
    assert await generate(model, now=now) == 1
    rows = await suggestions_of(tenant, world.agent_id)
    assert [r.topic_key for r in rows] == ["aparcamiento"]
    assert rows[0].conversations_count == 8
    assert rows[0].contacts_count == 6
    assert rows[0].week == svc.analyzed_week(now)[0]


async def test_three_contacts_writing_many_times_are_not_a_suggestion(
    db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    await seed(
        db_session,
        world.biz.tenant_id,
        world.channel_id,
        at=last_week(now),
        contacts=3,
        per_contact=3,
    )
    await db_session.commit()
    model = FakeModel()
    assert await generate(model, now=now) == 0
    assert await suggestions_of(world.biz.tenant_id, world.agent_id) == []
    # Ni siquiera se le pregunta al modelo: con menos de 5 contactos no hay tema.
    assert model.calls == []


# ── Paráfrasis sin datos personales, propuesta con su diff y su prueba ──────


async def test_a_suggestion_carries_a_paraphrase_a_diff_and_a_test(
    client: Any, db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    seeded = await seed(db_session, tenant, world.channel_id, at=last_week(now), contacts=6)
    await db_session.commit()
    name, phone = seeded.names[0], seeded.phones[1]

    def rule(text: str) -> list[dict[str, Any]]:
        return [{"op": "add", "path": "/rules/-", "value": text}]

    def topics(refs: list[str]) -> list[dict[str, Any]]:
        return [
            parking(refs),
            # Con el nombre de un cliente final en la paráfrasis.
            parking(
                refs,
                key="nombre",
                topic=f"{name} preguntó por el aparcamiento.",
                ops=rule("Habla del parking de la plaza."),
            ),
            # Con su teléfono en la prueba.
            parking(
                refs,
                key="telefono",
                ops=rule("Da la dirección del parking."),
                test={**PARKING_TEST, "first_message": f"Soy el {phone}, ¿hay parking?"},
            ),
            # Con un correo en el parche.
            parking(
                refs,
                key="correo",
                ops=rule("Si insisten, que escriban a mariela.q@example.com."),
            ),
            # Sin prueba.
            {**parking(refs, key="sin_prueba", ops=rule("Ofrece el parking.")), "test": None},
            # Tocando lo que una sugerencia no toca.
            parking(
                refs,
                key="herramientas",
                ops=[{"op": "add", "path": "/tools/-", "value": "reservas.create"}],
            ),
            # Un parche que no aplica.
            parking(refs, key="roto", ops=[{"op": "replace", "path": "/nada/0", "value": 1}]),
        ]

    model = FakeModel(topics=topics)
    assert await generate(model, now=now) == 1
    # El modelo leyó las conversaciones (dentro del cliente), con el nombre y el
    # teléfono del contacto tapados…
    assert seeded.bodies[0].split(":")[0] in model.prompt
    assert "[cliente]" in model.prompt and "[teléfono]" in model.prompt
    for word in [*seeded.names, *seeded.phones]:
        assert word not in model.prompt

    resp = await client.get(f"{world.url()}/improvements", headers=world.biz.headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed"] == ["accept", "discard"]
    [item] = body["items"]
    assert item["kind"] == "suggestion"
    assert item["topic"] == "Preguntaron por el aparcamiento y el agente no supo responder."
    assert item["conversations_count"] == 6 and item["contacts_count"] == 6
    assert item["diff"] == {"ops": [{"op": "add", "path": "/rules/-", "value": RULE}]}
    assert item["test"]["first_message"] == PARKING_TEST["first_message"]
    assert item["test"]["criteria"] == PARKING_TEST["criteria"]
    # …y a la consola solo sale lo agregado.
    for word in [*seeded.bodies, *seeded.names, *seeded.phones]:
        assert word not in resp.text
    for conv in seeded.conversations:
        assert str(conv) not in resp.text


#: Lo que contó de verdad un cliente final, sin nombre ni teléfono: el enmascarado
#: no lo toca y el modelo lo lee tal cual.
REAL_STORY = (
    "Mi hija tiene alergia a la penicilina y la última vez le pusieron una inyección "
    "que la dejó fatal toda la semana"
)


async def test_a_test_that_copies_a_real_message_is_dropped(
    db_session: AsyncSession, world: World
) -> None:
    """Spec 047, T217 (revisión de seguridad del 2026-10-30): la prueba de una
    sugerencia la escribe un modelo que leyó conversaciones reales. Si su primer
    mensaje, su persona o su plan copian casi al pie de la letra un mensaje del
    lote, la sugerencia no se guarda: esa prueba acabaría en «Por qué falló»."""
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    seeded = await seed(db_session, tenant, world.channel_id, at=last_week(now), contacts=5)
    async with tenant_scoped_session(db_session, tenant):
        first = await db_session.get(Conversation, seeded.conversations[0])
        assert first is not None
        db_session.add(
            Message(
                id=uuid.uuid4(),
                tenant_id=tenant,
                conversation_id=first.id,
                direction=MessageDirection.INBOUND,
                status=MessageStatus.DELIVERED,
                content=REAL_STORY + ".",
                origin="customer",
                created_at=first.created_at + timedelta(seconds=30),
            )
        )
    await db_session.commit()

    def rule(text: str) -> list[dict[str, Any]]:
        return [{"op": "add", "path": "/rules/-", "value": text}]

    copied = "¡" + REAL_STORY.upper() + "!"  # otra caja y otra puntuación

    def topics(refs: list[str]) -> list[dict[str, Any]]:
        return [
            parking(refs),
            parking(
                refs,
                key="primer_mensaje",
                ops=rule("Pregunta por alergias antes de reservar."),
                test={**PARKING_TEST, "first_message": copied},
            ),
            parking(
                refs,
                key="persona",
                ops=rule("Pregunta por alergias al dar cita."),
                test={**PARKING_TEST, "persona": f"Una madre que cuenta: {REAL_STORY}"},
            ),
            parking(
                refs,
                key="plan",
                ops=rule("Ofrece pasar con el equipo si hay alergias."),
                test={**PARKING_TEST, "plan": f"Cuenta que {REAL_STORY.lower()} y pide cita."},
            ),
            # Una frase corta y corriente que también dijo alguien no es una copia.
            parking(
                refs,
                key="corriente",
                ops=rule("Di que el parking está en la calle de atrás."),
                test={**PARKING_TEST, "first_message": "Hola, ¿dónde puedo aparcar?"},
            ),
        ]

    model = FakeModel(topics=topics)
    assert await generate(model, now=now) == 2
    assert REAL_STORY in model.prompt, "el modelo leyó el mensaje de verdad"
    keys = {r.topic_key for r in await suggestions_of(tenant, world.agent_id)}
    assert keys == {"aparcamiento", "corriente"}


# ── Aceptar: al borrador, y por la puerta ───────────────────────────────────


async def test_accepting_puts_the_change_and_its_test_in_the_draft_behind_the_gate(
    client: Any, db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    await seed(db_session, world.biz.tenant_id, world.channel_id, at=last_week(now), contacts=5)
    await db_session.commit()
    assert await generate(FakeModel(), now=now) == 1
    async with tenant_scoped_session(db_session, world.biz.tenant_id):
        active_before = await db_session.scalar(
            sa.select(AgentConfig.id).where(
                AgentConfig.agent_id == world.agent_id,
                AgentConfig.status == AgentConfigStatus.ACTIVE,
            )
        )
    listed = (await client.get(f"{world.url()}/improvements", headers=world.biz.headers())).json()
    sid = listed["items"][0]["id"]

    # Un hermano no alcanza la sugerencia (garantía 9) y un analyst no decide.
    foreign = await client.post(
        f"{world.url(world.sibling_id)}/improvements/{sid}/accept", headers=world.biz.headers()
    )
    assert foreign.status_code == 404, foreign.text
    analyst = await add_console_member(db_session, partner_id=world.biz.partner_id, role="analyst")
    seen = await client.get(f"{world.url()}/improvements", headers=analyst["headers"]())
    assert seen.status_code == 200 and seen.json()["allowed"] == []
    denied = await client.post(
        f"{world.url()}/improvements/{sid}/accept", headers=analyst["headers"]()
    )
    assert denied.status_code == 403

    resp = await client.post(
        f"{world.url()}/improvements/{sid}/accept", headers=world.biz.headers()
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "accepted" and out["draft_revision"] >= 1 and out["test_id"]

    draft = (await client.get(f"{world.url()}/draft", headers=world.biz.headers())).json()
    assert draft["exists"] is True
    assert RULE in (draft["spec"].get("rules") or [])
    suite = (await client.get(f"{world.url()}/tests", headers=world.biz.headers())).json()
    [added] = [t for t in suite["tests"] if t["id"] == out["test_id"]]
    assert added["kind"] == "conversation"
    assert added["name"] == PARKING_TEST["name"] and added["status"] == "not_run"

    # No se publica sola: la versión activa es la misma y «Guardar» pasa la puerta.
    async with tenant_scoped_session(db_session, world.biz.tenant_id):
        active_after = await db_session.scalar(
            sa.select(AgentConfig.id).where(
                AgentConfig.agent_id == world.agent_id,
                AgentConfig.status == AgentConfigStatus.ACTIVE,
            )
        )
    assert active_after == active_before
    preview = (
        await client.get(f"{world.url()}/publish-preview", headers=world.biz.headers())
    ).json()
    assert preview["has_draft"] is True
    assert "rules" in {row["part"] for row in preview["diff"]}
    assert preview["gate"] is not None and preview["gate"]["conditions"]

    async with tenant_scoped_session(db_session, world.biz.tenant_id):
        audit = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == "suggestion.accepted")
            )
        ).all()
    assert len(audit) == 1 and audit[0].target == f"agent:{world.agent_id}"
    assert audit[0].after_json and audit[0].after_json["suggestion_id"] == sid

    again = await client.post(
        f"{world.url()}/improvements/{sid}/accept", headers=world.biz.headers()
    )
    assert again.status_code == 409 and again.json()["detail"]["code"] == "improvement_closed"
    left = (await client.get(f"{world.url()}/improvements", headers=world.biz.headers())).json()
    assert left["items"] == []


# ── Descartar: con motivo, y 30 días sin volver ─────────────────────────────


async def test_discarding_asks_why_and_keeps_it_away_30_days(
    client: Any, db_session: AsyncSession, world: World
) -> None:
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    await seed(db_session, tenant, world.channel_id, at=last_week(now), contacts=5)
    await db_session.commit()
    model = FakeModel()
    assert await generate(model, now=now) == 1
    sid = (await client.get(f"{world.url()}/improvements", headers=world.biz.headers())).json()[
        "items"
    ][0]["id"]

    no_reason = await client.post(
        f"{world.url()}/improvements/{sid}/discard", json={}, headers=world.biz.headers()
    )
    assert no_reason.status_code == 422
    resp = await client.post(
        f"{world.url()}/improvements/{sid}/discard",
        json={"reason": "Ya lo explica el cartel de la puerta"},
        headers=world.biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "discarded"
    until = datetime.fromisoformat(resp.json()["suppress_until"])
    assert timedelta(days=29) < until - datetime.now(UTC) <= timedelta(days=30)
    async with tenant_scoped_session(db_session, tenant):
        audit = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "suggestion.discarded")
        )
    assert audit is not None and audit.after_json
    assert audit.after_json["discard_reason"] == "Ya lo explica el cartel de la puerta"

    # La semana siguiente, lo mismo: no vuelve.
    next_week = now + timedelta(days=7)
    await seed(db_session, tenant, world.channel_id, at=last_week(next_week), contacts=5)
    await db_session.commit()
    assert await generate(model, now=next_week) == 0
    assert len(model.calls) == 2
    assert "aparcamiento" in model.prompt, "el modelo sabe qué no proponer"
    # Ni con otras palabras: el mismo parche también está apartado.
    renamed = FakeModel(topics=lambda refs: [parking(refs, key="parking_coches")])
    two_weeks = now + timedelta(days=14)
    await seed(db_session, tenant, world.channel_id, at=last_week(two_weeks), contacts=5)
    await db_session.commit()
    assert await generate(renamed, now=two_weeks) == 0

    # Pasados los 30 días, vuelve.
    later = now + timedelta(days=35)
    await seed(db_session, tenant, world.channel_id, at=last_week(later), contacts=5)
    await db_session.commit()
    assert await generate(model, now=later) == 1
    rows = await suggestions_of(tenant, world.agent_id)
    assert [r.status for r in rows] == ["discarded", "open"]


# ── Dónde se generan: en el worker, dentro del cliente ──────────────────────


async def test_suggestions_are_generated_in_the_worker_inside_each_client(
    client: Any, db_session: AsyncSession, world: World, console_world: dict[str, Any]
) -> None:
    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    mine = await seed(
        db_session,
        tenant,
        world.channel_id,
        at=last_week(now),
        contacts=5,
        agent_id=world.agent_id,
        mark="MIO",
    )
    theirs = await seed(
        db_session,
        tenant,
        world.sibling_channel_id,
        at=last_week(now),
        contacts=5,
        agent_id=world.sibling_id,
        mark="HERMANO",
    )
    # Otro partner con la consola nueva, su cliente y su agente.
    b = console_world["b"]
    partner_b = await db_session.get(Partner, b["partner_id"])
    assert partner_b is not None
    partner_b.console_v2_enabled_at = now
    await db_session.commit()
    other = await add_agent(db_session, b["tenant_id"], "Recepción B")
    assert other["channel_id"] is not None
    foreign = await seed(
        db_session, b["tenant_id"], other["channel_id"], at=last_week(now), contacts=5, mark="AJENO"
    )
    await db_session.commit()

    model = FakeModel()
    assert await generate(model, now=now) == 3
    # Una llamada por agente, cada una con el cliente puesto y solo con lo suyo.
    assert len(model.calls) == 3
    assert sorted(map(str, model.tenants)) == sorted(map(str, [tenant, tenant, b["tenant_id"]]))
    # Cada llamada sale con la clave de su partner y nunca con la de otro
    # (fallo el-constructor-no-llega-al-modelo-en-staging).
    partner_of = {tenant: world.biz.partner_id, b["tenant_id"]: b["partner_id"]}
    assert model.partners == [partner_of[t] for t in model.tenants if t is not None]
    prompts = ["\n".join(m["content"] for m in call) for call in model.calls]
    for prompt, seen_tenant in zip(prompts, model.tenants, strict=True):
        groups = [
            any(body.split(":")[0] in prompt for body in group.bodies)
            for group in (mine, theirs, foreign)
        ]
        assert sum(groups) == 1, "una llamada no mezcla agentes ni clientes"
        if seen_tenant == b["tenant_id"]:
            assert groups == [False, False, True]

    # La fila es del cliente: con otro cliente puesto no existe.
    async with get_sessionmaker()() as session, tenant_scoped_session(session, b["tenant_id"]):
        visible = await session.scalar(
            sa.select(sa.func.count())
            .select_from(AgentSuggestion)
            .where(AgentSuggestion.tenant_id == tenant)
        )
    assert visible == 0
    assert len(await suggestions_of(tenant, world.agent_id)) == 1
    assert len(await suggestions_of(tenant, world.sibling_id)) == 1

    # Una vez por agente y semana: otra pasada no llama al modelo ni avisa otra vez.
    assert await generate(model, now=now) == 0
    assert len(model.calls) == 3
    notices = (
        await db_session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.partner_id == world.biz.partner_id,
                ConsoleNotification.kind == "agent.suggestions.ready",
            )
        )
    ).all()
    assert sorted(n.payload["agent_id"] for n in notices) == sorted(
        [str(world.agent_id), str(world.sibling_id)]
    )
    bell = await client.get("/console/notifications", headers=world.biz.headers())
    assert bell.status_code == 200
    assert "tab=performance" in bell.text


# ── Medidor: «Construcción y pruebas» ───────────────────────────────────────


async def test_generating_is_metered_on_the_build_line(
    db_session: AsyncSession, world: World
) -> None:
    from nexus_worker.metering import consumer as metering

    from nexus_api.core import redis_client

    now = datetime.now(UTC)
    tenant = world.biz.tenant_id
    await seed(db_session, tenant, world.channel_id, at=last_week(now), contacts=5)
    await db_session.commit()
    before = await db_session.scalar(
        sa.select(PartnerAllocation.remaining).where(PartnerAllocation.tenant_id == tenant)
    )
    metering._partner_of.clear()
    assert await generate(FakeModel(), now=now) == 1
    await metering.drain_once(redis_client.get_redis(), consumer_name="t173")

    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant):
        rows = (
            await session.execute(
                sa.select(UsageRecord.source, UsageRecord.line, UsageRecord.agent_id).where(
                    UsageRecord.source == "suggestions"
                )
            )
        ).all()
    assert rows, "la pasada no se midió"
    assert {(r.source, r.line, r.agent_id) for r in rows} == {
        ("suggestions", "build", world.agent_id)
    }
    db_session.expire_all()
    after = await db_session.scalar(
        sa.select(PartnerAllocation.remaining).where(PartnerAllocation.tenant_id == tenant)
    )
    assert after == before, "no sale de la bolsa del cliente"
