"""Spec 065, T063 (requisitos 6.2 y 6.3): cambiar el modelo de un agente no toca sus pruebas.

- No crea trabajos de pruebas (``Job``) ni versiones; eso lo fija ya
  ``test_agent_model_console.py``.
- No toca ``agents.tests_pass_returned_at`` (la pasada gratis que Auphere devuelve cuando
  cambia algo por su cuenta, spec 047, 68.14): ni el cambio del partner ni el de Auphere.
- Quién paga la pasada siguiente es lo mismo antes y después (``billing.next_full_pass``,
  requisito 68): probar el agente con otro modelo es una pasada como cualquier otra.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent
from nexus_api.services.agent_model import set_agent_model
from nexus_api.services.testing import billing
from tests.integration.models.test_agent_model_console import _catalog, agent_of, url  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"


async def _state(a: dict, agent) -> tuple[datetime | None, str]:  # type: ignore[type-arg]
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        returned = await session.scalar(
            sa.select(Agent.tests_pass_returned_at).where(Agent.id == agent)
        )
        payer = await billing.next_full_pass(
            session, agent_id=agent, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
        )
    return returned, payer


async def test_changing_the_model_leaves_the_passes_as_they_were(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    returned_at = datetime.now(UTC) - timedelta(days=3)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        await session.execute(
            sa.update(Agent).where(Agent.id == agent).values(tests_pass_returned_at=returned_at)
        )
        await session.commit()
    before = await _state(a, agent)

    by_partner = await client.put(
        url(a["ref"], agent), headers=a["headers"](), json={"model_id": TERRA}
    )
    assert by_partner.status_code == 200, by_partner.text
    assert await _state(a, agent) == before

    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        await set_agent_model(
            session,
            agent_id=agent,
            model_id=LUNA,
            set_by="operator",
            actor="operator:ops@auphere.com",
            allowed=None,
            action="admin.agent.model.update",
            reason="prueba",
        )
        await session.commit()
    after = await _state(a, agent)
    assert after == before, "un cambio de Auphere tampoco devuelve ni quita la pasada"
    assert after[0] == returned_at
