"""Spec 048 — a client that still books with ``booking.*``, for the pass to
Reservas tests (the activation from Acceso, the automatic pass at deploy time
and its isolation case).

An agent whose version names ``booking.*`` in the four places the pass rewrites:
``tools``, the AgentSpec (``tools`` and a procedure) and the text. Appointments
of ``appointments`` with their customer and their barber (a ``Barber`` node of
the graph, as ``booking.*`` writes them).
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Appointment,
    AppointmentStatus,
    BusinessProfile,
    Customer,
    KGNode,
)
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite
from tests.unit.test_agent_spec_contract import STRUCTURED

BOOKING = ["booking.check_availability", "booking.create_appointment"]
PROMPT = (
    "Eres la recepción. Antes de prometer una hora llama a "
    "booking.check_availability; para reservar, booking.create_appointment."
)

T = TypeVar("T")


def spec_with_booking() -> dict[str, Any]:
    doc = copy.deepcopy(STRUCTURED)
    doc["tools"] = [*BOOKING, "escalate.escalate_to_human"]
    doc["procedures"][0]["tools"] = list(BOOKING)
    doc["procedures"][0]["steps"] = (
        "Mira el hueco con booking.check_availability y reserva con booking.create_appointment."
    )
    doc["services"] = {"mode": "all"}
    doc["reception"] = {"enabled": False}
    doc.pop("test_suite", None)
    return doc


def booking_version(
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    version: int,
    *,
    status: AgentConfigStatus = AgentConfigStatus.ACTIVE,
    template: str | None = None,
    extra_prompt: str = "",
) -> AgentConfig:
    """A version that books with ``booking.*`` in the four places."""
    return AgentConfig(
        tenant_id=tenant_id,
        agent_id=agent_id,
        version=version,
        status=status,
        system_prompt_rendered=PROMPT + extra_prompt,
        channels=[],
        tools=[*BOOKING, "escalate.escalate_to_human"],
        policies={"console": {}, "kept": "as it was"},
        spec=spec_with_booking(),
        seed_template_ref=template,
        runtime_memory_tool=True,
        created_by="test",
    )


def plain_version(
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    version: int,
    *,
    status: AgentConfigStatus = AgentConfigStatus.ACTIVE,
) -> AgentConfig:
    """A version that does not book at all."""
    return AgentConfig(
        tenant_id=tenant_id,
        agent_id=agent_id,
        version=version,
        status=status,
        system_prompt_rendered="Eres el agente de ventas.",
        channels=[],
        tools=["escalate.escalate_to_human"],
        policies={},
        created_by="test",
    )


async def agent_with_booking(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str = "Recepción",
    template: str | None = None,
    draft: bool = False,
    tests: bool = False,
    first_version: int = 1,
) -> uuid.UUID:
    """An active agent whose active version books with ``booking.*``. With
    ``draft``, a partner's draft that also names it and changes something else
    (a sentence of the text). With ``tests``, a test suite with one test, fresh."""
    agent = Agent(tenant_id=tenant_id, name=name)
    db_session.add(agent)
    await db_session.flush()
    active = booking_version(tenant_id, agent.id, first_version, template=template)
    db_session.add(active)
    await db_session.flush()
    if draft:
        staged = booking_version(
            tenant_id,
            agent.id,
            first_version + 1,
            status=AgentConfigStatus.STAGED,
            template=template,
            extra_prompt=" Somos la mejor barbería del barrio.",
        )
        staged.base_version_id = active.id
        db_session.add(staged)
    if tests:
        suite = AgentTestSuite(id=uuid.uuid4(), tenant_id=tenant_id, agent_id=agent.id)
        db_session.add(suite)
        await db_session.flush()
        db_session.add(
            AgentTest(
                tenant_id=tenant_id,
                suite_id=suite.id,
                kind="case",
                name="Reserva un corte",
                first_message="Hola, ¿tienes hora mañana?",
            )
        )
    await db_session.commit()
    return agent.id


async def customer(db_session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    cust = Customer(
        tenant_id=tenant_id,
        identifier=f"5691{uuid.uuid4().int % 10**7:07d}",
        name="Ana Pérez",
        preferences={},
    )
    db_session.add(cust)
    await db_session.flush()
    return cust.id


async def barber(db_session: AsyncSession, tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    node = KGNode(tenant_id=tenant_id, label="Barber", properties={"name": name})
    db_session.add(node)
    await db_session.flush()
    return node.id


def appointment(
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    barber_id: uuid.UUID | None,
    service: str,
    starts_at: datetime,
    *,
    status: AppointmentStatus = AppointmentStatus.BOOKED,
    minutes: int = 30,
) -> Appointment:
    return Appointment(
        tenant_id=tenant_id,
        customer_id=customer_id,
        barber_id=barber_id,
        service_name=service,
        service_duration_min=minutes,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        price_cents=15000,
        currency="CLP",
        status=status,
        idempotency_key=f"legacy-{uuid.uuid4().hex[:12]}",
    )


async def business_sector(db_session: AsyncSession, tenant_id: uuid.UUID, key: str | None) -> None:
    """The client's business profile, with its saved sector (or none yet)."""
    sector = (
        {"key": key, "label": key, "confidence": 0.9, "source": "niche", "decided_by": "system"}
        if key is not None
        else None
    )
    db_session.add(
        BusinessProfile(
            tenant_id=tenant_id, niche="Negocio", timezone="America/Santiago", sector=sector
        )
    )
    await db_session.commit()


async def read(tenant_id: uuid.UUID, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Read as the client, under its RLS."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await fn(session)


__all__ = [
    "BOOKING",
    "PROMPT",
    "agent_with_booking",
    "appointment",
    "barber",
    "booking_version",
    "business_sector",
    "customer",
    "plain_version",
    "read",
    "spec_with_booking",
]
