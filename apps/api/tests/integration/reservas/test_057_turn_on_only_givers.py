"""Spec 057, historia 5 — encender Reservas solo toca a quien da citas (requisitos 5.1,
5.3 y 5.4; enmienda de la 043, 11.5).

Desde Acceso, solo los agentes activos que dan citas (prometen citas en su texto o
reservan en un conector) ganan la agenda, en un borrador sin publicar; el de cobros no
cambia. La lista de agentes lo dice (``agenda="prepared"``) y Acceso también, aunque el
borrador lo haya preparado una persona de la consola y no el operador.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus

from ..business._business_world import Biz, new_business

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_VERSION = iter(range(1, 1000))


def _spec(description: str, tools: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": "Agente", "description": description},
        "instructions": {"legacy_text": description},
        "tools": tools,
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "profile", "profile": "auto"},
        "memory": {"scope": "shared"},
    }


async def _agent(
    db_session: AsyncSession, biz: Biz, name: str, description: str, tools: list[str]
) -> uuid.UUID:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = Agent(tenant_id=biz.tenant_id, name=name)
        db_session.add(agent)
        await db_session.flush()
        db_session.add(
            AgentConfig(
                tenant_id=biz.tenant_id,
                agent_id=agent.id,
                version=next(_VERSION),
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=description,
                channels=[],
                tools=tools,
                policies={},
                spec=_spec(description, tools),
                created_by="test",
            )
        )
    return agent.id


async def _draft(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> AgentConfig | None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        return await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED)
            .execution_options(populate_existing=True)
        )


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Spa Jemma")


async def _turn_on(client: Any, biz: Biz) -> Any:
    resp = await client.put(
        f"/console/clients/{biz.ref}/client-access",
        json={
            "enabled": False,
            "modules": ["reservas"],
            "reservas": {"mode": "services", "capacity_kind": None},
        },
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_only_the_agents_that_give_appointments_get_a_draft(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    reception = await _agent(
        db_session,
        biz,
        "Recepción",
        "Agendas, cambias y cancelas citas del salón.",
        ["escalate.escalate_to_human"],
    )
    calendly = await _agent(
        db_session,
        biz,
        "Reservas web",
        "Atiendes la web del salón por WhatsApp.",
        ["CALENDLY_POST_INVITEE"],
    )
    billing = await _agent(
        db_session,
        biz,
        "Cobros",
        "Revisas los comprobantes de pago de las clientas.",
        ["payments.request_review"],
    )

    access = await _turn_on(client, biz)

    reception_draft = await _draft(db_session, biz, reception)
    assert reception_draft is not None and "reservas.create" in reception_draft.tools
    calendly_draft = await _draft(db_session, biz, calendly)
    assert calendly_draft is not None and "reservas.create" in calendly_draft.tools
    assert "CALENDLY_POST_INVITEE" not in calendly_draft.tools
    assert await _draft(db_session, biz, billing) is None

    # Acceso dice quién tiene la agenda preparada, aunque no lo preparara el operador.
    pending = {a["agent_id"] for a in access["reservas"]["agents_pending_promotion"]}
    assert {str(reception), str(calendly)} <= pending
    assert str(billing) not in pending

    cards = await client.get(f"/console/clients/{biz.ref}/agents", headers=biz.headers())
    assert cards.status_code == 200, cards.text
    agenda = {c["id"]: c["agenda"] for c in cards.json()}
    assert agenda[str(reception)] == "prepared"
    assert agenda[str(calendly)] == "prepared"
    assert agenda[str(billing)] == "none"


async def test_a_discarded_draft_does_not_come_back(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    reception = await _agent(
        db_session,
        biz,
        "Recepción",
        "Agendas, cambias y cancelas citas del salón.",
        ["escalate.escalate_to_human"],
    )
    await _turn_on(client, biz)
    assert await _draft(db_session, biz, reception) is not None
    url = f"/console/clients/{biz.ref}/agents/{reception}/draft"
    revision = (await client.get(url, headers=biz.headers())).json()["revision"]
    discard = await client.delete(url, headers={**biz.headers(), "If-Match": f'"{revision}"'})
    assert discard.status_code in (200, 204), discard.text
    # Apagar y volver a encender con la misma versión activa: no vuelve (043, 11.5).
    off = await client.put(
        f"/console/clients/{biz.ref}/client-access",
        json={"enabled": False, "modules": []},
        headers=biz.headers(),
    )
    assert off.status_code == 200, off.text
    await _turn_on(client, biz)
    assert await _draft(db_session, biz, reception) is None
    cards = await client.get(f"/console/clients/{biz.ref}/agents", headers=biz.headers())
    assert {c["id"]: c["agenda"] for c in cards.json()}[str(reception)] == "none"
